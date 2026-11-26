#!/bin/bash
# Steps shared by the DEB postinst, the RPM %post and the updater: ucm.env completion,
# the venv (standard wheels, or built against the system OpenSSL with UCM_FIPS_BUILD=1)
# and the host FIPS state. Subcommands and their arguments: see the case at the end.
set -eu

OS_RELEASE=${UCM_SETUP_OS_RELEASE:-/etc/os-release}
FIPS_FLAG=${UCM_SETUP_FIPS_FLAG:-/proc/sys/crypto/fips_enabled}
RUST_ROOT=${UCM_SETUP_RUST_ROOT:-/usr/lib}
BUILD_LOG=${UCM_SETUP_BUILD_LOG:-/var/log/ucm/fips-build.log}
SYSTEMD_RUN=${UCM_SETUP_SYSTEMD_RUN:-/run/systemd/system}
# Present while the last UCM_FIPS_BUILD=1 build failed: rpm reports success despite a failed %post
BUILD_FAILED=${BUILD_LOG%.log}.failed
RUST_MIN=1.83
GUARDED_VENV="" GUARDED_TMP="" SERVICE_STOPPED="" VENV_BUILDING="" HAD_VENV=""

say() { echo "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

# own <op> <path> ...: the only way root touches a file in /etc/ucm, /opt/ucm/data or /var/log/ucm,
# directories the service account owns. Everything goes through descriptors: a link there is never
# followed, a file is only ever replaced by a new one renamed over it within its directory.
#   write <path> <mode> [<user>:<group> | copy]  stdin becomes a new file (root's unless an owner is
#       given); copy: created at its own name, stdin also copied to stdout (a build log read live)
#   replace <path> [<mode>]   stdin replaces a regular file, keeping its owner and (unless given) mode
#   read <path>               a regular file to stdout; nothing for an absent one, an error for a link
#   (read, replace, mode and chown-tree never touch a regular file with a second name, a hard link)
#   mode <path> <mode> [link-ok]  fchmod of a regular file or directory (a final / follows the path
#       itself); link-ok: a link is left as it is
#   chown-tree <dir>/ <user>:<group> [<entry>...]  the directory, then what it holds, links themselves;
#       .ucm-archive-* and the listed entries (paths under <dir>) are skipped with what they hold;
#       given to root, group and other write and set-id bits are also removed
# UCM_PYTHON: the interpreter the package requires (python3.12 on EL9, where python3 may be absent)
OWN_PY='
import grp, os, pwd, signal, stat, sys
op, path, args = sys.argv[1], sys.argv[2], sys.argv[3:]
signal.signal(signal.SIGPIPE, signal.SIG_DFL)
ARCHIVE = ".ucm-archive-"

def fail(why):
    sys.stderr.write("ERROR: %s: %s\n" % (path, why))
    sys.exit(3)

def ids(spec):
    u, g = spec.split(":", 1)
    return (int(u) if u.isdigit() else pwd.getpwnam(u).pw_uid,
            int(g) if g.isdigit() else grp.getgrnam(g).gr_gid)

def parent():
    head, name = os.path.split(path)
    if not name:
        fail("no file name")
    # The directory itself may be a link an operator laid (data on another disk): only its entries are not
    return os.open(head or ".", os.O_RDONLY | os.O_DIRECTORY), name

def single(st):
    # A second name of a root file (a hard link the account laid) is never read, replaced or changed
    if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
        fail("a hard link to another file")
    return st

def entry(dirfd, name):
    try:
        st = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(st.st_mode):
        fail("a symbolic link or not a regular file")
    return single(st)

def copy(src, dst, echo=False):
    for chunk in iter(lambda: src.read1(1 << 16), b""):
        dst.write(chunk)
        dst.flush()
        if echo:
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()

def new_file(dirfd, name, mode, owner):
    for _ in range(100):
        tmp = ".%s.%s" % (name, os.urandom(6).hex())
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dirfd)
            break
        except FileExistsError:
            continue
    else:
        fail("no temporary name left")
    try:
        with os.fdopen(fd, "wb") as f:
            copy(sys.stdin.buffer, f)
            if owner:
                os.fchown(f.fileno(), *owner)
            os.fchmod(f.fileno(), mode)
            os.fsync(f.fileno())
        os.rename(tmp, name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
    except BaseException:
        try:
            os.unlink(tmp, dir_fd=dirfd)
        except OSError:
            pass
        raise

if op == "write":
    dirfd, name = parent()
    mode, extra = int(args[0], 8), args[1] if len(args) > 1 else ""
    if extra != "copy":
        new_file(dirfd, name, mode, ids(extra) if extra else None)
        sys.exit(0)
    try:
        os.unlink(name, dir_fd=dirfd)
    except FileNotFoundError:
        pass
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dirfd)
    os.fchmod(fd, mode)
    with os.fdopen(fd, "wb") as f:
        copy(sys.stdin.buffer, f, echo=True)
elif op == "replace":
    dirfd, name = parent()
    st = entry(dirfd, name)
    if st is None:
        fail("not found")
    mode = int(args[0], 8) if args else stat.S_IMODE(st.st_mode) & 0o777
    new_file(dirfd, name, mode, (st.st_uid, st.st_gid))
