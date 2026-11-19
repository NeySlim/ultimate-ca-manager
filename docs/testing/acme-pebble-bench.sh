#!/usr/bin/env bash
# ACME client bench: UCM against Pebble and pebble-challtestsrv, in throwaway containers.
# Runs on a Docker host. See acme-pebble-bench.md for the procedure.
#
#   acme-pebble-bench.sh build <source-tree>   build the UCM image from a source tree
#   acme-pebble-bench.sh up                     network, challtestsrv, Pebble, UCM
#   acme-pebble-bench.sh down                   remove containers, volumes and network
#   acme-pebble-bench.sh status
set -euo pipefail

PREFIX="${BENCH_PREFIX:-ucm-pebble}"
NET="${PREFIX}-net"
SUBNET="${BENCH_SUBNET:-10.231.77.0/24}"
NET_BASE="${SUBNET%.*}"            # 10.231.77
CHALLTEST_IP="${NET_BASE}.2"
PEBBLE_IP="${NET_BASE}.3"
UCM_IP="${NET_BASE}.4"
WORKDIR="${BENCH_WORKDIR:-$(pwd)/${PREFIX}-work}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

UCM_IMAGE="${UCM_IMAGE:-${PREFIX}-ucm:bench}"
PEBBLE_IMAGE="${PEBBLE_IMAGE:-ghcr.io/letsencrypt/pebble@sha256:ddf230642b1a584f519f32e347de1b05a6e4c1f6c35c1863b33effeab5f78199}"
CHALLTEST_IMAGE="${CHALLTEST_IMAGE:-ghcr.io/letsencrypt/pebble-challtestsrv@sha256:12ce21884def456bcf9786542113949e1f19dc7738d2c70e156c2d0c38a1405b}"

# Retry-After (seconds) Pebble sends on a processing order: the window the
# finalize-crash scenario uses, and what the polling scenario measures.
PEBBLE_RETRY_AFTER_ORDER="${PEBBLE_RETRY_AFTER_ORDER:-40}"
PEBBLE_AUTHZREUSE="${PEBBLE_AUTHZREUSE:-0}"
PEBBLE_WFE_NONCEREJECT="${PEBBLE_WFE_NONCEREJECT:-0}"

cmd_build() {
    local src="${1:?usage: build <source-tree>}"
    # The image copies frontend/dist: a placeholder is enough for an API-only bench.
    if [ ! -f "$src/frontend/dist/index.html" ]; then
        mkdir -p "$src/frontend/dist"
        echo '<!doctype html><title>bench</title>' > "$src/frontend/dist/index.html"
    fi
    docker build -q -t "$UCM_IMAGE" --label "${PREFIX}=1" "$src"
}

write_pebble_config() {
    mkdir -p "$WORKDIR"
    local id
    id=$(docker create "$PEBBLE_IMAGE")
    docker cp "$id:/test/certs/pebble.minica.pem" "$WORKDIR/pebble.minica.pem" >/dev/null
    docker rm "$id" >/dev/null
    cat > "$WORKDIR/pebble-config.json" <<EOF
{
  "pebble": {
    "listenAddress": "0.0.0.0:14000",
    "managementListenAddress": "0.0.0.0:15000",
    "certificate": "test/certs/localhost/cert.pem",
    "privateKey": "test/certs/localhost/key.pem",
    "httpPort": 5002,
    "tlsPort": 5001,
    "ocspResponderURL": "",
    "externalAccountBindingRequired": false,
    "domainBlocklist": ["blocked-domain.example"],
    "retryAfter": {"authz": 3, "order": ${PEBBLE_RETRY_AFTER_ORDER}},
    "keyAlgorithm": "ecdsa",
    "profiles": {"default": {"description": "default", "validityPeriod": 7776000}}
  }
}
EOF
    cp "$HERE/acme_pebble_hook.py" "$WORKDIR/acme_pebble_hook.py"
    chmod 0755 "$WORKDIR" "$WORKDIR/acme_pebble_hook.py"
    chmod 0644 "$WORKDIR/pebble.minica.pem" "$WORKDIR/pebble-config.json"
}

cmd_up() {
    write_pebble_config
    docker network create --subnet "$SUBNET" --label "${PREFIX}=1" "$NET" >/dev/null
    docker run -d --name "${PREFIX}-challtestsrv" --label "${PREFIX}=1" \
        --memory 128m --cpus 0.5 --network "$NET" --ip "$CHALLTEST_IP" \
        --network-alias challtestsrv \
        "$CHALLTEST_IMAGE" -defaultIPv4 "$UCM_IP" -defaultIPv6 "" \
        -http01 "" -https01 "" -tlsalpn01 "" -doh "" >/dev/null
    docker run -d --name "${PREFIX}-ca" --label "${PREFIX}=1" \
        --memory 256m --cpus 1 --network "$NET" --ip "$PEBBLE_IP" \
        --network-alias pebble \
        -e PEBBLE_VA_NOSLEEP=1 -e PEBBLE_AUTHZREUSE="$PEBBLE_AUTHZREUSE" \
        -e PEBBLE_WFE_NONCEREJECT="$PEBBLE_WFE_NONCEREJECT" \
        -v "$WORKDIR/pebble-config.json:/bench/pebble-config.json:ro" \
        "$PEBBLE_IMAGE" -config /bench/pebble-config.json -dnsserver "${CHALLTEST_IP}:8053" >/dev/null
    docker run -d --name "${PREFIX}-ucm" --label "${PREFIX}=1" \
        --memory 1g --cpus 2 --network "$NET" --ip "$UCM_IP" \
        -e REQUESTS_CA_BUNDLE=/bench/pebble.minica.pem \
        -e CHALLTEST_URL="http://${CHALLTEST_IP}:8055" \
        -e UCM_FQDN="$UCM_IP" \
        -v "$WORKDIR:/bench:ro" \
        "$UCM_IMAGE" >/dev/null
    echo "waiting for UCM..."
    for _ in $(seq 1 90); do
        if docker exec "${PREFIX}-ucm" curl -sfk https://127.0.0.1:8443/api/v2/health >/dev/null 2>&1; then
            cmd_status
            return 0
        fi
        sleep 2
    done
    echo "UCM did not become healthy" >&2
    docker logs --tail 50 "${PREFIX}-ucm" >&2
    return 1
}

cmd_down() {
    docker ps -aq --filter "label=${PREFIX}=1" | xargs -r docker rm -fv >/dev/null
    docker network ls -q --filter "label=${PREFIX}=1" | xargs -r docker network rm >/dev/null
    rm -rf "$WORKDIR"
    echo "removed containers, volumes, network and $WORKDIR"
}

cmd_status() {
    docker ps -a --filter "label=${PREFIX}=1" --format '{{.Names}}\t{{.Status}}'
    echo "UCM https://${UCM_IP}:8443  Pebble https://${PEBBLE_IP}:14000/dir  mgmt https://${PEBBLE_IP}:15000  challtestsrv http://${CHALLTEST_IP}:8055"
}

case "${1:-}" in
    build) shift; cmd_build "$@" ;;
    up) cmd_up ;;
    down) cmd_down ;;
    status) cmd_status ;;
    *) sed -n '2,8p' "$0"; exit 2 ;;
esac
