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
VERSION=${1:-}
RELEASE=${2:-"1"}
RPMBUILD_DIR="${HOME}/rpmbuild"

# Default to the version this checkout carries, and normalise whatever we end
# up with: RPM refuses a dash in the Version field. A tilde is the separator to
# use, because it sorts *before* the release it precedes: 2.229~dev is older
# than 2.229, while 2.229.dev would be newer and turn the real release into a
# downgrade for dnf.
if [ -z "$VERSION" ] && [ -f "$PROJECT_ROOT/VERSION" ]; then
    VERSION=$(tr -d '\n' < "$PROJECT_ROOT/VERSION")
fi
VERSION=${VERSION//-/\~}
if [ -z "$VERSION" ]; then
    echo -e "${RED}❌ Cannot determine the version to build${NC}"
    echo "   Pass it as the first argument, or check the VERSION file"
    exit 1
fi

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

# The spec installs frontend/dist and nothing else from the frontend
if [ ! -f frontend/dist/index.html ]; then
    echo -e "${RED}❌ frontend/dist holds no built interface${NC}"
    echo "   Build it first: cd frontend && npm run build"
    exit 1
fi

# Create temp directory for tarball creation
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT
PKG_DIR="$TEMP_DIR/ucm-${VERSION}"
mkdir -p "$PKG_DIR"

# Copy application files
echo "   Copying application files..."
cp -r backend "$PKG_DIR/"
# A working checkout also holds the database, the sessions and the private
# keys under backend/data, plus a virtual environment and caches. Shared with
# the Debian rules so the two cannot drift.
"$PROJECT_ROOT/packaging/scripts/prune-runtime-state.sh" "$PKG_DIR/backend"
# Only the built frontend goes in: frontend/ as a whole carries node_modules,
# hundreds of megabytes that would otherwise land in the source tarball
mkdir -p "$PKG_DIR/frontend"
cp -r frontend/dist "$PKG_DIR/frontend/"
cp -r scripts "$PKG_DIR/" 2>/dev/null || true
cp -r packaging "$PKG_DIR/"
# Both package builds stage a whole copy of backend/ under packaging/, secrets
# included, and leave it there
rm -rf "$PKG_DIR/packaging/debian/ucm" "$PKG_DIR/packaging/debian/.debhelper" \
       "$PKG_DIR/packaging/debian/files" "$PKG_DIR/packaging/debian/debhelper-build-stamp" \
       "$PKG_DIR/packaging/debian"/*.substvars "$PKG_DIR/packaging/debian"/*.debhelper.log \
       "$PKG_DIR/packaging/rpm/BUILD" "$PKG_DIR/packaging/rpm/BUILDROOT" \
       "$PKG_DIR/packaging/rpm/RPMS" "$PKG_DIR/packaging/rpm/SRPMS"
cp backend/requirements.txt "$PKG_DIR/"
cp wsgi.py "$PKG_DIR/"
# The spec installs this one as the package's version marker
cp VERSION "$PKG_DIR/"
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
# Leave the directory before the trap removes it, or every command that
# follows runs from a path that no longer exists
cd "$PROJECT_ROOT"

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

# The colouring loop must not swallow the build's verdict: without this, a
# failed build still exits 0 and the checks below happily pick up whatever
# package an earlier run left behind.
set -o pipefail
RPMBUILD_LOG="$RPMBUILD_DIR/last-build.log"
if ! rpmbuild -bb "$SPEC_FILE" 2>&1 | tee "$RPMBUILD_LOG" | while IFS= read -r line; do
    if [[ $line == *"error"* ]] || [[ $line == *"Error"* ]]; then
        echo -e "${RED}$line${NC}"
    elif [[ $line == *"warning"* ]] || [[ $line == *"Warning"* ]]; then
        echo -e "${YELLOW}$line${NC}"
    else
        echo "$line"
    fi
done; then
    echo ""
    echo -e "${RED}❌ rpmbuild failed${NC}"
    if grep -q '_unitdir' "$RPMBUILD_LOG" 2>/dev/null; then
        echo "   %{_unitdir} is undefined here, which happens on a distribution"
        echo "   without the systemd RPM macros: install systemd-rpm-macros, or"
        echo "   pass --define \"_unitdir /usr/lib/systemd/system\" to rpmbuild."
    fi
    exit 1
fi
set +o pipefail

# Check for built RPMs
echo ""
echo -e "${YELLOW}📦 Built packages:${NC}"
# Only the packages this run produced, never one left over from another
BUILT=0
for rpm in "$RPMBUILD_DIR/RPMS"/*/ucm-"${VERSION}"-"${RELEASE}".*.rpm; do
    [ -f "$rpm" ] || continue
    SIZE=$(du -h "$rpm" | cut -f1)
    echo -e "${GREEN}✅ $(basename "$rpm") ($SIZE)${NC}"
    cp "$rpm" "$PROJECT_ROOT/"
    echo "   Copied to: $PROJECT_ROOT/"
    BUILT=$((BUILT + 1))
done
if [ "$BUILT" -eq 0 ]; then
    echo -e "${RED}❌ No RPM built for ${VERSION}-${RELEASE}${NC}"
    exit 1
fi

# Generate checksums
echo ""
echo -e "${YELLOW}🔐 Generating checksums...${NC}"
cd "$PROJECT_ROOT"
for rpm in ucm-"${VERSION}"-"${RELEASE}".*.rpm; do
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
