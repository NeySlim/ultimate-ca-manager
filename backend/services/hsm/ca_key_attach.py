"""Attach a key an HSM still holds to a CA that holds only its certificate (#458).

A token key matches a CA when its SubjectPublicKeyInfo DER equals the certificate's. The key is
attached only after it has signed a throwaway CRL that the certificate's public key verifies.
"""
import base64
import json
import logging
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from models import CA, db
from models.hsm import HsmKey, HsmProvider
from services.hsm import HsmService, key_binding
from services.hsm.base_provider import HsmError, HsmSecretUnreadable
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

SIGNING_PURPOSES = ('signing', 'all')


class AttachRefused(ValueError):
    """Refusal with its HTTP status."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _spki(public_key):
    return public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def _spki_of_pem(pem):
    try:
        return _spki(serialization.load_pem_public_key(pem.encode() if isinstance(pem, str) else pem))
    except (ValueError, TypeError):
        return None


def matches_certificate(pem, cert):
    """Whether the public key *pem* is *cert*'s: SubjectPublicKeyInfo DER compared byte for byte."""
    spki = _spki_of_pem(pem) if pem else None
    return spki is not None and spki == _spki(cert.public_key())


def keyless_ca_certificate(ca):
    """The certificate of *ca* when a key may be attached to it, else AttachRefused."""
    if ca is None:
        raise AttachRefused('CA not found', 404)
    if ca.is_pending or not ca.crt:
        raise AttachRefused('A pending CA already holds its own key; install its certificate instead', 409)
    if ca.offline:
        raise AttachRefused('CA is offline: restore it with its exported key file or password '
                            'instead of attaching a key', 409)
    if ca.prv or ca.hsm_key_id:
        raise AttachRefused('CA already has a private key')
    try:
        return x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
    except Exception:
        raise AttachRefused('CA certificate could not be parsed')


def _provider(provider_id):
    provider = db.session.get(HsmProvider, provider_id) if provider_id else None
    if provider is None:
        raise AttachRefused('HSM provider not found', 404)
    key_binding.refuse_node_local_in_ha(provider)
    return provider


def _token_keys(provider):
    """[(HsmKeyInfo, SPKI DER or None)] of the provider's asymmetric signing keys, read on the token."""
    try:
        hsm = HsmService._get_provider_instance(provider)
        with hsm:
            out = []
            for info in hsm.list_keys():
                if info.key_type != 'asymmetric' or info.purpose not in SIGNING_PURPOSES:
                    continue
                pem = info.public_key_pem
                if not pem:
                    try:
                        pem = hsm.get_public_key(info.key_identifier)
                    except Exception as e:
                        logger.info(f"HSM key {info.label!r} on {provider.name}: public key unreadable: {e}")
                        pem = None
                    info.public_key_pem = pem
                out.append((info, _spki_of_pem(pem) if pem else None))
            return out
    except HsmSecretUnreadable as e:
        raise AttachRefused(str(e))
    except (HsmError, OSError, RuntimeError) as e:
        logger.warning(f"HSM provider {provider.name} unreachable while matching a CA key: {e}")
        raise AttachRefused('The HSM provider could not be reached', 502)


def _holder_of(spki):
    """Name of the authority that holds a key row with this public key, else None."""
    for key_id, bound in key_binding._bound_spki().items():
        if bound == spki:
            return key_binding.holders(key_id=key_id)[0]
    return None


def compatible_keys(ca, provider_id):
    """The provider's keys whose public key is the CA certificate's, each with the authority holding it."""
    cert = keyless_ca_certificate(ca)
    provider = _provider(provider_id)
    rows = {k.key_identifier: k for k in HsmKey.query.filter_by(provider_id=provider.id)}
    keys = []
    for info, spki in _token_keys(provider):
        if not matches_certificate(info.public_key_pem, cert):
            continue
        row = rows.get(info.key_identifier)
        # A bound row without a cached public key is matched by its id, not its SPKI
        held = (key_binding.holders(key_id=row.id) if row else None) or [None]
        keys.append({'key_identifier': info.key_identifier, 'label': info.label, 'algorithm': info.algorithm,
                     'hsm_key_id': row.id if row else None, 'held_by': held[0] or _holder_of(spki),
                     'refusal': HsmService.algorithm_refusal(provider.type, info.algorithm)})
    return sorted(keys, key=lambda k: (k['label'], k['key_identifier']))


