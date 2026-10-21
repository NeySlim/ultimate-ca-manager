"""Compliance profiles: policies in code, aligned with a versioned reference text.

A CA with a profile is bound by it as FIPS mode binds every CA (the two
intersect). ``allowed_key_types`` and ``allowed_digests`` are enforced today;
the other keys are read by the rule engine as it learns them. ``advisories``
holds rules in the same syntax that produce notices, never refusals.
"""
import logging

logger = logging.getLogger(__name__)

DEFAULT_SETTING = 'compliance_profile_default'

_DIGESTS = ['sha256', 'sha384', 'sha512']
_NIST_EC = ['EC-P256', 'EC-P384', 'EC-P521']
_RSA_STRONG = ['RSA-3072', 'RSA-4096']
_EDWARDS = ['ED25519', 'ED448']

PROFILES = {
    'anssi': {
        'title': 'ANSSI',
        'reference': 'ANSSI-PG-083 3.00',
        'url': 'https://messervices.cyber.gouv.fr/documents-guides/anssi-guide-mecanismes-crypto-3.00.pdf',
        'rules': {
            'allowed_key_types': ['RSA-2048'] + _RSA_STRONG + _NIST_EC + _EDWARDS,
            'allowed_digests': _DIGESTS,
            'allowed_signature_schemes': ['rsa_pkcs1v15', 'rsa_pss', 'ecdsa', 'eddsa'],
            'key_type_horizons': {'RSA-2048': '2030-12-31'},
            'require_hsm_ca_key': False,
            'pq_standalone': True,
            'tsa_signer_key_types': [],
            'advisories': {
                'allowed_key_types': _RSA_STRONG + _NIST_EC,
                'allowed_signature_schemes': ['rsa_pss', 'ecdsa'],
                'tsa_signer_key_types': _NIST_EC,
            },
        },
    },
    'bsi': {
        'title': 'BSI',
        'reference': 'BSI-TR-02102-1 2026-01',
        'url': 'https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/Publications/'
               'TechGuidelines/TG02102/BSI-TR-02102-1.pdf',
        'rules': {
            'allowed_key_types': _RSA_STRONG + _NIST_EC,
            'allowed_digests': _DIGESTS,
            'allowed_signature_schemes': ['rsa_pss', 'ecdsa'],
            'key_type_horizons': {},
            'require_hsm_ca_key': False,
            'pq_standalone': True,
            'tsa_signer_key_types': _NIST_EC,
            'advisories': {
                'allowed_key_types': _RSA_STRONG,
                'key_type_horizons': {k: '2035-12-31' for k in _RSA_STRONG + _NIST_EC},
            },
        },
    },
    'eu-acm': {
        'title': 'EU ACM',
        'reference': 'ECCG-ACM 2.0',
        'url': 'https://certification.enisa.europa.eu/publications/eucc-guidelines-cryptography_en',
        'rules': {
            'allowed_key_types': ['RSA-2048'] + _RSA_STRONG + _NIST_EC,
            'allowed_digests': _DIGESTS,
            'allowed_signature_schemes': ['rsa_pkcs1v15', 'rsa_pss', 'ecdsa'],
            'key_type_horizons': {'RSA-2048': '2028-12-31'},
            'key_type_issue_until': {'RSA-2048': '2026-12-31'},
            'require_hsm_ca_key': True,
            'pq_standalone': True,
            'tsa_signer_key_types': [],
            'advisories': {
                'allowed_key_types': _RSA_STRONG + _NIST_EC,
                'allowed_signature_schemes': ['rsa_pss', 'ecdsa'],
                'tsa_signer_key_types': _NIST_EC,
            },
        },
    },
}

PROFILE_NAMES = tuple(PROFILES)


def is_valid(name):
    return isinstance(name, str) and name in PROFILES


def normalize(value):
    """``(name or None, error)``: blank means no profile, anything else must be listed."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, None
    if not isinstance(value, str) or value.strip().lower() not in PROFILES:
        return None, f'complianceProfile must be one of: {", ".join(PROFILE_NAMES)}'
    return value.strip().lower(), None


def profile_policy(name):
    """The ``SystemPolicy`` of profile *name*; ValueError when it is not listed."""
    from services.policy_service import SystemPolicy
    if not is_valid(name):
        raise ValueError(f'Unknown compliance profile {name!r}')
    profile = PROFILES[name]
    return SystemPolicy(f'Compliance profile {name} ({profile["reference"]})',
                        profile['rules'], kind='profile')


def default_profile():
    """The profile new CAs receive when the request names none (None when unset)."""
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=DEFAULT_SETTING).first()
    value = (row.value or '').strip().lower() if row else ''
    return value if is_valid(value) else None


def profile_of_ca(ca_id):
    """The stored profile of CA *ca_id* (None for no CA, no profile, or a name not listed)."""
    if ca_id is None:
        return None
    from models import CA, db
    ca = db.session.get(CA, ca_id)
    name = getattr(ca, 'compliance_profile', None)
    return name if is_valid(name) else None
