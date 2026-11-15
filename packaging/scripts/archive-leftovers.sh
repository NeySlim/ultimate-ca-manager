#!/bin/sh
# Run by the DEB postinst and the RPM %post on a new install, before the configuration
# is written: when an earlier UCM was removed and left a SQLite database this release
# refuses (migration_runner.py check), everything it left is moved, intact, to a root-only
# archive, so the install goes on as on a new machine. Nothing is ever copied or deleted:
# each item is renamed once, so it is whole at exactly one path at any time, and a failed
# step renames back what was moved; the service is then not started.
#
# Usage: UCM_PYTHON=<python> archive-leftovers.sh <ucm home> <data dir> <config dir>
#            [<archive parent> [<log>]]
# Exit 0: nothing to archive, or archived; 3: a database it must not archive is left in
# place, and the service will refuse to start on it; 1: not archived, everything is back
# in place (or nothing was moved: no interpreter to rename with); 2: not archived, some
# files are still in the archive (the next run tries to put them back first). On 1 and 2
# the install must stop; on 3 it must not announce a success.
set -u

UCM_HOME=$1
DATA=$2
CONFIG=$3
# Beside the home (/opt/ucm-archive): outside every path the service may write or back up
PARENT=${4:-${UCM_HOME%/*}/ucm-archive}
LOG=${5:-/var/log/ucm/leftover-archive.log}
# Renames with rename(2) alone: without it, nothing moves
PYTHON=${UCM_PYTHON:-}
# The data directories the packages own or create: kept in place, their contents archived
KEEP_DIRS="ca certs private crl scep backups sessions"
TAB=$(printf '\t')
NL='
'
FIPS_LINE=UCM_FIPS_BUILD=1
# An item rename(2) cannot take out of its filesystem goes into <its directory>/$LOCAL_PREFIX<archive>
LOCAL_PREFIX=.ucm-archive-
# LOCALS: the local archives this run made, one per line between newlines
DEST="" JOURNAL="" MADE_PARENT="" LOCALS=$NL EARLIER="" LAST_ERR="" LAST_DIR=""

log_line() {
    { mkdir -p "${LOG%/*}" && printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; } \
        2>/dev/null || true
}
say() { printf '%s\n' "$*"; log_line "$*"; }

# dnf5 cuts a scriptlet's lines at 80 columns: once a run said a longer one, a last line
# names the log, which holds them whole (after its 21-column date)
LOG_START=$( { wc -c < "$LOG"; } 2>/dev/null) || LOG_START=0
full_text() {
    tail -c +$((LOG_START + 1)) -- "$LOG" 2>/dev/null | awk 'length($0) > 100 { f = 1 } END { exit !f }' \
        && say "UCM: the full text is in $LOG"
}
trap full_text EXIT

# Last value of $2 in env file $1, unquoted; the file is read, never sourced
env_value() {
    [ -f "$1" ] || return 0
    sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$2[[:space:]]*=[[:space:]]*//p" "$1" \
        | tail -n 1 | sed -E 's/[[:space:]]+$//; s/^"(.*)"$/\1/; s/^'"'"'(.*)'"'"'$/\1/'
}

# $1 is a mount point, from the mount table (a bind mount of the same filesystem too):
# kept in place, as it cannot be renamed (EBUSY)
is_mount() {
    mnt=$(findmnt -n -o TARGET -T "$1" 2>/dev/null) && [ "$mnt" = "$(normal "$1")" ]
}

# rename(2) of $1 to $2 (absent), never a copy: GNU mv copies when it is refused (EXDEV),
# outside the journal. Fails, moving nothing, without an interpreter.
rename_item() {
    LAST_ERR=""
    [ -n "$PYTHON" ] || return 1
    err=$(LC_ALL=C "$PYTHON" -I -c \
        'import os, sys; a, b = sys.argv[1:]; os.path.lexists(b) and sys.exit(1); os.rename(a, b)' \
        "$1" "$2" 2>&1) && return 0
    failed_in "$(dir_of "$2")" "$(printf '%s\n' "$err" | tail -n 1)"
    return 1
}

# A failed write keeps the system's error and the directory written in, for fail() to name:
# the commands it reads run under LC_ALL=C, so that "No space left on device" is English
failed_in() { LAST_DIR=$1 LAST_ERR=$2; }

# mkdir of $1, mode $2 if given
make_dir() {
    LAST_ERR=""
    err=$(LC_ALL=C mkdir ${2:+-m "$2"} -- "$1" 2>&1) || { failed_in "$(dir_of "$1")" "$err"; return 1; }
}

present() { [ -e "$1" ] || [ -L "$1" ]; }
dir_of() { d=${1%/*}; printf '%s\n' "${d:-/}"; }

# $1 without ".", ".." or doubled slashes (realpath -m: the path need not exist)
normal() { realpath -m -- "$1" 2>/dev/null || printf '%s\n' "$1"; }

# Appends line $1 to the journal, whole or not at all (tee: a command a test can fail or
# kill). A failed write is cut back to the size before it: truncating needs no free space,
# so this holds on a full disk. Nothing is appended after a line a kill left torn.
jot() {
    size=0 LAST_ERR=""
    if [ -e "$JOURNAL" ]; then
        [ -z "$(tail -c 1 -- "$JOURNAL")" ] && size=$(wc -c < "$JOURNAL") || return 1
    fi
    err=$(printf '%s\n' "$1" | LC_ALL=C tee -a -- "$JOURNAL" 2>&1 >/dev/null) && return 0
    failed_in "${JOURNAL%/*}" "$err"
    truncate -s "$size" -- "$JOURNAL" 2>/dev/null
    return 1
}

# $1 is a line this script writes, with all its fields
whole_step() {
    case $1 in *"$TAB"*"$TAB"*"$TAB"*) return 1 ;; esac
    case $1 in
        rename"$TAB"/*"$TAB"/*|mkdir"$TAB"/*"$TAB"/*|fips"$TAB"/*"$TAB"/*) return 0 ;;
        failed"$TAB"*"$TAB"*) return 1 ;;
        failed"$TAB"/*) return 0 ;;
    esac
    return 1
}

# A rename line, then rename(2) of $1 to $2. 0: moved; 1: refused while $1 is there and $2
# absent, its line out of the journal again; 2: any other failure.
try_rename() {
    jot "rename$TAB$1$TAB$2" || return 2
    rename_item "$1" "$2" && return 0
    { present "$1" && ! present "$2" && drop_line "rename$TAB$1$TAB$2"; } || return 2
    # A refusal met here is no cause of a later failure
    LAST_ERR=""
    return 1
}

# Moves item $1 to $2 in the archive; refused, into the local archive of its directory;
# refused too, a directory stays, its entries moved the same way, and a file fails.
move_item() {
    present "$2" && return 1
    try_rename "$1" "$2"; rc=$?
    [ "$rc" -eq 1 ] || return "$rc"
    dir=${1%/*} loc=${1%/*}/$LOCAL_NAME made=""
    case $LOCALS in
        *"$NL$loc$NL"*) ;;
        *)  # Another's directory of that name is never written into, nor removed
            if present "$loc"; then rc=3; else
                { jot "mkdir$TAB${dir:-/}$TAB$loc" && make_dir "$loc" 700; } || return 2
                LOCALS=$LOCALS$loc$NL made=1
            fi ;;
    esac
    if [ "$rc" -ne 3 ]; then
        try_rename "$1" "$loc/${1##*/}"; rc=$?
        [ "$rc" -eq 1 ] || return "$rc"
    fi
    if [ -n "$made" ]; then
        rmdir -- "$loc" || return 2
        LOCALS=${LOCALS%"$loc$NL"}
    fi
    if [ ! -d "$1" ] || [ -L "$1" ]; then
        say "UCM: $1 could not be renamed, into the archive or beside it."
        return 1
    fi
    archive_contents "$1" "$2"
}

is_kept() {
    [ "$1" = "$DATA" ] || return 1
    case " $KEEP_DIRS " in *" $2 "*) return 0 ;; esac
    return 1
}

