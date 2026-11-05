"""Custom X.509 extensions (#437): an OID and the DER bytes of its value.

The value is copied into the extension as given and never parsed. OIDs UCM
sets itself, or that the X.509 parser models, are refused: a malformed value
under one of those would make the certificate unreadable.
"""
import base64
import binascii
import json
import re
from typing import Optional, Tuple

from cryptography import x509
from cryptography.x509.oid import ExtensionOID

MAX_VALUE_BYTES = 4096
MAX_EXTENSIONS = 20
MAX_OID_LENGTH = 128
_OID_RE = re.compile(r'^[0-2](\.(0|[1-9][0-9]*))+$')
_HEX_RE = re.compile(r'^[0-9a-fA-F]*$')
_HEX_SEPARATORS = re.compile(r'[\s:]')
_ENTRY_KEYS = {'oid', 'critical', 'value', 'value_base64'}

# Extensions UCM builds without pyca knowing them
_UCM_EXTENSIONS = {
    '1.3.6.1.5.5.7.1.3': 'qcStatements',
    '1.3.6.1.5.5.7.1.31': 'acmeIdentifier',
    '1.3.6.1.5.5.7.1.36': 'relatedCertificate',
    '1.3.6.1.4.1.311.25.2': 'ntdsCaSecurityExt',
}
RESERVED_OIDS = {
    **{oid.dotted_string: oid._name for oid in vars(ExtensionOID).values()
       if isinstance(oid, x509.ObjectIdentifier)},
    **_UCM_EXTENSIONS,
}
# Display names for OIDs pyca does not name
_KNOWN_NAMES = {
    **_UCM_EXTENSIONS,
    '1.3.6.1.4.1.311.20.2': 'msCertificateTemplateName',
    '1.3.6.1.4.1.311.21.1': 'msCaVersion',
    '1.3.6.1.4.1.311.21.2': 'msPreviousCaCertHash',
    '1.3.6.1.4.1.311.21.10': 'msApplicationPolicies',
    '1.3.6.1.5.5.7.1.7': 'ipAddrBlocks',
    '1.3.6.1.5.5.7.1.8': 'autonomousSysIds',
    '2.16.840.1.113730.1.1': 'nsCertType',
    '2.16.840.1.113730.1.13': 'nsComment',
}


def _value_bytes(entry, where) -> Tuple[Optional[bytes], Optional[str]]:
    has_hex, has_b64 = 'value' in entry, 'value_base64' in entry
    if has_hex == has_b64:
        return None, f'{where}: give the value as hex in "value" (or base64 in "value_base64")'
    raw = entry['value'] if has_hex else entry['value_base64']
    if not isinstance(raw, str) or len(raw) > 3 * MAX_VALUE_BYTES + 64:
        return None, f'{where}: the value must be a string of at most {MAX_VALUE_BYTES} bytes'
    if has_hex:
        text = _HEX_SEPARATORS.sub('', raw)
        if not _HEX_RE.match(text) or len(text) % 2:
            return None, f'{where}: the value is not an even number of hex digits'
        value = bytes.fromhex(text)
    else:
        try:
            value = base64.b64decode(''.join(raw.split()), validate=True)
        except (binascii.Error, ValueError):
            return None, f'{where}: value_base64 is not valid base64'
    if not value:
        return None, f'{where}: the value is empty'
    if len(value) > MAX_VALUE_BYTES:
        return None, f'{where}: the value exceeds {MAX_VALUE_BYTES} bytes'
    return value, None


