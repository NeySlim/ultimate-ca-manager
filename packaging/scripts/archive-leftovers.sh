#!/bin/sh
# Run by the DEB postinst and the RPM %post on a new install, before the configuration
# is written: when an earlier UCM was removed and left a SQLite database this release
# refuses (migration_runner.py check), everything it left is moved, intact, to a root-only
# archive, so the install goes on as on a new machine. Nothing is ever deleted: a failed
# step puts back what was moved, and the service is then not started.
#
# Usage: archive-leftovers.sh <ucm home> <data dir> <config dir> [<archive parent> [<log>]]
# Exit 0: nothing to archive, or archived; 1: not archived, everything is back in place.
set -u

UCM_HOME=$1
DATA=$2
CONFIG=$3
# Beside the home (/opt/ucm-archive): outside every path the service may write or back up
PARENT=${4:-${UCM_HOME%/*}/ucm-archive}
LOG=${5:-/var/log/ucm/leftover-archive.log}
# The data directories the packages own or create: kept in place, their contents archived
KEEP_DIRS="ca certs private crl scep backups sessions"
TAB=$(printf '\t')
DEST="" JOURNAL="" MADE_PARENT=""

log_line() {
    { mkdir -p "${LOG%/*}" && printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; } \
        2>/dev/null || true
}
say() { printf '%s\n' "$*"; log_line "$*"; }

# Last value of $2 in env file $1, unquoted; the file is read, never sourced
env_value() {
    [ -f "$1" ] || return 0
    sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$2[[:space:]]*=[[:space:]]*//p" "$1" \
        | tail -n 1 | sed -E 's/[[:space:]]+$//; s/^"(.*)"$/\1/; s/^'"'"'(.*)'"'"'$/\1/'
}

device() { stat -c %d -- "$1"; }

# A comparable digest of a file, a symbolic link or a whole tree (names, types, contents)
digest() {
    if [ -L "$1" ]; then
        printf 'link %s\n' "$(readlink -- "$1")"
    elif [ -d "$1" ]; then
        (cd -- "$1" && find . \( -type f -exec cksum {} + \) -o \( -type l -exec sh -c \
            'for l; do printf "link %s %s\n" "$l" "$(readlink -- "$l")"; done' sh {} + \) \
            -o -print) | LC_ALL=C sort
    else
        cksum < "$1"
    fi
}

# Moves $1 to $2 (absent): a rename on one filesystem, else a verified copy whose source
# is removed only once every item is in the archive (remove_copied)
move_item() {
    if [ -e "$2" ] || [ -L "$2" ]; then return 1; fi
    if [ "$(device "$1")" = "$(device "${2%/*}")" ]; then
        printf 'rename\t%s\t%s\n' "$1" "$2" >> "$JOURNAL" || return 1
        mv -- "$1" "$2" || return 1
    else
        printf 'copy\t%s\t%s\n' "$1" "$2" >> "$JOURNAL" || return 1
        cp -a -- "$1" "$2" || return 1
        [ "$(digest "$1")" = "$(digest "$2")" ] || return 1
    fi
}

is_kept() {
    [ "$1" = "$DATA" ] || return 1
    case " $KEEP_DIRS " in *" $2 "*) return 0 ;; esac
    return 1
}

# Archives the contents of directory $1, which stays, into $2 (created here). A kept
# directory or a mount point is never moved itself: its contents are, the same way.
archive_contents() {
    printf 'mkdir\t%s\t%s\n' "$1" "$2" >> "$JOURNAL" || return 1
    mkdir -- "$2" || return 1
    for entry in "$1"/* "$1"/.[!.]* "$1"/..?*; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        if [ -d "$entry" ] && [ ! -L "$entry" ] && { is_kept "$1" "${entry##*/}" \
                || [ "$(device "$entry")" != "$(device "$1")" ]; }; then
            archive_contents "$entry" "$2/${entry##*/}" || return 1
        else
            move_item "$entry" "$2/${entry##*/}" || return 1
        fi
    done
}

# Second phase of a cross-filesystem move: every copy is verified, the sources go
remove_copied() {
    grep "^copy$TAB" "$JOURNAL" > "$JOURNAL.copies" || { rm -f -- "$JOURNAL.copies"; return 0; }
    while IFS="$TAB" read -r _op src dst; do
        printf 'remove\t%s\t%s\n' "$src" "$dst" >> "$JOURNAL" || return 1
        rm -rf -- "$src" || return 1
    done < "$JOURNAL.copies"
    rm -f -- "$JOURNAL.copies"
}

# Undoes the journal, last step first. Never deletes an original: a copy goes only once
# its source is complete again, and whatever cannot be put back is named.
roll_back() {
    stuck=""
    sed -n '1!G;h;$p' "$JOURNAL" > "$JOURNAL.undo" 2>/dev/null || cp -- "$JOURNAL" "$JOURNAL.undo"
    while IFS="$TAB" read -r op src dst; do
        case $op in
            rename)
                if { [ -e "$dst" ] || [ -L "$dst" ]; } && [ ! -e "$src" ] && [ ! -L "$src" ]; then
                    mv -- "$dst" "$src" || stuck="$stuck $dst"
                fi ;;
            remove)
                # The source was being removed: complete it again from its verified copy
                if [ -d "$dst" ] && [ ! -L "$dst" ]; then
                    mkdir -p -- "$src" && cp -a -- "$dst/." "$src/"
                else
                    { [ -e "$src" ] || [ -L "$src" ] || cp -a -- "$dst" "$src"; }
                fi
                if [ "$(digest "$src" 2>/dev/null)" = "$(digest "$dst")" ]; then
                    rm -rf -- "$dst"
                else
                    stuck="$stuck $dst"
                fi
                ;;
            copy)
                # A copy whose source removal started was dealt with on its remove line
                if ! grep -qxF "remove$TAB$src$TAB$dst" "$JOURNAL.undo" \
                        && { [ -e "$dst" ] || [ -L "$dst" ]; }; then
                    rm -rf -- "$dst" || stuck="$stuck $dst"
                fi ;;
            mkdir)
                [ ! -d "$dst" ] || rmdir -- "$dst" 2>/dev/null || stuck="$stuck $dst" ;;
        esac
    done < "$JOURNAL.undo"
    rm -f -- "$JOURNAL.undo" "$JOURNAL.copies" "$DEST/README.txt"
    if [ -z "$stuck" ]; then
        rm -f -- "$JOURNAL"
        rmdir -- "$DEST" 2>/dev/null || stuck="$DEST"
        [ -z "$MADE_PARENT" ] || rmdir -- "$PARENT" 2>/dev/null || true
    fi
    [ -z "$stuck" ]
}

