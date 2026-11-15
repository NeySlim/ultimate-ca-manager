#!/usr/bin/env bash
# Waits until URL answers HTTP 200 with a healthy UCM body (status "ok", service "ucm",
# no safe_mode), retrying every second; fails after TIMEOUT seconds (default 90).
set -euo pipefail

url=${1:?usage: wait-health.sh URL [TIMEOUT_SECONDS]}
timeout=${2-90}
[[ "$timeout" =~ ^[0-9]+$ ]] || { echo "FAIL: TIMEOUT must be a number of seconds, got '$timeout'" >&2; exit 2; }

body=$(mktemp)
trap 'rm -f "$body"' EXIT
start=$SECONDS
deadline=$((SECONDS + timeout))
code=000
while :; do
    code=$(curl -sk --max-time 5 -o "$body" -w '%{http_code}' "$url" 2>/dev/null) || code=000
    if [ "$code" = 200 ] && jq -e '.status == "ok" and .service == "ucm" and (.safe_mode // false) == false' \
            "$body" >/dev/null 2>&1; then
        echo "healthy after $((SECONDS - start))s: $(head -c 300 "$body")"
        exit 0
    fi
    [ "$SECONDS" -lt "$deadline" ] || break
    sleep 1
done
echo "FAIL: $url not healthy within ${timeout}s (last HTTP $code): $(head -c 300 "$body")" >&2
exit 1
