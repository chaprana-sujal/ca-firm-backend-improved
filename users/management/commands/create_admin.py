import os
from django.core.management.base import BaseCommand
from users.models import CustomUser  # Your import from before

# Django requires this class to be named EXACTLY 'Command'
class Command(BaseCommand):
    help = 'Creates a superuser non-interactively from environment variables'

    # This 'handle' function is what gets run
    def handle(self, *args, **options):
        email = os.environ.get('ADMIN_EMAIL')
        password = os.environ.get('ADMIN_PASSWORD')

        if not email or not password:
            # Use self.stdout for logging in management commands
            self.stdout.write(self.style.ERROR(
                'ADMIN_EMAIL or ADMIN_PASSWORD not set. Skipping.'
            ))
            return

        if CustomUser.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(
                f"Superuser with email {email} already exists."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Creating superuser: {email}"
            ))
            CustomUser.objects.create_superuser(email=email, password=password)
            self.stdout.write(self.style.SUCCESS(
                "Superuser created successfully."
            ))