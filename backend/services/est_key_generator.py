"""The EST key generator certificate of a CA (RFC 7030 §4.4.2: the party that generated the
key signs the package). Issued by the CA with digitalSignature only, so it works under a root
whose own keyUsage is keyCertSign and cRLSign. Like a delegated OCSP responder it is an ordinary
certificate row, listed, audited and revocable; a revoked, expiring or unreadable one is replaced
on the next encrypted request."""
import base64
import hashlib
import logging
import uuid
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID
from sqlalchemy.exc import IntegrityError

import fips_mode
from models import Certificate, db
from models.est_signer_cert import EstSignerCert
from utils import key_algorithms
from utils.datetime_utils import cert_not_before, utc_now

logger = logging.getLogger(__name__)

SUBJECT_CN = 'EST key generator'
SOURCE = 'est_key_generator'
LIFETIME_DAYS = 365
RENEW_DAYS = 30


def _fingerprint(ca_cert):
    return hashlib.sha256(ca_cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def delegate_key_label(ca_public_key):
    """The CA's family where OpenSSL verifies it in CMS (Ed448 gives Ed25519), FIPS-approved."""
    family = key_algorithms.family_for_public_key(ca_public_key)
    if family == 'RSA':
        label = 'RSA-3072'
    elif family in ('EC', 'ML-DSA'):
        label = key_algorithms.label_for_public_key(ca_public_key)
    else:
        label = 'ED25519'
    if fips_mode.enabled() and not key_algorithms.fips_approved(label):
        from utils.issuance_defaults import _of_strength, _security_bits
        label = _of_strength('EC', _security_bits(ca_public_key)).label
    return label


def delegate_subject(ca_subject):
    """Every RDN of the CA subject but its CN, in order, then the CN: dirName constraints hold."""
    rdns = []
    for rdn in ca_subject.rdns:
        kept = [a for a in rdn if a.oid != NameOID.COMMON_NAME]
        if kept:
            rdns.append(x509.RelativeDistinguishedName(kept))
    rdns.append(x509.RelativeDistinguishedName([x509.NameAttribute(NameOID.COMMON_NAME, SUBJECT_CN)]))
    return x509.Name(rdns)


def _issue(ca, ca_cert, key):
    """A certificate for *key* signed by *ca* through its signing key, HSM included."""
    from services.ca.ca_signing import CASigningMixin
    from services.hsm.ca_key_loader import get_ca_signing_key
    from services.policy_service import PolicyEvaluationService, PolicyViolation
    from utils.ca_signing_window import check_issuer_window, clamp_not_after
    from utils.signing_hash import rsa_padding_for
    from utils.x509_aki import authority_key_identifier_from_issuer

    CASigningMixin._check_ca_offline(ca)
    check_issuer_window(ca_cert)
    ca_key = get_ca_signing_key(ca)
    not_after = clamp_not_after(utc_now() + timedelta(days=LIFETIME_DAYS), ca_cert)
    builder = (
        x509.CertificateBuilder()
        .subject_name(delegate_subject(ca_cert.subject))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(cert_not_before())
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
            encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(authority_key_identifier_from_issuer(ca_cert), critical=False)
    )
    # The CA key's own digest and signature rules; no issuance policy scopes an internal signer
    sign_hash, violations = PolicyEvaluationService.checked_signing_hash(
        [], ca_key, None, explicit=True,
        key_type=key_algorithms.label_for_public_key(key.public_key()),
        context={'operation': 'issuance', 'ca_id': ca.id, 'subject': SUBJECT_CN})
    if violations:
        raise PolicyViolation('; '.join(violations))
    cert = builder.sign(ca_key, sign_hash, rsa_padding=rsa_padding_for(ca_key, sign_hash))
    return cert, not_after


def _certificate_row(ca, cert, key, not_after):
    """The Certificate row of a new delegate, built as the OCSP responder renewal builds its own."""
    from utils.key_codec import store_pem_bytes
    pem = cert.public_bytes(serialization.Encoding.PEM)
    return Certificate(
        refid=str(uuid.uuid4())[:8],
        descr=f'{SUBJECT_CN} ({ca.descr})',
        caref=ca.refid,
        crt=base64.b64encode(pem).decode(),
        prv=store_pem_bytes(key.private_bytes(serialization.Encoding.PEM,
                                              serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption())),
        cert_type='usr_cert',
        subject=cert.subject.rfc4514_string(),
        subject_cn=SUBJECT_CN,
        issuer=cert.issuer.rfc4514_string(),
        serial_number=str(cert.serial_number),
        valid_from=cert.not_valid_before_utc.replace(tzinfo=None),
        valid_to=not_after,
        source=SOURCE,
        created_by='system:est-key-generator',
    )


def _usable(link, ca, fingerprint, ca_cert):
    """(key, certificate) of the current delegate, or None when it must be replaced: another CA
    certificate, gone, revoked, expiring while a renewal would gain time, or unreadable."""
    if link is None or link.issuer_fingerprint != fingerprint:
        return None
    row = db.session.get(Certificate, link.certificate_id)
    # The id alone may name another certificate on SQLite: the row must be this delegate
    if row is None or row.source != SOURCE or row.subject_cn != SUBJECT_CN \
            or row.serial_number != link.serial_number or row.caref != ca.refid:
        return None
    if row.revoked or not row.crt or not row.prv:
        return None
    if row.valid_to is None or row.valid_to - utc_now() < timedelta(days=RENEW_DAYS):
        from utils.ca_signing_window import clamp_not_after
        if row.valid_to is None or \
                clamp_not_after(utc_now() + timedelta(days=LIFETIME_DAYS), ca_cert) > row.valid_to:
            return None
    try:
        return _load(row)
    except Exception as e:  # e.g. the master key changed without rotation
        logger.warning('EST key generator %s of CA %s unreadable, replacing it: %s', row.id, ca.id, e)
        return None


def _load(row):
    from utils.key_codec import load_pem_bytes
    key = serialization.load_pem_private_key(
        load_pem_bytes(row.prv, context=f'EST key generator certificate {row.id}'), password=None)
    return key, x509.load_pem_x509_certificate(base64.b64decode(row.crt))


class DelegateRenewedMeanwhile(RuntimeError):
    """The delegate being replaced was renewed in place since it was read: this replacement
    loses, and the request is answered 409 (a retry replaces the renewed row)."""


def _archive(previous, serial) -> bool:
    """Archive the replaced delegate only if it still holds *serial*, re-checked after any
    lock wait (still valid until it expires, as a renewed responder)."""
    from sqlalchemy import update
    from sqlalchemy.orm.attributes import set_committed_value
    done = db.session.execute(
        update(Certificate).where(Certificate.id == previous.id, Certificate.serial_number == serial)
        .values(archived=True).execution_options(synchronize_session=False)).rowcount == 1
    if done:
        set_committed_value(previous, 'archived', True)
    return done


def key_generator(ca, ca_cert):
    """(private key, certificate) of the CA's key generator, issued or re-issued as needed.

    Two first requests at once insert one pointer: the loser of the unique ca_id reads the
    winner's, and its own certificate row goes with its savepoint.
    """
    from services.audit.staging import stage_audit_entry
    fingerprint = _fingerprint(ca_cert)
    link = EstSignerCert.query.filter_by(ca_id=ca.id).first()
    current = _usable(link, ca, fingerprint, ca_cert)
    if current is not None:
        return current
    key = key_algorithms.generate(delegate_key_label(ca_cert.public_key()))
    cert, not_after = _issue(ca, ca_cert, key)
    previous_id = link.certificate_id if link is not None else None
    previous = db.session.get(Certificate, previous_id) if previous_id is not None else None
    if previous is not None and (previous.source != SOURCE or previous.serial_number != link.serial_number):
        previous = None  # a reused id: not ours to archive
    previous_serial = previous.serial_number if previous is not None else None
    try:
        with db.session.begin_nested():
            row = _certificate_row(ca, cert, key, not_after)
            db.session.add(row)
            db.session.flush()
            if link is None:
                db.session.add(EstSignerCert(ca_id=ca.id, certificate_id=row.id,
                                             serial_number=row.serial_number,
                                             issuer_fingerprint=fingerprint, created_at=utc_now()))
            else:
                link.certificate_id, link.issuer_fingerprint = row.id, fingerprint
                link.serial_number = row.serial_number
                link.created_at = utc_now()
            if previous is not None and previous.caref == ca.refid and not previous.revoked \
                    and not _archive(previous, previous_serial):
                raise DelegateRenewedMeanwhile(previous_id)
            db.session.flush()  # a concurrent pointer fails here, before the audit entry is staged
            # The delegate is an issuance of the CA; a lost race rolls the count back with it
            from utils.ca_serial_counter import next_ca_serial
            next_ca_serial(ca)
            stage_audit_entry(
                action='est_key_generator.issued' if link is None else 'est_key_generator.reissued',
                resource_type='ca', resource_id=ca.id, resource_name=ca.descr,
                details=(f'EST key generator certificate {row.id} (serial {cert.serial_number}) '
                         f'issued, valid to {not_after}'
                         + (f', replacing certificate {previous_id}' if previous_id else '')))
        db.session.commit()
    except DelegateRenewedMeanwhile:  # the savepoint goes, the caller's transaction stays
        logger.info('EST key generator certificate %s of CA %s was renewed meanwhile; '
                    'it is not replaced', previous_id, ca.id)
        raise
    except IntegrityError:  # the savepoint goes, the caller's transaction stays
        winner = EstSignerCert.query.filter_by(ca_id=ca.id).first()
        logger.info('EST key generator of CA %s made by a concurrent request', ca.id)
        usable = _usable(winner, ca, fingerprint, ca_cert)
        if usable is None:
            raise RuntimeError('the concurrent EST key generator is not usable')
        return usable
    from services.webhook_service import emit_cert_issued, emit_cert_renewed
    announce = emit_cert_renewed if previous_id is not None else emit_cert_issued
    announce(row.to_dict(), ca_refid=ca.refid, actor='system:est-key-generator')
    logger.info('EST key generator of CA %s issued, valid until %s', ca.id, not_after)
    return key, cert
