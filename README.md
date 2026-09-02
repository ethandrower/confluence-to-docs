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

### Run with Docker (alternative)

`docker compose up` brings up the whole stack — Postgres, Redis, the ASGI API
and the Vite dev server — with no Python, Node or database installed on the
host. You still need a `.env` (step 1); compose overrides `DATABASE_URL`,
`REDIS_URL` and `ALLOWED_HOSTS` so the same file works either way.

```bash
cp .env.example .env        # fill in the Confluence values
docker compose up           # http://localhost:5174

docker compose exec web python manage.py sync_confluence
docker compose exec web python manage.py create_test_users   # prints magic links
```

Both source trees are bind-mounted, so Django's autoreload and Vite's HMR pick
up edits without a rebuild. Rebuild only when dependencies change:
`docker compose build web`.

The image is `Dockerfile.dev`, not `Dockerfile` — production deploys through
Dokku's buildpacks, and a root `Dockerfile` would capture its builder
auto-detection and ship this dev image instead. Don't rename it.

This path runs **Postgres and a real Redis channel layer**, matching production
more closely than the SQLite + in-memory default — full-text search and
cross-worker WebSocket broadcasts behave as they do on Dokku. Postgres is
published on host port `5433` and Redis on `6380` so they don't collide with
anything already running locally.

### Run it the way production runs it (before a deploy)

`docker-compose.yml` is for iterating: runserver, `DEBUG=True`, the Vite dev
server, instant reload. It is a different **shape** of application from the one
Dokku runs, so passing locally has never meant much about a deploy.
`docker-compose.prod.yml` closes most of that gap.

```bash
docker compose -f docker-compose.prod.yml up --build   # http://localhost:8090
```

Its own project name, ports and volumes, so it runs alongside the dev stack.
What it exercises that dev cannot:

- **The real build.** `vite build`, then collectstatic through
  `CompressedManifestStaticFilesStorage`, at image-build time exactly as the
  buildpack does. That storage **raises** on a static reference it can't
  resolve, so a broken asset path fails the build instead of 500ing a page in
  production.
- **One origin.** WhiteNoise serves the hashed assets and Django serves the SPA
  shell itself. Dev's two origins (Vite + proxied API) are why
  `CSRF_TRUSTED_ORIGINS` needs a `DEBUG`-only block; none of that applies here.
- **`DEBUG=False`.** Secure cookies, SSL redirect, security headers, real error
  pages, and the `SECRET_KEY` requirement that refuses to boot without one.
- **The real web command.** gunicorn with two uvicorn workers and the 120s
  timeout from the Procfile, not single-process autoreload.
- **An nginx hop**, as Dokku has, so `SECURE_PROXY_SSL_HEADER` and the
  WebSocket upgrade path are actually exercised. It sets `X-Forwarded-Proto:
  https`, which is what stops `SECURE_SSL_REDIRECT` from bouncing every request
  to a TLS port that isn't there.
- **A release phase.** `migrate` runs as its own one-shot service that `web`
  waits on, so a bad migration fails visibly the way it aborts a deploy.

`SECURE_HSTS_SECONDS` is set to `0` here and **only** here. HSTS is remembered
by the browser per host, so a real header served from `localhost` would force
https on every other app you run there, for a month, with no obvious cause.

What this still does **not** prove: the buildpacks themselves, Mailgun
delivery, CloudFront, real S3 bucket policy and CORS, and the six cron entries
in `app.json` — none of which run locally. A staging app on the Dokku host is
the only true parity; this is the fast check that catches the common
breakages first.

### Smoke test — is the portal actually working for clients?

The suites in `portal/tests/` drive Django's test client against a fresh
database in-process. That is the right shape for logic and it is blind by
construction to release breakage, because the test client never builds a
bundle, never resolves a static asset, never terminates TLS and never reads
the environment the container was started with. `manage.py smoke` is the
complement: it walks a customer's journey against a **running** server, over
real HTTP.

