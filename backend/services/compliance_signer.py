"""What a signing CA is, for the rules that bind it: signature scheme and key storage.

``enforce_rules`` reads these two facts from a CA row or a loaded CA key.
"""
import os

from utils import key_algorithms

SCHEMES = ('rsa_pkcs1v15', 'rsa_pss', 'ecdsa', 'eddsa', 'ml_dsa', 'slh_dsa')
STORAGES = ('software', 'softhsm', 'hsm')


def scheme_for(public_key, signature_scheme=None):
    """``rsa_pkcs1v15`` / ``rsa_pss`` / ``ecdsa`` / ``eddsa`` for a key and the
    scheme ('pkcs1v15' or 'pss') its CA signs RSA with; None when unknown."""
    family = key_algorithms.family_for_public_key(public_key)
    if family == 'RSA':
        return 'rsa_pss' if signature_scheme == 'pss' else 'rsa_pkcs1v15'
    if family == 'EC':
        return 'ecdsa'
    if family in ('ED25519', 'ED448'):
        return 'eddsa'
    return None


def softhsm_provider(provider):
    """Whether an HSM provider row is SoftHSM: a PKCS#11 module named softhsm."""
    if provider is None or provider.type != 'pkcs11':
        return False
    module = (provider.get_config() or {}).get('module_path') or ''
    return 'softhsm' in os.path.basename(str(module)).lower()


def storage_for_hsm_key(hsm_key):
    """``softhsm`` / ``hsm`` for a stored HSM key row (``hsm`` when it cannot be told)."""
    try:
        return 'softhsm' if softhsm_provider(hsm_key.provider) else 'hsm'
    except Exception:
        return 'hsm'


def describe(signer):
    """``(scheme, storage)`` of *signer*: a CA row or a loaded CA signing key.
    Either is None when it cannot be told."""
    if signer is None:
        return None, None
    from models import CA
    if isinstance(signer, CA):
        from services.ca.signature_scheme import ca_public_key
        try:
            public = ca_public_key(signer)
        except Exception:
            public = None
        scheme = scheme_for(public, signer.signature_scheme) if public is not None else None
        storage = storage_for_hsm_key(signer.hsm_key) if signer.hsm_key_id else 'software'
        return scheme, storage
    try:
        public = signer.public_key()
    except Exception:
        return None, None
    scheme = scheme_for(public, getattr(signer, 'signature_scheme', None))
    hsm_id = getattr(signer, '_hsm_key_id', None)
    if hsm_id is None:
        return scheme, 'software'
    from models import db
    from models.hsm import HsmKey
    return scheme, storage_for_hsm_key(db.session.get(HsmKey, hsm_id))
