#!/bin/bash
set -e

echo "🧹 Cleaning UCM source directory..."
echo "======================================"

# Stop any running server
echo "Stopping any running UCM instances..."
pkill -f "python.*backend/app.py" 2>/dev/null || true
sleep 2

# Remove runtime data
echo "Removing runtime data..."
rm -rf backend/data/*.db
rm -rf backend/data/*.pem
rm -rf backend/data/ca/*
rm -rf backend/data/certs/*
rm -rf backend/data/crl/*
rm -rf backend/data/scep/*
rm -rf backend/data/backups/*

# Keep .gitkeep files
echo "Restoring .gitkeep files..."
touch backend/data/.gitkeep
touch backend/data/ca/.gitkeep
touch backend/data/certs/.gitkeep
touch backend/data/crl/.gitkeep
touch backend/data/scep/.gitkeep
touch backend/data/private/.gitkeep
touch backend/data/backups/.gitkeep

# Remove Python cache
echo "Removing Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Remove session files
echo "Removing session files..."
rm -f cookies.txt
rm -f /tmp/ucm*.log
rm -f /tmp/flask_session/*

# Remove test files
echo "Removing test artifacts..."
rm -f /tmp/test_*.sh
rm -f /tmp/ca_list_htmx.html

# Remove virtual environment (will be recreated in production)
echo "Removing virtual environment..."
rm -rf venv/

# Update .gitignore
echo "Updating .gitignore..."
cat > .gitignore << 'GITIGNORE'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/

# Database
*.db
*.db-journal

# Certificates and Keys
*.pem
*.crt
*.key
*.p12
*.pfx
*.csr

# Data directories (keep structure, not content)
backend/data/*.pem
backend/data/*.db
backend/data/ca/*
!backend/data/ca/.gitkeep
backend/data/certs/*
!backend/data/certs/.gitkeep
backend/data/private/*
!backend/data/private/.gitkeep
backend/data/crl/*
!backend/data/crl/.gitkeep
backend/data/scep/*
!backend/data/scep/.gitkeep
backend/data/backups/*
!backend/data/backups/.gitkeep

# Logs
*.log
logs/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Temporary files
cookies.txt
/tmp/
GITIGNORE

echo ""
echo "✅ Source directory cleaned!"
echo ""
echo "Directory size:"
du -sh /root/ucm-src
echo ""
echo "Remaining files in data:"
find backend/data -type f | head -10
