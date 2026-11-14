#!/bin/sh
# Run by the DEB postinst and the RPM %post on a new install, before the configuration
# is written: when an earlier UCM was removed and left a SQLite database this release
# refuses (migration_runner.py check), everything it left is moved, intact, to a root-only
# archive, so the install goes on as on a new machine. Nothing is ever deleted: a failed
# step puts back what was moved, and the service is then not started.
#
# Usage: UCM_PYTHON=<python> archive-leftovers.sh <ucm home> <data dir> <config dir>
#            [<archive parent> [<log>]]
# Exit 0: nothing to archive, or archived; 3: a database it must not archive is left in
# place, and the service will refuse to start on it; 1: not archived, everything is back
# in place; 2: not archived, some files are still in the archive (the next run tries to
# put them back first). On 1 and 2 the install must stop; on 3 it must not announce a success.
set -u

UCM_HOME=$1
DATA=$2
CONFIG=$3
# Beside the home (/opt/ucm-archive): outside every path the service may write or back up
PARENT=${4:-${UCM_HOME%/*}/ucm-archive}
LOG=${5:-/var/log/ucm/leftover-archive.log}
# Renames with rename(2) alone; without it, every move is a verified copy
PYTHON=${UCM_PYTHON:-}
# The data directories the packages own or create: kept in place, their contents archived
KEEP_DIRS="ca certs private crl scep backups sessions"
TAB=$(printf '\t')
FIPS_LINE=UCM_FIPS_BUILD=1
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

# $1 is a mount point, from the mount table (a bind mount of the same filesystem too):
# kept in place, as rm -rf would empty it then fail (EBUSY)
is_mount() {
    mnt=$(findmnt -n -o TARGET -T "$1" 2>/dev/null) && [ "$mnt" = "$(normal "$1")" ]
}

# rename(2) of $1 to $2 (absent), never a copy: GNU mv copies when it is refused (EXDEV),
# outside the journal. Fails, moving nothing, without an interpreter.
rename_item() {
    [ -n "$PYTHON" ] && "$PYTHON" -I -c \
        'import os, sys; a, b = sys.argv[1:]; os.path.lexists(b) and sys.exit(1); os.rename(a, b)' \
        "$1" "$2" 2>/dev/null
}

present() { [ -e "$1" ] || [ -L "$1" ]; }

# $1 without ".", ".." or doubled slashes (realpath -m: the path need not exist)
normal() { realpath -m -- "$1" 2>/dev/null || printf '%s\n' "$1"; }

# A comparable digest of a file, a symbolic link, a special file or a whole tree: names,
# types, contents, and what a copy carries over last (mode, owner, group, date of the
# files). Equal means whole; fails, printing nothing usable, when a command it runs fails.
digest() {
    if [ -L "$1" ]; then
        target=$(readlink -- "$1") || return 1
        printf 'link %s\n' "$target"
    elif [ -d "$1" ]; then
        list=$(cd -- "$1" && find . \( -type f -exec cksum {} + \) -o \( -type l -exec sh -c \
            'for l; do t=$(readlink -- "$l") || exit 1; printf "link %s %s\n" "$l" "$t"; done' sh {} + \) \
            -o -print && find . ! -type l -printf 'attr %y %m %U %G %p\n' \
            && find . -type f -printf 'date %Ts %p\n') || return 1
        printf '%s\n' "$list" | LC_ALL=C sort
    elif [ -f "$1" ]; then
        sum=$(cksum < "$1") && attr=$(stat -c 'attr %a %u %g %Y' -- "$1") || return 1
        printf '%s\n%s\n' "$sum" "$attr"
    else
        # A FIFO or a device is never read (a FIFO would block): its kind and attributes
        stat -c 'special %F %t %T %a %u %g' -- "$1"
    fi
}

# $1 and $2 have one digest, and both could be taken
same() { d1=$(digest "$1") && d2=$(digest "$2") && [ -n "$d1" ] && [ "$d1" = "$d2" ]; }

# Moves $1 to $2 (absent): a rename, else a verified copy whose source is removed only
# once every item is in the archive (remove_copied). A refused rename moved nothing: its
# line leaves the journal before the copy line comes.
move_item() {
    if present "$2"; then return 1; fi
    printf 'rename\t%s\t%s\n' "$1" "$2" >> "$JOURNAL" || return 1
    rename_item "$1" "$2" && return 0
    { present "$1" && ! present "$2" && drop_line "rename$TAB$1$TAB$2"; } || return 1
    printf 'copy\t%s\t%s\n' "$1" "$2" >> "$JOURNAL" || return 1
    cp -a -- "$1" "$2" || return 1
    same "$1" "$2" || return 1
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
                || is_mount "$entry"; }; then
            archive_contents "$entry" "$2/${entry##*/}" || return 1
        else
            move_item "$entry" "$2/${entry##*/}" || return 1
        fi
    done
}