write_readme() {
    cat > "$DEST/README.txt" <<EOF
UCM: what an earlier installation left on this machine

Archived on $STAMP (UTC) by the UCM $(cat "$UCM_HOME/VERSION" 2>/dev/null || echo 3.0) package,
installed while no UCM package was installed and an earlier one had left its files.
This release cannot start on the database that installation left:
  $REASON
So the package moved that installation's files here, unchanged, and set up a new,
empty UCM in their place.

Contents
  data/       what was in $DATA (database, CA files, private keys, backups, sessions)
  config/     what was in $CONFIG (ucm.env, master.key, HTTPS key and certificate)
$DB_LINE
This directory holds private keys and the key that decrypts the database: keep it
readable by root only. Nothing here is used or removed by UCM.

To put that installation back in service
  1. Stop UCM: sudo systemctl stop ucm
  2. Install UCM 2.254 in place of this release (Debian, Ubuntu:
     sudo apt install --allow-downgrades ./ucm_2.254_all.deb; RHEL, Fedora:
     sudo dnf downgrade ./ucm-2.254-1.<dist>.noarch.rpm), then stop it again.
  3. Move the new files aside, then put these back: the contents of data/ into
     $DATA, of config/ into $CONFIG$DB_RESTORE, then
     sudo chown -R ucm:ucm $DATA $CONFIG
  4. Start it (sudo systemctl start ucm) and check that UCM 2.254 opens: this
     records the 2.254 migrations in the database.
  5. Install this release again: it upgrades that database.
EOF
}

case "$(id -u)" in 0) as_root=1 ;; *) as_root="" ;; esac

# -- 1. Does this release start on what was left? ---------------------------------
ENV_FILE=$CONFIG/ucm.env
DB_URL=$(env_value "$ENV_FILE" DATABASE_URL)
DB_PATH=$(env_value "$ENV_FILE" DATABASE_PATH)
if [ -z "$DB_PATH" ]; then
    DB_PATH=$(env_value "$ENV_FILE" DATA_DIR)
    DB_PATH=${DB_PATH:-$DATA}/ucm.db
fi
# Bytecode is not written: the probe runs as root in a tree the service account owns
probe=$(cd "$UCM_HOME/backend" 2>/dev/null && PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_URL=$DB_URL DATABASE_PATH=$DB_PATH \
    "$UCM_HOME/venv/bin/python" migration_runner.py check 2>&1)
