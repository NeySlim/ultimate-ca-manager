#!/bin/bash
# UCM Auto-Update Script
# Triggered by ucm-updater.path when /opt/ucm/data/.update_pending appears
# Runs as root via systemd (no NoNewPrivileges restriction)

set -euo pipefail

TRIGGER_FILE="/opt/ucm/data/.update_pending"
LOG_FILE="/var/log/ucm/update.log"

log() {
    echo "$(date -Iseconds) [ucm-updater] $*" | tee -a "$LOG_FILE"
}

# Read and remove trigger file atomically
if [ ! -f "$TRIGGER_FILE" ]; then
    log "No trigger file found, exiting"
    exit 0
fi

PACKAGE_PATH=$(cat "$TRIGGER_FILE")
rm -f "$TRIGGER_FILE"

if [ -z "$PACKAGE_PATH" ] || [ ! -f "$PACKAGE_PATH" ]; then
    log "ERROR: Invalid or missing package path: '$PACKAGE_PATH'"
    exit 1
fi

log "Starting update with package: $PACKAGE_PATH"

# Detect package type and install
if [[ "$PACKAGE_PATH" == *.deb ]]; then
    log "Installing DEB package..."
    if dpkg -i "$PACKAGE_PATH" >> "$LOG_FILE" 2>&1; then
        log "DEB package installed successfully"
    else
        log "ERROR: DEB installation failed, attempting fix..."
        apt-get -f install -y >> "$LOG_FILE" 2>&1 || true
    fi
elif [[ "$PACKAGE_PATH" == *.rpm ]]; then
    log "Installing RPM package..."
    if rpm -U --force "$PACKAGE_PATH" >> "$LOG_FILE" 2>&1; then
        log "RPM package installed successfully"
    else
        log "ERROR: RPM installation failed"
        exit 1
    fi
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

# Restart UCM service
log "Restarting UCM service..."
systemctl restart ucm >> "$LOG_FILE" 2>&1

log "Update complete!"
