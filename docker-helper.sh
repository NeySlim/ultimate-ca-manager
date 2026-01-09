#!/bin/bash
# UCM v1.8.0-beta - Docker Helper Script
# Interactive deployment and management tool

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

# Banner
echo -e "${CYAN}"
cat << "EOF"
╔════════════════════════════════════════╗
║  Ultimate CA Manager - Docker Setup   ║
║  Version 1.8.0-beta                    ║
╚════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check dependencies
check_dependencies() {
    local missing=()
    
    command -v docker >/dev/null 2>&1 || missing+=("docker")
    command -v docker-compose >/dev/null 2>&1 || missing+=("docker-compose")
    
    if [ ${#missing[@]} -gt 0 ]; then
        echo -e "${RED}❌ Missing dependencies: ${missing[*]}${NC}"
        echo ""
        echo "Install with:"
        echo "  • Docker: https://docs.docker.com/get-docker/"
        echo "  • Docker Compose: https://docs.docker.com/compose/install/"
        exit 1
    fi
}

# Main menu
show_menu() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║           Main Menu                    ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${GREEN}Deployment:${NC}"
    echo "  1) 🚀 Quick Start (Development)"
    echo "  2) 🏢 Production Deployment"
    echo "  3) ⚙️  Custom Configuration"
    echo ""
    echo -e "${GREEN}Management:${NC}"
    echo "  4) 📊 View Status"
    echo "  5) 📝 View Logs"
    echo "  6) 🔄 Restart Container"
    echo "  7) 🛑 Stop Container"
    echo "  8) 🗑️  Remove Container"
    echo ""
    echo -e "${GREEN}Maintenance:${NC}"
    echo "  9) 💾 Backup Database"
    echo " 10) 📦 Update UCM"
    echo " 11) 🔐 Generate Secrets"
    echo " 12) 🧹 Clean Up"
    echo ""
    echo "  0) ❌ Exit"
    echo ""
    read -p "Select option: " choice
    echo ""
    
    case $choice in
        1) quick_start ;;
        2) production_deployment ;;
        3) custom_configuration ;;
        4) view_status ;;
        5) view_logs ;;
        6) restart_container ;;
        7) stop_container ;;
        8) remove_container ;;
        9) backup_database ;;
        10) update_ucm ;;
        11) generate_secrets ;;
        12) cleanup ;;
        0) exit 0 ;;
        *) echo -e "${RED}Invalid option${NC}"; show_menu ;;
    esac
}

# Quick start
quick_start() {
    echo -e "${BLUE}🚀 Quick Start Deployment${NC}"
    echo ""
    
    # Check if .env exists
    if [ -f .env ]; then
        echo -e "${YELLOW}⚠️  .env file already exists${NC}"
        read -p "Overwrite? (y/N): " overwrite
        if [[ ! $overwrite =~ ^[Yy]$ ]]; then
            show_menu
            return
        fi
    fi
    
    # Get FQDN
    read -p "Enter FQDN (e.g., ucm.example.com): " fqdn
    if [ -z "$fqdn" ]; then
        echo -e "${RED}❌ FQDN is required${NC}"
        show_menu
        return
    fi
    
    # Create .env
    cat > .env <<EOF
UCM_FQDN=$fqdn
UCM_HTTPS_PORT=8443
UCM_DEBUG=false
UCM_LOG_LEVEL=INFO
UCM_CACHE_ENABLED=true
UCM_BACKUP_ENABLED=true
EOF
    
    echo -e "${GREEN}✅ Configuration created${NC}"
    
    # Start container
    echo ""
    echo -e "${BLUE}Starting container...${NC}"
    docker-compose up -d
    
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║     UCM Started Successfully! 🎉       ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Access your UCM instance:${NC}"
    echo "  • URL: https://$fqdn:8443"
    echo "  • Username: admin"
    echo "  • Password: changeme123"
    echo ""
    echo -e "${RED}⚠️  CHANGE THE PASSWORD IMMEDIATELY!${NC}"
    echo ""
    
    read -p "Press Enter to continue..."
    show_menu
}

