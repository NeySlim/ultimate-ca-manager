#!/bin/bash
# UCM Service Action Handler
# Triggered by ucm-watcher.path when signal files appear in /opt/ucm/data/
# Handles: restart requests, package updates
# Runs as root via systemd

set -euo pipefail

# UCM_WATCHER_ROOT relocates every path, for tests only
ROOT="${UCM_WATCHER_ROOT:-}"
DATA_DIR="$ROOT/opt/ucm/data"
RESTART_FILE="$DATA_DIR/.restart_requested"
UPDATE_FILE="$DATA_DIR/.update_pending"
MANIFEST_FILE="$DATA_DIR/.update_manifest.json"
# Claimed copy of the manifest for THIS operation: a concurrent trigger may
# replace $MANIFEST_FILE while we work, so all metadata is read from the
# claimed copy only (never from the mutable global file)
PROCESSING_FILE="$DATA_DIR/.update_manifest.processing"
RESULT_FILE="$DATA_DIR/.update_result.json"
VERSION_FILE="$ROOT/opt/ucm/VERSION"
SETUP="$ROOT/opt/ucm/scripts/native-setup.sh"
UCM_ENV="$ROOT/etc/ucm/ucm.env"
LOG_FILE="$ROOT/var/log/ucm/ucm.log"
# Release digests are fetched by root from GitHub; UCM_WATCHER_RELEASES is honoured in tests only
RELEASES="https://github.com/NeySlim/ultimate-ca-manager/releases/download"
if [ -n "$ROOT" ] && [ -n "${UCM_WATCHER_RELEASES:-}" ]; then RELEASES="$UCM_WATCHER_RELEASES"; fi

log() {
    echo "$(date -Iseconds) [ucm-watcher] $*" | tee -a "$LOG_FILE"
}

manifest_get() {
    # Read one string field from the CLAIMED operation manifest ('' when absent)
    MANIFEST_PATH="$PROCESSING_FILE" python3 - "$1" <<'PYEOF' 2>/dev/null || true
import json, os, sys
try:
    with open(os.environ["MANIFEST_PATH"]) as f:
        print(json.load(f).get(sys.argv[1]) or '')
except Exception:
    pass
PYEOF
}

installed_version() {
    # The canonical UCM version shipped by the package itself — matches the
    # release tag exactly (e.g. 2.215-rc1), unlike dpkg/rpm versions where
    # the prerelease separator becomes '~' (2.215~rc1)
    if [ -f "$VERSION_FILE" ]; then
        tr -d ' \n' < "$VERSION_FILE" 2>/dev/null || true
        return
    fi
    if command -v dpkg-query &>/dev/null; then
        dpkg-query -W -f='${Version}' ucm 2>/dev/null || true
    elif command -v rpm &>/dev/null; then
        rpm -q --qf '%{VERSION}' ucm 2>/dev/null || true
    fi
}

versions_match() {
    # versions_match <detected> <target> — tolerate the packaging transforms:
    # prerelease '-' becomes '~' in DEB/RPM versions, and a package revision
    # ('-1') may be appended. Everything is compared '~'-normalized.
    local detected target base
    detected=$(printf '%s' "$1" | tr '~' '-')
    target=$(printf '%s' "$2" | tr '~' '-')
    base=$(printf '%s' "$detected" | sed 's/-[0-9][0-9]*$//')
    [ "$detected" = "$target" ] || [ "$base" = "$target" ]
}

