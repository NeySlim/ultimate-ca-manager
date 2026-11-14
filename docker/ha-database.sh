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