```bash
# before a deploy, against the parity stack
docker compose -f docker-compose.prod.yml run --rm --no-deps release \
    python manage.py smoke --url https://proxy --insecure

# after a deploy, against production
dokku run citemed-docs python manage.py smoke \
    --url https://support.citemed.com --as edrower@citemed.com
```

Nine checks, in this order: health endpoint, SPA shell, **every static asset
the shell references**, the API refusing anonymous callers, magic-link
sign-in, session identity, the file tree (including the tenancy boundary as
seen from outside), the ticket list, and sign-out.

The static-asset check is the one that earns its keep. Under manifest static
storage a hashed filename that wasn't collected 404s at runtime while every
unit test stays green — the page loads and renders nothing, which reads as
"the app is broken" with no error anywhere.

It runs **inside** the app, so it mints its own sign-in token rather than
handling a password, but every assertion is an HTTP request to `--url`.

**Safe against production.** It only reads. The one mutation is spending a
magic-link token for an account that already exists, which is what signing in
does anyway; it creates no company, folder or file and sends no email. Write
flows belong on the parity stack, where the blast radius is a docker volume.

Two flags earn an explanation. `--insecure` skips certificate verification and
is for the parity stack's self-signed cert **only** — against production a
cert error is a finding, not a nuisance. And the parity stack serves TLS on
`https://localhost:8443` precisely so this can run: with `DEBUG=False` Django
sets `SESSION_COOKIE_SECURE`, and while browsers treat `localhost` as a
trustworthy origin and will store a `Secure` cookie over plain http, ordinary
HTTP clients do not — so over `http://` the sign-in check fails with a 403
that looks like a CSRF bug and isn't.

Run it from the `release` service rather than `web`: `compose run web` starts a
second container answering to the same `web` DNS name, and Docker round-robins
between them, so results become nondeterministic.

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

### Integration API (`/api/v1/`)

A **separate**, read-only, machine-to-machine surface for systems that need
support data across every customer — RevenueHub's health scoring, today. It is
not an extension of the table above and shares no authentication with it.

| Endpoint | Method | Description |
|---|---|---|
| `/api/v1/companies/` | GET | Discovery: id, name, contract end, ticket counts, last ticket. Populate a consumer's account-id mapping from this once, instead of matching on names forever |
| `/api/v1/tickets/` | GET | Ticket metadata. Filters: `company_id`, `email` (+`include_cc`), `status`, `priority`, `created_since`, `updated_since`; cursor paginated |
| `/api/v1/tickets/<number>/` | GET | One ticket, same shape |
| `/api/v1/share-events/` | GET | Files and folders staff pushed **to** a customer, one row per person notified, with open and reminder state. Filters: `company_id`, `recipient_email`, `opened`, `sent_since`, `updated_since`; cursor paginated |
| `/api/v1/schema/` | GET | OpenAPI 3 schema (drf-spectacular) |
| `/api/v1/docs/` | GET | Swagger UI |

```bash
python manage.py create_api_client "RevenueHub"   # prints the token once
curl -H "Authorization: Bearer csp_…" https://…/api/v1/tickets/?updated_since=2026-08-01T00:00:00Z
```

Four rules hold this surface together, and all four are asserted in
`portal/tests/test_api_v1.py`:

- **Read-only.** GET only; there is no write path in the namespace.
- **Two doors, one key each.** The bearer authenticator never falls back to the
  session, and the session endpoints never accept a bearer token. A token
  authenticates nothing under `/api/`; a session authenticates nothing under
  `/api/v1/`.
- **No conversation content.** Payloads carry `message_count` (customer-visible
  messages only) and never a message body, an internal note, a watcher or a
  Jira key.
- **It crosses the tenant boundary on purpose.** Unlike every other reader in
  the portal it does not go through `Ticket.for_user`, because its consumer is
  a cross-customer dashboard. The token is therefore the only thing protecting
  it — revoke one in the Django admin under *Portal → API clients*.

