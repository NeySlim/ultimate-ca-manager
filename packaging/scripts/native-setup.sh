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
GUARDED_VENV="" GUARDED_TMP="" SERVICE_STOPPED="" VENV_BUILDING=""

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

# Sets a key that has no value: an empty assignment (KEY=, KEY="") is filled in place.
env_fill() {
    local re="^[[:space:]]*(export[[:space:]]+)?$2[[:space:]]*=[[:space:]]*(\"\"|'')?[[:space:]]*\$"
    if grep -Eq "$re" "$1"; then
        # Builtins only: the value is a secret and must not appear in a process's argv
        local tmp line
        tmp=$(mktemp "$1.XXXXXX")
        trap "rm -f -- $(printf %q "$tmp")" EXIT
        while IFS= read -r line || [ -n "$line" ]; do
            [[ $line =~ $re ]] && line="$2=$3"
            printf '%s\n' "$line"
        done < "$1" > "$tmp"
        chown --reference="$1" "$tmp"
        chmod --reference="$1" "$tmp"
        mv -f "$tmp" "$1"
        trap - EXIT
    else
        env_append "$1" "$2" "$3"
    fi
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
    local file=$1 data=$2 had_secret="" key
    touch "$file"
    env_has "$file" SECRET_KEY && had_secret=1
    # Restricted before the first secret is written
    env_has "$file" SECRET_KEY && env_has "$file" JWT_SECRET_KEY || chmod 600 "$file"
    for key in SECRET_KEY JWT_SECRET_KEY; do
        env_has "$file" "$key" || env_fill "$file" "$key" "$(openssl rand -hex 32)"
    done
    # A file the package never completed (written by hand before the install) gets the defaults too.
    if [ -z "$had_secret" ]; then
        env_has "$file" DATABASE_PATH || env_fill "$file" DATABASE_PATH "$data/ucm.db"
        env_has "$file" DATA_DIR || env_fill "$file" DATA_DIR "$data"
        env_has "$file" HTTPS_PORT || env_fill "$file" HTTPS_PORT 8443
        env_has "$file" HTTP_PROTOCOL_PORT || env_fill "$file" HTTP_PROTOCOL_PORT 8080
        env_has "$file" LOG_LEVEL || env_fill "$file" LOG_LEVEL INFO
        env_has "$file" INITIAL_ADMIN_PASSWORD || env_fill "$file" INITIAL_ADMIN_PASSWORD changeme123
        echo new
    fi
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

# A venv the service can start: an interrupted build leaves one without gunicorn or python.
venv_ok() {
    [ -x "$1/bin/gunicorn" ] && "$1/bin/python" -c '' >/dev/null 2>&1
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

# Until the new venv is complete, any exit (failure or signal) puts the previous one back and
# starts ucm again if it was stopped here; on success the package script starts it at the end.
guard_venv() {
    GUARDED_VENV=$1 GUARDED_TMP=${2:-}
    trap recover_venv EXIT
    # Trapped, a signal is handled once pip has exited: recover_venv never races a dying pip
    trap 'exit 129' HUP; trap 'exit 130' INT; trap 'exit 143' TERM
    # Skipped in a chroot or container without systemd
    if [ -d "$SYSTEMD_RUN" ] && systemctl is-active --quiet ucm; then
        say "Stopping UCM while its Python environment is rebuilt..."
        SERVICE_STOPPED=1
        systemctl stop ucm || say "WARNING: could not stop UCM; rebuilding its environment anyway"
    fi
}

recover_venv() {
    # Runs to the end despite a repeated Ctrl-C or a terminal gone (every write failing)
    trap '' HUP INT TERM
    set +e
    local venv=$GUARDED_VENV
    [ -z "$GUARDED_TMP" ] || rm -f "$GUARDED_TMP"
    case $VENV_BUILDING in
        moved) [ ! -e "$venv.prev" ] || { rm -rf "$venv" && mv -T "$venv.prev" "$venv" \
                   && say "Restored the previous Python environment." >&2; } ;;
        # A first install has no previous venv: an incomplete one must not pass venv-ok
        fresh) rm -rf "$venv" ;;
        *) if [ -e "$venv.prev" ] && ! venv_ok "$venv"; then rm -rf "$venv" && mv -T "$venv.prev" "$venv"; fi ;;
    esac
    if [ -n "$SERVICE_STOPPED" ] && venv_ok "$venv"; then
        say "Starting UCM again..." >&2
        systemctl start ucm
    fi
}

