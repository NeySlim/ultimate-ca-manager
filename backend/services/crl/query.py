import logging
from typing import List, Optional
from sqlalchemy import or_
from models import db, CA, Certificate
from models.crl import CRLMetadata
from services.cert.serial_resolution import resolve_record_serial, same_serial
from utils.cert_issuer import same_key_refids
from utils.datetime_utils import utc_now

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


_TRUE_WORDS = frozenset({'true', '1', 'yes', 'on'})


def _setting_enabled(key: str) -> bool:
    """A housekeeping flag: on for true/1/yes/on (any case), off otherwise."""
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None or row.value is None:
        return False
    return str(row.value).strip().lower() in _TRUE_WORDS


def _dedupe_live_records(records: list) -> list:
    """First record of each resolved serial, in the given order.

    Live records hold their certificate, so the integer they resolve to is
    the CRL entry; the column only decides when no integer can be read."""
    kept, seen_ints, seen_columns = [], set(), set()
    for record in records:
        serial_int = resolve_record_serial(record)
        if serial_int is not None:
            if serial_int in seen_ints:
                continue
            seen_ints.add(serial_int)
        else:
            column = getattr(record, 'serial_number', None)
            if column is not None and column in seen_columns:
                continue
        column = getattr(record, 'serial_number', None)
        if column is not None:
            seen_columns.add(column)
        kept.append(record)
    return kept


class CRLQueryMixin:
    @staticmethod
    def get_revoked_certificates(ca_id: int) -> list:
        """Revoked entries the full CRL of this CA carries; the revoked child
        CAs come from ``_revoked_child_cas``."""
        ca = db.session.get(CA, ca_id)
        if not ca:
            raise ValueError(f"CA with id {ca_id} not found")
        from models.revoked_serial import RevokedSerial
        now = utc_now()
        certificates = Certificate.query.filter(
            Certificate.caref.in_(same_key_refids(ca)),
            Certificate.revoked == True,  # noqa: E712
            _not_expired(Certificate.valid_to, now),
        ).order_by(Certificate.id).all()
        child_cas = sorted(_revoked_child_cas(ca, now), key=lambda c: c.id)
        # The certificate record comes first: it carries the invalidity date
        live = _dedupe_live_records(certificates + child_cas)
        persisted = RevokedSerial.query.filter(
            RevokedSerial.caref.in_(same_key_refids(ca)),
            RevokedSerial.valid_to > now,
        ).order_by(RevokedSerial.revoked_at, RevokedSerial.id).all()
        return live + CRLQueryMixin._filter_orphan_serials(persisted, live)

    @staticmethod
    def _filter_orphan_serials(revoked_serials: List, live_records: List) -> List:
        """Revocation records a CRL must still carry once the live records are listed.

        Dropped: a serial a live record already lists (identical column or
        same resolved integer, as ``same_serial``), a serial still carried by
        its linked certificate that is no longer revoked, and repeats of a
        serial kept earlier in the list."""
        listed_columns, listed_ints = set(), set()

        def _remember(record):
            column = getattr(record, 'serial_number', None)
            if column is not None:
                listed_columns.add(column)
            serial_int = resolve_record_serial(record)
            if serial_int is not None:
                listed_ints.add(serial_int)

        def _listed(record) -> bool:
            column = getattr(record, 'serial_number', None)
            if column is not None and column in listed_columns:
                return True
            serial_int = resolve_record_serial(record)
            return serial_int is not None and serial_int in listed_ints

        for record in live_records:
            _remember(record)

        linked_ids = {r.certificate_id for r in revoked_serials
                      if getattr(r, 'certificate_id', None) is not None}
        linked = {}
        if linked_ids:
            linked = {c.id: c for c in Certificate.query.filter(
                Certificate.id.in_(linked_ids)).all()}

        kept = []
        for record in revoked_serials:
            if _listed(record):
                continue
            holder = linked.get(getattr(record, 'certificate_id', None))
            # Lifted revocation the row outlived; a renewed serial differs and stays
            if holder is not None and not holder.revoked and same_serial(record, holder):
                continue
            _remember(record)
            kept.append(record)
        return kept

    @staticmethod
    def purge_stale_revoked_serials(ca_id) -> int:
        """Delete this CA's revocation records whose ``valid_to`` has passed."""
        ca = db.session.get(CA, ca_id)
        if not ca:
            return 0
        from models.revoked_serial import RevokedSerial
        try:
            count = RevokedSerial.query.filter(
                RevokedSerial.caref == ca.refid,
                RevokedSerial.valid_to < utc_now(),
            ).delete(synchronize_session=False)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"CRL: purge of stale revoked serials failed for CA {ca_id}: {e}",
                         exc_info=True)
            return 0
        if count:
            logger.info(f"CRL: purged {count} stale revoked serial(s) for CA {ca_id}")
        return count

    @staticmethod
    def is_auto_delete_enabled():
        return _setting_enabled('crl_auto_delete_expired_revoked')

    @staticmethod
    def is_purge_stale_serials_enabled():
        return _setting_enabled('crl_auto_purge_stale_serials')

    @staticmethod
    def purge_expired_revoked_certificates(ca_id) -> int:
        """Delete this CA's revoked certificates whose ``valid_to`` has passed,
        through the deletion service; a row without ``valid_to`` is kept."""
        ca = db.session.get(CA, ca_id)
        if not ca:
            return 0
        from services.cert.service import CertificateService
        cert_ids = [row.id for row in Certificate.query.with_entities(Certificate.id).filter(
            Certificate.caref == ca.refid,
            Certificate.revoked == True,  # noqa: E712
            Certificate.valid_to.isnot(None),
            Certificate.valid_to < utc_now(),
        ).order_by(Certificate.id).all()]
        deleted = 0
        for cert_id in cert_ids:
            try:
                if CertificateService.delete_certificate(cert_id, username='system'):
                    deleted += 1
            except Exception as e:
                db.session.rollback()
                logger.error(f"CRL: could not delete expired revoked certificate {cert_id}: {e}",
                             exc_info=True)
        if deleted:
            logger.info(f"CRL: deleted {deleted} expired revoked certificate(s) of CA {ca_id}")
        return deleted

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
