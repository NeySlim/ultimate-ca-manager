#!/usr/bin/env bash
# Ultimate CA Manager - Start Script

set -e

echo "========================================="
echo "  Starting Ultimate CA Manager"
echo "========================================="

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found"
    echo "Run ./scripts/setup.sh first"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Error: .env file not found"
    echo "Run ./scripts/setup.sh first"
    exit 1
fi

# Start server
echo "Starting HTTPS server..."
cd backend
python3 app.py
