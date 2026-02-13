"""
Database Management Service
Provides database maintenance, optimization, and health monitoring
"""
import os
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from models import db, Certificate, CA, CRL, OCSPResponse
from sqlalchemy import text, inspect
import gzip
import shutil

logger = logging.getLogger(__name__)


class DatabaseManagementService:
    """Service for database maintenance and optimization"""
    
    def __init__(self, db_path=None):
        """Initialize with database path"""
        if db_path is None:
            # Get from Flask app config
            from flask import current_app
            db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
            # Extract path from sqlite:///path/to/db.db
            if db_uri.startswith('sqlite:///'):
                self.db_path = db_uri.replace('sqlite:///', '')
            else:
                self.db_path = '/opt/ucm/data/ucm.db'
        else:
            self.db_path = db_path
    
    def get_database_stats(self):
        """
        Get comprehensive database statistics
        Returns dict with size, counts, health metrics
        """
        stats = {
            'size_mb': 0,
            'size_formatted': '0 MB',
            'page_count': 0,
            'page_size': 0,
            'fragmentation_pct': 0,
            'last_vacuum': None,
            'last_analyze': None,
            'tables': {},
            'connections': 0,
            'cache_size': 0,
            'integrity_check': 'unknown',
            'last_integrity_check': None,
            'disk_usage': {}
        }
        
        try:
            # File size
            if os.path.exists(self.db_path):
                size_bytes = os.path.getsize(self.db_path)
                stats['size_mb'] = round(size_bytes / (1024 * 1024), 2)
                stats['size_formatted'] = self._format_size(size_bytes)
            
            # SQLite internal stats
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Page count and size
            cursor.execute("PRAGMA page_count")
            stats['page_count'] = cursor.fetchone()[0]
            
            cursor.execute("PRAGMA page_size")
            stats['page_size'] = cursor.fetchone()[0]
            
            # Freelist (fragmentation indicator)
            cursor.execute("PRAGMA freelist_count")
            freelist = cursor.fetchone()[0]
            if stats['page_count'] > 0:
                stats['fragmentation_pct'] = round((freelist / stats['page_count']) * 100, 2)
            
            # Cache size
            cursor.execute("PRAGMA cache_size")
            stats['cache_size'] = cursor.fetchone()[0]
            
            # Table stats - SECURITY: Use whitelist to prevent SQL injection
            ALLOWED_TABLES = {
                'users', 'certificate_authorities', 'certificates', 'certificate_signing_requests',
                'certificate_templates', 'crl_metadata', 'ocsp_responses', 'truststore_entries',
                'audit_logs', 'settings', 'api_keys', 'webauthn_credentials', 'webauthn_challenges',
                'acme_accounts', 'acme_orders', 'acme_authorizations', 'acme_challenges',
                'acme_certificates', 'acme_providers', 'scep_requests', 'email_notifications',
                'pro_sso_providers', 'pro_sso_sessions', 'pro_groups', 'pro_group_members',
                'pro_rbac_roles', 'pro_rbac_permissions', 'pro_hsm_providers', 'pro_hsm_keys'
            }
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                if table in ALLOWED_TABLES:
                    try:
                        cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                        count = cursor.fetchone()[0]
                        stats['tables'][table] = count
                    except Exception as e:
                        logger.warning(f"Could not count table {table}: {e}")
                        stats['tables'][table] = 0
                else:
                    # Skip unknown tables but log them
                    logger.debug(f"Skipping unknown table: {table}")
                    stats['tables'][table] = 0
            
            conn.close()
            
            # Disk usage
            stats['disk_usage'] = self._get_disk_usage()
            
            # Check for maintenance metadata
            stats['last_vacuum'] = self._get_maintenance_timestamp('vacuum')
            stats['last_analyze'] = self._get_maintenance_timestamp('analyze')
            stats['last_integrity_check'] = self._get_maintenance_timestamp('integrity_check')
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return stats
    
    def vacuum_database(self):
        """
        Run VACUUM to reclaim space and defragment
        Returns dict with status and stats
        """
        try:
            size_before = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            
            # VACUUM cannot run in transaction
            conn = sqlite3.connect(self.db_path)
            conn.isolation_level = None  # Autocommit mode
            cursor = conn.cursor()
            
            logger.info("Starting database VACUUM...")
            cursor.execute("VACUUM")
            
            conn.close()
            
            size_after = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            space_saved = size_before - size_after
            
            # Save timestamp
            self._set_maintenance_timestamp('vacuum')
            
            logger.info(f"✓ Database VACUUM completed. Space saved: {self._format_size(space_saved)}")
            
            return {
                'success': True,
                'size_before_mb': round(size_before / (1024 * 1024), 2),
                'size_after_mb': round(size_after / (1024 * 1024), 2),
                'space_saved_mb': round(space_saved / (1024 * 1024), 2),
                'space_saved_formatted': self._format_size(space_saved),
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error during VACUUM: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def analyze_database(self):
        """
        Run ANALYZE to update query planner statistics
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            logger.info("Starting database ANALYZE...")
            cursor.execute("ANALYZE")
            conn.commit()
            conn.close()
            
            # Save timestamp
            self._set_maintenance_timestamp('analyze')
            
            logger.info("✓ Database ANALYZE completed")
            
            return {
                'success': True,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error during ANALYZE: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def optimize_database(self):
        """
        Run full optimization: VACUUM + ANALYZE
        """
        results = {
            'vacuum': self.vacuum_database(),
            'analyze': self.analyze_database()
        }
        
        return {
            'success': results['vacuum']['success'] and results['analyze']['success'],
            'vacuum': results['vacuum'],
            'analyze': results['analyze']
        }
    
    def check_integrity(self):
        """
        Run integrity check on database
        Returns health status and any errors
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            logger.info("Running integrity check...")
            cursor.execute("PRAGMA integrity_check")
            results = cursor.fetchall()
            
            conn.close()
            
            # Save timestamp
            self._set_maintenance_timestamp('integrity_check')
            
            # Check results
            is_ok = len(results) == 1 and results[0][0] == 'ok'
            
            status = {
                'success': True,
                'healthy': is_ok,
                'status': 'healthy' if is_ok else 'corrupted',
                'errors': [] if is_ok else [row[0] for row in results],
                'timestamp': datetime.now().isoformat()
            }
            
            if is_ok:
                logger.info("✓ Database integrity check passed")
            else:
                logger.error(f"✗ Database integrity check failed: {status['errors']}")
            
            return status
            
        except Exception as e:
            logger.error(f"Error during integrity check: {e}")
            return {
                'success': False,
                'healthy': False,
                'status': 'error',
                'error': str(e)
            }
    
    def clean_expired_certificates(self, days_after_expiry=30):
        """
        Delete certificates expired more than X days ago
        Returns count of deleted certificates
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_after_expiry)
            
            # Find expired certs
            expired_certs = Certificate.query.filter(
                Certificate.not_after < cutoff_date,
                Certificate.revoked == False  # Don't delete revoked certs (needed for CRL)
            ).all()
            
            count = len(expired_certs)
            
            # Delete them
            for cert in expired_certs:
                db.session.delete(cert)
            
            db.session.commit()
            
            logger.info(f"✓ Deleted {count} expired certificates (>{days_after_expiry} days old)")
            
            return {
                'success': True,
                'deleted_count': count,
                'cutoff_date': cutoff_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error cleaning expired certificates: {e}")
            db.session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
    
    def export_sql_dump(self, output_path=None, compress=True):
        """
        Export database as SQL dump
        """
        try:
            if output_path is None:
                timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
                output_path = f"/tmp/ucm-dump-{timestamp}.sql"
            
            conn = sqlite3.connect(self.db_path)
            
            # Generate SQL dump
            with open(output_path, 'w') as f:
                for line in conn.iterdump():
                    f.write(f"{line}\n")
            
            conn.close()
            
            # Compress if requested
            if compress:
                compressed_path = f"{output_path}.gz"
                with open(output_path, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(output_path)
                output_path = compressed_path
            
            file_size = os.path.getsize(output_path)
            
            logger.info(f"✓ Database exported to {output_path} ({self._format_size(file_size)})")
            
            return {
                'success': True,
                'file_path': output_path,
                'file_size': file_size,
                'file_size_formatted': self._format_size(file_size),
                'compressed': compress
            }
            
        except Exception as e:
            logger.error(f"Error exporting database: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_health_status(self):
        """
        Get overall database health status
        """
        stats = self.get_database_stats()
        
        health = {
            'status': 'healthy',
            'issues': [],
            'warnings': [],
            'recommendations': []
        }
        
        # Check fragmentation
        if stats['fragmentation_pct'] > 20:
            health['warnings'].append(f"High fragmentation: {stats['fragmentation_pct']}%")
            health['recommendations'].append("Run VACUUM to defragment database")
        
        # Check size
        if stats['size_mb'] > 1000:  # > 1GB
            health['warnings'].append(f"Large database: {stats['size_formatted']}")
            health['recommendations'].append("Consider archiving old data")
        
        # Check last vacuum
        last_vacuum = stats.get('last_vacuum')
        if last_vacuum:
            days_since_vacuum = (datetime.now() - datetime.fromisoformat(last_vacuum)).days
            if days_since_vacuum > 30:
                health['warnings'].append(f"Last VACUUM was {days_since_vacuum} days ago")
                health['recommendations'].append("Run database optimization")
        else:
            health['warnings'].append("No VACUUM history found")
            health['recommendations'].append("Run database optimization")
        
        # Overall status
        if len(health['issues']) > 0:
            health['status'] = 'critical'
        elif len(health['warnings']) > 0:
            health['status'] = 'warning'
        
        return health
    
    # Helper methods
    
    def _format_size(self, bytes_size):
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} TB"
    
    def _get_disk_usage(self):
        """Get disk usage stats"""
        try:
            stat = os.statvfs(os.path.dirname(self.db_path))
            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bavail * stat.f_frsize
            used = total - free
            
            return {
                'total': total,
                'used': used,
                'free': free,
                'used_pct': round((used / total) * 100, 2),
                'total_formatted': self._format_size(total),
                'used_formatted': self._format_size(used),
                'free_formatted': self._format_size(free)
            }
        except Exception as e:
            logger.warning(f"Could not get disk usage: {e}")
            return {}
    
    def _get_maintenance_timestamp(self, operation):
        """Get timestamp of last maintenance operation"""
        try:
            from models import SystemConfig
            config = SystemConfig.query.filter_by(key=f'db.maintenance.{operation}').first()
            return config.value if config else None
        except:
            return None
    
    def _set_maintenance_timestamp(self, operation):
        """Save timestamp of maintenance operation"""
        try:
            from models import SystemConfig
            timestamp = datetime.now().isoformat()
            
            config = SystemConfig.query.filter_by(key=f'db.maintenance.{operation}').first()
            if config:
                config.value = timestamp
            else:
                config = SystemConfig(
                    key=f'db.maintenance.{operation}',
                    value=timestamp,
                    description=f'Last {operation} timestamp'
                )
                db.session.add(config)
            
            db.session.commit()
        except Exception as e:
            logger.warning(f"Could not save maintenance timestamp: {e}")
            db.session.rollback()
