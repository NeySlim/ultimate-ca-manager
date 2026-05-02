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
            client = MicrosoftCAConnectionMixin._get_client(msca)
            cert_pem = client.get_existing_cert(req.request_id, encoding='b64')
            if isinstance(cert_pem, bytes):
                cert_pem = cert_pem.decode('utf-8', errors='replace')

            req.status = 'issued'
            req.issued_at = utc_now()
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
