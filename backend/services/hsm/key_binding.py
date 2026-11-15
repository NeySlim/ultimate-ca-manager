"""One HSM key backs one authority at most: an X.509 CA or an SSH CA, never both, never two.

A binding locks the ``hsm_keys`` row first (``lock_key``) and checks both tables under it:
two creations racing on one key serialise on that row lock until the first one commits.
Two rows naming one token key (two providers on one token) are matched by their public key
(``refuse_same_token_key``). On PostgreSQL each takes its own row lock: two creations racing on
the two rows at once are not serialised, and both may be created. SQLite serialises them, its
``lock_key`` taking the database write lock.
"""
from cryptography.hazmat.primitives import serialization
from sqlalchemy import update

from models import CA, db
from models.hsm import HsmKey
from models.ssh import SSHCertificateAuthority


class HsmKeyBound(ValueError):
    """The key already backs an authority (409)."""


def _x509(descr):
    return f"X.509 CA '{descr or ''}'"


def _ssh(ca_type, descr):
    return f"SSH {ca_type} CA '{descr or ''}'"


def lock_key(key_id):
    """The HsmKey row, locked until the caller's transaction ends: FOR UPDATE on PostgreSQL;
    on SQLite, which has no row lock, a no-op UPDATE takes the database write lock instead."""
    if db.session.get_bind().dialect.name == 'sqlite':
        table = HsmKey.__table__
        db.session.execute(update(table).where(table.c.id == key_id).values(id=table.c.id))
    return HsmKey.query.filter_by(id=key_id).with_for_update().one_or_none()


def holders(key_id=None, provider_id=None):
    """Names of the authorities on *key_id*, or on any key of *provider_id*: X.509 first."""
    x509 = db.session.query(CA.descr).filter(CA.hsm_key_id.isnot(None))
    ssh = db.session.query(SSHCertificateAuthority.ca_type, SSHCertificateAuthority.descr).filter(
        SSHCertificateAuthority.hsm_key_id.isnot(None))
    if key_id is not None:
        x509 = x509.filter(CA.hsm_key_id == key_id)
        ssh = ssh.filter(SSHCertificateAuthority.hsm_key_id == key_id)
    if provider_id is not None:
        x509 = x509.join(HsmKey, CA.hsm_key_id == HsmKey.id).filter(HsmKey.provider_id == provider_id)
        ssh = ssh.join(HsmKey, SSHCertificateAuthority.hsm_key_id == HsmKey.id).filter(
            HsmKey.provider_id == provider_id)
    return ([_x509(d) for (d,) in x509.order_by(CA.id)]
            + [_ssh(t, d) for t, d in ssh.order_by(SSHCertificateAuthority.id)])


def bound_key_ids():
    """Ids of every key an X.509 or an SSH CA holds."""
    ids = {r[0] for r in db.session.query(CA.hsm_key_id).filter(CA.hsm_key_id.isnot(None))}
    return ids | {r[0] for r in db.session.query(SSHCertificateAuthority.hsm_key_id).filter(
        SSHCertificateAuthority.hsm_key_id.isnot(None))}


def shared_keys():
    """{key id: holders} for every key more than one authority holds."""
    ids = [r[0] for r in db.session.query(CA.hsm_key_id).filter(CA.hsm_key_id.isnot(None))]
    ids += [r[0] for r in db.session.query(SSHCertificateAuthority.hsm_key_id).filter(
        SSHCertificateAuthority.hsm_key_id.isnot(None))]
    return {key_id: holders(key_id=key_id) for key_id in sorted(set(ids)) if ids.count(key_id) > 1}


def label_of(key_id):
    key = db.session.get(HsmKey, key_id)
    return key.label if key is not None else f'#{key_id}'


def refuse_node_local_in_ha(provider):
    """HaRestricted for a new CA on a token only one node reaches: SoftHSM, a local smart card reader."""
    from services import compliance_signer
    from utils.ha import refuse_reader_in_ha, refuse_softhsm_in_ha
    if compliance_signer.softhsm_provider(provider):
        refuse_softhsm_in_ha()
    elif compliance_signer.local_reader_provider(provider):
        refuse_reader_in_ha()


def refuse_bound_key(key):
    """HsmKeyBound naming the authority that holds *key*; call it with the row locked."""
    held = holders(key_id=key.id)
    if held:
        raise HsmKeyBound(f"HSM key '{key.label}' already backs the {held[0]}: "
                          f"an HSM key backs one authority only")


def summary(names, limit=5):
    """'A, B (+2 more)' for a refusal message."""
    more = '' if len(names) <= limit else f' (+{len(names) - limit} more)'
    return ', '.join(names[:limit]) + more


def _spki(public_key):
    return public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def _bound_spki():
    """{key id: SPKI} of every bound key row whose public key UCM holds."""
    bound = bound_key_ids()
    out = {}
    if not bound:
        return out
    for row in HsmKey.query.filter(HsmKey.id.in_(bound), HsmKey.public_key_pem.isnot(None)):
        pem = row.public_key_pem
        try:
            out[row.id] = _spki(serialization.load_pem_public_key(pem.encode() if isinstance(pem, str) else pem))
        except ValueError:
            continue
    return out


def taken_key_ids():
    """Ids of the bound key rows and of every other row naming the same token key (same public key)."""
    spkis = _bound_spki()
    taken = bound_key_ids()
    if not spkis:
        return taken
    wanted = set(spkis.values())
    for row in HsmKey.query.filter(HsmKey.id.notin_(taken), HsmKey.public_key_pem.isnot(None)):
        pem = row.public_key_pem
        try:
            if _spki(serialization.load_pem_public_key(pem.encode() if isinstance(pem, str) else pem)) in wanted:
                taken.add(row.id)
        except ValueError:
            continue
    return taken


def shared_token_keys():
    """{(key id, key id): (holder, holder)} for two bound key rows naming one token key (same public key)."""
    by_spki = {}
    for key_id, spki in sorted(_bound_spki().items()):
        by_spki.setdefault(spki, []).append(key_id)
    pairs = {}
    for ids in by_spki.values():
        for i, first in enumerate(ids):
            for second in ids[i + 1:]:
                pairs[(first, second)] = (holders(key_id=first)[0], holders(key_id=second)[0])
    return pairs


def refuse_same_token_key(key, public_key):
    """HsmKeyBound when another key row with *public_key* backs an authority: it is the same token key."""
    spki = _spki(public_key)
    bound = bound_key_ids() - {key.id}
    if not bound:
        return
    rows = HsmKey.query.filter(HsmKey.id.in_(bound), HsmKey.public_key_pem.isnot(None)).order_by(HsmKey.id)
    for other in rows:
        try:
            pem = other.public_key_pem
            if _spki(serialization.load_pem_public_key(pem.encode() if isinstance(pem, str) else pem)) != spki:
                continue
        except ValueError:
            continue
        raise HsmKeyBound(f"HSM key '{key.label}' is the token key of HSM key '{other.label}', "
                          f"which backs the {holders(key_id=other.id)[0]}: an HSM key backs one authority only")
