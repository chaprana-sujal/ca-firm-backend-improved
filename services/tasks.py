# services/tasks.py
"""
Background tasks for service management
Create this file in: services/tasks.py
"""

from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_case_reminders(self):
    """
    Send reminder emails for cases that need attention
    Runs every hour (configured in core/celery.py)
    """
    from .models import Case
    
    try:
        # Find cases in progress for more than 7 days without updates
        cutoff_date = timezone.now() - timedelta(days=7)
        
        stale_cases = Case.objects.filter(
            status=Case.CaseStatus.IN_PROGRESS,
            updated_at__lt=cutoff_date,
            assigned_staff__isnull=False
        ).select_related('client', 'assigned_staff', 'service_plan__service')
        
        reminder_count = 0
        
        for case in stale_cases:
            subject = f"Reminder: Case #{case.id} Needs Attention"
            message = (
                f"This is a reminder that Case #{case.id} "
                f"({case.service_plan.service.name}) for client "
                f"{case.client.email} has been in progress for over 7 days "
                f"without any updates.\n\n"
                f"Please review and update the case status."
            )
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[case.assigned_staff.email],
                fail_silently=False,
            )
            
            reminder_count += 1
            logger.info(f"Reminder sent for case #{case.id}")
        
        logger.info(f"Sent {reminder_count} case reminders")
        return f"Sent {reminder_count} reminders"
    
    except Exception as exc:
        logger.error(f"Case reminder task failed: {exc}")
        raise self.retry(exc=exc, countdown=300)


@shared_task(bind=True, max_retries=3)
def generate_daily_reports(self):
    """
    Generate and send daily reports to CA staff
    Runs daily at 9 AM (configured in core/celery.py)
    """
    from .models import Case
    from users.models import CustomUser
    
    try:
        # Get all CA firm staff
        staff_members = CustomUser.objects.filter(is_ca_firm=True, is_active=True)
        
        for staff in staff_members:
            # Get cases assigned to this staff member
            assigned_cases = Case.objects.filter(assigned_staff=staff)
            
            # Calculate statistics
            stats = {
                'total': assigned_cases.count(),
                'pending_payment': assigned_cases.filter(status=Case.CaseStatus.PENDING).count(),
                'paid': assigned_cases.filter(status=Case.CaseStatus.PAID).count(),
                'in_progress': assigned_cases.filter(status=Case.CaseStatus.IN_PROGRESS).count(),
                'needs_documents': assigned_cases.filter(status=Case.CaseStatus.NEEDS_DOCUMENTS).count(),
                'completed': assigned_cases.filter(status=Case.CaseStatus.COMPLETED).count(),
            }
            
            # Only send if there are active cases
            if stats['total'] > 0:
                subject = f"Daily Report: {stats['total']} Assigned Cases"
                message = (
                    f"Good morning {staff.first_name},\n\n"
                    f"Here's your daily case summary:\n\n"
                    f"Total Cases: {stats['total']}\n"
                    f"Pending Payment: {stats['pending_payment']}\n"
                    f"Paid (Ready to Start): {stats['paid']}\n"
                    f"In Progress: {stats['in_progress']}\n"
                    f"Awaiting Documents: {stats['needs_documents']}\n"
                    f"Completed: {stats['completed']}\n\n"
                    f"Please log in to review and update case statuses."
                )
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[staff.email],
                    fail_silently=False,
                )
                
                logger.info(f"Daily report sent to {staff.email}")
        
        return "Daily reports generated successfully"
    
    except Exception as exc:
        logger.error(f"Daily report generation failed: {exc}")
        raise self.retry(exc=exc, countdown=600)


@shared_task
def verify_document_async(document_id):
    """
    Asynchronously verify uploaded documents
    """
    from .models import Document
    
    try:
        document = Document.objects.get(id=document_id)
        
        # Add your document verification logic here
        # For example: virus scan, format validation, OCR
        
        # Simulate processing
        import time
        time.sleep(2)
        
        # Mark as verified
        document.is_verified = True
        document.save()
        
        logger.info(f"Document {document_id} verified successfully")
        return f"Document {document_id} verified"
    
    except Document.DoesNotExist:
        logger.error(f"Document {document_id} not found")
        raise
    except Exception as e:
        logger.error(f"Document verification failed: {e}")
        raise


