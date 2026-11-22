#!/bin/bash
# UCM_HA database handling: a node never owns a SQLite file, the database is PostgreSQL.
# Functions only: the image entrypoint sources this file, and the tests source it too.

# A flag as the application reads it: surrounding ASCII blanks dropped (C locale), lower case.
ucm_flag_text() {
    local LC_ALL=C v="${1:-}"
    v="${v#"${v%%[![:space:]]*}"}"
    v="${v%"${v##*[![:space:]]}"}"
    printf '%s' "$v" | tr '[:upper:]' '[:lower:]'
}

ucm_ha_active() {
    case "$(ucm_flag_text "${UCM_HA:-}")" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
}

ucm_flag_set() {
    case "$(ucm_flag_text "${1:-}")" in
        1|true|yes) return 0 ;;
        *) return 1 ;;
    esac
}

# Line for the generated .env: no SQLite path in HA mode.
ucm_env_database_line() {
    ucm_ha_active && return 0
    echo "DATABASE_PATH=${UCM_DATABASE_PATH}"
}

# Value shown in the configuration summary: the engine and the database name, never the
# address or the password of DATABASE_URL.
ucm_database_label() {
    local url="${DATABASE_URL:-}" name
    if [ -z "$url" ]; then
        if ucm_ha_active; then
            echo "PostgreSQL (DATABASE_URL)"
        else
            echo "SQLite, ${UCM_DATABASE_PATH}"
        fi
        return 0
    fi
    case "$url" in
        postgres://*|postgresql://*|postgresql+*://*)
            name="${url%%\?*}"
            name="${name#*://}"
            case "$name" in */*) name="${name##*/}" ;; *) name="" ;; esac
            if [ -n "$name" ]; then echo "PostgreSQL, database ${name}"; else echo "PostgreSQL (DATABASE_URL)"; fi ;;
        *) echo "DATABASE_URL" ;;
    esac
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
    elif [ -n "$source" ] && ucm_flag_set "${INITIAL_ADMIN_PASSWORD_FORCE_CHANGE:-}"; then
        # The Helm chart sets the flag for the value it draws into its Secret
        echo "   • Password: drawn by the deployment (${source}), not chosen by anyone;"
        echo "     with the Helm chart it is in the release's Secret, key UCM_INITIAL_ADMIN_PASSWORD."
        echo "     It must be changed at first login."
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

# 78: a database 2.254 started last stops the image of the new major before anything is written,
# until UCM_ACCEPT_MAJOR_UPGRADE names that major (migration_runner.py major_upgrade_refusal).
# Every node asks, PostgreSQL and HA included; an unreachable database is left to the application.
ucm_refuse_unaccepted_major_upgrade() {
    local db out rc dbs=()
    if [ -n "${DATABASE_URL:-}" ] || ucm_ha_active; then
        dbs=(DATABASE_URL)
    else
        for db in "$UCM_DATABASE_PATH" "$(ucm_old_database)"; do
            [ -f "$db" ] && dbs+=("$db")
        done
    fi
    for db in "${dbs[@]}"; do
        rc=0
        if [ "$db" = DATABASE_URL ]; then
            out=$(cd "${UCM_BASE_PATH:-/opt/ucm}/backend" && PYTHONDONTWRITEBYTECODE=1 UCM_DOCKER=1 \
                python3 migration_runner.py check --major-upgrade 2>&1) || rc=$?
        else
            out=$(cd "${UCM_BASE_PATH:-/opt/ucm}/backend" && PYTHONDONTWRITEBYTECODE=1 UCM_DOCKER=1 \
                DATABASE_URL= DATABASE_PATH="$db" python3 migration_runner.py check --major-upgrade 2>&1) || rc=$?
        fi
        [ "$rc" -eq 7 ] || continue
        echo -e "${RED:-}❌ This image will not upgrade the database without your consent:${NC:-}"
        # The file is named (it may sit at a path from before 2.70); a URL never is
        [ "$db" = DATABASE_URL ] || echo "   Database: $db"
        printf '%s\n' "$out" | sed '1d' | sed 's/^/   /'
        return 78
    done
}

# The data directories of the images before 2.70, which some volumes are still mounted at
ucm_old_data_paths() {
    # shellcheck disable=SC2086  # a list of paths without spaces
    printf '%s\n' ${UCM_OLD_DATA_PATHS:-/opt/ucm/backend/data /app/backend/data}
}

# The database ucm_carry_old_data_paths would copy into the data, if any, and only when the
# application opens it there: with UCM_DATABASE_PATH elsewhere, that copy is never read
ucm_old_database() {
    local old data=${DATA_PATH:-/opt/ucm/data}
    [ "$(realpath -m -- "${UCM_DATABASE_PATH:-$data/ucm.db}")" = "$(realpath -m -- "$data/ucm.db")" ] \
        || return 0
    [ ! -e "$data/ucm.db" ] || return 0
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
            # A database's -wal and -journal go with it, never beside another database
            case $name in ucm.db-wal|ucm.db-shm|ucm.db-journal) continue ;; esac
            if [ ! -e "$data/$name" ]; then
                echo -e "${YELLOW:-}   Migrating $(basename "$item") → $name...${NC:-}"
                if [ "$name" = ucm.db ]; then
                    rm -f "$data/ucm.db-wal" "$data/ucm.db-shm" "$data/ucm.db-journal"
                    for sub in -wal -journal; do
                        [ ! -e "$item$sub" ] || cp -a "$item$sub" "$data/$name$sub" 2>/dev/null || true
                    done
                fi
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

