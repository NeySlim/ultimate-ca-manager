"""
Discovery Service v2
Async TLS scanning, fingerprint-based matching, change detection, WebSocket progress.
"""
import socket
import ssl
import hashlib
import base64
import ipaddress
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from models import db, Certificate, ScanProfile, ScanRun, DiscoveredCertificate

logger = logging.getLogger(__name__)

# Module-level fingerprint cache
_fingerprint_cache = {}
_cache_built_at = None
_CACHE_TTL_SECONDS = 300  # 5 min


class DiscoveryService:
    """Certificate network discovery with async scanning and fingerprint matching."""

    def __init__(self, max_workers: int = 20, timeout: int = 5):
        self.max_workers = max_workers
        self.timeout = timeout

    # ------------------------------------------------------------------
    # TLS Probing
    # ------------------------------------------------------------------

    def probe_tls(self, host: str, port: int = 443) -> Dict:
        """Connect to host:port via TLS and return certificate info."""
        result = {'target': host, 'port': port}
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            with socket.create_connection((host, port), timeout=self.timeout) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as tls:
                    der = tls.getpeercert(binary_form=True)
                    if not der:
                        result['error'] = 'No certificate returned'
                        result['error_type'] = 'no_cert'
                        return result

                    cert = x509.load_der_x509_certificate(der)
                    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
                    fp = hashlib.sha256(der).hexdigest().upper()

                    result.update({
                        'subject': cert.subject.rfc4514_string(),
                        'issuer': cert.issuer.rfc4514_string(),
                        'serial_number': format(cert.serial_number, 'X'),
                        'not_before': cert.not_valid_before_utc.isoformat(),
                        'not_after': cert.not_valid_after_utc.isoformat(),
                        'fingerprint_sha256': fp,
                        'pem_certificate': pem,
                    })
        except ConnectionRefusedError:
            result['error'] = 'Connection refused'
            result['error_type'] = 'refused'
        except socket.timeout:
            result['error'] = 'Connection timed out'
            result['error_type'] = 'timeout'
        except socket.gaierror as e:
            result['error'] = f'DNS resolution failed: {e}'
            result['error_type'] = 'dns'
        except OSError as e:
            result['error'] = str(e)
            result['error_type'] = 'network'
        except Exception as e:
            logger.debug(f"TLS probe {host}:{port} failed: {e}")
            result['error'] = str(e)
            result['error_type'] = 'tls'
        return result

    # ------------------------------------------------------------------
    # Async Scanning
    # ------------------------------------------------------------------

    def start_scan(self, targets: List[str], ports: List[int] = None,
                   profile_id: int = None, triggered_by: str = 'manual',
                   triggered_by_user: str = None, app=None) -> int:
        """Start an async scan. Returns scan_run_id immediately."""
        if ports is None:
            ports = [443]

        # Build job list — auto-expand CIDR notation in targets
        jobs = []
        for raw in targets:
            raw = raw.strip()
            if not raw:
                continue
            # Detect CIDR notation (e.g. 192.168.1.0/24)
            if '/' in raw and ':' not in raw:
                try:
                    network = ipaddress.ip_network(raw, strict=False)
                    for ip in network.hosts():
                        for p in ports:
                            jobs.append((str(ip), p))
                    continue
                except ValueError:
                    pass  # Not a valid CIDR, fall through to normal parse

            host, custom_port = self._parse_target(raw)
            if not host:
                continue
            scan_ports = [custom_port] if custom_port else ports
            for p in scan_ports:
                jobs.append((host, p))

        # Create scan run record
        run = ScanRun(
            scan_profile_id=profile_id,
            total_targets=len(jobs),
            triggered_by=triggered_by,
            triggered_by_user=triggered_by_user,
        )
        db.session.add(run)
        db.session.commit()
        run_id = run.id

        # Launch background thread
        thread = threading.Thread(
            target=self._execute_scan,
            args=(run_id, jobs, profile_id, app),
            daemon=True,
        )
        thread.start()
        return run_id

    def start_subnet_scan(self, cidr: str, ports: List[int] = None,
                          profile_id: int = None, triggered_by: str = 'manual',
                          triggered_by_user: str = None, app=None) -> int:
        """Start async subnet scan. Returns scan_run_id."""
        network = ipaddress.ip_network(cidr, strict=False)
        targets = [str(ip) for ip in network.hosts()]
        return self.start_scan(targets, ports, profile_id, triggered_by,
                               triggered_by_user, app)

    def _execute_scan(self, run_id: int, jobs: List[Tuple[str, int]],
                      profile_id: int, app):
        """Background thread: scan all targets and save results."""
        try:
            if app:
                with app.app_context():
                    self._do_scan(run_id, jobs, profile_id)
            else:
                self._do_scan(run_id, jobs, profile_id)
        except Exception as e:
            logger.error(f"Scan run {run_id} failed: {e}", exc_info=True)
            try:
                if app:
                    with app.app_context():
                        self._fail_run(run_id, str(e))
                else:
                    self._fail_run(run_id, str(e))
            except Exception:
                pass

    def _do_scan(self, run_id: int, jobs: List[Tuple[str, int]], profile_id: int):
        """Core scanning logic running in background."""
        from websocket.emitters import (on_discovery_scan_started,
                                        on_discovery_scan_progress,
                                        on_discovery_scan_complete,
                                        on_discovery_new_cert,
                                        on_discovery_cert_changed)

        run = ScanRun.query.get(run_id)
        if not run:
            return

        profile_name = run.profile.name if run.profile else 'Ad-hoc scan'
        on_discovery_scan_started(run_id, profile_name, len(jobs))
        logger.info(f"Discovery scan {run_id} started: {len(jobs)} targets")

        # Build fingerprint index for matching
        fp_index = self._build_fingerprint_index()

        results = []
        scanned = 0
        found = 0
        errors_real = 0
        new_certs = 0
        changed_certs = 0
        now = datetime.now(timezone.utc)
        last_progress = time.time()

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(self.probe_tls, h, p): (h, p) for h, p in jobs}

            for future in as_completed(futures):
                r = future.result()
                results.append(r)
                scanned += 1

                # Emit progress every 10 targets or every 3 seconds
                if scanned % 10 == 0 or (time.time() - last_progress) > 3:
                    on_discovery_scan_progress(run_id, scanned, len(jobs), found)
                    last_progress = time.time()
                    # Update run record periodically
                    run.targets_scanned = scanned
                    db.session.commit()

                has_cert = 'fingerprint_sha256' in r
                has_error = 'error' in r
                is_refused = r.get('error_type') == 'refused'

                if has_cert:
                    found += 1
                elif has_error and not is_refused:
                    errors_real += 1

        # Save results to DB
        for r in results:
            is_refused = r.get('error_type') == 'refused'
            if 'error' in r and 'fingerprint_sha256' not in r:
                if is_refused:
                    # Skip connection refused — not interesting
                    continue
                # Real error — save for tracking
                self._save_error(r, profile_id, now)
                continue

            fp = r['fingerprint_sha256']
            ucm_id = fp_index.get(fp)
            status = 'managed' if ucm_id else 'unmanaged'

            existing = DiscoveredCertificate.query.filter_by(
                target=r['target'], port=r['port']
            ).first()

            if existing:
                # Change detection
                if existing.fingerprint_sha256 and existing.fingerprint_sha256 != fp:
                    changed_certs += 1
                    existing.previous_fingerprint = existing.fingerprint_sha256
                    existing.last_changed_at = now
                    on_discovery_cert_changed(
                        r['target'], r['port'],
                        existing.subject or '', r.get('subject', ''))

                existing.subject = r.get('subject')
                existing.issuer = r.get('issuer')
                existing.serial_number = r.get('serial_number')
                existing.not_before = _parse_iso(r.get('not_before'))
                existing.not_after = _parse_iso(r.get('not_after'))
                existing.fingerprint_sha256 = fp
                existing.pem_certificate = r.get('pem_certificate')
                existing.status = status
                existing.ucm_certificate_id = ucm_id
                existing.scan_profile_id = profile_id or existing.scan_profile_id
                existing.last_seen = now
                existing.scan_error = None
            else:
                new_certs += 1
                dc = DiscoveredCertificate(
                    scan_profile_id=profile_id,
                    target=r['target'], port=r['port'],
                    subject=r.get('subject'),
                    issuer=r.get('issuer'),
                    serial_number=r.get('serial_number'),
                    not_before=_parse_iso(r.get('not_before')),
                    not_after=_parse_iso(r.get('not_after')),
                    fingerprint_sha256=fp,
                    pem_certificate=r.get('pem_certificate'),
                    status=status,
                    ucm_certificate_id=ucm_id,
                    first_seen=now, last_seen=now,
                )
                db.session.add(dc)
                if status == 'unmanaged':
                    on_discovery_new_cert(r['target'], r['port'], r.get('subject', ''))

        # Finalize scan run
        run.completed_at = datetime.now(timezone.utc)
        run.status = 'completed'
        run.targets_scanned = scanned
        run.certs_found = found
        run.new_certs = new_certs
        run.changed_certs = changed_certs
        run.errors = errors_real
        db.session.commit()

        # Update profile last_scan_at + next_scan_at
        if profile_id:
            profile = ScanProfile.query.get(profile_id)
            if profile:
                profile.last_scan_at = now
                if profile.schedule_enabled:
                    profile.next_scan_at = now + timedelta(minutes=profile.schedule_interval_minutes)
                db.session.commit()

        summary = {
            'total_targets': len(jobs),
            'certs_found': found,
            'new_certs': new_certs,
            'changed_certs': changed_certs,
            'errors': errors_real,
        }
        on_discovery_scan_complete(run_id, summary)
        logger.info(f"Discovery scan {run_id} complete: {summary}")

        # Send email notifications if configured
        self._send_notifications(profile_id, summary, new_certs, changed_certs)

    def _save_error(self, r: Dict, profile_id: int, now: datetime):
        """Save a scan error (not connection_refused)."""
        existing = DiscoveredCertificate.query.filter_by(
            target=r['target'], port=r['port']
        ).first()
        if existing:
            existing.last_seen = now
            existing.scan_error = r.get('error')
            existing.status = 'error'
        else:
            dc = DiscoveredCertificate(
                scan_profile_id=profile_id,
                target=r['target'], port=r['port'],
                status='error', scan_error=r.get('error'),
                first_seen=now, last_seen=now,
            )
            db.session.add(dc)

    def _fail_run(self, run_id: int, error: str):
        """Mark a scan run as failed."""
        run = ScanRun.query.get(run_id)
        if run:
            run.status = 'failed'
            run.completed_at = datetime.now(timezone.utc)
            db.session.commit()

    # ------------------------------------------------------------------
    # Fingerprint matching — cache of UCM cert fingerprints
    # ------------------------------------------------------------------

    def _build_fingerprint_index(self) -> Dict[str, int]:
        """Build { sha256_hex: cert_id } from UCM certificate inventory."""
        global _fingerprint_cache, _cache_built_at

        now = time.time()
        if _cache_built_at and (now - _cache_built_at) < _CACHE_TTL_SECONDS:
            return _fingerprint_cache

        logger.debug("Building certificate fingerprint index...")
        index = {}
        certs = Certificate.query.filter(
            Certificate.crt.isnot(None)
        ).with_entities(Certificate.id, Certificate.crt).all()

        for cert_id, crt_b64 in certs:
            try:
                pem_data = base64.b64decode(crt_b64).decode('utf-8')
                cert_obj = x509.load_pem_x509_certificate(pem_data.encode())
                der = cert_obj.public_bytes(serialization.Encoding.DER)
                fp = hashlib.sha256(der).hexdigest().upper()
                index[fp] = cert_id
            except Exception:
                continue

        _fingerprint_cache = index
        _cache_built_at = now
        logger.debug(f"Fingerprint index built: {len(index)} certificates")
        return index

    @staticmethod
    def invalidate_fingerprint_cache():
        """Call when UCM certs change (issue, import, delete)."""
        global _cache_built_at
        _cache_built_at = None

    # ------------------------------------------------------------------
    # Email Notifications
    # ------------------------------------------------------------------

    def _send_notifications(self, profile_id: int, summary: Dict,
                            new_certs: int, changed_certs: int):
        """Send email digest if profile has notifications enabled."""
        if not profile_id:
            return
        profile = ScanProfile.query.get(profile_id)
        if not profile:
            return

        should_notify = (
            (profile.notify_on_new and new_certs > 0) or
            (profile.notify_on_change and changed_certs > 0)
        )
        if not should_notify:
            return

        try:
            from services.email_service import EmailService
            from models import SystemConfig

            # Get SMTP config
            smtp_row = SystemConfig.query.filter_by(key='smtp_config').first()
            if not smtp_row:
                return

            import json
            smtp_config = json.loads(smtp_row.value)
            recipients = smtp_config.get('notification_recipients', [])
            if not recipients and smtp_config.get('admin_email'):
                recipients = [smtp_config['admin_email']]
            if not recipients:
                return

            parts = []
            if new_certs > 0:
                parts.append(f"{new_certs} new unmanaged certificate(s)")
            if changed_certs > 0:
                parts.append(f"{changed_certs} certificate(s) changed")

            subject = f"[UCM] Discovery scan '{profile.name}': {', '.join(parts)}"
            body = (
                f"<h2>Discovery Scan Complete — {profile.name}</h2>"
                f"<p>Targets scanned: {summary['total_targets']}</p>"
                f"<p>Certificates found: {summary['certs_found']}</p>"
                f"<p>New unmanaged: <strong>{new_certs}</strong></p>"
                f"<p>Changed: <strong>{changed_certs}</strong></p>"
                f"<p>Errors: {summary['errors']}</p>"
            )

            EmailService.send_email(
                recipients=recipients,
                subject=subject,
                body_html=body,
                body_text=body.replace('<p>', '').replace('</p>', '\n')
                              .replace('<h2>', '').replace('</h2>', '\n')
                              .replace('<strong>', '').replace('</strong>', ''),
                notification_type='discovery_scan',
                resource_type='discovery',
            )
            logger.info(f"Discovery notification sent to {len(recipients)} recipients")
        except Exception as e:
            logger.warning(f"Failed to send discovery notification: {e}")

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_all(self, limit: int = 200, offset: int = 0,
                profile_id: int = None, status: str = None) -> Tuple[List[Dict], int]:
        """Return discovered certificates with pagination. Returns (items, total)."""
        query = DiscoveredCertificate.query.filter(
            DiscoveredCertificate.status != 'error'
        )
        if profile_id:
            query = query.filter_by(scan_profile_id=profile_id)
        if status:
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

    # ------------------------------------------------------------------
    # Scan Profiles CRUD
    # ------------------------------------------------------------------

    def get_profiles(self) -> List[Dict]:
        rows = ScanProfile.query.order_by(ScanProfile.name).all()
        return [r.to_dict() for r in rows]

    def get_profile(self, profile_id: int) -> Optional[Dict]:
        row = ScanProfile.query.get(profile_id)
        return row.to_dict() if row else None

    def create_profile(self, data: Dict) -> Dict:
        import json
        profile = ScanProfile(
            name=data['name'],
            description=data.get('description', ''),
            targets=json.dumps(data.get('targets', [])),
            ports=json.dumps(data.get('ports', [443])),
            schedule_enabled=data.get('schedule_enabled', False),
            schedule_interval_minutes=data.get('schedule_interval_minutes', 1440),
            notify_on_new=data.get('notify_on_new', True),
            notify_on_change=data.get('notify_on_change', True),
            notify_on_expiry=data.get('notify_on_expiry', True),
        )
        if profile.schedule_enabled:
            profile.next_scan_at = datetime.now(timezone.utc) + timedelta(
                minutes=profile.schedule_interval_minutes)
        db.session.add(profile)
        db.session.commit()
        return profile.to_dict()

    def update_profile(self, profile_id: int, data: Dict) -> Optional[Dict]:
        import json
        profile = ScanProfile.query.get(profile_id)
        if not profile:
            return None
        if 'name' in data:
            profile.name = data['name']
        if 'description' in data:
            profile.description = data['description']
        if 'targets' in data:
            profile.targets = json.dumps(data['targets'])
        if 'ports' in data:
            profile.ports = json.dumps(data['ports'])
        if 'schedule_enabled' in data:
            profile.schedule_enabled = data['schedule_enabled']
        if 'schedule_interval_minutes' in data:
            profile.schedule_interval_minutes = data['schedule_interval_minutes']
        if 'notify_on_new' in data:
            profile.notify_on_new = data['notify_on_new']
        if 'notify_on_change' in data:
            profile.notify_on_change = data['notify_on_change']
        if 'notify_on_expiry' in data:
            profile.notify_on_expiry = data['notify_on_expiry']
        profile.updated_at = datetime.now(timezone.utc)
        if profile.schedule_enabled and not profile.next_scan_at:
            profile.next_scan_at = datetime.now(timezone.utc) + timedelta(
                minutes=profile.schedule_interval_minutes)
        db.session.commit()
        return profile.to_dict()

    def delete_profile(self, profile_id: int) -> bool:
        profile = ScanProfile.query.get(profile_id)
        if not profile:
            return False
        db.session.delete(profile)
        db.session.commit()
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_target(raw: str) -> Tuple[str, Optional[int]]:
        """Parse 'host' or 'host:port' string."""
        raw = raw.strip()
        if not raw:
            return ('', None)
        if raw.startswith('['):
            if ']:' in raw:
                host, port_s = raw.rsplit(':', 1)
                return (host.strip('[]'), int(port_s))
            return (raw.strip('[]'), None)
        if ':' in raw:
            parts = raw.rsplit(':', 1)
            try:
                return (parts[0], int(parts[1]))
            except ValueError:
                return (raw, None)
        return (raw, None)


def _parse_iso(val) -> Optional[datetime]:
    """Parse ISO datetime string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None
