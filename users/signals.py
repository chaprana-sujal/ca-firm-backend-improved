# users/signals.py
"""
Signal handlers for user-related events
Handles post-registration actions, logging, and notifications
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """
    Actions to perform after a user is saved.
    - Send welcome email for new users
    - Clear user cache
    - Log user creation/updates
    """
    if created:
        # Log new user creation
        logger.info(f"New user created: {instance.email} (CA Firm: {instance.is_ca_firm})")
        
        # Send welcome email
        try:
            send_welcome_email(instance)
        except Exception as e:
            logger.error(f"Failed to send welcome email to {instance.email}: {e}")
        
        # Send notification to admin if it's a CA firm registration
        if instance.is_ca_firm:
            notify_admin_new_ca_firm(instance)
    
    else:
        # Log user update
        logger.info(f"User updated: {instance.email}")
    
    # Clear user profile cache
    cache_key = f'user_profile_{instance.id}'
    cache.delete(cache_key)


@receiver(pre_save, sender=User)
def user_pre_save(sender, instance, **kwargs):
    """
    Actions before saving a user.
    - Normalize email
    - Log changes for audit trail
    """
    # Normalize email to lowercase
    if instance.email:
        instance.email = instance.email.lower().strip()
    
    # Log if this is an update and track what changed
    if instance.pk:
        try:
            old_instance = User.objects.get(pk=instance.pk)
            
            # Track important field changes
            changes = []
            if old_instance.email != instance.email:
                changes.append(f"email: {old_instance.email} -> {instance.email}")
            if old_instance.is_active != instance.is_active:
                changes.append(f"is_active: {old_instance.is_active} -> {instance.is_active}")
            if old_instance.is_ca_firm != instance.is_ca_firm:
                changes.append(f"is_ca_firm: {old_instance.is_ca_firm} -> {instance.is_ca_firm}")
            
            if changes:
                logger.info(f"User {instance.email} changes: {', '.join(changes)}")
        
        except User.DoesNotExist:
            pass


def get_frontend_url():
    """
    Helper function to get frontend URL from settings.
    Handles both list and string formats of CORS_ALLOWED_ORIGINS.
    """
    if hasattr(settings, 'CORS_ALLOWED_ORIGINS'):
        cors_origins = settings.CORS_ALLOWED_ORIGINS
        
        # Handle list format
        if isinstance(cors_origins, list):
            return cors_origins[0] if cors_origins else ''
        
        # Handle string format (comma-separated)
        if isinstance(cors_origins, str):
            return cors_origins.split(',')[0].strip()
    
    return ''


def send_welcome_email(user):
    """
    Send a welcome email to newly registered users.
    Uses async task in production for better performance.
    """
    frontend_url = get_frontend_url()
    
    if user.is_ca_firm:
        subject = "Welcome to CA Firm Platform - Staff Account Created"
        message = f"""
Dear {user.first_name or 'Staff Member'},

Welcome to the CA Firm Management Platform!

Your staff account has been successfully created.

Email: {user.email}
Role: CA Firm Staff

You can now log in and start managing client cases.

If you have any questions, please contact the administrator.

Best regards,
CA Firm Platform Team
        """
    else:
        subject = "Welcome to CA Firm Platform - Your Account is Ready"
        message = f"""
Dear {user.first_name or 'Client'},

Welcome to our CA Firm Services Platform!

Your client account has been successfully created.

Email: {user.email}

You can now:
- Browse our compliance services
- Create and track your cases
- Upload required documents
- Communicate with our team

{f'Log in to get started: {frontend_url}' if frontend_url else 'Log in to get started.'}

Best regards,
CA Firm Platform Team
        """
    
    try:
        # In production, use Celery for async email sending
        if hasattr(settings, 'CELERY_BROKER_URL'):
            from core.tasks import send_email_async
            send_email_async.delay(
                subject=subject,
                message=message,
                recipient_list=[user.email]
            )
        else:
            # Fallback to synchronous sending in development
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        
        logger.info(f"Welcome email sent to {user.email}")
    
    except Exception as e:
        logger.error(f"Failed to send welcome email to {user.email}: {e}")


def notify_admin_new_ca_firm(user):
    """
    Notify administrators when a new CA firm staff member registers.
    """
    try:
        admin_emails = User.objects.filter(
            is_superuser=True, is_active=True
        ).values_list('email', flat=True)
        
        if admin_emails:
            subject = f"New CA Firm Staff Registration: {user.email}"
            message = f"""
A new CA Firm staff account has been created:

Name: {user.full_name}
Email: {user.email}
Joined: {user.date_joined}

Please review and verify this account in the admin panel.
            """
            
            if hasattr(settings, 'CELERY_BROKER_URL'):
                from core.tasks import send_email_async
                send_email_async.delay(
                    subject=subject,
                    message=message,
                    recipient_list=list(admin_emails)
                )
            else:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=list(admin_emails),
                    fail_silently=True,
                )
            
            logger.info(f"Admin notification sent for new CA firm staff: {user.email}")
    
    except Exception as e:
        logger.error(f"Failed to notify admin about new CA firm staff {user.email}: {e}")