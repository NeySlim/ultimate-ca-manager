"""
Ultimate CA Manager - Configuration Management
Handles all application settings with web UI configuration support
"""
import os
import subprocess
from pathlib import Path
from typing import Optional
from datetime import timedelta
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = BASE_DIR / "backend"
# In /opt/ucm: data is at same level as backend/, not inside it
DATA_DIR = BASE_DIR / "data"

# Ensure data directories exist
DATA_DIR.mkdir(exist_ok=True)
# Don't create subdirectories at module import time (permission issues)
# They will be created on-demand when needed

# Load environment variables
load_dotenv(BASE_DIR / ".env")


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
    APP_VERSION = os.getenv("APP_VERSION", "1.11.0")
    
    # SECRET_KEY and JWT_SECRET_KEY validation - deferred to runtime
    _secret_key = os.getenv("SECRET_KEY")
    _jwt_secret = os.getenv("JWT_SECRET_KEY")
    
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
    
    # Database
    # Respect package installation DATABASE_PATH or fallback to DATA_DIR
    _db_default = str(DATA_DIR / "ucm.db")
    DATABASE_PATH = Path(os.getenv("DATABASE_PATH", _db_default))
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # JWT Authentication
    JWT_SECRET_KEY = _jwt_secret if _jwt_secret else "INSTALL_TIME_PLACEHOLDER"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", "3600"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES", "2592000"))
    )
    
    @classmethod
    def validate_secrets(cls):
        """Validate that secrets are properly set - called at app startup"""
        if cls.SECRET_KEY == "INSTALL_TIME_PLACEHOLDER" or not cls.SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be set in environment. "
                "Check /etc/ucm/ucm.env or load environment variables."
            )
        if cls.JWT_SECRET_KEY == "INSTALL_TIME_PLACEHOLDER" or not cls.JWT_SECRET_KEY:
            raise ValueError(
                "JWT_SECRET_KEY must be set in environment. "
                "Check /etc/ucm/ucm.env or load environment variables."
            )
    
    # JWT Cookies - Enable cookie-based auth for UI
    JWT_TOKEN_LOCATION = ["headers", "cookies"]  # Accept both headers and cookies
    JWT_COOKIE_SECURE = True  # Require HTTPS
    JWT_COOKIE_CSRF_PROTECT = False  # Disable CSRF for simplicity (we're using SameSite)
    JWT_COOKIE_SAMESITE = "Lax"  # Protect against CSRF
    JWT_ACCESS_COOKIE_NAME = "access_token_cookie"
    JWT_REFRESH_COOKIE_NAME = "refresh_token_cookie"
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"
    
    # Session Configuration - Flask server-side sessions
    SESSION_TYPE = 'filesystem'  # Server-side sessions for multi-worker support
    SESSION_FILE_DIR = DATA_DIR / 'sessions'
    SESSION_COOKIE_SECURE = True  # HTTPS only
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)  # 30 minutes session timeout
    SESSION_REFRESH_EACH_REQUEST = True  # Reset timeout on each request
    
    # Initial Admin User (only used on first run)
    INITIAL_ADMIN_USERNAME = os.getenv("INITIAL_ADMIN_USERNAME", "admin")
    INITIAL_ADMIN_PASSWORD = os.getenv("INITIAL_ADMIN_PASSWORD", "changeme123")
    INITIAL_ADMIN_EMAIL = os.getenv("INITIAL_ADMIN_EMAIL", "admin@localhost")
    
    # SCEP Configuration
    SCEP_ENABLED = os.getenv("SCEP_ENABLED", "true").lower() == "true"
    SCEP_CA_ID = os.getenv("SCEP_CA_ID")
    SCEP_CHALLENGE_PASSWORD = os.getenv("SCEP_CHALLENGE_PASSWORD", "changeme")
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
    
    # CORS
    CORS_ORIGINS = ["https://localhost:8443", "https://127.0.0.1:8443"]
    
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