# Second phase of a cross-filesystem move: every copy is verified, the sources go
remove_copied() {
    grep "^copy$TAB" "$JOURNAL" | while IFS="$TAB" read -r _op src dst; do
        printf 'remove\t%s\t%s\n' "$src" "$dst" >> "$JOURNAL" || exit 1
        rm -rf -- "$src" || exit 1
    done
}

# The journal without line $1, written aside then renamed over it
drop_line() {
    { grep -vxF -- "$1" "$JOURNAL"; [ $? -le 1 ]; } > "$JOURNAL.new" 2>/dev/null \
        && mv -- "$JOURNAL.new" "$JOURNAL"
}

# $1 holds the new ucm.env, or the start of it a failed write left
fips_written() {
    [ -f "$1" ] && [ ! -L "$1" ] && [ "$(wc -c < "$1")" -le 17 ] \
        && case $FIPS_LINE in "$(cat -- "$1")"*) true ;; *) false ;; esac
}

# $1 could not be undone, $2 says how; named in $stuck, one line each, only while it is
# really there. A failed line remembers it in the journal: met again at the next attempt,
# retrying alone will not do.
unsettled() {
    left=1
    case " $seen " in *" $1 "*) return 0 ;; esac
    seen="$seen $1"
    if present "$1"; then stuck="$stuck
  $1: $2"; fi
    if grep -qxF "failed$TAB$1" "$JOURNAL" 2>/dev/null; then
        again=1
    else
        printf 'failed\t%s\n' "$1" >> "$JOURNAL" 2>/dev/null || true
    fi
}

# The paths not put back or cleared, then what the next attempt does with them
say_stuck() {
    say "Some files could not be put back or cleared (archive: $DEST):"
    printf '%s\n' "${stuck:-
  $DEST: still holds what could not be put back}" | sed 1d | while IFS= read -r line; do
        say "$line"
    done
    if [ -n "$again" ]; then
        say "These failed the same way at the previous attempt: retrying alone will not put"
        say "them back. Fix what each line names, then retry; they stay where they are meanwhile."
    elif [ -n "$twice" ]; then
        say "The next attempt tries again to put them back before anything else, except where"
        say "both paths exist: those wait for your choice."
    else
        say "The next attempt tries again to put them back before anything else."
    fi
}

