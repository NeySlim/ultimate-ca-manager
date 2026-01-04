#!/bin/bash
#
# Create UCM distribution package
#

set -e

VERSION="1.0.0"
PACKAGE_NAME="ucm-${VERSION}"
BUILD_DIR="/tmp/ucm-build"
DIST_DIR="/root"

echo "📦 Creating UCM distribution package..."
echo "========================================"

# Clean and prepare
echo "Cleaning build directory..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/$PACKAGE_NAME"

# Copy source files
echo "Copying source files..."
cd /root/ucm-src

# Copy visible files
cp -r backend frontend scripts docs *.sh *.md *.py "$BUILD_DIR/$PACKAGE_NAME/" 2>/dev/null || true

# Copy hidden files explicitly
cp .env.example "$BUILD_DIR/$PACKAGE_NAME/" 2>/dev/null || true
cp .gitignore "$BUILD_DIR/$PACKAGE_NAME/" 2>/dev/null || true

# Copy any other hidden files if they exist
shopt -s dotglob
for file in .[^.]*; do
    if [ -f "$file" ]; then
        cp "$file" "$BUILD_DIR/$PACKAGE_NAME/" 2>/dev/null || true
    fi
done
shopt -u dotglob

# Ensure clean state
echo "Ensuring clean state..."
cd "$BUILD_DIR/$PACKAGE_NAME"

# Remove any runtime data
rm -rf backend/data/*.db
rm -rf backend/data/*.log
rm -rf backend/data/*.pem
rm -rf backend/data/ca/* backend/data/certs/* backend/data/crl/*
rm -rf backend/data/scep/* backend/data/private/* backend/data/backups/*
rm -rf venv/ __pycache__ *.pyc cookies.txt

# Remove .env (keep only .env.example)
rm -f .env

# Keep .gitkeep files
find backend/data -type d -exec touch {}/.gitkeep \;

# Create VERSION file
echo "$VERSION" > VERSION

# Create MANIFEST file
cat > MANIFEST << MANIFEST
UCM Distribution Package
Version: $VERSION
Build Date: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
Build Host: $(hostname)

Contents:
  • UCM Source Code
  • Installation Scripts
  • Documentation
  • Systemd Service Files

Installation:
  sudo ./install.sh

Documentation:
  README.md
  INSTALLATION.md
  docs/
MANIFEST

# Set permissions
echo "Setting permissions..."
chmod +x install.sh uninstall.sh upgrade.sh
chmod +x scripts/*.sh 2>/dev/null || true

# Create tarball
echo "Creating tarball..."
cd "$BUILD_DIR"
tar -czf "$DIST_DIR/${PACKAGE_NAME}.tar.gz" "$PACKAGE_NAME/"

# Create checksums
echo "Creating checksums..."
cd "$DIST_DIR"
sha256sum "${PACKAGE_NAME}.tar.gz" > "${PACKAGE_NAME}.tar.gz.sha256"
md5sum "${PACKAGE_NAME}.tar.gz" > "${PACKAGE_NAME}.tar.gz.md5"

# Clean up
echo "Cleaning up..."
rm -rf "$BUILD_DIR"

# Display results
echo ""
echo "✅ Package created successfully!"
echo ""
echo "📦 Package Information:"
echo "   File: ${PACKAGE_NAME}.tar.gz"
echo "   Location: $DIST_DIR"
echo "   Size: $(du -h "$DIST_DIR/${PACKAGE_NAME}.tar.gz" | cut -f1)"
echo ""
echo "📋 Checksums:"
echo "   SHA256: $(cat "${PACKAGE_NAME}.tar.gz.sha256" | cut -d' ' -f1)"
echo "   MD5:    $(cat "${PACKAGE_NAME}.tar.gz.md5" | cut -d' ' -f1)"
echo ""
echo "🚀 To install on target system:"
echo "   1. Transfer ${PACKAGE_NAME}.tar.gz to target"
echo "   2. tar -xzf ${PACKAGE_NAME}.tar.gz"
echo "   3. cd ${PACKAGE_NAME}"
echo "   4. sudo ./install.sh"
echo ""
