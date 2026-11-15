#!/usr/bin/env bash
# Starts IMAGE with UCM_FIPS=1 on a copy of its fips.so with one byte appended, and
# fails unless the entrypoint stops with exit 1, saying the module was modified since
# the build, before it writes the provider configuration.
# Called by check-fips-image.sh; publishes no port.
set -euo pipefail

image=${1:?usage: check-fips-module-tamper.sh IMAGE [CONTAINER_NAME]}
name=${2:-ucm-fips-tamper}
work=$(mktemp -d)
cleanup() {
    docker rm -f -v "$name" >/dev/null 2>&1 || true
    rm -rf "$work"
}
trap cleanup EXIT
fail() {
    echo "FAIL: $*" >&2
    [ -f "$work/start.log" ] && cat "$work/start.log" >&2
    exit 1
}

module=$(docker run --rm --entrypoint sh "$image" -c \
    'echo "$(openssl version -m | sed -E "s/^MODULESDIR: \"(.*)\"$/\1/")/fips.so"') \
    || fail "cannot locate fips.so in $image"
docker create --name "$name" \
    -e UCM_FIPS=1 \
    -e SECRET_KEY=ci_fips_secret_key \
    -e UCM_INITIAL_ADMIN_PASSWORD=changeme123 \
    "$image" >/dev/null
docker cp "$name:$module" "$work/fips.so"
printf 'x' >> "$work/fips.so"
chmod 0644 "$work/fips.so"
docker cp "$work/fips.so" "$name:$module"

rc=0
timeout 180 docker start -a "$name" > "$work/start.log" 2>&1 || rc=$?
[ "$rc" = 1 ] || fail "a modified fips.so started with exit code $rc, expected 1"
grep -q 'modified since the image was built' "$work/start.log" \
    || fail "the refusal does not say the module was modified since the image was built"
# Exit 1 can come from a later step: the start must stop before the provider config is written
if docker cp "$name:/run/ucm/openssl-fips.cnf" - >/dev/null 2>&1; then
    fail "the start went past the module check: /run/ucm/openssl-fips.cnf was written"
fi
echo "modified fips.so refused at start: exit 1"
