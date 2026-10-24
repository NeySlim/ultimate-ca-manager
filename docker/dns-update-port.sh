#!/bin/bash
# Port check of the DNS UPDATE (RFC 2136) listener. Functions only: entrypoint.sh
# sources this file, and the tests source it too.

# Ports below 1024 need CAP_NET_BIND_SERVICE, which the image does not have.
validate_unprivileged_port() {
    local port=$1
    if [[ "$port" =~ ^[0-9]+$ ]] && [ "$port" -ge 1024 ] && [ "$port" -le 65535 ]; then
        return 0
    else
        return 1
    fi
}

# Validate UCM_DNS_UPDATE_PORT. Unset, blank or 0 = listener off.
# Returns 0 when the value is valid or off, 1 after an error message.
check_dns_update_port() {
    # The application strips the value and reads a blank value as unset: do the same here.
    local value="${UCM_DNS_UPDATE_PORT:-}"
    local https_port="${UCM_HTTPS_PORT:-8443}"
    local http_port="${UCM_HTTP_PORT:-8080}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    # An all-digit value of 0 (for example 00) is off. Compare in base 10 (no octal).
    if [[ "$value" =~ ^[0-9]+$ ]] && [ "$((10#$value))" -eq 0 ] 2>/dev/null; then
        value=""
    fi
    if [ -n "$value" ]; then
        if ! validate_unprivileged_port "$value"; then
            echo -e "${RED:-}❌ Invalid DNS UPDATE port: $value${NC:-}"
            echo "   UCM_DNS_UPDATE_PORT must be 0 (off) or an integer from 1024 to 65535."
            echo "   The container runs as an unprivileged user and cannot bind port 53."
            echo "   To serve port 53, keep the default 8053 and map it: -p 53:8053/udp -p 53:8053/tcp"
            return 1
        fi
        if [ "$((10#$value))" -eq "$((10#$https_port))" ] || [ "$((10#$value))" -eq "$((10#$http_port))" ]; then
            echo -e "${RED:-}❌ DNS UPDATE port $value is the same as the HTTPS or HTTP port${NC:-}"
            return 1
        fi
    fi
    return 0
}
