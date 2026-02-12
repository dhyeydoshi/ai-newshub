from celery import Celery
from celery.schedules import crontab
from kombu import Queue
import logging

from config import settings

logger = logging.getLogger(__name__)

CELERY_NAMESPACE = settings.REDIS_KEY_PREFIX.replace(":", "_")


def _queue_name(base_name: str) -> str:
    return f"{CELERY_NAMESPACE}.{base_name}"


# Initialize Celery app
celery_app = Celery(
    f'{CELERY_NAMESPACE}.news_aggregator',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        'app.tasks.news_tasks',
        'app.tasks.webhook_tasks',
    ]
)

# Celery Configuration
celery_app.conf.update(
    # Task serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',

    # Timezone settings
    timezone='UTC',
    enable_utc=True,

    # Task execution settings
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes hard limit
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
    task_acks_late=True,  # Task acknowledged after execution
    task_reject_on_worker_lost=True,

    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time
    worker_max_tasks_per_child=1000,  # Restart worker after 1000 tasks
    worker_disable_rate_limits=False,

    # Result backend settings
    result_expires=7200,  # Results expire after 2 hours

    # Broker settings
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,

    # Queue settings
    task_default_queue=_queue_name('news_tasks'),
    task_default_exchange=_queue_name('news_tasks'),
    task_default_routing_key='news.default',

    # Task routing
    task_routes={
        'app.tasks.news_tasks.fetch_and_save_news': {
            'queue': _queue_name('news_fetch'),
            'routing_key': 'news.fetch'
        },
        'app.tasks.news_tasks.fetch_rss_feeds': {
            'queue': _queue_name('news_rss'),
            'routing_key': 'news.rss'
        },
        'app.tasks.news_tasks.cleanup_old_articles': {
            'queue': _queue_name('news_maintenance'),
            'routing_key': 'news.maintenance'
        },
        'app.tasks.webhook_tasks.plan_webhook_batches': {
            'queue': _queue_name('integration_planner'),
            'routing_key': 'integration.plan'
        },
        'app.tasks.webhook_tasks.deliver_webhook_batch': {
            'queue': _queue_name('integration_delivery'),
            'routing_key': 'integration.deliver'
        },
        'app.tasks.webhook_tasks.flush_api_key_usage': {
            'queue': _queue_name('integration_maintenance'),
            'routing_key': 'integration.maintenance'
        },
        'app.tasks.webhook_tasks.cleanup_integration_delivery_history': {
            'queue': _queue_name('integration_maintenance'),
            'routing_key': 'integration.maintenance'
        }
    },

    # Define queues
    task_queues=(
        Queue(_queue_name('news_fetch'), routing_key='news.fetch'),
        Queue(_queue_name('news_rss'), routing_key='news.rss'),
        Queue(_queue_name('news_maintenance'), routing_key='news.maintenance'),
        Queue(_queue_name('news_tasks'), routing_key='news.default'),
        Queue(_queue_name('integration_planner'), routing_key='integration.plan'),
        Queue(_queue_name('integration_delivery'), routing_key='integration.deliver'),
        Queue(_queue_name('integration_maintenance'), routing_key='integration.maintenance'),
    ),

    # Logging
    worker_hijack_root_logger=False,
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s] [%(task_name)s(%(task_id)s)] %(message)s',
)

# Celery Beat Schedule (Periodic Tasks)
celery_app.conf.beat_schedule = {
    # Fetch news every 2 hours
    'fetch-news-every-2-hours': {
        'task': 'app.tasks.news_tasks.fetch_and_save_news',
        'schedule': crontab(minute=0, hour='*/2'),  # At minute 0 of every 2nd hour (0:00, 2:00, 4:00...)
        'options': {
            'expires': 7200,  # Task expires if not executed within 2 hours
        }
    },

    # Fetch RSS feeds every 2 hours (offset by 30 minutes from news fetch)
    'fetch-rss-every-2-hours': {
        'task': 'app.tasks.news_tasks.fetch_rss_feeds',
        'schedule': crontab(minute=30, hour='*/2'),  # At minute 30 of every 2nd hour (0:30, 2:30, 4:30...)
        'options': {
            'expires': 7200,
        }
    },

    # Cleanup old articles once per day at 3 AM
    'cleanup-old-articles-daily': {
        'task': 'app.tasks.news_tasks.cleanup_old_articles',
        'schedule': crontab(hour=3, minute=0),  # 3:00 AM daily
        'options': {
            'expires': 7200,
        }
    },
}

if settings.ENABLE_INTEGRATION_API:
    celery_app.conf.beat_schedule.update(
        {
            'flush-integration-key-usage-every-10-minutes': {
                'task': 'app.tasks.webhook_tasks.flush_api_key_usage',
                'schedule': crontab(minute='*/10'),
                'options': {'expires': 600},
            },
            'cleanup-integration-delivery-history-daily': {
                'task': 'app.tasks.webhook_tasks.cleanup_integration_delivery_history',
                'schedule': crontab(hour=4, minute=30),
                'options': {'expires': 7200},
            },
        }
    )

if settings.ENABLE_INTEGRATION_API and settings.ENABLE_INTEGRATION_DELIVERY:
    celery_app.conf.beat_schedule.update(
        {
            'plan-webhook-batches-every-5-minutes': {
                'task': 'app.tasks.webhook_tasks.plan_webhook_batches',
                'schedule': crontab(minute='*/5'),
                'options': {'expires': 300},
            }
        }
    )

# Ensure task modules are registered for worker/inspect tooling.
celery_app.autodiscover_tasks(["app"], related_name="tasks", force=True)

# Task error handlers
@celery_app.task(bind=True)
def error_handler(self, uuid):
    """Handle task errors"""
    result = celery_app.AsyncResult(uuid)
    logger.error(
        f'Task {uuid} raised exception: {result.traceback}'
    )


logger.info("Celery app configured successfully")

