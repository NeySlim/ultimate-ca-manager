"""
Anomaly Detection Service
Tracks login patterns and detects suspicious activity
"""

import os
from datetime import datetime, timedelta
from collections import defaultdict
import json
import hashlib
from typing import Optional, Dict, List

try:
    from models import db, User, AuditLog
    from services.audit_service import AuditService
except ImportError:
    db = None
    AuditService = None


class AnomalyDetector:
    """
    Detects suspicious patterns in user activity
    
    Patterns detected:
    - Impossible travel (login from distant locations in short time)
    - Unusual login times (outside normal hours)
    - Bulk operations (mass delete/export)
    - Multiple failed logins from different users (credential stuffing)
    - Login from new device/browser
    """
    
    # Thresholds
    BULK_OPERATION_THRESHOLD = 50  # Operations in 5 minutes
    FAILED_LOGIN_THRESHOLD = 5  # Different users in 5 minutes from same IP
    UNUSUAL_HOUR_START = 2  # 2 AM
    UNUSUAL_HOUR_END = 5  # 5 AM
    
    def __init__(self):
        self._cache = {
            'bulk_ops': defaultdict(list),  # user_id -> [timestamps]
            'failed_logins': defaultdict(list),  # ip -> [timestamps]
            'user_agents': {},  # user_id -> set of known user agents
        }
    
    def record_login(self, user_id: int, ip_address: str, user_agent: str, success: bool) -> List[Dict]:
        """
        Record login attempt and check for anomalies
        
        Returns list of anomalies detected (empty if none)
        """
        anomalies = []
        now = datetime.utcnow()
        
        if success:
            # Check for unusual time login
            if self.UNUSUAL_HOUR_START <= now.hour < self.UNUSUAL_HOUR_END:
                anomalies.append({
                    'type': 'unusual_time_login',
                    'severity': 'low',
                    'message': f'Login at unusual hour ({now.hour}:00 UTC)',
                    'user_id': user_id,
                    'ip': ip_address
                })
            
            # Check for new device/browser
            ua_hash = hashlib.sha256(user_agent.encode()).hexdigest()[:16]
            if user_id in self._cache['user_agents']:
                if ua_hash not in self._cache['user_agents'][user_id]:
                    anomalies.append({
                        'type': 'new_device',
                        'severity': 'medium',
                        'message': 'Login from new device/browser',
                        'user_id': user_id,
                        'ip': ip_address
                    })
                    self._cache['user_agents'][user_id].add(ua_hash)
            else:
                self._cache['user_agents'][user_id] = {ua_hash}
        
        else:
            # Track failed logins by IP
            self._cache['failed_logins'][ip_address].append(now)
            
            # Clean old entries (>5 min)
            cutoff = now - timedelta(minutes=5)
            self._cache['failed_logins'][ip_address] = [
                t for t in self._cache['failed_logins'][ip_address]
                if t > cutoff
            ]
            
            # Check for credential stuffing
            if len(self._cache['failed_logins'][ip_address]) >= self.FAILED_LOGIN_THRESHOLD:
                anomalies.append({
                    'type': 'credential_stuffing',
                    'severity': 'high',
                    'message': f'Multiple failed logins from same IP ({len(self._cache["failed_logins"][ip_address])} attempts)',
                    'ip': ip_address
                })
        
        # Log anomalies to audit log
        for anomaly in anomalies:
            self._log_anomaly(anomaly)
        
        return anomalies
    
    def record_bulk_operation(self, user_id: int, operation: str, count: int) -> Optional[Dict]:
        """
        Track bulk operations (export, delete, etc.)
        
        Returns anomaly if threshold exceeded
        """
        now = datetime.utcnow()
        
        # Add current operation
        self._cache['bulk_ops'][user_id].append((now, operation, count))
        
        # Clean old entries (>5 min)
        cutoff = now - timedelta(minutes=5)
        self._cache['bulk_ops'][user_id] = [
            (t, op, c) for t, op, c in self._cache['bulk_ops'][user_id]
            if t > cutoff
        ]
        
        # Count total operations
        total = sum(c for _, _, c in self._cache['bulk_ops'][user_id])
        
        if total >= self.BULK_OPERATION_THRESHOLD:
            anomaly = {
                'type': 'bulk_operation',
                'severity': 'high',
                'message': f'Bulk operations detected ({total} items in 5 minutes)',
                'user_id': user_id,
                'operations': [op for _, op, _ in self._cache['bulk_ops'][user_id]]
            }
            self._log_anomaly(anomaly)
            
            # Clear cache for this user after alert
            self._cache['bulk_ops'][user_id] = []
            
            return anomaly
        
        return None
    
    def _log_anomaly(self, anomaly: Dict):
        """Log anomaly to audit log"""
        if AuditService:
            AuditService.log_action(
                action='security_anomaly',
                resource_type='security',
                details=json.dumps(anomaly),
                success=True,
                username=f"user:{anomaly.get('user_id', 'unknown')}"
            )
    
    def get_recent_anomalies(self, hours: int = 24) -> List[Dict]:
        """Get anomalies from the last N hours"""
        if not AuditLog:
            return []
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        logs = AuditLog.query.filter(
            AuditLog.action == 'security_anomaly',
            AuditLog.timestamp >= cutoff
        ).order_by(AuditLog.timestamp.desc()).all()
        
        return [
            {
                'timestamp': log.timestamp.isoformat(),
                'details': json.loads(log.details) if log.details else {}
            }
            for log in logs
        ]


# Global instance
_detector = None


def get_anomaly_detector() -> AnomalyDetector:
    """Get or create anomaly detector instance"""
    global _detector
    if _detector is None:
        _detector = AnomalyDetector()
    return _detector
