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

logger = logging.getLogger(__name__)

# boot_config reads them before the application exists
from boot_config import HTTPS_BOUND_KEY as BOUND_REFID_KEY, HTTPS_CHAIN_KEY as CHAIN_KEY  # noqa: E402


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


def with_ca_chain(cert, cert_text: str) -> str:
    """*cert_text* followed by the chain of the CA that issued *cert* (root included), as the CA serves it."""
    from models import CA
    from services.ca_service import CAService

    ca = CA.query.filter_by(refid=cert.caref).first() if cert.caref else None
    if ca is None:
        return cert_text
    for chain_cert in CAService.get_ca_chain(ca.id):
        chain_str = chain_cert.decode('utf-8') if isinstance(chain_cert, bytes) else chain_cert
        if not cert_text.endswith('\n'):
            cert_text += '\n'
        cert_text += chain_str
    return cert_text


def https_key_pem(cert) -> str:
    """The certificate's private key as PEM text; raises ValueError when it cannot be read."""
    from boot_config import HttpsMaterialError, _key_text
    try:
        return _key_text(cert.prv, f"certificate {cert.id}")
    except HttpsMaterialError as e:
        raise ValueError(str(e)) from None


def materialize_https_cert(cert) -> str:
    """Write cert+key (+CA chain) to the HTTPS file pair and return the certificate text.

    Raises on failure, leaving both files as they were.
    """
    from boot_config import write_https_pair

    cert_path, key_path = _paths()
    key_data = https_key_pem(cert)
    full_cert = with_ca_chain(cert, _decode(cert.crt))
    write_https_pair(cert_path, key_path, full_cert, key_data,
                     backup_suffix=utc_now().strftime('%Y%m%d_%H%M%S'))
    return full_cert


def _set_config(key, value, description):
    from models import SystemConfig, db
    row = SystemConfig.query.filter_by(key=key).first()
    if not row:
        row = SystemConfig(key=key, description=description)
        db.session.add(row)
    row.value = value


def remember_chain(full_cert):
    """The certificate text every node writes at its next start (caller commits)."""
    _set_config(CHAIN_KEY, full_cert or '', 'HTTPS certificate chain written with the binding')


def get_bound_refid():
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=BOUND_REFID_KEY).first()
    return (row.value or '').strip() if row and row.value else ''


def set_bound_refid(refid, chain=None):
    """Bind *refid* (or nothing) with the certificate text written for it, and commit.

    A new binding replaces a regenerated self-signed pair stored for the cluster.
    """
    from models import db
    from services import shared_files
    _set_config(BOUND_REFID_KEY, refid or '', 'Certificate bound to the HTTPS listener')
    remember_chain(chain if refid else '')
    if refid:
        shared_files.drop_file(shared_files.HTTPS_GENERATED)
    # Any rebinding settles a renewal the binding could not follow
    from services.binding_attention import clear_https
    clear_https()
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


def backfill_chain():
    """A binding stored without its certificate text (before 3.0, or a renewal that could not
    store it) gets it now, so a node starting without the files writes the whole chain."""
    from boot_config import _first_certificate
    from models import Certificate, SystemConfig, db
    refid = get_bound_refid()
    if not refid:
        return
    cert = Certificate.query.filter_by(refid=refid).first()
    if not cert or not cert.crt:
        return
    leaf = _decode(cert.crt)
    row = SystemConfig.query.filter_by(key=CHAIN_KEY).first()
    if row and row.value and _first_certificate(row.value) == _first_certificate(leaf):
        return
    try:
        remember_chain(with_ca_chain(cert, leaf))
        db.session.commit()
    except Exception as exc:  # another process of the cluster stored it first
        db.session.rollback()
        logger.warning(f"HTTPS certificate chain not stored: {type(exc).__name__}")


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
                "(missing cert or key). HTTPS files left untouched", refid)
            return
        full_cert = materialize_https_cert(cert)
        from models import db
        remember_chain(full_cert)
        db.session.commit()
        logger.info(
            "HTTPS-bound certificate %s renewed, re-materialized, "
            "restarting the service", refid)
        from services.audit_service import AuditService
        AuditService.log_action(
            action='https_apply', resource_type='system',
            resource_id=str(cert.id), resource_name=cert.descr or refid,
            details='HTTPS certificate re-materialized after renewal',
            success=True,
        )
        started, message = restart_to_serve()
        if started is None:
            logger.warning("Running in Docker: restart the container to load "
                           "the renewed HTTPS certificate")
        elif not started:
            logger.error(f"HTTPS certificate renewed but not served yet: {message}")
    except Exception as exc:  # never break the renewal itself
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        logger.error(f"HTTPS re-materialization after renewal failed: {exc}")


def restart_to_serve():
    """``(started, message)`` after the HTTPS files changed; ``started`` is None when the
    container must be restarted by hand. HA: a rolling restart, each node writes the files
    from the database as it starts."""
    from config.settings import is_docker
    from utils.ha import ha_enabled
    if not ha_enabled() and is_docker():
        return None, "Restart the container to apply."
    from utils.service_manager import restart_service
    return restart_service()


def apply_bound_now(refid):
    """Re-materialize *refid* now that the binding names it (same path as a renewal)."""
    on_certificate_renewed('certificate.renewed', {'certificate': {'refid': refid}}, None, {})


def register_https_binding_subscriber(app):
    from services.events import event_bus
    if getattr(register_https_binding_subscriber, '_done', False):
        return
    event_bus.subscribe('certificate.renewed', on_certificate_renewed)
    with app.app_context():
        backfill_legacy_https_binding()
        try:
            backfill_chain()
        except Exception as exc:
            logger.warning(f"Could not check the stored HTTPS certificate chain: {exc}")
    register_https_binding_subscriber._done = True
