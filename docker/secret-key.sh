#!/bin/bash
# UCM_SECRET_KEY without a value: the key generated at the first start, kept in the configuration
# volume, so sessions and what is signed with the key survive a restart (#457).
# Functions only: entrypoint.sh sources this file, and the tests source it too.

# ucm_secret_key [dir]: sets UCM_SECRET_KEY; an explicit value wins and nothing is read or written
ucm_secret_key() {
    local dir="${1:-/etc/ucm}" file key tmp
    [ -n "${UCM_SECRET_KEY:-}" ] && return 0
    file="$dir/secret.key"
    if [ -f "$file" ]; then
        if ! key=$(head -n 1 "$file" 2>/dev/null | tr -d '[:space:]'); then key=; fi
        if [ -z "$key" ] && [ ! -r "$file" ]; then
            echo -e "${RED:-}❌ $file is not readable by UID $(id -u): the session key cannot be kept${NC:-}"
            return 1
        fi
        if [ -n "$key" ]; then
            UCM_SECRET_KEY=$key
            return 0
        fi
    fi
    key=$(od -An -tx1 -N32 /dev/urandom 2>/dev/null | tr -d ' \n')
    if [ ${#key} -ne 64 ]; then
        echo -e "${RED:-}❌ No session key could be read from /dev/urandom: set UCM_SECRET_KEY (64 hex characters," \
            "openssl rand -hex 32) or start the container with /dev/urandom available${NC:-}"
        return 1
    fi
    UCM_SECRET_KEY=$key
    # A new file (mktemp: O_EXCL, mode 600) renamed over the name: a link there is replaced, never followed
    if tmp=$(mktemp "$dir/.secret.key.XXXXXX" 2>/dev/null); then
        if printf '%s\n' "$key" > "$tmp" && chmod 600 "$tmp" \
            && { [ "$(id -u)" != 0 ] || chown 1000:1000 "$tmp"; } && mv -f -T "$tmp" "$file"; then
            echo -e "${GREEN:-}🔑 Session key generated and kept in $file${NC:-}"
            return 0
        fi
        rm -f "$tmp"
    fi
    echo -e "${YELLOW:-}⚠️  $dir is not writable: the session key generated for this start is lost at the next one;" \
        "mount a volume on $dir or set UCM_SECRET_KEY${NC:-}"
    return 0
}