# Moves the venv aside as venv.prev, after resolving what an interrupted build left behind.
set_aside_venv() {
    if [ -e "$1.prev" ] && ! venv_ok "$1"; then
        rm -rf "$1" && mv -T "$1.prev" "$1"
    fi
    rm -rf "$1.prev"
    if [ -e "$1" ]; then
        mv -T "$1" "$1.prev"
        VENV_BUILDING=moved
    else
        VENV_BUILDING=fresh
    fi
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
        say "(about 5 minutes the first time, then from pip's wheel cache; log: $BUILD_LOG)..."
        reqs=$(mktemp)
        fips_requirements "$home/requirements.txt" "$reqs"
        guard_venv "$venv" "$reqs"
        set_aside_venv "$venv"
        echo "build failed" > "$BUILD_FAILED"
        if ! build_fips_venv "$python" "$venv" "$reqs" > "$BUILD_LOG" 2>&1 \
                || ! verify_fips_venv "$home" >> "$BUILD_LOG" 2>&1; then
            tail -n 25 "$BUILD_LOG" >&2 || true
            # recover_venv then drops the new venv, even one verify_fips_venv refused with gunicorn in it
            echo "ERROR: the UCM_FIPS_BUILD=1 build failed (full log: $BUILD_LOG)." >&2
            echo "Fix the cause, or remove UCM_FIPS_BUILD from $envfile for the standard build, and" >&2
            retry_hint "$format" >&2
            exit 1
        fi
        rm -f "$reqs" "$BUILD_FAILED"
        tail -n 1 "$BUILD_LOG"
    else
        guard_venv "$venv"
        set_aside_venv "$venv"
        "$python" -m venv "$venv"
        "$venv/bin/pip" install --quiet --upgrade pip
        "$venv/bin/pip" install --quiet -r "$home/requirements.txt"
        # --no-deps keeps out twofish, an sdist-only dependency UCM never uses (see requirements.txt)
        "$venv/bin/pip" install --quiet --no-deps pyjks==20.0.0
    fi
    # Complete: the previous venv is no longer needed (flag first, so no exit drops the new one)
    VENV_BUILDING=""
    rm -rf "$venv.prev"

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
    trap - EXIT HUP INT TERM
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
    local home=$1 envfile=$2 python=python3
    fips_requested "$envfile" || return 0
    [ ! -x "$home/venv/bin/python" ] || python=$(readlink -f "$home/venv/bin/python")
    cmd_check_build_tools "$python" update > /dev/null
    # A new attempt starts: a failure marker left by an earlier one is not this update's
    rm -f "$BUILD_FAILED"
}

cmd_fips_build_ok() {
    if fips_requested "$1" && [ -e "$BUILD_FAILED" ]; then
        echo "the UCM_FIPS_BUILD=1 build failed (log: $BUILD_LOG); the previous environment was kept" >&2
        return 1
    fi
}

# Post-install banner; IPv6 addresses are bracketed in the URLs.
cmd_banner() {
    local envfile=$1 pkg=$2 host port ips ip pass
    # Cosmetic: a failed lookup (no hostname binary) must not cut it short
    set +e
    pass=$(sed -n 's/^INITIAL_ADMIN_PASSWORD=//p' "$envfile" | tail -n 1)
    echo ""
    host=$(hostname -f 2>/dev/null || hostname)
    port=$(grep "^HTTPS_PORT=" "$envfile" 2>/dev/null | cut -d= -f2)
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
    echo " Admin:    admin / $pass"
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
    venv-ok) venv_ok "$2/venv" ;;
    venv) cmd_venv "$2" "$3" "$4" "$5" ;;
    fips-finish) cmd_fips_finish "$2" "$3" "$4" "$5" ;;
    fips-requested) fips_requested "$2" ;;
    check-build-tools) cmd_check_build_tools "$2" "$3" ;;
    update-precheck) cmd_update_precheck "$2" "$3" ;;
    fips-build-ok) cmd_fips_build_ok "$2" ;;
    banner) cmd_banner "$2" "$3" ;;
    *) die "usage: $0 env <ucm.env> <data dir>
  | venv <ucm home> <python> <deb|rpm> <ucm.env> | venv-ok <ucm home>
  | fips-finish <ucm home> <ucm.env> <data dir> <user> | fips-requested <ucm.env>
  | check-build-tools <python> <deb|rpm> | update-precheck <ucm home> <ucm.env>
  | fips-build-ok <ucm.env> | banner <ucm.env> <deb|rpm>" ;;
esac
