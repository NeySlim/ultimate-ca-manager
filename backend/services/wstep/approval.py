"""WSTEP requests held by a policy requiring approval (MS-WSTEP 3.1.4.2.1).

The client is answered with a pending RSTR carrying the approval request's
id as ``wstep:RequestID``, which it sends back with QueryTokenStatus; the
approval issues the certificate as the enrolment or renewal would have, under the
profile the request was held for, and only while it is enabled. Profile and CA are
replayed by name and refid: a restore on another installation does not remap the ids.
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


def make_gate(ca, *, operation, profile, identity=None, extra=None):
    """The gate ``wstep_service.issue`` and the renewals call before signing.
    A renewal's identity is the certificate it renews; the decision replays *profile*."""
    def gate(*, csr, template, subject, san, signing_cert=None):
        requester = certificate_identity(signing_cert) if signing_cert is not None else identity
        cn_attrs = subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
        cn = str(cn_attrs[0].value) if cn_attrs else None
        if san is not None:
            dns = [n.value for n in san if isinstance(n, x509.DNSName)]
        else:
            dns = protocol_approval.csr_names(csr)[1]
        data = dict(extra or {}, operation=operation, profile_id=getattr(profile, 'id', None),
                    profile_name=getattr(profile, 'name', None), profile_realm=getattr(profile, 'realm', None))
        csr_ref = protocol_approval.csr_ref(csr)
        if signing_cert is not None:
            data['renewal_of'] = signing_cert.public_bytes(Encoding.PEM).decode()
        return protocol_approval.gate_protocol_issuance(
            'wstep', ca=ca, template_id=getattr(template, 'id', None), cn=cn, san_list=dns,
            csr_pem=csr.public_bytes(Encoding.PEM).decode(), identity=requester,
            # By refid, which a restore keeps; the id form names requests held before it
            protocol_ref=protocol_approval.make_ref('wstep', operation, ca.refid, requester, csr_ref),
            former_refs=(protocol_approval.make_ref('wstep', operation, ca.id, requester, csr_ref),),
            renewal=operation == 'renew', extra=data)
    return gate


PROFILE_GONE = 'The Windows enrollment profile of the request no longer exists'


def _profile_gone(data):
    name = data.get('profile_name')
    return f'The Windows enrollment profile {name} no longer exists' if name else PROFILE_GONE


def _held_realm(data):
    """The realm the request was held for: its profile's, else its Kerberos principal's."""
    realm = data.get('profile_realm')
    if not realm and '@' in (data.get('kerberos_principal') or ''):
        realm = data['kerberos_principal'].rsplit('@', 1)[1]
    return (realm or '').upper() or None


def _held_profile(data):
    """The profile the request was held for, by name (by id when held before names were
    recorded), the default for one held before profiles were; None when it no longer exists.
    A name no longer found, or taken by a profile of another realm, falls back on the id when
    that profile has the request's realm (renamed)."""
    from models import WindowsEnrollmentProfile
    from services.windows_profiles import default_profile
    if data.get('profile_name'):
        profile = WindowsEnrollmentProfile.query.filter_by(name=data['profile_name']).one_or_none()
        realm, recorded_id = _held_realm(data), data.get('profile_id')
        # Another row under the name and another realm than the one recorded: a homonym
        if (profile is not None and recorded_id is not None and profile.id != int(recorded_id)
                and data.get('profile_realm') and (profile.realm or '').upper() != realm):
            profile = None
        if profile is None and recorded_id is not None and realm:
            renamed = db.session.get(WindowsEnrollmentProfile, int(recorded_id))
            if renamed is not None and (renamed.realm or '').upper() == realm:
                return renamed
        return profile
    if 'profile_id' not in data:
        return default_profile()
    profile_id = data['profile_id']
    return db.session.get(WindowsEnrollmentProfile, int(profile_id)) if profile_id is not None else None


def held_ca(data):
    """The CA the request was held on, by refid (by id when held before refids were recorded)."""
    if data.get('ca_refid'):
        return CA.query.filter_by(refid=data['ca_refid']).first()
    return db.session.get(CA, int(data['ca_id'])) if data.get('ca_id') is not None else None


def _issue(approval, data):
    """Issue an approved request under the profile it was held for; refused at issuance
    when the CA or the profile is gone, or the profile no longer serves."""
    from services.wstep import wstep_service
    ca = held_ca(data)
    if ca is None:
        raise ProtocolRequestGone('The WSTEP CA no longer exists', refusal=protocol_approval.ISSUANCE_REFUSAL)
    profile = _held_profile(data)
    if profile is None:
        raise ProtocolRequestGone(_profile_gone(data), refusal=protocol_approval.ISSUANCE_REFUSAL)
    if not profile.enabled:
        raise ProtocolRequestGone(f'The Windows enrollment profile {profile.name} is disabled',
                                  refusal=protocol_approval.ISSUANCE_REFUSAL)
    validity_days = profile.validity_days
    csr = x509.load_pem_x509_csr(data['csr'].encode())
    require_pop = bool(data.get('require_pop', True))
    if data.get('operation') == 'renew':
        signing_cert = x509.load_pem_x509_certificate(data['renewal_of'].encode())
        db_cert, err = wstep_service._renewable_certificate(ca, signing_cert)
        if not err:
            # The proof of possession was checked when the request came in
            cert_pem, err = wstep_service._sign_renewal(
                ca, signing_cert, db_cert, csr, validity_days, 'wstep', require_pop,
                on_stored=protocol_approval.linker(approval), profile=profile)
    else:
        cert_pem, err = wstep_service.issue(
            ca, csr.public_bytes(Encoding.DER), validity_days, require_pop=require_pop,
            kerberos_principal=data.get('kerberos_principal'),
            on_stored=protocol_approval.linker(approval), profile=profile)
    if err:
        if isinstance(err, wstep_service.ServerError):
            raise ValueError(str(err))
        # The approver reads the audited form: the client is told the fixed refusal only
        raise ProtocolRequestGone(f'The WSTEP request can no longer be issued: {getattr(err, "audited", err)}',
                                  refusal=protocol_approval.ISSUANCE_REFUSAL)
    serial = x509.load_pem_x509_certificate(cert_pem.encode()).serial_number
    row = Certificate.query.filter_by(serial_number=str(serial), caref=ca.refid).first()
    return {'id': row.id if row is not None else None, 'cn': data.get('cn'), 'protocol': 'wstep',
            'serial_number': row.serial_number if row is not None else None}


def _gone(approval, data):
    if held_ca(data) is None:
        return 'The WSTEP CA no longer exists'
    return _profile_gone(data) if _held_profile(data) is None else None


protocol_approval.register('wstep_request', _issue, gone=_gone)


def request_for(request_id, ca, identity):
    """The request *request_id* names, when it is this requester's on this CA (None: any, the
    identity being the certificate itself); a pending one past its deadline is expired on the way."""
    from models.policy import ApprovalRequest
    if not str(request_id).isdecimal():
        return None
    approval = db.session.get(ApprovalRequest, int(request_id))
    if approval is None or approval.request_type != 'wstep_request':
        return None
    data = protocol_approval.request_data(approval)
    if data.get('identity') != identity:
        return None
    if ca is not None and getattr(held_ca(data), 'id', None) != ca.id:
        return None
    protocol_approval.expire_if_stale(approval)
    return approval


def issued_certificate(approval):
    """The certificate an approved request produced, None when none yet."""
    row = db.session.get(Certificate, approval.certificate_id) if approval.certificate_id else None
    if row is None or not row.crt:
        return None
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt))