write_result() {
    # write_result <status> <step> <error> — durable, atomic (rename),
    # consumed once by the UCM backend after the restart. The claimed
    # manifest is removed only after the result is durably written; on a
    # write failure it is kept for diagnosis and NO result is left behind
    # (the backend then simply never claims success).
    if STATUS="$1" STEP="$2" ERROR="$3" INSTALLED="$(installed_version)" \
        MANIFEST_PATH="$PROCESSING_FILE" RESULT_PATH="$RESULT_FILE" \
        python3 - <<'PYEOF' >> "$LOG_FILE" 2>&1
import json, os, time
manifest = {}
try:
    with open(os.environ["MANIFEST_PATH"]) as f:
        manifest = json.load(f)
except Exception:
    pass
result = {
    "op_id": manifest.get("op_id"),
    "from_version": manifest.get("from_version"),
    "to_version": manifest.get("to_version"),
    "initiated_by": manifest.get("initiated_by"),
    "status": os.environ["STATUS"],
    "step": os.environ["STEP"] or None,
    "error": (os.environ["ERROR"] or None) and os.environ["ERROR"][:500],
    "installed_version": os.environ["INSTALLED"] or None,
    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
result_path = os.environ["RESULT_PATH"]
tmp = result_path + ".tmp"
with open(tmp, "w") as f:
    json.dump(result, f)
os.chmod(tmp, 0o644)
os.replace(tmp, result_path)
PYEOF
    then
        rm -f "$PROCESSING_FILE"
    else
        log "ERROR: could not write the update result file — keeping the claimed manifest for diagnosis"
    fi
}

# Records a failed or interrupted UCM_FIPS_BUILD=1 build of this update as its result
fips_build_ok() {
    local msg
    if [ -f "$SETUP" ] && ! msg=$(bash "$SETUP" fips-build-ok "$UCM_ENV" 2>&1); then
        log "ERROR: $msg"
        write_result failed fips-build "$msg"
        return 1
    fi
}

# A restart asked for is not counted by the unit's start limit, meant for crashes alone:
# reset-failed flushes that counter first
restart_ucm() {
    systemctl reset-failed ucm >> "$LOG_FILE" 2>&1 || true
    systemctl restart ucm >> "$LOG_FILE" 2>&1
}

# claim_package <path> <to_version>: prints "ok <copy>" or "error <reason>". The service account
# writes the trigger, so root accepts only a release asset under updates/, copies it where that
# account cannot reach, and checks the copy against the release's .sha256 fetched from GitHub
claim_package() {
    PKG="$1" TO="$2" UPDATES="$DATA_DIR/updates" RELEASES="$RELEASES" python3 - <<'PYEOF' 2>/dev/null || echo "error package check failed"
import hashlib, os, re, ssl, stat, sys, tempfile, urllib.request
pkg, to, updates = os.environ["PKG"], os.environ["TO"], os.environ["UPDATES"]
# A rolling update names its download <12 hex>-<asset>: the asset name is checked and copied
name = re.sub(r"^[0-9a-f]{12}-", "", os.path.basename(pkg))
def refuse(reason):
    print("error " + reason)
    sys.exit(0)
if os.path.dirname(pkg) != updates or os.path.islink(updates):
    refuse("package not directly under " + updates)
if not re.fullmatch(r"ucm_[0-9][0-9A-Za-z.+]*_all\.deb|ucm(-el[0-9]+)?-[0-9][0-9A-Za-z.+]*-[0-9]+\.[0-9A-Za-z_]+\.noarch\.rpm", name):
    refuse("package name is not one of a UCM release: " + name)
if not re.fullmatch(r"[0-9][0-9A-Za-z.+-]*", to or ""):
    refuse("no valid target version in the update manifest")
try:
    fd = os.open(pkg, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
except OSError:
    refuse("package is missing or is a symbolic link")
with os.fdopen(fd, "rb") as src:
    st = os.fstat(src.fileno())
    if not stat.S_ISREG(st.st_mode):
        refuse("package is not a regular file")
    if st.st_size > 1 << 30:
        refuse("package is over 1 GiB")
    work = tempfile.mkdtemp(prefix="ucm-update.")
    copy = os.path.join(work, name)
    digest = hashlib.sha256()
    with open(copy, "wb") as dst:
        for chunk in iter(lambda: src.read(1 << 20), b""):
            digest.update(chunk)
            dst.write(chunk)
url = "%s/v%s/%s.sha256" % (os.environ["RELEASES"], to, name)
def discard(reason):
    os.remove(copy)
    os.rmdir(work)
    refuse(reason)
try:
    with urllib.request.urlopen(url, timeout=60, context=ssl.create_default_context()) as r:
        published = r.read(1 << 16).decode("utf-8", "replace")
except Exception as e:
    discard("could not fetch the release digest %s: %s" % (url, e))
# The asset name has '.' where the package name has '~' (GitHub)
wanted = [l.split()[0].lower() for l in published.splitlines()
          if len(l.split()) >= 2 and os.path.basename(l.split()[-1].lstrip("*")).replace("~", ".") == name]
if not wanted or wanted[0] != digest.hexdigest():
    discard("package digest does not match the release digest " + url)
print("ok " + copy)
PYEOF
}

# package_name <file>: the Package (DEB) or Name (RPM) the file declares
package_name() {
    if [[ "$1" == *.deb ]]; then
        dpkg-deb -f "$1" Package 2>/dev/null || true
    else
        rpm -qp --qf '%{NAME}' "$1" 2>/dev/null || true
    fi
}

finish_update() {
    # Always restart UCM so the backend consumes the result and emits the
    # truthful installed/failed event
    rm -f "$RESTART_FILE"
    log "Update handling done (status recorded), restarting UCM..."
    restart_ucm
    exit 0
}

# ── Handle update (install package + verify + record result + restart) ──
if [ -f "$UPDATE_FILE" ]; then
    PACKAGE_PATH=$(cat "$UPDATE_FILE")
    rm -f "$UPDATE_FILE"

    # Claim the manifest atomically: from here on, every metadata read and
    # the final result belong to THIS operation even if a new manifest is
    # written concurrently.
    mv -f "$MANIFEST_FILE" "$PROCESSING_FILE" 2>/dev/null || true

    if [ -z "$PACKAGE_PATH" ] || [ ! -f "$PACKAGE_PATH" ]; then
        log "ERROR: Invalid or missing package path: '$PACKAGE_PATH'"
        write_result failed precheck "invalid or missing package path"
        finish_update
    fi

    # From here on only the root-owned, digest-checked copy is installed
    ORIGINAL_PATH="$PACKAGE_PATH"
    CLAIM=$(claim_package "$PACKAGE_PATH" "$(manifest_get to_version)")
    if [[ "$CLAIM" != "ok "* ]]; then
        REASON="${CLAIM#error }"
        log "ERROR: update refused: $REASON"
        write_result failed precheck "$REASON"
        rm -f "$ORIGINAL_PATH"
        finish_update
    fi
    PACKAGE_PATH="${CLAIM#ok }"
    if [ "$(package_name "$PACKAGE_PATH")" != "ucm" ]; then
        log "ERROR: update refused: the package is not named ucm"
        write_result failed precheck "the package is not named ucm"
        rm -rf "$(dirname "$PACKAGE_PATH")"
        rm -f "$ORIGINAL_PATH"
        finish_update
    fi

    log "Starting update with package: $ORIGINAL_PATH (digest verified)"
    INSTALL_OK=1

    # UCM_FIPS_BUILD=1 compiles during the install: missing build tools refuse the update untouched
    if [ -f "$SETUP" ] && ! PRECHECK=$(bash "$SETUP" update-precheck "$ROOT/opt/ucm" "$UCM_ENV" 2>&1); then
        log "ERROR: update refused: $PRECHECK"
        write_result failed precheck "$PRECHECK"
        finish_update
    fi

    if [[ "$PACKAGE_PATH" == *.deb ]]; then
        log "Installing DEB package..."
        # dpkg first, then apt to resolve any missing dependencies; the
        # authoritative success check is the version verification below
        dpkg -i "$PACKAGE_PATH" >> "$LOG_FILE" 2>&1 || true
        # apt-get -f install would configure the package again, and rerun a failed FIPS build
        if ! fips_build_ok; then
            INSTALL_OK=0
        else
            log "Resolving dependencies..."
            if ! apt-get -f install -y >> "$LOG_FILE" 2>&1; then
                INSTALL_OK=0
                if fips_build_ok; then
                    log "ERROR: apt-get -f install failed"
                    write_result failed apt-get "apt-get -f install failed (see ucm.log)"
                fi
            fi
        fi
    elif [[ "$PACKAGE_PATH" == *.rpm ]]; then
        log "Installing RPM package..."
        if command -v dnf &>/dev/null; then
            RPM_TOOL=dnf; dnf install -y "$PACKAGE_PATH" >> "$LOG_FILE" 2>&1 || INSTALL_OK=0
        elif command -v yum &>/dev/null; then
            RPM_TOOL=yum; yum localinstall -y "$PACKAGE_PATH" >> "$LOG_FILE" 2>&1 || INSTALL_OK=0
        else
            RPM_TOOL=rpm; rpm -U "$PACKAGE_PATH" >> "$LOG_FILE" 2>&1 || INSTALL_OK=0
        fi
        if [ "$INSTALL_OK" != "1" ]; then
            log "ERROR: RPM install failed ($RPM_TOOL)"
            write_result failed "$RPM_TOOL" "RPM install failed (see ucm.log)"
        fi
    else
        log "ERROR: Unknown package format: $PACKAGE_PATH"
        write_result failed precheck "unknown package format"
        INSTALL_OK=0
    fi

    if [ "$INSTALL_OK" = "1" ]; then
        # Verify the version actually installed before declaring success —
        # a repaired-but-not-upgraded install must report failed. The check
        # reads the canonical /opt/ucm/VERSION shipped by the package, and
        # tolerates the DEB/RPM '~' prerelease transform on the fallback.
        TARGET_VERSION="$(manifest_get to_version)"
        DETECTED="$(installed_version)"
        log "Installed version: '${DETECTED}' (target: '${TARGET_VERSION}')"
        if [ -n "$TARGET_VERSION" ] && ! versions_match "$DETECTED" "$TARGET_VERSION"; then
            log "ERROR: installed version does not match the update target"
            write_result failed verify "installed version '$DETECTED' does not match target '$TARGET_VERSION'"
        elif fips_build_ok; then
            log "Package installed and version verified"
            write_result installed "" ""
        fi
    fi

    # Clean up the downloaded package and its checked copy
    rm -rf "$(dirname "$PACKAGE_PATH")"
    rm -f "$ORIGINAL_PATH"
    log "Cleaned up package: $ORIGINAL_PATH"

    finish_update
fi

# ── Handle simple restart ──
if [ -f "$RESTART_FILE" ]; then
    rm -f "$RESTART_FILE"
    log "Restart requested, restarting UCM..."
    restart_ucm
    log "Restart complete"
    exit 0
fi

log "Watcher triggered but no action file found"
