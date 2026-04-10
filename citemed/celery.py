import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'citemed.settings')

app = Celery('citemed')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Celery Beat schedule
from celery.schedules import crontab

app.conf.beat_schedule = {
    'sync-confluence-incremental': {
        'task': 'portal.tasks.sync_confluence_incremental',
        'schedule': 60 * 15,  # every 15 minutes
    },
    'sync-confluence-full': {
        'task': 'portal.tasks.sync_confluence_full',
        'schedule': crontab(hour=2, minute=0),  # 2am daily
    },
}
