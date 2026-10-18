#!/usr/bin/env bash
# Boots IMAGE with UCM_FIPS=1 and fails unless OpenSSL runs the FIPS provider
# and /api/v2/health reports fips_active: true. FIPS_CHECK_KEEP=1 leaves a
# passing container running for later steps.
set -euo pipefail

image=${1:?usage: check-fips-image.sh IMAGE [CONTAINER_NAME] [HOST_PORT]}
name=${2:-ucm-fips-check}
port=${3:-8443}
conf=/run/ucm/openssl-fips.cnf

passed=0
cleanup() {
    if [ "$passed" != 1 ] || [ "${FIPS_CHECK_KEEP:-0}" != 1 ]; then
        docker rm -f -v "$name" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT
fail() {
    echo "FAIL: $*" >&2
    docker logs "$name" >&2 || true
    exit 1
}

docker run -d --name "$name" -p "127.0.0.1:$port:8443" \
    -e UCM_FIPS=1 \
    -e SECRET_KEY=ci_fips_secret_key \
    -e JWT_SECRET_KEY=ci_fips_jwt_key \
    -e UCM_INITIAL_ADMIN_PASSWORD=changeme123 \
    "$image" >/dev/null

health=""
for i in $(seq 1 120); do
    [ "$(docker inspect -f '{{.State.Running}}' "$name")" = true ] || fail "container exited"
    health=$(curl -sk --max-time 5 "https://127.0.0.1:$port/api/v2/health" || true)
    if jq -e '.status == "ok"' >/dev/null 2>&1 <<<"$health"; then
        echo "ucm is up after ${i}s: $health"
        break
    fi
    health=""
    sleep 1
done
[ -n "$health" ] || fail "/api/v2/health did not answer"
jq -e '.fips_active == true' >/dev/null <<<"$health" || fail "fips_active is not true"

# The entrypoint exports OPENSSL_CONF to its own process only: name it here
providers=$(docker exec -e OPENSSL_CONF="$conf" "$name" openssl list -providers) \
    || fail "openssl list -providers failed"
printf '%s\n' "$providers"
printf '%s\n' "$providers" | awk '/^  [^ ]/{p=($1=="fips")} p&&/^ +status: active/{ok=1} END{exit !ok}' \
    || fail "the fips provider is not active"
if docker exec -e OPENSSL_CONF="$conf" "$name" sh -c 'echo x | openssl md5' >/dev/null 2>&1; then
    fail "MD5 still works under $conf"
fi

# Settings the module's security policy requires at 1 in the approved mode
for setting in security-checks conditional-errors tls1-prf-ems-check drbg-no-trunc-md; do
    docker exec "$name" grep -Eq "^[[:space:]]*$setting[[:space:]]*=[[:space:]]*1[[:space:]]*$" \
        /run/ucm/fipsmodule.cnf || fail "$setting is not 1 in fipsmodule.cnf"
done

# TLS: X25519 and X448 never negotiated, P-256 is
tls() { timeout 10 openssl s_client -connect "127.0.0.1:$port" "$@" </dev/null 2>&1 || true; }
tls -groups X25519:X448 | grep -q 'Cipher is (NONE)' || fail "TLS accepts X25519 or X448"
tls -groups P-256 | grep -Eq 'Temp Key: ECDH, prime256v1' || fail "TLS refuses P-256"
tls | grep -E 'Temp Key' | grep -q X25519 && fail "TLS negotiates X25519 by default"

passed=1
echo "FIPS check passed for $image"
