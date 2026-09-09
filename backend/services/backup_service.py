"""
Backup Service for UCM - Wrapper for backward compatibility
The actual implementation is in services.backup package
"""
from services.backup import BackupService, BackupPasswordError

__all__ = ['BackupService', 'BackupPasswordError']
