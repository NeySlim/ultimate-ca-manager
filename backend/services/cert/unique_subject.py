"""RFC 5280 §4.1.2.6 at issuance: a CA with ``enforce_unique_subject`` never certifies a
non-empty subject that a certificate of the CA, whatever its status, carries for another entity.

Every issuance path of an end-entity certificate calls :func:`refuse_taken_subject` once the CA
row is locked (``next_ca_serial``), before its commit. "The same entity" is proven by the same
public key, a designated renewal (lineage kept in ``certificates.subject_holder``), the path's
recorded identity (``sid:``, ``acme:``, ``user:``), or the SID extension (Windows enrollment).
"""
import base64
import logging

from cryptography import x509
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)


class SubjectTaken(ValueError):
    """The subject is carried by certificate *serial* of the CA, issued to another entity.
    ``str()`` names the subject only (what a protocol client is told); ``audited`` adds the serial."""

    def __init__(self, subject, serial):
        self.subject, self.serial = subject, serial
        self.public_message = (f'the subject {subject} is already carried by a certificate '
                               'of this CA issued to another entity')
        self.audited = f'the subject {subject} is already carried by certificate serial {serial}'
        super().__init__(self.public_message)


def lineage(row):
    """The identity a certificate issued as *row*'s designated successor records."""
    return row.subject_holder or f'cert:{row.refid}'


def sid_holder(sid):
    """The identity a Windows enrollment records: the requester's SID."""
    return f'sid:{sid}' if sid else None


def successor_holder(path_holder=None, renews=()):
    """What the new certificate records in ``subject_holder``: the path's identity, else the
    lineage of the certificate it renews, else nothing."""
    if path_holder:
        return path_holder
    for row in renews:
        if row is not None:
            return lineage(row)
    return None


def _spki(cert):
    try:
        return cert.public_key().public_bytes(serialization.Encoding.DER,
                                              serialization.PublicFormat.SubjectPublicKeyInfo)
    except Exception:  # a key pyca cannot load proves nothing
        return None


def _identities(row):
    return {i for i in (row.subject_holder, f'cert:{row.refid}') if i}


class _Requester:
    """Who asks: the issued certificate, its own and designated rows, the path's identity."""

    def __init__(self, issued, own, renews, holder, sid):
        from services.trust_store.csr_operations_mixin import ad_security_extension_sid
        rows = [r for r in list(own) + list(renews) if r is not None]
        self.identities = set().union(*(_identities(r) for r in rows)) if rows else set()
        if holder:
            self.identities.add(holder)
        self.spki = _spki(issued)
        # The issuer writes the SID extension (never copied from a request): an in-place renewal's copy
        self.sids = {sid, ad_security_extension_sid(issued)} - {None}

    def same_as(self, row, held, full):
        from services.trust_store.csr_operations_mixin import ad_security_extension_sid
        if ad_security_extension_sid(held) in self.sids:
            return True
        if not full:  # a common name pattern alone: the SID extension is the only proof
            return False
        return (bool(_identities(row) & self.identities)
                or (self.spki is not None and _spki(held) == self.spki))


def _held(row):
    try:
        return x509.load_pem_x509_certificate(base64.b64decode(row.crt)) if row.crt else None
    except Exception:
        return None


def applies(ca, pattern=False):
    """Whether an issuance under *ca* is checked (no query when it is not)."""
    return bool(pattern or getattr(ca, 'enforce_unique_subject', False))


def issuer_refids(ca):
    """RFC 5280 §4.1.2.6 scopes the subject to "the one CA as defined by the issuer field": the
    records of *ca*'s subject and key (a root and its cross-certificate, a re-imported CA)."""
    from utils.cert_issuer import same_key_refids
    return same_key_refids(ca)


