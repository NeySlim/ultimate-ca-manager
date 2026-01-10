"""
Ultimate CA Manager - Main Application
Flask application with HTTPS-only enforcement
"""
import os
import sys
from pathlib import Path
from flask import Flask, redirect, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_caching import Cache

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import get_config, BASE_DIR
from config.https_manager import HTTPSManager
from models import db, User, SystemConfig
from middleware.auth_middleware import init_auth_middleware

# Initialize cache globally
cache = Cache()


def create_app(config_name=None):
    """Application factory"""
    app = Flask(__name__, 
                static_folder=str(BASE_DIR / "frontend" / "static"),
                template_folder=str(BASE_DIR / "frontend" / "templates"))
    
    # Disable template caching for development
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    
    # Load configuration
    config = get_config(config_name)
    app.config.from_object(config)
    
    # Ensure HTTPS certificate exists
    if config.HTTPS_AUTO_GENERATE:
        HTTPSManager.ensure_https_cert(
            config.HTTPS_CERT_PATH,
            config.HTTPS_KEY_PATH,
            auto_generate=True
        )
    
    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    jwt = JWTManager(app)
    
    # Initialize cache
    cache.init_app(app, config={
        'CACHE_TYPE': 'SimpleCache',  # In-memory cache
        'CACHE_DEFAULT_TIMEOUT': 300   # 5 minutes default
    })
    
    # CORS - only HTTPS origins
    CORS(app, resources={
        r"/api/*": {
            "origins": config.CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True
        }
    })
    
    # Initialize auth middleware
    init_auth_middleware(jwt)
    
    # Initialize mTLS middleware
    from middleware.mtls_middleware import init_mtls_middleware
    init_mtls_middleware(app)
    
    # Create database tables and auto-migrate
    with app.app_context():
        try:
            # Always run create_all to ensure all tables exist
            # SQLAlchemy will skip existing tables automatically
            db.create_all()
            app.logger.info("Database tables created/verified")
        except Exception as e:
            app.logger.error(f"Database creation error: {e}")
            # Don't raise - continue if tables already exist
        
        # Run database health check and repair
        from database_health import check_and_repair_database
        check_and_repair_database(app)
        
        # Initialize default data (legacy, kept for compatibility)
        init_database(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Security headers and cleanup
    @app.after_request
    def add_security_headers(response):
        """Add security headers and fix deprecated headers"""
        # Set Permissions-Policy without deprecated features
        # Only include valid features that are widely supported
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        
        # Add security headers if not present
        if 'X-Content-Type-Options' not in response.headers:
            response.headers['X-Content-Type-Options'] = 'nosniff'
        if 'X-Frame-Options' not in response.headers:
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        if 'X-XSS-Protection' not in response.headers:
            response.headers['X-XSS-Protection'] = '1; mode=block'
        
        return response
    
    # FQDN redirect middleware (redirect IP to FQDN if configured)
    @app.before_request
    def redirect_to_fqdn():
        # Skip for health checks and static files
        if request.path in ['/api/health', '/health'] or request.path.startswith('/static/'):
            return None
        
        # Get configured FQDN - check both UCM_FQDN (Docker) and FQDN env vars
        fqdn = os.getenv('UCM_FQDN') or os.getenv('FQDN') or app.config.get('FQDN')
        if not fqdn or fqdn in ['localhost', '127.0.0.1', 'ucm.example.com', 'ucm.local', 'test.local']:
            return None  # Skip if FQDN is default/localhost
        
        # Get current host
        current_host = request.host.split(':')[0]  # Remove port
        
        # If accessing via IP or non-FQDN hostname, redirect to FQDN
        if current_host != fqdn:
            # Check if current host is an IP address
            import re
            if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', current_host):
                # It's an IP, redirect to FQDN
                scheme = 'https' if request.is_secure else 'http'
                port_str = request.host.split(':')[1] if ':' in request.host else None
                if port_str:
                    new_url = f"{scheme}://{fqdn}:{port_str}{request.full_path.rstrip('?')}"
                else:
                    # Use default ports
                    https_port = os.getenv('UCM_HTTPS_PORT', app.config.get('HTTPS_PORT', 8443))
                    http_port = os.getenv('UCM_HTTP_PORT', app.config.get('HTTP_PORT', 80))
                    port = https_port if request.is_secure else http_port
                    new_url = f"{scheme}://{fqdn}:{port}{request.full_path.rstrip('?')}"
                return redirect(new_url, code=302)
        
        return None
    
    # HTTPS redirect middleware (if enabled)
    if config.HTTP_REDIRECT:
        @app.before_request
        def enforce_https():
            if not request.is_secure and request.url.startswith('http://'):
                url = request.url.replace('http://', 'https://', 1)
                url = url.replace(f':{config.HTTPS_PORT}', f':{config.HTTPS_PORT}')
                return redirect(url, code=301)
    
    # Health check endpoint
    @app.route('/api/health')
    def health():
        return {"status": "ok", "version": config.APP_VERSION}
    
    # Restart signal detector (before_request middleware)
    @app.before_request
    def check_restart_signal():
        """Check if restart was requested and perform graceful shutdown"""
        from pathlib import Path
        from config.settings import DATA_DIR
        
        restart_signal = DATA_DIR / '.restart_requested'
        
        if restart_signal.exists():
            try:
                # Remove signal file
                restart_signal.unlink()
                
                # Schedule graceful shutdown after this request completes
                # Systemd will automatically restart the service
                def do_shutdown():
                    import time
                    import sys
                    import os
                    
                    time.sleep(1)  # Wait for response to be sent
                    
                    # Graceful shutdown - let systemd restart us
                    os._exit(0)
                
                import threading
                threading.Thread(target=do_shutdown, daemon=False).start()
                
            except Exception as e:
                # Log error but don't fail the request
                print(f"Restart signal error: {e}")
        
        return None
    
    return app


def init_database(app):
    """Initialize database with default data and verify schema"""
    from datetime import datetime
    from sqlalchemy.exc import IntegrityError, OperationalError
    from sqlalchemy import inspect
    
    # Verify all tables exist, create if missing
    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()
    
    # Get all model tables
    expected_tables = db.Model.metadata.tables.keys()
    missing_tables = [table for table in expected_tables if table not in existing_tables]
    
    if missing_tables:
        app.logger.warning(f"Missing database tables detected: {missing_tables}")
        app.logger.info("Running automatic schema migration...")
        db.create_all()
        app.logger.info("Schema migration completed successfully")
    
    # Create initial admin user if none exists
    # Use try/except to handle race conditions with multiple workers
    try:
        if User.query.count() == 0:
            admin = User(
                username=app.config["INITIAL_ADMIN_USERNAME"],
                email=app.config["INITIAL_ADMIN_EMAIL"],
                role="admin",
                active=True
            )
            admin.set_password(app.config["INITIAL_ADMIN_PASSWORD"])
            db.session.add(admin)
            
            # Add initial system config
            configs = [
                SystemConfig(key="app.initialized", value="true", 
                            description="Application initialized"),
                SystemConfig(key="app.version", value=app.config["APP_VERSION"],
                            description="Application version"),
                SystemConfig(key="https.enabled", value="true",
                            description="HTTPS enforcement enabled"),
            ]
            
            for config in configs:
                db.session.add(config)
            
            db.session.commit()
            print(f"\n[SETUP] Initial admin user created: {admin.username}")
            print(f"[SETUP] Default password: {app.config['INITIAL_ADMIN_PASSWORD']}")
            print(f"[SETUP] CHANGE THIS PASSWORD IMMEDIATELY!\n")
    except IntegrityError:
        # Another worker already created the initial data
        db.session.rollback()
        pass


def register_blueprints(app):
    """Register all API blueprints"""
    # Import blueprints
    from api.auth import auth_bp
    from api.ca import ca_bp
    from api.cert import cert_bp
    from api.crl import crl_bp
    from api.cdp_routes import cdp_bp
    from api.ocsp_routes import ocsp_bp
    from api.scep import scep_bp
    from api.system import system_bp
    from api.import_api import import_bp
    from api.notification_api import notification_bp
    from api.mtls_api import mtls_bp
    from api.webauthn_api import webauthn_bp
    from api.ui_routes import ui_bp
    from api.acme import acme_bp
    
    # Register UI routes (no prefix - serve from root)
    app.register_blueprint(ui_bp)
    
    # Register API with /api prefix
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(ca_bp, url_prefix='/api/v1/ca')
    app.register_blueprint(cert_bp, url_prefix='/api/v1/certificates')
    app.register_blueprint(crl_bp, url_prefix='/api/v1/crl')
    
    # Import and register OCSP API
    from api.ocsp_api import ocsp_api_bp
    app.register_blueprint(ocsp_api_bp, url_prefix='/api/v1/ocsp')
    
    app.register_blueprint(system_bp, url_prefix='/api/v1/system')
    app.register_blueprint(import_bp, url_prefix='/api/v1/import')
    app.register_blueprint(notification_bp, url_prefix='/api/v1/notifications')
    app.register_blueprint(mtls_bp, url_prefix='/api/v1/mtls')
    app.register_blueprint(webauthn_bp, url_prefix='/api/v1/webauthn')
    
    # Public endpoints (no auth, no /api prefix - standard paths)
    app.register_blueprint(scep_bp, url_prefix='/scep')  # SCEP protocol
    app.register_blueprint(cdp_bp, url_prefix='/cdp')     # CRL Distribution Points
    app.register_blueprint(ocsp_bp)                        # OCSP Responder (/ocsp)
    app.register_blueprint(acme_bp)                        # ACME protocol (/acme)


def main():
    """Main entry point"""
    config = get_config()
    app = create_app()
    
    # Get SSL context with optional client certificate verification
    import ssl
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(
        str(config.HTTPS_CERT_PATH),
        str(config.HTTPS_KEY_PATH)
    )
    
    # Check if mTLS is enabled and configure client cert verification
    from models import SystemConfig
    import tempfile
    import os
    
    ca_cert_path = None
    with app.app_context():
        mtls_enabled = SystemConfig.query.filter_by(key='mtls_enabled').first()
        mtls_required = SystemConfig.query.filter_by(key='mtls_required').first()
        mtls_ca_id = SystemConfig.query.filter_by(key='mtls_trusted_ca_id').first()
        
        if mtls_enabled and mtls_enabled.value == 'true' and mtls_ca_id:
            # Load trusted CA for client certificate verification
            from models import CA
            ca = CA.query.filter_by(refid=mtls_ca_id.value).first()
            if ca and ca.crt:
                # CA certificate is base64 encoded in database - decode it
                import base64
                try:
                    ca_pem = base64.b64decode(ca.crt).decode('utf-8')
                except:
                    # If decode fails, assume it's already in PEM format
                    ca_pem = ca.crt
                
                # Create temp CA file (kept for app lifetime)
                ca_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
                ca_file.write(ca_pem)
                ca_file.flush()
                ca_cert_path = ca_file.name
                ca_file.close()
                
                # Verify file exists and is readable
                if not os.path.exists(ca_cert_path):
                    print(f"  ERROR: CA cert file not found at {ca_cert_path}")
                    ca_cert_path = None
                else:
                    # Configure client cert verification
                    if mtls_required and mtls_required.value == 'true':
                        ssl_context.verify_mode = ssl.CERT_REQUIRED
                        print(f"  mTLS: REQUIRED (client cert mandatory)")
                    else:
                        ssl_context.verify_mode = ssl.CERT_OPTIONAL
                        print(f"  mTLS: OPTIONAL (client cert enhances security)")
                    
                    try:
                        ssl_context.load_verify_locations(ca_cert_path)
                        print(f"  mTLS CA: {ca.descr}")
                        print(f"  mTLS CA file: {ca_cert_path}")
                    except Exception as e:
                        print(f"  ERROR loading mTLS CA: {e}")
                        ca_cert_path = None
    
    print(f"\n{'='*60}")
    print(f"  {config.APP_NAME} v{config.APP_VERSION}")
    print(f"{'='*60}")
    print(f"  HTTPS Server: https://{config.HOST}:{config.HTTPS_PORT}")
    print(f"  Certificate: {config.HTTPS_CERT_PATH}")
    print(f"  Database: {config.DATABASE_PATH}")
    print(f"  SCEP Enabled: {config.SCEP_ENABLED}")
    print(f"{'='*60}\n")
    
    if config.SCEP_ENABLED:
        print(f"  SCEP Endpoint: https://{config.HOST}:{config.HTTPS_PORT}/scep/pkiclient.exe")
        print(f"{'='*60}\n")
    
    # Run HTTPS server
    try:
        app.run(
            host=config.HOST,
            port=config.HTTPS_PORT,
            ssl_context=ssl_context,
            debug=config.DEBUG,
            threaded=True
        )
    finally:
        # Cleanup temp CA file
        if ca_cert_path and os.path.exists(ca_cert_path):
            try:
                os.unlink(ca_cert_path)
            except:
                pass


if __name__ == "__main__":
    main()
