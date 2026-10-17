#!/bin/bash
# Steps shared by the DEB postinst and the RPM %post: ucm.env completion, the
# virtual environment (standard wheels, or built against the system OpenSSL
# with UCM_FIPS_BUILD=1) and the host FIPS state.
#
#   native-setup.sh env <ucm.env> <data dir>
#   native-setup.sh venv <ucm home> <python> <deb|rpm> <ucm.env>
#   native-setup.sh fips-finish <ucm home> <ucm.env> <data dir> <user>
#   native-setup.sh fips-requested <ucm.env>
#   native-setup.sh check-build-tools <python> <deb|rpm>
#   native-setup.sh update-precheck <ucm home> <ucm.env> <deb|rpm>
#   native-setup.sh fips-build-ok <ucm.env>
set -eu

OS_RELEASE=${UCM_SETUP_OS_RELEASE:-/etc/os-release}
FIPS_FLAG=${UCM_SETUP_FIPS_FLAG:-/proc/sys/crypto/fips_enabled}
RUST_ROOT=${UCM_SETUP_RUST_ROOT:-/usr/lib}
BUILD_LOG=${UCM_SETUP_BUILD_LOG:-/var/log/ucm/fips-build.log}
# Present while the last UCM_FIPS_BUILD=1 build failed: rpm reports success despite a failed %post
BUILD_FAILED=${BUILD_LOG%.log}.failed
RUST_MIN=1.83

say() { echo "$*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

# Last value assigned to $2 in env file $1, unquoted; empty when unset.
env_value() {
    [ -f "$1" ] || return 0
    sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$2[[:space:]]*=[[:space:]]*//p" "$1" \
        | tail -n 1 | sed -E 's/[[:space:]]+$//; s/^"(.*)"$/\1/; s/^'"'"'(.*)'"'"'$/\1/'
}

env_has() { [ -n "$(env_value "$1" "$2")" ]; }

is_true() {
    case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) return 0 ;;
    esac
    return 1
}

# Appends KEY=VALUE, starting a new line if the file does not end with one.
env_append() {
    if [ -s "$1" ] && [ -n "$(tail -c 1 "$1")" ]; then
        echo >> "$1"
    fi
    echo "$2=$3" >> "$1"
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
    if [ "$1" = deb ]; then
        say "then finish the installation with: sudo dpkg --configure -a"
    else
        say "then reinstall the package: sudo dnf reinstall ./<the ucm .el9.noarch.rpm file>"
    fi
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
            echo "ERROR: UCM_FIPS_BUILD=1 compiles cryptography, psycopg2, lxml and xmlsec against the system OpenSSL,"
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
    local file=$1 data=$2 had_secret="" added_secret="" key
    touch "$file"
    env_has "$file" SECRET_KEY && had_secret=1
    for key in SECRET_KEY JWT_SECRET_KEY; do
        if ! env_has "$file" "$key"; then
            env_append "$file" "$key" "$(openssl rand -hex 32)"
            added_secret=1
        fi
    done
    # A file the package never completed (written by hand before the install) gets the defaults too.
    if [ -z "$had_secret" ]; then
        env_has "$file" DATABASE_PATH || env_append "$file" DATABASE_PATH "$data/ucm.db"
        env_has "$file" DATA_DIR || env_append "$file" DATA_DIR "$data"
        env_has "$file" HTTPS_PORT || env_append "$file" HTTPS_PORT 8443
        env_has "$file" HTTP_PROTOCOL_PORT || env_append "$file" HTTP_PROTOCOL_PORT 8080
        env_has "$file" LOG_LEVEL || env_append "$file" LOG_LEVEL INFO
        env_has "$file" INITIAL_ADMIN_PASSWORD || env_append "$file" INITIAL_ADMIN_PASSWORD changeme123
        echo new
    fi
    [ -z "$added_secret" ] || chmod 600 "$file"
    if is_true "${UCM_FIPS_BUILD:-}" && ! is_true "$(env_value "$file" UCM_FIPS_BUILD)"; then
        if grep -Eq '^[[:space:]]*(export[[:space:]]+)?UCM_FIPS_BUILD[[:space:]]*=' "$file"; then
            sed -i -E 's/^[[:space:]]*(export[[:space:]]+)?UCM_FIPS_BUILD[[:space:]]*=.*/UCM_FIPS_BUILD=1/' "$file"
        else
            env_append "$file" UCM_FIPS_BUILD 1
        fi
    fi
    return 0
}

