import logging
from typing import Optional
from models import db
from models.msca import MicrosoftCA, MSCARequest
from utils.datetime_utils import utc_now
from .connection import MicrosoftCAConnectionMixin
from .requests import MicrosoftCARequestsMixin

logger = logging.getLogger(__name__)


class MicrosoftCACertsMixin:

    @staticmethod
    def get_ca_cert(msca_id):
        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            return None

        client = None
        try:
            client = MicrosoftCAConnectionMixin._get_client(msca)
            ca_cert_pem = client.get_ca_cert(encoding='b64')
            if isinstance(ca_cert_pem, bytes):
                ca_cert_pem = ca_cert_pem.decode('utf-8', errors='replace')
            return ca_cert_pem
        except Exception as e:
            logger.error(f"Failed to get CA cert from '{msca.name}': {e}")
            raise
        finally:
            if client:
                MicrosoftCAConnectionMixin._cleanup_client(client)

    @staticmethod
    def submit_csr(msca_id, csr_pem, template,
                   csr_id=None, submitted_by=None,
                   enrollee_name=None, enrollee_upn=None):
        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            raise ValueError('Connection not found')

        if not msca.enabled:
            raise ValueError('Microsoft CA connection is disabled')

        client = None
        try:
            client = MicrosoftCAConnectionMixin._get_client(msca)

            eobo_attributes = None
            if enrollee_name or enrollee_upn:
                parts = []
                if enrollee_name:
                    parts.append(f"EnrolleeObjectName:{enrollee_name}")
                if enrollee_upn:
                    parts.append(f"EnrolleePrincipalName:{enrollee_upn}")
                eobo_attributes = "\r\n".join(parts) + "\r\n"
                logger.info(
                    f"EOBO enrollment for '{enrollee_name or enrollee_upn}' via MS CA '{msca.name}'"
                )

            try:
                cert_pem = client.get_cert(csr_pem, template, encoding='b64',
                                           attributes=eobo_attributes)

                if isinstance(cert_pem, bytes):
                    cert_pem = cert_pem.decode('utf-8', errors='replace')

                try:
                    request = MSCARequest(
                        msca_id=msca_id,
                        csr_id=csr_id,
                        template=template,
                        status='issued',
                        submitted_at=utc_now(),
                        issued_at=utc_now(),
                        cert_pem=cert_pem,
                        submitted_by=submitted_by,
                        enrollee_name=enrollee_name,
                        enrollee_upn=enrollee_upn,
                    )
                    db.session.add(request)
                    db.session.commit()
                except Exception as db_err:
                    db.session.rollback()
                    logger.error(f"Failed to save issued cert: {db_err}")
                    raise

                logger.info(
                    f"CSR signed by MS CA '{msca.name}' (auto-approved), template={template}"
                )
                return {
                    'status': 'issued',
                    'request_id': request.id,
                    'cert_pem': cert_pem,
                }

            except Exception as submit_err:
                # Locale-independent classification. certsrv only understands
                # the English "Certificate Pending" page, so on a localized
                # AD CS (e.g. French) it raises RequestDenied for a genuinely
                # pending request — which UCM used to surface as a 400. The
                # helper keys off certsrv's locale-independent HTML markers.
                status, ms_request_id = MicrosoftCARequestsMixin._classify_certsrv_error(submit_err)
                is_pending = status == 'pending'
                is_denied = status == 'denied'

                if is_pending:
                    try:
                        req = MSCARequest(
                            msca_id=msca_id,
                            csr_id=csr_id,
                            request_id=ms_request_id,
                            template=template,
                            status='pending',
                            disposition_message=str(submit_err)[:500],
                            submitted_at=utc_now(),
                            submitted_by=submitted_by,
                            enrollee_name=enrollee_name,
                            enrollee_upn=enrollee_upn,
                        )
                        db.session.add(req)
                        db.session.commit()
                    except Exception as db_err:
                        db.session.rollback()
                        logger.error(f"Failed to save pending request: {db_err}")

                    logger.info(
                        f"CSR submitted to MS CA '{msca.name}' (pending approval), "
                        f"ms_request_id={ms_request_id}, template={template}"
                    )
                    return {
                        'status': 'pending',
                        'request_id': getattr(req, 'id', None),
                        'ms_request_id': ms_request_id,
                        'message': 'Request pending manager approval',
                    }

                if is_denied:
                    try:
                        req = MSCARequest(
                            msca_id=msca_id,
                            csr_id=csr_id,
                            template=template,
                            status='denied',
                            error_message=str(submit_err)[:500],
                            submitted_at=utc_now(),
                            submitted_by=submitted_by,
                            enrollee_name=enrollee_name,
                            enrollee_upn=enrollee_upn,
                        )
                        db.session.add(req)
                        db.session.commit()
                    except Exception as db_err:
                        db.session.rollback()
                        logger.error(f"Failed to save denied request: {db_err}")
                    raise ValueError(f"Certificate request denied: {submit_err}")

                logger.error(f"MS CA sign failed for '{msca.name}': {submit_err}", exc_info=True)
                try:
                    req = MSCARequest(
                        msca_id=msca_id,
                        csr_id=csr_id,
                        template=template,
                        status='failed',
                        error_message=str(submit_err)[:500],
                        submitted_at=utc_now(),
                        submitted_by=submitted_by,
                        enrollee_name=enrollee_name,
                        enrollee_upn=enrollee_upn,
                    )
                    db.session.add(req)
                    db.session.commit()
                except Exception as db_err:
                    db.session.rollback()
                    logger.error(f"Failed to save failed request: {db_err}")
                raise

        finally:
            if client:
                MicrosoftCAConnectionMixin._cleanup_client(client)
