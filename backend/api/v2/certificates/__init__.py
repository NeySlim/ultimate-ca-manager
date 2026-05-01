"""
Certificates API v2.0 - Modular Routes Package

This package contains routes for /api/v2/certificates/*
split into thematic modules.
"""

from flask import Blueprint

# Create the blueprint here
bp = Blueprint('certificates_v2', __name__)

# Note: Route modules are imported in api/v2/__init__.py to register routes
# This avoids circular import issues