# Archives the contents of directory $1, which stays, into $2 (created here). A kept
# directory or a mount point is never moved itself: its contents are, the same way. A
# local archive an earlier run left is not an item: it stays, and the README names it.
archive_contents() {
    odd_names "$1"
    { jot "mkdir$TAB$1$TAB$2" && make_dir "$2"; } || return 1
    for entry in "$1"/* "$1"/.[!.]* "$1"/..?*; do
        present "$entry" || continue
        case ${entry##*/} in "$LOCAL_PREFIX"*) EARLIER=$EARLIER$entry$NL; continue ;; esac
        if [ -d "$entry" ] && [ ! -L "$entry" ] && { is_kept "$1" "${entry##*/}" \
                || is_mount "$entry"; }; then
            archive_contents "$entry" "$2/${entry##*/}" || return 1
        else
            move_item "$entry" "$2/${entry##*/}" || return 1
        fi
    done
}

# The journal without line $1, written aside then renamed over it
drop_line() {
    { grep -vxF -e "$1" -- "$JOURNAL"; [ $? -le 1 ]; } > "$JOURNAL.new" 2>/dev/null \
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
    if present "$1"; then stuck="$stuck$NL  $1: $2"; fi
    if grep -qxF "failed$TAB$1" "$JOURNAL" 2>/dev/null; then
        again=1
    else
        jot "failed$TAB$1" 2>/dev/null || true
    fi
}

