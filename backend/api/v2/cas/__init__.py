"""
CAs API v2.0 - Modular Routes Package

Ce package contient les routes pour /api/v2/cas/*
découpées en modules thématiques.
"""

from flask import Blueprint

# Create the blueprint here
bp = Blueprint('cas_v2', __name__)

# Note: Route modules are imported in api/v2/__init__.py to register routes
# This avoids circular import issues
