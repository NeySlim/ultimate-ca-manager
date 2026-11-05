"""Certificates the ACME client obtained: the chain as the CA sent it, and the renewal of a row in place.

A renewal writes into the row of the certificate it replaces, which keeps its id and refid:
whatever names the row (HTTPS binding, deployment bindings, webhooks) follows the
certificate.renewed event without being told about a new row.
"""
import base64
import json
import logging
from typing import Optional, Tuple

from cryptography import x509

from utils.key_match import certificate_matches_private_key

logger = logging.getLogger(__name__)


def split_chain(cert_pem: str) -> Tuple[Optional[str], Optional[str]]:
    """``(end-entity PEM, rest of the chain or None)``; ``(None, None)`` without a certificate."""
    blocks, current = [], []
    for line in cert_pem.strip().splitlines():
        current.append(line)
        if line.strip() == '-----END CERTIFICATE-----':
            blocks.append('\n'.join(current))
            current = []
    if not blocks:
        return None, None
    return blocks[0], ('\n'.join(blocks[1:]) if len(blocks) > 1 else None)


def load_leaf(cert_pem: str) -> x509.Certificate:
    end_entity, _chain = split_chain(cert_pem)
    if end_entity is None:
        raise ValueError('No certificate in the CA response')
    return x509.load_pem_x509_certificate(end_entity.encode())


def check_key(leaf: x509.Certificate, key_pem: Optional[str]) -> None:
    """ValueError when the key held for the order is not the certificate's."""
    if key_pem is None:
        return
    from cryptography.hazmat.primitives import serialization
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    if not certificate_matches_private_key(leaf, key):
        raise ValueError('The certificate the CA issued does not match the key held for this order')


def write_renewed(row, cert_pem: str, key_pem: Optional[str], now) -> x509.Certificate:
    """Stage the renewed certificate (and its key, when one is held) into ``row``, uncommitted."""
    from utils.key_codec import store_pem_bytes
    from utils.san_parse import san_buckets_from_certificate

    end_entity, chain = split_chain(cert_pem)
    leaf = load_leaf(cert_pem)
    check_key(leaf, key_pem)
    full = end_entity.strip() + '\n' + chain.strip() if chain else end_entity
    row.crt = base64.b64encode(full.encode()).decode()  # key_algo, AKI and SKI follow crt
    if key_pem is not None:
        row.prv = store_pem_bytes(key_pem.encode())
    cn = leaf.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
    row.subject = leaf.subject.rfc4514_string()
    row.subject_cn = cn[0].value if cn else None
    row.issuer = leaf.issuer.rfc4514_string()
    row.serial_number = str(leaf.serial_number)  # decimal, as the import writes it
    row.valid_from = leaf.not_valid_before_utc.replace(tzinfo=None)
    row.valid_to = leaf.not_valid_after_utc.replace(tzinfo=None)
    for column, values in san_buckets_from_certificate(leaf).items():
        setattr(row, column, json.dumps(values) if values else None)
    row.archived = False
    row.renewed_at = now
    row.renewed_times = (row.renewed_times or 0) + 1
    return leaf


def after_renewal_commit(row, cert_pem: str, key_pem: Optional[str], old_serial) -> None:
    """Files, audit and certificate.renewed for a row renewed in place; failures are logged only."""
    snapshot = row.to_dict()  # before any subscriber's commit expires the row
    cert_id, caref, name = row.id, row.caref, row.descr or row.subject
    try:
        from services.file_regen_service import mirror_private_key
        from utils.file_naming import cert_cert_path, cert_key_path
        end_entity, _chain = split_chain(cert_pem)
        path = cert_cert_path(row)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(end_entity.encode())
        if key_pem is not None:
            mirror_private_key(cert_key_path(row), key_pem.encode(), context=f'certificate {cert_id}')
    except Exception as exc:
        logger.warning("Files of renewed certificate %s not written: %s", cert_id, exc)
    try:
        from services.audit_service import AuditService
        AuditService.log_action(
            action='certificate_renewed', resource_type='certificate', resource_id=str(cert_id),
            resource_name=name, success=True, username='system',
            details=f"Renewed by the ACME client until {snapshot.get('valid_to')}; serial "
                    f"{old_serial} -> {snapshot.get('serial_number')}")
    except Exception as exc:
        logger.warning("Renewal of certificate %s not audited: %s", cert_id, exc)
    try:
        from services.webhook_service import emit_cert_renewed
        emit_cert_renewed(snapshot, ca_refid=caref, actor='system')
    except Exception as exc:
        logger.warning("Renewal event of certificate %s not emitted: %s", cert_id, exc)
