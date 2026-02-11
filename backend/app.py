"""
Ultimate CA Manager - Main Application
Flask application with HTTPS-only enforcement
"""
import os
from os import environ
import sys
from pathlib import Path
from flask import Flask, redirect, request
from flask_cors import CORS
from flask_migrate import Migrate
from flask_caching import Cache
from flask_session import Session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from flasgger import Swagger

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import get_config, BASE_DIR
from config.https_manager import HTTPSManager
from models import db, User, SystemConfig
from websocket import socketio, init_websocket

# Initialize cache globally
cache = Cache()

# Initialize rate limiter globally
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute", "2000 per hour"],
    storage_uri="memory://"
)


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
    
    # Reverse proxy support (handles X-Forwarded-* headers)
    # Safe to enable even without proxy - only activates if headers present
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=1,      # X-Forwarded-For (client IP)
        x_proto=1,    # X-Forwarded-Proto (http/https)
        x_host=1,     # X-Forwarded-Host (original host)
        x_prefix=1    # X-Forwarded-Prefix (URL prefix)
    )
    
    # Validate secrets at runtime (not during package installation)
    try:
        config.validate_secrets()
    except ValueError as e:
        app.logger.error(f"Configuration error: {e}")
        # During install, this is OK - the service will fail to start until configured
        # but the package installation should complete
        if not os.getenv("UCM_SKIP_SECRET_VALIDATION"):
            raise
    
    # Ensure HTTPS certificate exists
    if config.HTTPS_AUTO_GENERATE:
        HTTPSManager.ensure_https_cert(
            config.HTTPS_CERT_PATH,
            config.HTTPS_KEY_PATH,
            auto_generate=True
        )
    
    # Run schema migrations BEFORE SQLAlchemy init (critical for upgrades)
    # This ensures columns/tables exist before models are mapped
    try:
        from migration_runner import run_all_migrations
        db_path = config.DATABASE_PATH
        if db_path and os.path.exists(db_path):
            os.environ.setdefault('DATABASE_PATH', str(db_path))
            run_all_migrations(dry_run=False, verbose=False)
    except Exception as e:
        app.logger.warning(f"Pre-init migration check: {e}")
    
    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    
    # Log database type
    app.logger.info(f"✓ Database: {config.DATABASE_TYPE.upper()}")
    
    # Initialize server-side session storage
    # If Redis URL is configured, set up Redis connection
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        try:
            import redis
            app.config['SESSION_REDIS'] = redis.from_url(redis_url)
            app.logger.info("✓ Redis session store enabled")
        except ImportError:
            app.logger.warning("⚠ redis library not installed, falling back to filesystem sessions")
            app.config['SESSION_TYPE'] = 'filesystem'
            app.config['SESSION_FILE_DIR'] = config.DATA_DIR / 'sessions'
    
    Session(app)
    
    # Ensure session directory exists with correct permissions (filesystem mode)
    session_dir = app.config.get('SESSION_FILE_DIR')
    if session_dir:
        session_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize cache
    cache.init_app(app, config={
        'CACHE_TYPE': 'SimpleCache',  # In-memory cache
        'CACHE_DEFAULT_TIMEOUT': 300   # 5 minutes default
    })
    
    # Initialize rate limiter
    if config.RATE_LIMIT_ENABLED:
        limiter.init_app(app)
        app.logger.info("✓ Rate limiting enabled")
    
    # Initialize WebSocket support
    init_websocket(app)
    app.logger.info("✓ WebSocket support enabled")
    
    # CORS - only HTTPS origins (includes WebSocket)
    CORS(app, resources={
        r"/api/*": {
            "origins": config.CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
            "allow_headers": ["Content-Type", "Authorization", "X-CSRF-Token"],
            "supports_credentials": True
        },
        r"/socket.io/*": {
            "origins": config.CORS_ORIGINS,
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True
        }
    })
    
    # Swagger/OpenAPI Documentation
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": 'apispec',
                "route": '/api/docs/apispec.json',
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/api/docs"
    }
    
    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": "UCM API v2.0",
            "description": "Ultimate Certificate Manager - REST API Documentation",
            "version": "2.0.0",
            "contact": {
                "name": "UCM Support",
                "url": "https://github.com/your-org/ucm"
            }
        },
        "basePath": "/api/v2",
        "schemes": ["https"],
        "securityDefinitions": {
            "ApiKey": {
                "type": "apiKey",
                "name": "X-API-Key",
                "in": "header",
                "description": "API Key authentication. Example: 'ucm_ak_...'"
            },
            "Session": {
                "type": "apiKey",
                "name": "Cookie",
                "in": "header",
                "description": "Session cookie (set after login)"
            }
        },
        "security": [{"ApiKey": []}, {"Session": []}],
        "tags": [
            {"name": "auth", "description": "Authentication endpoints"},
            {"name": "cas", "description": "Certificate Authorities"},
            {"name": "certificates", "description": "Certificates management"},
            {"name": "csrs", "description": "Certificate Signing Requests"},
            {"name": "crl", "description": "Certificate Revocation Lists"},
            {"name": "acme", "description": "ACME protocol"},
            {"name": "scep", "description": "SCEP protocol"},
            {"name": "dashboard", "description": "Dashboard statistics"},
            {"name": "users", "description": "User management"},
            {"name": "settings", "description": "System settings"},
            {"name": "templates", "description": "Certificate templates"},
            {"name": "truststore", "description": "Trust store"},
            {"name": "account", "description": "Account management"},
            {"name": "system", "description": "System operations"}
        ]
    }
    
    Swagger(app, config=swagger_config, template=swagger_template)
    
    # Initialize mTLS middleware
    from middleware.mtls_middleware import init_mtls_middleware
    init_mtls_middleware(app)
    
    # Create database tables FIRST (before scheduler which may query DB)
    # Use file lock to prevent race condition with multiple Gunicorn workers
    app.logger.info("=" * 60)
    app.logger.info("Starting database initialization...")
    app.logger.info("=" * 60)
    
    import fcntl
    import time
    from config.settings import DATA_DIR
    
    lock_file = os.path.join(DATA_DIR, '.db_init.lock')
    
    with app.app_context():
        # Acquire exclusive lock to ensure only one worker initializes DB
        with open(lock_file, 'w') as lock:
            app.logger.info("Waiting for database initialization lock...")
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            app.logger.info("✓ Database lock acquired")
            
            try:
                # Check if DB is already initialized by another worker
                from sqlalchemy import inspect
                inspector = inspect(db.engine)
                tables = inspector.get_table_names()
                
                if 'users' in tables and 'certificate_authorities' in tables:
                    app.logger.info("✓ Database tables already exist")
                else:
                    # Create all tables
                    app.logger.info("Creating database tables...")
                    db.create_all()
                    app.logger.info("✓ Database tables created/verified")
                
                # ===== EXTENDED TABLES =====
                # Import models to register them with SQLAlchemy
                try:
                    from models.rbac import CustomRole, RolePermission
                    from models.sso import SSOProvider, SSOSession
                    from models.policy import CertificatePolicy, ApprovalRequest
                    from models.hsm import HsmProvider, HsmKey
                    from services.webhook_service import WebhookEndpoint
                    
                    # Check if tables exist, create if missing
                    inspector = inspect(db.engine)
                    tables = inspector.get_table_names()
                    extended_tables = ['pro_custom_roles', 'pro_role_permissions', 
                                  'pro_sso_providers', 'pro_sso_sessions',
                                  'certificate_policies', 'approval_requests',
                                  'hsm_providers', 'hsm_keys',
                                  'webhook_endpoints']
                    missing = [t for t in extended_tables if t not in tables]
                    
                    if missing:
                        app.logger.info(f"Creating tables: {', '.join(missing)}")
                        db.create_all()
                        app.logger.info("✓ Extended database tables created")
                    else:
                        app.logger.info("✓ Extended database tables already exist")
                except ImportError:
                    pass
                # =======================
                
                # Always verify critical tables exist (whether just created or pre-existing)
                inspector = inspect(db.engine)
                tables = inspector.get_table_names()
                
                critical_tables = ['users', 'certificate_authorities', 'certificates', 'crl_metadata']
                missing_tables = [t for t in critical_tables if t not in tables]
                
                if missing_tables:
                    raise RuntimeError(f"Critical tables missing: {missing_tables}")
                
                app.logger.info(f"✓ All critical tables verified: {', '.join(critical_tables)}")
                
                # Migrations already run at startup before SQLAlchemy init
                
                # Run database health check and repair
                app.logger.info("Running database health check...")
                from database_health import check_and_repair_database
                check_and_repair_database(app)
                app.logger.info("✓ Database health check complete")
                
                # Initialize default data (runs even if tables already existed)
                app.logger.info("Initializing default data...")
                init_database(app)
                app.logger.info("✓ Default data initialized")
                
            except Exception as e:
                app.logger.error(f"❌ FATAL: Database initialization failed: {e}")
                raise
            finally:
                # Lock is automatically released when exiting 'with' block
                app.logger.info("✓ Database lock released")
    
    app.logger.info("=" * 60)
    app.logger.info("✓ DATABASE INITIALIZATION COMPLETE - Safe to proceed")
    app.logger.info("=" * 60)
    
    # Regenerate certificate/key files from database if missing
    try:
        with app.app_context():
            from services.file_regen_service import regenerate_all_files
            stats = regenerate_all_files()
            if sum(stats.values()) > 0:
                app.logger.info(f"✓ File regeneration completed: {stats}")
    except Exception as e:
        app.logger.warning(f"File regeneration failed (non-fatal): {e}")
    
    # Initialize general task scheduler (CRL auto-regen, etc) - AFTER database is ready
    try:
        from services.scheduler_service import init_scheduler
        from services.crl_scheduler_task import CRLSchedulerTask
        
        # Initialize and start scheduler (using global instance)
        # using autostart=False to ensure tasks are registered before first run
        scheduler = init_scheduler(app=app, autostart=False)
        
        # Register CRL auto-regeneration task (runs every hour)
        scheduler.register_task(
            name="crl_auto_regen",
            func=CRLSchedulerTask.execute,
            interval=3600,  # "interval" parameter, not "interval_seconds"
            description="Auto-regenerate expiring CRLs"
        )
        
        # Register audit log cleanup task (runs daily)
        try:
            from services.retention_service import scheduled_audit_cleanup
            scheduler.register_task(
                name="audit_log_cleanup",
                func=scheduled_audit_cleanup,
                interval=86400,  # 24 hours
                description="Clean up old audit logs based on retention policy"
            )
            app.logger.info("Registered audit log cleanup task (daily)")
        except ImportError:
            pass
        
        # Register certificate expiry alert task (runs daily)
        try:
            from services.expiry_alert_service import scheduled_expiry_check
            scheduler.register_task(
                name="cert_expiry_alerts",
                func=scheduled_expiry_check,
                interval=86400,  # 24 hours
                description="Check for expiring certificates and send alerts"
            )
            app.logger.info("Registered certificate expiry alert task (daily)")
        except ImportError:
            pass
        
        # Register ACME auto-renewal task (runs every 6 hours)
        try:
            from services.acme_renewal_service import scheduled_acme_renewal
            scheduler.register_task(
                name="acme_auto_renewal",
                func=scheduled_acme_renewal,
                interval=21600,  # 6 hours
                description="Auto-renew Let's Encrypt certificates"
            )
            app.logger.info("Registered ACME auto-renewal task (every 6 hours)")
        except ImportError:
            pass
        
        # Start scheduler now that tasks are registered
        scheduler.start(app=app)
        app.logger.info("Scheduler service started with all tasks")
        
        # Register scheduler in app context for graceful shutdown
        app.scheduler = scheduler
    except Exception as e:
        app.logger.error(f"Failed to start scheduler service: {e}")
    
    # Register blueprints
    register_blueprints(app)
    
    # HSM availability check at startup
    try:
        from utils.hsm_check import log_hsm_warning
        log_hsm_warning()
    except Exception as e:
        app.logger.debug(f"HSM check skipped: {e}")
    
    # Security headers and cleanup
    @app.after_request
    def add_security_headers(response):
        """Add security headers and fix deprecated headers"""
        # Set Permissions-Policy without deprecated features
        # Only include valid features that are widely supported
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        
        # Add security headers if not present
        if 'Strict-Transport-Security' not in response.headers:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        if 'X-Content-Type-Options' not in response.headers:
            response.headers['X-Content-Type-Options'] = 'nosniff'
        if 'X-Frame-Options' not in response.headers:
            response.headers['X-Frame-Options'] = 'DENY'
        if 'X-XSS-Protection' not in response.headers:
            response.headers['X-XSS-Protection'] = '1; mode=block'
        
        return response
    
    # FQDN redirect middleware (redirect IP to FQDN if configured)
    @app.before_request
    def redirect_to_fqdn():
        # Skip for health checks and static files
        if request.path in ['/api/health', '/health', '/api/auth/verify', '/api/v2/auth/verify'] or request.path.startswith('/static/') or request.path.startswith('/assets/'):
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
    
    # Context processor to inject variables into all templates
    @app.context_processor
    def inject_global_vars():
        return {
            'is_self_signed': HTTPSManager.is_self_signed(config.HTTPS_CERT_PATH)
        }

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
                
                print(f"🔄 Restart signal detected! Initiating graceful shutdown...")
                
                # Schedule graceful shutdown after this request completes
                # Docker/Systemd will automatically restart the service
                def do_shutdown():
                    import time
                    import sys
                    
                    print(f"🔄 Shutdown thread started, waiting 1 second...")
                    time.sleep(1)  # Wait for response to be sent
                    
                    print(f"🔄 Executing os._exit(1) to trigger systemd/docker restart...")
                    sys.stdout.flush()  # Ensure logs are written
                    
                    # Exit with code 1 to trigger systemd restart (Restart=on-failure)
                    # Docker will restart regardless (restart: unless-stopped)
                    os._exit(1)
                
                import threading
                threading.Thread(target=do_shutdown, daemon=False).start()
                print(f"🔄 Shutdown thread launched")
                
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
    import sqlite3
    
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
    
    # Auto-detect and add missing columns (SQLAlchemy create_all doesn't add new columns to existing tables)
    def add_missing_columns():
        """Automatically add missing columns to existing tables"""
        conn = sqlite3.connect(app.config['DATABASE_PATH'])
        cursor = conn.cursor()
        
        # Define expected columns for tables that may need migration
        # Format: (column_name, sql_type, default_value_or_None)
        expected_columns = {
            'users': [
                ('totp_secret', 'VARCHAR(32)', None),
                ('totp_confirmed', 'BOOLEAN', '0'),
                ('backup_codes', 'TEXT', None),
                ('failed_logins', 'INTEGER', '0'),
                ('locked_until', 'DATETIME', None),
                ('login_count', 'INTEGER', '0'),
            ],
            'certificates': [
                ('archived', 'BOOLEAN', '0'),
                ('source', 'VARCHAR(50)', None),
                ('template_id', 'INTEGER', None),
                ('owner_group_id', 'INTEGER', None),
                ('key_algo', 'VARCHAR(20)', None),
                ('subject_cn', 'VARCHAR(255)', None),
            ],
            'certificate_authorities': [
                ('cdp_enabled', 'BOOLEAN', '0'),
                ('cdp_url', 'VARCHAR(512)', None),
                ('ocsp_enabled', 'BOOLEAN', '0'),
                ('ocsp_url', 'VARCHAR(512)', None),
                ('owner_group_id', 'INTEGER', None),
                ('serial_number', 'VARCHAR(64)', None),
            ],
            'groups': [
                ('description', 'TEXT', None),
            ],
            'audit_logs': [
                ('resource_name', 'VARCHAR(255)', None),
                ('entry_hash', 'VARCHAR(64)', None),
                ('prev_hash', 'VARCHAR(64)', None),
            ],
            'notification_log': [
                ('retry_count', 'INTEGER', '0'),
            ],
            'dns_providers': [
                ('zones', 'TEXT', None),
                ('enabled', 'BOOLEAN', '1'),
            ],
            'acme_client_orders': [
                ('account_url', 'VARCHAR(500)', None),
                ('renewal_enabled', 'BOOLEAN', '1'),
                ('last_renewal_at', 'DATETIME', None),
                ('renewal_failures', 'INTEGER', '0'),
                ('last_error_at', 'DATETIME', None),
            ],
        }
        
        for table, columns in expected_columns.items():
            # Get existing columns - skip if table doesn't exist
            try:
                cursor.execute(f"PRAGMA table_info({table})")
                existing_cols = {row[1] for row in cursor.fetchall()}
                if not existing_cols:
                    # Table doesn't exist yet, skip
                    continue
                    
                for col_name, col_type, default_value in columns:
                    if col_name not in existing_cols:
                        default_clause = f"DEFAULT {default_value}" if default_value else ""
                        sql = f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type} {default_clause}".strip()
                        app.logger.info(f"✅ Adding missing column: {table}.{col_name}")
                        cursor.execute(sql)
            except Exception as e:
                app.logger.debug(f"Skipping migration for {table}: {e}")
        
        conn.commit()
        conn.close()
    
    def create_missing_tables():
        """Create tables that SQLAlchemy might miss"""
        conn = sqlite3.connect(app.config['DATABASE_PATH'])
        cursor = conn.cursor()
        
        # Get existing tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        # Define tables to create if missing
        tables_sql = {
            'api_keys': """
                CREATE TABLE api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name VARCHAR(128) NOT NULL,
                    key_hash VARCHAR(256) NOT NULL,
                    key_preview VARCHAR(16),
                    permissions TEXT DEFAULT '[]',
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP,
                    expires_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """,
            'webauthn_credentials': """
                CREATE TABLE webauthn_credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    credential_id BLOB UNIQUE NOT NULL,
                    public_key BLOB NOT NULL,
                    sign_count INTEGER DEFAULT 0 NOT NULL,
                    name VARCHAR(128),
                    aaguid VARCHAR(36),
                    transports TEXT,
                    is_backup_eligible BOOLEAN DEFAULT 0,
                    is_backup_device BOOLEAN DEFAULT 0,
                    user_verified BOOLEAN DEFAULT 0,
                    enabled BOOLEAN DEFAULT 1 NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """,
            'webauthn_challenges': """
                CREATE TABLE webauthn_challenges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    challenge VARCHAR(128) UNIQUE NOT NULL,
                    challenge_type VARCHAR(20) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """
        }
        
        for table_name, create_sql in tables_sql.items():
            if table_name not in existing_tables:
                app.logger.info(f"Creating missing table: {table_name}")
                cursor.execute(create_sql)
                # Create indexes
                if table_name == 'api_keys':
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_key_hash ON api_keys(key_hash)")
                elif table_name == 'webauthn_credentials':
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_webauthn_credential_id ON webauthn_credentials(credential_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_webauthn_user_id ON webauthn_credentials(user_id)")
                elif table_name == 'webauthn_challenges':
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_webauthn_challenge ON webauthn_challenges(challenge)")
        
        conn.commit()
        conn.close()
    
    try:
        add_missing_columns()
        create_missing_tables()
    except Exception as e:
        app.logger.warning(f"Schema migration check failed (may be normal): {e}")
    
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
            if app.config['INITIAL_ADMIN_PASSWORD'] == 'changeme123':
                print(f"[SETUP] Using default password - CHANGE THIS IMMEDIATELY!")
            else:
                print(f"[SETUP] Using custom password from INITIAL_ADMIN_PASSWORD")
            print(f"[SETUP] Login and change password in Settings > Account\n")
    except IntegrityError:
        # Another worker already created the initial data
        db.session.rollback()
        pass
    
    # Create system certificate templates if none exist
    try:
        import json
        from models.certificate_template import CertificateTemplate
        
        if CertificateTemplate.query.count() == 0:
            app.logger.info("Creating system certificate templates...")
            
            templates = [
                {
                    "name": "Web Server (TLS/SSL)",
                    "description": "Standard HTTPS/TLS web server certificate",
                    "template_type": "web_server",
                    "key_type": "RSA-2048",
                    "validity_days": 397,
                    "digest": "sha256",
                    "dn_template": json.dumps({"CN": "{hostname}", "O": "Organization", "OU": "IT"}),
                    "extensions_template": json.dumps({
                        "key_usage": ["digitalSignature", "keyEncipherment"],
                        "extended_key_usage": ["serverAuth"],
                        "basic_constraints": {"ca": False},
                        "san_types": ["dns", "ip"]
                    }),
                    "is_system": True
                },
                {
                    "name": "Client Certificate",
                    "description": "User authentication certificate for client devices",
                    "template_type": "client_auth",
                    "key_type": "RSA-2048",
                    "validity_days": 365,
                    "digest": "sha256",
                    "dn_template": json.dumps({"CN": "{username}", "emailAddress": "{email}"}),
                    "extensions_template": json.dumps({
                        "key_usage": ["digitalSignature", "keyEncipherment"],
                        "extended_key_usage": ["clientAuth"],
                        "basic_constraints": {"ca": False},
                        "san_types": ["email"]
                    }),
                    "is_system": True
                },
                {
                    "name": "VPN Server",
                    "description": "VPN server certificate (OpenVPN, IPsec, etc.)",
                    "template_type": "vpn_server",
                    "key_type": "RSA-2048",
                    "validity_days": 730,
                    "digest": "sha256",
                    "dn_template": json.dumps({"CN": "{hostname}", "O": "Organization"}),
                    "extensions_template": json.dumps({
                        "key_usage": ["digitalSignature", "keyEncipherment"],
                        "extended_key_usage": ["serverAuth"],
                        "basic_constraints": {"ca": False},
                        "san_types": ["dns", "ip"]
                    }),
                    "is_system": True
                },
                {
                    "name": "Email (S/MIME)",
                    "description": "Email encryption and signing certificate",
                    "template_type": "email",
                    "key_type": "RSA-2048",
                    "validity_days": 365,
                    "digest": "sha256",
                    "dn_template": json.dumps({"CN": "{username}", "emailAddress": "{email}"}),
                    "extensions_template": json.dumps({
                        "key_usage": ["digitalSignature", "keyEncipherment"],
                        "extended_key_usage": ["emailProtection"],
                        "basic_constraints": {"ca": False},
                        "san_types": ["email"]
                    }),
                    "is_system": True
                },
                {
                    "name": "Certificate Authority",
                    "description": "Certificate Authority (CA) for signing other certificates",
                    "template_type": "ca",
                    "key_type": "RSA-4096",
                    "validity_days": 3650,
                    "digest": "sha256",
                    "dn_template": json.dumps({"CN": "{ca_name}", "O": "Organization"}),
                    "extensions_template": json.dumps({
                        "key_usage": ["keyCertSign", "cRLSign"],
                        "basic_constraints": {"ca": True, "path_length": 0},
                        "san_types": []
                    }),
                    "is_system": True
                },
                {
                    "name": "Code Signing",
                    "description": "Code signing certificate for software/drivers",
                    "template_type": "code_signing",
                    "key_type": "RSA-2048",
                    "validity_days": 365,
                    "digest": "sha256",
                    "dn_template": json.dumps({"CN": "{username}", "O": "Organization"}),
                    "extensions_template": json.dumps({
                        "key_usage": ["digitalSignature"],
                        "extended_key_usage": ["codeSigning"],
                        "basic_constraints": {"ca": False},
                        "san_types": []
                    }),
                    "is_system": True
                }
            ]
            
            for tmpl_data in templates:
                tmpl = CertificateTemplate(**tmpl_data)
                db.session.add(tmpl)
            
            db.session.commit()
            app.logger.info(f"✓ Created {len(templates)} system certificate templates")
    except IntegrityError:
        db.session.rollback()
        app.logger.info("✓ System templates already exist")
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Failed to create system templates: {e}")
    
    # Generate self-signed HTTPS certificate if none exists
    try:
        from pathlib import Path
        from config.settings import DATA_DIR
        https_cert_path = DATA_DIR / 'https_cert.pem'
        https_key_path = DATA_DIR / 'https_key.pem'
        
        if not https_cert_path.exists() or not https_key_path.exists():
            app.logger.info("No HTTPS certificate found, generating self-signed certificate...")
            
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from datetime import timedelta
            import socket
            import ipaddress
            
            # Get hostname
            try:
                hostname = socket.gethostname()
            except:
                hostname = 'ucm.local'
            
            # Generate private key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
            
            # Create certificate
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, hostname[:64]),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "UCM Self-Signed"),
            ])
            
            cert_builder = x509.CertificateBuilder()
            cert_builder = cert_builder.subject_name(subject)
            cert_builder = cert_builder.issuer_name(issuer)
            cert_builder = cert_builder.public_key(private_key.public_key())
            cert_builder = cert_builder.serial_number(x509.random_serial_number())
            cert_builder = cert_builder.not_valid_before(datetime.utcnow())
            cert_builder = cert_builder.not_valid_after(datetime.utcnow() + timedelta(days=3650))
            
            # Add Subject Alternative Names
            san_list = [
                x509.DNSName(hostname),
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))
            ]
            
            cert_builder = cert_builder.add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False
            )
            
            # Self-sign certificate
            certificate = cert_builder.sign(private_key, hashes.SHA256())
            
            # Write cert and key
            https_cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
            https_key_path.write_bytes(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
            
            # Set permissions
            os.chmod(https_key_path, 0o600)
            os.chmod(https_cert_path, 0o644)
            
            app.logger.info(f"✓ Self-signed HTTPS certificate created (CN={hostname}, 10 years)")
        else:
            app.logger.info("✓ HTTPS certificate already exists")
    except Exception as e:
        app.logger.error(f"Failed to generate HTTPS certificate: {e}")
    
    # ===== INITIALIZE DEFAULT DATA =====
    try:
        from models.group import Group
        from models.rbac import CustomRole, RolePermission
        
        # Create default groups if none exist
        if Group.query.count() == 0:
            app.logger.info("Creating default Pro groups...")
            
            default_groups = [
                Group(
                    name="Administrators",
                    description="Full system administrators with all permissions",
                    permissions='["*"]'
                ),
                Group(
                    name="Certificate Operators",
                    description="Can manage certificates and CSRs",
                    permissions='["read:certificates", "write:certificates", "read:csrs", "write:csrs", "read:cas"]'
                ),
                Group(
                    name="Auditors",
                    description="Read-only access to audit logs and system status",
                    permissions='["read:audit", "read:dashboard", "read:certificates", "read:cas"]'
                )
            ]
            
            for group in default_groups:
                db.session.add(group)
            
            db.session.commit()
            app.logger.info(f"✓ Created {len(default_groups)} default Pro groups")
        
        # Create default custom roles if none exist
        if CustomRole.query.count() == 0:
            app.logger.info("Creating default Pro roles...")
            
            # System roles (built-in, cannot be deleted)
            system_roles = [
                {
                    "name": "Administrator",
                    "description": "Full system access with all permissions",
                    "is_system": True,
                    "permissions": ["*"]  # Wildcard = all permissions
                },
                {
                    "name": "Operator",
                    "description": "Day-to-day certificate operations",
                    "is_system": True,
                    "permissions": [
                        "read:dashboard", "read:cas", "read:certificates", "write:certificates",
                        "read:csrs", "write:csrs", "read:templates", "read:crl", "write:crl",
                        "read:scep", "read:acme", "read:truststore", "write:truststore"
                    ]
                },
                {
                    "name": "User",
                    "description": "Basic read access to certificates",
                    "is_system": True,
                    "permissions": [
                        "read:dashboard", "read:certificates", "read:cas", "read:templates"
                    ]
                }
            ]
            
            # Custom roles (can be modified/deleted)
            custom_roles = [
                {
                    "name": "Certificate Manager",
                    "description": "Full certificate lifecycle management",
                    "permissions": [
                        "read:certificates", "write:certificates", "delete:certificates",
                        "read:csrs", "write:csrs", "delete:csrs",
                        "read:templates", "read:cas"
                    ]
                },
                {
                    "name": "CA Administrator",
                    "description": "Certificate Authority management",
                    "permissions": [
                        "read:cas", "write:cas", "delete:cas",
                        "read:certificates", "write:certificates",
                        "read:crl", "write:crl"
                    ]
                },
                {
                    "name": "Security Auditor",
                    "description": "Read-only audit and compliance access",
                    "permissions": [
                        "read:audit", "read:dashboard", "read:certificates",
                        "read:cas", "read:users", "read:settings"
                    ]
                }
            ]
            
            # Create system roles first
            for role_data in system_roles:
                role = CustomRole(
                    name=role_data["name"],
                    description=role_data["description"],
                    permissions=role_data["permissions"],
                    is_system=True
                )
                db.session.add(role)
            
            # Create custom roles
            for role_data in custom_roles:
                role = CustomRole(
                    name=role_data["name"],
                    description=role_data["description"],
                    permissions=role_data["permissions"],
                    is_system=False
                )
                db.session.add(role)
            
            db.session.commit()
            app.logger.info(f"✓ Created {len(system_roles)} system roles and {len(custom_roles)} custom roles")
    
    except ImportError:
        pass  # Pro not available
    except Exception as e:
        db.session.rollback()
        app.logger.warning(f"⚠️ Failed to initialize Pro default data: {e}")


def register_blueprints(app):
    """Register all API blueprints"""
    # Import UI and public routes
    from api.ui_routes import ui_bp
    from api.cdp_routes import cdp_bp
    from api.ocsp_routes import ocsp_bp
    from api.health_routes import health_bp
    from api.scep_protocol import bp as scep_protocol_bp
    
    # Register Unified API v2.0 FIRST (routes already have /api/* prefix)
    # This must be before ui_bp which has catch-all routing
    from api.v2 import register_api_v2
    register_api_v2(app)
    
    # Public endpoints (no auth, no /api prefix - standard paths)
    app.register_blueprint(cdp_bp, url_prefix='/cdp')     # CRL Distribution Points
    app.register_blueprint(ocsp_bp)                        # OCSP Responder (/ocsp)
    app.register_blueprint(scep_protocol_bp)               # SCEP Protocol (/scep)
    app.register_blueprint(health_bp)  # Health check endpoints (no auth)
    
    # ACME Protocol (RFC 8555) - /acme/*
    try:
        from api.acme import acme_bp, acme_proxy_bp
        app.register_blueprint(acme_bp)
        app.register_blueprint(acme_proxy_bp)
        app.logger.info("✓ ACME protocol enabled (/acme, /acme/proxy)")
    except ImportError as e:
        app.logger.warning(f"⚠️ ACME protocol not available: {e}")
    
    # EST Protocol (RFC 7030) - /.well-known/est/*
    try:
        from api.est_protocol import bp as est_bp
        app.register_blueprint(est_bp)
        app.logger.info("✓ EST protocol enabled (/.well-known/est)")
    except ImportError:
        pass
    
    # Register UI routes LAST (catch-all for React SPA)
    app.register_blueprint(ui_bp)


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