# The two reasons a directory of a journal line is absent, and what each one asks for
remedy() {
    printf '%s' "mount what holds it, or, if it was removed by hand, make it again, empty (mkdir -p $1), then retry"
}

# $1 holds a path already named in $stuck: it stays, and is not named itself
holds_stuck() {
    case $stuck in *"$NL  $1/"*) left=1; return 0 ;; esac
    return 1
}

# A directory a mkdir line names as kept in place (never removed by this script) strictly
# under directory $1, absent now: the tree of $1 is not mounted, its mount point left empty
lost_under() {
    printf '%s\n' "$lines" | P=${1%/}/ awk -F "$TAB" '$1 == "mkdir" && index($2, ENVIRON["P"]) == 1 { print $2 }' \
        | while IFS= read -r d; do [ -d "$d" ] || { printf '%s\n' "$d"; break; }; done
}

# The paths not put back or cleared, then what the next attempt does with them
say_stuck() {
    say "Some files could not be put back or cleared (archive: $DEST):"
    printf '%s\n' "${stuck:-
  $DEST: still holds what could not be put back}" | sed 1d | while IFS= read -r line; do
        say "$line"
    done
    if [ -n "$broken" ]; then
        say "Nothing was put back, and retrying alone will not: do what the line says, then retry."
    elif [ -n "$again" ]; then
        say "These failed the same way at the previous attempt: retrying alone will not put"
        say "them back. Fix what each line names, then retry; they stay where they are meanwhile."
    elif [ -n "$twice" ]; then
        say "The next attempt tries again to put them back before anything else, except where"
        say "a line asks you to choose: those wait for your choice."
    else
        say "The next attempt tries again to put them back before anything else."
    fi
}