Statuses and priorities are returned in the portal's own vocabulary, unmapped.
Consumers with a smaller enum collapse it on ingest; note `csm_direct` is a
routing origin rather than a severity and has no clean severity equivalent.

#### Syncing share events

`/tickets/` answers *what has this customer asked us?*. `/share-events/`
answers *what have we sent them, and did anyone look?* — one row per (push,
person), so "two of the four people we sent this to have opened it" is
something a consumer computes rather than something we pre-aggregate away.

Poll it the same way as tickets, on `updated_at`:

```bash
curl -H "Authorization: Bearer csp_…" \
  "https://…/api/v1/share-events/?updated_since=2026-08-01T00:00:00Z"
```

**Use `updated_since`, not `sent_since`.** Nearly everything worth knowing
about a delivery happens after it is made: the open lands days later, and so do
the two reminders. `sent_since` only ever replays the push itself, so a sync
built on it would show every delivery frozen in the state it had a second after
it left. `updated_since` catches all three, and — because the ordering is
ascending — a row that changes mid-sync moves toward the end rather than behind
your cursor, making the sync resumable and at-least-once.

`last_email_at` is null when a push was recorded but no email was sent,
because the per-recipient rate limit below held it. Worth reading rather than
assuming `sent_at` implies delivery: a row that has sat unopened for a week
means something different once you know whether anyone was ever told, and a
consumer scoring engagement would otherwise count an email we never sent as one
the customer ignored.

Deliveries carry no file contents, no download URLs, and no link targets. The
endpoint reports *that* something was sent and what became of it, never what
was in it.

#### How much mail one person can get

Staff re-notify a folder as they add to it, which is the normal workflow rather
than misuse — so the limits are written about the person, not the row. Two
rules, both on `ShareNotice`:

- **One email per person per folder per day** (`SAME_FOLDER_COOLDOWN`). A
  second push of the same folder says the same sentence and points at the same
  link, so a second email adds nothing the first did not.
- **At most `MAX_EMAILS_PER_DAY` share emails per person across all folders**,
  as a backstop for any path added later.

A push whose email is held is still recorded, still appears in the status panel
and the sync feed, and still supersedes the older notice — only the email is
dropped, and `share_push` returns `held` so the UI can say so instead of
reporting a delivery that never left. The admin's notify dialog unticks anyone
already emailed about that folder today and flags them, so re-notifying is a
deliberate act.

Pushing a folder again **supersedes** that person's earlier unopened notices
for it rather than adding a second nudge cycle: the older rows stay on the
record but stop reminding. Without that, three pushes of one folder to one
person who never opened it sent nine emails — three sends and six reminders,
several on the same day under one subject line — even though the per-notice cap
of two was working exactly as documented.

#### What staff can no longer do to a shared folder

A shared folder the customer has been **notified** about (any `ShareNotice`
exists for it) cannot be deleted — the endpoint returns 409. The older rule
only refused to delete a folder that still held subfolders or live files, which
a determined admin got past by deleting the files one at a time; the folder then
went, and with it a link a customer had been emailed. The notification is the
line rather than the folder's creation because a staff folder appears in the
customer's tree as soon as it exists (`buckets_list` does not filter on
`origin`), so "before they could see it" is not a window that exists — but
undoing a folder created by mistake has to stay possible.

There is no archived state yet, so a notified folder currently cannot be
retired at all. That is the intended follow-up; this guard holds the line until
it lands.

Renaming a shared folder requires sending back the `updated_at` you were
looking at, and gets a 409 if the row has moved since. Two admins on one
account is ordinary, and without the precondition the second rename silently
won while the first admin went on reading a name that was no longer real. The
field is required rather than optional — a caller that omitted it would get
exactly the clobbering the check exists to prevent — and it is compared for
equality at millisecond resolution, not as a tolerance window, because a window
accepts the rename that landed a moment ago.

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
