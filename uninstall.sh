#!/bin/bash
#
# Ultimate CA Manager - Uninstallation Script
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="/opt/ucm"
SERVICE_USER="ucm"
SERVICE_NAME="ucm"

echo -e "${YELLOW}╔════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║  Ultimate CA Manager - Uninstaller    ║${NC}"
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
    exit 1
fi

echo -e "${YELLOW}⚠️  WARNING: This will completely remove UCM${NC}"
echo ""
echo "The following will be removed:"
echo "  • Service: $SERVICE_NAME"
echo "  • Installation: $INSTALL_DIR"
echo "  • User: $SERVICE_USER"
echo "  • All data, certificates, and databases"
echo ""
read -p "Are you sure you want to continue? (yes/NO): " -r
echo

if [ "$REPLY" != "yes" ]; then
    echo "Uninstallation cancelled."
    exit 0
fi

# Ask about backup
echo ""
read -p "Do you want to backup the database before uninstalling? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    BACKUP_FILE="/root/ucm_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
    echo "Creating backup..."
    tar -czf "$BACKUP_FILE" -C "$INSTALL_DIR/backend" data/
    echo -e "${GREEN}✅ Backup created: $BACKUP_FILE${NC}"
fi

# Stop and disable service
echo ""
echo "🛑 Stopping service..."
systemctl stop $SERVICE_NAME 2>/dev/null || true
systemctl disable $SERVICE_NAME 2>/dev/null || true

# Remove systemd service
echo "🗑️  Removing systemd service..."
rm -f /etc/systemd/system/$SERVICE_NAME.service
systemctl daemon-reload

# Remove installation directory
echo "🗑️  Removing installation directory..."
rm -rf $INSTALL_DIR

# Remove user
echo "👤 Removing service user..."
if id "$SERVICE_USER" &>/dev/null; then
    userdel $SERVICE_USER 2>/dev/null || true
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Uninstallation Complete! ✅          ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo "UCM has been removed from your system."
echo ""