# Undoes the journal, last step first, by renames back alone. Every line replays as a
# no-op once undone, so a retry from any interrupted state converges; an archive directory
# removed by hand reads as a filesystem not mounted until it is made again, empty.
roll_back() {
    stuck="" left="" seen="" again="" twice="" broken="" missing=""
    # A last line a kill left torn was never a step: cut off (that needs no free space), the
    # journal holds whole lines only from here on, and the next ones can be written
    { [ -z "$(tail -c 1 -- "$JOURNAL")" ] || truncate -s "$(sed '$d' -- "$JOURNAL" | wc -c)" -- "$JOURNAL"; } \
        && lines=$(cat -- "$JOURNAL") || { unsettled "$JOURNAL" "could not be read or cut to its whole lines"; return 1; }
    # Any line that is not a whole step stops the put-back before it touches anything
    while IFS= read -r line; do
        [ -z "$line" ] || whole_step "$line" && continue
        left=1 broken=1 stuck="
  $JOURNAL: holds a line that is not a whole step, so nothing it lists was put back: compare it with the archive, put back what it names by hand, then remove the journal"
        return 1
    done <<EOF
$lines
EOF
    undo=$(printf '%s\n' "$lines" | sed -n '1!G;h;$p')
    while IFS="$TAB" read -r op src dst; do
        case $op in
            rename)
                # The directory of either side absent is a filesystem not mounted (a line
                # written before its rename ran, too): nothing there is named lost or touched
                absent=""
                [ -d "$(dir_of "$dst")" ] || absent=$(dir_of "$dst")
                [ -d "$(dir_of "$src")" ] || absent=$(dir_of "$src")
                # So is a source directory left as an empty mount point
                [ -n "$absent" ] || present "$src" || absent=$(lost_under "$(dir_of "$src")")
                # A rename is atomic: both there, the source was made again since
                if present "$dst" && present "$src"; then
                    twice=1
                    unsettled "$dst" "not put back to $src, which exists again: keep one of the two, remove the other, then retry"
                elif present "$dst" && [ -n "$absent" ]; then
                    left=1 stuck="$stuck
  $dst: not put back to $src, as $absent is absent: $(remedy "$absent")"
                elif present "$dst"; then
                    rename_item "$dst" "$src" || unsettled "$dst" "not put back to $src"
                elif ! present "$src"; then
                    if [ -n "$absent" ]; then
                        left=1 stuck="$stuck
  $dst: not put back to $src: neither is there, as $absent is absent: $(remedy "$absent")"
                    else
                        # Removed by hand: named once, then its line goes, as its directory
                        # removed empty below would read as not mounted at the next attempt
                        say "UCM: $src is missing: an earlier attempt moved it to $dst, which no longer holds it either."
                        missing="$missing$NL  $src"
                        drop_line "rename$TAB$src$TAB$dst" \
                            || { unsettled "$JOURNAL" "could not be updated, so what it lists before $src was not put back"; break; }
                    fi
                fi ;;
            fips)
                # The new ucm.env goes while the archived one can take its place, once: the
                # line goes too, or an old ucm.env put back since could pass for the new one
                gone=""
                if present "$dst" && fips_written "$src"; then
                    rm -f -- "$src" || { unsettled "$src" "the new configuration could not be removed for $dst to be put back"; break; }
                    gone=" once $src was removed"
                fi
                # Stopped here, what is left is the journal with that line and the archive
                drop_line "fips$TAB$src$TAB$dst" \
                    || { unsettled "$JOURNAL" "could not be updated$gone, so nothing it lists was put back"; break; } ;;
            mkdir)
                # Kept, not named, when it holds a path named already, there or not: removing
                # it would lose that one, or read as not mounted at the next attempt
                if [ -d "$dst" ]; then holds_stuck "$dst" || rmdir -- "$dst" 2>/dev/null \
                    || unsettled "$dst" "could not be removed"; fi ;;
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

# After a complete put-back: $1, or $2 with what the journal named at neither path
put_back() {
    if [ -z "$missing" ]; then say "$1"; return; fi
    say "$2"
    printf '%s\n' "$missing" | sed 1d | while IFS= read -r line; do say "$line"; done
}

# Each local archive with what it holds, one line each
local_lines() {
    printf '%s' "$1" | while IFS= read -r d; do
        [ -z "$d" ] || printf '  %s/: %s\n' "$d" "$(ls -A -- "$d" 2>/dev/null | tr '\n' ' ' | sed 's/ $//')"
    done
}

# The 2.254 package published for this system, by the names of the 2.254 release assets
OS_RELEASE=${UCM_OS_RELEASE:-/etc/os-release}
os_field() {
    [ -r "$OS_RELEASE" ] && sed -n -E "s/^$1=//p" "$OS_RELEASE" | tail -n 1 | sed -E 's/^"(.*)"$/\1/'
}
install_254() {
    id=$(os_field ID) like=" $(os_field ID_LIKE) " ver=$(os_field VERSION_ID)
    deb="sudo apt install --allow-downgrades ./ucm_2.254_all.deb"
    fc="sudo dnf downgrade ./ucm-2.254-1.fc43.noarch.rpm"
    el9="sudo dnf downgrade ./ucm-el9-2.254-1.el9.noarch.rpm"
    case "$id$like" in
        rhel*|almalinux*|rocky*|centos*|*" rhel "*|*" centos "*)
            if [ "${ver%%.*}" = 9 ]; then echo "$el9"; else
                echo "no UCM 2.254 package was published for this system: put the archive back"
                echo "     on a system 2.254 was published for (Debian, Ubuntu, Fedora, EL9)"
            fi ;;
        fedora*) echo "$fc" ;;
        debian*|ubuntu*|*" debian "*|*" ubuntu "*) echo "$deb" ;;
        *) printf '%s\n' "Debian, Ubuntu: $deb;" "     Fedora: $fc;" "     EL9: $el9" ;;
    esac
}

