"""Findings and explicit repairs for CA records damaged before cross-certificates were modelled (#400).

Nothing here runs by itself: a self-signed root that was overwritten or deleted only
comes back from a backup or through restore-primary.
"""
import base64
import logging
from datetime import datetime, timezone
from typing import List, Optional

from cryptography import x509

from models import CA, db
from services.ca import cross_certs
from services.ca.cross_certs import CrossCertError

logger = logging.getLogger(__name__)

NOTE = ('A self-signed root that was overwritten or deleted is not recovered here: '
        'restore it from a backup, or give its certificate to restore-primary.')
_SETTINGS = ('acme.issuing_ca_id', 'est_ca_refid', 'tsa_ca_refid', 'wstep_ca_refid', 'xcep_ca_refid',
             'mtls_trusted_ca_id', 'scep_ca_id')
_ALIAS_PREFIX = 'ca_url_alias_'
_CROSS_PREFIX = 'ca_url_cross_'


def _identity(record):
    """``(certificate, fingerprint, spki, self_signed)`` of the record, or None without a readable certificate."""
    from utils.cert_issuer import is_self_signed
    cert = cross_certs._load_record(record) if record.crt else None
    if cert is None:
        return None
    from cryptography.hazmat.primitives import hashes
    try:
        return cert, cert.fingerprint(hashes.SHA256()).hex(), cross_certs._spki(cert), is_self_signed(cert)
    except Exception:
        return None  # a key pyca cannot load (SM2, GOST, FRP256v1): never part of a repair


def _held():
    held = []
    for record in CA.query.order_by(CA.id).all():
        ident = _identity(record)
        if ident is not None:
            held.append((record, *ident))
    return held


def _find_root(x_cert, x_spki, x_fp, held):
    """The self-signed record with the subject and key of a non-self-signed one, or None.

    Several candidates: the one valid the longest."""
    best = None
    for record, cert, fp, spki, selfs in held:
        if selfs and fp != x_fp and spki == x_spki and cert.subject == x_cert.subject:
            if best is None or cert.not_valid_after_utc > best[0]:
                best = (cert.not_valid_after_utc, record)
    return best[1] if best else None


def findings() -> List[dict]:
    held = _held()
    out, covered = [], set()
    for record, cert, fp, spki, selfs in held:
        if selfs:
            continue
        root = _find_root(cert, spki, fp, held)
        if root is None:
            continue
        covered.update((record.id, root.id))
        out.append({'kind': 'shadowed_root', 'ca_id': record.id, 'ca_name': record.descr,
                    'root_id': root.id, 'root_name': root.descr, 'subject': record.subject,
                    'ski': record.ski, 'actions': ['convert_to_cross']})
    groups = {}
    selfsigned = {record.id for record, _c, _f, _s, selfs in held if selfs}
    for record, _cert, fp, _spki, _selfs in held:
        if record.ski and record.id not in covered:
            groups.setdefault(record.ski, {})[record.id] = (record, fp)
    for ski, members in groups.items():
        if len({fp for _, fp in members.values()}) < 2:
            continue
        first = next(iter(members.values()))[0]
        out.append({'kind': 'same_key_distinct_certs', 'ca_ids': sorted(members), 'subject': first.subject,
                    'ski': ski, 'actions': [] if selfsigned & set(members) else ['restore_primary']})
    return out


def _record(ca_id) -> CA:
    record = db.session.get(CA, ca_id)
    if record is None:
        raise CrossCertError('CA not found', 404, 'not_found')
    return record


def _move_settings(record, root, cross=None):
    """Point the CA settings, the OCSP responder choice and the public URLs of *record* at *root*."""
    from models import SystemConfig
    for key in _SETTINGS:
        cfg = SystemConfig.query.filter_by(key=key).first()
        if cfg is None:
            continue
        if cfg.value == record.refid:
            cfg.value = root.refid
        elif cfg.value == str(record.id):
            cfg.value = str(root.id)
    responder = SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{record.id}').first()
    if responder is not None:
        if SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{root.id}').first() is None:
            responder.key = f'ocsp_responder_cert_{root.id}'
        else:
            db.session.delete(responder)
    for old in SystemConfig.query.filter(SystemConfig.key.like(f'{_ALIAS_PREFIX}%'),
                                         SystemConfig.value == record.refid).all():
        old.value = root.refid
    for ref in filter(None, (record.refid, record.url_slug, str(record.id))):
        key = f'{_ALIAS_PREFIX}{ref}'[:100]
        alias = SystemConfig.query.filter_by(key=key).first()
        if alias is None:
            db.session.add(SystemConfig(key=key, value=root.refid,
                                        description='URL of a removed duplicate CA record'))
        else:
            alias.value = root.refid
    if cross is not None:
        for ref in filter(None, (record.refid, record.url_slug)):
            _upsert(f'{_CROSS_PREFIX}{ref}'[:100], str(cross.id))


