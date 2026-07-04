#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/science-knot}"
PUBLIC_IP="${PUBLIC_IP:-5.42.118.92}"

echo "== Science Knot server repair/check =="
echo "app_dir=$APP_DIR"
echo "public_ip=$PUBLIC_IP"
echo

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: run as root" >&2
  exit 1
fi

echo "== OS =="
uname -a || true
. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" || true
echo

echo "== Network listeners before compose =="
ss -ltnp 'sport = :80 or sport = :8001 or sport = :22' || true
echo

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Installing..."
  apt-get update
  apt-get install -y ca-certificates curl gnupg tar
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

echo "== Docker =="
docker --version
docker compose version
systemctl is-active docker || systemctl start docker
echo

if [ ! -d "$APP_DIR" ]; then
  echo "ERROR: $APP_DIR does not exist. Upload and unpack the project first." >&2
  exit 2
fi

cd "$APP_DIR"

if [ ! -f docker-compose.prod.yml ]; then
  echo "ERROR: docker-compose.prod.yml is missing in $APP_DIR." >&2
  echo "Files in app dir:"
  ls -la
  exit 3
fi

if [ ! -f .env ]; then
  echo "ERROR: .env is missing in $APP_DIR." >&2
  echo "Create it from .env.production.example and set YANDEX_AI_API_KEY/YANDEX_AI_FOLDER_ID."
  exit 4
fi

mkdir -p data/runtime data/exports data/registry data/uploads corpus_ascii

echo "== Important files =="
ls -lah docker-compose.prod.yml .env frontend/Dockerfile.prod backend/Dockerfile 2>/dev/null || true
echo "corpus files count:"
find corpus_ascii -type f 2>/dev/null | wc -l || true
echo

echo "== Compose config check =="
docker compose -f docker-compose.prod.yml config >/tmp/science-knot-compose-config.yml
echo "compose config ok"
echo

echo "== Rebuild and restart =="
docker compose -f docker-compose.prod.yml down --remove-orphans
docker compose -f docker-compose.prod.yml up -d --build
echo

echo "== Compose ps =="
docker compose -f docker-compose.prod.yml ps
echo

echo "== Waiting for API health =="
ok=0
for i in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:8001/health" >/tmp/science-knot-health.json; then
    ok=1
    cat /tmp/science-knot-health.json
    echo
    break
  fi
  sleep 2
done

if [ "$ok" != "1" ]; then
  echo "ERROR: API is not healthy." >&2
  echo
  echo "== Container logs =="
  docker compose -f docker-compose.prod.yml logs --tail=180 >&2 || true
  echo
  echo "== Listeners after failed start =="
  ss -ltnp 'sport = :80 or sport = :8001 or sport = :22' >&2 || true
  exit 5
fi

echo "== Frontend check =="
curl -fsSI "http://127.0.0.1/" | sed -n '1,20p'
echo

echo "== Register corpus =="
curl -fsS -X POST "http://127.0.0.1:8001/api/demo/register-corpus" || true
echo

echo "== Final external URLs =="
echo "Frontend: http://${PUBLIC_IP}"
echo "API:      http://${PUBLIC_IP}:8001"
echo "Health:   http://${PUBLIC_IP}:8001/health"
