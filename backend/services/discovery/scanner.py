"""
Scanner mixin — async scan orchestration and core scan logic.
"""
import threading
import time
import ipaddress
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from models import db, ScanRun, DiscoveredCertificate, ScanProfile

from .helpers import _validate_port, _scan_semaphore, _MAX_CONCURRENT_SCANS, _parse_target, _parse_iso

logger = logging.getLogger(__name__)


class ScannerMixin:

    def start_scan(self, targets: List[str], ports: List[int] = None,
                   profile_id: int = None, triggered_by: str = 'manual',
                   triggered_by_user: str = None, app=None,
                   timeout: int = None, max_workers: int = None,
                   resolve_dns: bool = False) -> int:
        """Start an async scan. Returns scan_run_id immediately."""
        if not _scan_semaphore.acquire(blocking=False):
            raise ValueError(
                f"Too many concurrent scans (max {_MAX_CONCURRENT_SCANS}). "
                "Please wait for existing scans to complete."
            )
        try:
            return self._prepare_and_launch_scan(
                targets, ports, profile_id, triggered_by,
                triggered_by_user, app, timeout, max_workers, resolve_dns
            )
        except Exception:
            _scan_semaphore.release()
            raise

    def _prepare_and_launch_scan(self, targets, ports, profile_id, triggered_by,
                                  triggered_by_user, app, timeout, max_workers,
                                  resolve_dns) -> int:
        """Build job list and launch scan thread. Caller holds _scan_semaphore."""
        if ports is None:
            ports = [443]
        # Validate ports
        ports = [_validate_port(p) for p in ports]
        ports = [p for p in ports if p > 0] or [443]
        scan_timeout = timeout or self.timeout
        scan_workers = max_workers or self.max_workers

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

            host, custom_port = _parse_target(raw)
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
            timeout=scan_timeout,
            max_workers=scan_workers,
            resolve_dns=resolve_dns,
        )
        db.session.add(run)
        db.session.commit()
        run_id = run.id

        # Launch background thread
        thread = threading.Thread(
            target=self._execute_scan,
            args=(run_id, jobs, profile_id, app, scan_timeout, scan_workers, resolve_dns),
            daemon=True,
        )
        thread.start()
        return run_id

    def start_subnet_scan(self, cidr: str, ports: List[int] = None,
                          profile_id: int = None, triggered_by: str = 'manual',
                          triggered_by_user: str = None, app=None,
                          timeout: int = None, max_workers: int = None,
                          resolve_dns: bool = False) -> int:
        """Start async subnet scan. Returns scan_run_id."""
        network = ipaddress.ip_network(cidr, strict=False)
        targets = [str(ip) for ip in network.hosts()]
        return self.start_scan(targets, ports, profile_id, triggered_by,
                               triggered_by_user, app, timeout, max_workers, resolve_dns)

    def _execute_scan(self, run_id: int, jobs: List[Tuple[str, int]],
                      profile_id: int, app, timeout: int = 5,
                      max_workers: int = 20, resolve_dns: bool = False):
        """Background thread: scan all targets and save results."""
        try:
            if app:
                with app.app_context():
                    self._do_scan(run_id, jobs, profile_id, timeout, max_workers, resolve_dns)
            else:
                self._do_scan(run_id, jobs, profile_id, timeout, max_workers, resolve_dns)
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
        finally:
            _scan_semaphore.release()

    def _do_scan(self, run_id: int, jobs: List[Tuple[str, int]], profile_id: int,
                 timeout: int = 5, max_workers: int = 20, resolve_dns: bool = False):
        """Core scanning logic running in background."""
        import json as _json
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
        logger.info(f"Discovery scan {run_id} started: {len(jobs)} targets (timeout={timeout}s, workers={max_workers}, rdns={resolve_dns})")

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

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(self.probe_tls, h, p, timeout, resolve_dns): (h, p) for h, p in jobs}

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

        # SNI probing — re-probe IP targets with SAN hostnames to discover multi-cert proxies
        sni_jobs = {}  # (host, port, sni) -> default_fingerprint
        for r in results:
            if 'fingerprint_sha256' not in r:
                continue
            try:
                ipaddress.ip_address(r['target'])
            except ValueError:
                continue  # Only SNI-probe IP targets
            for san in (r.get('san_dns_names') or [])[:20]:
                if san.startswith('*.') or san == r['target']:
                    continue
                key = (r['target'], r['port'], san)
                if key not in sni_jobs:
                    sni_jobs[key] = r['fingerprint_sha256']

        if sni_jobs:
            logger.info(f"SNI probing: {len(sni_jobs)} additional probes for scan {run_id}")
            total_with_sni = len(jobs) + len(sni_jobs)
            run.total_targets = total_with_sni
            db.session.commit()

            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                sni_futures = {
                    pool.submit(self.probe_tls, h, p, timeout, False, sni): (h, p, sni, orig_fp)
                    for (h, p, sni), orig_fp in sni_jobs.items()
                }
                for future in as_completed(sni_futures):
                    h, p, sni, orig_fp = sni_futures[future]
                    r = future.result()
                    scanned += 1
                    if scanned % 10 == 0 or (time.time() - last_progress) > 3:
                        on_discovery_scan_progress(run_id, scanned, total_with_sni, found)
                        last_progress = time.time()
                    if 'fingerprint_sha256' in r and r['fingerprint_sha256'] != orig_fp:
                        logger.info(f"SNI discovery: {h}:{p} SNI={sni} → different cert ({r['fingerprint_sha256'][:16]})")
                        results.append(r)
                        found += 1
                        new_certs += 1

        # Save results to DB
        for r in results:
            error_type = r.get('error_type', '')
            if 'error' in r and 'fingerprint_sha256' not in r:
                # Skip connection-level errors (not TLS endpoints)
                if error_type in ('refused', 'network', 'timeout', 'dns'):
                    continue
                # Only save TLS-level errors (SNI rejected, cert parse, etc.)
                self._save_error(r, profile_id, now)
                continue

            fp = r['fingerprint_sha256']
            ucm_id = fp_index.get(fp)
            status = 'managed' if ucm_id else 'unmanaged'
            sni = r.get('sni_hostname', '')

            existing = DiscoveredCertificate.query.filter_by(
                target=r['target'], port=r['port'], sni_hostname=sni
            ).first()

            san_dns_json = _json.dumps(r.get('san_dns_names', []))
            san_ips_json = _json.dumps(r.get('san_ip_addresses', []))
            san_emails_json = _json.dumps(r.get('san_emails', []))
            san_uris_json = _json.dumps(r.get('san_uris', []))

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
                existing.san_dns_names = san_dns_json
                existing.san_ip_addresses = san_ips_json
                existing.san_emails = san_emails_json
                existing.san_uris = san_uris_json
                if r.get('dns_hostname'):
                    existing.dns_hostname = r['dns_hostname']
            else:
                new_certs += 1
                dc = DiscoveredCertificate(
                    scan_profile_id=profile_id,
                    target=r['target'], port=r['port'],
                    sni_hostname=sni,
                    subject=r.get('subject'),
                    issuer=r.get('issuer'),
                    serial_number=r.get('serial_number'),
                    not_before=_parse_iso(r.get('not_before')),
                    not_after=_parse_iso(r.get('not_after')),
                    fingerprint_sha256=fp,
                    pem_certificate=r.get('pem_certificate'),
                    status=status,
                    ucm_certificate_id=ucm_id,
                    dns_hostname=r.get('dns_hostname'),
                    san_dns_names=san_dns_json,
                    san_ip_addresses=san_ips_json,
                    san_emails=san_emails_json,
                    san_uris=san_uris_json,
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

        # Count expiring/expired certs for this profile
        expiring_certs = 0
        if profile_id:
            threshold = datetime.now(timezone.utc) + timedelta(days=30)
            expiring_certs = DiscoveredCertificate.query.filter(
                DiscoveredCertificate.scan_profile_id == profile_id,
                DiscoveredCertificate.not_after.isnot(None),
                DiscoveredCertificate.not_after <= threshold,
                DiscoveredCertificate.scan_error.is_(None),
            ).count()

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
            'expiring_certs': expiring_certs,
            'errors': errors_real,
        }
        on_discovery_scan_complete(run_id, summary)
        logger.info(f"Discovery scan {run_id} complete: {summary}")

        # Send email notifications if configured
        self._send_notifications(profile_id, summary, new_certs, changed_certs, expiring_certs)

    def _save_error(self, r: Dict, profile_id: int, now: datetime):
        """Save a scan error (not connection_refused)."""
        sni = r.get('sni_hostname', '')
        existing = DiscoveredCertificate.query.filter_by(
            target=r['target'], port=r['port'], sni_hostname=sni
        ).first()
        if existing:
            existing.last_seen = now
            existing.scan_error = r.get('error')
            existing.status = 'error'
        else:
            dc = DiscoveredCertificate(
                scan_profile_id=profile_id,
                target=r['target'], port=r['port'],
                sni_hostname=sni,
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