elif op == "read":
    dirfd, name = parent()
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dirfd)
    except FileNotFoundError:
        sys.exit(0)
    except OSError:
        fail("a symbolic link or not a regular file")
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(single(os.fstat(f.fileno())).st_mode):
            fail("not a regular file")
        copy(f, sys.stdout.buffer)
elif op == "mode":
    mode, link_ok = int(args[0], 8), args[1:] == ["link-ok"]
    if path.endswith("/"):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    else:
        dirfd, name = parent()
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dirfd)
        except OSError:
            if link_ok and os.path.islink(path):
                sys.exit(0)
            fail("a symbolic link or not a regular file or directory")
    st = single(os.fstat(fd))
    if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
        fail("not a regular file or directory")
    os.fchmod(fd, mode)
elif op == "chown-tree":
    uid, gid = ids(args[0])
    skip = set(os.path.normpath(a) for a in args[1:])
    # Given to root, a tree root runs from: no group or other account writes it, no set-id bit stays
    strip = 0o6022 if uid == 0 else 0
    try:
        top = os.open(path, os.O_RDONLY | os.O_DIRECTORY | (0 if path.endswith("/") else os.O_NOFOLLOW))
    except OSError:
        fail("a symbolic link or not a directory")

    def restrict(fd):
        mode = stat.S_IMODE(os.fstat(fd).st_mode)
        if mode & strip:
            os.fchmod(fd, mode & ~strip)

    def warn(rel, why):
        sys.stderr.write("WARNING: %s: %s\n" % (os.path.normpath(os.path.join(path, rel)), why))

    def give(dirfd, rel, n):
        """Changes entry n of dirfd; returns the descriptor of a directory to walk next, or None."""
        try:
            st = os.stat(n, dir_fd=dirfd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        fd = None
        if stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode):
            isdir = stat.S_ISDIR(st.st_mode)
            try:
                # A link laid since is refused by O_NOFOLLOW: only the entry itself is changed then
                fd = os.open(n, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOCTTY
                             | (os.O_DIRECTORY if isdir else 0), dir_fd=dirfd)
            except FileNotFoundError:
                return None
            except OSError as e:
                if isdir:
                    # Swapped since it was listed (the account owns it), or out of descriptors
                    warn(rel, "changed while walked (%s), left as it is" % e.strerror)
                    return None
        walk = False
        try:
            if fd is not None:
                st = os.fstat(fd)
            if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
                warn(rel, "a hard link, left as it is")
                return None
            if fd is not None and stat.S_ISREG(st.st_mode):
                os.fchown(fd, uid, gid)
            else:
                os.chown(n, uid, gid, dir_fd=dirfd, follow_symlinks=False)
            if fd is not None:
                restrict(fd)
            walk = fd is not None and stat.S_ISDIR(st.st_mode)
            return fd if walk else None
        except FileNotFoundError:
            return None
        finally:
            if fd is not None and not walk:
                os.close(fd)

    os.fchown(top, uid, gid)
    restrict(top)
    # Depth first, each directory listed through the descriptor it was opened by, never by its name
    stack = [(top, ".", None)]
    while stack:
        dirfd, where, names = stack.pop()
        if names is None:
            try:
                names = iter(os.listdir(dirfd))
            except OSError as e:
                warn(where, "not walked (%s)" % e.strerror)
                names = iter(())
        for n in names:
            rel = os.path.normpath(os.path.join(where, n))
            if n.startswith(ARCHIVE) or rel in skip:
                continue
            sub = give(dirfd, rel, n)
            if sub is not None:
                stack += [(dirfd, where, names), (sub, rel, None)]
                break
        else:
            os.close(dirfd)
else:
    fail("unknown operation " + op)
'
own() { "${UCM_PYTHON:-python3}" -I -c "$OWN_PY" "$@"; }

mark_build() { printf '%s\n' "$1" | own write "$BUILD_FAILED" 644; }

# Last value assigned to $2 in env file $1, unquoted; empty when unset.
env_value() {
    [ -f "$1" ] || return 0
    own read "$1" | sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$2[[:space:]]*=[[:space:]]*//p" \
        | tail -n 1 | sed -E 's/[[:space:]]+$//; s/^"(.*)"$/\1/; s/^'"'"'(.*)'"'"'$/\1/'
}

env_has() { [ -n "$(env_value "$1" "$2")" ]; }

is_true() {
    case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) return 0 ;;
    esac
    return 1
}

# /etc/ucm is the service account's: a ucm.env it replaced by a link or by anything but a file is
# refused before root reads it for a write; root then reads and replaces it only through own
env_check() {
    if [ -L "$1" ] || { [ -e "$1" ] && [ ! -f "$1" ]; }; then
        die "$1 is a symbolic link or not a regular file: replace it with a regular file, then install again"
    fi
}

# ENV_TEXT: the whole of env file $1, read once; a file that cannot be read stops here, before a write
env_read() {
    local text
    text=$(own read "$1" && printf x) || die "could not read $1"
    ENV_TEXT=${text%x}
}

# Whether a line of ENV_TEXT matches the extended regular expression $1
env_grep() { printf '%s' "$ENV_TEXT" | grep -Eq "$1"; }

