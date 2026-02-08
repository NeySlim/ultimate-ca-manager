"""
UCM Feature Modules
Auto-registers feature blueprints (SSO, HSM, RBAC, etc.)
Checks and optionally installs missing dependencies
"""

import os


def register_feature_blueprints(app):
    """Register all feature API blueprints and check dependencies"""
    
    # Check/install dependencies first
    from .dependency_checker import ensure_feature_dependencies, get_dependency_status
    
    auto_install = os.environ.get('UCM_AUTO_INSTALL_DEPS', '').lower() in ('true', '1', 'yes')
    app.config['AUTO_INSTALL_DEPS'] = auto_install
    
    deps_ok = ensure_feature_dependencies(app)
    app.config['FEATURES_DEPS_OK'] = deps_ok
    app.config['FEATURES_DEPS_STATUS'] = get_dependency_status()
    
    # Register blueprints (they handle missing deps gracefully)
    from .groups import bp as groups_bp
    from .rbac import bp as rbac_bp
    from .sso import bp as sso_bp
    from .hsm import bp as hsm_bp
    from .policies import bp as policies_bp
    from .reports import bp as reports_bp
    from .webhooks import bp as webhooks_bp
    
    app.register_blueprint(groups_bp)
    app.register_blueprint(rbac_bp)
    app.register_blueprint(sso_bp)
    app.register_blueprint(hsm_bp)
    app.register_blueprint(policies_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(webhooks_bp)
    
    # Register dependency status endpoint
    from .dependency_checker import get_dependency_status
    
    @app.route('/api/v2/features/dependencies')
    def features_dependencies():
        from utils.response import success_response
        return success_response(data={
            'dependencies': get_dependency_status(),
            'all_installed': deps_ok,
            'auto_install_enabled': auto_install
        })
    
    if deps_ok:
        app.logger.info("✨ UCM feature modules loaded - All dependencies OK")
    else:
        app.logger.warning("⚠️ UCM feature modules loaded - Some dependencies missing")
