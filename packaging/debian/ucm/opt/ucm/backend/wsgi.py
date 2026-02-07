"""
WSGI entry point for Gunicorn
"""
import sys
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app import create_app

# Create Flask application instance
app = create_app()

if __name__ == "__main__":
    app.run()
