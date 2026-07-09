# Confluence to Docs

Turn a Confluence space into a clean, self-service support portal — with searchable documentation, passwordless login, and a built-in support-ticket system with real-time (WebSocket) updates and email threading.

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

### Support tickets

The portal includes a full **native support-ticket system** (it replaced the earlier Jira Service Management hand-off — Jira is now an optional read-only *link* on a ticket, not the system of record). Signed-in customers open tickets, and staff work them from a two-pane helpdesk:

- **Customer side** — create tickets, thread replies, see status; each ticket is tenant-scoped to the customer's company.
- **Staff side** — an inbox (with an "awaiting reply" count in the nav), a two-pane helpdesk, internal notes (never shown to customers), status changes, CC management, and optional Jira links with live status.
- **Email** — outbound replies go out via Mailgun (Anymail) with RFC-5322 threading headers and per-message delivery tracking (queued / sent / delivered / bounced) via a Mailgun webhook + a reconciliation poller.
- **Security** — a `for_customer` serializer plus admin-only endpoints guarantee Jira keys, internal notes, staff identity, and delivery details are never exposed to customers.

### Real-time updates

Tickets update **live over WebSockets** (Django Channels + Redis), with **client polling as an automatic fallback**:

- **Transport** — the app is served over **ASGI** (`gunicorn` + `uvicorn` workers). A Channels `ProtocolTypeRouter` keeps all HTTP (docs, search, auth, static) on Django's ASGI app and adds a `websocket` protocol. WS auth reuses the portal's session identity (`SessionMiddlewareStack` + a custom `PortalUserMiddleware`), not Django auth.
- **Nudge + refetch** — the socket carries only a tiny `{ticket changed}` signal; the client refetches through the existing REST endpoints, so the customer/admin data-gating is never re-implemented on the socket (no content ever crosses the wire). Three groups back the surfaces: `ticket-<n>` (a thread), `admins` (the inbox/badge), and `co-<company>` (a customer's list).
- **Fallback** — WebSocket is primary; on disconnect the client reconnects with backoff and falls back to a 30s poll (visibility-gated, draft-safe) until the socket returns, then does a catch-up fetch. Requires `REDIS_URL` in production (falls back to an in-memory channel layer locally / when unset — fine for a single process).
- **Unread indicator** — the customer ticket list shows a per-row **unread dot + highlight** for tickets with a staff reply they haven't opened yet (tracked per user via a `TicketRead` model; cleared when the thread is opened).

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
| `/api/tickets/` | GET/POST | List (with per-ticket `unread`) or create the customer's tickets |
| `/api/tickets/<number>/` | GET | Ticket detail (also marks it read) |
| `/api/tickets/<number>/messages/` | POST | Customer reply |
| `/api/admin/tickets/*` | GET/POST | Staff helpdesk: inbox, list, detail, reply/notes, status, CC, Jira, resend (admin-only) |
| `/api/webhooks/mailgun/` | POST | Mailgun delivery-event webhook |
| `ws://…/ws/tickets/<number>/` | WS | Live thread updates (customer or staff) |
| `ws://…/ws/admin/tickets/` | WS | Live inbox/badge updates (staff) |
| `ws://…/ws/customer/tickets/` | WS | Live customer ticket-list updates |

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
  views/
    auth.py            Magic-link login/logout/session
    docs.py            Doc tree, page detail, search
    tickets.py         Customer ticket API (list/create/detail/reply, unread, mark-read)
    tickets_admin.py   Staff helpdesk API (inbox, reply/notes, status, CC, Jira, resend)
  consumers.py         WebSocket consumers (ticket / admin-inbox / customer-list)
  routing.py           WebSocket URL routes
  ws_auth.py           Channels middleware → resolves the portal session identity
  realtime.py          notify_ticket() — fans "changed" nudges to Channels groups
  ticket_notify.py     Outbound email (Anymail/Mailgun) + delivery tracking
  webhook_handlers.py  Mailgun delivery-event handling
  jira_client.py       Read-only Jira status for linked tickets
  models.py            DocPage, DocImage, PortalUser, MagicLinkToken,
                       Ticket, TicketMessage, TicketActivity, TicketRead, JiraTicketLink

frontend/             Vue 3 SPA
  src/
    components/
      auth/            Login, magic link sent, verify, auth gate
      docs/            Page renderer, table of contents, search
      layout/          App shell, sidebar tree, search bar, breadcrumbs
      support/         Ticket list, thread, admin two-pane helpdesk (unread dot)
    lib/
      usePolling.js        Visibility-gated polling (fallback + composable)
      useTicketChannel.js  WebSocket client (reconnect/backoff, catch-up)
      useThreadScroll.js   At-bottom auto-scroll + "new messages" pill
    stores/            Pinia stores (auth, docs, tickets)
    views/             Route-level views (SupportView, ManageTicketsView, …)
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

Production runs on **Dokku** (Hetzner). The `Procfile` serves the app over **ASGI** so WebSockets and HTTP share one web process:

```
release: python manage.py migrate --noinput
web: gunicorn citemed.asgi:application -k uvicorn.workers.UvicornWorker --workers 2 --timeout 120 --log-file - --access-logfile -
```

Migrations run automatically in the `release` phase. Build the frontend first: `cd frontend && npm run build`.

**Redis (for real-time):** WebSocket broadcasts need a Redis channel layer to reach clients across workers. Provision it once on the host, then `REDIS_URL` is injected automatically:

```bash
dokku plugin:install https://github.com/dokku/dokku-redis.git   # one-time
dokku redis:create citemed-realtime
dokku redis:link  citemed-realtime citemed-docs                 # sets REDIS_URL, restarts app
```

Without `REDIS_URL` the app still boots and works (in-memory channel layer + polling fallback), but real-time won't cross workers — so provision Redis **before** or right after the first ASGI deploy. Deploy with `git push dokku main`.