# The database itself says whether this start upgrades it: a migration of the image missing from
# its registry, or the serial step left to run again. Read-only; any doubt counts as an upgrade.
# A database whose -wal or -journal holds data is not opened (reading it would write); a WAL one
# is read with immutable=1, since a read-only open would create its -wal and -shm files.
ucm_sqlite_upgrade_possible() {
    python3 -I - "$UCM_DATABASE_PATH" "${UCM_MIGRATIONS_DIR:-/opt/ucm/backend/migrations}" <<'PY' 2>/dev/null && return 1
import pathlib, sqlite3, sys
path = pathlib.Path(sys.argv[1]).resolve()
with open(path, "rb") as f:
    head = f.read(20)
if head[:16] != b"SQLite format 3\0" or head[18:20] not in (b"\1\1", b"\2\2"):
    sys.exit(1)
for suffix in ("-wal", "-journal"):
    log = path.with_name(path.name + suffix)
    if log.exists() and log.stat().st_size:
        sys.exit(1)
names = {p.stem for p in pathlib.Path(sys.argv[2]).glob("*.py") if not p.name.startswith("_")}
db = sqlite3.connect(path.as_uri() + ("?immutable=1" if head[18:20] == b"\2\2" else "?mode=ro"), uri=True)
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

# True when both directories share a filesystem (arguments: directory, directory, df line, df line):
# one device id, or one /dev source (btrfs subvolumes); an unreadable id counts as shared, the
# cautious reading. Other df names (tmpfs) are not identities.
_ucm_same_fs() {
    local a b
    a=$(_ucm_dev "$1")
    b=$(_ucm_dev "$2")
    [ -z "$a" ] || [ -z "$b" ] || [ "$a" = "$b" ] || { [ "${3%% *}" = "${4%% *}" ] && [[ "$3" == /dev/* ]]; }
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
    local db_dir bytes size_kb size_mb db_need=0 copy_need=0 db_df="" copy_df="" short=false shared_dir
    db_dir=$(dirname "$UCM_DATABASE_PATH")
    bytes=$(stat -c %s "$UCM_DATABASE_PATH" 2>/dev/null || wc -c < "$UCM_DATABASE_PATH")
    # The writes still in the WAL are part of the database, and of its copy
    bytes=$(( bytes + $(stat -c %s "$UCM_DATABASE_PATH-wal" 2>/dev/null || echo 0) ))
    size_kb=$(( (bytes + 1023) / 1024 ))
    size_mb=$(( (size_kb + 1023) / 1024 ))
    ucm_sqlite_upgrade_possible && db_need=$size_kb
    [ "$UCM_BACKUP_ENABLED" = "true" ] && copy_need=$size_kb
    [ "$db_need" -gt 0 ] && db_df=$(_ucm_df "$db_dir")
    [ "$copy_need" -gt 0 ] && copy_df=$(_ucm_df "$UCM_SQLITE_BACKUP_DIR")
    if [ -n "$db_df" ] && [ -n "$copy_df" ] && _ucm_same_fs "$db_dir" "$UCM_SQLITE_BACKUP_DIR" "$db_df" "$copy_df"; then
        # one filesystem: the smaller of the two readings is the room
        shared_dir=$db_dir
        [ "${copy_df##* }" -lt "${db_df##* }" ] && db_df=$copy_df && shared_dir=$UCM_SQLITE_BACKUP_DIR
        if _ucm_room_short "$shared_dir" $(( db_need + copy_need )) "$db_df"; then
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

# True only for a PostgreSQL DATABASE_URL (the forms of utils/db_url.is_postgres_url). Any other
# value may still name the SQLite file, and its spelling is not parsed here: the file is checked.
_ucm_database_url_elsewhere() {
    case "${DATABASE_URL:-}" in
        postgresql://*|postgres://*|postgresql+*) return 0 ;;
        *) return 1 ;;
    esac
}

# First-run notice and pre-start copy of the SQLite file; both skipped in HA mode. With a PostgreSQL
# DATABASE_URL the SQLite file is neither checked nor copied.
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

            # Create backup: writes still in the WAL are copied with the file, then folded into it
            cp "$UCM_DATABASE_PATH" "$BACKUP_FILE"
            if [ -s "$UCM_DATABASE_PATH-wal" ]; then
                cp "$UCM_DATABASE_PATH-wal" "$BACKUP_FILE-wal"
                python3 -I -c 'import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.execute("PRAGMA journal_mode=DELETE")
c.close()' "$BACKUP_FILE" 2>/dev/null \
                    || echo -e "${YELLOW:-}   The backup keeps its -wal file beside it: copy both together${NC:-}"
            fi
            echo -e "${GREEN:-}✅ Database backup created${NC:-}"

            # Clean old backups
            find "$BACKUP_DIR" \( -name "ucm-backup-*.db" -o -name "ucm-backup-*.db-wal" \) \
                -mtime "+$UCM_BACKUP_RETENTION_DAYS" -delete 2>/dev/null || true
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
