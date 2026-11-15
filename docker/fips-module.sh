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
    local module=$1 run_dir=$2 reference=$3 expected actual
    if ! openssl fipsinstall -pedantic -module "$module" -provider_name fips \
        -out "$run_dir/fipsmodule.cnf" > "$run_dir/fipsinstall.log" 2>&1; then
        echo -e "${RED:-}❌ openssl fipsinstall failed: the FIPS module did not pass its self-tests${NC:-}"
        cat "$run_dir/fipsinstall.log"
        return 1
    fi
    # same format the Dockerfile checks when it writes the reference; no shell error shown
    if ! { expected=$(tr -d '[:space:]' < "$reference"); } 2>/dev/null \
        || ! [[ $expected =~ ^([0-9A-F]{2}:){31}[0-9A-F]{2}$ ]]; then
        echo -e "${RED:-}❌ The FIPS module integrity reference of the image ($reference) is missing or unreadable${NC:-}"
        echo "   Pull the published -fips image again; the module cannot be checked against its build."
        return 1
    fi
    actual=$(fips_module_mac "$run_dir/fipsmodule.cnf")
    if [ "$actual" != "$expected" ]; then
        echo -e "${RED:-}❌ The FIPS module of this image ($module) was modified since the image was built: its integrity value does not match${NC:-}"
        echo "   Pull the published -fips image again; UCM does not start FIPS mode on a modified module."
        return 1
    fi
}
