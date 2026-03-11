#!/bin/bash
# UCM Service Action Handler
# Triggered by ucm-watcher.path when signal files appear in /opt/ucm/data/
# Handles: restart requests, package updates
# Runs as root via systemd

set -euo pipefail

DATA_DIR="/opt/ucm/data"
RESTART_FILE="$DATA_DIR/.restart_requested"
UPDATE_FILE="$DATA_DIR/.update_pending"
LOG_FILE="/var/log/ucm/ucm.log"

log() {
    echo "$(date -Iseconds) [ucm-watcher] $*" | tee -a "$LOG_FILE"
}

# ── Handle update (install package + restart) ──
if [ -f "$UPDATE_FILE" ]; then
    PACKAGE_PATH=$(cat "$UPDATE_FILE")
    rm -f "$UPDATE_FILE"

    if [ -z "$PACKAGE_PATH" ] || [ ! -f "$PACKAGE_PATH" ]; then
        log "ERROR: Invalid or missing package path: '$PACKAGE_PATH'"
        exit 1
    fi

    log "Starting update with package: $PACKAGE_PATH"

    if [[ "$PACKAGE_PATH" == *.deb ]]; then
        log "Installing DEB package..."
        # Use dpkg to install, then apt to resolve any missing dependencies
        dpkg -i "$PACKAGE_PATH" >> "$LOG_FILE" 2>&1 || true
        log "Resolving dependencies..."
        apt-get -f install -y >> "$LOG_FILE" 2>&1
        log "DEB package installed successfully"
    elif [[ "$PACKAGE_PATH" == *.rpm ]]; then
        log "Installing RPM package..."
        # Use dnf to handle dependencies automatically, fall back to rpm
        if command -v dnf &>/dev/null; then
            dnf install -y "$PACKAGE_PATH" >> "$LOG_FILE" 2>&1
        elif command -v yum &>/dev/null; then
            yum localinstall -y "$PACKAGE_PATH" >> "$LOG_FILE" 2>&1
        else
            rpm -U --force "$PACKAGE_PATH" >> "$LOG_FILE" 2>&1
        fi
        log "RPM package installed successfully"
    else
        log "ERROR: Unknown package format: $PACKAGE_PATH"
        exit 1
    fi

    # Clean up downloaded package
    PACKAGE_DIR=$(dirname "$PACKAGE_PATH")
    if [[ "$PACKAGE_DIR" == */updates ]]; then
        rm -f "$PACKAGE_PATH"
        log "Cleaned up package: $PACKAGE_PATH"
    fi

    # Remove restart file too (update implies restart)
    rm -f "$RESTART_FILE"

    log "Update complete, restarting UCM..."
    systemctl restart ucm >> "$LOG_FILE" 2>&1
    exit 0
fi

# ── Handle simple restart ──
if [ -f "$RESTART_FILE" ]; then
    rm -f "$RESTART_FILE"
    log "Restart requested, restarting UCM..."
    systemctl restart ucm >> "$LOG_FILE" 2>&1
    log "Restart complete"
    exit 0
fi

log "Watcher triggered but no action file found"
