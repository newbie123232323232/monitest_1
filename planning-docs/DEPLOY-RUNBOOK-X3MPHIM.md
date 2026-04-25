# Deploy Runbook - x3mphim.click

## Purpose and scope

This runbook documents production deployment for MONI using:
- Docker Compose on a VPS
- host-level Nginx reverse proxy on ports 80/443
- GitHub Actions + GHCR image delivery

This version is written for `x3mphim.click`.
If the domain changes (for example `monitest.top`), keep the same process and update only domain/env/OAuth values.

## High-level flow

1. One-time VPS setup and folder structure
2. Production environment wiring
3. Nginx site + TLS provisioning
4. GitHub secrets + deploy workflow
5. Post-deploy verification
6. Rollback path

## Operational notes

- Do not modify unrelated sites on the same VPS.
- Always back up DB before migration.
- Keep OAuth URLs in sync with production domain.
- Celery `worker` and `beat` are separate services by design (not embedded in API process).
- A deployment is considered healthy only when `api + worker + beat` are all up.

This runbook deploys MONI to `x3mphim.click` without touching `myauction.fun`.

## 1) One-time setup on VPS

1. Create project folders:
   - `mkdir -p /opt/moni`
   - `mkdir -p /opt/moni/backups`
2. Copy deployment files into `/opt/moni`:
   - `docker-compose.prod.yml`
   - `.env.prod.example` -> rename to `.env` and fill real values
3. Install/verify Docker Engine + Compose plugin on VPS.
4. Keep host Nginx as the public reverse proxy on `80/443`.
5. Optional fast-path setup:
   - `sudo DOMAIN=x3mphim.click PROJECT_DIR=/opt/moni bash /opt/moni/deploy/vps-first-setup.sh`

## 2) Configure environment (`/opt/moni/.env`)

Use `.env.prod.example` as the baseline.

Agreed rule:
- change required values for Auth/JWT + CORS/OAuth/Base URLs
- keep DB/Redis/Celery shape aligned with current local setup unless intentionally migrating

Required production values:
- `APP_ENV=production`
- `APP_BASE_URL=https://x3mphim.click`
- `API_PUBLIC_URL=https://x3mphim.click`
- `GOOGLE_OAUTH_REDIRECT_URI=https://x3mphim.click/api/v1/auth/google/callback`
- strong `JWT_SECRET` (32+ chars, high entropy)
- real SMTP credentials
- real image tags for `BACKEND_IMAGE` and `FRONTEND_IMAGE`

## 3) Configure host Nginx

1. Copy `deploy/nginx/x3mphim.click.conf` to:
   - `/etc/nginx/sites-available/x3mphim.click`
2. Enable the site:
   - `ln -sf /etc/nginx/sites-available/x3mphim.click /etc/nginx/sites-enabled/x3mphim.click`
3. Validate and reload:
   - `nginx -t`
   - `systemctl reload nginx`

Note: do not remove or modify `myauction.fun` site.

## 4) Issue TLS certificate (Let's Encrypt)

If certificate does not exist:
- `certbot --nginx -d x3mphim.click`

Verify:
- `certbot certificates`
- `systemctl status certbot.timer --no-pager`

## 5) GitHub secrets required by workflow

- `VPS_HOST`
- `VPS_USER`
- `VPS_PORT` (optional, defaults to 22)
- `VPS_SSH_KEY`
- `GHCR_USERNAME`
- `GHCR_TOKEN` (package read access)

## 6) Deploy flow

On push to `main`, workflow does:
1. Build backend and frontend images.
2. Push images to GHCR (`sha` and `latest` tags).
3. SSH into VPS and:
   - update image tags in `/opt/moni/.env`
   - run `docker compose pull`
   - create postgres backup (`/opt/moni/backups/*.sql`)
   - run `alembic upgrade head`
   - run `docker compose up -d`
   - probe `http://127.0.0.1:8010/api/v1/health`

Manual emergency deploy (without Actions):

```bash
cd /opt/moni
docker compose --env-file .env -f docker-compose.prod.yml pull
docker compose --env-file .env -f docker-compose.prod.yml up -d postgres redis
docker compose --env-file .env -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose --env-file .env -f docker-compose.prod.yml up -d
curl -fsS http://127.0.0.1:8010/api/v1/health
```

## 7) Post-deploy verification

1. Open `https://x3mphim.click`.
2. Verify API response:
   - `GET /api/v1/health` returns `{ "status": "ok" }`.
3. Login with password.
4. Login with Google OAuth.
5. Open Dashboard/Monitors.
6. Trigger `Run Check` and validate state updates.
7. Optional: run smoke script from local against production URLs.

### 7.1 Swagger/docs exposure policy

- By default, production should keep docs disabled:
  - `EXPOSE_DOCS_IN_PRODUCTION=false`
- If temporary API testing via Swagger is required on production:
  1. Set `EXPOSE_DOCS_IN_PRODUCTION=true` in `.env`.
  2. Restart API service.
  3. Verify `/docs` loads normally (CSP for docs route is handled separately in backend middleware).
  4. After testing, set it back to `false` and restart API.

### 7.2 Celery runtime verification (critical)

Run:

```bash
docker compose --env-file .env -f docker-compose.prod.yml ps
```

Expected:
- `api` is `Up`
- `worker` is `Up`
- `beat` is `Up`

If `worker/beat` are down, manual run-check may stay `queued` and scheduled checks will not execute.

## 8) Rollback

1. Set previous image tags in `/opt/moni/.env`:
   - `BACKEND_IMAGE=...`
   - `FRONTEND_IMAGE=...`
2. Re-run:
   - `docker compose --env-file .env -f docker-compose.prod.yml pull`
   - `docker compose --env-file .env -f docker-compose.prod.yml up -d`
3. If migration is incompatible, restore latest DB backup from `/opt/moni/backups`.

## 9) OAuth checklist (must update in Google Cloud Console)

- Authorized JavaScript origins:
  - `https://x3mphim.click`
- Authorized redirect URIs:
  - `https://x3mphim.click/api/v1/auth/google/callback`
