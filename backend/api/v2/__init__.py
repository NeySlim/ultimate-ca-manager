"""
API v2 - Unified API
All routes use @require_auth() decorator
"""

from flask import Blueprint

# Import all route blueprints
from api.v2.auth import bp as auth_bp
from api.v2.auth_methods import bp as auth_methods_bp  # Multi-method auth
from api.v2.account import bp as account_bp
from api.v2.cas import bp as cas_bp
from api.v2.certificates import bp as certificates_bp
from api.v2.acme import bp as acme_bp
from api.v2.scep import bp as scep_bp
from api.v2.settings import bp as settings_bp
from api.v2.system import bp as system_bp
from api.v2.dashboard import bp as dashboard_bp
from api.v2.crl import bp as crl_bp
from api.v2.csrs import bp as csrs_bp
from api.v2.users import bp as users_bp
from api.v2.templates import bp as templates_bp
from api.v2.truststore import bp as truststore_bp
from api.v2.import_opnsense import bp as import_opnsense_bp
from api.v2.roles import bp as roles_bp
from api.v2.webauthn import bp as webauthn_bp
from api.v2.mtls import bp as mtls_bp
from api.v2.audit import bp as audit_bp
from api.v2.websocket import websocket_bp
from api.v2.groups import bp as groups_bp
from api.v2.search import bp as search_bp
from api.v2.smart_import import bp as smart_import_bp
from api.v2.tools import tools_bp
from api.v2.dns_providers import bp as dns_providers_bp
from api.v2.acme_client import bp as acme_client_bp

# List of all core blueprints to register
# Feature modules are loaded separately via features/__init__.py in app.py
API_V2_BLUEPRINTS = [
    auth_bp,
    auth_methods_bp,
    account_bp,
    cas_bp,
    certificates_bp,
    csrs_bp,
    acme_bp,
    scep_bp,
    settings_bp,
    system_bp,
    dashboard_bp,
    crl_bp,
    users_bp,
    templates_bp,
    truststore_bp,
    import_opnsense_bp,
    roles_bp,
    webauthn_bp,
    mtls_bp,
    audit_bp,
    websocket_bp,
    groups_bp,
    search_bp,
    smart_import_bp,
    tools_bp,
    dns_providers_bp,
    acme_client_bp,
]


def register_api_v2(app):
    """
    Register all API v2 blueprints
    
    Usage in app.py:
        from api.v2 import register_api_v2
        register_api_v2(app)
    
    Note: Feature modules are loaded separately via features/__init__.py
    """
    for blueprint in API_V2_BLUEPRINTS:
        app.register_blueprint(blueprint)
    
    print(f"✅ Registered {len(API_V2_BLUEPRINTS)} API v2 core blueprints")
