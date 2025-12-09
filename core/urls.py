"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
# core/urls.py

from django.contrib import admin
from django.urls import path, include
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse
from core import views as core_views

# Defines the entry point (API_ROOT)
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
        'service-categories': reverse('servicecategory-list', request=request, format=format),
        'services': reverse('service-list', request=request, format=format),
        'cases': reverse('case-list', request=request, format=format),
    })


urlpatterns = [
    # Django Admin Site
    path('admin/', admin.site.urls),
    
    # API Root: GET /api/
    path('api/', api_root, name='api_root'),
    # Health and readiness endpoints
    path('api/health/', core_views.health_check, name='api_health'),
    path('api/ready/', core_views.readiness_check, name='api_ready'),
    path('api/alive/', core_views.liveness_check, name='api_alive'),
    
    # Include all paths from the users app under the /api/ namespace
    path('api/', include('users.urls')), 
    path('api/', include('services.urls')),
]
