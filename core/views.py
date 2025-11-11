# core/views.py
"""
System health check and monitoring endpoints
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.db import connection
from django.core.cache import cache
from django.conf import settings
import redis
from celery import current_app
import time


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Comprehensive health check endpoint for monitoring
    GET /api/health/
    """
    health_status = {
        'status': 'healthy',
        'timestamp': time.time(),
        'version': '1.0.0',
        'environment': settings.DJANGO_ENV if hasattr(settings, 'DJANGO_ENV') else 'unknown',
        'checks': {}
    }
    
    overall_healthy = True
    
    # 1. Database Check
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            health_status['checks']['database'] = {
                'status': 'connected',
                'type': settings.DATABASES['default']['ENGINE'].split('.')[-1]
            }
    except Exception as e:
        health_status['checks']['database'] = {
            'status': 'error',
            'message': str(e)
        }
        overall_healthy = False
    
    # 2. Redis/Cache Check
    try:
        cache_key = 'health_check_test'
        cache.set(cache_key, 'ok', 10)
        result = cache.get(cache_key)
        
        if result == 'ok':
            health_status['checks']['redis'] = {
                'status': 'connected',
                'backend': settings.CACHES['default']['BACKEND'].split('.')[-1]
            }
        else:
            raise Exception("Cache read/write failed")
    except Exception as e:
        health_status['checks']['redis'] = {
            'status': 'error',
            'message': str(e)
        }
        overall_healthy = False
    
    # 3. Celery Check
    try:
        # Check if Celery is configured
        celery_app = current_app
        
        # Try to get active workers
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()
        
        if active_workers:
            health_status['checks']['celery'] = {
                'status': 'running',
                'workers': list(active_workers.keys()) if active_workers else []
            }
        else:
            health_status['checks']['celery'] = {
                'status': 'warning',
                'message': 'No active workers found'
            }
    except Exception as e:
        health_status['checks']['celery'] = {
            'status': 'error',
            'message': str(e)
        }
        # Celery failure is not critical for basic functionality
    
    # 4. Storage Check (if using S3)
    if hasattr(settings, 'AWS_STORAGE_BUCKET_NAME'):
        try:
            from storages.backends.s3boto3 import S3Boto3Storage
            storage = S3Boto3Storage()
            health_status['checks']['storage'] = {
                'status': 'configured',
                'type': 'S3',
                'bucket': settings.AWS_STORAGE_BUCKET_NAME
            }
        except Exception as e:
            health_status['checks']['storage'] = {
                'status': 'error',
                'message': str(e)
            }
    else:
        health_status['checks']['storage'] = {
            'status': 'local',
            'type': 'filesystem'
        }
    
    # Set overall status
    if not overall_healthy:
        health_status['status'] = 'unhealthy'
        return Response(health_status, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    
    return Response(health_status, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def readiness_check(request):
    """
    Kubernetes readiness probe endpoint
    GET /api/ready/
    """
    try:
        # Quick database check
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        
        return Response({'status': 'ready'}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'status': 'not ready', 'error': str(e)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def liveness_check(request):
    """
    Kubernetes liveness probe endpoint
    GET /api/alive/
    """
    return Response({'status': 'alive'}, status=status.HTTP_200_OK)


@api_view(['GET'])
def system_info(request):
    """
    Detailed system information (staff only)
    GET /api/system/info/
    """
    if not request.user.is_staff:
        return Response(
            {'error': 'Permission denied'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    import sys
    import django
    from django.db import connection
    
    info = {
        'python_version': sys.version,
        'django_version': django.get_version(),
        'database': {
            'engine': settings.DATABASES['default']['ENGINE'],
            'name': settings.DATABASES['default']['NAME'],
        },
        'cache': {
            'backend': settings.CACHES['default']['BACKEND'],
            'location': settings.CACHES['default'].get('LOCATION', 'N/A'),
        },
        'debug': settings.DEBUG,
        'allowed_hosts': settings.ALLOWED_HOSTS,
        'installed_apps': list(settings.INSTALLED_APPS),
        'middleware': list(settings.MIDDLEWARE),
    }
    
    return Response(info, status=status.HTTP_200_OK)