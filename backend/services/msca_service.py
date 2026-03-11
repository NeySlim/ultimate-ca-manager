"""
Microsoft AD CS Service
Handles communication with Microsoft Certificate Authority via certsrv Web Enrollment.
Supports three authentication methods: Client Certificate (mTLS), Kerberos, Basic Auth.
"""

import base64
import logging
import tempfile
import os
from datetime import datetime
from typing import Optional

from models import db
from models.msca import MicrosoftCA, MSCARequest

logger = logging.getLogger(__name__)


class MicrosoftCAService:
    """Service for interacting with Microsoft AD CS via certsrv"""

    @staticmethod
    def _get_client(msca: MicrosoftCA):
        """Create a certsrv client instance for the given MS CA connection"""
        import certsrv

        server = msca.server
        ca_name = msca.ca_name or ''

        # SSL verification
        verify = True
        if not msca.verify_ssl:
            verify = False
        elif msca.ca_bundle:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pem', mode='w')
            tmp.write(msca.ca_bundle)
            tmp.close()
            verify = tmp.name

        try:
            if msca.auth_method == 'certificate':
                cert_file = tempfile.NamedTemporaryFile(
                    delete=False, suffix='.pem', mode='w'
                )
                cert_file.write(msca.client_cert_pem or '')
                cert_file.close()

                key_file = tempfile.NamedTemporaryFile(
                    delete=False, suffix='.pem', mode='w'
                )
                key_file.write(msca.client_key_pem or '')
                key_file.close()

                client = certsrv.Certsrv(
                    server=server,
                    cafile=ca_name,
                    auth_method='cert',
                    cert=(cert_file.name, key_file.name),
                    verify=verify,
                )
                # Store temp file paths for cleanup
                client._temp_files = [cert_file.name, key_file.name]

            elif msca.auth_method == 'kerberos':
                try:
                    from requests_kerberos import HTTPKerberosAuth, OPTIONAL
                except ImportError:
                    raise RuntimeError(
                        "requests-kerberos package not installed. "
                        "Install with: pip install requests-kerberos"
                    )

                if msca.kerberos_keytab_path:
                    os.environ['KRB5_KTNAME'] = msca.kerberos_keytab_path
                if msca.kerberos_principal:
                    os.environ['KRB5_CLIENT_KTNAME'] = msca.kerberos_keytab_path or ''

                client = certsrv.Certsrv(
                    server=server,
                    cafile=ca_name,
                    auth_method='ntlm',  # certsrv uses NTLM/Negotiate wrapper
                    username='',
                    password='',
                    verify=verify,
                )
                # Override auth with Kerberos
                client.session.auth = HTTPKerberosAuth(
                    mutual_authentication=OPTIONAL
                )
                client._temp_files = []

            elif msca.auth_method == 'basic':
                client = certsrv.Certsrv(
                    server=server,
                    cafile=ca_name,
                    auth_method='basic',
                    username=msca.username or '',
                    password=msca.password or '',
                    verify=verify,
                )
                client._temp_files = []

            else:
                raise ValueError(f"Unsupported auth method: {msca.auth_method}")

            # Add CA bundle temp file for cleanup
            if isinstance(verify, str) and verify != True:
                client._temp_files.append(verify)

            return client

        except Exception:
            # Cleanup temp files on error
            if isinstance(verify, str):
                try:
                    os.unlink(verify)
                except OSError:
                    pass
            raise

    @staticmethod
    def _cleanup_client(client):
        """Remove temporary files created for certsrv client"""
        for f in getattr(client, '_temp_files', []):
            try:
                os.unlink(f)
            except OSError:
                pass

    @staticmethod
    def test_connection(msca_id: int) -> dict:
        """Test connectivity and authentication to MS CA"""
        msca = MicrosoftCA.query.get(msca_id)
        if not msca:
            return {'success': False, 'error': 'Connection not found'}

        client = None
        try:
            client = MicrosoftCAService._get_client(msca)
            # Try to get CA info - this validates auth + connectivity
            ca_cert = client.get_ca_cert()

            msca.last_test_at = datetime.utcnow()
            msca.last_test_result = 'success'
            db.session.commit()

            return {
                'success': True,
                'ca_name': msca.ca_name or msca.server,
                'ca_cert_available': ca_cert is not None,
            }
        except Exception as e:
            logger.error(f"MS CA connection test failed for '{msca.name}': {e}")
            msca.last_test_at = datetime.utcnow()
            msca.last_test_result = f'failed: {str(e)[:200]}'
            db.session.commit()
            return {'success': False, 'error': str(e)}
        finally:
            if client:
                MicrosoftCAService._cleanup_client(client)

    @staticmethod
    def list_templates(msca_id: int) -> list:
        """Fetch available certificate templates from MS CA"""
        msca = MicrosoftCA.query.get(msca_id)
        if not msca:
            raise ValueError('Connection not found')

        client = None
        try:
            client = MicrosoftCAService._get_client(msca)
            templates = client.get_cert_templates()
            return sorted(templates) if templates else []
        except Exception as e:
            logger.error(f"Failed to list templates for '{msca.name}': {e}")
            raise
        finally:
            if client:
                MicrosoftCAService._cleanup_client(client)

    @staticmethod
    def get_ca_cert(msca_id: int) -> Optional[str]:
        """Retrieve the CA certificate from MS CA (PEM)"""
        msca = MicrosoftCA.query.get(msca_id)
        if not msca:
            return None

        client = None
        try:
            client = MicrosoftCAService._get_client(msca)
            ca_cert_pem = client.get_ca_cert(encoding='b64')
            return ca_cert_pem
        except Exception as e:
            logger.error(f"Failed to get CA cert from '{msca.name}': {e}")
            raise
        finally:
            if client:
                MicrosoftCAService._cleanup_client(client)

    @staticmethod
    def submit_csr(msca_id: int, csr_pem: str, template: str,
                   csr_id: int = None, submitted_by: str = None) -> dict:
        """Submit a CSR to MS CA for signing

        Args:
            msca_id: Microsoft CA connection ID
            csr_pem: CSR in PEM format
            template: Certificate template name
            csr_id: Optional UCM CSR ID for tracking
            submitted_by: Username who submitted

        Returns:
            dict with request info (request_id, status, cert if auto-approved)
        """
        msca = MicrosoftCA.query.get(msca_id)
        if not msca:
            raise ValueError('Connection not found')

        if not msca.enabled:
            raise ValueError('Microsoft CA connection is disabled')

        client = None
        try:
            client = MicrosoftCAService._get_client(msca)

            # Submit CSR - certsrv returns cert directly for auto-approved templates
            try:
                cert_pem = client.get_cert(csr_pem, template, encoding='b64')

                # Auto-approved: cert returned immediately
                request = MSCARequest(
                    msca_id=msca_id,
                    csr_id=csr_id,
                    template=template,
                    status='issued',
                    submitted_at=datetime.utcnow(),
                    issued_at=datetime.utcnow(),
                    cert_pem=cert_pem,
                    submitted_by=submitted_by,
                )
                db.session.add(request)
                db.session.commit()

                logger.info(f"CSR signed by MS CA '{msca.name}' (auto-approved), template={template}")
                return {
                    'status': 'issued',
                    'request_id': request.id,
                    'cert_pem': cert_pem,
                }

            except Exception as submit_err:
                err_str = str(submit_err).lower()
                # Check if it's a pending approval (disposition = 5 / "taken under submission")
                if 'pending' in err_str or 'taken under submission' in err_str:
                    # Extract request ID from error if possible
                    ms_request_id = MicrosoftCAService._extract_request_id(str(submit_err))

                    request = MSCARequest(
                        msca_id=msca_id,
                        csr_id=csr_id,
                        request_id=ms_request_id,
                        template=template,
                        status='pending',
                        disposition_message=str(submit_err)[:500],
                        submitted_at=datetime.utcnow(),
                        submitted_by=submitted_by,
                    )
                    db.session.add(request)
                    db.session.commit()

                    logger.info(
                        f"CSR submitted to MS CA '{msca.name}' (pending approval), "
                        f"ms_request_id={ms_request_id}, template={template}"
                    )
                    return {
                        'status': 'pending',
                        'request_id': request.id,
                        'ms_request_id': ms_request_id,
                        'message': 'Request pending manager approval',
                    }

                # Check if denied
                if 'denied' in err_str:
                    request = MSCARequest(
                        msca_id=msca_id,
                        csr_id=csr_id,
                        template=template,
                        status='denied',
                        error_message=str(submit_err)[:500],
                        submitted_at=datetime.utcnow(),
                        submitted_by=submitted_by,
                    )
                    db.session.add(request)
                    db.session.commit()
                    raise ValueError(f"Certificate request denied: {submit_err}")

                # Unknown error
                request = MSCARequest(
                    msca_id=msca_id,
                    csr_id=csr_id,
                    template=template,
                    status='failed',
                    error_message=str(submit_err)[:500],
                    submitted_at=datetime.utcnow(),
                    submitted_by=submitted_by,
                )
                db.session.add(request)
                db.session.commit()
                raise

        finally:
            if client:
                MicrosoftCAService._cleanup_client(client)

    @staticmethod
    def check_request(msca_id: int, request_id: int) -> dict:
        """Check status of a pending request"""
        req = MSCARequest.query.get(request_id)
        if not req or req.msca_id != msca_id:
            raise ValueError('Request not found')

        if req.status == 'issued':
            return req.to_dict()

        if not req.request_id:
            return req.to_dict()

        msca = MicrosoftCA.query.get(msca_id)
        if not msca:
            raise ValueError('Connection not found')

        client = None
        try:
            client = MicrosoftCAService._get_client(msca)
            # Try to retrieve the cert (will succeed if approved)
            cert_pem = client.get_existing_cert(req.request_id, encoding='b64')

            req.status = 'issued'
            req.issued_at = datetime.utcnow()
            req.cert_pem = cert_pem
            db.session.commit()

            logger.info(
                f"Pending request {req.request_id} on '{msca.name}' is now issued"
            )
            return req.to_dict()

        except Exception as e:
            err_str = str(e).lower()
            if 'pending' in err_str or 'taken under submission' in err_str:
                return req.to_dict()
            elif 'denied' in err_str:
                req.status = 'denied'
                req.error_message = str(e)[:500]
                db.session.commit()
                return req.to_dict()
            else:
                logger.error(f"Error checking request {req.request_id}: {e}")
                raise
        finally:
            if client:
                MicrosoftCAService._cleanup_client(client)

    @staticmethod
    def _extract_request_id(error_message: str) -> Optional[int]:
        """Try to extract MS CA request ID from error/response message"""
        import re
        match = re.search(r'request\s*(?:id|#)?\s*[=:]?\s*(\d+)', error_message, re.IGNORECASE)
        if match:
            return int(match.group(1))
        match = re.search(r'(\d+)', error_message)
        if match:
            val = int(match.group(1))
            if val > 0:
                return val
        return None

    @staticmethod
    def get_pending_requests(msca_id: int = None) -> list:
        """Get all pending requests, optionally filtered by MS CA"""
        query = MSCARequest.query.filter_by(status='pending')
        if msca_id:
            query = query.filter_by(msca_id=msca_id)
        return [r.to_dict() for r in query.order_by(MSCARequest.submitted_at.desc()).all()]

    @staticmethod
    def get_enabled_connections() -> list:
        """Get all enabled MS CA connections (for UI dynamic display)"""
        return [
            msca.to_dict()
            for msca in MicrosoftCA.query.filter_by(enabled=True).order_by(MicrosoftCA.name).all()
        ]
