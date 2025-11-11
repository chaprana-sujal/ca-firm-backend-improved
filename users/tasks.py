# users/tasks.py
"""
Celery tasks for user management
Handles asynchronous operations like email verification, password resets, etc.
"""

from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

User = get_user_model()


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


@shared_task(bind=True, max_retries=3)
def send_password_reset_email(self, user_id, reset_token):
    """
    Send password reset email with token
    """
    try:
        user = User.objects.get(id=user_id)
        
        # Construct reset URL
        frontend_url = get_frontend_url()
        reset_url = f"{frontend_url}/reset-password/{reset_token}"
        
        subject = "Password Reset Request - CA Firm Platform"
        message = f"""
Dear {user.first_name or 'User'},

You have requested to reset your password for your CA Firm Platform account.

Please click the link below to reset your password:
{reset_url}

This link will expire in 1 hour.

If you did not request this password reset, please ignore this email.

Best regards,
CA Firm Platform Team
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        logger.info(f"Password reset email sent to {user.email}")
        return f"Password reset email sent to {user.email}"
    
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found for password reset")
        raise
    except Exception as exc:
        logger.error(f"Password reset email failed: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def send_email_verification(self, user_id, verification_token):
    """
    Send email verification link to new users
    """
    try:
        user = User.objects.get(id=user_id)
        
        # Construct verification URL
        frontend_url = get_frontend_url()
        verification_url = f"{frontend_url}/verify-email/{verification_token}"
        
        subject = "Verify Your Email - CA Firm Platform"
        message = f"""
Dear {user.first_name or 'User'},

Thank you for registering with CA Firm Platform!

Please verify your email address by clicking the link below:
{verification_url}

This link will expire in 24 hours.

If you did not create this account, please ignore this email.

Best regards,
CA Firm Platform Team
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        logger.info(f"Email verification sent to {user.email}")
        return f"Verification email sent to {user.email}"
    
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found for email verification")
        raise
    except Exception as exc:
        logger.error(f"Email verification failed: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task
def cleanup_inactive_users():
    """
    Remove unverified users after 30 days
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=30)
        
        inactive_users = User.objects.filter(
            is_active=False,
            date_joined__lt=cutoff_date
        )
        
        count = inactive_users.count()
        
        # Send final reminder before deletion
        for user in inactive_users:
            try:
                subject = "Account Deletion Warning - CA Firm Platform"
                message = f"""
Dear {user.first_name or 'User'},

Your CA Firm Platform account ({user.email}) has been inactive for 30 days.

This account will be permanently deleted within 7 days unless you verify your email and activate it.

To keep your account, please log in and verify your email.

Best regards,
CA Firm Platform Team
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,
                )
            except Exception as e:
                logger.error(f"Failed to send deletion warning to {user.email}: {e}")
        
        # Delete users inactive for more than 37 days (30 + 7 grace period)
        final_cutoff = timezone.now() - timedelta(days=37)
        deleted_users = User.objects.filter(
            is_active=False,
            date_joined__lt=final_cutoff
        )
        deleted_count = deleted_users.count()
        deleted_users.delete()
        
        logger.info(f"Sent warnings to {count} inactive users, deleted {deleted_count} old accounts")
        return f"Processed {count} inactive users, deleted {deleted_count}"
    
    except Exception as e:
        logger.error(f"Cleanup inactive users task failed: {e}")
        raise


@shared_task
def generate_user_activity_report():
    """
    Generate monthly user activity report for admins
    """
    try:
        from services.models import Case
        
        # Get statistics for the past month
        one_month_ago = timezone.now() - timedelta(days=30)
        
        stats = {
            'new_users': User.objects.filter(date_joined__gte=one_month_ago).count(),
            'new_clients': User.objects.filter(
                date_joined__gte=one_month_ago,
                is_ca_firm=False
            ).count(),
            'new_staff': User.objects.filter(
                date_joined__gte=one_month_ago,
                is_ca_firm=True
            ).count(),
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'new_cases': Case.objects.filter(created_at__gte=one_month_ago).count(),
        }
        
        # Get admin emails
        admin_emails = User.objects.filter(
            is_superuser=True,
            is_active=True
        ).values_list('email', flat=True)
        
        if admin_emails:
            subject = "Monthly User Activity Report - CA Firm Platform"
            message = f"""
Monthly User Activity Report
Period: {one_month_ago.strftime('%Y-%m-%d')} to {timezone.now().strftime('%Y-%m-%d')}

NEW REGISTRATIONS:
- Total New Users: {stats['new_users']}
- New Clients: {stats['new_clients']}
- New Staff: {stats['new_staff']}

PLATFORM TOTALS:
- Total Users: {stats['total_users']}
- Active Users: {stats['active_users']}
- New Cases Created: {stats['new_cases']}

For detailed analytics, please log in to the admin panel.

Best regards,
CA Firm Platform System
            """
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=list(admin_emails),
                fail_silently=False,
            )
            
            logger.info("Monthly user activity report sent to admins")
        
        return "User activity report generated successfully"
    
    except Exception as e:
        logger.error(f"User activity report generation failed: {e}")
        raise


@shared_task(bind=True, max_retries=3)
def notify_user_profile_update(self, user_id, updated_fields):
    """
    Send notification when user profile is updated
    """
    try:
        user = User.objects.get(id=user_id)
        
        subject = "Profile Update Confirmation - CA Firm Platform"
        message = f"""
Dear {user.first_name or 'User'},

Your profile has been successfully updated.

Updated fields: {', '.join(updated_fields)}

If you did not make these changes, please contact support immediately.

Best regards,
CA Firm Platform Team
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        logger.info(f"Profile update notification sent to {user.email}")
        return f"Notification sent to {user.email}"
    
    except User.DoesNotExist:
        logger.error(f"User with ID {user_id} not found")
        raise
    except Exception as exc:
        logger.error(f"Profile update notification failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


@shared_task
def sync_user_data_to_external_system():
    """
    Sync user data to external CRM or analytics system
    Placeholder for future integration
    """
    try:
        # Implement external API sync here
        # Example: Sync with CRM, Analytics, etc.
        
        logger.info("User data sync initiated")
        return "User data sync completed"
    
    except Exception as e:
        logger.error(f"User data sync failed: {e}")
        raise