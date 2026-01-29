#!/bin/bash
#
# Ultimate CA Manager - Upgrade Script
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

INSTALL_DIR="/opt/ucm"
SERVICE_NAME="ucm"

echo -e "${YELLOW}╔════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║  Ultimate CA Manager - Upgrader       ║${NC}"
echo -e "${YELLOW}╚════════════════════════════════════════╝${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ This script must be run as root${NC}"
    exit 1
fi

# Check if installed
if [ ! -d "$INSTALL_DIR" ]; then
    echo -e "${RED}❌ UCM is not installed at $INSTALL_DIR${NC}"
    echo "Run install.sh first"
    exit 1
fi

# Backup current installation
BACKUP_DIR="/root/ucm_upgrade_backup_$(date +%Y%m%d_%H%M%S)"
echo "📦 Creating backup..."
mkdir -p "$BACKUP_DIR"
cp -r "$INSTALL_DIR"/{backend/data,.env} "$BACKUP_DIR/"
echo -e "${GREEN}✅ Backup created: $BACKUP_DIR${NC}"

# Stop service
echo ""
echo "🛑 Stopping service..."
systemctl stop $SERVICE_NAME

# Update files
echo ""
echo "📁 Updating files..."
cp -r backend frontend scripts docs README.md "$INSTALL_DIR/"

# Update dependencies
echo ""
echo "📦 Updating Python dependencies..."
cd $INSTALL_DIR
source venv/bin/activate
pip install --upgrade pip -q
pip install -r backend/requirements.txt --upgrade -q

# Run database migrations if any
if [ -f "$INSTALL_DIR/backend/migrate.py" ]; then
    echo ""
    echo "🗄️  Running database migrations..."
    python backend/migrate.py
fi

# Fix permissions
echo ""
echo "🔒 Fixing permissions..."
chown -R ucm:ucm $INSTALL_DIR
chmod -R 755 $INSTALL_DIR
chmod 700 $INSTALL_DIR/backend/data/private

# Start service
echo ""
echo "🔄 Starting service..."
systemctl start $SERVICE_NAME

# Check status
sleep 2
if systemctl is-active --quiet $SERVICE_NAME; then
    echo -e "${GREEN}✅ Service started successfully${NC}"
else
    echo -e "${RED}❌ Service failed to start${NC}"
    echo "Restoring backup..."
    cp -r "$BACKUP_DIR"/* "$INSTALL_DIR/"
    systemctl start $SERVICE_NAME
    echo "Check logs: journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Upgrade Complete! 🎉               ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo "Backup location: $BACKUP_DIR"
echo ""
