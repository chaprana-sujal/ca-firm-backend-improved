# services/signals.py
"""
Signal handlers for service-related events
Handles case status changes, document uploads, payment processing, etc.
"""

from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import logging

from .models import Case, Document, Payment, ServiceCategory, Service
from .utils import send_status_update_email

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Case)
def case_post_save(sender, instance, created, **kwargs):
    """
    Actions after a case is saved.
    - Send notifications on status changes
    - Log case creation/updates
    - Trigger background tasks
    """
    if created:
        # New case created
        logger.info(f"New case created: #{instance.id} for {instance.client.email}")
        
        # Send confirmation email to client
        try:
            subject = f"Case #{instance.id} Created Successfully"
            message = f"""
Dear {instance.client.first_name or 'Client'},

Your case has been created successfully.

Case ID: #{instance.id}
Service: {instance.service_plan.service.name}
Plan: {instance.service_plan.name}
Amount: ₹{instance.service_plan.price}
Status: {instance.get_status_display()}

Next Steps:
{'1. Complete the payment to proceed.' if instance.status == Case.CaseStatus.PENDING else '2. Upload required documents.'}

You can track your case progress in your dashboard.

Best regards,
CA Firm Platform Team
            """
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[instance.client.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Failed to send case creation email: {e}")
        
        # Notify admins if it's a high-value case
        if instance.service_plan.price > 50000:
            notify_admin_high_value_case(instance)
    
    else:
        # Case updated
        logger.info(f"Case #{instance.id} updated - Status: {instance.status}")
        
        # Check if status changed (need to fetch from DB to compare)
        # Note: We can't reliably detect status changes here without additional queries
        # This is handled in the view layer instead
    
    # Clear case-related caches
    cache.delete(f'case_{instance.id}')
    cache.delete(f'user_cases_{instance.client.id}')


@receiver(post_save, sender=Document)
def document_post_save(sender, instance, created, **kwargs):
    """
    Actions after a document is uploaded.
    - Send notifications
    - Trigger verification tasks
    - Log document uploads
    """
    if created:
        logger.info(f"Document uploaded: {instance.document_type} for Case #{instance.case.id}")
        
        # Notify case owner (client)
        try:
            subject = f"Document Uploaded - Case #{instance.case.id}"
            message = f"""
Dear {instance.case.client.first_name or 'Client'},

A new document has been uploaded for your case #{instance.case.id}.

Document Type: {instance.document_type}
Uploaded By: {instance.uploaded_by.email}
Verification Status: {'Verified' if instance.is_verified else 'Pending'}

You can view this document in your case dashboard.

Best regards,
CA Firm Platform Team
            """
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[instance.case.client.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Failed to send document upload notification: {e}")
        
        # Notify assigned staff if document uploaded by client
        if not instance.uploaded_by.is_ca_firm and instance.case.assigned_staff:
            try:
                staff_message = f"""
Dear {instance.case.assigned_staff.first_name or 'Staff'},

A new document has been uploaded by the client for Case #{instance.case.id}.

Document Type: {instance.document_type}
Client: {instance.case.client.email}

Please review and verify the document.

Best regards,
CA Firm Platform System
                """
                
                send_mail(
                    subject=f"New Document for Review - Case #{instance.case.id}",
                    message=staff_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[instance.case.assigned_staff.email],
                    fail_silently=True,
                )
            except Exception as e:
                logger.error(f"Failed to notify staff about document: {e}")
        
        # Trigger async document verification
        if hasattr(settings, 'CELERY_BROKER_URL'):
            try:
                from .tasks import verify_document_async
                verify_document_async.delay(instance.id)
            except Exception as e:
                logger.error(f"Failed to trigger document verification task: {e}")


@receiver(post_save, sender=Payment)
def payment_post_save(sender, instance, created, **kwargs):
    """
    Actions after a payment is recorded.
    - Update case status
    - Send confirmation emails
    - Generate receipts
    """
    if created:
        logger.info(f"Payment recorded for Case #{instance.case.id} - Amount: ₹{instance.amount}")
        
        if instance.is_successful:
            # Send payment confirmation to client
            try:
                subject = f"Payment Confirmed - Case #{instance.case.id}"
                message = f"""
Dear {instance.case.client.first_name or 'Client'},

Your payment has been successfully processed!

Case ID: #{instance.case.id}
Amount Paid: ₹{instance.amount}
Transaction ID: {instance.transaction_id}
Payment Date: {instance.paid_at.strftime('%Y-%m-%d %H:%M')}

Your case is now in progress. Our team will review and assign it to a staff member shortly.

You can track your case status in your dashboard.

Best regards,
CA Firm Platform Team
                """
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[instance.case.client.email],
                    fail_silently=False,
                )
                
                logger.info(f"Payment confirmation sent for Case #{instance.case.id}")
            except Exception as e:
                logger.error(f"Failed to send payment confirmation: {e}")
            
            # Notify admin about successful payment
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                
                admin_emails = User.objects.filter(
                    is_superuser=True, is_active=True
                ).values_list('email', flat=True)
                
                if admin_emails:
                    admin_message = f"""
New payment received:

Case ID: #{instance.case.id}
Client: {instance.case.client.email}
Service: {instance.case.service_plan.service.name}
Amount: ₹{instance.amount}
Transaction ID: {instance.transaction_id}

Please assign staff to this case.
                    """
                    
                    send_mail(
                        subject=f"Payment Received - Case #{instance.case.id}",
                        message=admin_message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=list(admin_emails),
                        fail_silently=True,
                    )
            except Exception as e:
                logger.error(f"Failed to notify admin about payment: {e}")


@receiver(pre_save, sender=Case)
def case_pre_save(sender, instance, **kwargs):
    """
    Validation before saving a case.
    """
    # Validate status transitions
    if instance.pk:
        try:
            old_instance = Case.objects.get(pk=instance.pk)
            
            # Prevent reopening completed cases
            if old_instance.status == Case.CaseStatus.COMPLETED and instance.status != Case.CaseStatus.COMPLETED:
                logger.warning(f"Attempt to reopen completed Case #{instance.id}")
                # In production, you might want to raise ValidationError here
            
            # Log status changes
            if old_instance.status != instance.status:
                logger.info(
                    f"Case #{instance.id} status change: "
                    f"{old_instance.get_status_display()} -> {instance.get_status_display()}"
                )
        except Case.DoesNotExist:
            pass


@receiver(post_delete, sender=Document)
def document_post_delete(sender, instance, **kwargs):
    """
    Clean up file storage when document is deleted.
    """
    try:
        if instance.file:
            instance.file.delete(save=False)
            logger.info(f"File deleted: {instance.file.name}")
    except Exception as e:
        logger.error(f"Failed to delete file: {e}")


def notify_admin_high_value_case(case):
    """
    Notify administrators about high-value case creation.
    """
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        admin_emails = User.objects.filter(
            is_superuser=True, is_active=True
        ).values_list('email', flat=True)
        
        if admin_emails:
            subject = f"High-Value Case Created: #{case.id}"
            message = f"""
A high-value case has been created:

Case ID: #{case.id}
Client: {case.client.email}
Service: {case.service_plan.service.name}
Plan: {case.service_plan.name}
Amount: ₹{case.service_plan.price}
Status: {case.get_status_display()}

Please prioritize review and assignment.
            """
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=list(admin_emails),
                fail_silently=True,
            )
            
            logger.info(f"Admin notified about high-value case #{case.id}")
    except Exception as e:
        logger.error(f"Failed to notify admin about high-value case: {e}")


def notify_staff_assignment(case):
    """
    Notify staff member when a case is assigned to them.
    """
    if not case.assigned_staff:
        return
    
    try:
        subject = f"New Case Assigned: #{case.id}"
        message = f"""
Dear {case.assigned_staff.first_name or 'Staff Member'},

A new case has been assigned to you.

Case ID: #{case.id}
Client: {case.client.email}
Service: {case.service_plan.service.name}
Plan: {case.service_plan.name}
Amount: ₹{case.service_plan.price}
Status: {case.get_status_display()}

Please review the case details and update the status accordingly.

Log in to view full case details.

Best regards,
CA Firm Platform System
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[case.assigned_staff.email],
            fail_silently=False,
        )
        
        logger.info(f"Staff assignment notification sent for Case #{case.id}")
    except Exception as e:
        logger.error(f"Failed to send staff assignment notification: {e}")