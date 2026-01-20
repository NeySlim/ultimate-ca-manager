"""
UI Routes - Serve React SPA
Single Page Application - all routes serve index.html
"""
from flask import Blueprint, send_from_directory, current_app
import os

ui_bp = Blueprint('ui', __name__)


@ui_bp.route('/', defaults={'path': ''})
@ui_bp.route('/<path:path>')
def spa(path):
    """
    Serve React SPA
    - If path is a file (has extension), try to serve it from frontend/
    - Otherwise serve index.html (React Router handles routing)
    """
    # Path to frontend build directory
    frontend_dir = os.path.join(current_app.root_path, '..', 'frontend')
    
    # SPECIAL: Serve demo file if requested
    if path == 'topbar-demo.html':
        return send_from_directory(frontend_dir, 'topbar-demo.html')

    # Prevent API routes from being captured by SPA catch-all
    # This ensures we get 404 JSON instead of 200 HTML for missing API endpoints
    if path.startswith('api/'):
        return {"error": "API route not found", "path": path}, 404

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
