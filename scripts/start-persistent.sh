#!/bin/bash
# UCM Persistent Start Script
# This script starts the UCM server in background with nohup

cd /root/ucm-src
source venv/bin/activate

# Check if already running
if pgrep -f "python backend/app.py" > /dev/null; then
    echo "⚠️  UCM is already running!"
    echo "PID: $(pgrep -f 'python backend/app.py')"
    exit 1
fi

# Start server
nohup python backend/app.py > /tmp/ucm.log 2>&1 &
PID=$!

sleep 3

# Verify it started
if pgrep -f "python backend/app.py" > /dev/null; then
    echo "✅ UCM started successfully!"
    echo "PID: $(pgrep -f 'python backend/app.py')"
    echo "URL: https://localhost:8443"
    echo "Logs: tail -f /tmp/ucm.log"
else
    echo "❌ Failed to start UCM"
    echo "Check logs: tail /tmp/ucm.log"
    exit 1
fi
