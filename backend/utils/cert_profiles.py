"""Key Usage / Extended Key Usage profiles per certificate type.

One table for every issuance path (direct form, approval workflow), so a
request issued through an approval gets the same certificate as the same
request issued directly (self-review of #347).
"""
from cryptography.x509.oid import ExtendedKeyUsageOID


def _ku(**flags):
    base = dict(digital_signature=True, key_encipherment=False, content_commitment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False)
    base.update(flags)
    return base


CERT_PROFILES = {
    'server': {'ku': _ku(key_encipherment=True), 'eku': [ExtendedKeyUsageOID.SERVER_AUTH]},
    'client': {'ku': _ku(), 'eku': [ExtendedKeyUsageOID.CLIENT_AUTH]},
    'combined': {'ku': _ku(key_encipherment=True),
                 'eku': [ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]},
    'code_signing': {'ku': _ku(), 'eku': [ExtendedKeyUsageOID.CODE_SIGNING]},
    'email': {'ku': _ku(key_encipherment=True, content_commitment=True),
              'eku': [ExtendedKeyUsageOID.EMAIL_PROTECTION]},
    # No implied EKU: only extra_ekus / template EKUs end up in the cert
    'custom': {'ku': _ku(), 'eku': []},
}


def profile_for(cert_type):
    """A fresh copy of the profile for *cert_type* (server when unknown)."""
    profile = CERT_PROFILES.get(cert_type, CERT_PROFILES['server'])
    return {'ku': dict(profile['ku']), 'eku': list(profile['eku'])}
