"""
UI Routes - Serve React SPA
Single Page Application - all routes serve index.html
"""
from flask import Blueprint, abort, send_from_directory, current_app, make_response, request, session
from pathlib import Path
import json
import logging
import os
import re

ui_bp = Blueprint('ui', __name__)

# Frontend directory - relative to backend parent (BASE_DIR/frontend)
# Use dist/ for production builds, frontend/ for development
_frontend_base = Path(__file__).resolve().parent.parent.parent / "frontend"
_dist_dir = _frontend_base / "dist"
# Use dist if it exists and has index.html, otherwise use base (dev mode)
FRONTEND_DIR = _dist_dir if (_dist_dir / "index.html").exists() else _frontend_base

# The guide's chapters drawn at build time (frontend/scripts/prerender-guide.js): <lang>/<chapter>.html,
# sent by _serve_guide to a valid session only, never as static files
PRERENDER_DIRNAME = 'guide-prerender'
# The languages of the help; any other interface language reads the English one
GUIDE_LANGUAGES = ('en', 'fr', 'ru', 'zh')
_CHAPTER = re.compile(r'^[A-Za-z][A-Za-z0-9-]{0,63}$')
_THEME_FAMILIES = ('atelier', 'aurore')
_THEME_MODES = ('light', 'dark')

logger = logging.getLogger(__name__)


def _no_cache(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


def _serve_index():
    """Serve index.html with no-cache headers so browser always gets fresh chunk references"""
    return _no_cache(make_response(send_from_directory(str(FRONTEND_DIR), 'index.html')))


def _guide_reader():
    """The account of a valid session, checked as the API checks it (database sessions in HA
    included); None without one, or while a forced 2FA enrolment or password change holds it."""
    from auth.twofa_enforcement import ENROLL_SESSION_KEY
    from auth.unified import AuthManager
    if 'user_id' not in session:
        return None
    info = AuthManager().verify_session()
    if not info or session.get(ENROLL_SESSION_KEY):
        return None
    user = info['user']
    return None if getattr(user, 'force_password_change', False) else user


def _preferences(user):
    try:
        prefs = json.loads(user.preferences or '{}')
    except (TypeError, ValueError):
        return {}
    return prefs if isinstance(prefs, dict) else {}


def _guide_language(prefs):
    """The account's language, else the browser's among the help's, else English."""
    chosen = prefs.get('language')
    if isinstance(chosen, str) and chosen.strip():
        key = chosen.strip()[:2].lower()
        return key if key in GUIDE_LANGUAGES else 'en'
    return request.accept_languages.best_match(GUIDE_LANGUAGES) or 'en'


def _theme_attributes(prefs):
    """The account's theme on <html>, as the console sets it: no repaint when React takes the page over."""
    attrs = ''
    family = prefs.get('theme_family')
    if isinstance(family, str) and family:
        attrs += f' data-theme="{family if family in _THEME_FAMILIES else "atelier"}"'
    if prefs.get('theme_mode') in _THEME_MODES:
        attrs += f' data-mode="{prefs["theme_mode"]}"'
    return attrs


def _guide_page(chapter):
    """The chapter drawn at build time, for a valid session and a known chapter; None otherwise."""
    if request.query_string or not chapter or not _CHAPTER.fullmatch(chapter):
        return None
    try:
        user = _guide_reader()
    except Exception:  # noqa: BLE001 - the page as before, which checks the session itself
        logger.warning('guide: session check failed, the page is sent undrawn', exc_info=True)
        return None
    if user is None:
        return None
    prefs = _preferences(user)
    lang = _guide_language(prefs)
    drawn = FRONTEND_DIR / PRERENDER_DIRNAME / lang / f'{chapter}.html'
    if not drawn.is_file():
        return None
    html = drawn.read_text(encoding='utf-8')
    opening = f'<html lang="{lang}">'
    html = html.replace(opening, f'<html lang="{lang}"{_theme_attributes(prefs)}>', 1)
    response = make_response(html)
    response.mimetype = 'text/html'
    return _no_cache(response)


def _serve_guide(chapter):
    """/guide/<chapter>: the chapter already in the page (a reader view decides at load), else index.html."""
    response = _guide_page(chapter) or _serve_index()
    response.vary.update(('Cookie', 'Accept-Language'))
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
    # Don't catch API or protocol routes - let them 404 properly if not found.
    # The protocol list is shared with the CSRF exemption, the http→https
    # exemption and the safe-mode allowlist (utils.public_endpoints), which is
    # what keeps 'scep/' (the protocol endpoint) apart from 'scep-config' and
    # 'tsa' apart from 'tsa-config' — both React routes that must be served.
    from utils.public_endpoints import is_public_protocol_path
    if path.startswith('acme/'):
        abort(404)  # answered as an ACME problem, 405 where another method is served
    if path.startswith('api/') or is_public_protocol_path('/' + path):
        from utils.response import error_response
        return error_response('Not found', 404)
        
    # The guide's chapters: drawn in the page for a valid session, never served as files
    if path == 'guide' or path.startswith('guide/'):
        return _serve_guide(path[len('guide/'):] if path.startswith('guide/') else None)
    if path == PRERENDER_DIRNAME or path.startswith(PRERENDER_DIRNAME + '/'):
        return _serve_index()

    # SPECIAL: Serve demo file if requested
    if path == 'topbar-demo.html':
        return send_from_directory(str(_frontend_base), 'topbar-demo.html')

    # If path has an extension, it's likely a static file
    if path and '.' in path.split('/')[-1]:
        try:
            return _serve_asset(path)
        except Exception:
            # Hashed asset not found (stale cache after update) → serve index.html
            # Browser will reload with fresh chunk references
            pass
    
    # Serve index.html for all other routes (React Router will handle)
    return _serve_index()
