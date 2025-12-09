from django.core.management.base import BaseCommand, CommandError
from django.core.mail import send_mail
from django.conf import settings


class Command(BaseCommand):
    help = 'Send a test email to the provided address using configured EMAIL_BACKEND (SendGrid if configured)'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='Recipient email address for the test message')

    def handle(self, *args, **options):
        recipient = options['email']
        subject = 'CA Firm - Test Email'
        message = 'This is a test email from the CA Firm backend. If you received this, email is configured correctly.'
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@cafirm.com')

        try:
            send_mail(subject, message, from_email, [recipient], fail_silently=False)
        except Exception as exc:
            raise CommandError(f'Failed to send email: {exc}')

        self.stdout.write(self.style.SUCCESS(f'Successfully sent test email to {recipient}'))
