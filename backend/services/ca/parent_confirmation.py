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


def settle_confirmed_parent(ca, cert):
    """Before *ca* takes *cert*: True while its parent confirmed by hand still holds, else that
    link and its mark are cleared (a verified parent, if any, is the caller's to set)."""
    if keeps_confirmed_parent(ca, cert):
        return True
    if ca.parent_confirmed_at is not None:
        ca.caref = None
        ca.parent_confirmed_by = None
        ca.parent_confirmed_at = None
    return False
