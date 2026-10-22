"""What a signing CA is, for the rules that bind it: signature scheme and key storage.

``enforce_rules`` reads these two facts from a CA row or a loaded CA key.
"""
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
    """Whether an HSM provider row is SoftHSM: a PKCS#11 provider whose module
    path or name says softhsm."""
    if provider is None or provider.type != 'pkcs11':
        return False
    module = str((provider.get_config() or {}).get('module_path') or '')
    return 'softhsm' in module.lower() or 'softhsm' in (provider.name or '').lower()


# Providers whose keys are all in hardware; a cloud key says so key by key
_HARDWARE_PROVIDERS = ('pkcs11', 'aws-cloudhsm')
_CLOUD_PROVIDERS = ('azure-keyvault', 'google-kms')


def storage_for_provider(provider, protection_level=None):
    """``softhsm`` / ``hsm`` / ``software`` for a key on *provider*: a cloud key
    is an HSM key only when its protection level is HSM, an OpenBao key never."""
    if provider is None:
        return 'software'
    if provider.type in _HARDWARE_PROVIDERS:
        return 'softhsm' if softhsm_provider(provider) else 'hsm'
    if provider.type in _CLOUD_PROVIDERS and str(protection_level or '').upper() == 'HSM':
        return 'hsm'
    return 'software'


def storage_for_new_key(provider):
    """Storage of a key UCM is about to generate on *provider*: Azure always
    asks for an HSM key, Google for the provider's protection level."""
    level = None
    if provider is not None and provider.type == 'azure-keyvault':
        level = 'HSM'
    elif provider is not None and provider.type == 'google-kms':
        level = (provider.get_config() or {}).get('protection_level', 'HSM')
    return storage_for_provider(provider, level)


def storage_for_hsm_key(hsm_key):
    """Storage of a stored HSM key row; ``software`` when the row, its provider
    or its protection level cannot be read, so an HSM rule fails closed."""
    if hsm_key is None:
        return 'software'
    try:
        provider = hsm_key.provider
        level = None
        if provider is not None and provider.type in _CLOUD_PROVIDERS:
            level = (hsm_key.get_metadata() or {}).get('protection_level')
        return storage_for_provider(provider, level)
    except Exception:
        return 'software'


def storage_of_ca(ca):
    """``software`` / ``softhsm`` / ``hsm`` for a CA row's key."""
    return storage_for_hsm_key(ca.hsm_key) if ca.hsm_key_id else 'software'


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
        return scheme, storage_of_ca(signer)
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


def normalize_certification(value):
    """``(certification or None, error)``: blank means not declared, anything
    else must be one of ``HsmProvider.CERTIFICATIONS``."""
    from models.hsm import HsmProvider
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    if not isinstance(value, str) or value.strip() not in HsmProvider.CERTIFICATIONS:
        return None, f'certification must be one of: {", ".join(HsmProvider.CERTIFICATIONS)}'
    return value.strip(), None


def certification_for_provider(provider):
    """The certification declared for an HSM provider row; None when not declared."""
    return normalize_certification(getattr(provider, 'certification', None))[0] if provider is not None else None


def certification_for_hsm_key(hsm_key):
    """Certification declared for the provider of a stored HSM key row; None when unreadable."""
    try:
        return certification_for_provider(hsm_key.provider) if hsm_key is not None else None
    except Exception:
        return None


def certification_of(signer):
    """Certification declared for the HSM holding the key of *signer* (a CA row or
    a loaded CA signing key); None for a software key or when not declared."""
    if signer is None:
        return None
    from models import CA, db
    from models.hsm import HsmKey
    if isinstance(signer, CA):
        return certification_for_hsm_key(signer.hsm_key) if signer.hsm_key_id else None
    hsm_id = getattr(signer, '_hsm_key_id', None)
    return certification_for_hsm_key(db.session.get(HsmKey, hsm_id)) if hsm_id is not None else None