def _lock_twins(ca, refids):
    """Serialise the issuances of twin records on the lowest-id one, *ca*'s own row being locked
    already: two twins never wait on each other, both wait on that one."""
    from models import CA, db
    anchor = db.session.query(CA.id).filter(CA.refid.in_(refids)).order_by(CA.id).first()
    if anchor is not None and anchor[0] != ca.id:
        db.session.query(CA.id).filter(CA.id == anchor[0]).with_for_update().first()


def refuse_taken_subject(ca, issued, *, own=(), renews=(), holder=None, requester_sid=None,
                         pattern=False, override=False, source='manual', requester=None, locked=True,
                         audited=True):
    """Raise :class:`SubjectTaken` (session rolled back, refusal audited) when another entity's
    certificate of *ca* carries *issued*'s subject; called under the CA row lock. With *override*
    (manual issuance and CSR signing), return an :class:`Override` instead. ``locked=False``: the
    early check before anything is published, without the lock, repeated under it.
    ``audited=False``: the caller writes the refusal's one audit entry (WSTEP)."""
    if not applies(ca, pattern) or len(issued.subject) == 0:
        return None
    from models import Certificate, db
    from utils.dn_match import name_key, same_name
    full = bool(getattr(ca, 'enforce_unique_subject', False))
    if any(r is not None and r.id is None for r in own):
        db.session.flush()  # the rows of this issuance are excluded by id
    refids = issuer_refids(ca) if full else [ca.refid]  # a pattern alone keeps its own record
    if locked and len(refids) > 1:
        _lock_twins(ca, refids)
    who = _Requester(issued, own, renews, holder, requester_sid)
    own_ids = {r.id for r in own if r is not None and r.id is not None}
    rows = (db.session.query(Certificate)
            .filter(Certificate.caref.in_(refids), Certificate.subject_key == name_key(issued.subject),
                    Certificate.crt.isnot(None), ~Certificate.id.in_(own_ids or {-1}))
            .order_by(Certificate.id))
    carriers = []
    for row in rows:
        held = _held(row)
        if held is not None and same_name(held.subject, issued.subject):
            carriers.append((row, held))
    # A row is the requester's when one row of its entity is: one grouping, as the count's
    groups = _entities(carriers, full)
    others = [g for g in groups if not any(who.same_as(row, held, full) for row, held in g)]
    if not others:
        return None
    taken = others[0][0][0]
    if override and full:
        return _attested(own, groups, taken)
    refusal = SubjectTaken(issued.subject.rfc4514_string(), taken.serial_number)
    db.session.rollback()
    if full and audited:
        _audit_refusal(ca, refusal, source, requester)
    raise refusal


class Override:
    """An override: *serial* carries the subject; *adopted* is the certificate whose holder the
    issued rows took when one entity carries it, else None and *entities* say how many do."""

    def __init__(self, serial, adopted=None, entities=1):
        self.serial, self.adopted, self.entities = serial, adopted, entities


def _attested(own, groups, taken):
    """The operator attests the same entity: with one entity carrying the subject, the issued
    rows take its lineage, as a renewal would; with several, nothing says which one is meant."""
    if len(groups) != 1:
        return Override(taken.serial_number, entities=len(groups))
    first = groups[0][0][0]
    for row in own:
        if row is not None:
            row.subject_holder = lineage(first)
    return Override(taken.serial_number, adopted=first.serial_number)


def _entities(carriers, full=True):
    """The (row, certificate) pairs grouped by entity, merged on any shared proof: key, recorded
    identity or lineage, SID (the SID only for a common name pattern). In first-row order."""
    from services.trust_store.csr_operations_mixin import ad_security_extension_sid
    groups = []  # one entry per entity: [members, keys, identities, SIDs]
    for row, held in carriers:
        sid = {ad_security_extension_sid(held)} - {None}
        mine = [[(row, held)], {_spki(held)} - {None} if full else set(),
                _identities(row) if full else set(), sid]
        joined = [g for g in groups if g[1] & mine[1] or g[2] & mine[2] or g[3] & mine[3]]
        groups = [g for g in groups if all(g is not j for j in joined)]
        merged = [[m for g in [mine, *joined] for m in g[0]],
                  *(set().union(*(g[i] for g in [mine, *joined])) for i in (1, 2, 3))]
        groups.append(merged)
    members = [sorted(g[0], key=lambda m: m[0].id) for g in groups]
    return sorted(members, key=lambda g: g[0][0].id)


