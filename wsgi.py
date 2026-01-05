#!/usr/bin/env python3
"""
WSGI Entry Point for UCM
Production server using Gunicorn
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app import create_app

# Create application instance
application = create_app()
app = application  # Alias for WSGI servers

if __name__ == "__main__":
    # This is only for debugging - production uses Gunicorn
    from config.settings import get_config
    config = get_config()
    
    ssl_context = (
        str(config.HTTPS_CERT_PATH),
        str(config.HTTPS_KEY_PATH)
    )
    
    print(f"\n⚠️  Running development server!")
    print(f"   For production, use: gunicorn -c gunicorn.conf.py wsgi:app\n")
    
    app.run(
        host=config.HOST,
        port=config.HTTPS_PORT,
        ssl_context=ssl_context,
        debug=config.DEBUG
    )
