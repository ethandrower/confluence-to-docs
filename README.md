# Confluence to Docs

Turn a Confluence space into a clean, self-service support portal — with searchable documentation, passwordless login, and ticket submission via Jira Service Management.

## How it works

```
┌──────────────┐         ┌──────────────────┐         ┌──────────────────┐
│  Confluence   │         │   Sync Engine    │         │   Docs Portal    │
│              │  REST   │                  │  store  │                  │
│  Space (ECD) ├────────►│  Fetch pages     ├────────►│  Browse docs     │
│  Pages       │  API    │  Transform HTML  │   DB    │  Search          │
│  Attachments │         │  Download images │         │  Submit tickets  │
│              │         │  Build tree      │         │  Magic-link auth │
└──────────────┘         └──────────────────┘         └──────────────────┘
```

### Sync pipeline

The sync engine connects to Confluence's REST API, pulls every page from a space, and processes them:

```
Confluence Storage XML
        │
        ▼
┌─────────────────────┐
│  StorageTransformer  │
│                     │
│  • ac:structured-   │     ┌─────────────┐
│    macro → <pre>,   │     │  Attachment  │
│    <div>, panels    │     │  Downloader  │
│  • ac:image → <img> │     │             │
│  • ac:link → <a>    │     │  Downloads   │
│  • task lists →     │     │  images to   │
│    checkboxes       │     │  local/S3    │
│  • bleach sanitize  │     └──────┬──────┘
└────────┬────────────┘            │
         │                         │
         ▼                         ▼
┌──────────────────────────────────────┐
│            DocPage record            │
│                                      │
│  • slug (URL-friendly)               │
│  • rendered_html (clean, safe HTML)  │
│  • raw_storage (original XML)        │
│  • parent → tree hierarchy           │
│  • search_vector (full-text index)   │
│  • image URLs rewritten to storage   │
└──────────────────────────────────────┘
```

### Page hierarchy

Confluence pages have a parent-child tree structure. The sync preserves this by processing parents before children:

```
Confluence space "ECD"            Portal sidebar
─────────────────────             ──────────────

Getting Started                   📄 Getting Started
├── Installation                     ├── 📄 Installation
├── Quick Start                      ├── 📄 Quick Start
│   └── First Project                │   └── 📄 First Project
└── Configuration                    └── 📄 Configuration
API Reference                     📄 API Reference
├── Authentication                   ├── 📄 Authentication
└── Endpoints                        └── 📄 Endpoints
```

Each page gets a unique slug derived from its title (e.g. `installation`, `quick-start`). Internal Confluence links between pages are rewritten to portal URLs (`/docs/quick-start`).

### Multi-space / multi-product support

Each `DocPage` record stores a `space_key` identifying which Confluence space it came from. To serve docs for multiple products or versions:

1. Create separate Confluence spaces (e.g. `PRODUCT_V1`, `PRODUCT_V2`)
2. Run `python manage.py sync_confluence --space PRODUCT_V1` for each
3. All pages coexist in the same database with their `space_key` preserved

The API can filter by space key to serve different doc sets from the same portal instance.

### Authentication flow

```
┌────────┐     ┌─────────┐     ┌──────────┐     ┌────────┐
│  User  │     │ Frontend│     │ Backend  │     │ Email  │
└───┬────┘     └────┬────┘     └────┬─────┘     └───┬────┘
    │               │               │               │
    │  Enter email  │               │               │
    ├──────────────►│  POST /api/   │               │
    │               │  auth/request │               │
    │               ├──────────────►│               │
    │               │               │  Send link    │
    │               │               ├──────────────►│
    │               │  "Check your  │               │
    │               │◄──────────────┤               │
    │  Click link   │               │               │
    │◄──────────────────────────────────────────────┤
    │               │               │               │
    ├──────────────►│  GET /api/    │               │
    │               │  auth/verify  │               │
    │               ├──────────────►│               │
    │               │  session      │               │
    │               │  cookie set   │               │
    │               │◄──────────────┤               │
    │  Logged in    │               │               │
    │◄──────────────┤               │               │
```