def _upsert(key, value):
    from models import SystemConfig
    cfg = SystemConfig.query.filter_by(key=key).first()
    if cfg is None:
        db.session.add(SystemConfig(key=key, value=value, description='URL of a removed duplicate CA record'))
    else:
        cfg.value = value


def _move_publication(record, root):
    """Keep CRL/OCSP publication on: a root left disabled would never regenerate the moved CRL."""
    for flag in ('cdp_enabled', 'ocsp_enabled', 'delta_crl_enabled'):
        setattr(root, flag, bool(getattr(root, flag) or getattr(record, flag)))
    for field in ('crl_validity_days', 'crl_publish_interval_hours', 'crl_digest'):
        if not getattr(root, field):
            setattr(root, field, getattr(record, field))


def _move_scep_challenge(record, root, was_scep_ca=False):
    """Move the challenge and its timestamp together; the configured SCEP CA's pair wins over the root's."""
    from models import SystemConfig
    pair = [SystemConfig.query.filter_by(key=f'scep_challenge_{record.id}{suffix}').first()
            for suffix in ('', '_generated_at')]
    if pair[0] is None and pair[1] is None:
        return
    mine = SystemConfig.query.filter(SystemConfig.key.in_(
        [f'scep_challenge_{root.id}', f'scep_challenge_{root.id}_generated_at'])).all()
    if mine and not was_scep_ca:
        for old in pair:
            if old is not None:
                db.session.delete(old)
        return
    for old in mine:
        db.session.delete(old)
    db.session.flush()
    for old, suffix in zip(pair, ('', '_generated_at')):
        if old is not None:
            old.key = f'scep_challenge_{root.id}{suffix}'


def alias_target(ref):
    """The CA now serving the URLs of a duplicate record that was converted, or None."""
    from models import SystemConfig
    cfg = SystemConfig.query.filter_by(key=f'{_ALIAS_PREFIX}{ref}'[:100]).first()
    return CA.query.filter_by(refid=cfg.value).first() if cfg and cfg.value else None


def alias_cross(ref, ca):
    """The cross-certificate row the duplicate URL *ref* served, if it belongs to *ca* and is servable."""
    from models import SystemConfig
    from models.ca_cross_certificate import CACrossCertificate
    cfg = SystemConfig.query.filter_by(key=f'{_CROSS_PREFIX}{ref}'[:100]).first()
    row = db.session.get(CACrossCertificate, int(cfg.value)) if cfg and (cfg.value or '').isdigit() else None
    return row if row is not None and row.ca_id == ca.id and row.servable else None


