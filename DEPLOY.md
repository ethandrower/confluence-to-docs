# Deploying to Dokku

Target: Dokku host at `116.203.82.103` (Hetzner). Assumes Dokku is installed and you have SSH access.

## One-time setup on the server

```bash
# SSH in as root or a dokku-enabled user
ssh root@116.203.82.103

# Plugins (skip any already installed — check with `dokku plugin:list`)
sudo dokku plugin:install https://github.com/dokku/dokku-postgres.git
sudo dokku plugin:install https://github.com/dokku/dokku-letsencrypt.git
sudo dokku letsencrypt:cron-job --add

# Create the app
dokku apps:create citemed-docs

# Provision Postgres and link it (auto-sets DATABASE_URL on the app)
dokku postgres:create citemed-docs-db
dokku postgres:link citemed-docs-db citemed-docs

# Buildpacks — Node (builds Vue) then Python (Django). Order matters.
dokku buildpacks:add citemed-docs https://github.com/heroku/heroku-buildpack-nodejs
dokku buildpacks:add citemed-docs https://github.com/heroku/heroku-buildpack-python
```

## Configure environment

```bash
# Generate a Django secret key on your laptop:
#   python -c 'import secrets; print(secrets.token_urlsafe(64))'

dokku config:set citemed-docs \
  SECRET_KEY='<paste-generated-key>' \
  DEBUG=False \
  ALLOWED_HOSTS=support.citemed.com \
  CSRF_TRUSTED_ORIGINS=https://support.citemed.com \
  FRONTEND_URL=https://support.citemed.com \
  ADMIN_PATH='<random-9-char-string>' \
  CONFLUENCE_DOMAIN=citemed.atlassian.net \
  CONFLUENCE_EMAIL=placeholder@example.com \
  CONFLUENCE_API_TOKEN=placeholder \
  CONFLUENCE_SPACE_KEY=CITEMED \
  ATLASSIAN_CLOUD_ID=placeholder \
  MAILGUN_ACCESS_KEY=<mailgun-key> \
  MAILGUN_SERVER_NAME=notification.citemed.com \
  MAILGUN_WEBHOOK_SIGNING_KEY=<mailgun-http-webhook-signing-key> \
  DEFAULT_FROM_EMAIL='CiteMed Support <noreply@notification.citemed.com>' \
  SUPPORT_EMAIL=support@citemed.com \
  PORTAL_MAGIC_LINK_EXPIRY_MINUTES=15 \
  STAFF_EMAIL_DOMAINS=citemed.com
```

`STAFF_EMAIL_DOMAINS` makes a first-time sign-in from one of those domains an
agent automatically. Leave it unset and the portal stays fully closed — every
agent must be created by hand. It only applies to brand-new accounts, so a user
you disable or demote is never re-upgraded by signing in again.

To reuse Mailgun creds from another Dokku app on the same host:
```bash
dokku config:show <other-app> | grep MAILGUN
```

### Inbound email replies (ECD-2250) — Mailgun route

Customers reply straight from their inbox and the reply lands on the ticket.
This needs Mailgun-side config that no deploy or migration sets up for you.

**The reply address must be on a domain whose MX points at Mailgun.**
`portal/ticket_notify.py` builds `Reply-To: ticket-<n>+<token>@<domain>`, where
`<domain>` is the domain part of `DEFAULT_FROM_EMAIL`. `notification.citemed.com`
has Mailgun MX; `citemed.com` and `citemedical.com` are on Microsoft 365 and can
never deliver to Mailgun. Point `DEFAULT_FROM_EMAIL` at a Mailgun-MX domain or
inbound capture silently does nothing — outbound mail keeps working, so this
failure is invisible from the app side.

**The route must use `forward()`, not `store()`.** Anymail's inbound webhook
rejects `store()` payloads outright (it raises `AnymailConfigurationError`, and
the request 500s before our handler runs). A route created via the Mailgun UI's
"Store and Notify" option looks correct in the dashboard and drops every reply.
This cost weeks of swallowed customer replies once already — see
`portal/tests/test_inbound_webhook.py`, which pins the requirement.

```
Expression:  match_recipient("ticket-.*@notification.citemed.com")
Actions:     forward("https://support.citemed.com/api/webhooks/mailgun/inbound/")
             stop()
Priority:    10
```

Check the live route (needs a key with route read scope):

```bash
curl -s -u "api:$MAILGUN_ACCESS_KEY" https://api.mailgun.net/v3/routes
```

Also required: `MAILGUN_WEBHOOK_SIGNING_KEY` (Mailgun dashboard → **Webhooks →
HTTP webhook signing key** — this is *not* the API key), and a DMARC record on
`notification.citemed.com`.

To verify end to end, send a mail to a nonexistent ticket on that domain — the
route still matches, so the whole chain runs and the handler logs the drop:

```bash
dokku logs citemed-docs -t | grep -i inbound
```

