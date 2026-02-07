#!/bin/bash
# UCM Universal Installer
# Works on ANY Linux distribution - auto-detects and uses best method
# No dependencies required - fully self-contained

set -e

VERSION="1.8.3"
GITHUB_REPO="NeySlim/ultimate-ca-manager"
INSTALL_DIR="/opt/ucm"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${BLUE}ℹ${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }
log_step() { echo -e "${CYAN}➜${NC} $1"; }

banner() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}     ${GREEN}Ultimate CA Manager - Universal Installer${NC}         ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}                   Version ${VERSION}                         ${CYAN}║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Check root
check_root() {
    if [ "$EUID" -ne 0 ]; then 
        log_error "Please run as root: sudo $0"
        exit 1
    fi
}

# Detect OS and package manager
detect_system() {
    log_step "Detecting system..."
    
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID=$ID
        OS_VERSION=$VERSION_ID
        OS_NAME=$PRETTY_NAME
    else
        OS_ID="unknown"
        OS_NAME="Unknown Linux"
    fi
    
    # Detect package manager
    if command -v apt-get &> /dev/null; then
        PKG_MGR="apt"
    elif command -v dnf &> /dev/null; then
        PKG_MGR="dnf"
    elif command -v yum &> /dev/null; then
        PKG_MGR="yum"
    elif command -v zypper &> /dev/null; then
        PKG_MGR="zypper"
    elif command -v pacman &> /dev/null; then
        PKG_MGR="pacman"
    elif command -v apk &> /dev/null; then
        PKG_MGR="apk"
    else
        PKG_MGR="none"
    fi
    
    log_info "OS: $OS_NAME"
    log_info "Package Manager: $PKG_MGR"
}

# Check if we can use native package
can_use_native_package() {
    case "$OS_ID" in
        ubuntu|debian|linuxmint|pop)
            if command -v dpkg &> /dev/null; then
                return 0
            fi
            ;;
        rhel|rocky|almalinux|centos|fedora)
            if command -v rpm &> /dev/null; then
                return 0
            fi
            ;;
    esac
    return 1
}

# Install using native package
install_native_package() {
    local pkg_type=$1
    log_step "Installing using native $pkg_type package..."
    
    local url="https://github.com/$GITHUB_REPO/releases/download/v${VERSION}"
    
    if [ "$pkg_type" = "deb" ]; then
        local pkg_file="ucm_${VERSION}_all.deb"
        log_info "Downloading $pkg_file..."
        
        if command -v wget &> /dev/null; then
            wget -q --show-progress "$url/$pkg_file" -O "/tmp/$pkg_file"
        elif command -v curl &> /dev/null; then
            curl -L --progress-bar "$url/$pkg_file" -o "/tmp/$pkg_file"
        else
            log_error "Need wget or curl to download package"
            return 1
        fi
        
        log_info "Installing package..."
        dpkg -i "/tmp/$pkg_file" || apt-get install -f -y
        rm -f "/tmp/$pkg_file"
        
    elif [ "$pkg_type" = "rpm" ]; then
        local pkg_file="ucm-${VERSION}-1.el9.noarch.rpm"
        log_info "Downloading $pkg_file..."
        
        if command -v wget &> /dev/null; then
            wget -q --show-progress "$url/$pkg_file" -O "/tmp/$pkg_file"
        elif command -v curl &> /dev/null; then
            curl -L --progress-bar "$url/$pkg_file" -o "/tmp/$pkg_file"
        else
            log_error "Need wget or curl to download package"
            return 1
        fi
        
        log_info "Installing package..."
        if command -v dnf &> /dev/null; then
            dnf install -y "/tmp/$pkg_file"
        else
            yum install -y "/tmp/$pkg_file"
        fi
        rm -f "/tmp/$pkg_file"
    fi
    
    log_success "Native package installed"
    return 0
}

# Install dependencies for source install
install_dependencies() {
    log_step "Installing dependencies..."
    
    case "$PKG_MGR" in
        apt)
            export DEBIAN_FRONTEND=noninteractive
            apt-get update -qq
            apt-get install -y -qq python3 python3-pip python3-venv systemd openssl adduser curl
            ;;
        dnf)
            dnf install -y python3 python3-pip systemd openssl curl
            ;;
        yum)
            yum install -y python3 python3-pip systemd openssl curl
            ;;
        zypper)
            zypper install -y python3 python3-pip systemd openssl curl
            ;;
        pacman)
            pacman -Sy --noconfirm python python-pip systemd openssl curl
            ;;
        apk)
            apk add --no-cache python3 py3-pip openrc openssl curl
            ;;
        *)
            log_error "Cannot install dependencies automatically"
            log_info "Please install manually: python3, pip, systemd, openssl, curl"
            exit 1
            ;;
    esac
    
    log_success "Dependencies installed"
}