# Production deployment
production_deployment() {
    echo -e "${BLUE}🏢 Production Deployment${NC}"
    echo ""
    
    # FQDN
    read -p "FQDN: " fqdn
    [ -z "$fqdn" ] && { echo -e "${RED}Required${NC}"; show_menu; return; }
    
    # SMTP
    echo ""
    echo -e "${CYAN}SMTP Configuration (for email alerts)${NC}"
    read -p "Enable SMTP? (y/N): " smtp_enabled
    
    if [[ $smtp_enabled =~ ^[Yy]$ ]]; then
        read -p "  SMTP Server: " smtp_server
        read -p "  SMTP Port [587]: " smtp_port
        smtp_port=${smtp_port:-587}
        read -p "  SMTP Username: " smtp_user
        read -sp "  SMTP Password: " smtp_pass
        echo ""
        read -p "  From Address: " smtp_from
        smtp_enabled="true"
    else
        smtp_enabled="false"
    fi
    
    # Generate secrets
    echo ""
    echo -e "${CYAN}Generating secrets...${NC}"
    secret_key=$(openssl rand -hex 32)
    jwt_secret=$(openssl rand -hex 32)
    
    # Create .env
    cat > .env <<EOF
UCM_FQDN=$fqdn
UCM_HTTPS_PORT=8443
UCM_DEBUG=false
UCM_LOG_LEVEL=WARNING
UCM_SECRET_KEY=$secret_key
UCM_JWT_SECRET=$jwt_secret
UCM_SMTP_ENABLED=$smtp_enabled
EOF
    
    if [ "$smtp_enabled" = "true" ]; then
        cat >> .env <<EOF
UCM_SMTP_SERVER=$smtp_server
UCM_SMTP_PORT=$smtp_port
UCM_SMTP_USERNAME=$smtp_user
UCM_SMTP_PASSWORD=$smtp_pass
UCM_SMTP_FROM=$smtp_from
UCM_SMTP_TLS=true
EOF
    fi
    
    echo -e "${GREEN}✅ Configuration created${NC}"
    
    # Start with production config
    echo ""
    echo -e "${BLUE}Starting in production mode...${NC}"
    docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
    
    echo ""
    echo -e "${GREEN}✅ Production deployment complete!${NC}"
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "  1. Access: https://$fqdn:8443"
    echo "  2. Login: admin / changeme123"
    echo "  3. Change password immediately"
    echo "  4. Configure reverse proxy (Nginx/Apache)"
    echo "  5. Set up trusted HTTPS certificate"
    echo ""
    
    read -p "Press Enter to continue..."
    show_menu
}

# Custom configuration
custom_configuration() {
    echo -e "${BLUE}⚙️  Custom Configuration${NC}"
    echo ""
    echo "Edit .env file manually with your preferred editor"
    echo ""
    echo "Available editors:"
    command -v nano >/dev/null && echo "  • nano .env"
    command -v vim >/dev/null && echo "  • vim .env"
    command -v code >/dev/null && echo "  • code .env"
    echo ""
    echo "See .env.example for all available options"
    echo ""
    
    read -p "Press Enter to continue..."
    show_menu
}

# View status
view_status() {
    echo -e "${BLUE}📊 Container Status${NC}"
    echo ""
    
    docker-compose ps
    
    echo ""
    docker stats --no-stream ucm 2>/dev/null || echo "Container not running"
    
    echo ""
    read -p "Press Enter to continue..."
    show_menu
}

# View logs
view_logs() {
    echo -e "${BLUE}📝 Container Logs${NC}"
    echo ""
    echo "Press Ctrl+C to stop viewing logs"
    echo ""
    sleep 2
    
    docker-compose logs -f --tail=100 ucm
    
    show_menu
}

# Restart container
restart_container() {
    echo -e "${BLUE}🔄 Restarting container...${NC}"
    docker-compose restart
    echo -e "${GREEN}✅ Container restarted${NC}"
    
    read -p "Press Enter to continue..."
    show_menu
}

