# URL and Environment Conventions (dev / prod)

## Purpose

This document standardizes environment variables and URL contracts so that:

- development and production differ by values, not API path structure
- OAuth callback configuration is consistent
- CORS behavior is predictable
- DB/Redis/Celery config stays aligned across local and production

## Quick start

Read in this order:

1. `APP_BASE_URL` and `API_PUBLIC_URL`
2. Development or Production blocks
3. Frontend API base conventions
4. PostgreSQL / Redis / Celery sections
5. CORS section

## Core principles

- API prefix is fixed: `/api/v1`
- OAuth redirect URI must match exactly between:
  - backend env (`GOOGLE_OAUTH_REDIRECT_URI`)
  - Google Cloud Console
- Vite env variables (`VITE_*`) are loaded from the frontend directory
- `DATABASE_URL` uses the asyncpg dialect for backend runtime

## Variable roles

| Variable | Meaning |
|------|--------|
| `APP_BASE_URL` | Origin of the **Vue SPA** (verify-email links, post-login redirects). No trailing `/`. |
| `API_PUBLIC_URL` | Public origin of **FastAPI** used by browser and Google OAuth callbacks. No trailing `/`. |

## API path contract (fixed across environments)

- REST prefix: **`/api/v1`**
- Google OAuth callback handled by backend:  
  **`GET {API_PUBLIC_URL}/api/v1/auth/google/callback`**

All places in code and cloud config must use the same callback URI string defined by `GOOGLE_OAUTH_REDIRECT_URI`.

## Development (local default)

| Component | URL |
|------------|-----|
| SPA (Vite) | `http://localhost:5173` |
| API (uvicorn) | `http://localhost:8000` |
| Google OAuth redirect URI | `http://localhost:8000/api/v1/auth/google/callback` |

Example `.env` values:

```env
APP_BASE_URL=http://localhost:5173
API_PUBLIC_URL=http://localhost:8000
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
```

Google Cloud Console (OAuth client, Web):

- Authorized JavaScript origins: `http://localhost:5173`
- Authorized redirect URIs: `http://localhost:8000/api/v1/auth/google/callback`

## Production (VPS + HTTPS)

Example domain mapping:

| Component | Example URL |
|------------|-----------|
| SPA | `https://app.example.com` |
| API | `https://api.example.com` |

```env
APP_BASE_URL=https://app.example.com
API_PUBLIC_URL=https://api.example.com
GOOGLE_OAUTH_REDIRECT_URI=https://api.example.com/api/v1/auth/google/callback
```

Google Cloud Console:

- Authorized JavaScript origins: `https://app.example.com`
- Authorized redirect URIs: `https://api.example.com/api/v1/auth/google/callback`

## Frontend API base

Set in `frontend/.env` or `frontend/.env.development` / `frontend/.env.production` (Vite reads only `VITE_*` from frontend scope):

- Dev (recommended): leave `VITE_API_BASE_URL` empty and call `/api/v1/...` via Vite proxy (`vite.config.ts` -> `http://127.0.0.1:8010`). This avoids cross-origin CORS during local development.
- Dev (direct API call): set `VITE_API_BASE_URL=http://127.0.0.1:8010` and ensure backend CORS is enabled for that origin.
- Prod: set `VITE_API_BASE_URL=https://api.example.com` (no Vite proxy in static hosting).

Final API URL pattern remains: `(VITE_API_BASE_URL or '') + '/api/v1/...'`.

## PostgreSQL (`DATABASE_URL`)

Single Postgres instance is used by API and worker flows. Async SQLAlchemy URL format:

```text
postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DATABASE
```

### pgAdmin <-> `.env` alignment (dev)

Use the same credentials in pgAdmin and `.env`:

| pgAdmin field | Local dev value |
|--------------------------------------------------|-------------------------|
| Server name | `MONI local` (display label only) |
| Host | `localhost` |
| Port | `5432` |
| Database | `moni` |
| User | `moni` |
| Password | must match `DATABASE_URL` |

Example:

```env
DATABASE_URL=postgresql+asyncpg://moni:moni_local_dev@localhost:5432/moni
```

First-time SQL setup (superuser):

```sql
CREATE USER moni WITH PASSWORD 'moni_local_dev';
CREATE DATABASE moni OWNER moni;
```

If password changes, update both Postgres and `DATABASE_URL`. URL-encode special characters in the password.

| Part | Dev local | Prod (Docker/VPS) |
|------|-----------|---------------------|
| `USER` / `DATABASE` | usually `moni` / `moni` | project-specific |
| `HOST` | `localhost` | Docker service (`postgres`) or host binding |
| `PORT` | `5432` | usually `5432` |
| `PASSWORD` | local setup value | secure env value |

Do not switch to plain `postgresql://` in runtime where asyncpg is expected.

Postgres 15+ note for schema permissions:

`GRANT ALL ON SCHEMA public TO moni;`  
or set DB owner accordingly.

## Redis (`REDIS_URL`)

Redis is used for Celery broker and result backend. Format:

```text
redis://[PASSWORD@]HOST:PORT/DBINDEX
```

Local example:

```env
REDIS_URL=redis://localhost:6379/0
```

| Part | Meaning |
|------|--------|
| `HOST` / `PORT` | default `6379`; in Compose usually `redis` |
| `DBINDEX` | `0`-`15`; `/0` is enough for MVP |
| Password form | `redis://:yourpassword@host:port/0` |

Local setup options:

1. Install Redis locally or run `redis:7-alpine` in Docker
2. Verify with `redis-cli -u redis://localhost:6379/0 ping` -> `PONG`
3. Set env values accordingly

Redis Cloud format:

`redis://default:PASSWORD@HOST:PORT/0`

If TLS is required, use `rediss://...`.

### Celery and Beat variables

| Variable | Role |
|------|--------|
| `CELERY_BROKER_URL` | task queue broker |
| `CELERY_RESULT_BACKEND` | task state/result backend |

Celery Beat has no dedicated env variable; it uses the same app and broker settings as worker.

## CORS

Backend origin policy is anchored to `APP_BASE_URL`.

- In development, backend may allow localhost/127.0.0.1 flexible origins to avoid local CORS friction.
- In production, keep strict origin policy to real HTTPS origins only.

Note: when SMTP fails during registration flow, API should return explicit `smtp_failed` with 503 rather than generic 500.
