"""
UI Routes - Serve React SPA
Single Page Application - all routes serve index.html
"""
from flask import Blueprint, send_from_directory, current_app, make_response
from pathlib import Path
import os

ui_bp = Blueprint('ui', __name__)

# Frontend directory - relative to backend parent (BASE_DIR/frontend)
# Use dist/ for production builds, frontend/ for development
_frontend_base = Path(__file__).resolve().parent.parent.parent / "frontend"
_dist_dir = _frontend_base / "dist"
# Use dist if it exists and has index.html, otherwise use base (dev mode)
FRONTEND_DIR = _dist_dir if (_dist_dir / "index.html").exists() else _frontend_base


def _serve_index():
    """Serve index.html with no-cache headers so browser always gets fresh chunk references"""
    response = make_response(send_from_directory(str(FRONTEND_DIR), 'index.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def _serve_asset(path):
    """Serve static assets with long cache for hashed files, no-cache for others"""
    response = make_response(send_from_directory(str(FRONTEND_DIR), path))
    # Vite hashed assets (e.g. vendor-BNwtikur.js) can be cached forever
    filename = path.split('/')[-1]
    if filename and '-' in filename and '.' in filename:
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    return response


@ui_bp.route('/')
def index():
    """Serve index.html for root"""
    return _serve_index()


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
        
    # SPECIAL: Serve demo file if requested
    if path == 'topbar-demo.html':
        return send_from_directory(str(_frontend_base), 'topbar-demo.html')

    # If path has an extension, it's likely a static file
    if path and '.' in path.split('/')[-1]:
        try:
            return _serve_asset(path)
        except:
            # Hashed asset not found (stale cache after update) → serve index.html
            # Browser will reload with fresh chunk references
            pass
    
    # Serve index.html for all other routes (React Router will handle)
    return _serve_index()
