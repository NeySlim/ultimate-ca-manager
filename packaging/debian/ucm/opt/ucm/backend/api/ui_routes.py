"""
UI Routes - Serve React SPA
Single Page Application - all routes serve index.html
"""
from flask import Blueprint, send_from_directory, current_app
from pathlib import Path
import os

ui_bp = Blueprint('ui', __name__)

# Frontend directory - relative to backend parent (BASE_DIR/frontend)
# Use dist/ for production builds, frontend/ for development
_frontend_base = Path(__file__).resolve().parent.parent.parent / "frontend"
_dist_dir = _frontend_base / "dist"
# Use dist if it exists and has index.html, otherwise use base (dev mode)
FRONTEND_DIR = _dist_dir if (_dist_dir / "index.html").exists() else _frontend_base


@ui_bp.route('/')
def index():
    """Serve index.html for root"""
    return send_from_directory(str(FRONTEND_DIR), 'index.html')


@ui_bp.route('/<path:path>')
def spa(path):
    """
    Serve React SPA
    - API routes are handled by API blueprints (not caught here)
    - If path is a file (has extension), try to serve it from frontend/
    - Otherwise serve index.html (React Router handles routing)
    """
    # Don't catch API or protocol routes - let them 404 properly if not found
    # Note: 'scep/' is the protocol endpoint, 'scep-config' is a React route (should NOT be excluded)
    if path.startswith(('api/', 'scep/', 'acme/', '.well-known/')) or path == 'scep':
        return {"error": "Not Found"}, 404
        
    frontend_dir = str(FRONTEND_DIR)
    
    # SPECIAL: Serve demo file if requested
    if path == 'topbar-demo.html':
        return send_from_directory(str(_frontend_base), 'topbar-demo.html')

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
