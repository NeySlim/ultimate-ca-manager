#!/bin/bash
# FIPS module installation at start, checked against the integrity value of the build.
# Functions only: entrypoint.sh sources this file, the Dockerfile and the tests source it too.

# module-mac of a fipsmodule.cnf written by openssl fipsinstall
fips_module_mac() {
    awk -F= '{ gsub(/[ \t\r]/, "") } $1 == "module-mac" { value = $2 } END { print value }' "$1"
}

# fipsinstall runs the self-tests on this platform (security policy 11.1); the module-mac it
# computes must equal the one recorded when the image was built, or the module was modified
install_fips_module() {
    local module=$1 run_dir=$2 reference=$3 expected actual out checked
    # the provider loads fips.so from OPENSSL_MODULES when set: only the checked directory, as an
    # absolute path (a relative one names another directory in the process that loads the module);
    # a directory that cannot be resolved is refused, not taken as equal
    checked=$(realpath -m -- "$(dirname -- "$module")" 2>/dev/null)
    if [ -n "${OPENSSL_MODULES+set}" ] && { [ "${OPENSSL_MODULES#/}" = "$OPENSSL_MODULES" ] || [ -z "$checked" ] \
        || [ "$(realpath -m -- "$OPENSSL_MODULES" 2>/dev/null)" != "$checked" ]; }; then
        echo -e "${RED:-}❌ OPENSSL_MODULES ($OPENSSL_MODULES) is not the absolute path of the directory of the checked FIPS module ($(dirname -- "$module"))${NC:-}"
        echo "   Remove OPENSSL_MODULES: UCM does not start FIPS mode on a module it has not checked."
        return 1
    fi
    # fipsinstall writes beside the config, which is replaced only once the module-mac matches
    out=$(mktemp "$run_dir/fipsmodule.cnf.XXXXXX") || return 1
    if ! openssl fipsinstall -pedantic -module "$module" -provider_name fips \
        -out "$out" > "$run_dir/fipsinstall.log" 2>&1; then
        rm -f -- "$out"
        echo -e "${RED:-}❌ openssl fipsinstall failed: the FIPS module did not pass its self-tests${NC:-}"
        cat "$run_dir/fipsinstall.log"
        return 1
    fi
    # same format the Dockerfile checks when it writes the reference; no shell error shown
    if ! { expected=$(tr -d '[:space:]' < "$reference"); } 2>/dev/null \
        || ! printf '%s\n' "$expected" | grep -Eqx '([0-9A-F]{2}:){31}[0-9A-F]{2}'; then
        rm -f -- "$out"
        echo -e "${RED:-}❌ The FIPS module integrity reference of the image ($reference) is missing, unreadable or malformed${NC:-}"
        echo "   Pull the published -fips image again; the module cannot be checked against its build."
        return 1
    fi
    actual=$(fips_module_mac "$out")
    if [ "$actual" != "$expected" ]; then
        rm -f -- "$out"
        echo -e "${RED:-}❌ The FIPS module of this image ($module) was modified since the image was built: its integrity value does not match${NC:-}"
        echo "   Pull the published -fips image again; UCM does not start FIPS mode on a modified module."
        return 1
    fi
    mv -f -- "$out" "$run_dir/fipsmodule.cnf"
    # pinned: ucm.env, read by the app after this check, cannot move it (no dotenv override)
    export OPENSSL_MODULES
    OPENSSL_MODULES=$(dirname -- "$module")
}
