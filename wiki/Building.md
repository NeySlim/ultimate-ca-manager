# Building from Source

This guide covers building Ultimate CA Manager v1.8.2 from source code.

## Prerequisites

### System Requirements

**Operating Systems:**
- Ubuntu 20.04/22.04/24.04 LTS
- Debian 11/12
- Rocky Linux 8/9
- AlmaLinux 8/9
- macOS 12+ (development only)

**Hardware:**
- CPU: 1+ cores
- RAM: 512 MB minimum, 1 GB recommended
- Disk: 500 MB for application + space for certificates

### Required Software

**Core Dependencies:**
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y \
  python3 \
  python3-pip \
  python3-venv \
  git \
  build-essential \
  libssl-dev \
  libffi-dev \
  python3-dev

# Rocky Linux/AlmaLinux
sudo dnf install -y \
  python3 \
  python3-pip \
  python3-virtualenv \
  git \
  gcc \
  openssl-devel \
  libffi-devel \
  python3-devel
```

**Python Version:**
- Python 3.8+ required
- Python 3.10+ recommended

**Verify Installation:**
```bash
python3 --version  # Should be 3.8+
pip3 --version
git --version
```

## Clone Repository

### From GitHub

```bash
# Clone main branch
git clone https://github.com/fabriziosalmi/ultimate-ca-manager.git
cd ultimate-ca-manager

# Or clone specific version
git clone --branch v1.8.2 https://github.com/fabriziosalmi/ultimate-ca-manager.git
cd ultimate-ca-manager
```

### From Git Archive

```bash
# Download release tarball
wget https://github.com/fabriziosalmi/ultimate-ca-manager/archive/refs/tags/v1.8.2.tar.gz

# Extract
tar -xzf v1.8.2.tar.gz
cd ultimate-ca-manager-1.8.2
```

## Build Process

### 1. Create Virtual Environment

```bash
# Create venv
python3 -m venv venv

# Activate venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows
```

### 2. Install Dependencies

```bash
# Upgrade pip
pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

# Verify installation
pip list
```

**Requirements.txt Contents:**
```
Flask>=3.0.0
Flask-SQLAlchemy>=3.0.0
Flask-Login>=0.6.2
Flask-WTF>=1.1.1
cryptography>=41.0.0
pyOpenSSL>=23.2.0
webauthn>=1.11.0
acme>=2.7.0
PyJWT>=2.8.0
python-dotenv>=1.0.0
gunicorn>=21.2.0
```

### 3. Initialize Database

```bash
# Create instance directory
mkdir -p instance

# Initialize database
flask db init
flask db migrate -m "Initial migration"
flask db upgrade

# Verify database
ls -l instance/ucm.db
```

### 4. Create Admin User

```bash
# Interactive creation
flask create-admin

# Or non-interactive
flask create-admin --username admin --password YourSecurePassword --email admin@example.com
```

### 5. Initialize CA

```bash
# Create Root CA
flask init-ca \
  --cn "Example Root CA" \
  --org "Example Organization" \
  --country US \
  --validity 3650

# Verify CA creation
openssl x509 -in instance/certs/ca.crt -noout -text
```

## Development Build

### Run Development Server

```bash
# Activate venv
source venv/bin/activate

# Run Flask dev server
flask run --host=0.0.0.0 --port=5000

# Or with debug mode
export FLASK_ENV=development
export FLASK_DEBUG=1
flask run
```

**Access Application:**
```
http://localhost:5000
```

### Development Configuration

**Create `.env` file:**
```bash
cat > .env << 'EOF'
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=dev-secret-key-change-in-production
DATABASE_URL=sqlite:///instance/ucm.db
LOG_LEVEL=DEBUG
EOF
```

## Production Build

### 1. Install Production Server

```bash
# Gunicorn already in requirements.txt
pip install gunicorn

# Verify
gunicorn --version
```

### 2. Production Configuration

**Create `config/production.py`:**
```python
import os

class ProductionConfig:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'change-this-in-production'
    SQLALCHEMY_DATABASE_URI = 'sqlite:////opt/ucm/instance/ucm.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Security
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FILE = '/opt/ucm/logs/ucm.log'
    
    # Features
    ENABLE_ACME = True
    ENABLE_SCEP = True
    ENABLE_OCSP = True
```

### 3. Create Installation Package

**Directory Structure:**
```bash
mkdir -p /opt/ucm
cp -r * /opt/ucm/
cd /opt/ucm

