from celery import Celery
from celery.schedules import crontab
from kombu import Queue
import logging

from config import settings

logger = logging.getLogger(__name__)

# Initialize Celery app
celery_app = Celery(
    'news_aggregator',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        'app.tasks.news_tasks'
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
    task_default_queue='news_tasks',
    task_default_exchange='news_tasks',
    task_default_routing_key='news.default',

    # Task routing
    task_routes={
        'app.tasks.news_tasks.fetch_and_save_news': {
            'queue': 'news_fetch',
            'routing_key': 'news.fetch'
        },
        'app.tasks.news_tasks.fetch_rss_feeds': {
            'queue': 'news_rss',
            'routing_key': 'news.rss'
        },
        'app.tasks.news_tasks.cleanup_old_articles': {
            'queue': 'news_maintenance',
            'routing_key': 'news.maintenance'
        }
    },

    # Define queues
    task_queues=(
        Queue('news_fetch', routing_key='news.fetch'),
        Queue('news_rss', routing_key='news.rss'),
        Queue('news_maintenance', routing_key='news.maintenance'),
        Queue('news_tasks', routing_key='news.default'),
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

# Task error handlers
@celery_app.task(bind=True)
def error_handler(self, uuid):
    """Handle task errors"""
    result = celery_app.AsyncResult(uuid)
    logger.error(
        f'Task {uuid} raised exception: {result.traceback}'
    )


logger.info("Celery app configured successfully")

