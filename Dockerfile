# Local-dev image for the Django/ASGI backend.
#
# Production runs on Dokku's buildpacks (see DEPLOY.md) — this image exists so
# `docker compose up` gives you the whole stack (Postgres, Redis, API, Vite)
# without installing Python, Node or a database on the host.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# git: the trinity-atlassian-cli dependency installs from a git+https URL.
# libpq5: psycopg2-binary's runtime shared library.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements are copied on their own so the (slow) install layer is cached
# and only re-runs when the dependency list actually changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# The source tree is bind-mounted over this in compose, so the COPY only
# matters for a standalone `docker build`.
COPY . .

EXPOSE 8001

CMD ["python", "manage.py", "runserver", "0.0.0.0:8001"]
