#!/bin/bash
# Build Debian package for UCM

set -e

VERSION=$(cat VERSION)
PKG_NAME="ucm-${VERSION}"
BUILD_DIR="build"

echo "Building UCM Debian package version ${VERSION}"

# Clean previous build
rm -rf ${BUILD_DIR}
mkdir -p ${BUILD_DIR}/${PKG_NAME}

# Create directory structure
mkdir -p ${BUILD_DIR}/${PKG_NAME}/DEBIAN
mkdir -p ${BUILD_DIR}/${PKG_NAME}/opt/ucm
mkdir -p ${BUILD_DIR}/${PKG_NAME}/etc/systemd/system
mkdir -p ${BUILD_DIR}/${PKG_NAME}/usr/share/doc/ucm

# Copy application files
echo "Copying application files..."
cp -r backend frontend ${BUILD_DIR}/${PKG_NAME}/opt/ucm/
cp .env.example ${BUILD_DIR}/${PKG_NAME}/opt/ucm/
cp README.md INSTALLATION.md CHANGELOG.md ${BUILD_DIR}/${PKG_NAME}/usr/share/doc/ucm/

# Create control file
echo "Creating control file..."
cat > ${BUILD_DIR}/${PKG_NAME}/DEBIAN/control << EOF
Package: ucm
Version: ${VERSION}
Section: admin
Priority: optional
Architecture: all
Depends: python3 (>= 3.11), python3-pip, python3-venv, nginx, systemd
Maintainer: UCM Team <support@ucm.local>
Homepage: https://github.com/yourusername/ucm
Description: Ultimate CA Manager
 A comprehensive Certificate Authority management system.
 Features include:
  - CA creation and management
  - Certificate issuance and revocation
  - CRL distribution (RFC 5280 compliant)
  - OCSP responder
  - SCEP server
  - Multi-theme web interface
  - Custom styled scrollbars
  - Full dark mode support
EOF

# Create systemd service
echo "Creating systemd service..."
cat > ${BUILD_DIR}/${PKG_NAME}/etc/systemd/system/ucm.service << 'EOF'
[Unit]
Description=Ultimate CA Manager
After=network.target

[Service]
Type=simple
User=ucm
Group=ucm
WorkingDirectory=/opt/ucm
Environment="PATH=/opt/ucm/venv/bin"
ExecStart=/opt/ucm/venv/bin/gunicorn -c /opt/ucm/backend/gunicorn_config.py backend.app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create postinst script
echo "Creating postinst script..."
cat > ${BUILD_DIR}/${PKG_NAME}/DEBIAN/postinst << 'POSTINST'
#!/bin/bash
set -e

echo "Installing UCM..."

# Create ucm user if not exists
if ! id -u ucm > /dev/null 2>&1; then
    echo "Creating ucm user..."
    useradd -r -s /bin/bash -d /opt/ucm -m ucm
fi

# Set permissions
chown -R ucm:ucm /opt/ucm
chmod 755 /opt/ucm

# Create virtual environment
echo "Setting up Python virtual environment..."
cd /opt/ucm
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt

# Create data directories
bash -c 'mkdir -p /opt/ucm/data/{ca,certs,crl,ocsp,scep}'
chown -R ucm:ucm /opt/ucm/data

# Initialize database if not exists
if [ ! -f /opt/ucm/data/ucm.db ]; then
    echo "Initializing database..."
    sudo -u ucm venv/bin/python backend/init_db.py
fi

# Generate self-signed certificate for HTTPS
if [ ! -f /opt/ucm/data/ucm_https.crt ]; then
    echo "Generating self-signed HTTPS certificate..."
    openssl req -x509 -newkey rsa:4096 -nodes \
        -keyout /opt/ucm/data/ucm_https.key \
        -out /opt/ucm/data/ucm_https.crt \
        -days 3650 \
        -subj "/CN=UCM/O=UCM/C=US"
    chown ucm:ucm /opt/ucm/data/ucm_https.*
fi

# Enable and start service
echo "Enabling UCM service..."
systemctl daemon-reload
systemctl enable ucm.service
systemctl start ucm.service

echo ""
echo "=================================================="
echo "  UCM ${VERSION} installed successfully!"
echo "=================================================="
echo ""
echo "Access the web interface at:"
echo "  https://$(hostname -I | awk '{print $1}'):8443"
echo ""
echo "Default credentials:"
echo "  Username: admin"
echo "  Password: admin"
echo ""
echo "Please change the default password after first login!"
echo ""

exit 0
POSTINST

chmod 755 ${BUILD_DIR}/${PKG_NAME}/DEBIAN/postinst

# Create prerm script
echo "Creating prerm script..."
cat > ${BUILD_DIR}/${PKG_NAME}/DEBIAN/prerm << 'PRERM'
#!/bin/bash
set -e

echo "Stopping UCM service..."
systemctl stop ucm.service || true
systemctl disable ucm.service || true

exit 0
PRERM

chmod 755 ${BUILD_DIR}/${PKG_NAME}/DEBIAN/prerm

# Build package
echo "Building Debian package..."
dpkg-deb --build ${BUILD_DIR}/${PKG_NAME}

# Move and rename
mv ${BUILD_DIR}/${PKG_NAME}.deb ucm_${VERSION}_all.deb

# Create checksums
echo "Creating checksums..."
md5sum ucm_${VERSION}_all.deb > ucm_${VERSION}_all.deb.md5
sha256sum ucm_${VERSION}_all.deb > ucm_${VERSION}_all.deb.sha256

echo ""
echo "Package built successfully:"
echo "  ucm_${VERSION}_all.deb"
echo ""
echo "Checksums:"
cat ucm_${VERSION}_all.deb.md5
cat ucm_${VERSION}_all.deb.sha256
echo ""
