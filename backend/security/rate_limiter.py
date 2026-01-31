"""
Rate Limiting Module
Per-endpoint rate limiting with configurable limits
"""
import time
import logging
from collections import defaultdict
from threading import Lock
from typing import Dict, Any, Optional, Tuple
from functools import wraps
from flask import request, jsonify, g

logger = logging.getLogger(__name__)


class RateLimitConfig:
    """Rate limit configuration per endpoint pattern"""
    
    # Default limits (requests per minute)
    DEFAULT_LIMITS = {
        # Authentication - strict limits
        '/api/v2/auth/login': {'rpm': 10, 'burst': 3},
        '/api/v2/auth/register': {'rpm': 5, 'burst': 2},
        '/api/v2/auth/reset-password': {'rpm': 5, 'burst': 2},
        
        # Heavy operations - moderate limits
        '/api/v2/certificates/issue': {'rpm': 30, 'burst': 5},
        '/api/v2/cas': {'rpm': 30, 'burst': 5},
        '/api/v2/csrs/sign': {'rpm': 20, 'burst': 5},
        '/api/v2/import': {'rpm': 10, 'burst': 2},
        '/api/v2/export': {'rpm': 10, 'burst': 2},
        '/api/v2/backup': {'rpm': 5, 'burst': 2},
        
        # Standard endpoints - reasonable limits
        '/api/v2/users': {'rpm': 60, 'burst': 10},
        '/api/v2/certificates': {'rpm': 120, 'burst': 20},
        '/api/v2/audit': {'rpm': 60, 'burst': 10},
        
        # Protocol endpoints - higher limits
        '/acme/': {'rpm': 300, 'burst': 50},
        '/scep/': {'rpm': 300, 'burst': 50},
        '/ocsp': {'rpm': 500, 'burst': 100},
        '/cdp/': {'rpm': 500, 'burst': 100},
        
        # Default for unspecified endpoints
        '_default': {'rpm': 120, 'burst': 20}
    }
    
    # Global settings
    _enabled: bool = True
    _custom_limits: Dict[str, Dict] = {}
    _whitelist: set = set()  # IPs that bypass rate limiting
    
    @classmethod
    def is_enabled(cls) -> bool:
        return cls._enabled
    
    @classmethod
    def set_enabled(cls, enabled: bool):
        cls._enabled = enabled
        logger.info(f"Rate limiting {'enabled' if enabled else 'disabled'}")
    
    @classmethod
    def get_limit(cls, path: str) -> Dict[str, int]:
        """Get rate limit for a path"""
        # Check custom limits first
        for pattern, limit in cls._custom_limits.items():
            if path.startswith(pattern):
                return limit
        
        # Check default limits
        for pattern, limit in cls.DEFAULT_LIMITS.items():
            if pattern != '_default' and path.startswith(pattern):
                return limit
        
        return cls.DEFAULT_LIMITS['_default']
    
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
        return ip in cls._whitelist
    
    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """Get full configuration"""
        return {
            'enabled': cls._enabled,
            'default_limits': cls.DEFAULT_LIMITS,
            'custom_limits': cls._custom_limits,
            'whitelist': list(cls._whitelist)
        }


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
        for pattern in RateLimitConfig.DEFAULT_LIMITS.keys():
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
