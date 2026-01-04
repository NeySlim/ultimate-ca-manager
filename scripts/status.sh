#!/bin/bash
# UCM Status Script

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Ultimate CA Manager - Status"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

PID=$(pgrep -f "python backend/app.py")

if [ -z "$PID" ]; then
    echo "Status: 🔴 Arrêté"
    echo ""
    echo "Pour démarrer: /root/ucm-src/scripts/start-persistent.sh"
else
    echo "Status: 🟢 En ligne"
    echo "PID: $PID"
    echo ""
    echo "URLs:"
    echo "  • https://localhost:8443"
    echo "  • https://192.168.1.253:8443"
    echo ""
    echo "Login: admin / changeme123"
    echo ""
    echo "Logs: tail -f /tmp/ucm.log"
    echo ""
    echo "Uptime:"
    ps -p $PID -o etime= | sed 's/^/  • /'
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
