#!/bin/bash
#
# UCM RPM Package Builder
# Version: 1.0.0
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  UCM RPM Package Builder               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Configuration
VERSION=${1:-"1.8.0"}
RELEASE=${2:-"1"}
RPMBUILD_DIR="${HOME}/rpmbuild"

echo -e "${BLUE}📦 Configuration:${NC}"
echo "   Version: $VERSION"
echo "   Release: $RELEASE"
echo "   Build dir: $RPMBUILD_DIR"
echo ""

# Check for required tools
echo -e "${YELLOW}🔧 Checking dependencies...${NC}"
for cmd in rpmbuild tar; do
    if ! command -v $cmd &> /dev/null; then
        echo -e "${RED}❌ $cmd not found${NC}"
        echo "   Install with: sudo dnf install rpm-build"
        exit 1
    fi
    echo -e "${GREEN}✅ $cmd found${NC}"
done

# Create rpmbuild structure
echo ""
echo -e "${YELLOW}📁 Creating rpmbuild structure...${NC}"
for dir in BUILD RPMS SOURCES SPECS SRPMS; do
    mkdir -p "$RPMBUILD_DIR/$dir"
    echo "   Created: $dir/"
done

# Create source tarball
echo ""
echo -e "${YELLOW}📦 Creating source tarball...${NC}"
TARBALL_NAME="ucm-${VERSION}.tar.gz"
TARBALL_PATH="$RPMBUILD_DIR/SOURCES/$TARBALL_NAME"

cd "$PROJECT_ROOT"

# Create temp directory for tarball creation
TEMP_DIR=$(mktemp -d)
PKG_DIR="$TEMP_DIR/ucm-${VERSION}"
mkdir -p "$PKG_DIR"

# Copy application files
echo "   Copying application files..."
cp -r backend "$PKG_DIR/"
cp -r frontend "$PKG_DIR/"
cp -r scripts "$PKG_DIR/" 2>/dev/null || true
cp -r packaging "$PKG_DIR/"
cp backend/requirements.txt "$PKG_DIR/"
cp gunicorn.conf.py "$PKG_DIR/"
cp wsgi.py "$PKG_DIR/"
cp README.md "$PKG_DIR/" 2>/dev/null || true
cp LICENSE "$PKG_DIR/" 2>/dev/null || true

# Clean up
echo "   Cleaning up..."
find "$PKG_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PKG_DIR" -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
find "$PKG_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$PKG_DIR" -type f -name "*.pyo" -delete 2>/dev/null || true
find "$PKG_DIR" -type f -name ".DS_Store" -delete 2>/dev/null || true

# Create tarball
cd "$TEMP_DIR"
tar czf "$TARBALL_PATH" "ucm-${VERSION}/"
rm -rf "$TEMP_DIR"

TARBALL_SIZE=$(du -h "$TARBALL_PATH" | cut -f1)
echo -e "${GREEN}✅ Tarball created: $TARBALL_SIZE${NC}"

# Copy spec file
echo ""
echo -e "${YELLOW}📝 Copying spec file...${NC}"
SPEC_FILE="$RPMBUILD_DIR/SPECS/ucm.spec"
cp "$PROJECT_ROOT/packaging/rpm/ucm.spec" "$SPEC_FILE"

# Update version in spec file
sed -i "s/^Version:.*/Version:        $VERSION/" "$SPEC_FILE"
sed -i "s/^Release:.*/Release:        $RELEASE%{?dist}/" "$SPEC_FILE"
echo -e "${GREEN}✅ Spec file ready${NC}"

# Build RPM
echo ""
echo -e "${YELLOW}🔨 Building RPM package...${NC}"
echo ""

rpmbuild -bb "$SPEC_FILE" 2>&1 | while IFS= read -r line; do
    if [[ $line == *"error"* ]] || [[ $line == *"Error"* ]]; then
        echo -e "${RED}$line${NC}"
    elif [[ $line == *"warning"* ]] || [[ $line == *"Warning"* ]]; then
        echo -e "${YELLOW}$line${NC}"
    else
        echo "$line"
    fi
done

# Check for built RPMs
echo ""
echo -e "${YELLOW}📦 Built packages:${NC}"
ARCH_DIR=$(ls -d "$RPMBUILD_DIR/RPMS"/* 2>/dev/null | head -1)
if [ -d "$ARCH_DIR" ]; then
    for rpm in "$ARCH_DIR"/ucm-*.rpm; do
        if [ -f "$rpm" ]; then
            SIZE=$(du -h "$rpm" | cut -f1)
            echo -e "${GREEN}✅ $(basename "$rpm") ($SIZE)${NC}"
            
            # Copy to project directory
            cp "$rpm" "$PROJECT_ROOT/"
            echo "   Copied to: $PROJECT_ROOT/"
        fi
    done
else
    echo -e "${RED}❌ No RPM files found${NC}"
    exit 1
fi

# Generate checksums
echo ""
echo -e "${YELLOW}🔐 Generating checksums...${NC}"
cd "$PROJECT_ROOT"
for rpm in ucm-*.rpm; do
    if [ -f "$rpm" ]; then
        md5sum "$rpm" > "$rpm.md5"
        sha256sum "$rpm" > "$rpm.sha256"
        echo -e "${GREEN}✅ $rpm.md5${NC}"
        echo -e "${GREEN}✅ $rpm.sha256${NC}"
    fi
done

# Summary
echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  RPM BUILD COMPLETE!                   ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📦 Installation:${NC}"
echo "   sudo dnf install ./ucm-${VERSION}-${RELEASE}.*.rpm"
echo ""
echo -e "${BLUE}🚀 Post-install:${NC}"
echo "   1. Review: /etc/ucm/.env"
echo "   2. Start: sudo systemctl start ucm"
echo "   3. Enable: sudo systemctl enable ucm"
echo "   4. Access: https://\$(hostname -f):8443"
echo ""
