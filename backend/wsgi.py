"""
WSGI entry point for Gunicorn
"""
from app import create_app

# Create Flask application instance
app = create_app()

if __name__ == "__main__":
    app.run()
