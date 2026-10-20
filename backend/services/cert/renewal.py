"""In-place renewal of a certificate whose private key the server holds.
PLANB-B.2: the routine shared by the renew route, the bulk route, the
scheduler and the execution of an approved renewal is to be written from
the specification. A device-held key renews through its enrollment protocol."""
from base64 import b64decode
import cryptography.x509 as x509
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtensionOID, NameOID
from models import db, CA, Certificate
from services.file_regen_service import mirror_private_key
from utils.key_codec import eddsa_key_name, load_pem_bytes, private_key_to_pem
from utils import key_algorithms
from utils.key_algorithms import (algorithms as registered_algorithms, family_for_public_key,
                                  generate_ec, generate_rsa)
import fips_mode
from fips_mode import FipsRestricted
from utils.eku_validation import add_ocsp_nocheck_if_responder
from utils.validity import MAX_VALIDITY_DAYS as MAX_RENEWAL_DAYS
from utils.x509_aki import authority_key_identifier_from_issuer
from utils.ca_pointer_extensions import add_ca_pointer_extensions
from utils.leaf_key_usage import constrain_builder_key_usage
from utils.datetime_utils import cert_not_before
from utils import notices as notices_mod


_SCT_LIST_OID = x509.ObjectIdentifier('1.3.6.1.4.1.11129.2.4.2')
_ISSUER_OWNED_EXTENSION_OIDS = frozenset({
    ExtensionOID.AUTHORITY_KEY_IDENTIFIER,
    ExtensionOID.SUBJECT_KEY_IDENTIFIER,
    ExtensionOID.CRL_DISTRIBUTION_POINTS,
    ExtensionOID.AUTHORITY_INFORMATION_ACCESS,
    ExtensionOID.CERTIFICATE_POLICIES,
    _SCT_LIST_OID,
})


# ``known_serial`` default: the caller passes nothing, the instance's own
# serial is the reference (None is a real value: a row that gained a serial
# meanwhile was renewed)
SERIAL_UNSET = object()


def _renewed_meanwhile_message(trigger: str) -> str:
    """The 409 message: the retry advice is for an operator, not a batch."""
    if trigger == 'auto':
        return 'Certificate was renewed by another request'
    return 'Certificate was renewed by another request; reload it and retry'


class RenewalError(Exception):  # PLANB-B.2: à implémenter selon SPEC (constructeur et attributs)
    def __init__(self, message: str, status: int = 400, problem_type=None):
        raise NotImplementedError('PLANB-B.2: RenewalError')

    @classmethod
    def from_fips(cls, exc: FipsRestricted) -> 'RenewalError':
        return cls(str(exc), 400, problem_type=fips_mode.PROBLEM_TYPE)
def resolve_issuing_ca(cert: Certificate) -> 'CA | None':
    """Find the CA that signed ``cert``: by refid, else by signature.

    Names alone used to decide (subject, then the issuer's Common Name
    among every CA): a homonymous CA after a rotation, or a local CA merely
    sharing the CN of an external issuer, re-signed the certificate. The
    CAs carrying the issuer's name are tried first, then every other, and
    only the one whose key verifies the certificate's signature qualifies.
    """
    if cert.caref:
        by_refid = CA.query.filter_by(refid=cert.caref).first()
        if by_refid is not None:
            return by_refid
    if not cert.crt:
        return
    try:
        leaf = x509.load_pem_x509_certificate(b64decode(cert.crt))
    except Exception:
        return
    from utils.cert_issuer import authority_key_identifier_hex, certificate_signed_by
    named = CA.query.filter(CA.subject == cert.issuer).all() if cert.issuer else []
    others = [c for c in CA.query.all() if c not in named]
    leaf_aki = authority_key_identifier_hex(leaf)
    verified = []
    for candidate in named + others:
        if not candidate.crt:
            continue
        try:
            ca_cert = x509.load_pem_x509_certificate(b64decode(candidate.crt))
            if certificate_signed_by(leaf, ca_cert):
                verified.append((candidate, ca_cert))
        except Exception:
            continue
    if not verified:
        return
    # Several CA records for one key (a cross-signed or re-issued CA): the
    # one whose SKI the certificate names as its AKI is the real issuer
    if leaf_aki:
        for candidate, ca_cert in verified:
            try:
                ski = ca_cert.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_KEY_IDENTIFIER).value.key_identifier
            except x509.ExtensionNotFound:  # without its SKI a CA cannot be the one the AKI names
                continue
            if ski.hex(':').upper() == str(leaf_aki).upper():
                return candidate
    return verified[0][0]
def check_renewable(cert: Certificate) -> None:
    """Raise :class:`RenewalError` when ``cert`` cannot be renewed at all
    (no certificate, revoked, issued by a Microsoft CA, key not held by the
    server). Shared by the renewal itself and by the routes, which check it
    before queueing a renewal for approval: a request no renewal could honour
    must not wait for an approver."""
    # PLANB-B.2: à implémenter selon SPEC (invariant 34, gardes a à c : sans crt,
    # révoqué, MSCA, dans cet ordre, avant celles qui suivent)
    if not cert.prv:
        # The key lives on the device (SCEP, EST, WSTEP, ACME enrolment,
        # certificate imported without its key): a certificate re-signed
        # here could never reach it, and superseding the serial the device
        # still presents only got that device refused by OCSP and the CRL
        raise RenewalError(
            'The server does not hold the private key of this certificate; '
            'renew it through its enrollment protocol, sign a new request or '
            'issue a new certificate',
            409,
        )

    # Read from the stored type, before the certificate's key is ever loaded
    if fips_mode.enabled():
        alg = key_algorithms.get(cert.key_algo)
        name = alg.display if alg else _stored_eddsa_name(cert)
        if name in ('Ed25519', 'Ed448'):
            try:
                fips_mode.refuse(f'{name} key of certificate {cert.id}')
            except FipsRestricted as e:
                raise RenewalError.from_fips(e) from e

    # The template's SAN types bind the renewed names as they bound the issuance
    template_id = getattr(cert, 'template_id', None)
    if template_id:
        from models.certificate_template import CertificateTemplate
        from services.template_service import allowed_san_types, san_type_of, san_type_refusal
        template = db.session.get(CertificateTemplate, template_id)
        allowed = allowed_san_types(template) if template is not None else None
        if allowed is not None:
            try:
                names = x509.load_pem_x509_certificate(b64decode(cert.crt)).extensions \
                    .get_extension_for_class(x509.SubjectAlternativeName).value
            except x509.ExtensionNotFound:  # a certificate without SAN carries no SAN type
                names = []
            refusal = san_type_refusal(allowed, [san_type_of(n) for n in names], template.name)
            if refusal:
                raise RenewalError(f'Policy violation: {refusal}', 400)


def _stored_eddsa_name(cert: Certificate):
    try:
        return eddsa_key_name(load_pem_bytes(cert.prv, context=f'certificate {cert.id}'))
    except ValueError:
        return None


def renew_certificate_in_place(cert: Certificate, ca=None, *, username: str = 'system',
                               actor_user_id=None, rekey: bool = True, regenerate_crl: bool = True,
                               trigger: str = 'manual', known_serial=SERIAL_UNSET,
                               validity_days=None) -> dict:
    # PLANB-B.2: à implémenter selon SPEC (invariants 1 à 11, 25, 32 à 40, contrats du §3.4)
    raise NotImplementedError('PLANB-B.2: renew_certificate_in_place')