# Appends KEY=VALUE, starting a new line if the file does not end with one.
env_append() {
    env_read "$1"
    {
        printf '%s' "$ENV_TEXT"
        [[ -z $ENV_TEXT || $ENV_TEXT == *$'\n' ]] || echo
        printf '%s=%s\n' "$2" "$3"
    } | own replace "$1"
}

# Appends KEY=VALUE unless a line already assigns KEY.
env_ensure() {
    env_check "$1"
    env_read "$1"
    env_grep "^$2=" || env_append "$1" "$2" "$3"
}

# Sets a key that has no value: an empty assignment (KEY=, KEY="") is filled in place.
env_fill() {
    local re="^[[:space:]]*(export[[:space:]]+)?$2[[:space:]]*=[[:space:]]*(\"\"|'')?[[:space:]]*\$"
    env_read "$1"
    if env_grep "$re"; then
        # Builtins only: the value is a secret and must not appear in a process's argv
        local line
        while IFS= read -r line || [ -n "$line" ]; do
            [[ $line =~ $re ]] && line="$2=$3"
            printf '%s\n' "$line"
        done < <(printf '%s' "$ENV_TEXT") | own replace "$1"
    else
        env_append "$1" "$2" "$3"
    fi
}

# Removes the public default older packages wrote: the account exists, a database reset
# then generates a password instead of reusing it. A value the operator chose stays.
env_drop_legacy_admin_password() {
    local re='^[[:space:]]*(export[[:space:]]+)?INITIAL_ADMIN_PASSWORD[[:space:]]*=[[:space:]]*("changeme123"|'"'changeme123'"'|changeme123)[[:space:]]*$'
    env_read "$1"
    env_grep "$re" || return 0
    local line
    while IFS= read -r line || [ -n "$line" ]; do
        [[ $line =~ $re ]] || printf '%s\n' "$line"
    done < <(printf '%s' "$ENV_TEXT") | own replace "$1"
}

fips_requested() {
    is_true "${UCM_FIPS_BUILD:-}" || is_true "$(env_value "$1" UCM_FIPS_BUILD)"
}

os_field() {
    [ -r "$OS_RELEASE" ] || return 0
    sed -n -E "s/^$1=//p" "$OS_RELEASE" | tail -n 1 | sed -E 's/^"(.*)"$/\1/'
}

# Prints el9, ubuntu2404 or nothing for an unsupported host.
fips_distro() {
    local id like ver
    id=$(os_field ID); like=" $(os_field ID_LIKE) "; ver=$(os_field VERSION_ID)
    if [ "$id" != fedora ] && { case "$id" in rhel|almalinux|rocky|centos) true ;; *) false ;; esac \
            || case "$like" in *" rhel "*) true ;; *) false ;; esac; } \
            && [ "${ver%%.*}" = 9 ]; then
        echo el9
    elif [ "$id" = ubuntu ] && [ "$ver" = 24.04 ]; then
        echo ubuntu2404
    fi
}

install_hint() {
    case "$1" in
        el9)
            if [ "$(os_field ID)" = rhel ]; then
                say "  sudo subscription-manager repos --enable codeready-builder-for-rhel-9-\$(arch)-rpms"
            else
                say "  sudo dnf config-manager --set-enabled crb"
            fi
            say "  sudo dnf install -y python3.12-devel gcc pkgconf-pkg-config libpq-devel libxml2-devel libxslt-devel openssl-devel xmlsec1-devel xmlsec1-openssl libtool-ltdl-devel rust cargo"
            ;;
        ubuntu2404)
            say "  sudo apt-get install -y gcc pkg-config python3-dev python3-venv libpq-dev libxml2-dev libxslt1-dev zlib1g-dev libssl-dev libxmlsec1-dev libxmlsec1t64-openssl rustc-1.91 cargo-1.91"
            ;;
    esac
}

retry_hint() {
    case "$1" in
        deb) say "then finish the installation with: sudo dpkg --configure -a" ;;
        rpm) say "then reinstall the package: sudo dnf reinstall ./ucm-el9-<version>-1.el9.noarch.rpm" ;;
        update) say "then run the update again." ;;
    esac
}

# Newest directory holding both cargo and rustc >= RUST_MIN, PATH first.
find_rust() {
    local best="" best_ver="" dir ver cand
    for cand in "$(command -v rustc 2>/dev/null || true)" "$RUST_ROOT"/rust-1.*/bin/rustc; do
        [ -n "$cand" ] && [ -x "$cand" ] || continue
        dir=$(dirname "$cand")
        [ -x "$dir/cargo" ] || continue
        ver=$("$cand" --version 2>/dev/null | awk '{print $2}')
        [ -n "$ver" ] || continue
        if [ -z "$best_ver" ] || [ "$(printf '%s\n%s\n' "$best_ver" "$ver" | sort -V | tail -n 1)" = "$ver" ]; then
            best=$dir; best_ver=$ver
        fi
    done
    [ -n "$best" ] || return 1
    [ "$(printf '%s\n%s\n' "$RUST_MIN" "$best_ver" | sort -V | head -n 1)" = "$RUST_MIN" ] || return 1
    echo "$best"
}

