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

# 78 (EX_CONFIG): a SQLite database the runner refuses (older than 2.254, or written by a
# later release) stops the start before anything is written to the volume; any other
# answer leaves the decision to the application. The database a path from before 2.70 still
# holds is asked about too, before ucm_carry_old_data_paths copies it into the data.
ucm_refuse_unstartable_database() {
    local db out rc
    ucm_ha_active && return 0
    [ -n "${DATABASE_URL:-}" ] && return 0
    for db in "$UCM_DATABASE_PATH" "$(ucm_old_database)"; do
        [ -f "$db" ] || continue
        rc=0
        out=$(cd "${UCM_BASE_PATH:-/opt/ucm}/backend" && PYTHONDONTWRITEBYTECODE=1 DATABASE_URL= \
            DATABASE_PATH="$db" python3 migration_runner.py check 2>&1) || rc=$?
        case $rc in
            4|6) ;;
            *) continue ;;
        esac
        echo -e "${RED:-}❌ This release cannot start on $db:${NC:-}"
        printf '%s\n' "$out" | sed -n '2,4p' | sed 's/^/   /'
        echo "   Nothing was written to the volume. See UPGRADE.md, Upgrading to v3.0."
        return 78
    done
}

# The data directories of the images before 2.70, which some volumes are still mounted at
ucm_old_data_paths() {
    # shellcheck disable=SC2086  # a list of paths without spaces
    printf '%s\n' ${UCM_OLD_DATA_PATHS:-/opt/ucm/backend/data /app/backend/data}
}

# The database ucm_carry_old_data_paths would copy into the data, if any
ucm_old_database() {
    local old
    [ ! -e "${DATA_PATH:-/opt/ucm/data}/ucm.db" ] || return 0
    for old in $(ucm_old_data_paths); do
        [ ! -f "$old/ucm.db" ] || { printf '%s\n' "$old/ucm.db"; return 0; }
    done
}

# Copies into the data what a path from before 2.70 holds and the data lacks ('cas' is 'ca')
ucm_carry_old_data_paths() {
    local data=${DATA_PATH:-/opt/ucm/data} old item name sub
    for old in $(ucm_old_data_paths); do
        [ -d "$old" ] && [ -n "$(ls -A "$old" 2>/dev/null)" ] || continue
        echo -e "${YELLOW:-}   Checking for data migration from $old...${NC:-}"
        for item in "$old"/*; do
            [ -e "$item" ] || continue
            name=$(basename "$item")
            [ "$name" != cas ] || name=ca
            if [ ! -e "$data/$name" ]; then
                echo -e "${YELLOW:-}   Migrating $(basename "$item") → $name...${NC:-}"
                cp -a "$item" "$data/$name" 2>/dev/null || true
            elif [ -d "$item" ] && [ -d "$data/$name" ]; then
                for sub in "$item"/*; do
                    [ -e "$sub" ] || continue
                    if [ ! -e "$data/$name/$(basename "$sub")" ]; then
                        echo -e "${YELLOW:-}   Migrating $name/$(basename "$sub")...${NC:-}"
                        cp -a "$sub" "$data/$name/" 2>/dev/null || true
                    fi
                done
            fi
        done
        echo -e "${GREEN:-}✅ Data migration complete${NC:-}"
    done
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
            BACKUP_DIR="${DATA_PATH:-/opt/ucm/data}/backups"
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
