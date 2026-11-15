import logging
import re
from typing import Optional
from models import db
from models.msca import MicrosoftCA, MSCARequest
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class MSCAImportError(RuntimeError):
    """The CA issued the certificate but UCM could not store it."""


class MSCASignedElsewhere(RuntimeError):
    """The CSR row already holds a certificate the Microsoft CA did not issue."""


# Terminal state of a request whose CSR received a certificate from another source
SUPERSEDED = 'superseded'
SUPERSEDED_MESSAGE = 'The CSR was signed elsewhere; the Microsoft CA request is closed'


def holds_foreign_certificate(row):
    """True when the row carries a certificate that no Microsoft CA connection issued."""
    return bool(row is not None and row.crt and row.source != 'msca'
                and not (row.imported_from or '').startswith('msca:'))


def msca_may_write_clause():
    """SQL twin of ``not holds_foreign_certificate``: the row has no certificate, or one
    a Microsoft CA issued (a renewal replaces it in place)."""
    from models import Certificate
    return db.or_(Certificate.crt.is_(None), Certificate.crt == '',
                  Certificate.source == 'msca', Certificate.imported_from.like('msca:%'))


def supersede(req_ids, *, username=None, commit=True):
    """Close the given open requests as superseded, audited under *username* (else the
    request's user, else 'system'); returns how many changed. Rides the caller's
    transaction when ``commit`` is False."""
    from flask import g, has_request_context
    from services.audit.staging import stage_audit_entry
    if username is None and has_request_context():
        username = getattr(getattr(g, 'current_user', None), 'username', None)
    username = username or 'system'
    closed = 0
    for req in MSCARequest.query.filter(MSCARequest.id.in_(list(req_ids))).all():
        changed = (MSCARequest.query
                   .filter(MSCARequest.id == req.id, MSCARequest.cert_id.is_(None),
                           MSCARequest.status.in_(('submitted', 'pending')))
                   .update({MSCARequest.status: SUPERSEDED,
                            MSCARequest.error_message: 'CSR signed elsewhere'},
                           synchronize_session=False))
        if changed != 1:
            continue
        closed += 1
        msca = db.session.get(MicrosoftCA, req.msca_id)
        stage_audit_entry(action='msca.request_superseded', resource_type='microsoft_ca',
                          resource_id=str(req.msca_id), resource_name=msca.name if msca else None,
                          username=username,
                          details=f"RequestId={req.request_id} csr_id={req.csr_id}: CSR signed elsewhere")
        logger.info(f"MS CA request RequestId={req.request_id} closed: its CSR (id={req.csr_id}) "
                    f"was signed elsewhere")
    if commit:
        db.session.commit()
    return closed


def supersede_for_csr(csr_id, *, username=None, commit=True):
    """Close the open Microsoft CA requests of a CSR that just received a certificate."""
    ids = [rid for (rid,) in db.session.query(MSCARequest.id).filter(
        MSCARequest.csr_id == csr_id, MSCARequest.cert_id.is_(None),
        MSCARequest.status.in_(('submitted', 'pending')))]
    return supersede(ids, username=username, commit=commit) if ids else 0


class MicrosoftCARequestsMixin:

    @staticmethod
    def check_request(msca_id, request_id):
        from .connection import MicrosoftCAConnectionMixin

        req = db.session.get(MSCARequest, request_id)
        if not req or req.msca_id != msca_id:
            raise ValueError('Request not found')

        if req.status in ('issued', SUPERSEDED):
            return req.to_dict()

        if not req.request_id:
            return req.to_dict()

        if not req.cert_id and req.csr_id:
            from models import Certificate
            if holds_foreign_certificate(db.session.get(Certificate, req.csr_id)):
                supersede([req.id])
                db.session.refresh(req)
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

            if not req.cert_id:
                # Claim + import in one step, shared with the CA panel and the inventory;
                # a deleted CSR (csr_id None) imports into a new certificate row
                from .ca_control import MicrosoftCACAControlMixin
                try:
                    MicrosoftCACAControlMixin.complete_request(msca, req, cert_pem)
                except Exception as imp_err:
                    db.session.rollback()
                    raise MSCAImportError(str(imp_err)) from imp_err
                db.session.refresh(req)
                return req.to_dict()
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

        except MSCAImportError:
            raise
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
