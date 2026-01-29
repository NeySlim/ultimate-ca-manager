#!/bin/bash
#
# Ultimate CA Manager - Installation Script
# Version: 1.0.0
# 
# This script installs UCM to /opt/ucm with systemd service
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/ucm"
SERVICE_USER="ucm"
SERVICE_NAME="ucm"
PYTHON_MIN_VERSION="3.9"

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Ultimate CA Manager - Installer      ║${NC}"
echo -e "${BLUE}║  Version 1.0.0                         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ This script must be run as root${NC}"
    echo "   Please run: sudo $0"
    exit 1
fi

echo -e "${GREEN}✅ Running as root${NC}"

# Check Python version
echo ""
echo "🐍 Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed${NC}"
    echo "   Please install Python 3.9 or higher"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo -e "${GREEN}✅ Python $PYTHON_VERSION found${NC}"

# Check if already installed
if [ -d "$INSTALL_DIR" ]; then
    echo ""
    echo -e "${YELLOW}⚠️  UCM is already installed at $INSTALL_DIR${NC}"
    read -p "Do you want to upgrade? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
    echo "Stopping existing service..."
    systemctl stop $SERVICE_NAME 2>/dev/null || true
fi

# Install system dependencies
echo ""
echo "📦 Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3-pip python3-venv python3-dev build-essential libssl-dev \
    libffi-dev python3-setuptools

echo -e "${GREEN}✅ Dependencies installed${NC}"

# Create service user
echo ""
echo "👤 Creating service user..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d $INSTALL_DIR -m $SERVICE_USER
    echo -e "${GREEN}✅ User '$SERVICE_USER' created${NC}"
else
    echo -e "${YELLOW}⚠️  User '$SERVICE_USER' already exists${NC}"
fi

# Create installation directory
echo ""
echo "📁 Creating installation directory..."
mkdir -p $INSTALL_DIR
cp -r * $INSTALL_DIR/
chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_DIR

echo -e "${GREEN}✅ Files copied to $INSTALL_DIR${NC}"

# Create virtual environment
echo ""
echo "🐍 Creating Python virtual environment..."
cd $INSTALL_DIR
sudo -u $SERVICE_USER python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo ""
echo "📦 Installing Python packages..."
pip install --upgrade pip setuptools wheel -q
pip install -r backend/requirements.txt -q

echo -e "${GREEN}✅ Python packages installed${NC}"

# Create .env file if not exists
echo ""
echo "⚙️  Configuring environment..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp $INSTALL_DIR/.env.example $INSTALL_DIR/.env
    
    # Generate random secrets
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    
    sed -i "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" $INSTALL_DIR/.env
    sed -i "s/JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$JWT_SECRET/" $INSTALL_DIR/.env
    
    echo -e "${GREEN}✅ Configuration file created${NC}"
else
    echo -e "${YELLOW}⚠️  Using existing .env file${NC}"
fi

# Initialize database
echo ""
echo "🗄️  Initializing database..."
cd $INSTALL_DIR
source venv/bin/activate
python backend/init_db.py

echo -e "${GREEN}✅ Database initialized${NC}"

# Create systemd service
echo ""
echo "🔧 Creating systemd service..."
cat > /etc/systemd/system/$SERVICE_NAME.service << SERVICEEOF
[Unit]
Description=Ultimate CA Manager
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin"
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/backend/app.py
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR/backend/data
ReadOnlyPaths=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
SERVICEEOF

echo -e "${GREEN}✅ Systemd service created${NC}"

# Reload systemd and enable service
echo ""
echo "🔄 Enabling service..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME

# Start service
echo ""
read -p "Do you want to start UCM now? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    systemctl start $SERVICE_NAME
    sleep 3
    
    if systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${GREEN}✅ UCM service started successfully${NC}"
    else
        echo -e "${RED}❌ Failed to start UCM service${NC}"
        echo "Check logs with: journalctl -u $SERVICE_NAME -n 50"
        exit 1
    fi
fi

# Configure firewall (optional)
echo ""
read -p "Do you want to configure firewall to allow HTTPS (port 8443)? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if command -v ufw &> /dev/null; then
        ufw allow 8443/tcp
        echo -e "${GREEN}✅ Firewall configured (ufw)${NC}"
    elif command -v firewall-cmd &> /dev/null; then
        firewall-cmd --permanent --add-port=8443/tcp
        firewall-cmd --reload
        echo -e "${GREEN}✅ Firewall configured (firewalld)${NC}"
    else
        echo -e "${YELLOW}⚠️  No firewall detected. Please manually allow port 8443${NC}"
    fi
fi

# Print success message
echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Installation Complete! 🎉         ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo "📋 Installation Summary:"
echo "   • Installation directory: $INSTALL_DIR"
echo "   • Service name: $SERVICE_NAME"
echo "   • Service user: $SERVICE_USER"
echo ""
echo "🔗 Access UCM:"
echo "   • URL: https://$(hostname -I | awk '{print $1}'):8443"
echo "   • URL: https://localhost:8443"
echo ""
echo "🔑 Default credentials:"
echo "   • Username: admin"
echo "   • Password: changeme123"
echo -e "   ${RED}⚠️  CHANGE THIS PASSWORD IMMEDIATELY!${NC}"
echo ""
echo "📚 Useful commands:"
echo "   • Start service:    systemctl start $SERVICE_NAME"
echo "   • Stop service:     systemctl stop $SERVICE_NAME"
echo "   • Restart service:  systemctl restart $SERVICE_NAME"
echo "   • Service status:   systemctl status $SERVICE_NAME"
echo "   • View logs:        journalctl -u $SERVICE_NAME -f"
echo ""
echo "📖 Documentation: $INSTALL_DIR/README.md"
echo ""
