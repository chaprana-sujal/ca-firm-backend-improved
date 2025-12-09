#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.base')
    try:
        # Ensure compatibility: some libraries expect `django.utils.timezone.utc` to exist.
        # Newer Django versions may not expose `utc`; provide a safe fallback.
        try:
            import django.utils.timezone as _dj_tz
            if not hasattr(_dj_tz, 'utc'):
                from datetime import timezone as _dt_timezone
                _dj_tz.utc = _dt_timezone.utc
        except Exception:
            # Non-fatal: if this fails, the import below will raise the original error.
            pass
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
