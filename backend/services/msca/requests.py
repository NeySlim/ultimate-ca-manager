import logging
import re
from typing import Optional
from models import db
from models.msca import MicrosoftCA, MSCARequest
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class MicrosoftCARequestsMixin:

    @staticmethod
    def check_request(msca_id, request_id):
        from .connection import MicrosoftCAConnectionMixin

        req = db.session.get(MSCARequest, request_id)
        if not req or req.msca_id != msca_id:
            raise ValueError('Request not found')

        if req.status == 'issued':
            return req.to_dict()

        if not req.request_id:
            return req.to_dict()

        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            raise ValueError('Connection not found')

        client = None
        try:
            client = MicrosoftCAConnectionMixin._get_client(msca)
            cert_pem = client.get_existing_cert(req.request_id, encoding='b64')
            if isinstance(cert_pem, bytes):
                cert_pem = cert_pem.decode('utf-8', errors='replace')

            req.status = 'issued'
            req.issued_at = utc_now()
            req.cert_pem = cert_pem
            try:
                db.session.commit()
            except Exception as db_err:
                db.session.rollback()
                logger.error(f"Failed to persist issued status for request {req.request_id}: {db_err}")
                raise

            logger.info(
                f"Pending request {req.request_id} on '{msca.name}' is now issued"
            )
            return req.to_dict()

        except Exception as e:
            # Locale-independent classification: a French/localized AD CS
            # returns generic error text for a still-pending request, which the
            # old string matching mistook for a hard failure (500 on poll).
            status, _rid = MicrosoftCARequestsMixin._classify_certsrv_error(e)
            if status == 'pending':
                return req.to_dict()
            elif status == 'denied':
                req.status = 'denied'
                req.error_message = str(e)[:500]
                try:
                    db.session.commit()
                except Exception as db_err:
                    db.session.rollback()
                    logger.error(f"Failed to persist denied status for request {req.request_id}: {db_err}")
                return req.to_dict()
            else:
                logger.error(f"Error checking request {req.request_id}: {e}")
                raise
        finally:
            if client:
                MicrosoftCAConnectionMixin._cleanup_client(client)

    @staticmethod
    def _extract_request_id(error_message):
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
    def _certsrv_response_html(err):
        """Best-effort extraction of the raw ADCS HTML carried by a certsrv error."""
        resp = getattr(err, 'response', None)
        if isinstance(resp, str):
            return resp
        if resp is not None:
            return getattr(resp, 'text', '') or ''
        return ''

    @staticmethod
    def _classify_certsrv_error(err):
        """Classify a certsrv exception in a locale-independent way.

        The certsrv library recognizes only the *English* "Certificate Pending"
        page, so against a localized AD CS (e.g. French) it misclassifies a
        pending submission as RequestDenied, and a poll of a still-pending
        request as a generic failure. The certsrv HTML tags pages with
        locale-independent element ids and numeric disposition codes, which we
        key off instead of the translated prose:

        - ``certfnsh.asp`` pending page carries ``ID=locInfoReqID`` (+ the id).
        - ``certnew.cer`` fetch of a pending request is an error page whose
          disposition code (``ID=locDispSpacer``) is 5 (under submission);
          code 2 is denied.

        Returns ``(status, request_id)`` with status in
        {'pending', 'denied', 'error'}; request_id may be None.
        """
        msg = str(err)
        lower = msg.lower()
        html = MicrosoftCARequestsMixin._certsrv_response_html(err)

        is_pending = 'pending' in lower or 'taken under submission' in lower
        try:
            import certsrv as _certsrv
            if hasattr(_certsrv, 'CertificatePendingException'):
                is_pending = is_pending or isinstance(
                    err, _certsrv.CertificatePendingException
                )
        except ImportError:
            pass

        request_id = None
        if html:
            if 'locinforeqid' in html.lower():
                is_pending = True
                m = re.search(r'locInfoReqID.*?(\d+)', html, re.IGNORECASE | re.DOTALL)
                if m:
                    request_id = int(m.group(1))
            disp = re.search(r'(\d+)\s*<LocID\s+ID=locDispSpacer', html, re.IGNORECASE)
            if disp:
                code = int(disp.group(1))
                if code == 5:
                    is_pending = True
                elif code == 2 and not is_pending:
                    return 'denied', None

        if is_pending:
            if request_id is None:
                request_id = MicrosoftCARequestsMixin._extract_request_id(msg)
            return 'pending', request_id
        if 'denied' in lower:
            return 'denied', None
        return 'error', None

    @staticmethod
    def get_pending_requests(msca_id=None):
        query = MSCARequest.query.filter_by(status='pending')
        if msca_id:
            query = query.filter_by(msca_id=msca_id)
        return [r.to_dict() for r in query.order_by(MSCARequest.submitted_at.desc()).all()]

    @staticmethod
    def get_enabled_connections():
        return [
            msca.to_dict()
            for msca in MicrosoftCA.query.filter_by(enabled=True).order_by(MicrosoftCA.name).all()
        ]