has_shared_lib() {
    local ldconfig
    ldconfig=$(command -v ldconfig 2>/dev/null || echo /sbin/ldconfig)
    "$ldconfig" -p 2>/dev/null | grep -q "$1"
}

# Fails with the distribution's install command when a build tool is missing;
# prints the Rust directory to put first in PATH.
cmd_check_build_tools() {
    local python=$1 format=$2 distro missing="" rust tool
    distro=$(fips_distro)
    if [ -z "$distro" ]; then
        echo "ERROR: UCM_FIPS_BUILD=1 is supported on RHEL, AlmaLinux and Rocky Linux 9 and on Ubuntu 24.04;" >&2
        echo "this host is $(os_field PRETTY_NAME || true). Remove UCM_FIPS_BUILD from /etc/ucm/ucm.env to install the standard build." >&2
        exit 1
    fi
    "$python" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null || missing="$missing python>=3.12"
    "$python" -c 'import os, sys, sysconfig; sys.exit(not os.path.isfile(os.path.join(sysconfig.get_paths()["include"], "Python.h")))' 2>/dev/null \
        || missing="$missing Python.h"
    "$python" -c 'import ensurepip, venv' 2>/dev/null || missing="$missing python-venv"
    for tool in gcc pkg-config pg_config xml2-config xslt-config xmlsec1-config; do
        command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
    done
    if command -v pkg-config >/dev/null 2>&1; then
        pkg-config --exists openssl 2>/dev/null || missing="$missing openssl-headers"
    fi
    has_shared_lib 'libxmlsec1-openssl\.so' || missing="$missing libxmlsec1-openssl"
    # Without cargo, the maturin build backend silently downloads a whole Rust toolchain.
    rust=$(find_rust) || missing="$missing cargo/rustc>=$RUST_MIN"
    if [ -n "$missing" ]; then
        {
            echo "ERROR: UCM_FIPS_BUILD=1 compiles cryptography, psycopg, lxml and xmlsec against the system OpenSSL,"
            echo "and this host lacks:$missing"
            echo "Install the build tools first:"
            install_hint "$distro"
            retry_hint "$format"
        } >&2
        exit 1
    fi
    echo "$rust"
}

cmd_env() {
    local file=$1 data=$2 had_secret="" key
    env_check "$file"
    # Restricted from the start
    [ -e "$file" ] || own write "$file" 600 < /dev/null
    env_has "$file" SECRET_KEY && had_secret=1
    # Restricted before the first secret is written
    env_has "$file" SECRET_KEY || own mode "$file" 600
    env_has "$file" SECRET_KEY || env_fill "$file" SECRET_KEY "$(openssl rand -hex 32)"
    # A file the package never completed (written by hand before the install) gets the defaults too.
    if [ -z "$had_secret" ]; then
        env_has "$file" DATABASE_PATH || env_fill "$file" DATABASE_PATH "$data/ucm.db"
        env_has "$file" DATA_DIR || env_fill "$file" DATA_DIR "$data"
        env_has "$file" HTTPS_PORT || env_fill "$file" HTTPS_PORT 8443
        env_has "$file" HTTP_PROTOCOL_PORT || env_fill "$file" HTTP_PROTOCOL_PORT 8080
        env_has "$file" LOG_LEVEL || env_fill "$file" LOG_LEVEL INFO
        echo new
    fi
    env_drop_legacy_admin_password "$file"
    if is_true "${UCM_FIPS_BUILD:-}" && ! is_true "$(env_value "$file" UCM_FIPS_BUILD)"; then
        env_read "$file"
        if env_grep '^[[:space:]]*(export[[:space:]]+)?UCM_FIPS_BUILD[[:space:]]*='; then
            printf '%s' "$ENV_TEXT" | sed -E 's/^[[:space:]]*(export[[:space:]]+)?UCM_FIPS_BUILD[[:space:]]*=.*/UCM_FIPS_BUILD=1/' \
                | own replace "$file"
        else
            env_append "$file" UCM_FIPS_BUILD 1
        fi
    fi
    return 0
}

# requirements.txt with psycopg[c] instead of psycopg[binary] (and xmlsec pinned on EL9), into $2.
fips_requirements() {
    [ "$(grep -c '^psycopg\[binary\]' "$1")" = 1 ] || die "$1: psycopg[binary] not found once"
    sed 's/^psycopg\[binary\]/psycopg[c]/' "$1" > "$2"
    if [ "$(fips_distro)" = el9 ]; then
        # python-xmlsec 1.3.14 and later do not build against xmlsec1 1.2.29
        [ "$(grep -c '^xmlsec[<>=]' "$2")" = 1 ] || die "$1: xmlsec not found once"
        sed -i 's/^xmlsec[<>=].*/xmlsec==1.3.13/' "$2"
    fi
}

# Same steps as the standard install, with the OpenSSL-linked packages from source.
build_fips_venv() {
    local python=$1 venv=$2 reqs=$3 prompt=$4
    "$python" -m venv "$venv" --prompt "$prompt" &&
    "$venv/bin/pip" install --upgrade pip &&
    "$venv/bin/pip" install --no-binary cryptography,psycopg-c,lxml,xmlsec -r "$reqs" &&
    "$venv/bin/pip" install --no-deps pyjks==20.0.0
}

