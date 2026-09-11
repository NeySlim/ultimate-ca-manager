#!/bin/bash
# Build UCM Debian Package

set -e

# Colors
RED='\033[0;31m'
CYAN='\033[0;36m'
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
# debhelper ships no binary of that name; dh is the one it provides
command -v dh >/dev/null 2>&1 || MISSING_DEPS+=("debhelper")

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo -e "${RED}Missing dependencies: ${MISSING_DEPS[*]}${NC}"
    echo "Install with: sudo apt-get install ${MISSING_DEPS[*]}"
    exit 1
fi

echo -e "${GREEN}✓ Build dependencies OK${NC}"
echo ""

# Get version
if [ -z "$1" ]; then
    echo -e "${YELLOW}Version not specified, reading the VERSION file...${NC}"
    # The || never fired here: a pipeline's status is its last command's, and
    # sed succeeds on empty input. Read the version this checkout carries, and
    # fall back to the latest tag only if that file is missing.
    # The script already refuses to run anywhere but the source root
    if [ -f VERSION ]; then
        VERSION=$(tr -d '\n' < VERSION)
    else
        VERSION=$(git describe --tags --abbrev=0 2>/dev/null | sed 's/^v//')
    fi
    if [ -z "$VERSION" ]; then
        echo -e "${RED}Cannot determine the version to build${NC}"
        exit 1
    fi
    # A dash separates the upstream version from the Debian revision, so
    # 2.229-dev would sort above the real 2.229-1 and make it look like a
    # downgrade. A tilde sorts before, which is what a pre-release needs, and
    # is what the release workflow writes too. Only what we read here is
    # rewritten: an explicit argument may legitimately carry a revision.
    VERSION=${VERSION//-/\~}
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
# Only this run's artefacts: the parent directory is shared with other
# checkouts, whose packages are none of our business
rm -rf ../ucm_"${VERSION}"_*.deb ../ucm_"${VERSION}"_*.changes \
       ../ucm_"${VERSION}"_*.buildinfo ../ucm_"${VERSION}".tar.* 2>/dev/null || true
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
    ls -lh ../ucm_"${VERSION}"_*.deb 2>/dev/null || true
    echo ""
    
    # Only the package this run produced, never one left in the parent
    DEB_FILE=$(ls -1 ../ucm_"${VERSION}"_*.deb 2>/dev/null | head -1)
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
