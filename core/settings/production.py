import os
import dj_database_url
from .base import * # Import all base settings

# --- Production Security ---
# DEBUG is False unless explicitly set to 'true' in env
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
SECRET_KEY = os.environ.get('SECRET_KEY') # Must be set in Railway

RENDER_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME")

if RENDER_HOST:
    ALLOWED_HOSTS = [RENDER_HOST, "localhost", "127.0.0.1"]
else:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',  # Before auth
    # ... rest
]

# --- PRODUCTION DATABASE (CRITICAL FIX) ---
# This forces Django to use the DATABASE_URL provided by Railway's environment,
# overriding the local 'db' host from base.py.
DATABASES = {
    'default': dj_database_url.config( 
        # Get the DATABASE_URL from the environment
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=600,
        ssl_require=True # Important for most cloud database connections
    )
}
# --- END CRITICAL FIX ---


# --- CORS Headers (For your Frontend) ---
# Set CORS_ALLOWED_ORIGINS in Railway to your frontend's URL
CORS_ALLOWED_ORIGINS = os.environ.get('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS]
#securtiy headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# --- Static Files (Whitenoise) ---
# This serves your Django Admin static files
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
# Insert Whitenoise middleware *after* SecurityMiddleware
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')


# --- Media Files (Amazon S3) ---
# This configures all file uploads (like in Document model) to go to S3.
DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'

# These MUST be set in Railway variables for file uploads to work
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME')
AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = 'private'