# Undoes the journal, last step first. Every line replays as a no-op once undone, so a
# retry from any interrupted state converges. A copy goes only once its source is whole
# again and its remove line is out of the journal: no retry meets a half-deleted copy.
roll_back() {
    stuck="" left="" seen="" again="" twice=""
    undo=$(sed -n '1!G;h;$p' "$JOURNAL") || { unsettled "$JOURNAL" "could not be read"; return 1; }
    while IFS="$TAB" read -r op src dst; do
        case $op in
            rename)
                # A rename is atomic: both there, the source was made again since
                if present "$dst" && present "$src"; then
                    twice=1
                    unsettled "$dst" "not put back to $src, which exists again: keep one of the two, remove the other, then retry"
                elif present "$dst"; then
                    rename_item "$dst" "$src" || unsettled "$dst" "not put back to $src"
                fi ;;
            remove)
                # Undone already when the copy is gone: its source was whole again first
                present "$dst" || continue
                if [ -d "$dst" ] && [ ! -L "$dst" ]; then
                    mkdir -p -- "$src" && cp -a -- "$dst/." "$src/"
                else
                    # Always redone: a put-back cut short leaves a source that only looks whole
                    rm -f -- "$src" && cp -a -- "$dst" "$src"
                fi
                put=$?
                # Whole again, and the copy said so: its copy line, undone next, removes the copy
                if [ "$put" -ne 0 ] || ! same "$src" "$dst" \
                        || ! drop_line "remove$TAB$src$TAB$dst"; then
                    unsettled "$dst" "not put back to $src"
                fi ;;
            copy)
                # While its remove line stays, the copy may be all that is left of a file
                if grep -qxF "remove$TAB$src$TAB$dst" "$JOURNAL"; then
                    unsettled "$dst" "not put back to $src"
                elif present "$dst"; then
                    rm -rf -- "$dst" || unsettled "$dst" "a copy of $src, which is back in place, could not be removed"
                fi ;;
            fips)
                # The new ucm.env goes while the archived one can take its place, once: the
                # line goes too, or an old ucm.env put back since could pass for the new one
                if present "$dst" && fips_written "$src"; then
                    rm -f -- "$src" || { unsettled "$src" "the new configuration could not be removed for $dst to be put back"; break; }
                fi
                # Stopped here, what is left is the journal with that line and the archive
                drop_line "fips$TAB$src$TAB$dst" \
                    || { unsettled "$JOURNAL" "could not be updated once $src was removed, so nothing it lists was put back"; break; } ;;
            mkdir)
                if [ -d "$dst" ]; then rmdir -- "$dst" 2>/dev/null || unsettled "$dst" "could not be removed"; fi ;;
        esac
    done <<EOF
$undo
EOF
    for f in "$DEST/README.txt" "$JOURNAL.new"; do
        if present "$f"; then rm -f -- "$f" || unsettled "$f" "could not be removed"; fi
    done
    [ -z "$left" ] || return 1
    rm -f -- "$JOURNAL" || { unsettled "$JOURNAL" "could not be removed"; return 1; }
    rmdir -- "$DEST" 2>/dev/null || { unsettled "$DEST" "could not be removed"; return 1; }
    [ -z "$MADE_PARENT" ] || rmdir -- "$PARENT" 2>/dev/null || true
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
  data/       what was in $DATA (database, CA files, private keys, HTTPS key and
              certificate, backups, sessions)
  config/     what was in $CONFIG (ucm.env, master.key)
$DB_LINE
This directory holds private keys and the key that decrypts the database: keep it
readable by root only. Nothing here is used or removed by UCM. What was copied from
another filesystem was checked: contents, mode, owner, group, and the dates of files;
extended attributes and ACLs were copied where this filesystem keeps them, unchecked.

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

# -- 0. An earlier run that could not put everything back is finished first --------
for d in "$PARENT"/*/; do
    # Killed before its journal was written, or after it was removed: nothing to keep
    [ -e "$d.journal" ] || [ -e "${d}README.txt" ] || { rm -f -- "$d.journal.new"; rmdir -- "$d"; } \
        2>/dev/null || true
done
for j in "$PARENT"/*/.journal; do
    [ -f "$j" ] || continue
    DEST=${j%/.journal} JOURNAL=$j
    if roll_back; then
        say "UCM: an earlier attempt to archive what a removed UCM left did not complete:"
        say "the files it could not put back are in place again."
    else
        say "UCM: an earlier attempt to archive what a removed UCM left did not complete."
        say_stuck
        say "The installation stops here: nothing else is written, and UCM was not started."
        exit 2
    fi
done
DEST="" JOURNAL=""

