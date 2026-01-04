#!/bin/bash
# UCM Stop Script

echo "🛑 Arrêt du serveur UCM..."

PID=$(pgrep -f "python backend/app.py")

if [ -z "$PID" ]; then
    echo "⚠️  UCM n'est pas en cours d'exécution"
    exit 0
fi

kill $PID
sleep 2

if pgrep -f "python backend/app.py" > /dev/null; then
    echo "⚠️  Arrêt forcé..."
    kill -9 $PID
    sleep 1
fi

if ! pgrep -f "python backend/app.py" > /dev/null; then
    echo "✅ UCM arrêté (PID: $PID)"
else
    echo "❌ Échec de l'arrêt"
    exit 1
fi
