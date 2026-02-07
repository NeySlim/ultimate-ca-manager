"""
UCM Pro Modules
Auto-registers Pro blueprints when imported
Checks and optionally installs missing dependencies
"""

import os


def register_pro_blueprints(app):
    """Register all Pro API blueprints and check dependencies"""
    
    # Check/install dependencies first
    from .dependency_checker import ensure_pro_dependencies, get_dependency_status
    
    auto_install = os.environ.get('UCM_AUTO_INSTALL_DEPS', '').lower() in ('true', '1', 'yes')
    app.config['AUTO_INSTALL_DEPS'] = auto_install
    
    deps_ok = ensure_pro_dependencies(app)
    app.config['PRO_DEPS_OK'] = deps_ok
    app.config['PRO_DEPS_STATUS'] = get_dependency_status()
    
    # Register blueprints (they handle missing deps gracefully)
    from .groups import bp as groups_bp
    from .rbac import bp as rbac_bp
    from .license import bp as license_bp
    from .sso import bp as sso_bp
    from .hsm import bp as hsm_bp
    from .policies import bp as policies_bp
    from .reports import bp as reports_bp
    from .webhooks import bp as webhooks_bp
    
    app.register_blueprint(groups_bp)
    app.register_blueprint(rbac_bp)
    app.register_blueprint(license_bp)
    app.register_blueprint(sso_bp)
    app.register_blueprint(hsm_bp)
    app.register_blueprint(policies_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(webhooks_bp)
    
    # Register dependency status endpoint
    from .dependency_checker import get_dependency_status
    
    @app.route('/api/v2/pro/dependencies')
    def pro_dependencies():
        from utils.response import success_response
        return success_response(data={
            'dependencies': get_dependency_status(),
            'all_installed': deps_ok,
            'auto_install_enabled': auto_install
        })
    
    app.config['PRO_ENABLED'] = True
    app.config['PRO_VERSION'] = '2.0.0'
    
    if deps_ok:
        app.logger.info("✨ UCM Pro modules loaded (v2.0.0) - All dependencies OK")
    else:
        app.logger.warning("⚠️ UCM Pro modules loaded (v2.0.0) - Some dependencies missing")
