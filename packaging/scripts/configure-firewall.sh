#!/bin/bash
# =============================================================================
# UCM Firewall Configuration Script
# =============================================================================
# This script configures firewall rules for UCM.
# It supports both firewalld (RHEL/Fedora) and ufw (Debian/Ubuntu).
#
# Usage:
#   Interactive:     ./configure-firewall.sh
#   Non-interactive: UCM_PORT=8443 UCM_FIREWALL=yes ./configure-firewall.sh
#
# Environment Variables:
#   UCM_PORT      - HTTPS port (default: 8443)
#   UCM_FIREWALL  - Open firewall: yes/no/ask (default: ask)
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Defaults
DEFAULT_PORT=8443

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

is_interactive() {
    # Check if running interactively (not piped, has tty)
    [ -t 0 ] && [ -t 1 ]
}

# =============================================================================
# Detect Firewall System
# =============================================================================

detect_firewall() {
    if command -v firewall-cmd &> /dev/null && systemctl is-active --quiet firewalld 2>/dev/null; then
        echo "firewalld"
    elif command -v ufw &> /dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
        echo "ufw"
    elif command -v iptables &> /dev/null; then
        echo "iptables"
    else
        echo "none"
    fi
}

# =============================================================================
# Get Configuration
# =============================================================================

get_port() {
    if [ -n "$UCM_PORT" ]; then
        echo "$UCM_PORT"
        return
    fi
    
    # Try to read from existing config
    if [ -f /etc/ucm/ucm.env ]; then
        local existing_port=$(grep "^HTTPS_PORT=" /etc/ucm/ucm.env 2>/dev/null | cut -d= -f2)
        if [ -n "$existing_port" ]; then
            DEFAULT_PORT="$existing_port"
        fi
    fi
    
    if is_interactive && [ "$UCM_FIREWALL" != "no" ]; then
        read -p "HTTPS port [$DEFAULT_PORT]: " input_port
        echo "${input_port:-$DEFAULT_PORT}"
    else
        echo "$DEFAULT_PORT"
    fi
}

get_firewall_choice() {
    if [ -n "$UCM_FIREWALL" ]; then
        case "$UCM_FIREWALL" in
            yes|y|Y|true|1) echo "yes" ;;
            no|n|N|false|0) echo "no" ;;
            *) echo "ask" ;;
        esac
        return
    fi
    
    if is_interactive; then
        read -p "Open firewall for UCM? [Y/n]: " choice
        case "$choice" in
            n|N|no|NO) echo "no" ;;
            *) echo "yes" ;;
        esac
    else
        # Non-interactive without env var: don't change firewall
        echo "no"
    fi
}

# =============================================================================
# Configure Firewall
# =============================================================================

configure_firewalld() {
    local port=$1
    
    log_info "Configuring firewalld for port $port..."
    
    # Install UCM service definition with correct port
    local service_file="/usr/lib/firewalld/services/ucm.xml"
    cat > "$service_file" << EOF
<?xml version="1.0" encoding="utf-8"?>
<service>
  <short>UCM</short>
  <description>Ultimate CA Manager - PKI Certificate Management Platform</description>
  <port protocol="tcp" port="$port"/>
</service>
EOF
    
    # Reload firewalld to recognize new service
    firewall-cmd --reload --quiet
    
    # Add service to default zone
    if firewall-cmd --permanent --add-service=ucm 2>/dev/null; then
        firewall-cmd --reload --quiet
        log_info "✓ Firewall configured: UCM service added (port $port/tcp)"
    else
        # Fallback: add port directly
        if firewall-cmd --permanent --add-port="$port/tcp" 2>/dev/null; then
            firewall-cmd --reload --quiet
            log_info "✓ Firewall configured: port $port/tcp opened"
        else
            log_error "Failed to configure firewall"
            return 1
        fi
    fi
}

configure_ufw() {
    local port=$1
    
    log_info "Configuring ufw for port $port..."
    
    # Install UCM application profile with correct port
    cat > /etc/ufw/applications.d/ucm << EOF
[UCM]
title=Ultimate CA Manager
description=PKI Certificate Management Platform
ports=$port/tcp
EOF
    
    # Allow UCM through firewall
    if ufw allow ucm 2>/dev/null; then
        log_info "✓ Firewall configured: UCM application allowed (port $port/tcp)"
    else
        # Fallback: allow port directly
        if ufw allow "$port/tcp" 2>/dev/null; then
            log_info "✓ Firewall configured: port $port/tcp allowed"
        else
            log_error "Failed to configure firewall"
            return 1
        fi
    fi
}

configure_iptables() {
    local port=$1
    
    log_info "Configuring iptables for port $port..."
    
    # Add rule if not already exists
    if ! iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
        iptables -I INPUT -p tcp --dport "$port" -j ACCEPT
        log_info "✓ iptables rule added for port $port/tcp"
        log_warn "Note: iptables rules are not persistent. Save them with your distro's method."
    else
        log_info "✓ iptables rule already exists for port $port/tcp"
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    # Must be root
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root"
        exit 1
    fi
    
    # Get configuration
    local port=$(get_port)
    local firewall_choice=$(get_firewall_choice)
    
    if [ "$firewall_choice" = "no" ]; then
        log_info "Skipping firewall configuration"
        exit 0
    fi
    
    # Detect and configure firewall
    local firewall_type=$(detect_firewall)
    
    case "$firewall_type" in
        firewalld)
            configure_firewalld "$port"
            ;;
        ufw)
            configure_ufw "$port"
            ;;
        iptables)
            configure_iptables "$port"
            ;;
        none)
            log_warn "No active firewall detected. Skipping configuration."
            ;;
    esac
    
    echo ""
    log_info "UCM will be accessible at: https://<hostname>:$port"
}

main "$@"