# requirements.txt with psycopg2 instead of psycopg2-binary (and xmlsec pinned on EL9), into $2.
fips_requirements() {
    [ "$(grep -c '^psycopg2-binary' "$1")" = 1 ] || die "$1: psycopg2-binary not found once"
    sed 's/^psycopg2-binary/psycopg2/' "$1" > "$2"
    if [ "$(fips_distro)" = el9 ]; then
        # python-xmlsec 1.3.14 and later do not build against xmlsec1 1.2.29
        [ "$(grep -c '^xmlsec[<>=]' "$2")" = 1 ] || die "$1: xmlsec not found once"
        sed -i 's/^xmlsec[<>=].*/xmlsec==1.3.13/' "$2"
    fi
}

# Same steps as the standard install, with the OpenSSL-linked packages from source.
build_fips_venv() {
    local python=$1 venv=$2 reqs=$3
    "$python" -m venv "$venv" &&
    "$venv/bin/pip" install --upgrade pip &&
    "$venv/bin/pip" install --no-binary cryptography,psycopg2,lxml,xmlsec -r "$reqs" &&
    "$venv/bin/pip" install --no-deps pyjks==20.0.0
}

# Every OpenSSL the venv loads must be the system one.
verify_fips_venv() {
    "$1/venv/bin/python" - <<'PY'
import glob, importlib.metadata as md, os, ssl, subprocess, sys, sysconfig
import _hashlib
from cryptography.hazmat.backends.openssl.backend import backend

venv = os.path.realpath(sys.prefix)
problems = []
if backend.openssl_version_text() != ssl.OPENSSL_VERSION:
    problems.append(f'cryptography uses {backend.openssl_version_text()}, not the system {ssl.OPENSSL_VERSION}')
try:
    md.distribution('psycopg2-binary')
    problems.append('psycopg2-binary is installed')
except md.PackageNotFoundError:
    pass
site = sysconfig.get_paths()['platlib']
modules = {
    'cryptography': glob.glob(f'{site}/cryptography/hazmat/bindings/_rust*.so'),
    'psycopg2': glob.glob(f'{site}/psycopg2/_psycopg*.so'),
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
import lxml.etree, psycopg2, xmlsec  # noqa: E401,F401
if problems:
    print('\n'.join(problems), file=sys.stderr)
    sys.exit(1)
print(f'cryptography, hashlib and psycopg2 use the system {ssl.OPENSSL_VERSION}')
PY
}

cmd_venv() {
    local home=$1 python=$2 format=$3 envfile=$4 venv=$1/venv rust reqs
    local had_requests_kerberos="" had_pyspnego_kerberos=""

    # requests-kerberos and pyspnego[kerberos] are optional and admin-installed:
    # the venv is recreated on every upgrade, so reinstall whatever was there.
    if [ -x "$venv/bin/pip" ]; then
        "$venv/bin/pip" show requests-kerberos >/dev/null 2>&1 && had_requests_kerberos=1 || true
        "$venv/bin/pip" show gssapi >/dev/null 2>&1 && had_pyspnego_kerberos=1 || true
    fi

    if fips_requested "$envfile"; then
        mkdir -p "$(dirname "$BUILD_LOG")"
        echo "build tools missing" > "$BUILD_FAILED"
        rust=$(cmd_check_build_tools "$python" "$format")
        export PATH="$rust:$PATH" RUSTC="$rust/rustc" CARGO="$rust/cargo"
        say "UCM_FIPS_BUILD=1: building cryptography, psycopg2, lxml and xmlsec against the system OpenSSL"
        say "(about 5 minutes, log: $BUILD_LOG)..."
        reqs=$(mktemp)
        fips_requirements "$home/requirements.txt" "$reqs"
        rm -rf "$venv.prev"
        [ ! -e "$venv" ] || mv "$venv" "$venv.prev"
        echo "build failed" > "$BUILD_FAILED"
        if ! build_fips_venv "$python" "$venv" "$reqs" > "$BUILD_LOG" 2>&1 \
                || ! verify_fips_venv "$home" >> "$BUILD_LOG" 2>&1; then
            rm -f "$reqs"
            tail -n 25 "$BUILD_LOG" >&2 || true
            rm -rf "$venv"
            [ ! -e "$venv.prev" ] || mv "$venv.prev" "$venv"
            echo "ERROR: the UCM_FIPS_BUILD=1 build failed (full log: $BUILD_LOG); the previous environment was kept." >&2
            echo "Fix the cause, or remove UCM_FIPS_BUILD from $envfile for the standard build, and" >&2
            retry_hint "$format" >&2
            exit 1
        fi
        rm -rf "$venv.prev" "$reqs" "$BUILD_FAILED"
        tail -n 1 "$BUILD_LOG"
    else
        rm -rf "$venv" 2>/dev/null || true
        "$python" -m venv "$venv"
        "$venv/bin/pip" install --quiet --upgrade pip
        "$venv/bin/pip" install --quiet -r "$home/requirements.txt"
        # --no-deps keeps out twofish, an sdist-only dependency UCM never uses (see requirements.txt)
        "$venv/bin/pip" install --quiet --no-deps pyjks==20.0.0
    fi

    if [ -n "$had_requests_kerberos" ]; then
        say "Reinstalling requests-kerberos (was present before upgrade)..."
        "$venv/bin/pip" install --quiet requests-kerberos || \
            say "WARNING: requests-kerberos reinstall failed, Kerberos auth to the upstream CA is unavailable until 'pip install requests-kerberos' is run manually in $venv"
    fi
    if [ -n "$had_pyspnego_kerberos" ]; then
        say "Reinstalling pyspnego[kerberos] (was present before upgrade)..."
        "$venv/bin/pip" install --quiet 'pyspnego[kerberos]' || \
            say "WARNING: pyspnego[kerberos] reinstall failed (needs libkrb5-dev/gcc), Autoenrollment's Kerberos/SPNEGO binding is unavailable until 'pip install pyspnego[kerberos]' is run manually in $venv"
    fi
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
    if ! fips_requested "$envfile"; then
        [ "$flag" != 1 ] || say "Note: host is in FIPS mode: set UCM_FIPS_BUILD=1 in $envfile and reinstall, to link UCM to the system OpenSSL."
        return 0
    fi
    if [ "$flag" = 1 ]; then
        grep -Eq '^[[:space:]]*(export[[:space:]]+)?UCM_FIPS[[:space:]]*=' "$envfile" || env_append "$envfile" UCM_FIPS 1
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
            ubuntu2404) say "To enable it (Ubuntu Pro): sudo pro enable fips-updates, reboot, then reinstall the package." ;;
        esac
        ! is_true "$(env_value "$envfile" UCM_FIPS)" || say "WARNING: UCM_FIPS=1 is set in $envfile: the service refuses to start until the host is in FIPS mode."
    fi
    run_preflight "$home" "$envfile" "$data" "$user"
}