code=$?
backend=$(printf '%s\n' "$probe" | head -n 1)
REASON=$(printf '%s\n' "$probe" | sed -n '2,4p' | tr '\n' ' ' | sed 's/ *$//')

case $code in
    0|3) exit 0 ;;
    4) case $backend in
           "sqlite "/*) DB_FILE=${backend#sqlite } ;;
           *)
               say "UCM: the configuration an earlier UCM left in $CONFIG names a database this release"
               say "cannot start on: $REASON"
               say "It is not a SQLite file at an absolute path, so nothing was moved: the service"
               say "will refuse to start."
               say "Install 2.254 and start it once on that database, then install this release again;"
               say "or move $CONFIG and $DATA aside and reinstall this package to start empty."
               exit 0 ;;
       esac ;;
    *)
        say "UCM: an earlier UCM left a configuration or database here that this release could not read"
        say "(${backend:+$backend: }${REASON:-check exited with code $code})."
        say "Nothing was moved; if the service refuses to start,"
        say "install 2.254 and start it once on that data, or move $CONFIG and $DATA aside and reinstall."
        exit 0 ;;
esac

# -- 2. Archive ------------------------------------------------------------------
umask 077
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
say "UCM: an earlier UCM was removed and left a database this release cannot start on:"
say "  $DB_FILE: $REASON"
fail() {
    say "UCM: archiving what it left failed ($1)."
    if [ -n "$JOURNAL" ] && [ -f "$JOURNAL" ]; then
        if roll_back; then
            say "Everything was put back in place."
        else
            say "Some files could not be put back and are still in $DEST:$stuck"
        fi
    else
        [ -z "$DEST" ] || rmdir -- "$DEST" 2>/dev/null
        [ -z "$MADE_PARENT" ] || rmdir -- "$PARENT" 2>/dev/null
        say "Nothing was moved."
    fi
    say "UCM was not started. Fix the cause, then run as root:"
    say "  sh $UCM_HOME/scripts/archive-leftovers.sh $UCM_HOME $DATA $CONFIG"
    say "and set up the new installation: dpkg-reconfigure ucm (Debian, Ubuntu) or"
    say "dnf reinstall ucm (RHEL, Fedora)."
    exit 1
}
if [ ! -d "$PARENT" ]; then
    mkdir -p -- "$PARENT" || fail "cannot create $PARENT"
    MADE_PARENT=1
fi
chmod 700 "$PARENT" || fail "cannot restrict $PARENT"
[ -z "$as_root" ] || chown 0:0 "$PARENT" || fail "cannot give $PARENT to root"
DEST=$PARENT/$STAMP
n=1
until mkdir -- "$DEST" 2>/dev/null; do
    { [ -e "$DEST" ] && [ "$n" -lt 100 ]; } || { DEST=""; fail "cannot create a directory in $PARENT"; }
    n=$((n + 1))
    DEST=$PARENT/$STAMP-$n
done
JOURNAL=$DEST/.journal
: > "$JOURNAL" || fail "cannot write in $DEST"

DB_LINE="" DB_RESTORE=""
if [ -d "$DATA" ]; then
    archive_contents "$DATA" "$DEST/data" || fail "moving $DATA"
fi
if [ -d "$CONFIG" ]; then
    archive_contents "$CONFIG" "$DEST/config" || fail "moving $CONFIG"
fi
# A database DATABASE_PATH placed elsewhere, with what SQLite keeps beside it
case $DB_FILE in
    "$DATA"/*|"$CONFIG"/*) ;;
    *)
        printf 'mkdir\t%s\t%s\n' "${DB_FILE%/*}" "$DEST/database" >> "$JOURNAL" \
            && mkdir -- "$DEST/database" || fail "creating $DEST/database"
        for f in "$DB_FILE" "$DB_FILE-wal" "$DB_FILE-shm" "$DB_FILE-journal"; do
            [ -e "$f" ] || continue
            move_item "$f" "$DEST/database/${f##*/}" || fail "moving $f"
        done
        DB_LINE="  database/   $DB_FILE, which DATABASE_PATH placed outside $DATA
"
        DB_RESTORE=", database/ back to ${DB_FILE%/*}" ;;
esac
remove_copied || fail "removing the sources of the copies"
write_readme || fail "writing $DEST/README.txt"
rm -f -- "$JOURNAL"

say "Moved, unchanged, everything it left in $DATA and $CONFIG${DB_RESTORE:+ and $DB_FILE}"
say "to $DEST (root only; README.txt there says how to restore it)."
say "This installation starts empty, with a new configuration."
exit 0