def _key_row_for(provider, info):
    """The key row naming *info* on *provider*, created or refreshed from the token's reading."""
    # Under the provider lock, as sync_keys: a sync adding this key commits first, then it is found
    HsmService._lock_provider(provider.id)
    row = HsmKey.query.filter_by(provider_id=provider.id, key_identifier=info.key_identifier).first()
    if row is None:
        row = HsmKey(provider_id=provider.id, key_identifier=info.key_identifier, label=info.label,
                     algorithm=info.algorithm, key_type=info.key_type, purpose=info.purpose,
                     is_extractable=info.is_extractable,
                     extra_data=json.dumps(info.metadata) if info.metadata else None)
        db.session.add(row)
    # The token is the truth: a stale cached public key or label is replaced by what it reads now
    row.public_key_pem = info.public_key_pem
    row.label, row.algorithm, row.purpose = info.label, info.algorithm, info.purpose
    return row


def _prove(ca, cert, key_row):
    """AttachRefused unless the token key signs a CRL that the certificate's public key verifies."""
    from services.hsm.ca_key_loader import bind_signature_scheme
    from services.hsm.hsm_private_key import load_hsm_private_key
    from utils.signing_hash import rsa_padding_for, signing_hash_for
    try:
        key = bind_signature_scheme(load_hsm_private_key(key_row.id), ca.signature_scheme)
        now = utc_now()
        builder = (x509.CertificateRevocationListBuilder().issuer_name(cert.subject)
                   .last_update(now).next_update(now + timedelta(minutes=1)))
        digest = signing_hash_for(key)
        proof = builder.sign(key, digest, rsa_padding=rsa_padding_for(key, digest))
    except HsmError as e:
        logger.warning(f"HSM key {key_row.label!r} could not sign the attachment proof: {e}")
        raise AttachRefused('The HSM key could not sign: the HSM provider refused or could not be reached', 502)
    except Exception as e:
        logger.warning(f"HSM key {key_row.label!r} could not sign the attachment proof: {e}")
        raise AttachRefused('The HSM key did not produce a signature the CA certificate verifies')
    if not proof.is_signature_valid(cert.public_key()):
        raise AttachRefused('The HSM key did not produce a signature the CA certificate verifies')


def _refuse_signing(ca, cert, provider, algorithm):
    """AttachRefused when *provider* cannot sign for *ca* with this key, under its signature scheme."""
    from services.ca.signature_scheme import pss_refusal
    from utils.key_type import weak_ca_key_refusal
    refusal = (HsmService.algorithm_refusal(provider.type, algorithm)
               or weak_ca_key_refusal(cert.public_key()))
    if not refusal and ca.signature_scheme == 'pss':
        from utils import key_algorithms
        refusal = pss_refusal(key_algorithms.family_for_public_key(cert.public_key()) == 'RSA', provider.type)
    if refusal:
        raise AttachRefused(refusal)


def attach(ca_id, provider_id, key_identifier):
    """Bind the token key *key_identifier* of *provider_id* to the keyless CA *ca_id*; returns (ca, key row).

    Commits the key row before the signing proof, so the token round trip holds no lock. The key
    row and the CA are then locked, and the CA's state, the key match, the binding rules and the
    signing refusals (provider algorithm, key size, RSA-PSS, FIPS mode) are checked again.
    """
    ca = db.session.get(CA, ca_id)
    cert = keyless_ca_certificate(ca)
    provider = _provider(provider_id)
    if not key_identifier:
        raise AttachRefused('key_identifier is required')
    info = next((i for i, _ in _token_keys(provider) if i.key_identifier == key_identifier), None)
    if info is None:
        raise AttachRefused('HSM key not found on this provider', 404)
    if not info.public_key_pem or _spki_of_pem(info.public_key_pem) is None:
        raise AttachRefused('The public key of this HSM key could not be read')
    if not matches_certificate(info.public_key_pem, cert):
        raise AttachRefused('HSM key does not match the CA certificate')
    _refuse_signing(ca, cert, provider, info.algorithm)

    key_row = _key_row_for(provider, info)
    db.session.flush()
    HsmService.refuse_signing_in_fips_mode(key_row)
    key_binding.refuse_bound_key(key_row)
    key_binding.refuse_same_token_key(key_row, cert.public_key())
    db.session.commit()
    _prove(ca, cert, key_row)

    key_row = key_binding.lock_key(key_row.id)
    ca = CA.query.filter_by(id=ca_id).with_for_update().populate_existing().one_or_none()
    try:
        cert = keyless_ca_certificate(ca)
        if key_row is None:
            raise AttachRefused('HSM key not found on this provider', 404)
        if not matches_certificate(key_row.public_key_pem, cert):
            raise AttachRefused('HSM key does not match the CA certificate')
        key_binding.refuse_bound_key(key_row)
        key_binding.refuse_same_token_key(key_row, cert.public_key())
        _refuse_signing(ca, cert, provider, key_row.algorithm)
        HsmService.refuse_signing_in_fips_mode(key_row, fetch=False)
    except Exception:
        db.session.rollback()
        raise
    ca.hsm_key_id = key_row.id
    db.session.commit()
    return ca, key_row
