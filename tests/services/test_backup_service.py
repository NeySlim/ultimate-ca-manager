"""
Tests for Backup Service
"""
import pytest
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend'))


class TestBackupService:
    """Test BackupService"""

    def test_password_validation_too_short(self, app):
        """Password must be at least 12 characters"""
        with app.app_context():
            from services.backup_service import BackupService
            
            service = BackupService()
            
            with pytest.raises(ValueError, match="at least 12 characters"):
                service.create_backup("short")

    def test_password_validation_low_entropy(self, app):
        """Password must have sufficient entropy"""
        with app.app_context():
            from services.backup_service import BackupService
            
            service = BackupService()
            
            with pytest.raises(ValueError, match="too simple"):
                service.create_backup("aaaaaaaaaaaa")  # 12 chars but only 1 unique

    def test_create_backup_success(self, app):
        """create_backup returns encrypted bytes"""
        with app.app_context():
            from services.backup_service import BackupService
            
            service = BackupService()
            password = "MySecureP@ssw0rd123"
            
            backup_bytes = service.create_backup(password)
            
            assert isinstance(backup_bytes, bytes)
            assert len(backup_bytes) > 0

    def test_restore_backup_wrong_password(self, app):
        """restore_backup fails with wrong password"""
        with app.app_context():
            from services.backup_service import BackupService
            
            service = BackupService()
            password = "MySecureP@ssw0rd123"
            wrong_password = "WrongPassword123!"
            
            backup_bytes = service.create_backup(password)
            
            with pytest.raises(ValueError, match="wrong password"):
                service.restore_backup(backup_bytes, wrong_password)

    def test_backup_restore_roundtrip(self, app):
        """Backup can be restored with correct password"""
        with app.app_context():
            from services.backup_service import BackupService
            
            service = BackupService()
            password = "MySecureP@ssw0rd123"
            
            # Create backup
            backup_bytes = service.create_backup(password)
            
            # Restore backup
            result = service.restore_backup(backup_bytes, password)
            
            assert isinstance(result, dict)
            assert 'users' in result
            assert 'cas' in result
            assert 'certificates' in result

    def test_backup_includes_metadata(self, app):
        """Backup contains metadata"""
        with app.app_context():
            from services.backup_service import BackupService
            
            service = BackupService()
            
            # Access internal method
            metadata = service._get_metadata('full')
            
            assert 'version' in metadata
            assert 'created_at' in metadata
            assert 'backup_type' in metadata
            assert metadata['backup_type'] == 'full'

    def test_backup_corrupted_data(self, app):
        """restore_backup fails with corrupted data"""
        with app.app_context():
            from services.backup_service import BackupService
            
            service = BackupService()
            
            # Corrupt data
            corrupted = b'corrupted data that is not valid'
            
            with pytest.raises(ValueError):
                service.restore_backup(corrupted, "AnyPassword123!")
