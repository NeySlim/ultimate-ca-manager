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
# A WAL database is not opened: a read-only open would create its -wal and -shm files.
ucm_sqlite_upgrade_possible() {
    python3 -I - "$UCM_DATABASE_PATH" "${UCM_MIGRATIONS_DIR:-/opt/ucm/backend/migrations}" <<'PY' 2>/dev/null && return 1
import pathlib, sqlite3, sys
path = pathlib.Path(sys.argv[1]).resolve()
with open(path, "rb") as f:
    head = f.read(20)
if head[:16] != b"SQLite format 3\0" or head[18:20] != b"\1\1":
    sys.exit(1)
names = {p.stem for p in pathlib.Path(sys.argv[2]).glob("*.py") if not p.name.startswith("_")}
db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
applied = {row[0] for row in db.execute("SELECT name FROM _migrations")}
tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
pending = "system_config" in tables and db.execute(
    "SELECT 1 FROM system_config WHERE key = 'serial_unique_index_pending'").fetchone()
sys.exit(0 if names and names <= applied and not pending else 1)
PY
    return 0
}

# Where the image puts its pre-start copy of the database.
UCM_SQLITE_BACKUP_DIR=/opt/ucm/data/backups

# "<filesystem> <KB available>" for a directory, nothing when df cannot answer.
_ucm_df() {
    df -Pk "$1" 2>/dev/null | awk 'NR == 2 && $4 ~ /^[0-9]+$/ { print $1, $4 }'
}

# Device id of the filesystem holding a directory (its nearest existing parent), nothing when unknown.
_ucm_dev() {
    local d=$1 dev
    until dev=$(stat -c %d "$d" 2>/dev/null) && [ -n "$dev" ]; do
        [ "$d" = "/" ] || [ "$d" = "." ] && return 0
        d=$(dirname "$d")
    done
    echo "$dev"
}

# True when both directories share a filesystem; an unreadable device id counts as shared, the
# cautious reading (the needs add up against the smaller room). df names are not identities.
_ucm_same_fs() {
    local a b
    a=$(_ucm_dev "$1")
    b=$(_ucm_dev "$2")
    [ -z "$a" ] || [ -z "$b" ] || [ "$a" = "$b" ]
}

# Prints the refusal and fails when `df` line $3 has less than $2 KB for directory $1.
_ucm_room_short() {
    local avail_kb=${3##* }
    [ -z "$3" ] || [ "$avail_kb" -ge "$2" ] && return 1
    # needed rounded up, available down: the message never shows a need it satisfies
    echo -e "${RED:-}❌ Not enough disk space in $1: the start needs $(( ($2 + 1023) / 1024 )) MB free, $(( avail_kb / 1024 )) MB available.${NC:-}"
}

# Room for the start: the copy on the backups' filesystem when enabled, the database's size
# again on its own filesystem when an upgrade may run (journal and growth), summed when both
# are one filesystem. Fails with what is needed and available; a df that cannot answer passes.
ucm_sqlite_disk_room() {
    local db_dir bytes size_kb size_mb db_need=0 copy_need=0 db_df="" copy_df="" short=false
    db_dir=$(dirname "$UCM_DATABASE_PATH")
    bytes=$(stat -c %s "$UCM_DATABASE_PATH" 2>/dev/null || wc -c < "$UCM_DATABASE_PATH")
    size_kb=$(( (bytes + 1023) / 1024 ))
    size_mb=$(( (size_kb + 1023) / 1024 ))
    ucm_sqlite_upgrade_possible && db_need=$size_kb
    [ "$UCM_BACKUP_ENABLED" = "true" ] && copy_need=$size_kb
    [ "$db_need" -gt 0 ] && db_df=$(_ucm_df "$db_dir")
    [ "$copy_need" -gt 0 ] && copy_df=$(_ucm_df "$UCM_SQLITE_BACKUP_DIR")
    if [ -n "$db_df" ] && [ -n "$copy_df" ] && _ucm_same_fs "$db_dir" "$UCM_SQLITE_BACKUP_DIR"; then
        # one filesystem: the smaller of the two readings is the room
        [ "${copy_df##* }" -lt "${db_df##* }" ] && db_df=$copy_df
        if _ucm_room_short "$db_dir" $(( db_need + copy_need )) "$db_df"; then
            echo "   The database is $size_mb MB; upgrading it needs its size for the upgrade's journal and growth,"
            echo "   and its size again for the pre-start copy unless UCM_BACKUP_ENABLED=false. Free space, then start again."
            return 1
        fi
        return 0
    fi
    if _ucm_room_short "$db_dir" "$db_need" "$db_df"; then
        echo "   The database is $size_mb MB; upgrading it needs its size beside it for the upgrade's journal and growth."
        short=true
    fi
    if _ucm_room_short "$UCM_SQLITE_BACKUP_DIR" "$copy_need" "$copy_df"; then
        echo "   The database is $size_mb MB; the pre-start copy needs its size (UCM_BACKUP_ENABLED=false skips it)."
        short=true
    fi
    [ "$short" = "true" ] && echo "   Free space, then start again." && return 1
    return 0
}

# True when DATABASE_URL points the application away from the SQLite file at UCM_DATABASE_PATH:
# any PostgreSQL URL (utils/db_url.is_postgres_url), another scheme, or another SQLite file.
# An sqlite:/// URL on that same file leaves it in use.
_ucm_database_url_elsewhere() {
    local url=${DATABASE_URL:-} path
    [ -z "$url" ] && return 1
    case "$url" in
        sqlite:///*)
            path=${url#sqlite:///}
            path=${path%%\?*}
            [ "$path" -ef "$UCM_DATABASE_PATH" ] && return 1
            [ "/$path" -ef "$UCM_DATABASE_PATH" ] && return 1
            return 0 ;;
        *) return 0 ;;
    esac
}

# First-run notice and pre-start copy of the SQLite file; both skipped in HA mode. A SQLite file
# the application does not open (DATABASE_URL elsewhere) is neither checked nor copied.
ucm_sqlite_check_and_backup() {
    if ucm_ha_active; then
        echo -e "${GREEN:-}✅ HA mode: database is PostgreSQL, no SQLite backup${NC:-}"
        return 0
    fi
    if [ ! -f "$UCM_DATABASE_PATH" ]; then
        echo -e "${YELLOW:-}   First run detected - database will be auto-created${NC:-}"
        ucm_initial_admin_notice
    elif _ucm_database_url_elsewhere; then
        echo -e "${GREEN:-}✅ Database from DATABASE_URL: the SQLite file is not used, no SQLite backup${NC:-}"
    else
        echo -e "${GREEN:-}✅ Database exists${NC:-}"
        ucm_sqlite_disk_room || return 1

        # Database backup if enabled
        if [ "$UCM_BACKUP_ENABLED" = "true" ]; then
            BACKUP_DIR="$UCM_SQLITE_BACKUP_DIR"
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