# A venv the service can start: an interrupted build leaves one without gunicorn or python.
venv_ok() {
    [ -x "$1/bin/gunicorn" ] && "$1/bin/python" -c '' </dev/null >/dev/null 2>&1
}

# venv_ok, plus: python takes the directory as its venv and gunicorn's shebang resolves.
venv_starts() {
    venv_ok "$1" &&
    "$1/bin/python" -c 'import os, sys; sys.exit(os.path.realpath(sys.prefix) != os.path.realpath(sys.argv[1]))' \
        "$1" </dev/null >/dev/null 2>&1 &&
    "$1/bin/gunicorn" --version </dev/null >/dev/null 2>&1
}

# Venv $1 to be moved to $2: rewrites its path where venv and pip write it, pyvenv.cfg and the text
# files of bin/ (shebangs, activate*). Binaries are skipped (-I): a shorter path would corrupt them.
relocate_venv() {
    local dir=$1 from=$1 to=$2 pat rep f
    pat=$(printf '%s\n' "$from" | sed 's/[][\.*^$/]/\\&/g')
    rep=$(printf '%s\n' "$to" | sed 's/[\&/]/\\&/g')
    for f in "$dir/pyvenv.cfg" "$dir"/bin/*; do
        [ -f "$f" ] && [ ! -L "$f" ] && grep -qIF -e "$from" "$f" || continue
        sed -i "s/$pat/$rep/g" "$f"
    done
    ! grep -rqsIF -e "$from" "$dir/pyvenv.cfg" "$dir/bin"
}

# Every OpenSSL the venv loads must be the system one.
verify_fips_venv() {
    "$1/bin/python" - <<'PY'
import glob, importlib.metadata as md, os, ssl, subprocess, sys, sysconfig
import _hashlib
from cryptography.hazmat.backends.openssl.backend import backend

venv = os.path.realpath(sys.prefix)
problems = []
if backend.openssl_version_text() != ssl.OPENSSL_VERSION:
    problems.append(f'cryptography uses {backend.openssl_version_text()}, not the system {ssl.OPENSSL_VERSION}')
try:
    md.distribution('psycopg-binary')
    problems.append('psycopg-binary is installed')
except md.PackageNotFoundError:
    pass
site = sysconfig.get_paths()['platlib']
modules = {
    'cryptography': glob.glob(f'{site}/cryptography/hazmat/bindings/_rust*.so'),
    'psycopg': glob.glob(f'{site}/psycopg_c/pq*.so'),
    'hashlib': [getattr(_hashlib, '__file__', None) or sys.executable],
}
for name, files in modules.items():
    if not files:
        problems.append(f'{name}: extension module not found')
    for path in files:
        out = subprocess.run(['ldd', path], capture_output=True, text=True).stdout
        libs = [l.split() for l in out.splitlines() if 'libcrypto' in l or 'libssl' in l]
        if not any('libcrypto' in l[0] for l in libs):
            problems.append(f'{name}: not linked to a shared libcrypto')
        for l in libs:
            target = l[2] if len(l) > 2 and l[1] == '=>' else l[0]
            if target == 'not' or os.path.realpath(target).startswith(venv + os.sep):
                problems.append(f'{name}: {" ".join(l)}')
for root, _dirs, names in os.walk(venv):
    problems += [f'bundled {os.path.join(root, n)}' for n in names if n.startswith(('libssl', 'libcrypto'))]
import lxml.etree, psycopg, xmlsec  # noqa: E401,F401
if psycopg.pq.__impl__ != 'c':
    problems.append(f'psycopg uses its {psycopg.pq.__impl__} implementation, not the one built here')
if problems:
    print('\n'.join(problems), file=sys.stderr)
    sys.exit(1)
print(f'cryptography, hashlib and psycopg use the system {ssl.OPENSSL_VERSION}')
PY
}

# The new venv is built in venv.next while ucm runs. Until it is in place and starts, any exit
# (failure or signal) drops it, keeps or puts back the previous one, and starts ucm again if it was
# stopped here; on success the package script starts it at the end.
guard_venv() {
    GUARDED_VENV=$1 GUARDED_TMP=${2:-}
    trap recover_venv EXIT
    # Trapped, a signal is handled once pip has exited: recover_venv never races a dying pip
    trap 'exit 129' HUP; trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 141' PIPE
}

recover_venv() {
    # Runs to the end despite a repeated Ctrl-C or a session gone (every write failing or raising SIGPIPE)
    trap '' HUP INT TERM PIPE
    set +e
    local venv=$GUARDED_VENV
    [ -z "$GUARDED_TMP" ] || rm -rf "$GUARDED_TMP"
    case $VENV_BUILDING in
        next) rm -rf "$venv.next"
              [ ! -e "$venv" ] || say "Kept the previous Python environment." >&2 ;;
        swap) rm -rf "$venv.next"
              if [ -e "$venv.prev" ]; then
                  rm -rf "$venv" && mv -T "$venv.prev" "$venv" && say "Restored the previous Python environment." >&2
              # A first install has no previous venv: an unchecked one must not pass venv-ok
              elif [ -z "$HAD_VENV" ]; then
                  rm -rf "$venv"
              fi ;;
        *) if [ -e "$venv.prev" ] && ! venv_ok "$venv"; then rm -rf "$venv" && mv -T "$venv.prev" "$venv"; fi ;;
    esac
    if [ -n "$SERVICE_STOPPED" ] && venv_ok "$venv"; then
        say "Starting UCM again..." >&2
        # Stopped here, not crashed: not counted by the start limit
        systemctl reset-failed ucm 2>/dev/null
        systemctl start ucm
    fi
}

# Resolves what an interrupted run left behind (venv.prev, venv.next), then marks the build started.
clear_leftovers() {
    if [ -e "$1.prev" ] && ! venv_ok "$1"; then
        rm -rf "$1" && mv -T "$1.prev" "$1"
    fi
    rm -rf "$1.prev" "$1.next"
    VENV_BUILDING=next
}

stop_service() {
    # Skipped in a chroot or container without systemd
    if [ -d "$SYSTEMD_RUN" ] && systemctl is-active --quiet ucm; then
        say "Stopping UCM to switch to its new Python environment..."
        SERVICE_STOPPED=1
        systemctl stop ucm || say "WARNING: could not stop UCM; switching its environment anyway"
    fi
}

# venv.next becomes venv (the previous one venv.prev); ucm is stopped for this step only.
switch_venv() {
    local venv=$1
    # From here venv.next/bin/pip runs the interpreter of $venv: no pip call after this line
    relocate_venv "$venv.next" "$venv" || die "could not rewrite the paths of the new Python environment"
    stop_service
    [ ! -e "$venv" ] || HAD_VENV=1
    VENV_BUILDING=swap
    [ -z "$HAD_VENV" ] || mv -T "$venv" "$venv.prev"
    mv -T "$venv.next" "$venv"
    venv_starts "$venv" || die "the new Python environment does not start"
}

cmd_venv() {
    local home=$1 python=$2 format=$3 envfile=$4 venv=$1/venv rust reqs="" work built
    local had_kerberos=""

    # pyspnego[kerberos] is optional and admin-installed: the venv is recreated on every
    # upgrade, so it is reinstalled when it was there, or what 2.x used for MS CA Kerberos:
    # requests-kerberos (certsrv) or pykerberos alone (pywinrm[kerberos], the WinRM channel)
    if [ -x "$venv/bin/pip" ]; then
        "$venv/bin/pip" show gssapi >/dev/null 2>&1 && had_kerberos=1 || true
        "$venv/bin/pip" show requests-kerberos >/dev/null 2>&1 && had_kerberos=1 || true
        "$venv/bin/pip" show pykerberos >/dev/null 2>&1 && had_kerberos=1 || true
    fi

    if fips_requested "$envfile"; then
        mkdir -p "$(dirname "$BUILD_LOG")"
        mark_build "build tools missing"
        rust=$(cmd_check_build_tools "$python" "$format")
        export PATH="$rust:$PATH" RUSTC="$rust/rustc" CARGO="$rust/cargo"
        say "UCM_FIPS_BUILD=1: building cryptography, psycopg, lxml and xmlsec against the system OpenSSL"
        say "(about 5 minutes the first time, then from pip's wheel cache; log: $BUILD_LOG)..."
        # Root's own copy of the log, read back here: the one in BUILD_LOG is the service account's to swap
        work=$(mktemp -d)
        reqs=$work/requirements.txt
        guard_venv "$venv" "$work"
        fips_requirements "$home/requirements.txt" "$reqs"
        clear_leftovers "$venv"
        mark_build "build failed"
        set +e
        { build_fips_venv "$python" "$venv.next" "$reqs" "${venv##*/}" && verify_fips_venv "$venv.next"; } 2>&1 \
            | own write "$BUILD_LOG" 644 copy > "$work/build.log"
        built=("${PIPESTATUS[@]}")
        set -e
        [ "${built[1]}" = 0 ] || die "could not write $BUILD_LOG"
        if [ "${built[0]}" != 0 ]; then
            tail -n 25 "$work/build.log" >&2 || true
            echo "ERROR: the UCM_FIPS_BUILD=1 build failed (full log: $BUILD_LOG)." >&2
            echo "Fix the cause, or remove UCM_FIPS_BUILD from $envfile for the standard build, and" >&2
            retry_hint "$format" >&2
            exit 1
        fi
        # Built: from here the marker only says the switch did not happen
        mark_build "switch not completed"
        tail -n 1 "$work/build.log" || true
        rm -rf "$work"
    else
        guard_venv "$venv"
        clear_leftovers "$venv"
        "$python" -m venv "$venv.next" --prompt "${venv##*/}"
        "$venv.next/bin/pip" install --quiet --upgrade pip
        "$venv.next/bin/pip" install --quiet -r "$home/requirements.txt"
        # --no-deps keeps out twofish, an sdist-only dependency UCM never uses (see requirements.txt)
        "$venv.next/bin/pip" install --quiet --no-deps pyjks==20.0.0
    fi

    if [ -n "$had_kerberos" ]; then
        say "Reinstalling pyspnego[kerberos] (Kerberos support was present before upgrade)..."
        "$venv.next/bin/pip" install --quiet 'pyspnego[kerberos]' || \
            say "WARNING: pyspnego[kerberos] reinstall failed (needs libkrb5-dev/gcc), Kerberos auth to a Microsoft CA and Autoenrollment's Kerberos/SPNEGO binding are unavailable until 'pip install pyspnego[kerberos]' is run manually in $venv"
    fi

    switch_venv "$venv"
    # In place and starting: the previous venv is no longer needed (flag first, so no exit drops the new one)
    VENV_BUILDING=""
    [ -z "$reqs" ] || rm -f "$BUILD_FAILED"
    rm -rf "$venv.prev"
    trap - EXIT HUP INT TERM PIPE
}

