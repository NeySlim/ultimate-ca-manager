"""Distinguished names compared as RFC 5280 §7.1 asks: same RDNs in the same order, each the
same set of attribute types, values equal once prepared (RFC 4518 for directory strings)."""
import hashlib
import json
import re
import unicodedata

from cryptography import x509
from cryptography.x509.name import _ASN1Type
from cryptography.x509.oid import NameOID

_DIRECTORY_STRINGS = frozenset({_ASN1Type.UTF8String, _ASN1Type.PrintableString, _ASN1Type.BMPString,
                                _ASN1Type.UniversalString, _ASN1Type.T61String})
# RFC 4518 §2.2: mapped to nothing, then to SPACE
_TO_NOTHING = re.compile('[\u00ad\u034f\u1806\u180b-\u180d\ufe00-\ufe0f\ufffc\u200b'
                         '\u0000-\u0008\u000e-\u001f\u007f-\u0084\u0086-\u009f]')
_TO_SPACE = re.compile('[\u0009-\u000d\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]')
_SPACES = re.compile(' +')
_ASCII_LOWER = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')


def _directory_string(value):
    """RFC 4518 steps 2, 3 and 6 for caseIgnoreMatch: map (case fold included), NFKC, spaces."""
    value = _TO_SPACE.sub(' ', _TO_NOTHING.sub('', value)).casefold()
    value = unicodedata.normalize('NFKC', value).casefold()
    return _SPACES.sub(' ', value).strip(' ')


def _prepared_value(attribute):
    value = attribute.value
    if isinstance(value, bytes):
        return 'bytes:' + value.hex()
    if attribute.oid == NameOID.DOMAIN_COMPONENT:
        # RFC 5280 §7.3: a domain label, compared without regard to ASCII case
        return value.translate(_ASCII_LOWER)
    if attribute.oid == NameOID.EMAIL_ADDRESS:
        # RFC 5280 §7.5: the local part is exact, the host is not case sensitive
        local, at, host = value.rpartition('@')
        return f'{local}{at}{host.lower()}'
    if getattr(attribute, '_type', None) in _DIRECTORY_STRINGS:
        return _directory_string(value)
    return value


def prepared_name(name: x509.Name):
    """The form two equal names share: per RDN, the sorted (type, prepared value) pairs."""
    return tuple(tuple(sorted((a.oid.dotted_string, _prepared_value(a)) for a in rdn)) for rdn in name.rdns)


def same_name(a: x509.Name, b: x509.Name) -> bool:
    return prepared_name(a) == prepared_name(b)


def name_key(name: x509.Name) -> str:
    """SHA-256 (hex) of ``prepared_name``: what an index finds equal names by."""
    encoded = json.dumps(prepared_name(name), ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()
