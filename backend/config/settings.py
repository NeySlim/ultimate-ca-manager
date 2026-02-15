"""
Ultimate CA Manager - Configuration Management
Handles all application settings with web UI configuration support
"""
import os
import secrets
import subprocess
from pathlib import Path
from typing import Optional
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables FIRST (before using them)
# Try multiple locations for .env files
load_dotenv("/etc/ucm/ucm.env")  # System config (DEB/RPM)
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")  # Local dev

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = BASE_DIR / "backend"

# DATA_DIR is configurable via environment for RPM (/var/lib/ucm) vs DEB (/opt/ucm/data)
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data")))

# Ensure data directories exist (may fail for permission reasons - that's OK)
try:
    DATA_DIR.mkdir(exist_ok=True)
except PermissionError:
    pass  # Directory should already exist from package install


def is_docker():
    """Detect if running in Docker container"""
    return os.path.exists('/.dockerenv') or os.environ.get('UCM_DOCKER') == '1'


def restart_ucm_service():
    """
    Restart UCM service - Multi-distro compatible without sudo
    Uses signal file + graceful exit for automatic restart
    Returns: (success: bool, message: str)
    """
    if is_docker():
        # Docker: Use same signal file mechanism
        # Container will auto-restart (restart: unless-stopped in docker-compose.yml)
        try:
            restart_signal = DATA_DIR / '.restart_requested'
            restart_signal.write_text('restart')
            
            import time
            time.sleep(0.5)
            
            return True, "✅ Certificate updated. Service will restart automatically in 3-5 seconds. Please reload the page."
            
        except Exception as e:
            return False, f"❌ Failed to create restart signal: {str(e)}"
    
    # Native installation - multiple restart strategies
    
    # Strategy 1: Process replacement (instant, no permissions needed)
    # Create restart signal file for app.py to detect and self-restart
    try:
        restart_signal = DATA_DIR / '.restart_requested'
        restart_signal.write_text('restart')
        
        # Give app time to detect the signal
        import time
        time.sleep(0.5)
        
        return True, "✅ Service restart initiated. Please wait 5 seconds and reload the page."
        
    except Exception as e:
        # Strategy 2: Try systemctl (works if permissions allow)
        try:
            result = subprocess.run(
                ['systemctl', 'restart', 'ucm'],
                capture_output=True,
                timeout=3,
                check=False
            )
            if result.returncode == 0:
                return True, "✅ Service restart initiated. Please wait 10 seconds and reload the page."
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Strategy 3: Try service command (SysV)
        try:
            result = subprocess.run(
                ['service', 'ucm', 'restart'],
                capture_output=True,
                timeout=3,
                check=False
            )
            if result.returncode == 0:
                return True, "✅ Service restart initiated. Please wait 10 seconds and reload the page."
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # If all automated methods fail, user must restart manually
        return True, "✅ Certificate updated successfully. ⚠️ Please restart the service manually:\n\nsystemctl restart ucm\n\nor\n\nservice ucm restart"