run_preflight() {
    local home=$1 envfile=$2 data=$3 user=$4 db out rc
    db=$(env_value "$envfile" DATABASE_PATH); db=${db:-$data/ucm.db}
    if ! env_has "$envfile" DATABASE_URL && [ ! -f "$db" ]; then
        say "FIPS readiness check skipped: no database yet."
        return 0
    fi
    say "FIPS readiness check (read-only):"
    rc=0
    out=$(cd "$home/backend" && runuser -u "$user" -- "$home/venv/bin/python" -m scripts.fips_preflight 2>&1) || rc=$?
    printf '%s\n' "$out" | head -n 40 | sed 's/^/  /'
    [ "$(printf '%s\n' "$out" | wc -l)" -le 40 ] || say "  ..."
    [ "$rc" = 0 ] || say "Review the findings above, then run again: cd $home/backend && sudo -u $user $home/venv/bin/python -m scripts.fips_preflight"
}

cmd_fips_finish() {
    local home=$1 envfile=$2 data=$3 user=$4 flag active
    flag=$(cat "$FIPS_FLAG" 2>/dev/null || true)
    env_check "$envfile"
    if ! fips_requested "$envfile"; then
        [ "$flag" != 1 ] || say "Note: host is in FIPS mode: set UCM_FIPS_BUILD=1 in $envfile and reinstall, to link UCM to the system OpenSSL."
        return 0
    fi
    if [ "$flag" = 1 ]; then
        env_read "$envfile"
        env_grep '^[[:space:]]*(export[[:space:]]+)?UCM_FIPS[[:space:]]*=' || env_append "$envfile" UCM_FIPS 1
        # The check the service runs at startup with UCM_FIPS=1
        active=$(cd "$home/backend" && "$home/venv/bin/python" -c 'import fips_mode; print(int(fips_mode.provider_active()))' 2>/dev/null || echo 0)
        if [ "$active" = 1 ]; then
            say "Host FIPS mode: the system OpenSSL FIPS provider is active for UCM (UCM_FIPS=$(env_value "$envfile" UCM_FIPS))."
        else
            say "WARNING: the host is in FIPS mode but the FIPS provider is not active for UCM's Python; with UCM_FIPS=1 the service refuses to start."
        fi
    else
        say "The host is not in FIPS mode: UCM runs in standard mode on the system OpenSSL."
        case "$(fips_distro)" in
            el9) say "To enable it: sudo fips-mode-setup --enable, reboot, then reinstall the package." ;;
            ubuntu2404) say "To enable it (Ubuntu Pro): sudo pro enable fips (the certified binaries), reboot, then reinstall the package." ;;
        esac
        ! is_true "$(env_value "$envfile" UCM_FIPS)" || say "WARNING: UCM_FIPS=1 is set in $envfile: the service refuses to start until the host is in FIPS mode."
    fi
    run_preflight "$home" "$envfile" "$data" "$user"
}

