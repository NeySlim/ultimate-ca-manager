#!/bin/bash
# UCM_HA check: every node must receive the same UCM_SECRET_KEY, never a generated one.
# Functions only: entrypoint.sh sources this file, and the tests source it too.

check_ha_secret() {
    # Read as the application reads it: surrounding ASCII blanks dropped (C locale), lower case
    local LC_ALL=C ha="${UCM_HA:-}"
    ha="${ha#"${ha%%[![:space:]]*}"}"
    ha="${ha%"${ha##*[![:space:]]}"}"
    case "$(printf '%s' "$ha" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) ;;
        *) return 0 ;;
    esac
    if [ -z "${UCM_SECRET_KEY:-}" ]; then
        echo -e "${RED:-}❌ UCM_HA=1 requires UCM_SECRET_KEY set, identical on every node${NC:-}"
        return 1
    fi
}