# -- 1. Does this release start on what was left? ---------------------------------
ENV_FILE=$CONFIG/ucm.env
DB_URL=$(env_value "$ENV_FILE" DATABASE_URL)
DB_PATH=$(env_value "$ENV_FILE" DATABASE_PATH)
if [ -z "$DB_PATH" ]; then
    DB_PATH=$(env_value "$ENV_FILE" DATA_DIR)
    DB_PATH=${DB_PATH:-$DATA}/ucm.db
fi
# An install choice, not instance data: the venv was already built from it
case $(env_value "$ENV_FILE" UCM_FIPS_BUILD | tr '[:upper:]' '[:lower:]') in
    1|true|yes|on) FIPS_BUILD=1 ;;
    *) FIPS_BUILD="" ;;
esac
# No configuration and no database left: a new host, nothing to ask the runner about
if [ ! -e "$ENV_FILE" ] && [ ! -e "$DB_PATH" ] && [ ! -L "$DB_PATH" ]; then
    exit 0
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
    6)
        # A downgrade, not leftovers of an older release: nothing is archived
        say "UCM: the database an earlier UCM left (${backend:-unknown}) was written by a release"
        say "later than this one: $REASON"
        say "Nothing was moved, and the service will refuse to start on it."
        say "Reinstall the release that wrote this database, or move $CONFIG and $DATA aside"
        say "and reinstall this package to start empty."
        exit 3 ;;
    4) case $backend in
           "sqlite "/*) DB_FILE=${backend#sqlite } ;;
           *)
               say "UCM: the configuration an earlier UCM left in $CONFIG names a database"
               say "(${backend:-unknown}) this release cannot start on: $REASON"
               say "It is not a SQLite file at an absolute path, so nothing was moved: the service"
               say "will refuse to start."
               say "Install 2.254 and start it once on that database, then install this release again;"
               say "or move $CONFIG and $DATA aside and reinstall this package to start empty."
               exit 3 ;;
       esac ;;
    *)
        say "UCM: an earlier UCM left a configuration or database here that this release could not read"
        say "(${backend:+$backend: }${REASON:-check exited with code $code})."
        say "Nothing was moved; if the service refuses to start,"
        say "install 2.254 and start it once on that data, or move $CONFIG and $DATA aside and reinstall."
        exit 3 ;;
esac

# -- 2. Archive ------------------------------------------------------------------
umask 077
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
say "UCM: an earlier UCM was removed and left a database this release cannot start on:"
say "  $DB_FILE: $REASON"
fail() {
    say "UCM: archiving what it left failed ($1)."
    rc=1
    if [ -n "$JOURNAL" ] && [ -f "$JOURNAL" ]; then
        if roll_back; then
            say "Everything was put back in place."
        else
            say_stuck
            rc=2
        fi
    else
        [ -z "$DEST" ] || rmdir -- "$DEST" 2>/dev/null
        [ -z "$MADE_PARENT" ] || rmdir -- "$PARENT" 2>/dev/null
        say "Nothing was moved."
    fi
    say "The installation stops here: nothing else is written, and UCM was not started."
    exit "$rc"
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
case $(normal "$DB_FILE") in
    "$(normal "$DATA")"/*|"$(normal "$CONFIG")"/*) ;;
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
# Written inside the journal, so that a retry after any interruption takes it back first
if [ -n "$FIPS_BUILD" ]; then
    { printf 'fips\t%s\t%s\n' "$ENV_FILE" "$DEST/config/ucm.env" >> "$JOURNAL" \
        && printf 'UCM_FIPS_BUILD=1\n' > "$ENV_FILE"; } || fail "writing UCM_FIPS_BUILD=1 into $ENV_FILE"
fi
write_readme || fail "writing $DEST/README.txt"
rm -f -- "$JOURNAL" || fail "removing $JOURNAL"

say "Moved, unchanged, everything it left in $DATA and $CONFIG${DB_RESTORE:+ and $DB_FILE}"
say "to $DEST (root only; README.txt there says how to restore it)."
[ -z "$FIPS_BUILD" ] || say "UCM_FIPS_BUILD=1, set in the archived ucm.env, is kept in the new $ENV_FILE."
say "This installation starts empty, with a new configuration."
exit 0
