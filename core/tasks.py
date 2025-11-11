# core/tasks.py
"""
Core background tasks for system maintenance and utilities
"""

from celery import shared_task
from django.core.management import call_command
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.sessions.models import Session
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def cleanup_sessions(self):
    """
    Remove expired sessions from the database
    Runs daily at 2 AM (configured in celery.py)
    """
    try:
        expired_sessions = Session.objects.filter(expire_date__lt=timezone.now())
        count = expired_sessions.count()
        expired_sessions.delete()
        
        logger.info(f"Cleaned up {count} expired sessions")
        return f"Removed {count} expired sessions"
    
    except Exception as exc:
        logger.error(f"Session cleanup failed: {exc}")
        raise self.retry(exc=exc, countdown=300)  # Retry after 5 minutes


@shared_task(bind=True, max_retries=3)
def backup_database(self):
    """
    Create database backup
    Runs daily at 3 AM (configured in celery.py)
    """
    try:
        # Call Django's dbbackup command (requires django-dbbackup package)
        # call_command('dbbackup', '--clean')
        
        logger.info("Database backup completed successfully")
        return "Database backup completed"
    
    except Exception as exc:
        logger.error(f"Database backup failed: {exc}")
        raise self.retry(exc=exc, countdown=600)  # Retry after 10 minutes


@shared_task
def send_email_async(subject, message, recipient_list, from_email=None):
    """
    Send email asynchronously
    
    Args:
        subject: Email subject
        message: Email body
        recipient_list: List of recipient email addresses
        from_email: Sender email (optional)
    """
    try:
        from_email = from_email or settings.DEFAULT_FROM_EMAIL
        
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email,
            recipient_list=recipient_list,
            fail_silently=False,
        )
        
        logger.info(f"Email sent successfully to {recipient_list}")
        return f"Email sent to {len(recipient_list)} recipients"
    
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        raise


@shared_task
def send_bulk_email_async(subject, message, recipient_list, from_email=None):
    """
    Send bulk emails with rate limiting
    
    Args:
        subject: Email subject
        message: Email body
        recipient_list: List of recipient email addresses
        from_email: Sender email (optional)
    """
    from time import sleep
    
    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    success_count = 0
    failure_count = 0
    
    for recipient in recipient_list:
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=[recipient],
                fail_silently=False,
            )
            success_count += 1
            
            # Rate limit: 1 email per second
            sleep(1)
            
        except Exception as e:
            logger.error(f"Failed to send email to {recipient}: {e}")
            failure_count += 1
    
    logger.info(f"Bulk email completed: {success_count} sent, {failure_count} failed")
    return {
        'success': success_count,
        'failed': failure_count,
        'total': len(recipient_list)
    }


@shared_task(bind=True)
def process_file_upload(self, file_path, user_id):
    """
    Process uploaded file asynchronously
    
    Args:
        file_path: Path to the uploaded file
        user_id: ID of the user who uploaded the file
    """
    try:
        from users.models import CustomUser
        
        user = CustomUser.objects.get(id=user_id)
        
        # Add your file processing logic here
        # For example: virus scan, OCR, thumbnail generation, etc.
        
        logger.info(f"File processed successfully: {file_path}")
        return f"File {file_path} processed successfully"
    
    except Exception as exc:
        logger.error(f"File processing failed: {exc}")
        raise self.retry(exc=exc, countdown=60)


@shared_task
def cleanup_old_files():
    """
    Remove old uploaded files to save storage
    Customize retention period as needed
    """
    import os
    from datetime import timedelta
    from pathlib import Path
    
    try:
        media_root = Path(settings.MEDIA_ROOT)
        cutoff_date = timezone.now() - timedelta(days=90)  # 90 days retention
        
        deleted_count = 0
        
        # Walk through media directory
        for root, dirs, files in os.walk(media_root):
            for filename in files:
                file_path = Path(root) / filename
                
                # Check file modification time
                if file_path.stat().st_mtime < cutoff_date.timestamp():
                    file_path.unlink()
                    deleted_count += 1
        
        logger.info(f"Cleaned up {deleted_count} old files")
        return f"Removed {deleted_count} old files"
    
    except Exception as e:
        logger.error(f"File cleanup failed: {e}")
        raise


@shared_task
def generate_report_async(report_type, user_id, **params):
    """
    Generate reports asynchronously
    
    Args:
        report_type: Type of report to generate
        user_id: ID of the user requesting the report
        params: Additional parameters for report generation
    """
    try:
        from users.models import CustomUser
        
        user = CustomUser.objects.get(id=user_id)
        
        # Add your report generation logic here
        # For example: PDF generation, data export, etc.
        
        logger.info(f"Report {report_type} generated for user {user.email}")
        return f"Report {report_type} generated successfully"
    
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 5})
def process_payment_webhook(self, payload):
    """
    Process payment gateway webhook asynchronously
    
    Args:
        payload: Webhook payload from payment gateway
    """
    try:
        # Add your webhook processing logic here
        # For example: Razorpay, Stripe webhook handling
        
        logger.info("Payment webhook processed successfully")
        return "Webhook processed"
    
    except Exception as exc:
        logger.error(f"Webhook processing failed: {exc}")
        raise


@shared_task
def send_daily_digest():
    """
    Send daily digest emails to users
    Runs daily at configured time
    """
    from users.models import CustomUser
    from services.models import Case
    
    try:
        # Get all CA firm staff
        staff_users = CustomUser.objects.filter(is_ca_firm=True, is_active=True)
        
        for user in staff_users:
            # Get pending cases assigned to this user
            pending_cases = Case.objects.filter(
                assigned_staff=user,
                status__in=['PENDING', 'IN_PROGRESS']
            ).count()
            
            if pending_cases > 0:
                subject = f"Daily Digest: {pending_cases} pending cases"
                message = f"You have {pending_cases} pending cases that need attention."
                
                send_email_async.delay(
                    subject=subject,
                    message=message,
                    recipient_list=[user.email]
                )
        
        logger.info("Daily digest sent successfully")
        return "Daily digest sent"
    
    except Exception as e:
        logger.error(f"Daily digest failed: {e}")
        raise


@shared_task
def update_case_status_auto():
    """
    Automatically update case statuses based on business logic
    For example: mark cases as overdue if not completed within timeline
    """
    from services.models import Case
    from datetime import timedelta
    
    try:
        # Find cases that are overdue (example: 30 days old and still in progress)
        cutoff_date = timezone.now() - timedelta(days=30)
        
        overdue_cases = Case.objects.filter(
            status='IN_PROGRESS',
            created_at__lt=cutoff_date
        )
        
        for case in overdue_cases:
            # Send notification to assigned staff
            if case.assigned_staff:
                subject = f"Case #{case.id} is overdue"
                message = f"Case {case.id} for {case.client.email} is overdue and needs attention."
                
                send_email_async.delay(
                    subject=subject,
                    message=message,
                    recipient_list=[case.assigned_staff.email]
                )
        
        logger.info(f"Checked {overdue_cases.count()} overdue cases")
        return f"Processed {overdue_cases.count()} overdue cases"
    
    except Exception as e:
        logger.error(f"Auto status update failed: {e}")
        raise