write_readme() {
    UNCHANGED=unchanged ROOT_OWNED=""
    if [ "$LOCALS" != "$NL" ]; then
        # Given to root once the journal is gone (see the end of the run), as root only
        [ -z "$as_root" ] || UNCHANGED="unchanged but for the owner of what is kept beside" ROOT_OWNED="
What they hold now belongs to root (owner and group); nothing else in it changed."
        BESIDE="
Kept beside where they were, in directories readable by root only, as each one
could not be renamed out of its filesystem (another filesystem, a bind mount, overlayfs):
$(local_lines "$LOCALS")$ROOT_OWNED
Nothing in them is used or removed by UCM: removing the package with its
configuration (apt purge) leaves them where they are.
"
    else
        BESIDE=""
    fi
    # Only this archiving's local archives go back: an earlier one holds another installation
    LOCAL_RESTORE=""
    [ "$LOCALS" = "$NL" ] || LOCAL_RESTORE=",
     and the contents of each directory listed under \"Kept beside where they
     were\" into the directory that holds it (then remove it, empty)"
    if [ -n "$EARLIER" ]; then
        BESIDE="$BESIDE
Left where they were, by an earlier archiving (their own README.txt is in the archive
that run wrote under $PARENT):
$(printf '%s' "$EARLIER" | sed 's/^/  /')
"
    fi
    # A purge removed ucm.env with the package: the one this installation writes is kept, as
    # 2.254 keeps an existing ucm.env that holds a SECRET_KEY
    CONFIG_LINE="  config/     what was in $CONFIG (ucm.env, master.key)
" CONFIG_RESTORE=", of config/ into $CONFIG" ENV_KEEP="" NO_ENV=""
    [ -n "$(ls -A -- "$DEST/config" 2>/dev/null)" ] || CONFIG_LINE="" CONFIG_RESTORE=""
    if ! present "$DEST/config/ucm.env" && ! present "$CONFIG/$LOCAL_NAME/ucm.env"; then
        ENV_KEEP=", and $CONFIG/ucm.env"
        NO_ENV="
No ucm.env was left in $CONFIG (removing the package with its configuration, as
apt purge does, removes it): step 4 keeps $CONFIG/ucm.env, the one this installation
wrote, which UCM 2.254 keeps as it installs.
What the removed one held is lost: its SECRET_KEY, the session key (open sessions
end), and any setting written there by hand. Private keys encrypted with a
master.key or a KEY_ENCRYPTION_KEY that was not kept cannot be decrypted.
"
    fi
    cat > "$DEST/README.txt" <<EOF
UCM: what an earlier installation left on this machine

Archived on $STAMP (UTC) by the UCM $(cat "$UCM_HOME/VERSION" 2>/dev/null || echo 3.0) package,
installed while no UCM package was installed and an earlier one had left its files.
This release cannot start on the database that installation left:
  $REASON
So the package moved that installation's files, unchanged, and set up a new, empty UCM
in their place.

Contents
  data/       what was in $DATA (database, CA files, private keys, HTTPS key and
              certificate, backups, sessions)
$CONFIG_LINE$DB_LINE$BESIDE$NO_ENV
This directory holds private keys and the key that decrypts the database: keep it
readable by root only. Nothing here is used or removed by UCM. Every file was renamed,
never copied: each one is here or in a directory listed above, $UNCHANGED. A directory
that could not be renamed stays where it was, and its entries were moved the same way.
While an attempt left a .journal in a directory under $PARENT, remove nothing from it;
make a directory removed there again, empty (mkdir -p), before a retry puts back the rest.

To put that installation back in service
  1. Stop UCM: sudo systemctl stop ucm
  2. Install UCM 2.254 in place of this release (the Debian and Ubuntu package
     starts it as it installs):
     $(install_254)
  3. Stop it: sudo systemctl stop ucm
  4. Move aside what the new installation wrote in $DATA and $CONFIG (all but
     the directories named .ucm-archive-*$ENV_KEEP), then put these back: the contents of data/
     into $DATA$CONFIG_RESTORE$DB_RESTORE$LOCAL_RESTORE; then
     sudo find $DATA/ $CONFIG/ -name '.ucm-archive-*' -prune -o -exec chown -h ucm:ucm {} +
     The 2.254 package gave every .ucm-archive-* directory to the service account as it
     installed: give those left back to root, readable by root only:
     sudo find $DATA/ $CONFIG/ -name '.ucm-archive-*' -prune -exec chown -hR root:root {} + -exec chmod 700 {} +
  5. Start it (sudo systemctl start ucm) and check that UCM 2.254 opens: this
     records the 2.254 migrations in the database.
  6. Install this release again: it upgrades that database.
EOF
}