@shared_task
def generate_case_report_async(case_id):
    """
    Generate a detailed PDF report for a case
    """
    from .models import Case
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    import io
    
    try:
        case = Case.objects.select_related(
            'client', 'service_plan__service', 'assigned_staff', 'payment'
        ).prefetch_related('documents').get(id=case_id)
        
        # Create PDF buffer
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        
        # Add content to PDF
        p.drawString(100, 750, f"Case Report - #{case.id}")
        p.drawString(100, 730, f"Service: {case.service_plan.service.name}")
        p.drawString(100, 710, f"Plan: {case.service_plan.name}")
        p.drawString(100, 690, f"Client: {case.client.email}")
        p.drawString(100, 670, f"Status: {case.get_status_display()}")
        
        if case.assigned_staff:
            p.drawString(100, 650, f"Assigned Staff: {case.assigned_staff.email}")
        
        p.drawString(100, 630, f"Created: {case.created_at.strftime('%Y-%m-%d %H:%M')}")
        
        if case.payment and case.payment.is_successful:
            p.drawString(100, 610, f"Payment: ₹{case.payment.amount}")
            p.drawString(100, 590, f"Transaction ID: {case.payment.transaction_id}")
        
        # Add documents
        y_position = 550
        p.drawString(100, y_position, "Documents:")
        for doc in case.documents.all():
            y_position -= 20
            p.drawString(120, y_position, f"- {doc.document_type} (Verified: {doc.is_verified})")
        
        p.showPage()
        p.save()
        
        # Save PDF
        pdf_content = buffer.getvalue()
        buffer.close()
        
        logger.info(f"Case report generated for case #{case_id}")
        return f"Report generated for case #{case_id}"
    
    except Case.DoesNotExist:
        logger.error(f"Case {case_id} not found")
        raise
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise


@shared_task
def cleanup_incomplete_cases():
    """
    Clean up cases that have been pending payment for too long
    """
    from .models import Case
    
    try:
        # Find cases pending for more than 30 days
        cutoff_date = timezone.now() - timedelta(days=30)
        
        old_pending_cases = Case.objects.filter(
            status=Case.CaseStatus.PENDING,
            created_at__lt=cutoff_date
        )
        
        count = old_pending_cases.count()
        
        # Send reminder emails before canceling
        for case in old_pending_cases:
            subject = f"Reminder: Complete Payment for Case #{case.id}"
            message = (
                f"Dear {case.client.first_name or 'Client'},\n\n"
                f"This is a reminder that your case #{case.id} "
                f"({case.service_plan.service.name}) is still pending payment.\n\n"
                f"The case will be automatically canceled if payment is not "
                f"received within 7 days.\n\n"
                f"Please complete the payment to proceed."
            )
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[case.client.email],
                fail_silently=True,
            )
        
        logger.info(f"Sent reminders to {count} cases pending payment")
        return f"Processed {count} incomplete cases"
    
    except Exception as e:
        logger.error(f"Cleanup task failed: {e}")
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def send_case_notification_async(self, case_id, notification_type):
    """
    Send various types of notifications for case updates
    """
    from .models import Case
    
    try:
        case = Case.objects.select_related(
            'client', 'service_plan__service', 'assigned_staff'
        ).get(id=case_id)
        
        if notification_type == 'status_update':
            subject = f"Case #{case.id} Status Updated"
            message = (
                f"Dear {case.client.first_name or 'Client'},\n\n"
                f"Your case #{case.id} ({case.service_plan.service.name}) "
                f"status has been updated to: {case.get_status_display()}.\n\n"
                f"Please log in to view more details."
            )
        elif notification_type == 'assignment':
            subject = f"Case #{case.id} Assigned to Staff"
            message = (
                f"Dear {case.client.first_name or 'Client'},\n\n"
                f"Your case #{case.id} has been assigned to {case.assigned_staff.get_full_name()}.\n\n"
                f"They will be in touch soon."
            )
        elif notification_type == 'completion':
            subject = f"Case #{case.id} Completed"
            message = (
                f"Dear {case.client.first_name or 'Client'},\n\n"
                f"Great news! Your case #{case.id} ({case.service_plan.service.name}) "
                f"has been completed successfully.\n\n"
                f"Please log in to view the final documents."
            )
        else:
            subject = f"Case #{case.id} Update"
            message = f"There is an update on your case #{case.id}."
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[case.client.email],
            fail_silently=False,
        )
        
        logger.info(f"Notification sent for case #{case_id}: {notification_type}")
        return f"Notification sent successfully"
    
    except Case.DoesNotExist:
        logger.error(f"Case {case_id} not found for notification")
        raise
    except Exception as exc:
        logger.error(f"Notification failed: {exc}")
        raise