def convert_to_cross(ca_id: int, username: str = 'system'):
    """Turn a non-self-signed record shadowing a held root into that root's cross-certificate.

    Its children, issued certificates and settings move to the root, and its URLs keep resolving to it;
    returns ``(root, row, warnings)``."""
    from types import SimpleNamespace
    from services.ski_aki_backfill import _move_ca_dependents
    from models.ca_cross_certificate import CACrossCertificate
    record = _record(ca_id)
    ident = _identity(record)
    if ident is None or ident[3]:
        raise CrossCertError('Only a record holding a certificate that is not self-signed can be converted',
                             409, 'not_convertible')
    cert, fp, spki, _ = ident
    held = _held()
    root = _find_root(cert, spki, fp, held)
    if root is not None:
        carrier = CACrossCertificate.query.filter_by(fingerprint_sha256=fp).first()
        if carrier is not None and carrier.ca_id != root.id:
            holder = next((r for r, c, _f, k, selfs in held
                           if r.id == carrier.ca_id and selfs and k == spki and c.subject == cert.subject
                           and c.not_valid_after_utc > datetime.now(timezone.utc)), None)
            if holder is not None:
                root = holder
            else:
                carrier.ca_id = root.id
    if root is None:
        raise CrossCertError('No self-signed record holds this subject and key: restore a backup, or '
                             'give the self-signed certificate to restore-primary', 409, 'no_root')
    snapshot = record.descr
    for row in cross_certs.list_for(record):
        row.served = False
    db.session.flush()
    row = CACrossCertificate.query.filter_by(ca_id=root.id, fingerprint_sha256=fp).first()
    warnings = []
    if row is None:
        row, warnings = cross_certs.attach_certificate(root, cert, username, commit=False)
    if not root.prv and not root.hsm_key_id:
        root.prv, root.hsm_key_id = record.prv, record.hsm_key_id
    _move_ca_dependents(db, record, root)
    from models import SystemConfig
    scep_cfg = SystemConfig.query.filter_by(key='scep_ca_id').first()
    was_scep_ca = bool(scep_cfg and scep_cfg.value in (str(record.id), record.refid))
    _move_settings(record, root, row)
    _move_scep_challenge(record, root, was_scep_ca)
    _move_publication(record, root)
    snapshot_dict = record.to_dict()
    files = SimpleNamespace(**{c.key: getattr(record, c.key) for c in CA.__table__.columns})
    db.session.execute(db.text('DELETE FROM certificate_authorities WHERE id = :id'), {'id': record.id})
    db.session.expunge(record)
    db.session.commit()
    try:
        from services.ca.helpers import delete_ca_files
        delete_ca_files(files)
    except Exception as e:
        logger.warning(f'Converted duplicate {snapshot}: its files could not be removed: {e}')
    from services.webhook_service import emit_ca_deleted
    emit_ca_deleted(snapshot_dict, actor=username)
    from services.audit_service import AuditService
    AuditService.log_ca('ca_cross_repair_converted', root,
                        f'Duplicate record {snapshot} converted into a cross-certificate of {root.descr}',
                        username=username)
    cross_certs.announce(root, 'attached', row, username, {'converted_ca': snapshot})
    return root, row, warnings


def restore_primary(ca_id: int, certificate, username: str = 'system'):
    """Put a self-signed certificate back on a record that holds a cross-certificate of its key.

    The replaced certificate is kept as a cross-certificate; returns ``(record, row, warnings)``."""
    from services.import_service import extract_cert_info, update_ca_from_import, ImportConflict
    from utils.cert_issuer import is_self_signed
    record = _record(ca_id)
    ident = _identity(record)
    if ident is None or ident[3]:
        raise CrossCertError('Only a record holding a certificate that is not self-signed can be restored',
                             409, 'not_restorable')
    old, old_fp, spki, _ = ident
    new = cross_certs.parse_certificate(certificate)
    try:
        basic = new.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        basic = False
    if not basic or not is_self_signed(new):
        raise CrossCertError('The certificate must be a self-signed CA certificate')
    if new.subject != old.subject or cross_certs._spki(new) != spki:
        raise CrossCertError("The certificate's subject or key differs from the record's")
    root = _find_root(old, spki, old_fp, _held())
    if root is not None:
        raise CrossCertError(f'The self-signed record {root.descr} already holds this key: '
                             'use convert-to-cross on this duplicate', 409, 'root_held')
    from cryptography.hazmat.primitives import serialization
    pem = new.public_bytes(serialization.Encoding.PEM)
    try:
        update_ca_from_import(record, new, pem, extract_cert_info(new), name=record.descr)
        row, warnings = cross_certs.attach_certificate(record, old, username, commit=False)
    except ImportConflict as e:
        db.session.rollback()
        raise CrossCertError(str(e), 409, 'key_unverifiable') from e
    except CrossCertError:
        db.session.rollback()
        raise
    db.session.commit()
    from services.audit_service import AuditService
    AuditService.log_ca('ca_cross_repair_restored', record,
                        f'Self-signed certificate restored on CA {record.descr}', username=username)
    cross_certs.announce(record, 'attached', row, username, {'restored_primary': True})
    return record, row, warnings
