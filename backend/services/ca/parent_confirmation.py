"""A CA whose parent's signature cannot be checked here (a key or signature algorithm this
build does not handle) is proposed a parent and linked to it only on an explicit confirmation.

A signature that verifies links on its own; one that does not verify is never linked; only
the unverifiable case is proposed, and the confirmation checks all of it again when given.
"""
import base64
from dataclasses import dataclass

from cryptography import x509

from utils.cert_issuer import (
    INVALID, UNVERIFIABLE, VERIFIED, authority_key_identifier_hex, is_self_signed, self_signed_first,
    signature_verdict,
)
from utils.datetime_utils import utc_now
from utils.dn_match import same_name


@dataclass(frozen=True)
class Proposal:
    parent: object
    algorithm: str

    @property
    def reason(self):
        return f'signature not verifiable here: {self.algorithm}'

    def to_dict(self):
        return {'id': self.parent.id, 'name': self.parent.descr, 'algorithm': self.algorithm,
                'reason': self.reason}


class ConfirmationRefused(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.message = message
        self.status = status


def _certificate(ca):
    try:
        return x509.load_pem_x509_certificate(base64.b64decode(ca.crt)) if ca and ca.crt else None
    except Exception:
        return None


def _namesakes(cert, exclude_id):
    """Stored CAs whose subject is *cert*'s issuer (RFC 5280 §7.1) and whose SKI is its AKI when both exist."""
    from models import CA
    aki = authority_key_identifier_hex(cert)
    found = {}
    for row in CA.query.filter(CA.crt.isnot(None), CA.crt != '').order_by(CA.id).all():
        if row.id == exclude_id or (aki and row.ski and row.ski.upper() != aki):
            continue
        parent_cert = _certificate(row)
        if parent_cert is not None and same_name(parent_cert.subject, cert.issuer):
            found[row.id] = (row, parent_cert)
    return [(row, found[row.id][1]) for row in self_signed_first([row for row, _ in found.values()])]


def proposal_for(cert, exclude_id=None):
    """The stored CA to propose as *cert*'s parent: the first namesake (root before a cross or
    link certificate) whose key cannot check the signature. None for a self-signed certificate,
    when a namesake's key verifies it (it is linked without asking) or when none is left."""
    if is_self_signed(cert):
        return None
    proposal = None
    for row, parent_cert in _namesakes(cert, exclude_id):
        verdict, algorithm = signature_verdict(cert, parent_cert)
        if verdict == VERIFIED:
            return None
        if verdict == UNVERIFIABLE and proposal is None:
            proposal = Proposal(row, algorithm)
    return proposal


def proposal(ca):
    """The proposal for a stored CA left without a parent; None for a linked one."""
    if ca is None or ca.caref or not ca.crt:
        return None
    cert = _certificate(ca)
    return None if cert is None else proposal_for(cert, ca.id)


def notices(cas):
    """What an import reports for each of *cas* left without a parent for this reason."""
    out = []
    for ca in cas:
        found = proposal(ca)
        if found is not None:
            out.append({'ca_id': ca.id, 'ca_name': ca.descr,
                        'candidate': {'id': found.parent.id, 'name': found.parent.descr},
                        'algorithm': found.algorithm, 'reason': found.reason})
    return out


def confirm(ca, parent, username):
    """Link *ca* under *parent* as confirmed by *username*; raises ConfirmationRefused with the
    reason unless *ca* has no parent, *parent* is its proposal and the signature is still unverifiable."""
    if ca.caref:
        raise ConfirmationRefused('This CA already has a parent: there is nothing to confirm')
    cert = _certificate(ca)
    if cert is None:
        raise ConfirmationRefused('This CA holds no readable certificate', 400)
    if parent is None or parent.id == ca.id:
        raise ConfirmationRefused('Parent CA not found', 404)
    parent_cert = _certificate(parent)
    verdict = signature_verdict(cert, parent_cert)[0] if parent_cert is not None else None
    if verdict == INVALID:
        raise ConfirmationRefused(f'The key of "{parent.descr}" does not verify the signature of this CA: '
                                  'it is not its parent')
    if verdict == VERIFIED:
        raise ConfirmationRefused(f'The key of "{parent.descr}" verifies the signature of this CA: '
                                  'chain repair links it without a confirmation')
    found = proposal_for(cert, ca.id)
    if found is None or found.parent.id != parent.id:
        proposed = f'the proposed parent is "{found.parent.descr}"' if found else 'no parent is proposed'
        raise ConfirmationRefused(f'"{parent.descr}" is not the proposed parent of this CA: {proposed}')
    ca.caref = parent.refid
    ca.parent_confirmed_by = username
    ca.parent_confirmed_at = utc_now()
    return found


def withdraw(ca):
    """Unlink a parent confirmed by hand; raises ConfirmationRefused for any other link."""
    if not ca.caref or ca.parent_confirmed_at is None:
        raise ConfirmationRefused('This CA has no parent confirmed by hand: there is nothing to withdraw')
    former = ca.caref
    ca.caref = None
    ca.parent_confirmed_by = None
    ca.parent_confirmed_at = None
    return former


def keeps_confirmed_parent(ca, cert):
    """Whether the parent confirmed by hand for *ca* is still the proposal for its new certificate *cert*."""
    if not ca.caref or ca.parent_confirmed_at is None:
        return False
    found = proposal_for(cert, ca.id)
    return found is not None and found.parent.refid == ca.caref


def _revoked_as(ca, cert):
    """Whether *cert* is the revoked certificate of *ca*: revocation is per serial (RFC 5280 5.3)."""
    from services.import_service import stored_certificate_serial
    return stored_certificate_serial(ca) == cert.serial_number and ca.is_revoked


def may_drop_parent(ca, cert, parent):
    """Whether *parent* may be removed from *ca* holding *cert*: the one rule of the chain repair
    and of every certificate change. Never for a revoked CA (its parent's CRL lists it); yes for a
    subject that is not the issuer name (RFC 5280 6.1.3 (a)(4)) or for the key the AKI names
    (4.2.1.1) when it disproves the signature; no for a parent re-keyed since (the AKI names
    another key) and whatever proves nothing."""
    from utils.cert_issuer import signature_disproved
    parent_cert = _certificate(parent)
    if parent_cert is None or _revoked_as(ca, cert):
        return False
    if is_self_signed(cert) or not same_name(parent_cert.subject, cert.issuer):
        return True
    try:
        ski = parent_cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value
    except x509.ExtensionNotFound:
        return False
    aki = authority_key_identifier_hex(cert)
    return aki is not None and aki == ski.key_identifier.hex(':').upper() and signature_disproved(cert, parent_cert)


def settle_parent(ca, cert):
    """Before *ca* takes *cert*: ``caref`` becomes its parent confirmed by hand while that is still
    the proposal, else the CA whose subject is the issuer name of *cert* and whose key verifies it,
    else the former parent unless ``may_drop_parent`` allows its removal, else None. A revoked CA
    keeps its parent. Returns whether the confirmed parent held; the caller audits a dropped link
    after its commit with ``audit_dropped``."""
    if keeps_confirmed_parent(ca, cert):
        return True
    from models import CA
    from services.import_service import relink_parent_caref
    former, confirmed = ca.caref, ca.parent_confirmed_at is not None
    parent = CA.query.filter_by(refid=former).first() if former else None
    held = parent is not None and parent.id != ca.id and not may_drop_parent(ca, cert, parent)
    if held and _revoked_as(ca, cert):
        # Moved under another record, the CA would leave the CRL of the parent that revoked it
        return confirmed
    held = held and not confirmed  # a link confirmed by hand holds only while it is the proposal
    ca.caref = relink_parent_caref(cert, None, exclude_ca_id=ca.id) or (former if held else None)
    ca.parent_confirmed_by = None
    ca.parent_confirmed_at = None
    if former and (confirmed or ca.caref != former and not _same_issuer_record(former, ca.caref)):
        ca._dropped_parent = (former, confirmed)
    return False


def _same_issuer_record(former, now):
    """Whether *former* holds the subject and key of the record *now*: a move between them drops nothing."""
    from models import CA
    from utils.cert_issuer import same_key_refids
    parent = CA.query.filter_by(refid=now).first() if now else None
    return parent is not None and former in same_key_refids(parent)


def audit_dropped(ca, username=None):
    """After the caller's commit: the audit entry of a parent ``settle_parent`` dropped
    (``ca_parent_unconfirmed`` for one confirmed by hand, ``ca_parent_unlinked`` otherwise)."""
    dropped = ca.__dict__.pop('_dropped_parent', None)
    if dropped is None:
        return
    former, confirmed = dropped
    from models import CA
    from services.audit_service import AuditService
    parent = CA.query.filter_by(refid=former).first()
    name = parent.descr if parent else former
    if confirmed:
        AuditService.log_ca(
            'ca_parent_unconfirmed', ca,
            f'Parent "{name}" confirmed by hand dropped: the new certificate of this CA is not under it',
            username=username)
        return
    now = CA.query.filter_by(refid=ca.caref).first() if ca.caref else None
    AuditService.log_ca(
        'ca_parent_unlinked', ca,
        f'Parent "{name}" dropped: {_why_not_issuer(parent, _certificate(ca))}'
        + (f'; linked under "{now.descr}"' if now else ''), username=username)


def _why_not_issuer(parent, cert):
    """Why *parent* is not the issuer of *cert* (RFC 5280 6.1.3 (a)(1) signature, (a)(4) name)."""
    parent_cert = _certificate(parent)
    if parent_cert is None or cert is None:
        return 'it is not the issuer of the certificate of this CA'
    if not same_name(parent_cert.subject, cert.issuer):
        return 'its subject is not the issuer name of the certificate of this CA'
    if signature_verdict(cert, parent_cert)[0] == UNVERIFIABLE:
        return 'its signature of the certificate of this CA cannot be verified here'
    return 'its key does not verify the certificate of this CA'
