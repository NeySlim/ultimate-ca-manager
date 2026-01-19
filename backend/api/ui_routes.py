"""
UI Routes - Serve HTML templates
Simple & modular routes for frontend pages
"""
from flask import Blueprint, render_template, redirect, url_for, session

ui_bp = Blueprint('ui', __name__)


@ui_bp.route('/')
def index():
    """Root - redirect to login or dashboard"""
    if session.get('user_id'):
        return redirect(url_for('ui.dashboard'))
    return redirect(url_for('ui.login'))


@ui_bp.route('/login')
def login():
    """Login page"""
    return render_template('auth/login.html')


@ui_bp.route('/dashboard')
def dashboard():
    """Dashboard page"""
    return render_template('index.html')


@ui_bp.route('/certificates')
def certificates():
    """Certificates page"""
    return render_template('index.html')


@ui_bp.route('/cas')
def cas():
    """Certificate Authorities page"""
    return render_template('index.html')
