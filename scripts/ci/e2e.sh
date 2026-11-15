#!/usr/bin/env bash
# End-to-end suite: builds the interface, starts one UCM instance on a free loopback port
# with a fresh SQLite database in a temporary directory, runs Playwright against it, and
# always stops the instance. Exit code: Playwright's. Arguments go to `playwright test`.
# Run from the repository root. Writes only under a temporary directory and frontend/.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT" || exit 2
if [ ! -f backend/wsgi.py ] || [ ! -f frontend/package.json ]; then
  echo "e2e: not a UCM checkout: $ROOT" >&2
  exit 2
fi

# settings.py loads <checkout>/.env under env -i too: its database, Redis or keys would be the
# instance's, and the restore test replaces that database
if [ -e .env ]; then
  echo "e2e: $ROOT/.env would configure the test instance: move it aside to run the suite" >&2
  exit 2
fi

PY=${UCM_PYTHON:-$(command -v python || command -v python3)}
[ -n "$PY" ] || { echo "e2e: no python on PATH (set UCM_PYTHON)" >&2; exit 2; }
command -v npm >/dev/null || { echo "e2e: no npm on PATH" >&2; exit 2; }

WORK=$(mktemp -d "${TMPDIR:-/tmp}/ucm-e2e.XXXXXX") || exit 2
PID=""
# The functions below run from the EXIT trap (SC2317, SC2329: reached, though never called by name)
# shellcheck disable=SC2317,SC2329
stop_instance() {
  [ -n "$PID" ] || return 0
  # The instance runs in its own process group (setsid): TERM it, then KILL what is left
  kill -TERM -- "-$PID" 2>/dev/null
  for _ in $(seq 1 30); do kill -0 -- "-$PID" 2>/dev/null || break; sleep 1; done
  kill -KILL -- "-$PID" 2>/dev/null
  wait "$PID" 2>/dev/null
  PID=""
}
# shellcheck disable=SC2317,SC2329
finish() {
  stop_instance
  rm -rf "$WORK"
}
trap finish EXIT
trap 'exit 130' INT TERM

echo "== building the interface"
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm ci --no-audit --no-fund) || exit 2
fi
(cd frontend && npm run build) || { echo "e2e: interface build failed" >&2; exit 2; }

PORT=$("$PY" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])') || exit 2
PASSWORD="E2e-$("$PY" -c 'import secrets; print(secrets.token_hex(8))')-9z"
BASE_URL="https://127.0.0.1:$PORT"
mkdir -p "$WORK/data" "$WORK/config" "$WORK/logs" "$WORK/home" "$WORK/tmp"
SECRET=$("$PY" -c 'import secrets; print(secrets.token_hex(32))')

# Only what is set here reaches the instance (.env is refused above); the guard kills it if it
# touches an installation path
echo "== starting UCM on $BASE_URL (data in $WORK/data)"
(cd backend && exec env -i \
    PATH="$PATH" HOME="$WORK/home" TMPDIR="$WORK/tmp" LC_ALL=C.UTF-8 \
    PYTHONPATH="$ROOT/backend/tests/ha/guard:$ROOT/backend" PYTHONDONTWRITEBYTECODE=1 \
    UCM_HA_GUARD_FILE="$WORK/guard.log" UCM_CONFIG_DIR="$WORK/config" UCM_BASE_PATH="$WORK" \
    DATA_DIR="$WORK/data" HOST=127.0.0.1 HTTPS_PORT="$PORT" HTTP_PROTOCOL_PORT=0 HTTP_REDIRECT=false \
    UCM_LOG_FILE="$WORK/logs/ucm.log" UCM_LOG_DIR="$WORK/logs" \
    ACCESS_LOG="$WORK/logs/access.log" ERROR_LOG="$WORK/logs/error.log" \
    SECRET_KEY="$SECRET" INITIAL_ADMIN_PASSWORD="$PASSWORD" FQDN=ucm-e2e.test \
    setsid "$PY" -m gunicorn -c gunicorn_config.py wsgi:app) > "$WORK/console.log" 2>&1 &
PID=$!

dump_logs() {
  local f
  for f in "$WORK/console.log" "$WORK/logs/ucm.log" "$WORK/logs/access.log" "$WORK/guard.log"; do
    if [ -s "$f" ]; then echo "--- $(basename "$f") (last 100 lines)"; tail -n 100 "$f"; fi
  done
}

wait_healthy() {
  if command -v curl >/dev/null && command -v jq >/dev/null; then
    scripts/ci/wait-health.sh "$1" 180
    return
  fi
  # Same rule as wait-health.sh, for an environment without curl or jq
  "$PY" - "$1" 180 <<'EOF'
import json, ssl, sys, time, urllib.request
url, deadline = sys.argv[1], time.monotonic() + int(sys.argv[2])
ctx = ssl._create_unverified_context()
last = ''
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=5) as r:
            body = json.loads(r.read())
            if r.status == 200 and body.get('status') == 'ok' and body.get('service') == 'ucm' and not body.get('safe_mode'):
                print('healthy:', json.dumps(body)[:300]); sys.exit(0)
            last = json.dumps(body)[:300]
    except Exception as e:
        last = repr(e)
    time.sleep(1)
print(f'FAIL: {url} not healthy: {last}', file=sys.stderr); sys.exit(1)
EOF
}

if ! wait_healthy "$BASE_URL/api/v2/health" || ! kill -0 "$PID" 2>/dev/null; then
  echo "e2e: the instance did not become healthy" >&2
  dump_logs
  exit 2
fi

echo "== Playwright"
cd frontend || exit 2
npx playwright install chromium || { echo "e2e: browser download failed" >&2; exit 2; }
# UCM_E2E_MANAGED: the instance is this script's own, so the setup may change it and restore over it
UCM_E2E_MANAGED=1 UCM_E2E_BASE_URL="$BASE_URL" UCM_E2E_ADMIN_PASSWORD="$PASSWORD" npx playwright test "$@"
RC=$?
if [ "$RC" -ne 0 ]; then dump_logs; fi
exit "$RC"
