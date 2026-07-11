"""CA control operations for Microsoft CA connections (#185 phase C).

Pending-request management (list / approve / deny) and a CA health snapshot,
over the WinRM admin channel. Health is assembled from stable, locale-neutral
sources (a marker-tagged service query plus the CA certificate and CRL that
UCM already fetches) rather than parsing localized ``certutil -CAInfo`` text.
"""
import csv
import io
import logging
import re

from models import db
from models.msca import MicrosoftCA

logger = logging.getLogger(__name__)

_DISPOSITION_PENDING = 9

# certutil -view input columns for pending requests (English; CSV header is
# localized so we parse by position).
_PENDING_COLUMNS = "RequestId,RequesterName,CommonName,CertificateTemplate,SubmittedWhen"

_INT_RE = re.compile(r'^\d+$')


class MicrosoftCACAControlMixin:

    # --- Pending requests --------------------------------------------------

    @staticmethod
    def list_pending_requests(msca_id):
        """List certificate requests awaiting CA manager approval."""
        from .admin_channel import MicrosoftCAAdminChannelMixin, MSCAAdminChannelError

        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            raise MSCAAdminChannelError('Connection not found')
        if not MicrosoftCAAdminChannelMixin.admin_channel_available(msca):
            raise MSCAAdminChannelError('WinRM admin channel is not configured')

        config = MicrosoftCAAdminChannelMixin._config_arg(msca)
        restrict = f"Disposition={_DISPOSITION_PENDING}"
        script = (
            "$ErrorActionPreference='Stop';chcp 65001 | Out-Null;"
            f'certutil {config}-view -restrict "{restrict}" -out "{_PENDING_COLUMNS}" csv'
        )
        out = MicrosoftCAAdminChannelMixin._run_ps(msca, script)
        return MicrosoftCACAControlMixin._parse_pending_csv(out)

    @staticmethod
    def approve_request(msca_id, request_id, import_issued=True):
        """Approve (resubmit) a pending request; optionally import the issued cert."""
        from .admin_channel import MicrosoftCAAdminChannelMixin, MSCAAdminChannelError

        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            raise MSCAAdminChannelError('Connection not found')
        rid = MicrosoftCACAControlMixin._validate_request_id(request_id)
        config = MicrosoftCAAdminChannelMixin._config_arg(msca)
        script = (
            "$ErrorActionPreference='Stop';chcp 65001 | Out-Null;"
            f"certutil {config}-resubmit {rid}"
        )
        out = MicrosoftCAAdminChannelMixin._run_ps(msca, script)

        result = {'success': True, 'request_id': rid, 'output': out.strip()[-300:],
                  'imported_cert_id': None}

        # After approval the request is typically issued immediately; pull the
        # cert and import it so UCM tracks it.
        if import_issued:
            try:
                from .inventory import MicrosoftCAInventoryMixin
                pem = MicrosoftCAInventoryMixin._fetch_cert_pem(msca, rid)
                if pem and not MicrosoftCACAControlMixin._request_serial_known(msca, rid, pem):
                    cert = MicrosoftCAInventoryMixin._import_inventory_cert(
                        msca, rid, None, pem
                    )
                    db.session.commit()
                    result['imported_cert_id'] = cert.id
            except Exception as e:
                logger.warning(
                    f"MS CA '{msca.name}': approved request {rid} but import failed: {e}"
                )
                result['import_error'] = str(e)[:200]

        logger.info(f"MS CA '{msca.name}' approved pending request {rid}")
        return result

    @staticmethod
    def deny_request(msca_id, request_id):
        """Deny a pending request on the CA."""
        from .admin_channel import MicrosoftCAAdminChannelMixin, MSCAAdminChannelError

        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            raise MSCAAdminChannelError('Connection not found')
        rid = MicrosoftCACAControlMixin._validate_request_id(request_id)
        config = MicrosoftCAAdminChannelMixin._config_arg(msca)
        script = (
            "$ErrorActionPreference='Stop';chcp 65001 | Out-Null;"
            f"certutil {config}-deny {rid}"
        )
        out = MicrosoftCAAdminChannelMixin._run_ps(msca, script)
        logger.info(f"MS CA '{msca.name}' denied pending request {rid}")
        return {'success': True, 'request_id': rid, 'output': out.strip()[-300:]}

    # --- CA health ---------------------------------------------------------

    @staticmethod
    def ca_health(msca_id):
        """Assemble a CA health snapshot from locale-neutral sources."""
        from .admin_channel import MicrosoftCAAdminChannelMixin, MSCAAdminChannelError
        from .connection import MicrosoftCAConnectionMixin

        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            raise MSCAAdminChannelError('Connection not found')
        if not MicrosoftCAAdminChannelMixin.admin_channel_available(msca):
            raise MSCAAdminChannelError('WinRM admin channel is not configured')

        health = {'certsvc_status': None, 'ca_cert': None, 'crl': None,
                  'pending_count': None, 'warnings': []}

        # 1) Service status via a UCM-tagged marker (stable across locales).
        try:
            script = ("$ErrorActionPreference='SilentlyContinue';chcp 65001 | Out-Null;"
                      "$s=(Get-Service certsvc).Status;Write-Output \"UCM_CERTSVC=$s\"")
            out = MicrosoftCAAdminChannelMixin._run_ps(msca, script)
            m = re.search(r'UCM_CERTSVC=(\w+)', out)
            health['certsvc_status'] = m.group(1) if m else None
        except Exception as e:
            health['warnings'].append(f'service status unavailable: {str(e)[:120]}')

        # 2) CA certificate (fetched through the connector, parsed locally).
        try:
            from cryptography import x509
            from utils.datetime_utils import utc_now
            import base64
            client = MicrosoftCAConnectionMixin._get_client(msca)
            try:
                ca_pem = client.get_ca_cert(encoding='b64')
            finally:
                MicrosoftCAConnectionMixin._cleanup_client(client)
            if isinstance(ca_pem, bytes):
                ca_pem = ca_pem.decode('utf-8', errors='replace')
            if '-----BEGIN CERTIFICATE-----' in ca_pem:
                ca_cert = x509.load_pem_x509_certificate(ca_pem.encode())
            else:
                ca_cert = x509.load_der_x509_certificate(
                    base64.b64decode(ca_pem.replace('\r', '').replace('\n', ''))
                )
            not_after = ca_cert.not_valid_after_utc.replace(tzinfo=None)
            days_left = (not_after - utc_now()).days
            health['ca_cert'] = {
                'subject': ca_cert.subject.rfc4514_string(),
                'not_after': not_after.isoformat(),
                'days_until_expiry': days_left,
            }
            if days_left < 90:
                health['warnings'].append(f'CA certificate expires in {days_left} days')
        except Exception as e:
            health['warnings'].append(f'CA certificate unavailable: {str(e)[:120]}')

        # 3) CRL freshness (reuse the CRL-sync fetcher + resolver).
        try:
            from .crl_sync import MicrosoftCACRLSyncMixin
            from utils.datetime_utils import utc_now
            crl_url = MicrosoftCACRLSyncMixin._resolve_crl_url(msca)
            crl = MicrosoftCACRLSyncMixin._fetch_crl(msca, crl_url)
            next_update = crl.next_update_utc.replace(tzinfo=None) if crl.next_update_utc else None
            health['crl'] = {
                'url': crl_url,
                'last_update': crl.last_update_utc.replace(tzinfo=None).isoformat() if crl.last_update_utc else None,
                'next_update': next_update.isoformat() if next_update else None,
                'revoked_count': sum(1 for _ in crl),
                'expired': bool(next_update and next_update < utc_now()),
            }
            if health['crl']['expired']:
                health['warnings'].append('CRL is past its next-update time')
        except Exception as e:
            health['warnings'].append(f'CRL unavailable: {str(e)[:120]}')

        # 4) Pending request count (cheap; pending sets are small).
        try:
            health['pending_count'] = len(
                MicrosoftCACAControlMixin.list_pending_requests(msca_id)
            )
        except Exception as e:
            health['warnings'].append(f'pending count unavailable: {str(e)[:120]}')

        return health

    # --- Internals ---------------------------------------------------------

    @staticmethod
    def _validate_request_id(request_id):
        from .admin_channel import MSCAAdminChannelError
        s = str(request_id).strip()
        if not _INT_RE.match(s):
            raise MSCAAdminChannelError(f'Invalid request id: {request_id!r}')
        return int(s)

    @staticmethod
    def _parse_pending_csv(text):
        """Parse pending-request CSV by column position (headers localized)."""
        rows = []
        for i, cols in enumerate(csv.reader(io.StringIO(text))):
            if i == 0:  # localized header
                continue
            if len(cols) < 5:
                continue
            rid = cols[0].strip()
            if not _INT_RE.match(rid):
                continue
            rows.append({
                'request_id': int(rid),
                'requester_name': cols[1].strip(),
                'subject_cn': cols[2].strip(),
                'template': cols[3].strip(),
                'submitted_when': cols[4].strip(),
            })
        return rows

    @staticmethod
    def _request_serial_known(msca, request_id, pem):
        """True if the just-issued cert's serial is already in UCM."""
        try:
            from cryptography import x509
            from .inventory import MicrosoftCAInventoryMixin
            serial = format(
                x509.load_pem_x509_certificate(pem.encode()).serial_number, 'x'
            )
            return serial.lower() in MicrosoftCAInventoryMixin._known_serials()
        except Exception:
            return False
