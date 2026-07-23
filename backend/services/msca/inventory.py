"""CA inventory sync for Microsoft CA connections (#185 phase B).

Imports certificates issued directly on the Windows CA (e.g. via native tools,
autoenrollment, or before UCM existed) into UCM's store, using the WinRM admin
channel + ``certutil -view``. Incremental by RequestId, plus a reconciliation
view (certs on the CA unknown to UCM, and UCM msca certs absent from the CA).
"""
import csv
import io
import logging
import re

from models import db, Certificate
from models.msca import MicrosoftCA, MSCARequest
from utils.datetime_utils import utc_now
from utils.serial_format import serial_to_int

logger = logging.getLogger(__name__)

# certutil disposition codes.
_DISPOSITION_ISSUED = 20
_DISPOSITION_REVOKED = 21

# certutil -view input column names (English; the CSV *header* is localized so
# we parse strictly by position, never by header text).
_VIEW_COLUMNS = "RequestId,SerialNumber,NotAfter,CertificateTemplate,CommonName"

_INT_RE = re.compile(r'^\d+$')
_HEX_RE = re.compile(r'^[0-9a-fA-F]+$')


class MicrosoftCAInventoryMixin:

    @staticmethod
    def inventory_sync(msca_id, username='system', full=False):
        """Import issued certs from the CA that UCM doesn't know yet.

        full=True rescans from RequestId 0 (ignores the high-water mark).
        Returns a summary dict.
        """
        from .admin_channel import MicrosoftCAAdminChannelMixin, MSCAAdminChannelError

        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            raise MSCAAdminChannelError('Connection not found')
        if not MicrosoftCAAdminChannelMixin.admin_channel_available(msca):
            raise MSCAAdminChannelError('WinRM admin channel is not configured')

        start_id = 0 if full else (msca.last_synced_request_id or 0)

        try:
            rows = MicrosoftCAInventoryMixin._list_issued(msca, start_id)
        except Exception as e:
            msca.last_inventory_sync_at = utc_now()
            msca.last_inventory_sync_result = f'failed: {str(e)[:200]}'
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            raise

        imported, skipped, failed = [], 0, 0
        max_request_id = start_id

        # Preload known serials (as ints) and CA request ids so dedup is O(1)
        # per row.
        known_serials = MicrosoftCAInventoryMixin._known_serial_ints()
        known_request_ids = MicrosoftCAInventoryMixin._known_request_ids(msca)

        for row in rows:
            req_id, serial, template, cn = row
            max_request_id = max(max_request_id, req_id)

            # Dedup level 1: this CA RequestId is already tracked by UCM
            # (exact link — covers certs signed through UCM itself).
            if req_id in known_request_ids:
                skipped += 1
                continue
            # Dedup level 2: serial already known. certutil -view displays the
            # serial with its byte pairs in reversed order on some AD CS
            # builds, so match both interpretations against UCM's store.
            variants = MicrosoftCAInventoryMixin._serial_int_variants(serial)
            if variants & known_serials:
                # Name what was skipped: the reversed-byte-order matching can
                # (rarely, on short/sequential serials) collide with a
                # genuinely distinct cert — a silent skip is undiagnosable.
                logger.info(
                    "MSCA inventory: skipping RequestId %s (serial %s, CN %r) "
                    "— serial already known in UCM", req_id, serial, cn,
                )
                skipped += 1
                continue
            known_serials |= variants  # avoid re-importing a dup within this run

            try:
                pem = MicrosoftCAInventoryMixin._fetch_cert_pem(msca, req_id)
                if not pem:
                    failed += 1
                    continue
                cert = MicrosoftCAInventoryMixin._import_inventory_cert(
                    msca, req_id, template, pem
                )
                imported.append({'id': cert.id, 'request_id': req_id,
                                 'serial_number': serial, 'subject_cn': cn})
            except Exception as e:
                failed += 1
                logger.warning(
                    f"MS CA '{msca.name}' inventory: failed to import RequestId={req_id}: {e}"
                )

        msca.last_synced_request_id = max(msca.last_synced_request_id or 0, max_request_id)
        msca.last_inventory_sync_at = utc_now()
        msca.last_inventory_sync_result = (
            f"success: {len(imported)} imported, {skipped} known, {failed} failed"
        )

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        # NB: intentionally NO per-cert cert_issued event here. An initial full
        # inventory can import thousands of pre-existing certs; emitting one
        # lifecycle event each would flood webhook/email subscribers. These
        # certs are catalogued, not freshly issued — the audit summary below is
        # the record of the sync.
        from services.audit_service import AuditService
        AuditService.log_action(
            action='msca.inventory_sync',
            resource_type='microsoft_ca',
            resource_id=msca.id,
            resource_name=msca.name,
            details=(f"Inventory sync: {len(imported)} imported, "
                     f"{skipped} known, {failed} failed "
                     f"(up to RequestId {max_request_id})"),
            success=True,
            username=username,
        )

        if imported:
            logger.info(
                f"MS CA '{msca.name}' inventory sync imported {len(imported)} certificate(s)"
            )
        return {
            'status': 'success',
            'imported': len(imported),
            'skipped': skipped,
            'failed': failed,
            'last_request_id': msca.last_synced_request_id,
            'certs': imported,
        }

    @staticmethod
    def reconcile_inventory(msca_id):
        """Compare the CA's issued set with UCM's known certs for this connection.

        Returns {ca_only: [...], ucm_only: [...]} — certificates present on the
        CA but not in UCM (import candidates), and UCM msca certs absent from
        the CA's issued list (e.g. removed CA-side). Read-only.
        """
        from .admin_channel import MicrosoftCAAdminChannelMixin, MSCAAdminChannelError

        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            raise MSCAAdminChannelError('Connection not found')
        if not MicrosoftCAAdminChannelMixin.admin_channel_available(msca):
            raise MSCAAdminChannelError('WinRM admin channel is not configured')

        ca_rows = MicrosoftCAInventoryMixin._list_issued(msca, 0)
        known_request_ids = MicrosoftCAInventoryMixin._known_request_ids(msca)
        ca_row_ids = {r[0] for r in ca_rows}

        ucm_certs = [
            c for c in MicrosoftCAInventoryMixin._ucm_connection_certs(msca)
            if c.serial_number
        ]
        ucm_ints = set()
        for c in ucm_certs:
            ucm_ints |= MicrosoftCAInventoryMixin._db_serial_variants(c.serial_number)

        # Map UCM cert id → CA RequestId (exact link, when known).
        req_ids_by_cert = {
            row[0]: row[1] for row in
            db.session.query(MSCARequest.cert_id, MSCARequest.request_id)
            .filter(MSCARequest.msca_id == msca.id,
                    MSCARequest.cert_id.isnot(None),
                    MSCARequest.request_id.isnot(None)).all()
        }

        # Serial matching handles both certutil byte orders (see inventory_sync).
        ca_only, ca_all_ints = [], set()
        for r in ca_rows:
            variants = MicrosoftCAInventoryMixin._serial_int_variants(r[1])
            ca_all_ints |= variants
            if r[0] in known_request_ids:
                continue
            if variants & ucm_ints:
                continue
            ca_only.append({'request_id': r[0], 'serial_number': r[1],
                            'template': r[2], 'subject_cn': r[3]})

        ucm_only = [
            {'id': c.id, 'serial_number': c.serial_number, 'subject_cn': c.subject_cn,
             'descr': c.descr}
            for c in ucm_certs
            if not (MicrosoftCAInventoryMixin._db_serial_variants(c.serial_number)
                    & ca_all_ints)
            and req_ids_by_cert.get(c.id) not in ca_row_ids
        ]
        return {
            'ca_total': len(ca_rows),
            'ucm_total': len(ucm_certs),
            'ca_only': sorted(ca_only, key=lambda x: x['request_id']),
            'ucm_only': ucm_only,
        }

    # --- Internals ---------------------------------------------------------

    @staticmethod
    def _list_issued(msca, start_request_id):
        """Return [(request_id:int, serial:str, template:str, cn:str), ...]."""
        from .admin_channel import MicrosoftCAAdminChannelMixin

        config = MicrosoftCAAdminChannelMixin._config_arg(msca)
        restrict = f"Disposition={_DISPOSITION_ISSUED},RequestId>={int(start_request_id)}"
        script = (
            "$ErrorActionPreference='Stop';chcp 65001 | Out-Null;"
            f'certutil {config}-view -restrict "{restrict}" -out "{_VIEW_COLUMNS}" csv'
        )
        out = MicrosoftCAAdminChannelMixin._run_ps(msca, script)
        return MicrosoftCAInventoryMixin._parse_view_csv(out)

    @staticmethod
    def _parse_view_csv(text):
        """Parse certutil CSV strictly by column position (headers are localized)."""
        rows = []
        reader = csv.reader(io.StringIO(text))
        for i, cols in enumerate(reader):
            if i == 0:  # localized header
                continue
            if len(cols) < 5:
                continue
            req_raw = cols[0].strip()
            if not _INT_RE.match(req_raw):
                continue
            serial = cols[1].strip().replace(':', '').lower()
            template = cols[3].strip()
            cn = cols[4].strip()
            rows.append((int(req_raw), serial, template, cn))
        return rows

    @staticmethod
    def _fetch_cert_pem(msca, request_id):
        """Retrieve a single issued certificate as PEM by RequestId."""
        from .admin_channel import MicrosoftCAAdminChannelMixin

        config = MicrosoftCAAdminChannelMixin._config_arg(msca)
        script = (
            "$ErrorActionPreference='Stop';chcp 65001 | Out-Null;"
            f'certutil {config}-view -restrict "RequestId={int(request_id)}" -out "RawCertificate"'
        )
        out = MicrosoftCAAdminChannelMixin._run_ps(msca, script)
        m = re.search(
            r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', out, re.S
        )
        return m.group(0) if m else None

    @staticmethod
    def _serial_int_variants(serial):
        """Integer interpretations of a certutil serial: as-is and with the
        byte pairs reversed (AD CS displays serials in reversed byte order in
        some certutil views, so a straight compare misses known certs).
        Returns a set of ints (empty for non-hex input)."""
        s = (serial or '').replace(':', '').strip().lower()
        if s.startswith('0x'):
            s = s[2:]
        if not s or not _HEX_RE.match(s):
            return set()
        if len(s) % 2:
            s = '0' + s
        pairs = [s[i:i + 2] for i in range(0, len(s), 2)]
        return {int(s, 16), int(''.join(reversed(pairs)), 16)}

    @staticmethod
    def _db_serial_variants(raw):
        """Integer interpretations of a DB-stored serial. Rows are a
        historical mix of decimal and hex strings, so ambiguous all-digit
        values are included under both readings."""
        s = (raw or '').replace(':', '').strip().lower()
        if s.startswith('0x'):
            s = s[2:]
        if not s:
            return set()
        out = set()
        n = serial_to_int(s)
        if n is not None:
            out.add(n)
        if _HEX_RE.match(s):
            out.add(int(s, 16))
        return out

    @staticmethod
    def _known_serial_ints():
        """Set of all known cert serials as integers (all interpretations)."""
        ints = set()
        for row in (db.session.query(Certificate.serial_number)
                    .filter(Certificate.serial_number.isnot(None)).all()):
            ints |= MicrosoftCAInventoryMixin._db_serial_variants(row[0])
        return ints

    @staticmethod
    def _known_request_ids(msca):
        """CA-side RequestIds already tracked by UCM for this connection."""
        return {
            row[0] for row in
            db.session.query(MSCARequest.request_id)
            .filter(MSCARequest.msca_id == msca.id,
                    MSCARequest.request_id.isnot(None)).all()
        }

    @staticmethod
    def _ucm_connection_certs(msca):
        ids = {
            row[0] for row in
            db.session.query(MSCARequest.cert_id)
            .filter(MSCARequest.msca_id == msca.id, MSCARequest.cert_id.isnot(None))
            .all()
        }
        query = Certificate.query.filter(Certificate.crt.isnot(None))
        if ids:
            return query.filter(
                db.or_(Certificate.id.in_(ids),
                       Certificate.imported_from == f'msca:{msca.name}')
            ).all()
        return query.filter(Certificate.imported_from == f'msca:{msca.name}').all()

    @staticmethod
    def _import_inventory_cert(msca, request_id, template, pem):
        """Create the MSCARequest + import the cert via the shared importer."""
        from api.v2.msca import _import_signed_cert

        req = MSCARequest(
            msca_id=msca.id,
            request_id=request_id,
            template=template or 'unknown',
            status='issued',
            submitted_at=utc_now(),
            issued_at=utc_now(),
            submitted_by='inventory',
        )
        db.session.add(req)
        db.session.flush()
        # csr=None → the importer creates a fresh Certificate row and links it
        # to this MSCARequest.
        _import_signed_cert(None, pem, msca, template or 'unknown', req.id)
        return db.session.get(Certificate, req.cert_id)


def scheduled_msca_inventory_sync():
    """Scheduler entry point: incremental inventory sync for opted-in connections."""
    connections = MicrosoftCA.query.filter_by(
        enabled=True, inventory_sync_enabled=True
    ).all()
    if not connections:
        return
    from .admin_channel import MicrosoftCAAdminChannelMixin
    for msca in connections:
        if not MicrosoftCAAdminChannelMixin.admin_channel_available(msca):
            continue
        try:
            summary = MicrosoftCAInventoryMixin.inventory_sync(msca.id, username='scheduler')
            logger.info(
                f"MS CA '{msca.name}' scheduled inventory sync: "
                f"{summary['imported']} imported, {summary['skipped']} known"
            )
        except Exception as e:
            logger.error(f"MS CA '{msca.name}' scheduled inventory sync failed: {e}")
