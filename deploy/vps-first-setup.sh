#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   chmod +x deploy/vps-first-setup.sh
#   sudo DOMAIN=x3mphim.click PROJECT_DIR=/opt/moni bash deploy/vps-first-setup.sh
#
# This script is safe for first-time MONI setup on VPS and does not modify myauction.fun.

DOMAIN="${DOMAIN:-x3mphim.click}"
PROJECT_DIR="${PROJECT_DIR:-/opt/moni}"
SITE_AVAILABLE="/etc/nginx/sites-available/${DOMAIN}"
SITE_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}"

echo "[1/8] Checking required commands..."
for cmd in docker nginx certbot; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd"
    exit 1
  fi
done

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose plugin is required but not found."
  exit 1
fi

echo "[2/8] Creating project folders..."
mkdir -p "${PROJECT_DIR}/backups"

echo "[3/8] Verifying required files in ${PROJECT_DIR}..."
required_files=(
  "${PROJECT_DIR}/docker-compose.prod.yml"
  "${PROJECT_DIR}/.env"
  "${PROJECT_DIR}/deploy/nginx/${DOMAIN}.conf"
)
for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Required file not found: $file"
    echo "Copy repo files to ${PROJECT_DIR} first."
    exit 1
  fi
done

echo "[4/8] Installing nginx site config for ${DOMAIN}..."
cp "${PROJECT_DIR}/deploy/nginx/${DOMAIN}.conf" "${SITE_AVAILABLE}"
ln -sf "${SITE_AVAILABLE}" "${SITE_ENABLED}"
nginx -t
systemctl reload nginx

echo "[5/8] Ensuring TLS certificate exists..."
if certbot certificates 2>/dev/null | grep -q "Domains:.*${DOMAIN}"; then
  echo "Certificate already exists for ${DOMAIN}."
else
  certbot --nginx -d "${DOMAIN}"
fi

echo "[6/8] Starting data services (postgres/redis)..."
cd "${PROJECT_DIR}"
docker compose --env-file .env -f docker-compose.prod.yml up -d postgres redis

echo "[7/8] Running migration..."
docker compose --env-file .env -f docker-compose.prod.yml run --rm api alembic upgrade head

echo "[8/8] Starting full stack..."
docker compose --env-file .env -f docker-compose.prod.yml up -d

echo "Done. Health check:"
curl -fsS http://127.0.0.1:8010/api/v1/health && echo
echo "Open: https://${DOMAIN}"
