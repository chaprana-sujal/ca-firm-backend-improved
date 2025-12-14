import logging
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from .models import ConsultationRequest

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def send_consultation_email_task(self, request_id):
    """
    Sends an email notification to the admin/support team about a new consultation request.
    """
    try:
        consultation_request = ConsultationRequest.objects.get(id=request_id)
        
        # Admin email subject and message
        subject = f"New Consultation Request: {consultation_request.email}"
        message = f"""
A new consultation request has been received.

Name: {consultation_request.name or 'N/A'}
Email: {consultation_request.email}
Phone: {consultation_request.phone or 'N/A'}
Service: {consultation_request.service or 'N/A'}

Requested At: {consultation_request.created_at.strftime('%Y-%m-%d %H:%M:%S')}
IP Address: {consultation_request.ip_address}

Please reach out to the user as soon as possible.
        """
        
        # Send to admins (using SERVER_EMAIL or a specific support email)
        recipient_list = [settings.SERVER_EMAIL] # Or settings.DEFAULT_FROM_EMAIL if preferred as recipient
        # Ideally, this should go to the "admin" user's email, or a configured CONTACT_EMAIL.
        # For now, I'll send it to the DEFAULT_FROM_EMAIL to ensure it goes *somewhere* known, 
        # but realistically it should be the business owner's email. 
        # I'll use a list including DEFAULT_FROM_EMAIL.
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.DEFAULT_FROM_EMAIL], 
            fail_silently=False,
        )
        
        logger.info(f"Consultation email sent for {consultation_request.email}")
        
    except ConsultationRequest.DoesNotExist:
        logger.error(f"ConsultationRequest with id {request_id} does not exist.")
    except Exception as exc:
        logger.error(f"Failed to send consultation email: {exc}")
        raise self.retry(exc=exc, countdown=60)
