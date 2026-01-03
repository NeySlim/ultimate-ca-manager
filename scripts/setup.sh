#!/usr/bin/env bash
# Ultimate CA Manager - Setup Script

set -e

echo "========================================="
echo "  Ultimate CA Manager - Setup"
echo "========================================="
echo ""

# Check Python version
echo "[1/6] Checking Python version..."
python3 --version || { echo "Python 3.10+ required"; exit 1; }

# Create .env from example if not exists
echo "[2/6] Setting up configuration..."
if [ ! -f .env ]; then
    cp .env.example .env
    # Generate secrets
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/your-secret-key-here-change-this/$SECRET_KEY/" .env
    sed -i "s/your-jwt-secret-here-change-this/$JWT_SECRET/" .env
    echo "✓ Created .env with generated secrets"
else
    echo "✓ .env already exists"
fi

# Create virtual environment
echo "[3/6] Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate and install dependencies
echo "[4/6] Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt
echo "✓ Dependencies installed"

# Initialize database
echo "[5/6] Initializing database..."
cd backend
python3 -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all(); print('✓ Database initialized')"
cd ..

# Install frontend dependencies (if Node.js available)
echo "[6/6] Checking frontend setup..."
if command -v npm &> /dev/null; then
    echo "npm found, frontend setup will be done separately"
else
    echo "⚠ npm not found - frontend setup skipped"
    echo "  Install Node.js 18+ and run: cd frontend && npm install && npm run build"
fi

echo ""
echo "========================================="
echo "  Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Review and customize .env file"
echo "  2. Change default admin password (admin/changeme123)"
echo "  3. Start server: ./scripts/start.sh"
echo ""
echo "Default credentials:"
echo "  Username: admin"
echo "  Password: changeme123"
echo "  ⚠ CHANGE THIS IMMEDIATELY!"
echo ""
