# users/urls.py

from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import RegisterView, RetrieveUpdateUserView

urlpatterns = [
    # AUTH Endpoints
    # POST /api/auth/register/ -> Create a new user (Client or CA Firm)
    path('auth/register/', RegisterView.as_view(), name='auth_register'),
    
    # POST /api/auth/login/ -> Exchange credentials for JWT access/refresh tokens
    path('auth/login/', TokenObtainPairView.as_view(), name='auth_login'),
    
    # POST /api/auth/refresh/ -> Refresh the access token
    path('auth/refresh/', TokenRefreshView.as_view(), name='auth_refresh'),

    # USER Endpoints
    # GET/PUT/PATCH /api/user/profile/ -> Retrieve or update the authenticated user's profile
    path('user/profile/', RetrieveUpdateUserView.as_view(), name='user_profile'),
]