# Run by the updater before installing: a FIPS build that cannot happen is refused up front.
cmd_update_precheck() {
    local home=$1 envfile=$2 python=python3
    fips_requested "$envfile" || return 0
    [ ! -x "$home/venv/bin/python" ] || python=$(readlink -f "$home/venv/bin/python")
    cmd_check_build_tools "$python" update > /dev/null
    # A new attempt starts: a failure marker left by an earlier one is not this update's
    rm -f "$BUILD_FAILED"
}

cmd_fips_build_ok() {
    fips_requested "$1" && [ -e "$BUILD_FAILED" ] || return 0
    if [ "$(own read "$BUILD_FAILED" 2>/dev/null)" = "switch not completed" ]; then
        echo "the UCM_FIPS_BUILD=1 update did not complete after the build (log: $BUILD_LOG); the previous environment was kept" >&2
    else
        echo "the UCM_FIPS_BUILD=1 build failed (log: $BUILD_LOG); the previous environment was kept" >&2
    fi
    return 1
}

# This host's name: hostname is not installed everywhere (Fedora 43 container images), uname
# is coreutils
host_name() {
    local name
    name=$(hostname -f 2>/dev/null) || name=""
    [ -n "$name" ] || name=$(hostname 2>/dev/null) || name=""
    [ -n "$name" ] || name=$(uname -n 2>/dev/null) || name=""
    printf '%s\n' "${name:-localhost}"
}

