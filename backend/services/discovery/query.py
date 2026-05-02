"""
Query mixin — discovered certificate and scan run retrieval helpers.
"""
import socket
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple

from models import db, DiscoveredCertificate, ScanRun

logger = logging.getLogger(__name__)


class QueryMixin:

    def bulk_resolve_dns(self) -> Dict:
        """Re-resolve reverse DNS for all discovered certificates."""
        certs = DiscoveredCertificate.query.filter(
            DiscoveredCertificate.status != 'error',
            DiscoveredCertificate.fingerprint_sha256.isnot(None),
        ).all()

        updated = 0
        for cert in certs:
            try:
                hostname, _, _ = socket.gethostbyaddr(cert.target)
                if hostname and hostname != cert.target:
                    if cert.dns_hostname != hostname:
                        cert.dns_hostname = hostname
                        updated += 1
            except (socket.herror, socket.gaierror, OSError):
                pass

        db.session.commit()
        return {'total': len(certs), 'updated': updated}

    def get_all(self, limit: int = 200, offset: int = 0,
                profile_id: int = None, status=None) -> Tuple[List[Dict], int]:
        """Return discovered certificates with pagination. Returns (items, total).
        status can be str or list[str] for multi-select.
        """
        query = DiscoveredCertificate.query
        if profile_id:
            query = query.filter_by(scan_profile_id=profile_id)
        if status:
            if isinstance(status, list):
                query = query.filter(DiscoveredCertificate.status.in_(status))
            else:
                query = query.filter_by(status=status)
        total = query.count()
        rows = query.order_by(DiscoveredCertificate.last_seen.desc()
                              ).offset(offset).limit(limit).all()
        return [r.to_dict() for r in rows], total

    def get_stats(self, profile_id: int = None) -> Dict:
        """Return summary statistics."""
        base = DiscoveredCertificate.query
        if profile_id:
            base = base.filter_by(scan_profile_id=profile_id)
        total = base.filter(DiscoveredCertificate.status != 'error').count()
        managed = base.filter_by(status='managed').count()
        unmanaged = base.filter_by(status='unmanaged').count()
        now = datetime.now(timezone.utc)
        expired = base.filter(
            DiscoveredCertificate.not_after < now,
            DiscoveredCertificate.status != 'error',
        ).count()
        expiring = base.filter(
            DiscoveredCertificate.not_after > now,
            DiscoveredCertificate.not_after <= now + timedelta(days=30),
            DiscoveredCertificate.status != 'error',
        ).count()
        errors = base.filter_by(status='error').count()
        return {
            'total': total, 'managed': managed, 'unmanaged': unmanaged,
            'expired': expired, 'expiring_soon': expiring, 'errors': errors,
        }

    def get_runs(self, limit: int = 50, offset: int = 0,
                 profile_id: int = None) -> Tuple[List[Dict], int]:
        """Return scan run history."""
        query = ScanRun.query
        if profile_id:
            query = query.filter_by(scan_profile_id=profile_id)
        total = query.count()
        rows = query.order_by(ScanRun.started_at.desc()
                              ).offset(offset).limit(limit).all()
        return [r.to_dict() for r in rows], total

    def get_run(self, run_id: int) -> Optional[Dict]:
        run = ScanRun.query.get(run_id)
        return run.to_dict() if run else None

    def delete(self, disc_id: int) -> bool:
        row = DiscoveredCertificate.query.get(disc_id)
        if not row:
            return False
        db.session.delete(row)
        db.session.commit()
        return True

    def delete_all(self, profile_id: int = None) -> int:
        query = DiscoveredCertificate.query
        if profile_id:
            query = query.filter_by(scan_profile_id=profile_id)
        count = query.delete()
        db.session.commit()
        return count
