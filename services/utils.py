 #services/utils.py
from django.core.mail import send_mail
from django.conf import settings

def send_status_update_email(case):
    """
    Sends an email notification to the client when the case status changes.
    In local dev (due to settings.EMAIL_BACKEND='console'), this prints to the Docker logs.
    """
    subject = f"Case Update: Case #{case.id} is now {case.get_status_display()}"
    
    message = (
        f"Dear {case.client.first_name},\n\n"
        f"The status of your case ({case.service_plan.service.name} - {case.service_plan.name}) "
        f"has been updated to: {case.get_status_display()}.\n\n"
        f"You can view the full details in your platform dashboard."
    )
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [case.client.email],
        fail_silently=False,
    )
    return True