# dnf 4 (EL9) ends a failed scriptlet with "Complete!" and exit 0: the line says how to tell
stopped() {
    say "The installation stops here: nothing else is written, and UCM was not started."
    say "Even if dnf ends with Complete!, UCM is not running: systemctl is-active ucm"
}

# Without an interpreter, nothing is renamed: before archiving, the run stops (1); with
# an attempt left to finish, that attempt's archive is named as it stands (2)
no_interpreter() {
    say "UCM: no interpreter to rename files with (UCM_PYTHON=${PYTHON:-unset}): nothing was moved."
    if [ -n "$DEST" ]; then
        say "An earlier attempt to archive what a removed UCM left did not complete."
        stuck="
  $DEST: still holds what could not be put back, which needs that interpreter" again="" twice="" broken=""
        say_stuck
    fi
    stopped
    exit "$1"
}

case "$(id -u)" in 0) as_root=1 ;; *) as_root="" ;; esac
RENAME=""
[ -z "$PYTHON" ] || ! "$PYTHON" -I -c '' 2>/dev/null || RENAME=1

# -- 0. An earlier run that could not put everything back is finished first --------
for d in "$PARENT"/*/; do
    # Killed before its journal was written, or after it was removed: nothing to keep
    [ -e "$d.journal" ] || [ -e "${d}README.txt" ] || { rm -f -- "$d.journal.new"; rmdir -- "$d"; } \
        2>/dev/null || true
done
for j in "$PARENT"/*/.journal; do
    [ -f "$j" ] || continue
    DEST=${j%/.journal} JOURNAL=$j
    [ -n "$RENAME" ] || no_interpreter 2
    if roll_back; then
        say "UCM: an earlier attempt to archive what a removed UCM left did not complete:"
        put_back "what it had left in its archive is back in place now." \
            "the rest of what it had left in its archive is back in place now; at neither path:"
    else
        say "UCM: an earlier attempt to archive what a removed UCM left did not complete."
        say_stuck
        stopped
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
# Nothing can be archived without it: the run stops before asking about the database
[ -n "$RENAME" ] || no_interpreter 1
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
    case $LAST_ERR in
        *"No space left on device"*) say "No space left in $LAST_DIR: $LAST_ERR" ;;
    esac
    rc=1
    if [ -n "$JOURNAL" ] && [ -f "$JOURNAL" ]; then
        if roll_back; then
            put_back "Everything was put back in place." \
                "Everything else was put back in place; at neither path:"
        else
            say_stuck
            rc=2
        fi
    else
        [ -z "$DEST" ] || rmdir -- "$DEST" 2>/dev/null
        [ -z "$MADE_PARENT" ] || rmdir -- "$PARENT" 2>/dev/null
        say "Nothing was moved."
    fi
    stopped
    exit "$rc"
}
# A journal line holds no tab or line break: one in the path of the database or of an entry
# of the directories $@ (those the run walks, through a link too) stops it, shown visibly
odd_names() {
    odd=$(find -H "$@" -maxdepth 1 \( -path "*$TAB*" -o -path "*$NL*" \) -printf '%p.' -quit 2>/dev/null)
    case $DB_FILE in *"$TAB"*) odd=${odd:-$DB_FILE.} ;; esac
    [ -z "$odd" ] || fail "$(printf '%s' "$odd" | sed -e ':a' -e '$!N' -e '$!ba' -e 's/\n/<newline>/g' \
        -e "s/$TAB/<tab>/g" -e 's/\.$//') has a tab or a line break in its name, which the journal cannot hold: rename it"
}
# Before anything moves: the entries of the data, the configuration, each kept directory not a link
set --; for d in $KEEP_DIRS; do [ -L "$DATA/$d" ] || set -- "$@" "$DATA/$d"; done; odd_names "$DATA" "$CONFIG" "$@"
[ -d "$PARENT" ] || { mkdir -p -- "$PARENT" || fail "cannot create $PARENT"; MADE_PARENT=1; }
chmod 700 "$PARENT" || fail "cannot restrict $PARENT"
[ -z "$as_root" ] || chown 0:0 "$PARENT" || fail "cannot give $PARENT to root"
DEST=$PARENT/$STAMP n=1
until mkdir -- "$DEST" 2>/dev/null; do
    { [ -e "$DEST" ] && [ "$n" -lt 100 ]; } || { DEST=""; fail "cannot create a directory in $PARENT"; }
    n=$((n + 1))
    DEST=$PARENT/$STAMP-$n
