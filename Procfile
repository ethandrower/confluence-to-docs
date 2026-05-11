release: python manage.py migrate --noinput
web: gunicorn citemed.wsgi --log-file - --access-logfile - --workers 2 --timeout 60
# worker / beat disabled for v1 — sync runs via `dokku run` cron, no Redis dependency.
# Re-enable after provisioning the Redis plugin if background tasks become needed.
# worker: celery -A citemed worker --loglevel=info
# beat: celery -A citemed beat --loglevel=info
