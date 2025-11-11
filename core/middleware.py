# core/middleware.py
"""
Custom middleware for security, logging, and request handling
"""

import logging
import time
import json
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from rest_framework import status

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Logs all requests with timing information for performance monitoring
    """
    
    def process_request(self, request):
        # Store start time
        request.start_time = time.time()
        
        # Log request details (excluding sensitive data)
        log_data = {
            'method': request.method,
            'path': request.path,
            'ip': self.get_client_ip(request),
            'user': str(request.user) if hasattr(request, 'user') and request.user.is_authenticated else 'Anonymous'
        }
        
        logger.info(f"Request: {json.dumps(log_data)}")
    
    def process_response(self, request, response):
        # Calculate request duration
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time
            
            # Log response with timing
            log_data = {
                'method': request.method,
                'path': request.path,
                'status': response.status_code,
                'duration_ms': round(duration * 1000, 2),
                'user': str(request.user) if hasattr(request, 'user') and request.user.is_authenticated else 'Anonymous'
            }
            
            # Log as warning if slow request (>1 second)
            if duration > 1.0:
                logger.warning(f"SLOW REQUEST: {json.dumps(log_data)}")
            else:
                logger.info(f"Response: {json.dumps(log_data)}")
        
        return response
    
    @staticmethod
    def get_client_ip(request):
        """Extract client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Adds security headers to all responses
    """
    
    def process_response(self, request, response):
        # Content Security Policy
        response['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        
        # Additional security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        return response


class ErrorHandlingMiddleware(MiddlewareMixin):
    """
    Global error handler for consistent error responses
    """
    
    def process_exception(self, request, exception):
        # Log the exception
        logger.error(
            f"Unhandled exception: {str(exception)}",
            exc_info=True,
            extra={
                'request_path': request.path,
                'request_method': request.method,
                'user': str(request.user) if hasattr(request, 'user') and request.user.is_authenticated else 'Anonymous'
            }
        )
        
        # Return JSON error response for API requests
        if request.path.startswith('/api/'):
            error_response = {
                'error': 'Internal Server Error',
                'message': 'An unexpected error occurred. Please try again later.',
                'status_code': 500
            }
            
            # In debug mode, include exception details
            if hasattr(request, 'user') and request.user.is_staff:
                error_response['detail'] = str(exception)
            
            return JsonResponse(
                error_response,
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Let Django handle non-API errors normally
        return None


class RateLimitMiddleware(MiddlewareMixin):
    """
    Simple rate limiting middleware using Django cache
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        from django.core.cache import cache
        self.cache = cache
    
    def __call__(self, request):
        # Skip rate limiting for staff users
        if hasattr(request, 'user') and request.user.is_authenticated and request.user.is_staff:
            return self.get_response(request)
        
        # Get client identifier
        client_ip = self.get_client_ip(request)
        
        # Different rate limits for different endpoints
        if request.path.startswith('/api/auth/'):
            rate_limit = self.check_rate_limit(client_ip, 'auth', max_requests=5, window=3600)
        else:
            rate_limit = self.check_rate_limit(client_ip, 'general', max_requests=100, window=3600)
        
        if rate_limit['exceeded']:
            return JsonResponse(
                {
                    'error': 'Rate limit exceeded',
                    'message': f"Too many requests. Please try again in {rate_limit['retry_after']} seconds.",
                    'retry_after': rate_limit['retry_after']
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        response = self.get_response(request)
        
        # Add rate limit headers
        response['X-RateLimit-Limit'] = rate_limit['limit']
        response['X-RateLimit-Remaining'] = rate_limit['remaining']
        response['X-RateLimit-Reset'] = rate_limit['reset']
        
        return response
    
    def check_rate_limit(self, identifier, category, max_requests, window):
        """Check if rate limit is exceeded"""
        cache_key = f'ratelimit:{category}:{identifier}'
        
        # Get current count
        current = self.cache.get(cache_key, {'count': 0, 'reset': time.time() + window})
        
        # Reset if window expired
        if current['reset'] < time.time():
            current = {'count': 0, 'reset': time.time() + window}
        
        # Increment count
        current['count'] += 1
        
        # Save to cache
        self.cache.set(cache_key, current, window)
        
        return {
            'exceeded': current['count'] > max_requests,
            'limit': max_requests,
            'remaining': max(0, max_requests - current['count']),
            'reset': int(current['reset']),
            'retry_after': int(current['reset'] - time.time())
        }
    
    @staticmethod
    def get_client_ip(request):
        """Extract client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class HealthCheckMiddleware(MiddlewareMixin):
    """
    Bypass authentication for health check endpoint
    """
    
    def process_request(self, request):
        if request.path == '/api/health/':
            # Skip all other middleware for health checks
            return None
        return None