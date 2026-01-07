"""
Ultimate CA Manager - Configuration Management
Handles all application settings with web UI configuration support
"""
import os
from pathlib import Path
from typing import Optional
from datetime import timedelta
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = BASE_DIR / "backend"
DATA_DIR = BACKEND_DIR / "data"

# Ensure data directories exist
DATA_DIR.mkdir(exist_ok=True)
(DATA_DIR / "ca").mkdir(exist_ok=True)
(DATA_DIR / "certs").mkdir(exist_ok=True)
(DATA_DIR / "private").mkdir(mode=0o700, exist_ok=True)
(DATA_DIR / "crl").mkdir(exist_ok=True)
(DATA_DIR / "scep").mkdir(exist_ok=True)
(DATA_DIR / "backups").mkdir(exist_ok=True)

# Load environment variables
load_dotenv(BASE_DIR / ".env")


class Config:
    """Base configuration - values can be overridden by database settings"""
    
    # Application
    APP_NAME = os.getenv("APP_NAME", "Ultimate CA Manager")
    APP_VERSION = os.getenv("APP_VERSION", "1.7.0")
    SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32).hex())
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    
    # Server - HTTPS mandatory
    HOST = os.getenv("HOST", "0.0.0.0")
    HTTPS_PORT = int(os.getenv("HTTPS_PORT", "8443"))
    HTTP_REDIRECT = os.getenv("HTTP_REDIRECT", "true").lower() == "true"
    
    # HTTPS Certificate (auto-generated if not exists)
    HTTPS_CERT_PATH = DATA_DIR / "https_cert.pem"
    HTTPS_KEY_PATH = DATA_DIR / "https_key.pem"
    HTTPS_AUTO_GENERATE = os.getenv("HTTPS_AUTO_GENERATE", "true").lower() == "true"
    
    # Database
    DATABASE_PATH = DATA_DIR / "ucm.db"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # JWT Authentication
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.urandom(32).hex())
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES", "3600"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES", "2592000"))
    )
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"
    
    # Session Configuration
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
