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
  ALLOWED_HOSTS=docs.citemed.com \
  CSRF_TRUSTED_ORIGINS=https://docs.citemed.com \
  FRONTEND_URL=https://docs.citemed.com \
  ADMIN_PATH='<random-9-char-string>' \
  CONFLUENCE_DOMAIN=citemed.atlassian.net \
  CONFLUENCE_EMAIL=<sync-user-email> \
  CONFLUENCE_API_TOKEN=<token> \
  CONFLUENCE_SPACE_KEY=CITEMED \
  ATLASSIAN_CLOUD_ID=<cloud-id> \
  MAILGUN_ACCESS_KEY=<mailgun-key> \
  MAILGUN_SERVER_NAME=<mailgun-domain> \
  DEFAULT_FROM_EMAIL='CiteMed Support <support@citemedical.com>' \
  SUPPORT_EMAIL=support@citemed.com \
  PORTAL_MAGIC_LINK_EXPIRY_MINUTES=15
```

To reuse Mailgun creds from another Dokku app on the same host:
```bash
dokku config:show <other-app> | grep MAILGUN
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
dokku domains:add citemed-docs docs.citemed.com
dokku domains:remove citemed-docs citemed-docs.116.203.82.103.sslip.io  # remove the auto-assigned one

# DNS: point an A record for docs.citemed.com at 116.203.82.103 (and wait for it to propagate)

# Then enable HTTPS:
dokku letsencrypt:set citemed-docs email ops@citemed.com
dokku letsencrypt:enable citemed-docs
```

## Create the first admin user

```bash
dokku run citemed-docs python manage.py createsuperuser
```
Then visit `https://docs.citemed.com/admin/` to manage `ContactSubmission` rows, `PortalUser` records, etc.

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
- `https://docs.citemed.com/` → redirects to `/login` (auth gate)
- `https://docs.citemed.com/tickets` → public contact form (no auth)
- Submit a test contact form → check `/admin/portal/contactsubmission/` shows status=`sent`
- Check Mailgun dashboard for delivered event
- Click magic link → arrives back at `/docs/`

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
