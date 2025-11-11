# core/urls.py

from django.contrib import admin
from django.urls import path, include
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse

# Defines the entry point (API_ROOT) as requested in the prompt table
@api_view(['GET'])
def api_root(request, format=None):
    """
    The entry point of the compliance platform API.
    """
    return Response({
        'auth_register': reverse('auth_register', request=request, format=format),
        'auth_login': reverse('auth_login', request=request, format=format),
        'auth_refresh': reverse('auth_refresh', request=request, format=format),
        'user_profile': reverse('user_profile', request=request, format=format),
        # Add links to future phases here (e.g., 'services', 'cases')
    })


urlpatterns = [
    # Django Admin Site
    path('admin/', admin.site.urls),
    
    # API Root: GET /api/
    path('api/', api_root, name='api_root'),
    
    # Include all paths from the users app under the /api/ namespace
    # This includes: /api/auth/register/, /api/auth/login/, etc.
    path('api/', include('users.urls')),
]