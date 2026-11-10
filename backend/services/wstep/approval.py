"""WSTEP requests held by a policy requiring approval (MS-WSTEP 3.1.4.2.1).

The client is answered with a pending RSTR carrying the approval request's
id as ``wstep:RequestID``, which it sends back with QueryTokenStatus; the
approval issues the certificate as the enrolment or renewal would have.
"""
import base64
import hashlib
import logging

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

from models import CA, Certificate, db
from services import protocol_approval
from services.protocol_approval import ProtocolRequestGone

logger = logging.getLogger(__name__)


def certificate_identity(cert) -> str:
    """The identity of a requester authenticated by its certificate."""
    return 'cert:' + hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest()


def make_gate(ca, *, operation, identity=None, extra=None):
    """The gate ``wstep_service.issue`` and the renewals call before signing.
    A renewal's identity is the certificate it renews."""
    def gate(*, csr, template, subject, san, signing_cert=None):
        requester = certificate_identity(signing_cert) if signing_cert is not None else identity
        cn_attrs = subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
        cn = str(cn_attrs[0].value) if cn_attrs else None
        if san is not None:
            dns = [n.value for n in san if isinstance(n, x509.DNSName)]
        else:
            dns = protocol_approval.csr_names(csr)[1]
        data = dict(extra or {}, operation=operation)
        if signing_cert is not None:
            data['renewal_of'] = signing_cert.public_bytes(Encoding.PEM).decode()
        return protocol_approval.gate_protocol_issuance(
            'wstep', ca=ca, template_id=getattr(template, 'id', None), cn=cn, san_list=dns,
            csr_pem=csr.public_bytes(Encoding.PEM).decode(), identity=requester,
            protocol_ref=protocol_approval.make_ref('wstep', operation, ca.id, requester,
                                                    protocol_approval.csr_ref(csr)),
            renewal=operation == 'renew', extra=data)
    return gate


def _issue(approval, data):
    from api.wstep_protocol import _validity_days
    from services.wstep import wstep_service
    ca = db.session.get(CA, int(data['ca_id'])) if data.get('ca_id') is not None else None
    if ca is None:
        raise ProtocolRequestGone('The WSTEP CA no longer exists')
    csr = x509.load_pem_x509_csr(data['csr'].encode())
    require_pop = bool(data.get('require_pop', True))
    if data.get('operation') == 'renew':
        signing_cert = x509.load_pem_x509_certificate(data['renewal_of'].encode())
        db_cert, err = wstep_service._renewable_certificate(ca, signing_cert)
        if not err:
            # The proof of possession was checked when the request came in
            cert_pem, err = wstep_service._sign_renewal(
                ca, signing_cert, db_cert, csr, _validity_days(), 'wstep', require_pop,
                on_stored=protocol_approval.linker(approval))
    else:
        cert_pem, err = wstep_service.issue(
            ca, csr.public_bytes(Encoding.DER), _validity_days(), require_pop=require_pop,
            kerberos_principal=data.get('kerberos_principal'),
            on_stored=protocol_approval.linker(approval))
    if err:
        if isinstance(err, wstep_service.ServerError):
            raise ValueError(str(err))
        raise ProtocolRequestGone(f'The WSTEP request can no longer be issued: {err}')
    serial = x509.load_pem_x509_certificate(cert_pem.encode()).serial_number
    row = Certificate.query.filter_by(serial_number=str(serial), caref=ca.refid).first()
    return {'id': row.id if row is not None else None, 'cn': data.get('cn'), 'protocol': 'wstep',
            'serial_number': row.serial_number if row is not None else None}


def _gone(approval, data):
    if data.get('ca_id') is None or db.session.get(CA, int(data['ca_id'])) is None:
        return 'The WSTEP CA no longer exists'
    return None


protocol_approval.register('wstep_request', _issue, gone=_gone)


def request_for(request_id, ca, identity):
    """The request *request_id* names, when it is this requester's on this CA;
    a pending one past its deadline is expired on the way."""
    from models.policy import ApprovalRequest
    if not str(request_id).isdecimal():
        return None
    approval = db.session.get(ApprovalRequest, int(request_id))
    if approval is None or approval.request_type != 'wstep_request':
        return None
    data = protocol_approval.request_data(approval)
    if data.get('ca_id') != ca.id or data.get('identity') != identity:
        return None
    protocol_approval.expire_if_stale(approval)
    return approval


def issued_certificate(approval):
    """The certificate an approved request produced, None when none yet."""
    row = db.session.get(Certificate, approval.certificate_id) if approval.certificate_id else None
    if row is None or not row.crt:
        return None
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt))
