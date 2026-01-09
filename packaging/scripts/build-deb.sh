#!/bin/bash
# Build UCM Debian Package

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     UCM Debian Package Builder        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Check we're in the right directory
if [ ! -f "backend/app.py" ]; then
    echo -e "${RED}Error: Must be run from UCM source root${NC}"
    exit 1
fi

# Check dependencies
echo -e "${YELLOW}Checking build dependencies...${NC}"
MISSING_DEPS=()

command -v dpkg-buildpackage >/dev/null 2>&1 || MISSING_DEPS+=("dpkg-dev")
command -v debhelper >/dev/null 2>&1 || MISSING_DEPS+=("debhelper")

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo -e "${RED}Missing dependencies: ${MISSING_DEPS[*]}${NC}"
    echo "Install with: sudo apt-get install ${MISSING_DEPS[*]}"
    exit 1
fi

echo -e "${GREEN}✓ Build dependencies OK${NC}"
echo ""

# Get version
if [ -z "$1" ]; then
    echo -e "${YELLOW}Version not specified, reading from git tag...${NC}"
    VERSION=$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//' || echo "1.8.0-beta")
else
    VERSION="$1"
fi

echo -e "${CYAN}Building version: $VERSION${NC}"
echo ""

# Generate changelog
echo -e "${YELLOW}Generating changelog...${NC}"
./packaging/scripts/generate-changelog.sh "$VERSION"
echo ""

# Create debian directory if it doesn't exist
if [ ! -d "debian" ]; then
    ln -s packaging/debian debian
fi

# Clean previous builds
echo -e "${YELLOW}Cleaning previous builds...${NC}"
rm -rf ../ucm_*.deb ../ucm_*.changes ../ucm_*.buildinfo ../ucm_*.tar.* 2>/dev/null || true
echo -e "${GREEN}✓ Clean complete${NC}"
echo ""

# Build package
echo -e "${YELLOW}Building Debian package...${NC}"
echo ""

dpkg-buildpackage -us -uc -b

# Check if build succeeded
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   Build Successful! 🎉                ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo ""
    
    # List generated files
    echo -e "${CYAN}Generated files:${NC}"
    ls -lh ../ucm_*.deb 2>/dev/null || true
    echo ""
    
    DEB_FILE=$(ls -1 ../ucm_*.deb 2>/dev/null | head -1)
    if [ -n "$DEB_FILE" ]; then
        echo -e "${CYAN}Install with:${NC}"
        echo "  sudo dpkg -i $DEB_FILE"
        echo "  sudo apt-get install -f  # (if dependencies missing)"
        echo ""
        
        echo -e "${CYAN}Package info:${NC}"
        dpkg-deb --info "$DEB_FILE" | head -20
    fi
else
    echo -e "${RED}Build failed!${NC}"
    exit 1
fi
