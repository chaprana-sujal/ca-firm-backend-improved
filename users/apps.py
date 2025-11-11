# users/apps.py

from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'
    verbose_name = 'User Management'

    def ready(self):
        """
        Import signal handlers when the app is ready.
        This ensures signals are registered properly.
        """
        try:
            import users.signals  # noqa F401
        except ImportError:
            pass