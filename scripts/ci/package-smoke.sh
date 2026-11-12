#!/bin/sh
# Install a published DEB or RPM in a bare distribution container and check it runs.
# Usage: package-smoke.sh /path/to/ucm.deb|ucm.rpm   (run as root inside the container)
# POSIX sh, not bash: bare images guarantee /bin/sh only. No systemctl is needed,
# since the container has no systemd as PID 1: the unit's command is started by hand.

PKG=${1:-}
# Overridable so a test can keep every write under its own directory; defaults are the package's.
HOME_DIR=${UCM_SMOKE_HOME:-/opt/ucm}
ENV_FILE=${UCM_SMOKE_ENV_FILE:-/etc/ucm/ucm.env}
RUN_DIR=${UCM_SMOKE_RUN_DIR:-/tmp/ucm-smoke}
SUDOERS_DIR=${UCM_SMOKE_SUDOERS_DIR:-/etc/sudoers.d}
INSTALL_LOG=$RUN_DIR/install.log
WAIT=${SMOKE_WAIT:-90}
FAILS=0

fail() { FAILS=$((FAILS + 1)); echo "FAIL: $*"; }
ok() { echo "ok: $*"; }
as_ucm() { su -s /bin/sh ucm -c "$1"; }

[ -f "$PKG" ] || { echo "FAIL: usage: package-smoke.sh <package file>"; exit 2; }
[ "$(id -u)" = 0 ] || { echo "FAIL: must run as root"; exit 2; }

# shellcheck disable=SC2016
case "$PKG" in
  *.deb)
    export DEBIAN_FRONTEND=noninteractive
    WANT=$(dpkg-deb -f "$PKG" Version 2>/dev/null)
    UNSUDO='dpkg --purge --force-depends sudo'
    DEPS_CHECK='apt-get check'
    INSTALL='apt-get update -qq && apt-get install -y -qq "$PKG"'
    GET_SU=:
    ;;
  *.rpm)
    WANT=$(rpm -qp --qf '%{VERSION}' "$PKG" 2>/dev/null)
    UNSUDO='rpm -e --nodeps sudo'
    DEPS_CHECK='dnf check --dependencies'
    INSTALL='dnf install -y -q "$PKG"'
    GET_SU='dnf install -y -q util-linux'
    ;;
  *) echo "FAIL: unsupported package type: $PKG"; exit 2 ;;
esac
# The package must not need sudo: start from an image without it, so a later sudo is the package's.
if command -v sudo >/dev/null 2>&1; then
  eval "$UNSUDO" >/dev/null 2>&1
  hash -r 2>/dev/null
  command -v sudo >/dev/null 2>&1 && { echo "FAIL: precondition: sudo cannot be removed from this image"; exit 2; }
  eval "$DEPS_CHECK" >/dev/null 2>&1 || { echo "FAIL: precondition: removing sudo broke package dependencies in this image"; exit 2; }
fi
# Checks run as ucm through su: without it they would blame the package. Container images
# of Fedora ship util-linux-core, which lacks su; util-linux does not bring sudo.
command -v su >/dev/null 2>&1 || eval "$GET_SU" >/dev/null 2>&1
command -v su >/dev/null 2>&1 || { echo "FAIL: precondition: su is missing in this image"; exit 2; }
mkdir -p "$RUN_DIR" || { echo "FAIL: precondition: cannot create $RUN_DIR"; exit 2; }
if ! eval "$INSTALL" >"$INSTALL_LOG" 2>&1; then
  tail -n 30 "$INSTALL_LOG"
  echo "FAIL: package installation exited non-zero"
  exit 1
fi
ok "package installed"
WANT=$(echo "$WANT" | tr '~' '-')

command -v sudo >/dev/null 2>&1 && fail "sudo is present: the package must not need it"
set -- "$SUDOERS_DIR"/ucm*
[ -e "$1" ] && fail "sudoers file created: $*"

[ -x "$HOME_DIR/venv/bin/python" ] || fail "venv interpreter missing in $HOME_DIR/venv"
for mod in cryptography gevent psycopg lxml xmlsec pkcs11; do
  as_ucm "$HOME_DIR/venv/bin/python -c 'import $mod'" >/dev/null 2>&1 || fail "venv cannot import $mod"
done

[ -f "$ENV_FILE" ] || fail "$ENV_FILE missing"
# shellcheck disable=SC1090
PORT=$( . "$ENV_FILE" 2>/dev/null; echo "${HTTPS_PORT:-8443}")

# Same user, directory, environment file and command as the systemd unit
chown ucm "$RUN_DIR"
as_ucm "cd $HOME_DIR/backend && set -a && . $ENV_FILE && set +a && \
  echo \$\$ > $RUN_DIR/pid && exec $HOME_DIR/venv/bin/gunicorn -c gunicorn_config.py wsgi:app" \
  >"$RUN_DIR/app.log" 2>&1 &

# The announced bound is wall-clock: each probe is capped by what remains of WAIT.
BODY=
START=$(date +%s)
ELAPSED=0
while [ "$ELAPSED" -lt "$WAIT" ]; do
  LEFT=$((WAIT - ELAPSED)); [ "$LEFT" -gt 3 ] && LEFT=3
  BODY=$("$HOME_DIR/venv/bin/python" -c "
import ssl, urllib.request
c = ssl._create_unverified_context()
print(urllib.request.urlopen('https://127.0.0.1:$PORT/api/v2/health', timeout=$LEFT, context=c).read().decode())
" 2>/dev/null) && break
  BODY=
  sleep 1
  ELAPSED=$(($(date +%s) - START))
done
ELAPSED=$(($(date +%s) - START))
if [ -z "$BODY" ]; then
  tail -n 30 "$RUN_DIR/app.log"
  fail "/api/v2/health gave no 200 over HTTPS within ${WAIT}s"
else
  ok "health answered after ${ELAPSED}s"
  GOT=$(echo "$BODY" | "$HOME_DIR/venv/bin/python" -c "import json,sys; print(json.load(sys.stdin).get('version',''))" 2>/dev/null)
  if [ -n "$GOT" ] && [ "$GOT" != "$WANT" ]; then
    fail "health reports version $GOT, package is $WANT"
  fi
  SAFE=$(echo "$BODY" | "$HOME_DIR/venv/bin/python" -c "import json,sys; print(bool(json.load(sys.stdin).get('safe_mode')))" 2>/dev/null)
  [ "$SAFE" = True ] && fail "health reports safe_mode: the application started degraded"
fi

# Clean stop: TERM the process, it must exit within 35s
PID=$(cat "$RUN_DIR/pid" 2>/dev/null)
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  kill -TERM "$PID"
  i=0
  while [ "$i" -lt 35 ] && kill -0 "$PID" 2>/dev/null; do i=$((i + 1)); sleep 1; done
  if kill -0 "$PID" 2>/dev/null; then kill -KILL "$PID"; fail "application did not stop within 35s of SIGTERM"; fi
else
  fail "application is not running at the end of the check"
fi

[ "$FAILS" -eq 0 ] && { echo "package smoke passed"; exit 0; }
echo "package smoke: $FAILS check(s) failed"
exit 1
