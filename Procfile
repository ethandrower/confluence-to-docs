web: gunicorn citemed.wsgi --log-file -
worker: celery -A citemed worker --loglevel=info
beat: celery -A citemed beat --loglevel=info