# https-cert <data dir> <user> <group>: a self-signed HTTPS certificate when the data has none. The data
# is the service account's: generated in root's own directory, then put in place without following a link
cmd_https_cert() {
    local data=$1 user=$2 group=$3 host san ip work
    [ ! -f "$data/https_cert.pem" ] || return 0
    say "Generating HTTPS certificate..."
    host=$(host_name)
    san="DNS:${host},DNS:localhost,IP:127.0.0.1"
    for ip in $(hostname -I 2>/dev/null); do san="$san,IP:$ip"; done
    work=$(mktemp -d)
    trap "rm -rf -- $(printf %q "$work")" EXIT
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 -keyout "$work/key.pem" -out "$work/cert.pem" \
        -subj "/CN=${host}/O=UCM/OU=PKI" -addext "subjectAltName=${san}" 2>/dev/null
    own write "$data/https_key.pem" 600 "$user:$group" < "$work/key.pem"
    own write "$data/https_cert.pem" 644 "$user:$group" < "$work/cert.pem"
    rm -rf -- "$work"
    trap - EXIT
}

# Post-install banner; IPv6 addresses are bracketed in the URLs.
cmd_banner() {
    local envfile=$1 pkg=$2 host port ips ip pwfile data user
    # Cosmetic: a failed lookup (no hostname binary) must not cut it short
    set +e
    pwfile=$(env_value "$envfile" INITIAL_ADMIN_PASSWORD_FILE)
    data=$(env_value "$envfile" DATA_DIR)
    echo ""
    host=$(host_name)
    port=$(env_value "$envfile" HTTPS_PORT 2>/dev/null)
    port=${port:-8443}
    ips=$(hostname -I 2>/dev/null | xargs)
    echo ""
    echo "============================================"
    echo " UCM INSTALLED"
    echo "============================================"
    echo ""
    echo " Access:   https://${host}:${port}"
    for ip in $ips; do
        case $ip in *:*) ip="[$ip]" ;; esac
        echo "            https://${ip}:${port}"
    done
    echo ""
    # Never the value: where it comes from, or where the first start writes it
    user=$(env_value "$envfile" INITIAL_ADMIN_USERNAME)
    echo " Admin:    ${user:-admin}"
    if [ -n "$pwfile" ] && env_has "$envfile" INITIAL_ADMIN_PASSWORD; then
        # The application refuses to start then: which one was meant cannot be guessed
        echo " Password: INITIAL_ADMIN_PASSWORD and INITIAL_ADMIN_PASSWORD_FILE are both set"
        echo "           in $envfile: the start is refused, keep only one"
    elif [ -n "$pwfile" ]; then
        echo " Password: the one you provided (INITIAL_ADMIN_PASSWORD_FILE=$pwfile)"
    elif env_has "$envfile" INITIAL_ADMIN_PASSWORD; then
        echo " Password: the one you provided (INITIAL_ADMIN_PASSWORD in $envfile)"
    else
        echo " Password: generated at first start, read it with:"
        echo "             sudo cat ${data:-/opt/ucm/data}/initial-admin-password"
        echo "           It must be changed at first login, which removes the file."
    fi
    echo " Config:   $envfile"
    echo ""
    echo " Optional packages:"
    if [ "$pkg" = deb ]; then
        # Installed in the same apt run, softhsm2 is only unpacked while ucm is configured
        if dpkg-query -W -f='${Status}' softhsm2 2>/dev/null | grep -Eq '^(install|hold) ok (installed|unpacked|half-configured|triggers-(awaited|pending))$'; then
            echo "  [ok] softhsm2 (HSM support)"
        else
            echo "  [ ]  softhsm2 - HSM support (apt install softhsm2)"
        fi
    elif rpm -q softhsm >/dev/null 2>&1; then
        echo "  [ok] softhsm (HSM support)"
    else
        echo "  [ ]  softhsm - HSM support (dnf install softhsm)"
    fi
    echo ""
    echo "============================================"
}

case "${1:-}" in
    env) cmd_env "$2" "$3" ;;
    env-check) env_check "$2" ;;
    env-ensure) env_ensure "$2" "$3" "$4" ;;
    venv-ok) venv_ok "$2/venv" ;;
    venv) cmd_venv "$2" "$3" "$4" "$5" ;;
    fips-finish) cmd_fips_finish "$2" "$3" "$4" "$5" ;;
    fips-requested) fips_requested "$2" ;;
    check-build-tools) cmd_check_build_tools "$2" "$3" ;;
    update-precheck) cmd_update_precheck "$2" "$3" ;;
    fips-build-ok) cmd_fips_build_ok "$2" ;;
    banner) cmd_banner "$2" "$3" ;;
    host-name) host_name ;;
    https-cert) cmd_https_cert "$2" "$3" "$4" ;;
    own) shift; own "$@" ;;
    *) die "usage: $0 env <ucm.env> <data dir> | env-check <ucm.env> | env-ensure <ucm.env> <key> <value>
  | venv <ucm home> <python> <deb|rpm> <ucm.env> | venv-ok <ucm home>
  | fips-finish <ucm home> <ucm.env> <data dir> <user> | fips-requested <ucm.env>
  | check-build-tools <python> <deb|rpm> | update-precheck <ucm home> <ucm.env>
  | fips-build-ok <ucm.env> | banner <ucm.env> <deb|rpm> | host-name
  | https-cert <data dir> <user> <group> | own <op> <path> ..." ;;
esac
