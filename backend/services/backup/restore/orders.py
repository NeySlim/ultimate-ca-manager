"""ACME client orders this installation moved on with after the archive was taken.

Merge: the order here wins when it is further along, renewed since (with its
certificate, its owed revocations and the archived renewal children) or
finalizing with a key held. Replacement: the archive wins, and says what it gives up.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from models import db

from ..export_generic import REFERENCE_SUFFIX
from ..manifest import SECTIONS

# Statuses of an order whose finalization was sent: the CA may already have issued
_FINALIZING = ('processing', 'valid')


def _instant(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _utc(moment: datetime) -> str:
    return f"{moment:%Y-%m-%d %H:%M:%S} UTC"


def _here(row: Dict[str, Any]):
    from models.acme_models import AcmeClientOrder
    created_at = _instant(row.get('created_at'))
    if created_at is None:
        return None
    with db.session.no_autoflush:
        return AcmeClientOrder.query.filter_by(environment=row.get('environment'),
                                               domains=row.get('domains'),
                                               created_at=created_at).first()


def _renewed_here(order, row) -> bool:
    archived = _instant(row.get('last_renewal_at'))
    return order.last_renewal_at is not None and (archived is None or order.last_renewal_at > archived)


def _finalizing_here(order, row) -> bool:
    """A finalization under way here, where the archive is still before it."""
    if not (order._pending_key or order.status in _FINALIZING):
        return False
    status = row.get('status')
    return status not in _FINALIZING + ('issued',) or (bool(order._pending_key) and not row.get('pending_key'))


def keep_newer_orders(backup_data: Dict[str, Any], mode: str) -> List[str]:
    """Apply the rule to the archive (a merge drops what the row here outranks); the warnings."""
    from models import Certificate

    rows = backup_data.get('acme_client_orders')
    if not isinstance(rows, list):
        return []
    identity = SECTIONS['acme_client_orders'].identity
    warnings: List[str] = []
    dropped, certificates, parents = set(), set(), []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        order = _here(row)
        if order is None:
            continue
        names = row.get('domains')
        if _renewed_here(order, row):
            when = _utc(order.last_renewal_at)
            if mode == 'merge':
                dropped.add(index)
                parents.append({field: row.get(field) for field in identity})
                refid = (row.get(f'certificate_id{REFERENCE_SUFFIX}') or {}).get('refid')
                if refid:
                    certificates.add(refid)
                warnings.append(
                    f"ACME order {names} was renewed here on {when}, after the archive was "
                    "taken: the order, its certificate and its owed revocations here are kept")
            else:
                with db.session.no_autoflush:
                    issued = db.session.get(Certificate, order.certificate_id) if order.certificate_id else None
                serial = getattr(issued, 'serial_number', None) or 'unknown'
                warnings.append(
                    f"ACME order {names} was renewed here on {when}, after the archive was taken: "
                    f"the archived order and certificate replace it. The certificate issued here "
                    f"(serial {serial}) is still valid at the CA and no longer known to UCM, and the "
                    "restored one may have been revoked at the CA on renewal: renew the order")
        elif _finalizing_here(order, row):
            if mode == 'merge':
                dropped.add(index)
                warnings.append(
                    f"ACME order {names} is being finalized here ({order.status}): "
                    "kept as it is, with the key it holds")
            else:
                warnings.append(
                    f"ACME order {names} was being finalized here ({order.status}): the archived "
                    "order replaces it and the key held for it is dropped; the CA may have issued "
                    "a certificate UCM cannot import, place the order again")
    if mode == 'merge' and dropped:
        # A renewal child of an order renewed here: that renewal is over
        for index, row in enumerate(rows):
            if isinstance(row, dict) and row.get(f'renewal_of_order_id{REFERENCE_SUFFIX}') in parents:
                dropped.add(index)
        backup_data['acme_client_orders'] = [row for index, row in enumerate(rows) if index not in dropped]
        if certificates and isinstance(backup_data.get('certificates'), list):
            backup_data['certificates'] = [row for row in backup_data['certificates']
                                           if not (isinstance(row, dict) and row.get('refid') in certificates)]
    return warnings