# Run by the updater before installing: a FIPS build that cannot happen is refused up front.
cmd_update_precheck() {
    local home=$1 envfile=$2 format=$3 python=python3
    fips_requested "$envfile" || return 0
    [ ! -x "$home/venv/bin/python" ] || python=$(readlink -f "$home/venv/bin/python")
    cmd_check_build_tools "$python" "$format" > /dev/null
}

cmd_fips_build_ok() {
    if fips_requested "$1" && [ -e "$BUILD_FAILED" ]; then
        echo "the UCM_FIPS_BUILD=1 build failed (log: $BUILD_LOG); the previous environment was kept" >&2
        return 1
    fi
}

case "${1:-}" in
    env) cmd_env "$2" "$3" ;;
    venv) cmd_venv "$2" "$3" "$4" "$5" ;;
    fips-finish) cmd_fips_finish "$2" "$3" "$4" "$5" ;;
    fips-requested) fips_requested "$2" ;;
    check-build-tools) cmd_check_build_tools "$2" "$3" ;;
    update-precheck) cmd_update_precheck "$2" "$3" "$4" ;;
    fips-build-ok) cmd_fips_build_ok "$2" ;;
    *) die "usage: $0 env|venv|fips-finish|fips-requested|check-build-tools|update-precheck|fips-build-ok ..." ;;
esac
