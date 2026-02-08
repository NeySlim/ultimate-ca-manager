"""
Rate Limiting Module
Per-endpoint rate limiting with configurable limits
Configurable via environment variables in /etc/ucm/ucm.env
"""
import os
import time
import logging
from collections import defaultdict
from threading import Lock
from typing import Dict, Any, Optional, Tuple
from functools import wraps
from flask import request, jsonify, g

logger = logging.getLogger(__name__)


def _get_env_int(key: str, default: int) -> int:
    """Get integer from environment variable"""
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def _get_env_bool(key: str, default: bool) -> bool:
    """Get boolean from environment variable"""
    val = os.environ.get(key, str(default)).lower()
    return val in ('true', '1', 'yes', 'on')


class RateLimitConfig:
    """Rate limit configuration per endpoint pattern
    
    Environment variables (set in /etc/ucm/ucm.env):
    
    RATE_LIMIT_ENABLED=true           # Enable/disable rate limiting globally
    RATE_LIMIT_AUTH_RPM=10            # Auth endpoints: requests per minute
    RATE_LIMIT_AUTH_BURST=3           # Auth endpoints: burst allowance
    RATE_LIMIT_HEAVY_RPM=30           # Heavy ops (issue cert, create CA): rpm
    RATE_LIMIT_HEAVY_BURST=5          # Heavy ops: burst
    RATE_LIMIT_STANDARD_RPM=120       # Standard API endpoints: rpm
    RATE_LIMIT_STANDARD_BURST=20      # Standard API: burst
    RATE_LIMIT_PROTOCOL_RPM=500       # Protocol (ACME/SCEP/OCSP): rpm
    RATE_LIMIT_PROTOCOL_BURST=100     # Protocol: burst
    RATE_LIMIT_WHITELIST=127.0.0.1,::1  # Comma-separated IPs to whitelist
    """
    
    # Limits loaded from environment or defaults
    _limits_loaded = False
    _default_limits: Dict[str, Dict] = {}
    
    @classmethod
    def _load_limits(cls):
        """Load limits from environment variables"""
        if cls._limits_loaded:
            return
        
        # Auth limits - more permissive defaults
        auth_rpm = _get_env_int('RATE_LIMIT_AUTH_RPM', 30)
        auth_burst = _get_env_int('RATE_LIMIT_AUTH_BURST', 10)
        
        # Heavy operation limits
        heavy_rpm = _get_env_int('RATE_LIMIT_HEAVY_RPM', 60)
        heavy_burst = _get_env_int('RATE_LIMIT_HEAVY_BURST', 15)
        
        # Standard API limits - higher for normal browsing
        standard_rpm = _get_env_int('RATE_LIMIT_STANDARD_RPM', 300)
        standard_burst = _get_env_int('RATE_LIMIT_STANDARD_BURST', 50)
        
        # Protocol limits (ACME, SCEP, OCSP, CDP)
        protocol_rpm = _get_env_int('RATE_LIMIT_PROTOCOL_RPM', 500)
        protocol_burst = _get_env_int('RATE_LIMIT_PROTOCOL_BURST', 100)
        
        cls._default_limits = {
            # Authentication - strict limits
            '/api/v2/auth/login': {'rpm': auth_rpm, 'burst': auth_burst},
            '/api/v2/auth/register': {'rpm': auth_rpm // 2, 'burst': auth_burst - 1},
            '/api/v2/auth/reset-password': {'rpm': auth_rpm // 2, 'burst': auth_burst - 1},
            # Public auth endpoints - no rate limit (read-only checks)
            '/api/v2/auth/email-configured': {'rpm': 1000, 'burst': 100},
            '/api/v2/sso/available': {'rpm': 1000, 'burst': 100},
            
            # Heavy operations - moderate limits
            '/api/v2/certificates/issue': {'rpm': heavy_rpm, 'burst': heavy_burst},
            '/api/v2/cas': {'rpm': heavy_rpm, 'burst': heavy_burst},
            '/api/v2/csrs/sign': {'rpm': heavy_rpm // 2, 'burst': heavy_burst},
            '/api/v2/import': {'rpm': heavy_rpm // 3, 'burst': 2},
            '/api/v2/export': {'rpm': heavy_rpm // 3, 'burst': 2},
            '/api/v2/backup': {'rpm': heavy_rpm // 6, 'burst': 2},
            
            # Standard endpoints - reasonable limits
            '/api/v2/users': {'rpm': standard_rpm // 2, 'burst': standard_burst // 2},
            '/api/v2/certificates': {'rpm': standard_rpm, 'burst': standard_burst},
            '/api/v2/audit': {'rpm': standard_rpm // 2, 'burst': standard_burst // 2},
            
            # Protocol endpoints - higher limits
            '/acme/': {'rpm': protocol_rpm // 2, 'burst': protocol_burst // 2},
            '/scep/': {'rpm': protocol_rpm // 2, 'burst': protocol_burst // 2},
            '/ocsp': {'rpm': protocol_rpm, 'burst': protocol_burst},
            '/cdp/': {'rpm': protocol_rpm, 'burst': protocol_burst},
            
            # Default for unspecified endpoints
            '_default': {'rpm': standard_rpm, 'burst': standard_burst}
        }
        
        # Load whitelist from env
        whitelist_str = os.environ.get('RATE_LIMIT_WHITELIST', '127.0.0.1,::1')
        if whitelist_str:
            for ip in whitelist_str.split(','):
                ip = ip.strip()
                if ip:
                    cls._whitelist.add(ip)
        
        cls._limits_loaded = True
        logger.info(f"Rate limits loaded: auth={auth_rpm}rpm, heavy={heavy_rpm}rpm, "
                   f"standard={standard_rpm}rpm, protocol={protocol_rpm}rpm")
    
    @classmethod
    def get_default_limits(cls) -> Dict[str, Dict]:
        """Get default limits (loads from env if not loaded)"""
        cls._load_limits()
        return cls._default_limits
    
    # Global settings
    _enabled: bool = None  # Will be loaded from env
    _custom_limits: Dict[str, Dict] = {}
    _whitelist: set = set()  # IPs that bypass rate limiting
    
    @classmethod
    def is_enabled(cls) -> bool:
        if cls._enabled is None:
            cls._enabled = _get_env_bool('RATE_LIMIT_ENABLED', True)
        return cls._enabled
    
    @classmethod
    def set_enabled(cls, enabled: bool):
        cls._enabled = enabled
        logger.info(f"Rate limiting {'enabled' if enabled else 'disabled'}")
    
    @classmethod
    def get_limit(cls, path: str) -> Dict[str, int]:
        """Get rate limit for a path"""
        cls._load_limits()
        
        # Check custom limits first
        for pattern, limit in cls._custom_limits.items():
            if path.startswith(pattern):
                return limit
        
        # Check default limits
        for pattern, limit in cls._default_limits.items():
            if pattern != '_default' and path.startswith(pattern):
                return limit
        
        return cls._default_limits['_default']
    
    @classmethod
    def set_custom_limit(cls, path: str, rpm: int, burst: int):
        """Set custom rate limit for a path pattern"""
        cls._custom_limits[path] = {'rpm': rpm, 'burst': burst}
        logger.info(f"Custom rate limit set: {path} -> {rpm} rpm, {burst} burst")
    
    @classmethod
    def remove_custom_limit(cls, path: str):
        """Remove custom rate limit"""
        if path in cls._custom_limits:
            del cls._custom_limits[path]
    
    @classmethod
    def add_whitelist(cls, ip: str):
        """Add IP to whitelist"""
        cls._whitelist.add(ip)
    
    @classmethod
    def remove_whitelist(cls, ip: str):
        """Remove IP from whitelist"""
        cls._whitelist.discard(ip)
    
    @classmethod
    def is_whitelisted(cls, ip: str) -> bool:
        """Check if IP is whitelisted"""
        cls._load_limits()  # Load whitelist from env
        return ip in cls._whitelist
    
    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """Get full configuration"""
        cls._load_limits()
        return {
            'enabled': cls.is_enabled(),
            'default_limits': cls._default_limits,
            'custom_limits': cls._custom_limits,
            'whitelist': list(cls._whitelist)
        }
    
    @classmethod
    def reload(cls):
        """Reload configuration from environment"""
        cls._limits_loaded = False
        cls._enabled = None
        cls._whitelist = set()
        cls._load_limits()
        logger.info("Rate limit configuration reloaded")


class RateLimiter:
    """
    Token bucket rate limiter with sliding window
    Thread-safe implementation
    """
    
    def __init__(self):
        self._buckets: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._lock = Lock()
        self._stats = {
            'total_requests': 0,
            'rate_limited': 0,
            'by_endpoint': defaultdict(lambda: {'allowed': 0, 'blocked': 0})
        }
    
    def _get_key(self, ip: str, path: str) -> str:
        """Generate bucket key from IP and path pattern"""
        # Normalize path to pattern
        default_limits = RateLimitConfig.get_default_limits()
        for pattern in default_limits.keys():
            if pattern != '_default' and path.startswith(pattern):
                return f"{ip}:{pattern}"
        return f"{ip}:_default"
    
    def check_rate_limit(self, ip: str, path: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if request should be rate limited
        
        Args:
            ip: Client IP address
            path: Request path
            
        Returns:
            (allowed: bool, info: dict with remaining, reset_time, etc.)
        """
        if not RateLimitConfig.is_enabled():
            return True, {'enabled': False}
        
        if RateLimitConfig.is_whitelisted(ip):
            return True, {'whitelisted': True}
        
        limit = RateLimitConfig.get_limit(path)
        rpm = limit['rpm']
        burst = limit['burst']
        
        key = self._get_key(ip, path)
        now = time.time()
        window = 60.0  # 1 minute window
        
        with self._lock:
            self._stats['total_requests'] += 1
            
            if key not in self._buckets:
                self._buckets[key] = {
                    'tokens': burst,
                    'last_update': now,
                    'requests': []
                }
            
            bucket = self._buckets[key]
            
            # Clean old requests outside window
            bucket['requests'] = [t for t in bucket['requests'] if now - t < window]
            
            # Replenish tokens based on time elapsed
            elapsed = now - bucket['last_update']
            tokens_to_add = (elapsed / window) * rpm
            bucket['tokens'] = min(burst, bucket['tokens'] + tokens_to_add)
            bucket['last_update'] = now
            
            # Check if we have tokens
            requests_in_window = len(bucket['requests'])
            
            if bucket['tokens'] >= 1 and requests_in_window < rpm:
                bucket['tokens'] -= 1
                bucket['requests'].append(now)
                self._stats['by_endpoint'][path]['allowed'] += 1
                
                return True, {
                    'allowed': True,
                    'remaining': int(bucket['tokens']),
                    'limit': rpm,
                    'reset': int(now + window - (bucket['requests'][0] if bucket['requests'] else now))
                }
            else:
                self._stats['rate_limited'] += 1
                self._stats['by_endpoint'][path]['blocked'] += 1
                
                # Calculate retry-after
                if bucket['requests']:
                    oldest = bucket['requests'][0]
                    retry_after = int(window - (now - oldest)) + 1
                else:
                    retry_after = int(window)
                
                return False, {
                    'allowed': False,
                    'remaining': 0,
                    'limit': rpm,
                    'retry_after': retry_after,
                    'message': f'Rate limit exceeded. Try again in {retry_after}s'
                }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rate limiting statistics"""
        with self._lock:
            return {
                'total_requests': self._stats['total_requests'],
                'rate_limited': self._stats['rate_limited'],
                'rate_limited_percent': round(
                    (self._stats['rate_limited'] / self._stats['total_requests'] * 100)
                    if self._stats['total_requests'] > 0 else 0, 2
                ),
                'by_endpoint': dict(self._stats['by_endpoint'])
            }
    
    def reset_stats(self):
        """Reset statistics"""
        with self._lock:
            self._stats = {
                'total_requests': 0,
                'rate_limited': 0,
                'by_endpoint': defaultdict(lambda: {'allowed': 0, 'blocked': 0})
            }
    
    def clear_bucket(self, ip: str = None):
        """Clear rate limit buckets"""
        with self._lock:
            if ip:
                keys_to_remove = [k for k in self._buckets.keys() if k.startswith(f"{ip}:")]
                for key in keys_to_remove:
                    del self._buckets[key]
            else:
                self._buckets.clear()


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def init_rate_limiter(app=None) -> RateLimiter:
    """Initialize rate limiter and optionally register middleware"""
    global _rate_limiter
    _rate_limiter = RateLimiter()
    
    if app:
        @app.before_request
        def rate_limit_middleware():
            # Skip for certain paths
            if request.path.startswith('/static') or request.path == '/health':
                return None
            
            ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if ip and ',' in ip:
                ip = ip.split(',')[0].strip()
            
            allowed, info = _rate_limiter.check_rate_limit(ip, request.path)
            
            if not allowed:
                from services.audit_service import AuditService
                AuditService.log_action(
                    action='rate_limited',
                    resource_type='api',
                    details=f"Rate limited: {request.path}",
                    success=False
                )
                
                response = jsonify({
                    'success': False,
                    'error': 'Rate limit exceeded',
                    'retry_after': info.get('retry_after', 60)
                })
                response.status_code = 429
                response.headers['Retry-After'] = str(info.get('retry_after', 60))
                response.headers['X-RateLimit-Limit'] = str(info.get('limit', 0))
                response.headers['X-RateLimit-Remaining'] = '0'
                return response
            
            # Add rate limit headers to response
            g.rate_limit_info = info
        
        @app.after_request
        def add_rate_limit_headers(response):
            if hasattr(g, 'rate_limit_info') and g.rate_limit_info.get('allowed'):
                info = g.rate_limit_info
                response.headers['X-RateLimit-Limit'] = str(info.get('limit', 0))
                response.headers['X-RateLimit-Remaining'] = str(info.get('remaining', 0))
                if 'reset' in info:
                    response.headers['X-RateLimit-Reset'] = str(info['reset'])
            return response
        
        logger.info("Rate limiter middleware registered")
    
    return _rate_limiter


def rate_limit(rpm: int = None, burst: int = None):
    """
    Decorator for custom rate limiting on specific endpoints
    
    Usage:
        @rate_limit(rpm=10, burst=3)
        def login():
            ...
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            limiter = get_rate_limiter()
            
            ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if ip and ',' in ip:
                ip = ip.split(',')[0].strip()
            
            # Use custom or default limits
            path = request.path
            if rpm is not None:
                RateLimitConfig.set_custom_limit(path, rpm, burst or rpm // 3)
            
            allowed, info = limiter.check_rate_limit(ip, path)
            
            if not allowed:
                return jsonify({
                    'success': False,
                    'error': 'Rate limit exceeded',
                    'retry_after': info.get('retry_after', 60)
                }), 429
            
            return f(*args, **kwargs)
        return wrapper
    return decorator
