# Deploy Runbook - x3mphim.click

This runbook deploys MONI to `x3mphim.click` without touching `myauction.fun`.

## 1) One-time setup on VPS

1. Create project folder:
   - `mkdir -p /opt/moni`
   - `mkdir -p /opt/moni/backups`
2. Copy these files from repo to `/opt/moni`:
   - `docker-compose.prod.yml`
   - `.env.prod.example` -> rename to `.env` and fill real secrets
3. Install/verify Docker Engine + Compose plugin on VPS.
4. Keep host Nginx as public reverse proxy on `80/443`.
5. Optional fast-path script (recommended after files are copied):
   - `sudo DOMAIN=x3mphim.click PROJECT_DIR=/opt/moni bash /opt/moni/deploy/vps-first-setup.sh`

## 2) Configure environment (`/opt/moni/.env`)

Use `.env.prod.example` as baseline.

Rule agreed:
- Change required values for Auth/JWT + CORS/OAuth/Base URLs.
- Keep DB/Redis/Celery shape aligned with current local setup unless intentionally changed.

Required production values:
- `APP_ENV=production`
- `APP_BASE_URL=https://x3mphim.click`
- `API_PUBLIC_URL=https://x3mphim.click`
- `GOOGLE_OAUTH_REDIRECT_URI=https://x3mphim.click/api/v1/auth/google/callback`
- Strong `JWT_SECRET` (32+ chars, high entropy)
- Real SMTP credentials
- Real image tags for `BACKEND_IMAGE` and `FRONTEND_IMAGE`

## 3) Configure Nginx host

1. Copy `deploy/nginx/x3mphim.click.conf` to:
   - `/etc/nginx/sites-available/x3mphim.click`
2. Enable site:
   - `ln -sf /etc/nginx/sites-available/x3mphim.click /etc/nginx/sites-enabled/x3mphim.click`
3. Validate + reload:
   - `nginx -t`
   - `systemctl reload nginx`

Note: do not remove/modify `myauction.fun` site.

## 4) Issue TLS certificate (Let's Encrypt)

If cert does not exist yet:
- `certbot --nginx -d x3mphim.click`

Verify:
- `certbot certificates`
- `systemctl status certbot.timer --no-pager`

## 5) GitHub secrets for workflow

Repository secrets required:
- `VPS_HOST`
- `VPS_USER`
- `VPS_PORT` (optional, defaults 22)
- `VPS_SSH_KEY`
- `GHCR_USERNAME`
- `GHCR_TOKEN` (package read access)

## 6) Deploy flow

On push to `main`, workflow:
1. Build backend/frontend images.
2. Push images to GHCR (`sha` + `latest` tags).
3. SSH to VPS and:
   - update image tags in `/opt/moni/.env`
   - `docker compose pull`
   - backup postgres (`/opt/moni/backups/*.sql`)
   - run `alembic upgrade head`
   - `docker compose up -d`
   - probe `http://127.0.0.1:8010/api/v1/health`

Manual deploy command (if you need emergency deploy without Actions):

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
2. Confirm API via browser/devtools:
   - `GET /api/v1/health` returns `{ "status": "ok" }`.
3. Login with password.
4. Login with Google OAuth.
5. Open Dashboard/Monitors.
6. Trigger `Run Check` and verify status updates.
7. Optional: run smoke script from local with production base URLs.

## 8) Rollback

1. Set previous image tags in `/opt/moni/.env`:
   - `BACKEND_IMAGE=...`
   - `FRONTEND_IMAGE=...`
2. Re-run:
   - `docker compose --env-file .env -f docker-compose.prod.yml pull`
   - `docker compose --env-file .env -f docker-compose.prod.yml up -d`
3. If migration broke compatibility, restore latest DB backup from `/opt/moni/backups`.

## 9) OAuth checklist (must update in Google Console)

- Authorized JavaScript origins:
  - `https://x3mphim.click`
- Authorized redirect URIs:
  - `https://x3mphim.click/api/v1/auth/google/callback`