# Download and extract source
install_from_source() {
    log_step "Installing from source..."
    
    local tarball="ucm-${VERSION}.tar.gz"
    local url="https://github.com/$GITHUB_REPO/releases/download/v${VERSION}/$tarball"
    
    log_info "Downloading source tarball..."
    if command -v wget &> /dev/null; then
        wget -q --show-progress "$url" -O "/tmp/$tarball"
    elif command -v curl &> /dev/null; then
        curl -L --progress-bar "$url" -o "/tmp/$tarball"
    else
        log_error "Need wget or curl"
        exit 1
    fi
    
    log_info "Extracting to $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    tar xzf "/tmp/$tarball" -C "$INSTALL_DIR"
    rm -f "/tmp/$tarball"
    
    # Create ucm user
    if ! id -u ucm &>/dev/null; then
        log_info "Creating ucm user..."
        useradd -r -s /bin/bash -d "$INSTALL_DIR" -c "UCM Service" ucm 2>/dev/null || true
    fi
    
    # Setup Python venv
    log_info "Setting up Python environment..."
    cd "$INSTALL_DIR/backend"
    python3 -m venv venv
    source venv/bin/activate
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    
    # Initialize database
    log_info "Initializing database..."
    mkdir -p "$INSTALL_DIR/backend/data"/{ca,certs,private,crl,backups,scep}
    
    if [ ! -f "$INSTALL_DIR/backend/data/ucm.db" ]; then
        python3 init_db.py
    fi
    
    # Install systemd service
    log_info "Installing systemd service..."
    cat > /etc/systemd/system/ucm.service << 'SERVICEEOF'
[Unit]
Description=Ultimate CA Manager
After=network.target

[Service]
Type=simple
User=ucm
Group=ucm
WorkingDirectory=/opt/ucm/backend
Environment="PATH=/opt/ucm/backend/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/opt/ucm/backend/venv/bin/gunicorn --config /opt/ucm/backend/gunicorn_config.py wsgi:application
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICEEOF
    
    # Set permissions
    log_info "Setting permissions..."
    chown -R ucm:ucm "$INSTALL_DIR"
    chmod -R 750 "$INSTALL_DIR"
    chmod 700 "$INSTALL_DIR/backend/data"
    
    systemctl daemon-reload
    
    log_success "Source installation complete"
}

# Main installation logic
main() {
    banner
    check_root
    detect_system
    
    echo ""
    log_info "Choose installation method:"
    echo ""
    
    local method=""
    
    # Offer native package if available
    if can_use_native_package; then
        case "$OS_ID" in
            ubuntu|debian|linuxmint|pop)
                echo "  1) Native DEB package (Recommended)"
                echo "  2) From source tarball"
                ;;
            rhel|rocky|almalinux|centos|fedora)
                echo "  1) Native RPM package (Recommended)"
                echo "  2) From source tarball"
                ;;
        esac
        
        echo ""
        read -p "Select option [1]: " choice < /dev/tty
        choice=${choice:-1}
        
        if [ "$choice" = "1" ]; then
            case "$OS_ID" in
                ubuntu|debian|linuxmint|pop)
                    method="deb"
                    ;;
                rhel|rocky|almalinux|centos|fedora)
                    method="rpm"
                    ;;
            esac
        else
            method="source"
        fi
    else
        log_warn "No native package available for $OS_NAME"
        log_info "Will install from source"
        method="source"
        sleep 2
    fi
    
    echo ""
    
    # Install
    if [ "$method" = "deb" ] || [ "$method" = "rpm" ]; then
        if install_native_package "$method"; then
            show_success
            exit 0
        else
            log_warn "Native package install failed, trying source..."
            method="source"
        fi
    fi
    
    if [ "$method" = "source" ]; then
        install_dependencies
        install_from_source
        show_success
    fi
}

show_success() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}              ${GREEN}Installation Complete!${NC}                       ${GREEN}║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    log_info "Start the service:"
    echo -e "  ${CYAN}sudo systemctl enable --now ucm${NC}"
    echo ""
    
    log_info "Check status:"
    echo -e "  ${CYAN}sudo systemctl status ucm${NC}"
    echo ""
    
    log_info "Access UCM:"
    if command -v hostname &> /dev/null; then
        echo -e "  ${CYAN}https://$(hostname -f 2>/dev/null || hostname):8443${NC}"
    fi
    echo -e "  ${CYAN}https://localhost:8443${NC}"
    echo ""
    
    log_warn "Default credentials:"
    echo -e "  Username: ${YELLOW}admin${NC}"
    echo -e "  Password: ${YELLOW}changeme123${NC}"
    echo ""
    
    echo -e "${RED}⚠️  CHANGE THE PASSWORD IMMEDIATELY AFTER FIRST LOGIN!${NC}"
    echo ""
    
    log_info "Documentation: https://github.com/$GITHUB_REPO/wiki"
    echo ""
}

main "$@"
