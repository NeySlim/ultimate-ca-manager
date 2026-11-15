#!/bin/bash
# UCM_HA database handling: a node never owns a SQLite file, the database is PostgreSQL.
# Functions only: the image entrypoint sources this file, and the tests source it too.

ucm_ha_active() {
    local ha
    ha=$(printf '%s' "${UCM_HA:-}" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
    case "$ha" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
}

# Line for the generated .env: no SQLite path in HA mode.
ucm_env_database_line() {
    ucm_ha_active && return 0
    echo "DATABASE_PATH=${UCM_DATABASE_PATH}"
}

# Value shown in the configuration summary.
ucm_database_label() {
    if ucm_ha_active; then
        echo "PostgreSQL (DATABASE_URL)"
    else
        echo "${UCM_DATABASE_PATH}"
    fi
}

# Where the first password comes from; never the value itself.
ucm_initial_admin_notice() {
    local source=""
    [ -n "${UCM_INITIAL_ADMIN_PASSWORD:-}" ] && source=INITIAL_ADMIN_PASSWORD
    [ -n "${UCM_INITIAL_ADMIN_PASSWORD_FILE:-}" ] && source=INITIAL_ADMIN_PASSWORD_FILE
    echo "   • Username: ${UCM_INITIAL_ADMIN_USERNAME:-admin}"
    if [ -n "${UCM_INITIAL_ADMIN_PASSWORD:-}" ] && [ -n "${UCM_INITIAL_ADMIN_PASSWORD_FILE:-}" ]; then
        # The application refuses to start then: which one was meant cannot be guessed
        echo "   • Password: INITIAL_ADMIN_PASSWORD and INITIAL_ADMIN_PASSWORD_FILE are both set:"
        echo "     the start will be refused, keep only one"
    elif [ -n "$source" ]; then
        echo "   • Password: the one you provided (${source})"
    else
        echo "   • Password: generated at first start, read it with:"
        echo "       docker exec <container> cat /opt/ucm/data/initial-admin-password"
        echo "     It must be changed at first login, which removes the file."
    fi
}

# The database itself says whether this start upgrades it: a migration of the image missing from
# its registry, or the serial step left to run again. Read-only; any doubt counts as an upgrade.
ucm_sqlite_upgrade_possible() {
    python3 -I - "$UCM_DATABASE_PATH" "${UCM_MIGRATIONS_DIR:-/opt/ucm/backend/migrations}" <<'PY' 2>/dev/null && return 1
import pathlib, sqlite3, sys
names = {p.stem for p in pathlib.Path(sys.argv[2]).glob("*.py") if not p.name.startswith("_")}
db = sqlite3.connect(pathlib.Path(sys.argv[1]).resolve().as_uri() + "?mode=ro", uri=True)
applied = {row[0] for row in db.execute("SELECT name FROM _migrations")}
tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
pending = "system_config" in tables and db.execute(
    "SELECT 1 FROM system_config WHERE key = 'serial_unique_index_pending'").fetchone()
sys.exit(0 if names and names <= applied and not pending else 1)
PY
    return 0
}

# Room for the start next to the database: its copy when enabled, plus its size again when an
# upgrade may run, for its journal and growth (measured: 1.7 times the database with the copy).
# Fails with what is needed and available; a df that cannot answer lets the start go on.
ucm_sqlite_disk_room() {
    local dir bytes size_kb need_kb=0 avail_kb upgrade=false
    dir=$(dirname "$UCM_DATABASE_PATH")
    bytes=$(stat -c %s "$UCM_DATABASE_PATH" 2>/dev/null || wc -c < "$UCM_DATABASE_PATH")
    size_kb=$(( (bytes + 1023) / 1024 ))
    ucm_sqlite_upgrade_possible && upgrade=true && need_kb=$size_kb
    [ "$UCM_BACKUP_ENABLED" = "true" ] && need_kb=$(( need_kb + size_kb ))
    [ "$need_kb" -eq 0 ] && return 0
    avail_kb=$(df -Pk "$dir" 2>/dev/null | awk 'NR == 2 { print $4 }') || avail_kb=""
    case "$avail_kb" in ''|*[!0-9]*) return 0 ;; esac
    [ "$avail_kb" -ge "$need_kb" ] && return 0
    echo -e "${RED:-}❌ Not enough disk space in $dir: the start needs $(( need_kb / 1024 )) MB free, $(( avail_kb / 1024 )) MB available.${NC:-}"
    if [ "$upgrade" = "true" ]; then
        echo "   The database is $(( size_kb / 1024 )) MB; upgrading it needs its size for the upgrade's journal and growth,"
        echo "   and its size again for the pre-start copy unless UCM_BACKUP_ENABLED=false. Free space, then start again."
    else
        echo "   The database is $(( size_kb / 1024 )) MB; the pre-start copy needs its size (UCM_BACKUP_ENABLED=false skips it)."
        echo "   Free space, then start again."
    fi
    return 1
}

# First-run notice and pre-start copy of the SQLite file; both skipped in HA mode.
ucm_sqlite_check_and_backup() {
    if ucm_ha_active; then
        echo -e "${GREEN:-}✅ HA mode: database is PostgreSQL, no SQLite backup${NC:-}"
        return 0
    fi
    if [ ! -f "$UCM_DATABASE_PATH" ]; then
        echo -e "${YELLOW:-}   First run detected - database will be auto-created${NC:-}"
        ucm_initial_admin_notice
    else
        echo -e "${GREEN:-}✅ Database exists${NC:-}"
        ucm_sqlite_disk_room || return 1

        # Database backup if enabled
        if [ "$UCM_BACKUP_ENABLED" = "true" ]; then
            BACKUP_DIR="/opt/ucm/data/backups"
            BACKUP_FILE="$BACKUP_DIR/ucm-backup-$(date +%Y%m%d-%H%M%S).db"

            # Create backup
            cp "$UCM_DATABASE_PATH" "$BACKUP_FILE"
            echo -e "${GREEN:-}✅ Database backup created${NC:-}"

            # Clean old backups
            find "$BACKUP_DIR" -name "ucm-backup-*.db" -mtime "+$UCM_BACKUP_RETENTION_DAYS" -delete 2>/dev/null || true
        fi
    fi
}

# Export the SQLite path for the application, except in HA mode.
ucm_export_database_path() {
    ucm_ha_active && return 0
    export DATABASE_PATH="${UCM_DATABASE_PATH}"
}

# Default SoftHSM token: returns 0 only when HA is off and HSM_AUTO_INIT (default true) is true.
# In HA mode no token is created (a token stays on one node's disk).
ucm_softhsm_auto_init() {
    ucm_ha_active && return 1
    [ "${HSM_AUTO_INIT:-true}" = "true" ]
}