def _audit_refusal(ca, taken, source, requester):
    from services.audit.staging import stage_audit_entry
    from utils.db_transaction import safe_commit
    stage_audit_entry(
        action='certificate.subject_taken', resource_type='ca', resource_id=str(ca.id),
        resource_name=ca.descr, username=requester, success=False,
        details=f'{source} issuance refused: {taken.audited}')
    safe_commit(logger, 'Subject uniqueness refusal audit commit failed')


def audit_override(ca, issued_row, override, username):
    """The audit entry of an override: the operator attests that the certificate is for the
    entity that already carries the subject, or the subject stays shared by several."""
    from services.audit.staging import stage_audit_entry
    from utils.db_transaction import safe_commit
    issued = (f'certificate serial {issued_row.serial_number} under CA {ca.descr} (id={ca.id}) '
              f'with the subject {issued_row.subject}')
    if override.adopted is not None:
        details = (f'{username} attested that {issued} is for the same entity as the one that already '
                   f'carries this subject: it takes the holder of certificate serial {override.adopted}')
    else:
        details = (f'{username} issued {issued}, already carried by {override.entities} entities '
                   f'(certificate serial {override.serial} among them): the subject stays shared')
    stage_audit_entry(
        action='certificate.subject_override', resource_type='certificate',
        resource_id=str(issued_row.id), resource_name=issued_row.subject, username=username,
        details=details)
    safe_commit(logger, 'Subject uniqueness override audit commit failed')


def shared_subjects(ca):
    """The subjects certificates of *ca* (its twin records included) already carry for more than
    one entity, in id order: ``[{'subject', 'serial_numbers'}]``."""
    from sqlalchemy import func
    from models import Certificate, db
    refids = issuer_refids(ca)
    keys = [k for (k,) in db.session.query(Certificate.subject_key)
            .filter(Certificate.caref.in_(refids), Certificate.subject_key.isnot(None),
                    Certificate.crt.isnot(None))
            .group_by(Certificate.subject_key).having(func.count(Certificate.id) > 1)
            .order_by(func.min(Certificate.id))]
    shared = []
    for key in keys:
        carriers = []
        for row in Certificate.query.filter(Certificate.caref.in_(refids), Certificate.subject_key == key,
                                            Certificate.crt.isnot(None)).order_by(Certificate.id):
            try:
                carriers.append((row, x509.load_pem_x509_certificate(base64.b64decode(row.crt))))
            except Exception:
                continue
        if len(_entities(carriers)) > 1:
            shared.append({'subject': carriers[0][1].subject.rfc4514_string(),
                           'serial_numbers': [row.serial_number for row, _ in carriers]})
    return shared


OVERRIDE_FIELD = 'override_unique_subject'


def override_requested(data):
    """Whether a manual issuance or CSR signing asks for the override: ``override_unique_subject:
    true`` only. Both routes already require write:certificates, the permission to issue."""
    return (data or {}).get(OVERRIDE_FIELD) is True


def taken_response(taken):
    """409 naming the subject and the certificate carrying it, and how to issue anyway."""
    from utils.response import error_response
    return error_response(
        f'The subject {taken.subject} is already carried by certificate serial {taken.serial}, '
        f'issued by this CA; send {OVERRIDE_FIELD}: true to attest that this certificate is for '
        f'the same entity as the one that already carries this subject (audited)', 409,
        details={'subject': taken.subject, 'serial_number': taken.serial,
                 'override_field': OVERRIDE_FIELD})
