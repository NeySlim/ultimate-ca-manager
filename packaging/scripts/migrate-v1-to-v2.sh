#!/bin/bash
# UCM v1.8.x → v2.0.0 Automatic Migration Script
# Called by postinst during package upgrade

set -e

UCM_HOME="${UCM_HOME:-/opt/ucm}"
UCM_DATA="${UCM_DATA:-/opt/ucm/data}"
UCM_CONFIG="${UCM_CONFIG:-/etc/ucm}"
V1_DATA="$UCM_HOME/backend/data"
LOG_FILE="/var/log/ucm/migration.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Check if migration is needed
if [ ! -f "$V1_DATA/ucm.db" ]; then
    exit 0  # No v1.8.x data, nothing to migrate
fi

if [ -f "$UCM_DATA/ucm.db" ]; then
    exit 0  # v2.0 data already exists
fi

log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log " UCM v1.8.x → v2.0.0 Migration"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Create backup
BACKUP_DIR="$UCM_HOME/backup_v1.8_$(date +%Y%m%d_%H%M%S)"
log "Creating backup: $BACKUP_DIR"
cp -r "$V1_DATA" "$BACKUP_DIR"
log "✓ Backup created"

# Create v2 directories
mkdir -p "$UCM_DATA"/{ca,certs,private,sessions,backups,scep,crl}

# Migrate files
log "Migrating files..."
for dir in ca certs private crl scep backups; do
    if [ -d "$V1_DATA/$dir" ] && [ "$(ls -A $V1_DATA/$dir 2>/dev/null)" ]; then
        cp -r "$V1_DATA/$dir"/* "$UCM_DATA/$dir/" 2>/dev/null || true
        log "  ✓ Copied $dir/"
    fi
done

# Copy database
cp "$V1_DATA/ucm.db" "$UCM_DATA/ucm.db"
log "  ✓ Copied ucm.db"

# Copy HTTPS certificates
[ -f "$V1_DATA/https_cert.pem" ] && cp "$V1_DATA/https_cert.pem" "$UCM_DATA/"
[ -f "$V1_DATA/https_key.pem" ] && cp "$V1_DATA/https_key.pem" "$UCM_DATA/"
log "  ✓ Copied HTTPS certificates"

# Migrate configuration
if [ -f "$UCM_HOME/.env" ] && [ ! -f "$UCM_CONFIG/ucm.env" ]; then
    log "Migrating configuration..."
    mkdir -p "$UCM_CONFIG"
    
    # Copy and update config
    {
        echo "# UCM Configuration (migrated from v1.8.x)"
        echo "# Migrated at: $(date)"
        echo ""
        grep -v '^#' "$UCM_HOME/.env" | grep '=' || true
        echo ""
        echo "# Updated for v2.0.0"
        echo "DATABASE_PATH=$UCM_DATA/ucm.db"
    } > "$UCM_CONFIG/ucm.env"
    
    chmod 600 "$UCM_CONFIG/ucm.env"
    log "✓ Config migrated to $UCM_CONFIG/ucm.env"
fi

# Run database migration
if [ -f "$UCM_HOME/backend/migrate_v1_to_v2.py" ]; then
    log "Running database schema migration..."
    cd "$UCM_HOME/backend"
    python3 migrate_v1_to_v2.py --db-only "$UCM_DATA/ucm.db" 2>&1 | tee -a "$LOG_FILE"
fi

# Fix permissions
if id ucm &>/dev/null; then
    chown -R ucm:ucm "$UCM_DATA"
    chown -R ucm:ucm "$UCM_CONFIG"
fi

log ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log " MIGRATION COMPLETE"
log " Old data backed up to: $BACKUP_DIR"
log " To clean up old data:"
log "   rm -rf $V1_DATA"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exit 0
