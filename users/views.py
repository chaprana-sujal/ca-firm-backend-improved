# users/views.py
"""
Modernized user authentication views with security enhancements
"""

from rest_framework import generics, status
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
import logging

from .serializers import RegistrationSerializer, CustomUserSerializer

CustomUser = get_user_model()
logger = logging.getLogger(__name__)


class AuthRateThrottle(AnonRateThrottle):
    """Custom rate limiting for authentication endpoints"""
    rate = '5/hour'


class RegisterView(generics.CreateAPIView):
    """
    API View to handle new user registration with rate limiting and logging.
    URL: /api/auth/register/
    """
    queryset = CustomUser.objects.all()
    serializer_class = RegistrationSerializer
    permission_classes = (AllowAny,)
    throttle_classes = [AuthRateThrottle]

    def create(self, request, *args, **kwargs):
        # Log registration attempt
        logger.info(f"Registration attempt from IP: {self.get_client_ip(request)}")
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = self.perform_create(serializer)
        
        # Generate JWT tokens for immediate login
        refresh = RefreshToken.for_user(user)
        
        # Log successful registration
        logger.info(f"User registered successfully: {user.email}")
        
        # Return user data with tokens
        response_data = {
            'user': CustomUserSerializer(user).data,
            'tokens': {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            'message': 'Registration successful'
        }
        
        headers = self.get_success_headers(serializer.data)
        return Response(
            response_data, 
            status=status.HTTP_201_CREATED, 
            headers=headers
        )

    def perform_create(self, serializer):
        return serializer.save()
    
    @staticmethod
    def get_client_ip(request):
        """Extract client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class RetrieveUpdateUserView(generics.RetrieveUpdateAPIView):
    """
    API View to retrieve or update the authenticated user's profile.
    URL: /api/user/profile/
    
    Improvements:
    - Caching for better performance
    - Activity logging
    - Proper validation
    """
    serializer_class = CustomUserSerializer
    permission_classes = (IsAuthenticated,)
    throttle_classes = [UserRateThrottle]
    
    def get_object(self):
        """
        Returns the authenticated user with caching.
        """
        user_id = self.request.user.id
        cache_key = f'user_profile_{user_id}'
        
        # Try to get from cache first
        cached_user = cache.get(cache_key)
        if cached_user:
            return cached_user
        
        user = self.request.user
        
        # Cache for 5 minutes
        cache.set(cache_key, user, 300)
        
        return user
    
    def retrieve(self, request, *args, **kwargs):
        """Get user profile"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        # Log profile access
        logger.info(f"Profile accessed by user: {instance.email}")
        
        return Response(serializer.data)
    
    def update(self, request, *args, **kwargs):
        """Update user profile"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Clear cache after update
        cache_key = f'user_profile_{instance.id}'
        cache.delete(cache_key)
        
        # Log profile update
        logger.info(f"Profile updated by user: {instance.email}")
        
        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)


@api_view(['POST'])
@throttle_classes([AuthRateThrottle])
def logout_view(request):
    """
    Logout endpoint that blacklists the refresh token
    POST /api/auth/logout/
    """
    try:
        refresh_token = request.data.get("refresh")
        
        if not refresh_token:
            return Response(
                {"error": "Refresh token is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        token = RefreshToken(refresh_token)
        token.blacklist()
        
        # Log logout
        logger.info(f"User logged out: {request.user.email if request.user.is_authenticated else 'Anonymous'}")
        
        return Response(
            {"message": "Successfully logged out"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return Response(
            {"error": "Invalid token"},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['POST'])
@throttle_classes([AuthRateThrottle])
def change_password_view(request):
    """
    Change password endpoint with validation
    POST /api/user/change-password/
    """
    if not request.user.is_authenticated:
        return Response(
            {"error": "Authentication required"},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')
    
    if not old_password or not new_password:
        return Response(
            {"error": "Both old_password and new_password are required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Verify old password
    if not request.user.check_password(old_password):
        logger.warning(f"Failed password change attempt for user: {request.user.email}")
        return Response(
            {"error": "Old password is incorrect"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate new password
    from django.contrib.auth.password_validation import validate_password
    try:
        validate_password(new_password, request.user)
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Set new password
    request.user.set_password(new_password)
    request.user.save()
    
    # Clear any cached user data
    cache_key = f'user_profile_{request.user.id}'
    cache.delete(cache_key)
    
    # Log password change
    logger.info(f"Password changed successfully for user: {request.user.email}")
    
    return Response(
        {"message": "Password changed successfully"},
        status=status.HTTP_200_OK
    )


@api_view(['GET'])
def user_statistics(request):
    """
    Get user statistics (for CA firm staff only)
    GET /api/user/statistics/
    """
    if not request.user.is_authenticated or not request.user.is_ca_firm:
        return Response(
            {"error": "Permission denied"},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Get statistics
    from services.models import Case
    
    stats = {
        'total_users': CustomUser.objects.count(),
        'total_clients': CustomUser.objects.filter(is_ca_firm=False).count(),
        'total_staff': CustomUser.objects.filter(is_ca_firm=True).count(),
        'active_users': CustomUser.objects.filter(is_active=True).count(),
        'cases_managed': Case.objects.filter(assigned_staff=request.user).count() if request.user.is_ca_firm else 0,
    }
    
    return Response(stats, status=status.HTTP_200_OK)