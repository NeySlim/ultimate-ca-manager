"""
PKI Reset Service - Reset PKI data while keeping users intact
Ultimate CA Manager v1.7.0
"""
import os
import shutil
from pathlib import Path
from datetime import datetime
from models import db
from config.settings import DATA_DIR
import logging

logger = logging.getLogger(__name__)


class PKIResetService:
    """Service to reset PKI data (CAs, certificates, CRLs) while preserving users"""
    
    @staticmethod
    def create_backup() -> str:
        """
        Create backup of current PKI data before reset
        
        Returns:
            str: Path to backup directory
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(DATA_DIR, f'pki_backup_{timestamp}')
        
        os.makedirs(backup_dir, exist_ok=True)
        
        # Backup CA data directories
        for subdir in ['cas', 'certs', 'private', 'ca', 'crl', 'scep']:
            src_dir = os.path.join(DATA_DIR, subdir)
            if os.path.exists(src_dir):
                dst_dir = os.path.join(backup_dir, subdir)
                if os.path.isdir(src_dir):
                    shutil.copytree(src_dir, dst_dir)
                    logger.info(f"Backed up {subdir}/ to {dst_dir}")
        
        # Backup database (just copy the file)
        db_path = os.path.join(DATA_DIR, 'ucm.db')
        if os.path.exists(db_path):
            shutil.copy2(db_path, os.path.join(backup_dir, 'ucm.db'))
            logger.info(f"Backed up database to {backup_dir}/ucm.db")
        
        return backup_dir
    
    @staticmethod
    def reset_pki_data():
        """
        Reset all PKI data:
        - Delete all CAs and certificates from filesystem
        - Delete PKI tables from database
        - Keep users, sessions, and auth data intact
        
        Returns:
            dict: Summary of reset operation
        """
        try:
            stats = {
                'cas_deleted': 0,
                'certificates_deleted': 0,
                'crls_deleted': 0,
                'ocsp_records_deleted': 0,
                'backup_path': None
            }
            
            # 1. Create backup first
            backup_path = PKIResetService.create_backup()
            stats['backup_path'] = backup_path
            logger.info(f"Backup created at: {backup_path}")
            
            # 2. Delete CA directories and certificate files from filesystem
            cas_dir = os.path.join(DATA_DIR, 'cas')
            if os.path.exists(cas_dir):
                ca_count = len([d for d in os.listdir(cas_dir) 
                               if os.path.isdir(os.path.join(cas_dir, d))])
                shutil.rmtree(cas_dir)
                os.makedirs(cas_dir, exist_ok=True)
                stats['cas_deleted'] = ca_count
                logger.info(f"Deleted {ca_count} CA directories")
            
            # Delete certificate files (certs/, private/, ca/, crl/, scep/)
            for subdir in ['certs', 'private', 'ca', 'crl', 'scep']:
                dir_path = os.path.join(DATA_DIR, subdir)
                if os.path.exists(dir_path):
                    # Count files
                    file_count = len([f for f in os.listdir(dir_path) 
                                     if os.path.isfile(os.path.join(dir_path, f))])
                    # Delete all files but keep directory
                    for filename in os.listdir(dir_path):
                        file_path = os.path.join(dir_path, filename)
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                    logger.info(f"Deleted {file_count} files from {subdir}/")

            
            # 3. Delete PKI tables from database
            # Note: We preserve users, sessions, system_config, auth tables
            # (db is already imported at module level)
            
            # Tables to reset (PKI-related only)
            pki_tables = [
                'certificates',
                'certificate_authorities', 
                'trust_stores',
                'crl_metadata',
                'crls',
                'ocsp_responses',
                'scep_requests',
            ]
            
            for table_name in pki_tables:
                try:
                    # SQLite: DELETE FROM table
                    result = db.session.execute(db.text(f"DELETE FROM {table_name}"))
                    deleted = result.rowcount
                    
                    if table_name == 'certificates':
                        stats['certificates_deleted'] = deleted
                    elif table_name == 'certificate_authorities':
                        stats['cas_deleted'] += deleted
                    elif table_name in ['crl_metadata', 'crls']:
                        stats['crls_deleted'] = stats.get('crls_deleted', 0) + deleted
                    elif table_name == 'ocsp_responses':
                        stats['ocsp_records_deleted'] = deleted
                    
                    logger.info(f"Deleted {deleted} rows from {table_name}")
                except Exception as e:
                    # Table might not exist, skip
                    logger.warning(f"Could not delete from {table_name}: {e}")
            
            # 4. Reset auto-increment sequences (SQLite)
            for table_name in pki_tables:
                try:
                    db.session.execute(db.text(
                        f"DELETE FROM sqlite_sequence WHERE name='{table_name}'"
                    ))
                except Exception as e:
                    logger.warning(f"Could not reset sequence for {table_name}: {e}")
            
            # 5. Commit all changes
            db.session.commit()
            
            logger.info(f"PKI reset completed: {stats}")
            return stats
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"PKI reset failed: {e}")
            raise
    
    @staticmethod
    def get_pki_stats() -> dict:
        """
        Get current PKI statistics
        
        Returns:
            dict: PKI data counts
        """
        # (db is already imported at module level)
        
        stats = {}
        
        # Count PKI records
        pki_counts = {
            'certificate_authorities': 'CAs',
            'certificates': 'Certificates',
            'crl_metadata': 'CRLs',
            'ocsp_responses': 'OCSP Responses',
            'scep_requests': 'SCEP Requests',
        }
        
        for table_name, label in pki_counts.items():
            try:
                result = db.session.execute(
                    db.text(f"SELECT COUNT(*) FROM {table_name}")
                )
                count = result.scalar()
                stats[label.lower().replace(' ', '_')] = count
            except Exception:
                stats[label.lower().replace(' ', '_')] = 0
        
        # Check filesystem
        cas_dir = os.path.join(DATA_DIR, 'cas')
        if os.path.exists(cas_dir):
            stats['ca_directories'] = len([
                d for d in os.listdir(cas_dir)
                if os.path.isdir(os.path.join(cas_dir, d))
            ])
        else:
            stats['ca_directories'] = 0
        
        return stats