def get_system_fqdn():
    """
    Get system FQDN based on environment:
    - Docker: Use UCM_FQDN env var (MUST be set)
    - Native: Use hostname -f command or FQDN env var
    Returns None if not configured or on error
    """
    # Docker: MUST use environment variable
    if is_docker():
        return os.getenv('UCM_FQDN')
    
    # Native installation: Try hostname -f first
    try:
        result = subprocess.run(
            ['hostname', '-f'],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            fqdn = result.stdout.strip()
            # Validate it's not just a hostname (has a dot)
            if fqdn and '.' in fqdn and fqdn not in ['localhost', 'localhost.localdomain']:
                return fqdn
    except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Fallback: Check environment variable
    env_fqdn = os.getenv('FQDN')
    if env_fqdn and env_fqdn not in ['localhost', 'ucm.local', 'ucm.example.com']:
        return env_fqdn
    
    # Last resort: Will be loaded from database later via Config.get_db_setting()
    return None


class Config:
    """Base configuration - values can be overridden by database settings"""
    
    # Application
    APP_NAME = os.getenv("APP_NAME", "Ultimate CA Manager")
    
    # Version - single source of truth from VERSION file
    @staticmethod
    def _get_version():
        """Read version from VERSION file"""
        try:
            version_path = BASE_DIR / "VERSION"
            if version_path.exists():
                return version_path.read_text().strip()
            # Docker: VERSION might be at root
            docker_version = Path("/opt/ucm/VERSION")
            if docker_version.exists():
                return docker_version.read_text().strip()
        except Exception:
            pass
        return os.getenv("APP_VERSION", "2.1.0")
    
    APP_VERSION = _get_version.__func__()
    
    # SECRET_KEY validation - deferred to runtime
    _secret_key = os.getenv("SECRET_KEY")
    
    # For packaging: allow missing secrets during install, but validate at runtime
    SECRET_KEY = _secret_key if _secret_key else "INSTALL_TIME_PLACEHOLDER"
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    
    # Server - HTTPS mandatory
    HOST = os.getenv("HOST", "0.0.0.0")
    HTTPS_PORT = int(os.getenv("HTTPS_PORT", "8443"))
    HTTP_REDIRECT = os.getenv("HTTP_REDIRECT", "true").lower() == "true"
    
    # HTTPS Certificate
    # Respect package installation paths: /var/lib/ucm (Debian) or /etc/ucm (RPM)
    # Fallback to DATA_DIR for Docker or manual installations
    _https_cert_default = str(DATA_DIR / "https_cert.pem")
    _https_key_default = str(DATA_DIR / "https_key.pem")
    
    HTTPS_CERT_PATH = Path(os.getenv("HTTPS_CERT_PATH", _https_cert_default))
    HTTPS_KEY_PATH = Path(os.getenv("HTTPS_KEY_PATH", _https_key_default))
    HTTPS_AUTO_GENERATE = os.getenv("HTTPS_AUTO_GENERATE", "true").lower() == "true"
    
    # File Upload Limits (security)
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max (base64 inflates ~33%)
    
    # Database
    # Supports SQLite (default) or PostgreSQL for high availability
    # DATABASE_URL takes precedence (PostgreSQL), else fallback to SQLite
    _db_url = os.getenv("DATABASE_URL")
    _db_default = str(DATA_DIR / "ucm.db")
    DATABASE_PATH = Path(os.getenv("DATABASE_PATH", _db_default))
    
    if _db_url:
        # PostgreSQL or external database (HA mode)
        # Format: postgresql://user:password@host:port/dbname
        SQLALCHEMY_DATABASE_URI = _db_url
        DATABASE_TYPE = "postgresql" if "postgresql" in _db_url else "external"
    else:
        # SQLite (standalone mode)
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
        DATABASE_TYPE = "sqlite"
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # PostgreSQL-specific settings
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
    } if _db_url else {}
    
    
    @classmethod
    def validate_secrets(cls):
        """Validate that secrets are properly set - called at app startup"""
        if cls.SECRET_KEY == "INSTALL_TIME_PLACEHOLDER" or not cls.SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be set in environment. "
                "Check /etc/ucm/ucm.env or load environment variables."
            )
    
    # Session settings
    
    # Session Configuration - Flask server-side sessions
    # Supports filesystem (default) or Redis (HA mode)
    _redis_url = os.getenv("REDIS_URL")
    
    if _redis_url:
        # Redis session store for HA deployments
        SESSION_TYPE = 'redis'
        SESSION_REDIS = _redis_url  # Will be converted to Redis connection in app.py
        SESSION_KEY_PREFIX = os.getenv("SESSION_KEY_PREFIX", "ucm:session:")
    else:
        # Filesystem sessions for standalone deployment
        SESSION_TYPE = 'filesystem'
        SESSION_FILE_DIR = DATA_DIR / 'sessions'
    
    SESSION_COOKIE_SECURE = True  # HTTPS only
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)  # 24 hours session
    SESSION_REFRESH_EACH_REQUEST = True  # Reset timeout on each request
    
    # Initial Admin User (only used on first run)
    # SECURITY: Default password should be random in production
    # Generate random password if not set explicitly
    @staticmethod
    def _get_initial_password():
        """Get initial admin password - generate random if not set"""
        env_password = os.getenv("INITIAL_ADMIN_PASSWORD")
        if env_password and env_password != "changeme123":
            return env_password
        # In production, generate random password and log it
        import secrets
        import string
        # 16 chars with upper, lower, digits, special
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        random_pass = ''.join(secrets.choice(alphabet) for _ in range(16))
        return random_pass
    
    INITIAL_ADMIN_USERNAME = os.getenv("INITIAL_ADMIN_USERNAME", "admin")
    INITIAL_ADMIN_PASSWORD = os.getenv("INITIAL_ADMIN_PASSWORD", "changeme123")  # Will be overridden at init
    INITIAL_ADMIN_EMAIL = os.getenv("INITIAL_ADMIN_EMAIL", "admin@localhost")
    
    # SCEP Configuration
    SCEP_ENABLED = os.getenv("SCEP_ENABLED", "true").lower() == "true"
    SCEP_CA_ID = os.getenv("SCEP_CA_ID")
    # Generate random SCEP password if not configured (security: avoid weak defaults)
    SCEP_CHALLENGE_PASSWORD = os.getenv("SCEP_CHALLENGE_PASSWORD") or secrets.token_urlsafe(16)
    SCEP_AUTO_APPROVE = os.getenv("SCEP_AUTO_APPROVE", "false").lower() == "true"
    SCEP_CERT_LIFETIME = int(os.getenv("SCEP_CERT_LIFETIME", "365"))
    SCEP_KEY_SIZE = int(os.getenv("SCEP_KEY_SIZE", "2048"))
    SCEP_RENEWAL_DAYS = int(os.getenv("SCEP_RENEWAL_DAYS", "30"))
    
    # Rate Limiting
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = DATA_DIR / "ucm.log"
    AUDIT_LOG_FILE = DATA_DIR / "audit.log"
    
    # CORS - auto-include FQDN if set
    _cors_origins = ["https://localhost:8443", "https://127.0.0.1:8443"]
    _fqdn = get_system_fqdn()
    _https_port = int(os.getenv("HTTPS_PORT", "8443"))
    if _fqdn and _fqdn not in ('localhost', '127.0.0.1', 'ucm.example.com', 'ucm.local'):
        _cors_origins.append(f"https://{_fqdn}:{_https_port}")
    # Allow extra origins via env
    _extra = os.getenv("CORS_EXTRA_ORIGINS", "")
    if _extra:
        _cors_origins.extend([o.strip() for o in _extra.split(",") if o.strip()])
    CORS_ORIGINS = _cors_origins
    
    # FQDN for redirect - auto-detected based on environment
    # Docker: Uses UCM_FQDN env var
    # Native: Uses hostname -f or FQDN env var
    FQDN = get_system_fqdn()
    HTTP_PORT = int(os.getenv("HTTP_PORT", "80"))  # For redirect URL construction
    
    # File paths
    CA_DIR = DATA_DIR / "ca"
    CERT_DIR = DATA_DIR / "certs"
    PRIVATE_DIR = DATA_DIR / "private"
    CRL_DIR = DATA_DIR / "crl"
    SCEP_DIR = DATA_DIR / "scep"
    BACKUP_DIR = DATA_DIR / "backups"
    
    @classmethod
    def get_db_setting(cls, key: str, default=None):
        """Retrieve setting from database (overrides env vars)"""
        # Will be implemented after DB models are created
        return default
    
    @classmethod
    def set_db_setting(cls, key: str, value):
        """Store setting in database"""
        # Will be implemented after DB models are created
        pass


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    DEBUG = True
    DATABASE_PATH = ":memory:"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


# Configuration dictionary
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": ProductionConfig,
}


def get_config(env: Optional[str] = None) -> Config:
    """Get configuration based on environment"""
    if env is None:
        env = os.getenv("FLASK_ENV", "production")
    return config.get(env, config["default"])
