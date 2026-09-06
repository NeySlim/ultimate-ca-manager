"""HTTPS certificate binding (#303 M1).

Applying a managed certificate to HTTPS remembers its refid
(SystemConfig ``https_bound_certificate_refid``). When that certificate is
renewed (in-place since 2.214: the refid survives, the key may change), the
files are re-materialized and the service restarts, so the web UI never
serves a stale certificate again.
"""
import base64
import logging
import os
from pathlib import Path

from utils.datetime_utils import utc_now
from utils.key_codec import load_pem_bytes

logger = logging.getLogger(__name__)

BOUND_REFID_KEY = 'https_bound_certificate_refid'


def _paths():
    data_dir = os.environ.get('DATA_DIR', '/opt/ucm/data')
    cert_path = Path(os.environ.get('HTTPS_CERT_PATH', f'{data_dir}/https_cert.pem'))
    key_path = Path(os.environ.get('HTTPS_KEY_PATH', f'{data_dir}/https_key.pem'))
    return cert_path, key_path


def _decode(value):
    if value.startswith('-----BEGIN'):
        return value
    try:
        return base64.b64decode(value).decode('utf-8')
    except Exception:
        return value


def materialize_https_cert(cert) -> None:
    """Write cert+key (+CA chain) to the HTTPS file pair. Raises on failure."""
    import shutil

    from models import CA
    from services.ca_service import CAService

    cert_path, key_path = _paths()

    if cert_path.exists():
        backup_suffix = utc_now().strftime('%Y%m%d_%H%M%S')
        shutil.copy(cert_path, f"{cert_path}.backup-{backup_suffix}")
        if key_path.exists():
            shutil.copy(key_path, f"{key_path}.backup-{backup_suffix}")

    cert_data = _decode(cert.crt)
    key_data = load_pem_bytes(
        cert.prv, context=f"certificate {cert.id}"
    ).decode('utf-8')

    full_cert = cert_data
    if cert.caref:
        ca = CA.query.filter_by(refid=cert.caref).first()
        if ca:
            for chain_cert in CAService.get_ca_chain(ca.id):
                chain_str = chain_cert.decode('utf-8') if isinstance(chain_cert, bytes) else chain_cert
                if not full_cert.endswith('\n'):
                    full_cert += '\n'
                full_cert += chain_str

    cert_path.write_text(full_cert)
    key_path.write_text(key_data)
    os.chmod(key_path, 0o600)
    try:
        import pwd
        ucm_user = pwd.getpwnam('ucm')
        os.chown(cert_path, ucm_user.pw_uid, ucm_user.pw_gid)
        os.chown(key_path, ucm_user.pw_uid, ucm_user.pw_gid)
    except (KeyError, ImportError):
        pass


def get_bound_refid():
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=BOUND_REFID_KEY).first()
    return (row.value or '').strip() if row and row.value else ''


def set_bound_refid(refid):
    from models import SystemConfig, db
    row = SystemConfig.query.filter_by(key=BOUND_REFID_KEY).first()
    if not row:
        row = SystemConfig(key=BOUND_REFID_KEY,
                           description='Certificate bound to the HTTPS listener')
        db.session.add(row)
    row.value = refid or ''
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.error("Failed to update HTTPS certificate binding", exc_info=True)
        raise


def backfill_legacy_https_binding():
    """Bind a managed certificate that was applied before bindings existed.

    Versions before 2.217 copied the selected certificate to the HTTPS files
    without remembering its refid. On the first boot after upgrading, compare
    the installed leaf certificate with locally managed certificates and store
    the unique match. Existing explicit bindings always win; ambiguous matches
    are left untouched rather than guessing which row should follow renewals.
    """
    try:
        existing = get_bound_refid()
    except Exception as exc:
        logger.warning("Could not read HTTPS certificate binding: %s", exc)
        return ''
    if existing:
        return existing

    cert_path, _key_path = _paths()
    if not cert_path.exists():
        return ''

    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        from models import Certificate

        installed = x509.load_pem_x509_certificate(cert_path.read_bytes())
        installed_fingerprint = installed.fingerprint(hashes.SHA256())
        candidates = (
            Certificate.query
            .filter(Certificate.crt.isnot(None), Certificate.prv.isnot(None))
            .filter(Certificate.revoked.isnot(True), Certificate.archived.isnot(True))
            .all()
        )
        matches = []
        for candidate in candidates:
            try:
                managed = x509.load_pem_x509_certificate(
                    _decode(candidate.crt).encode('utf-8')
                )
                if managed.fingerprint(hashes.SHA256()) == installed_fingerprint:
                    matches.append(candidate.refid)
            except Exception:
                continue

        if len(matches) == 1:
            set_bound_refid(matches[0])
            logger.info(
                "Detected legacy HTTPS certificate binding to managed certificate %s",
                matches[0],
            )
            return matches[0]
        if len(matches) > 1:
            logger.warning(
                "Could not backfill HTTPS certificate binding: installed certificate "
                "matches multiple managed rows"
            )
    except Exception as exc:
        logger.warning("Could not detect legacy HTTPS certificate binding: %s", exc)
    return ''


def on_certificate_renewed(event_type, payload, ca_refid, meta):
    """Event-bus subscriber: re-materialize the bound HTTPS certificate.

    Runs synchronously in the renewing request (bus contract) but only does
    file writes plus an async service restart; it reads its own data by
    refid and never touches the caller's ORM instances.
    """
    try:
        cert_info = (payload or {}).get('certificate') or {}
        refid = cert_info.get('refid')
        bound = get_bound_refid()
        if not bound or not refid or refid != bound:
            return
        from models import Certificate
        cert = Certificate.query.filter_by(refid=refid).first()
        if not cert or not cert.crt or not cert.prv:
            logger.warning(
                "HTTPS-bound certificate %s renewed but unusable "
                "(missing cert or key) — HTTPS files left untouched", refid)
            return
        materialize_https_cert(cert)
        logger.info(
            "HTTPS-bound certificate %s renewed — re-materialized, "
            "restarting the service", refid)
        from services.audit_service import AuditService
        AuditService.log_action(
            action='https_apply', resource_type='system',
            resource_id=str(cert.id), resource_name=cert.descr or refid,
            details='HTTPS certificate re-materialized after renewal',
            success=True,
        )
        if os.getenv('UCM_DOCKER') == '1' or os.path.exists('/.dockerenv'):
            logger.warning("Running in Docker: restart the container to load "
                           "the renewed HTTPS certificate")
            return
        from utils.service_manager import restart_service
        restart_service()
    except Exception as exc:  # never break the renewal itself
        logger.error(f"HTTPS re-materialization after renewal failed: {exc}")


def register_https_binding_subscriber(app):
    from services.events import event_bus
    if getattr(register_https_binding_subscriber, '_done', False):
        return
    event_bus.subscribe('certificate.renewed', on_certificate_renewed)
    with app.app_context():
        backfill_legacy_https_binding()
    register_https_binding_subscriber._done = True