# Stop container
stop_container() {
    echo -e "${YELLOW}🛑 Stopping container...${NC}"
    docker-compose stop
    echo -e "${GREEN}✅ Container stopped${NC}"
    
    read -p "Press Enter to continue..."
    show_menu
}

# Remove container
remove_container() {
    echo -e "${RED}🗑️  Remove Container${NC}"
    echo ""
    echo -e "${YELLOW}⚠️  WARNING: This will remove the container${NC}"
    echo "   Data volume will be preserved"
    echo ""
    read -p "Are you sure? (yes/NO): " confirm
    
    if [ "$confirm" = "yes" ]; then
        docker-compose down
        echo -e "${GREEN}✅ Container removed${NC}"
    else
        echo -e "${CYAN}Cancelled${NC}"
    fi
    
    read -p "Press Enter to continue..."
    show_menu
}

# Backup database
backup_database() {
    echo -e "${BLUE}💾 Database Backup${NC}"
    echo ""
    
    backup_file="ucm-backup-$(date +%Y%m%d-%H%M%S).db"
    
    echo "Creating backup: $backup_file"
    docker cp ucm:/app/backend/data/ucm.db "./$backup_file"
    
    echo ""
    echo -e "${GREEN}✅ Backup created: $backup_file${NC}"
    echo ""
    ls -lh "$backup_file"
    
    read -p "Press Enter to continue..."
    show_menu
}

# Update UCM
update_ucm() {
    echo -e "${BLUE}📦 Update UCM${NC}"
    echo ""
    
    # Backup first
    echo "Creating backup before update..."
    backup_file="ucm-backup-before-update-$(date +%Y%m%d-%H%M%S).db"
    docker cp ucm:/app/backend/data/ucm.db "./$backup_file" 2>/dev/null || true
    
    echo ""
    echo "Pulling latest image..."
    docker-compose pull
    
    echo ""
    echo "Restarting with new version..."
    docker-compose up -d
    
    echo ""
    echo -e "${GREEN}✅ Update complete${NC}"
    echo ""
    docker-compose exec ucm python3 --version || true
    
    read -p "Press Enter to continue..."
    show_menu
}

# Generate secrets
generate_secrets() {
    echo -e "${BLUE}🔐 Generate Secrets${NC}"
    echo ""
    
    secret_key=$(openssl rand -hex 32)
    jwt_secret=$(openssl rand -hex 32)
    
    echo -e "${GREEN}Generated secrets:${NC}"
    echo ""
    echo "SECRET_KEY=$secret_key"
    echo "JWT_SECRET=$jwt_secret"
    echo ""
    echo -e "${YELLOW}Add these to your .env file${NC}"
    echo ""
    
    read -p "Press Enter to continue..."
    show_menu
}

# Cleanup
cleanup() {
    echo -e "${BLUE}🧹 Cleanup${NC}"
    echo ""
    
    echo "Available cleanup options:"
    echo "  1) Remove unused images"
    echo "  2) Remove old backups"
    echo "  3) Full cleanup (images + volumes)"
    echo "  0) Cancel"
    echo ""
    read -p "Select: " cleanup_choice
    
    case $cleanup_choice in
        1)
            docker image prune -f
            echo -e "${GREEN}✅ Unused images removed${NC}"
            ;;
        2)
            find . -name "ucm-backup-*.db" -mtime +30 -delete
            echo -e "${GREEN}✅ Old backups removed${NC}"
            ;;
        3)
            echo -e "${RED}⚠️  This will remove ALL unused Docker resources${NC}"
            read -p "Are you sure? (yes/NO): " confirm
            if [ "$confirm" = "yes" ]; then
                docker system prune -af
                echo -e "${GREEN}✅ Full cleanup complete${NC}"
            fi
            ;;
        *)
            echo "Cancelled"
            ;;
    esac
    
    echo ""
    read -p "Press Enter to continue..."
    show_menu
}

# Main
main() {
    check_dependencies
    show_menu
}

main