- `inbound: no ticket match, dropping` + 200 → route and webhook are healthy
- `AnymailConfigurationError ... store()` + 500 → route is still on `store()`
- nothing at all → mail never reached Mailgun; check the MX and the `Reply-To`

### About the Confluence env vars

The four `CONFLUENCE_*` / `ATLASSIAN_CLOUD_ID` values above are intentionally set to placeholders for the initial deploy. **The portal serves docs from the database, not live Confluence on each request** — pages are populated by the `sync_from_mcp` management command and then read locally. So a freshly deployed instance with placeholder Confluence creds works for everything *except* re-syncing.

Before running `manage.py sync_from_mcp` on the deployed app, swap in the real values:

```bash
dokku config:set citemed-docs \
  CONFLUENCE_EMAIL=<real-sync-user-email> \
  CONFLUENCE_API_TOKEN=<real-token> \
  ATLASSIAN_CLOUD_ID=<real-cloud-id>
```

Get a token at [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens). Cloud ID is at `https://citemed.atlassian.net/_edge/tenant_info`.

### Initial database population

A freshly provisioned Postgres has zero pages. Two paths:

1. **Sync from Confluence** (recommended once creds are set):
   ```bash
   dokku run citemed-docs python manage.py sync_from_mcp
   ```
2. **Restore from a local snapshot** (faster, lets us serve the existing 385 pages immediately):
   ```bash
   # On your laptop, dump local SQLite to a Postgres-compatible SQL file:
   .venv/bin/python manage.py dumpdata --indent 2 portal > /tmp/portal-snapshot.json

   # Copy it to the Hetzner host:
   scp /tmp/portal-snapshot.json root@116.203.82.103:/tmp/

   # Load it inside the app container:
   dokku run citemed-docs python manage.py loaddata /tmp/portal-snapshot.json
   ```

## Pre-flight checklist

Run through this before a release that carries new features.

**1. Confirm Dokku is still building with buildpacks, not a Dockerfile.**

The repo contains `Dockerfile.dev` and `docker-compose.yml` for local development.
They're named so Dokku ignores them — its builder auto-detection treats a root
`Dockerfile` as the build strategy, which would deploy the dev image (runserver,
no frontend build) instead of the Node+Python buildpack chain. Never rename
`Dockerfile.dev` to `Dockerfile`. To be certain:

```bash
dokku builder:report citemed-docs          # expect herokuish, not dockerfile
```

**2. Set any new config.** Missing vars don't error — features default to off
and fail silently, which is harder to spot than a crash:

```bash
# Staff auto-provisioning. Unset means NOBODY is auto-provisioned and every
# agent has to be created by hand.
dokku config:set citemed-docs STAFF_EMAIL_DOMAINS=citemed.com

# Jira escalation targets. The defaults (ECD,AI and epic type 10000) are
# already correct for this Jira site — set them only to change the targets.
# dokku config:set citemed-docs JIRA_ESCALATION_PROJECTS=ECD,AI
# dokku config:set citemed-docs JIRA_EPIC_ISSUE_TYPE_ID=10000
```

**3. Confluence creds must be REAL, not the placeholders above.** The Jira
client reuses `CONFLUENCE_DOMAIN` / `CONFLUENCE_EMAIL` / `CONFLUENCE_API_TOKEN`.
With placeholders, escalation and live Jira status both no-op silently — the
button appears to work and nothing is ever created:

```bash
dokku config:show citemed-docs | grep -E 'CONFLUENCE_(EMAIL|API_TOKEN)'
```

**4. Redis, if you want real-time across workers.** The `Procfile` runs two
web workers; without `REDIS_URL` each has its own in-memory channel layer, so a
WebSocket broadcast only reaches clients on the worker that produced it. The
client falls back to a 30s poll, so nothing breaks — it's just not live:

```bash
dokku plugin:install https://github.com/dokku/dokku-redis.git   # one-time
dokku redis:create citemed-realtime
dokku redis:link citemed-realtime citemed-docs                  # sets REDIS_URL
```

**5. Check pending migrations.** Additive and nullable ones are safe to run
against a live database; anything that rewrites a table deserves a maintenance
window:

```bash
dokku run citemed-docs python manage.py showmigrations portal | grep '\[ \]'
```

## Deploy

From your laptop:

```bash
# Add Dokku remote (one-time)
git remote add dokku dokku@116.203.82.103:citemed-docs

# Push main to trigger the build + deploy
git push dokku main
```

The `release:` line in `Procfile` runs `manage.py migrate --noinput` automatically before the new web container takes over. `collectstatic` is run by the Python buildpack during build.

## Set up custom domain + HTTPS

```bash
dokku domains:add citemed-docs support.citemed.com
dokku domains:remove citemed-docs citemed-docs.116.203.82.103.sslip.io  # remove the auto-assigned one

# DNS: point an A record for support.citemed.com at 116.203.82.103 (and wait for it to propagate)

# Then enable HTTPS:
dokku letsencrypt:set citemed-docs email ops@citemed.com
dokku letsencrypt:enable citemed-docs
```

## Create the first admin user