def validate_custom_extensions(raw, field='custom_extensions') -> Tuple[Optional[list], Optional[str]]:
    """``(entries, None)`` with each entry ``{oid, critical, value}`` (lowercase hex),
    or ``(None, error)``. None and an empty list give ``[]``."""
    if raw is None or raw == '':
        return [], None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return None, f'{field} is not valid JSON'
    if not isinstance(raw, list):
        return None, f'{field} must be a list of {{oid, critical, value}}'
    if len(raw) > MAX_EXTENSIONS:
        return None, f'{field} accepts at most {MAX_EXTENSIONS} extensions'
    cleaned, seen = [], set()
    for i, entry in enumerate(raw):
        where = f'{field}[{i}]'
        if not isinstance(entry, dict):
            return None, f'{where} must be an object {{oid, critical, value}}'
        unknown = set(entry) - _ENTRY_KEYS
        if unknown:
            return None, f'{where}: unknown key {sorted(unknown)[0]}'
        oid = entry.get('oid')
        oid = oid.strip() if isinstance(oid, str) else oid
        if not isinstance(oid, str) or len(oid) > MAX_OID_LENGTH or not _OID_RE.match(oid):
            return None, f'{where}: {oid!r} is not a dotted OID'
        try:
            x509.ObjectIdentifier(oid)
        except ValueError:
            return None, f'{where}: {oid!r} is not a valid OID'
        if oid in RESERVED_OIDS:
            return None, (f'{where}: {oid} is the {RESERVED_OIDS[oid]} extension, which UCM '
                          'sets itself; use its dedicated setting')
        if oid in seen:
            return None, f'{where}: {oid} appears more than once'
        seen.add(oid)
        critical = entry.get('critical', False)
        if not isinstance(critical, bool):
            return None, f'{where}: critical must be true or false'
        value, err = _value_bytes(entry, where)
        if err:
            return None, err
        cleaned.append({'oid': oid, 'critical': critical, 'value': value.hex()})
    return cleaned, None


def merge_custom_extensions(*lists) -> list:
    """One entry per OID; a later list replaces an earlier one's entry in place."""
    merged = {}
    for entries in lists:
        for entry in entries or ():
            merged[entry['oid']] = entry
    return list(merged.values())


def template_custom_extensions(template) -> list:
    """The template's validated entries; raises ValueError when the stored list is invalid."""
    raw = getattr(template, 'custom_extensions', None) if template is not None else None
    entries, err = validate_custom_extensions(raw)
    if err:
        raise ValueError(f"Template '{template.name}' holds invalid custom extensions: {err}")
    return entries


def issuance_custom_extensions(template, requested=None) -> list:
    """The template's extensions, then the request's (which win for the same OID)."""
    asked, err = validate_custom_extensions(requested)
    if err:
        raise ValueError(err)
    return merge_custom_extensions(template_custom_extensions(template), asked)


def add_custom_extensions(builder: x509.CertificateBuilder, entries) -> x509.CertificateBuilder:
    """Add each entry the builder does not already carry."""
    present = {e.oid.dotted_string for e in builder._extensions}
    for entry in entries or ():
        if entry['oid'] in present:
            continue
        builder = builder.add_extension(
            x509.UnrecognizedExtension(x509.ObjectIdentifier(entry['oid']), bytes.fromhex(entry['value'])),
            critical=entry['critical'])
        present.add(entry['oid'])
    return builder


def carried_custom_extensions(certificate) -> list:
    """Entries for the extensions of *certificate* a custom list could hold."""
    out = []
    for ext in certificate.extensions:
        if isinstance(ext.value, x509.UnrecognizedExtension) and ext.oid.dotted_string not in RESERVED_OIDS:
            out.append({'oid': ext.oid.dotted_string, 'critical': ext.critical,
                        'value': ext.value.value.hex()})
    return out


def extension_name(oid: x509.ObjectIdentifier) -> Optional[str]:
    name = getattr(oid, '_name', None)
    if name and name != 'Unknown OID':
        return name
    return _KNOWN_NAMES.get(oid.dotted_string)


def describe_other_extensions(extensions, shown=()) -> list:
    """``[{oid, name, critical, value_hex}]`` for the extensions whose OID is not in *shown*."""
    skip = {o.dotted_string if isinstance(o, x509.ObjectIdentifier) else o for o in shown}
    out = []
    for ext in extensions:
        oid = ext.oid.dotted_string
        if oid in skip:
            continue
        if isinstance(ext.value, x509.UnrecognizedExtension):
            value = ext.value.value
        else:
            try:
                value = ext.value.public_bytes()
            except (NotImplementedError, ValueError, AttributeError):
                value = None
        out.append({'oid': oid, 'name': extension_name(ext.oid), 'critical': ext.critical,
                    'value_hex': value.hex() if value is not None else None})
    return out
