#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/science-knot"
ARCHIVE="${1:-/tmp/nornikel_hack_deploy_light.tgz}"
PUBLIC_IP="${PUBLIC_IP:-5.42.118.92}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root" >&2
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl gnupg tar
install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
fi
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

mkdir -p "$APP_DIR"
tar -xzf "$ARCHIVE" -C "$APP_DIR"
cd "$APP_DIR"
mkdir -p data/runtime data/exports data/registry data/uploads corpus_ascii

if [ ! -f .env ]; then
  cat > .env <<EOF
SCIENCE_KNOT_LLM_PROVIDER=yandex
YANDEX_AI_API_KEY=REPLACE_ME
YANDEX_AI_FOLDER_ID=REPLACE_ME
YANDEX_AI_MODEL=yandexgpt-lite/latest
PUBLIC_API_BASE_URL=http://${PUBLIC_IP}:8001
SCIENCE_KNOT_NEO4J_PASSWORD=science-knot-demo
POSTGRES_PASSWORD=science
EXTERNAL_SOURCES_ENABLED=true
OPENALEX_ENABLED=true
CROSSREF_ENABLED=true
GOOGLE_PATENTS_ENABLED=true
EOF
  echo "Created $APP_DIR/.env. Edit YANDEX_AI_API_KEY and YANDEX_AI_FOLDER_ID before running docker compose." >&2
  exit 2
fi

docker compose -f docker-compose.prod.yml up -d --build

echo "Waiting for API..."
for i in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:8001/health" >/tmp/science-knot-health.json; then
    cat /tmp/science-knot-health.json
    echo
    echo "Frontend: http://${PUBLIC_IP}"
    echo "API:      http://${PUBLIC_IP}:8001"
    exit 0
  fi
  sleep 2
done

echo "API did not become healthy in time. Recent logs:" >&2
docker compose -f docker-compose.prod.yml logs --tail=120 >&2
exit 1