No passwords — users authenticate via a time-limited magic link (15 min expiry) sent to their email.

### Ticket integration

Users can submit support requests that create tickets in Jira Service Management. The portal checks if the user is a known JSM customer and exposes request types from your service desk.

## Quick start

### 1. Configure

```bash
cp .env.example .env
# Edit .env — at minimum set these:
#   CONFLUENCE_DOMAIN, CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN,
#   CONFLUENCE_SPACE_KEY, ATLASSIAN_CLOUD_ID
```

See `.env.example` for the full list including email, S3 storage, and JSM options.

### 2. Install & sync

```bash
# Backend
uv sync              # or: pip install -r requirements.txt
python manage.py migrate
python manage.py sync_confluence

# Frontend
cd frontend && npm install
```

### 3. Run

```bash
# Terminal 1 — API server
python manage.py runserver 8001

# Terminal 2 — Frontend dev server (proxies /api → :8001)
cd frontend && npm run dev
```

Open `http://localhost:5174`.

### Keeping docs in sync

**Manual:** `python manage.py sync_confluence` (full) or `--incremental` (changed pages only).

**Automatic:** With Redis available, run Celery for scheduled background sync:

```bash
celery -A citemed worker --loglevel=info
celery -A citemed beat --loglevel=info
```

## API

| Endpoint | Method | Description |
|---|---|---|
| `/api/docs/` | GET | Page tree (roots with nested children) |
| `/api/docs/<slug>/` | GET | Single page with breadcrumbs and siblings |
| `/api/docs/search/?q=...` | GET | Full-text search (Postgres) or text search (SQLite) |
| `/api/auth/request-magic-link/` | POST | Send login link to email |
| `/api/auth/verify/?token=...` | GET | Verify magic link, set session |
| `/api/auth/me/` | GET | Current user info |
| `/api/auth/logout/` | POST | End session |
| `/api/tickets/` | GET/POST | List or create support tickets |
| `/api/tickets/request-types/` | GET | Available JSM request types |
| `/api/tickets/<id>/` | GET | Ticket detail |

## Project structure

```
citemed/              Django project config
  settings.py         All configuration via environment variables
  celery.py           Celery app for background sync
  urls.py             /admin + /api routing

portal/               Main application
  confluence/
    client.py          Confluence REST API client (wraps trinity-atlassian-cli)
    transformer.py     Confluence storage XML → clean HTML
    sync.py            Orchestrates full/incremental space sync
  jsm/
    client.py          Jira Service Management API client
  views/
    auth.py            Magic-link login/logout/session
    docs.py            Doc tree, page detail, search
    tickets.py         Ticket CRUD (JSM integration)
  models.py            DocPage, DocImage, PortalUser, MagicLinkToken
  tasks.py             Celery tasks for background sync

frontend/             Vue 3 SPA
  src/
    components/
      auth/            Login, magic link sent, verify, auth gate
      docs/            Page renderer, table of contents, search
      layout/          App shell, sidebar tree, search bar, breadcrumbs
      tickets/         Ticket form, list, detail
    stores/            Pinia stores (auth, docs, tickets)
    views/             Route-level views
    assets/            CSS (Tailwind v4 + Confluence content styles)
```

## Environment variables

See `.env.example` for the complete list. Key groups:

**Required — Confluence sync:**
`CONFLUENCE_DOMAIN`, `CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN`, `CONFLUENCE_SPACE_KEY`, `ATLASSIAN_CLOUD_ID`

**Optional — Infrastructure:**
`DATABASE_URL` (default: SQLite), `REDIS_URL` (only for Celery), `SECRET_KEY`

**Optional — Email:**
`EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`

**Optional — S3/R2 image storage:**
`AWS_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_ENDPOINT_URL`, `MEDIA_URL`

## Deployment

The `Procfile` runs three processes (for Heroku/Render/etc.):

```
web: gunicorn citemed.wsgi --log-file -
worker: celery -A citemed worker --loglevel=info
beat: celery -A citemed beat --loglevel=info
```

Build the frontend first: `cd frontend && npm run build`