```bash
dokku run citemed-docs python manage.py createsuperuser
```
Then visit `https://support.citemed.com/admin/` to manage `ContactSubmission` rows, `PortalUser` records, etc.

## Initial sync of Confluence content

```bash
dokku run citemed-docs python manage.py sync_from_mcp
```

## Scheduled re-sync (recommended)

Add a cron entry on the host that runs the sync hourly:

```bash
# /etc/cron.d/citemed-docs-sync
0 * * * * dokku ssh-keys:list >/dev/null 2>&1 && dokku run citemed-docs python manage.py sync_from_mcp >> /var/log/citemed-docs-sync.log 2>&1
```

(Or use the Dokku cron plugin if installed.)

## Verifying the deploy

```bash
# Logs (live)
dokku logs citemed-docs --tail

# Process status
dokku ps:report citemed-docs

# Restart (rarely needed; release phase + zero-downtime deploys handle this)
dokku ps:restart citemed-docs
```

In a browser:
- `https://support.citemed.com/` → redirects to `/login` (auth gate)
- `https://support.citemed.com/tickets` → public contact form (no auth)
- Submit a test contact form → check `/admin/portal/contactsubmission/` shows status=`sent`
- Check Mailgun dashboard for delivered event
- Click magic link → arrives back at `/docs/`

## Health checks and uptime monitoring

`GET /healthz/` reports on the three things that make this app work, and is what
the deploy gates on:

```bash
curl -s https://support.citemed.com/healthz/ | python -m json.tool
# {"status": "ok", "checks": {"database": "ok", "redis": "ok", "migrations": "ok"}}
```

- `database` — runs an actual `SELECT 1`, not just a connection object
- `redis` — a real `PING`; reports `skipped` when `REDIS_URL` is unset (local dev)
- `migrations` — `error` when the release's code is ahead of the schema

`200` when healthy, `503` when any check errors. It is unauthenticated (no
checker carries a session) and deliberately says nothing else — no versions, no
config, no counts. Failure reasons go to `dokku logs`, not to the response.

`app.json` registers it as a `startup` healthcheck, so **a release that can't
reach Postgres or Redis fails to promote instead of going live**. Before this
existed, every push printed `No healthchecks found in app.json for web process
type` and the only check was "is something listening on port 5000".

Verify the gate actually works — don't assume:

```bash
# Break a dependency on purpose and confirm the deploy REFUSES to promote.
dokku config:set citemed-docs REDIS_URL=redis://127.0.0.1:1/0
git commit --allow-empty -m "test healthcheck gate" && git push dokku main
#   expect: the deploy fails at the healthcheck step and the old release keeps serving
dokku redis:link citemed-redis citemed-docs   # restore (re-sets REDIS_URL)
```

> **Unverified on first deploy:** Dokku probes the container by its own IP, so
> that IP arrives as the `Host` header. `settings.py` appends the container's
> resolved IP to `ALLOWED_HOSTS` when `DEBUG=False` for exactly this reason. If
> the first deploy after this change fails its healthcheck, check
> `dokku logs citemed-docs` for `Invalid HTTP_HOST header` — the fallback is to
> add the internal host to `ALLOWED_HOSTS` explicitly.

### External uptime monitoring — still to be set up

The healthcheck only runs at deploy time. **Nothing yet watches production
between deploys**, so an outage at 2am is still found by a customer emailing in.
This needs a console action; it can't be done from the repo:

1. Create a monitor at [BetterStack](https://betterstack.com/better-uptime),
   UptimeRobot, or a Cloudflare health check — **anything except this host**. A
   monitor on the same box goes down with the thing it monitors.
2. Point it at `https://support.citemed.com/healthz/`, every 1–3 minutes.
3. Alert on a non-200 (the endpoint returns `503` when a dependency is down, so
   no keyword matching is needed).
4. Route alerts somewhere a human sees **out of hours** — phone/SMS or a paged
   Slack channel, not email alone.
5. Once it's collecting, the monthly uptime figure EC-SOP-07 §3.3 promises
   clients on request becomes reportable. It isn't today.

## Rollback

```bash
# Roll back to the previous release
dokku ps:rebuild citemed-docs           # rebuild from current code
dokku releases:rollback citemed-docs    # if releases plugin available, otherwise:
git push dokku <previous-sha>:main      # force-deploy a known-good commit
```

## Known gotchas

- **First push will take ~5 minutes** because both buildpacks have to install everything from scratch. Subsequent pushes are cached and take ~1–2 min.
- **`Pillow` needs libjpeg/libpng at build time** — the Heroku Python buildpack handles this automatically. If we ever migrate to a custom Dockerfile, install `libjpeg-dev libpng-dev` in the base image.
- **WhiteNoise serves the Vue build via Django's static pipeline**, so `collectstatic` MUST succeed during release. If you see "Static files not found" in browser, check that `frontend/dist/` was created by the Node buildpack step.
- **Magic-link emails use `FRONTEND_URL`** — if you change the domain, update that env var or the email link will be wrong.
