# CiteMed Support Portal

Customer-facing support portal that syncs documentation from Confluence and provides ticket management via Jira Service Management (JSM). Built with Django + Vue 3.

## Architecture

- **Backend:** Django 4.2 + Django REST Framework — serves the API at `/api/`
- **Frontend:** Vue 3 + Pinia + Tailwind CSS 4 + Vite
- **Task queue:** Celery + Redis (periodic Confluence sync, email sending)
- **Auth:** Passwordless magic-link login via email
- **Docs:** Synced from Confluence (HTML transformed and images downloaded)
- **Tickets:** Created/viewed via Jira Service Management API

## Prerequisites

- Python 3.12+
- Node.js 18+
- Redis (for Celery)
- An Atlassian account with Confluence + JSM API access

## Setup

### 1. Clone & configure environment

```bash
cp .env.example .env
# Edit .env with your credentials (Confluence API token, email settings, etc.)
```

### 2. Backend

```bash
# Install Python dependencies (using uv)
uv sync

# Or with pip
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create test users (optional)
python manage.py create_test_users

# Sync docs from Confluence
python manage.py sync_confluence
```

### 3. Frontend

```bash
cd frontend
npm install
```

## Running (development)

Start three processes (or use the Procfile with a process manager):

```bash
# Terminal 1 — Django API server
python manage.py runserver 8001

# Terminal 2 — Vue dev server (proxies /api to Django)
cd frontend && npm run dev

# Terminal 3 — Celery worker (optional, for background sync)
celery -A citemed worker --loglevel=info
```

The frontend runs at `http://localhost:5174` and proxies API calls to Django on port 8001.

## Project Structure

```
citemed/          # Django project settings, URLs, WSGI/ASGI, Celery config
portal/           # Main Django app
  confluence/     # Confluence API client, HTML transformer, sync logic
  jsm/            # Jira Service Management API client
  management/     # Management commands (sync_confluence, create_test_users)
  views/          # API views split by domain (auth, docs, tickets)
  models.py       # Page, PageImage, MagicLink models
  serializers.py  # DRF serializers
  tasks.py        # Celery tasks
frontend/         # Vue 3 SPA
  src/
    components/   # UI components (auth/, docs/, layout/, tickets/)
    stores/       # Pinia stores (auth, docs, tickets)
    views/        # Route-level views
    router/       # Vue Router config
```

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Purpose |
|---|---|
| `CONFLUENCE_DOMAIN` | Your Atlassian domain (e.g. `company.atlassian.net`) |
| `CONFLUENCE_API_TOKEN` | Atlassian API token for the service account |
| `CONFLUENCE_SPACE_KEY` | Confluence space to sync |
| `ATLASSIAN_CLOUD_ID` | From `https://yourcompany.atlassian.net/_edge/tenant_info` |
| `DATABASE_URL` | Database connection string (defaults to SQLite for dev) |
| `REDIS_URL` | Redis URL for Celery broker |
| `EMAIL_BACKEND` | Django email backend (console in dev, SMTP in prod) |
| `FRONTEND_URL` | Frontend origin for magic-link emails |
| `AWS_STORAGE_BUCKET_NAME` | S3/R2 bucket for images (leave blank for local storage) |

## Deployment

The included `Procfile` runs three processes via Gunicorn + Celery:

```
web: gunicorn citemed.wsgi --log-file -
worker: celery -A citemed worker --loglevel=info
beat: celery -A citemed beat --loglevel=info
```

Build the frontend before deploying: `cd frontend && npm run build`
