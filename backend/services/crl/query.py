import logging
from typing import List, Optional
from sqlalchemy import or_
from models import db, CA, Certificate
from models.crl import CRLMetadata
from services.cert.serial_resolution import resolve_record_serial, same_serial

logger = logging.getLogger(__name__)


def _not_expired(column, now):
    """Rows whose validity has not passed, including those that never said.

    RFC 5280 §5: an expired certificate needs no CRL entry, a client rejects
    it on its own dates. A row with no ``valid_to`` says nothing about its
    dates, and ``column > now`` answers NULL for it — neither true nor false
    — on SQLite and on PostgreSQL alike, so both silently dropped the
    revocation while the OCSP responder, which filters on nothing of the
    sort, went on answering revoked. Unknown expiry is not expiry: the entry
    stays until something says otherwise.
    """
    return or_(column.is_(None), column > now)


def _revoked_child_cas(ca, now) -> list:
    """Revoked child CAs of ``ca`` whose validity has not passed.
    A revoked child CA is listed from its own row too: its record under
    this CA can be missing (a backup restored without certificates),
    and OCSP already answers revoked from the flag (review of #343)."""
    return CA.query.filter(
        CA.caref == ca.refid,
        CA.revoked == True,
        _not_expired(CA.valid_to, now)
    ).all()
class CRLQueryMixin:
    @staticmethod  # PLANB-B.6: à implémenter selon SPEC (invariants 21 à 23, 30, 31)
    def get_revoked_certificates(ca_id: int) -> list:
        """Revoked entries the full CRL of this CA carries; the revoked child
        CAs come from ``_revoked_child_cas``."""
        ca = db.session.get(CA, ca_id)
        if not ca:
            raise ValueError(f"CA with id {ca_id} not found")
        raise NotImplementedError('PLANB-B.6: get_revoked_certificates')
    @staticmethod  # PLANB-B.6: à implémenter selon SPEC (invariants 21, 22, 52)
    def _filter_orphan_serials(revoked_serials: List, live_records: List) -> List:
        """Revocation records a CRL must still carry once the live records are listed.

        "Same serial" is the identical column *or* the same resolved integer:
        the column has three writers, so one certificate can be a decimal row
        here and a hex row there, and the entry is built from the integer.
        Matching on the column alone let both through and put the same serial
        on the CRL twice. Widening the test only ever drops more, never
        resurrects an entry the column test dropped."""
        raise NotImplementedError('PLANB-B.6: _filter_orphan_serials')
    @staticmethod  # PLANB-B.6: à implémenter selon SPEC (invariant 26)
    def purge_stale_revoked_serials(ca_id) -> int:
        raise NotImplementedError('PLANB-B.6: purge_stale_revoked_serials')

    @staticmethod  # PLANB-B.6: à implémenter selon SPEC (invariant 54)
    def is_auto_delete_enabled():
        raise NotImplementedError('PLANB-B.6: is_auto_delete_enabled')

    @staticmethod  # PLANB-B.6: à implémenter selon SPEC (invariant 54)
    def is_purge_stale_serials_enabled():
        raise NotImplementedError('PLANB-B.6: is_purge_stale_serials_enabled')

    @staticmethod  # PLANB-B.6: à implémenter selon SPEC (invariant 27)
    def purge_expired_revoked_certificates(ca_id) -> int:
        raise NotImplementedError('PLANB-B.6: purge_expired_revoked_certificates')
    @staticmethod
    def get_latest_crl(ca_id: int) -> Optional[CRLMetadata]:
        return CRLMetadata.query.filter_by(
            ca_id=ca_id, is_delta=False
        ).order_by(CRLMetadata.crl_number.desc()).first()

    @staticmethod
    def get_latest_crl_by_refid(ca_refid: str) -> Optional[CRLMetadata]:
        ca = CA.query.filter_by(refid=ca_refid).first()
        if not ca:
            return None
        return CRLQueryMixin.get_latest_crl(ca.id)

    @staticmethod
    def get_crl_pem(ca_refid: str) -> Optional[str]:
        crl = CRLQueryMixin.get_latest_crl_by_refid(ca_refid)
        return crl.crl_pem if crl else None

    @staticmethod
    def get_crl_der(ca_refid: str) -> Optional[bytes]:
        crl = CRLQueryMixin.get_latest_crl_by_refid(ca_refid)
        return crl.crl_der if crl else None

    @staticmethod
    def get_latest_delta_crl(ca_id: int) -> Optional[CRLMetadata]:
        return CRLMetadata.query.filter_by(
            ca_id=ca_id, is_delta=True
        ).order_by(CRLMetadata.crl_number.desc()).first()

    @staticmethod
    def get_latest_base_crl(ca_id: int) -> Optional[CRLMetadata]:
        return CRLMetadata.query.filter_by(
            ca_id=ca_id, is_delta=False
        ).order_by(CRLMetadata.crl_number.desc()).first()
