#!/bin/bash
# UCM Docker Entrypoint Script
# Handles initialization and environment setup

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Ultimate CA Manager - Docker         ║${NC}"
echo -e "${GREEN}║  Version 1.0.0                         ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""

# Check if .env exists, if not create from example
if [ ! -f /app/.env ]; then
    echo -e "${YELLOW}⚠️  Creating .env from example...${NC}"
    cp /app/.env.example /app/.env
    
    # Generate random secrets if running in Docker
    if [ -n "$UCM_DOCKER" ]; then
        SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
        JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
        
        sed -i "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" /app/.env
        sed -i "s/JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$JWT_SECRET/" /app/.env
    fi
    echo -e "${GREEN}✅ Configuration created${NC}"
fi

# Override with environment variables if provided
if [ -n "$UCM_SECRET_KEY" ]; then
    sed -i "s/SECRET_KEY=.*/SECRET_KEY=$UCM_SECRET_KEY/" /app/.env
fi

if [ -n "$UCM_JWT_SECRET" ]; then
    sed -i "s/JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$UCM_JWT_SECRET/" /app/.env
fi

if [ -n "$UCM_DATABASE_PATH" ]; then
    sed -i "s|DATABASE_PATH=.*|DATABASE_PATH=$UCM_DATABASE_PATH|" /app/.env
fi

if [ -n "$UCM_HTTPS_PORT" ]; then
    sed -i "s/HTTPS_PORT=.*/HTTPS_PORT=$UCM_HTTPS_PORT/" /app/.env
fi

# Check data directory permissions
if [ ! -w /app/backend/data ]; then
    echo -e "${RED}❌ Data directory is not writable!${NC}"
    echo "   Please check volume permissions"
    exit 1
fi

echo -e "${GREEN}✅ Data directory is writable${NC}"

# Check if HTTPS certificate exists, if not generate it
if [ ! -f /app/backend/data/https_cert.pem ] || [ ! -f /app/backend/data/https_key.pem ]; then
    echo -e "${YELLOW}📝 Generating self-signed HTTPS certificate...${NC}"
    
    # Generate self-signed certificate
    openssl req -x509 -newkey rsa:4096 -nodes \
        -keyout /app/backend/data/https_key.pem \
        -out /app/backend/data/https_cert.pem \
        -days 365 \
        -subj "/C=US/ST=State/L=City/O=UCM/CN=ucm.local" \
        2>/dev/null
    
    echo -e "${GREEN}✅ Certificate generated${NC}"
fi

# Check if database exists
if [ ! -f /app/backend/data/ucm.db ]; then
    echo -e "${YELLOW}📝 First run detected - database will be auto-created${NC}"
    echo "   Default credentials: admin / changeme123"
    echo -e "   ${RED}⚠️  CHANGE THIS PASSWORD IMMEDIATELY!${NC}"
fi

# Display configuration
echo ""
echo -e "${GREEN}📋 Configuration:${NC}"
echo "   • Data directory: /app/backend/data"
echo "   • HTTPS port: ${UCM_HTTPS_PORT:-8443}"
echo "   • Database: $([ -f /app/backend/data/ucm.db ] && echo 'Exists' || echo 'Will be created')"
echo ""

echo -e "${GREEN}🚀 Starting UCM...${NC}"
echo ""

# Execute the main command
exec "$@"
