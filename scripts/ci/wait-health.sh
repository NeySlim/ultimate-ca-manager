#!/usr/bin/env bash
# Waits until URL answers HTTP 200 with a healthy UCM body (status "ok", service "ucm",
# no safe_mode), retrying every second; fails after TIMEOUT seconds (default 90).
set -euo pipefail

url=${1:?usage: wait-health.sh URL [TIMEOUT_SECONDS]}
timeout=${2-90}
[[ "$timeout" =~ ^[0-9]+$ ]] || { echo "FAIL: TIMEOUT must be a number of seconds, got '$timeout'" >&2; exit 2; }

body=$(mktemp)
trap 'rm -f "$body"' EXIT
# Milliseconds, not $SECONDS: that one ticks with the clock's seconds and ends a wait up to 1 s early
now_ms() { local t=${EPOCHREALTIME/[.,]/}; printf '%s' "$((t / 1000))"; }
start=$(now_ms)
deadline=$((start + timeout * 1000))
code=000
while :; do
    code=$(curl -sk --max-time 5 -o "$body" -w '%{http_code}' "$url" 2>/dev/null) || code=000
    if [ "$code" = 200 ] && jq -e '.status == "ok" and .service == "ucm" and (.safe_mode // false) == false' \
            "$body" >/dev/null 2>&1; then
        echo "healthy after $((($(now_ms) - start) / 1000))s: $(head -c 300 "$body")"
        exit 0
    fi
    [ "$(now_ms)" -lt "$deadline" ] || break
    sleep 1
done
echo "FAIL: $url not healthy within ${timeout}s (last HTTP $code): $(head -c 300 "$body")" >&2
exit 1
