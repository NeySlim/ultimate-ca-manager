"""
Structured Logging - UCM Backend
JSON-formatted logs for observability
"""

import logging
import json
from datetime import datetime
from flask import request, g, has_request_context

class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Add request context if available
        if has_request_context():
            log_data['request'] = {
                'method': request.method,
                'path': request.path,
                'ip': request.remote_addr,
                'user_agent': request.headers.get('User-Agent', '')[:100]
            }
            # Add user if authenticated
            if hasattr(g, 'current_user') and g.current_user:
                log_data['user'] = {
                    'id': g.current_user.id,
                    'username': g.current_user.username
                }
        
        # Add extra fields
        if hasattr(record, 'extra_data'):
            log_data['data'] = record.extra_data
        
        # Add exception info
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


class StructuredLogger:
    """Wrapper for structured logging with extra data support"""
    
    def __init__(self, name='ucm'):
        self.logger = logging.getLogger(name)
    
    def _log(self, level, message, **kwargs):
        extra = {'extra_data': kwargs} if kwargs else {}
        getattr(self.logger, level)(message, extra=extra)
    
    def info(self, message, **kwargs):
        self._log('info', message, **kwargs)
    
    def warning(self, message, **kwargs):
        self._log('warning', message, **kwargs)
    
    def error(self, message, **kwargs):
        self._log('error', message, **kwargs)
    
    def debug(self, message, **kwargs):
        self._log('debug', message, **kwargs)
    
    # Audit logging shortcuts
    def audit(self, action, **kwargs):
        """Log an auditable action"""
        self._log('info', f"AUDIT: {action}", action=action, **kwargs)


def setup_structured_logging(app, json_output=True):
    """Configure structured logging for the Flask app"""
    
    # Get or create UCM logger
    logger = logging.getLogger('ucm')
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    logger.handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    
    if json_output:
        console_handler.setFormatter(StructuredFormatter())
    else:
        # Human-readable format for development
        console_handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(levelname)s %(name)s: %(message)s'
        ))
    
    logger.addHandler(console_handler)
    
    # Also configure Flask's logger
    app.logger.handlers = []
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.INFO)
    
    return StructuredLogger('ucm')


# Global logger instance
logger = StructuredLogger('ucm')
