# core/celery.py
"""
Celery configuration for CA Firm Backend
Handles background tasks and scheduled jobs
"""

import os
from celery import Celery
from celery.schedules import crontab
from django.conf import settings

# Set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.base')

# Create Celery app
app = Celery('cafirm')

# Load configuration from Django settings with 'CELERY_' prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# Autodiscover tasks in all installed apps
app.autodiscover_tasks()

# ============================================================================
# CELERY CONFIGURATION
# ============================================================================

app.conf.update(
    # Result backend
    result_backend='django-db',
    result_extended=True,
    
    # Task execution
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='Asia/Kolkata',
    enable_utc=True,
    
    # Task routing
    task_routes={
        'services.tasks.*': {'queue': 'services'},
        'users.tasks.*': {'queue': 'users'},
        'contact.tasks.*': {'queue': 'default'},
        'core.tasks.*': {'queue': 'default'},
    },
    
    # Task results
    task_ignore_result=False,
    task_track_started=True,
    task_time_limit=1800,  # 30 minutes hard limit
    task_soft_time_limit=1500,  # 25 minutes soft limit
    
    # Worker configuration
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=False,
    
    # Broker connection
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    
    # Task result expiration
    result_expires=3600,  # 1 hour
    
    # Task acknowledgment
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Beat schedule (scheduled tasks)
    beat_schedule={
        # Example: Clean up old sessions every day at 2 AM
        'cleanup-sessions': {
            'task': 'core.tasks.cleanup_sessions',
            'schedule': crontab(hour=2, minute=0),
        },
        # Example: Send reminder emails every hour
        'send-case-reminders': {
            'task': 'services.tasks.send_case_reminders',
            'schedule': crontab(minute=0),  # Every hour
        },
        # Example: Generate daily reports at 9 AM
        'generate-daily-reports': {
            'task': 'services.tasks.generate_daily_reports',
            'schedule': crontab(hour=9, minute=0),
        },
        # Example: Backup database every day at 3 AM
        'backup-database': {
            'task': 'core.tasks.backup_database',
            'schedule': crontab(hour=3, minute=0),
        },
    },
)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task to test Celery configuration"""
    print(f'Request: {self.request!r}')


@app.task(bind=True, max_retries=3)
def test_retry_task(self, fail=True):
    """Test task with retry logic"""
    if fail:
        raise Exception("Task failed, will retry")
    return "Task succeeded"


# ============================================================================
# CELERY SIGNALS
# ============================================================================

from celery.signals import (
    task_prerun,
    task_postrun,
    task_failure,
    task_success,
    worker_ready,
    worker_shutdown,
)
import logging

logger = logging.getLogger(__name__)


@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **extra):
    """Log when task starts"""
    logger.info(f"Task {task.name} [{task_id}] started")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, **extra):
    """Log when task completes"""
    logger.info(f"Task {task.name} [{task_id}] completed")


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, **extra):
    """Log when task fails"""
    logger.error(f"Task {sender.name} [{task_id}] failed: {exception}", exc_info=True)


@task_success.connect
def task_success_handler(sender=None, result=None, **extra):
    """Log when task succeeds"""
    logger.info(f"Task {sender.name} succeeded with result: {result}")


@worker_ready.connect
def worker_ready_handler(sender=None, **extra):
    """Log when worker is ready"""
    logger.info(f"Celery worker ready: {sender.hostname}")


@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **extra):
    """Log when worker shuts down"""
    logger.info(f"Celery worker shutting down: {sender.hostname}")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def send_task_with_retry(task_name, args=None, kwargs=None, max_retries=3, countdown=60):
    """
    Helper function to send task with automatic retry on failure
    
    Args:
        task_name: Name of the task to execute
        args: Positional arguments
        kwargs: Keyword arguments
        max_retries: Maximum number of retries
        countdown: Delay before retry (seconds)
    """
    try:
        return app.send_task(
            task_name,
            args=args or (),
            kwargs=kwargs or {},
            max_retries=max_retries,
            default_retry_delay=countdown,
        )
    except Exception as e:
        logger.error(f"Failed to send task {task_name}: {e}")
        raise


def get_task_status(task_id):
    """
    Get the status of a task by ID
    
    Args:
        task_id: UUID of the task
        
    Returns:
        dict with task status information
    """
    from celery.result import AsyncResult
    
    result = AsyncResult(task_id, app=app)
    
    return {
        'task_id': task_id,
        'status': result.state,
        'result': result.result if result.ready() else None,
        'traceback': result.traceback if result.failed() else None,
    }


def revoke_task(task_id, terminate=False):
    """
    Revoke (cancel) a running task
    
    Args:
        task_id: UUID of the task
        terminate: If True, forcefully terminate the task
    """
    app.control.revoke(task_id, terminate=terminate)
    logger.info(f"Task {task_id} revoked (terminate={terminate})")


def purge_queue(queue_name='default'):
    """
    Purge all tasks from a queue
    
    Args:
        queue_name: Name of the queue to purge
        
    Returns:
        Number of tasks purged
    """
    with app.connection() as conn:
        count = conn.default_channel.queue_purge(queue_name)
        logger.info(f"Purged {count} tasks from queue {queue_name}")
        return count