# Set permissions
chmod 755 /opt/ucm
chmod -R 644 /opt/ucm/*
chmod 755 /opt/ucm/venv/bin/*
```

### 4. Create Systemd Service

**Create `/etc/systemd/system/ucm.service`:**
```ini
[Unit]
Description=Ultimate CA Manager
After=network.target

[Service]
Type=notify
User=ucm
Group=ucm
WorkingDirectory=/opt/ucm
Environment="PATH=/opt/ucm/venv/bin"
ExecStart=/opt/ucm/venv/bin/gunicorn \
    --workers 4 \
    --bind 0.0.0.0:8443 \
    --certfile /opt/ucm/instance/server.crt \
    --keyfile /opt/ucm/instance/server.key \
    --access-logfile /opt/ucm/logs/access.log \
    --error-logfile /opt/ucm/logs/error.log \
    --log-level info \
    "app:create_app()"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and Start:**
```bash
# Create ucm user
sudo useradd -r -s /bin/false ucm
sudo chown -R ucm:ucm /opt/ucm

# Enable service
sudo systemctl daemon-reload
sudo systemctl enable ucm
sudo systemctl start ucm

# Check status
sudo systemctl status ucm
```

## Building Packages

### Debian/Ubuntu Package

**Install Build Tools:**
```bash
sudo apt install -y devscripts debhelper dh-python
```

**Build Package:**
```bash
# Prepare build environment
cd ultimate-ca-manager
dpkg-buildpackage -us -uc

# Package will be created in parent directory
ls -l ../ucm_*.deb
```

**Manual Build:**
```bash
# Create package structure
mkdir -p ucm_1.8.2/DEBIAN
mkdir -p ucm_1.8.2/opt/ucm
mkdir -p ucm_1.8.2/etc/systemd/system

# Copy files
cp -r * ucm_1.8.2/opt/ucm/
cp packaging/debian/ucm.service ucm_1.8.2/etc/systemd/system/

# Create control file
cat > ucm_1.8.2/DEBIAN/control << 'EOF'
Package: ucm
Version: 1.8.2
Architecture: all
Maintainer: Your Name <you@example.com>
Depends: python3, python3-pip, python3-venv
Suggests: nginx
Description: Ultimate CA Manager - Enterprise Certificate Authority
 Complete CA management solution with ACME, SCEP, WebAuthn, and more.
EOF

# Create postinst script
cat > ucm_1.8.2/DEBIAN/postinst << 'EOF'
#!/bin/bash
set -e

# Create user
useradd -r -s /bin/false ucm || true

# Setup venv
cd /opt/ucm
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Initialize database
flask db upgrade

# Set permissions
chown -R ucm:ucm /opt/ucm
chmod 600 /opt/ucm/instance/*.key

# Enable service
systemctl daemon-reload
systemctl enable ucm

echo "UCM installed. Run 'sudo systemctl start ucm' to start."
EOF

chmod 755 ucm_1.8.2/DEBIAN/postinst

# Build package
dpkg-deb --build ucm_1.8.2

# Install
sudo dpkg -i ucm_1.8.2.deb
```

### RPM Package (Red Hat/Rocky/Alma)

**Install Build Tools:**
```bash
sudo dnf install -y rpm-build rpmdevtools
```

**Create RPM Structure:**
```bash
# Setup build environment
rpmdev-setuptree

# Copy files
cp ultimate-ca-manager-1.8.2.tar.gz ~/rpmbuild/SOURCES/
cp packaging/rpm/ucm.spec ~/rpmbuild/SPECS/

# Build
cd ~/rpmbuild
rpmbuild -ba SPECS/ucm.spec

# Package location
ls -l ~/rpmbuild/RPMS/noarch/ucm-*.rpm
```

### Docker Image

**Build Image:**
```bash
# Build
docker build -t ucm:1.8.2 .

# Tag
docker tag ucm:1.8.2 ghcr.io/fabriziosalmi/ucm:1.8.2
docker tag ucm:1.8.2 ghcr.io/fabriziosalmi/ucm:latest

# Push (if authenticated)
docker push ghcr.io/fabriziosalmi/ucm:1.8.2
docker push ghcr.io/fabriziosalmi/ucm:latest
```

**Multi-arch Build:**
```bash
# Setup buildx
docker buildx create --use

# Build for multiple architectures
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ghcr.io/fabriziosalmi/ucm:1.8.2 \
  --push .
```

## Testing Build

### Unit Tests

```bash
# Install test dependencies
pip install pytest pytest-cov pytest-flask

# Run tests
pytest tests/

# With coverage
pytest --cov=app tests/
```

### Integration Tests

```bash
# Start test server
flask run --port 5001 &
TEST_PID=$!

# Run integration tests
python tests/integration/test_api.py
python tests/integration/test_acme.py

# Cleanup
kill $TEST_PID
```

### Verify Installation

```bash
# Check version
curl http://localhost:5000/api/health

# Check CA
curl http://localhost:5000/api/ca

# Create test certificate
curl -X POST http://localhost:5000/api/certificates \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"common_name":"test.example.com","type":"server"}'
```

## Build Troubleshooting

### Common Issues

**Python Version Mismatch:**
```bash
# Check Python version
python3 --version

# Use specific version
python3.10 -m venv venv
```

**Missing Dependencies:**
```bash
# Ubuntu/Debian
sudo apt install -y python3-dev libssl-dev

# Rocky/Alma
sudo dnf install -y python3-devel openssl-devel
```

**Database Migration Errors:**
```bash
# Reset migrations
rm -rf migrations/ instance/ucm.db
flask db init
flask db migrate
flask db upgrade
```

**Permission Errors:**
```bash
# Fix ownership
sudo chown -R ucm:ucm /opt/ucm

# Fix permissions
chmod 700 /opt/ucm/instance
chmod 600 /opt/ucm/instance/*.key
```

## Build Optimization

### Reduce Package Size

```bash
# Remove development files
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
rm -rf .git tests/ docs/

# Use --no-cache-dir for pip
pip install --no-cache-dir -r requirements.txt
```

### Compile Python

```bash
# Compile Python files
python3 -m compileall app/

# Use optimized mode
python3 -O -m compileall app/
```

## Continuous Integration

### GitHub Actions

**`.github/workflows/build.yml`:**
```yaml
name: Build UCM

on:
  push:
    tags:
      - 'v*'

jobs:
  build-deb:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      
      - name: Run tests
        run: pytest tests/
      
      - name: Build package
        run: dpkg-buildpackage -us -uc
      
      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: debian-package
          path: ../ucm_*.deb
```

## See Also

- [Configuration](Configuration.md) - Configuration options
- [Architecture](Architecture.md) - System architecture
- [Contributing](Contributing.md) - Development guidelines
- [Docker Quick Start](../DOCKER_QUICKSTART.md) - Docker deployment