done
JOURNAL=$DEST/.journal LOCAL_NAME=$LOCAL_PREFIX${DEST##*/}

DB_LINE="" DB_RESTORE="" DB_MOVED=""
if [ -d "$DATA" ]; then
    archive_contents "$DATA" "$DEST/data" || fail "moving $DATA"
fi
if [ -d "$CONFIG" ]; then
    archive_contents "$CONFIG" "$DEST/config" || fail "moving $CONFIG"
fi
# A database DATABASE_PATH placed elsewhere, with what SQLite keeps beside it
case $(normal "$DB_FILE") in
    "$(normal "$DATA")"/*|"$(normal "$CONFIG")"/*) ;;
    *)  # A database in / is named there by "/", as a journal line has no empty field
        DB_DIR=${DB_FILE%/*}
        { jot "mkdir$TAB${DB_DIR:-/}$TAB$DEST/database" && make_dir "$DEST/database"; } \
            || fail "creating $DEST/database"
        for f in "$DB_FILE" "$DB_FILE-wal" "$DB_FILE-shm" "$DB_FILE-journal"; do
            [ -e "$f" ] || continue
            move_item "$f" "$DEST/database/${f##*/}" || fail "moving $f"
        done
        DB_MOVED=1
        # Kept beside itself, it is named with the local archives: database/ stays empty
        [ -z "$(ls -A -- "$DEST/database")" ] || DB_LINE="  database/   $DB_FILE, which DATABASE_PATH placed outside $DATA
" DB_RESTORE=", of database/ into ${DB_DIR:-/}" ;;
esac
# Written inside the journal, so that a retry after any interruption takes it back first;
# the line names where the archived ucm.env went, centrally or beside the new one
if [ -n "$FIPS_BUILD" ]; then
    OLD_ENV=$DEST/config/ucm.env
    present "$OLD_ENV" || OLD_ENV=$CONFIG/$LOCAL_NAME/ucm.env
    { jot "fips$TAB$ENV_FILE$TAB$OLD_ENV" && printf 'UCM_FIPS_BUILD=1\n' > "$ENV_FILE"; } \
        || fail "writing UCM_FIPS_BUILD=1 into $ENV_FILE"
fi
write_readme || fail "writing $DEST/README.txt"
rm -f -- "$JOURNAL" || fail "removing $JOURNAL"
# Once nothing can be put back: what a local archive holds is root's, like the directory
[ -z "$as_root" ] || printf '%s' "$LOCALS" | while IFS= read -r d; do
    [ -z "$d" ] || chown -hR 0:0 -- "$d" || say "UCM: what $d holds could not all be given to root."
done

say "Moved, unchanged, everything it left in $DATA and $CONFIG${DB_MOVED:+ and $DB_FILE}"
say "to $DEST (root only; README.txt there says how to restore it)."
if [ "$LOCALS" != "$NL" ]; then
    say "What could not be renamed out of its filesystem is beside it, readable by root only, in:"
    printf '%s' "$LOCALS" | while IFS= read -r d; do [ -z "$d" ] || say "  $d"; done
fi
[ -z "$FIPS_BUILD" ] || say "UCM_FIPS_BUILD=1, set in the archived ucm.env, is kept in the new $ENV_FILE."
say "This installation starts empty, with a new configuration."
exit 0
