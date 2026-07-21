"""CRL-based revocation sync for Microsoft CA connections (#185).

Pulls the CA's CRL and marks UCM-known certificates revoked when they are
revoked CA-side. Strictly one-way (CA → UCM): a certificate revoked locally
in UCM is never un-revoked, and nothing is pushed to the CA.
"""
import base64
import logging
import tempfile
import os

from cryptography import x509

from models import db, Certificate
from models.msca import MicrosoftCA, MSCARequest
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

# Invert the UCM-string → ReasonFlags map used by CRL generation so both
# directions speak the same reason vocabulary.
from services.crl._constants import REASON_MAP
_REASON_FLAG_TO_UCM = {flag: name for name, flag in REASON_MAP.items()}


class MicrosoftCACRLSyncMixin:

    @staticmethod
    def sync_crl(msca_id, username='system'):
        """Fetch the connection's CRL and revoke matching UCM certificates.

        Returns a summary dict:
        {status, crl_url, crl_entries, checked, revoked, certs: [...]}
        Raises ValueError on configuration/fetch/verification problems.
        """
        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            raise ValueError('Connection not found')

        try:
            crl_url = MicrosoftCACRLSyncMixin._resolve_crl_url(msca)
            crl = MicrosoftCACRLSyncMixin._fetch_crl(msca, crl_url)
            MicrosoftCACRLSyncMixin._verify_crl(msca, crl)

            revoked_entries = {}
            for entry in crl:
                reason = 'unspecified'
                try:
                    ext = entry.extensions.get_extension_for_class(x509.CRLReason)
                    reason = _REASON_FLAG_TO_UCM.get(ext.value.reason, 'unspecified')
                except x509.ExtensionNotFound:
                    pass
                revoked_entries[entry.serial_number] = (
                    entry.revocation_date_utc.replace(tzinfo=None),
                    reason,
                )

            candidates = MicrosoftCACRLSyncMixin._connection_certificates(msca)
            newly_revoked = []
            for cert in candidates:
                try:
                    serial_int = int(cert.serial_number, 16)
                except (TypeError, ValueError):
                    continue
                if serial_int not in revoked_entries:
                    continue
                revoked_at, reason = revoked_entries[serial_int]
                # removeFromCRL means the hold was lifted CA-side; UCM only
                # syncs revocations, so skip rather than revoke.
                if reason == 'removeFromCRL':
                    continue
                cert.revoked = True
                cert.revoked_at = revoked_at
                cert.revoke_reason = reason
                newly_revoked.append(cert)

            summary = {
                'status': 'success',
                'crl_url': crl_url,
                'crl_entries': len(revoked_entries),
                'checked': len(candidates),
                'revoked': len(newly_revoked),
                'certs': [
                    {'id': c.id, 'subject_cn': c.subject_cn, 'serial_number': c.serial_number,
                     'revoke_reason': c.revoke_reason}
                    for c in newly_revoked
                ],
            }

            # Snapshot payloads BEFORE emit: bus subscribers may commit and
            # expire the ORM instances.
            revoked_snapshots = [
                (c.to_dict(), c.revoke_reason, c.caref) for c in newly_revoked
            ]

            msca.last_crl_sync_at = utc_now()
            msca.last_crl_sync_result = (
                f"success: {summary['revoked']} revoked / {summary['checked']} checked"
            )
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise

            # Purge any cached OCSP "good" responses for the certs just marked
            # revoked, so the responder stops serving stale good status before
            # nextUpdate (RFC 6960 §2.2). Same step every other revoke path runs.
            try:
                from services.ocsp_service import OCSPService
                for cert in newly_revoked:
                    OCSPService.invalidate_cached_responses(cert.serial_number)
            except Exception as exc:
                logger.warning(f"OCSP cache invalidation after MSCA CRL sync failed: {exc}")

            from services.audit_service import AuditService
            AuditService.log_action(
                action='msca.crl_sync',
                resource_type='microsoft_ca',
                resource_id=msca.id,
                resource_name=msca.name,
                details=(
                    f"CRL sync: {summary['revoked']} certificate(s) revoked "
                    f"({summary['checked']} checked, {summary['crl_entries']} CRL entries)"
                ),
                success=True,
                username=username,
            )

            from services.webhook_service import emit_cert_revoked
            for snapshot, reason, caref in revoked_snapshots:
                emit_cert_revoked(snapshot, reason=reason, ca_refid=caref,
                                  actor=f'crl-sync:{msca.name}')

            if newly_revoked:
                logger.info(
                    f"MS CA '{msca.name}' CRL sync revoked {len(newly_revoked)} certificate(s)"
                )
            return summary

        except Exception as e:
            db.session.rollback()
            msca.last_crl_sync_at = utc_now()
            msca.last_crl_sync_result = f'failed: {str(e)[:200]}'
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
            raise

    # --- Internals ---------------------------------------------------------

    @staticmethod
    def _connection_certificates(msca):
        """Non-revoked issued certs UCM knows for this connection."""
        ids = {
            row[0] for row in
            db.session.query(MSCARequest.cert_id)
            .filter(MSCARequest.msca_id == msca.id, MSCARequest.cert_id.isnot(None))
            .all()
        }
        query = Certificate.query.filter(
            Certificate.revoked.isnot(True),
            Certificate.crt.isnot(None),
            Certificate.serial_number.isnot(None),
        )
        if ids:
            query = query.filter(
                db.or_(
                    Certificate.id.in_(ids),
                    Certificate.imported_from == f'msca:{msca.name}',
                )
            )
        else:
            query = query.filter(Certificate.imported_from == f'msca:{msca.name}')
        return query.all()

    @staticmethod
    def _resolve_crl_url(msca):
        """Explicit crl_url, else the http(s) CDP of a cert this CA issued."""
        if msca.crl_url:
            return msca.crl_url

        certs = MicrosoftCACRLSyncMixin._connection_certificates(msca)
        for cert in sorted(certs, key=lambda c: c.id, reverse=True):
            try:
                pem = base64.b64decode(cert.crt)
                cert_obj = x509.load_pem_x509_certificate(pem)
                cdp = cert_obj.extensions.get_extension_for_class(
                    x509.CRLDistributionPoints
                )
                for dp in cdp.value:
                    for name in (dp.full_name or []):
                        if isinstance(name, x509.UniformResourceIdentifier) and \
                                name.value.lower().startswith(('http://', 'https://')):
                            return name.value
            except (x509.ExtensionNotFound, ValueError):
                continue
            except Exception as e:
                logger.debug(f"CDP parse failed for cert {cert.id}: {e}")
                continue

        raise ValueError(
            'No CRL URL: set one on the connection, or ensure certificates issued '
            'by this CA carry an http(s) CRL Distribution Point'
        )

    @staticmethod
    def _fetch_crl(msca, crl_url):
        """Download and parse the CRL (DER or PEM), SSRF-pinned."""
        from utils.ssrf_protection import safe_request_get

        verify = True
        cafile = None
        try:
            if not msca.verify_ssl:
                verify = False
            elif msca.ca_bundle:
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pem', mode='w')
                tmp.write(msca.ca_bundle)
                tmp.close()
                cafile = tmp.name
                verify = cafile

            resp = safe_request_get(crl_url, verify=verify)
            if resp.status_code != 200:
                raise ValueError(f'CRL fetch failed: HTTP {resp.status_code}')
            data = resp.content
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f'CRL fetch failed: {e}')
        finally:
            if cafile:
                try:
                    os.unlink(cafile)
                except OSError:
                    pass

        try:
            if b'-----BEGIN X509 CRL-----' in data:
                return x509.load_pem_x509_crl(data)
            return x509.load_der_x509_crl(data)
        except Exception as e:
            raise ValueError(f'CRL is not parseable (DER/PEM): {e}')

    @staticmethod
    def _verify_crl(msca, crl):
        """Verify the CRL signature against the connection's CA certificate.

        The CA cert is fetched through the authenticated connector channel;
        without a verifiable signature the CRL is rejected (a forged CRL could
        mass-revoke certificates in UCM)."""
        from .connection import MicrosoftCAConnectionMixin

        client = None
        try:
            client = MicrosoftCAConnectionMixin._get_client(msca)
            ca_cert_raw = client.get_ca_cert(encoding='b64')
        except Exception as e:
            raise ValueError(f'Cannot fetch CA certificate to verify the CRL: {e}')
        finally:
            if client:
                MicrosoftCAConnectionMixin._cleanup_client(client)

        if isinstance(ca_cert_raw, bytes):
            ca_cert_raw = ca_cert_raw.decode('utf-8', errors='replace')
        try:
            if '-----BEGIN CERTIFICATE-----' in ca_cert_raw:
                ca_cert = x509.load_pem_x509_certificate(ca_cert_raw.encode())
            else:
                ca_cert = x509.load_der_x509_certificate(
                    base64.b64decode(ca_cert_raw.replace('\r', '').replace('\n', ''))
                )
        except Exception as e:
            raise ValueError(f'CA certificate is not parseable: {e}')

        if not crl.is_signature_valid(ca_cert.public_key()):
            raise ValueError('CRL signature verification failed against the CA certificate')


def scheduled_msca_crl_sync():
    """Scheduler entry point: sync every enabled connection that opted in."""
    connections = MicrosoftCA.query.filter_by(enabled=True, crl_sync_enabled=True).all()
    if not connections:
        return
    for msca in connections:
        try:
            summary = MicrosoftCACRLSyncMixin.sync_crl(msca.id, username='scheduler')
            logger.info(
                f"MS CA '{msca.name}' scheduled CRL sync: "
                f"{summary['revoked']} revoked / {summary['checked']} checked"
            )
        except Exception as e:
            logger.error(f"MS CA '{msca.name}' scheduled CRL sync failed: {e}")
