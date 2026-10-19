"""
CAs API v2.0 - Modular Routes Package

This package contains routes for /api/v2/cas/*
split into thematic modules.
"""

from flask import Blueprint

# Create the blueprint here
bp = Blueprint('cas_v2', __name__)

# Note: Route modules are imported in api/v2/__init__.py to register routes
# This avoids circular import issues

# CA private-key exports are audited by a hook until the route records them itself.
from services.key_export_audit import register_ca_export_audit  # noqa: E402
register_ca_export_audit(bp)
