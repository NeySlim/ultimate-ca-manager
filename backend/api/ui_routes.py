"""
UI Routes - Serve React SPA
Single Page Application - all routes serve index.html
"""
from flask import Blueprint, send_from_directory, current_app
from pathlib import Path
import os

ui_bp = Blueprint('ui', __name__)

# Frontend directory - relative to backend parent (BASE_DIR/frontend)
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


@ui_bp.route('/', defaults={'path': ''})
@ui_bp.route('/<path:path>')
def spa(path):
    """
    Serve React SPA
    - If path is a file (has extension), try to serve it from frontend/
    - Otherwise serve index.html (React Router handles routing)
    """
    frontend_dir = str(FRONTEND_DIR)
    
    # SPECIAL: Serve demo file if requested
    if path == 'topbar-demo.html':
        return send_from_directory(frontend_dir, 'topbar-demo.html')

    # If path has an extension, it's likely a static file
    if path and '.' in path.split('/')[-1]:
        # Try to serve the file
        try:
            return send_from_directory(frontend_dir, path)
        except:
            # File not found, serve index.html
            pass
    
    # Serve index.html for all other routes (React Router will handle)
    return send_from_directory(frontend_dir, 'index.html')
