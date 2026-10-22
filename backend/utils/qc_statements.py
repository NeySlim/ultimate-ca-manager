"""qcStatements (RFC 3739, ETSI EN 319 412-5) and the certificate policies of a template.

One module for the whole chain: validate the template's ``qc_statements`` /
``certificate_policies``, build the extension DER, merge the policies, decode
the extension for display. Out of scope: QcIdentMethod, QcQSCDlegislation and
the PSD2 statements (ETSI TS 119 495).
"""
import re
from typing import List, Optional

from asn1crypto import core as asn1
from cryptography import x509

QC_STATEMENTS_OID = x509.ObjectIdentifier('1.3.6.1.5.5.7.1.3')
ANY_POLICY_OID = '2.5.29.32.0'

_QCS = '0.4.0.1862.1.'
OID_COMPLIANCE = _QCS + '1'
OID_LIMIT_VALUE = _QCS + '2'
OID_RETENTION = _QCS + '3'
OID_SSCD = _QCS + '4'
OID_PDS = _QCS + '5'
OID_TYPE = _QCS + '6'
OID_CC_LEGISLATION = _QCS + '7'
OID_QCS_SYNTAX_V2 = '1.3.6.1.5.5.7.11.2'

QC_TYPES = {'esign': OID_TYPE + '.1', 'eseal': OID_TYPE + '.2', 'web': OID_TYPE + '.3'}
SEMANTICS = {
    'natural': '0.4.0.194121.1.1', 'legal': '0.4.0.194121.1.2',
    'eidas-natural': '0.4.0.194121.1.3', 'eidas-legal': '0.4.0.194121.1.4',
}
ALLOWED_KEYS = ('compliance', 'cc_legislation', 'type', 'sscd', 'pds',
                'retention_period', 'limit_value', 'semantics')

MAX_POLICY_OIDS = 20
MAX_PDS = 10
MAX_URL_LENGTH = 2048
_MAX_INT = 10 ** 12
_OID_RE = re.compile(r'^[0-2](\.(0|[1-9][0-9]*))+$')
_CCY_RE = re.compile(r'^[A-Z]{3}$')
_COUNTRY_RE = re.compile(r'^[A-Z]{2}$')
_LANG_RE = re.compile(r'^[a-z]{2}$')


# ── validation ──────────────────────────────────────────────────────────────

def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_policy_oids(value) -> List[str]:
    """Errors for a template's ``certificate_policies`` (list of dotted OIDs)."""
    if value is None:
        return []
    if not isinstance(value, list):
        return ['certificate_policies must be a list of OIDs']
    if len(value) > MAX_POLICY_OIDS:
        return [f'certificate_policies accepts at most {MAX_POLICY_OIDS} OIDs']
    errors = []
    for oid in value:
        if not isinstance(oid, str) or not _OID_RE.match(oid.strip()):
            errors.append(f'Invalid certificate policy OID: {oid!r}')
            continue
        try:
            x509.ObjectIdentifier(oid.strip())
        except ValueError:
            errors.append(f'Invalid certificate policy OID: {oid!r}')
    if not errors and len({o.strip() for o in value}) != len(value):
        errors.append('certificate_policies contains a duplicate OID')
    return errors


def _validate_pds(pds) -> List[str]:
    if not isinstance(pds, list) or not pds:
        return ['qc_statements.pds must be a non-empty list of {url, language}']
    if len(pds) > MAX_PDS:
        return [f'qc_statements.pds accepts at most {MAX_PDS} entries']
    errors, languages = [], []
    for item in pds:
        if not isinstance(item, dict) or set(item) - {'url', 'language'}:
            errors.append('qc_statements.pds entries must be {url, language}')
            continue
        url, lang = item.get('url'), item.get('language')
        if (not isinstance(url, str) or not url.startswith('https://') or len(url) <= 8
                or len(url) > MAX_URL_LENGTH or not url.isascii()
                or any(c.isspace() for c in url)):
            errors.append(f'qc_statements.pds url must be an https URL: {url!r}')
        if not isinstance(lang, str) or not _LANG_RE.match(lang):
            errors.append(f'qc_statements.pds language must be a lowercase ISO 639-1 code: {lang!r}')
        else:
            languages.append(lang)
    if not errors and 'en' not in languages:
        errors.append('qc_statements.pds needs one entry in English (EN 319 412-5, 4.3.4)')
    return errors


def validate_qc_statements(qc) -> List[str]:
    """Errors for a template's ``qc_statements`` dict ([] when valid or unset)."""
    if qc is None:
        return []
    if not isinstance(qc, dict):
        return ['qc_statements must be an object']
    errors = [f'Unknown qc_statements key: {k}' for k in qc if k not in ALLOWED_KEYS]
    if 'compliance' in qc and not isinstance(qc['compliance'], bool):
        errors.append('qc_statements.compliance must be true or false')
    if 'sscd' in qc and not isinstance(qc['sscd'], bool):
        errors.append('qc_statements.sscd must be true or false')
    if 'cc_legislation' in qc:
        cc = qc['cc_legislation']
        if (not isinstance(cc, list) or not cc
                or any(not isinstance(c, str) or not _COUNTRY_RE.match(c) for c in cc)):
            errors.append('qc_statements.cc_legislation must be a non-empty list of '
                          'uppercase ISO 3166 alpha-2 country codes')
        elif len(set(cc)) != len(cc):
            errors.append('qc_statements.cc_legislation contains a duplicate country')
        if qc.get('compliance') is True:
            errors.append('qc_statements.cc_legislation and compliance are mutually '
                          'exclusive (EN 319 412-5, 4.2.4)')
    if 'type' in qc and qc['type'] not in QC_TYPES:
        errors.append('qc_statements.type must be one of: ' + ', '.join(QC_TYPES))
    if 'semantics' in qc and qc['semantics'] not in SEMANTICS:
        errors.append('qc_statements.semantics must be one of: ' + ', '.join(SEMANTICS))
    if 'pds' in qc:
        errors.extend(_validate_pds(qc['pds']))
    if 'retention_period' in qc:
        rp = qc['retention_period']
        if not _is_int(rp) or not 0 < rp <= 1000:
            errors.append('qc_statements.retention_period must be a whole number of years above 0')
    if 'limit_value' in qc:
        lv = qc['limit_value']
        if (not isinstance(lv, dict) or set(lv) != {'currency', 'amount', 'exponent'}
                or not isinstance(lv['currency'], str) or not _CCY_RE.match(lv['currency'])
                or not _is_int(lv['amount']) or not 0 <= lv['amount'] <= _MAX_INT
                or not _is_int(lv['exponent']) or not 0 <= lv['exponent'] <= 12):
            errors.append('qc_statements.limit_value must be {currency (ISO 4217 alpha-3), '
                          'amount, exponent} with non-negative integers')
    return errors


def has_qc_statements(qc) -> bool:
    return isinstance(qc, dict) and any(k in qc and qc[k] not in (None, False, [], {}) for k in ALLOWED_KEYS)


# ── DER ─────────────────────────────────────────────────────────────────────

class _Currency(asn1.Choice):
    _alternatives = [('alphabetic', asn1.PrintableString), ('numeric', asn1.Integer)]


class _MonetaryValue(asn1.Sequence):
    _fields = [('currency', _Currency), ('amount', asn1.Integer), ('exponent', asn1.Integer)]


class _PdsLocation(asn1.Sequence):
    _fields = [('url', asn1.IA5String), ('language', asn1.PrintableString)]


class _PdsLocations(asn1.SequenceOf):
    _child_spec = _PdsLocation


class _Countries(asn1.SequenceOf):
    _child_spec = asn1.PrintableString


class _Oids(asn1.SequenceOf):
    _child_spec = asn1.ObjectIdentifier


class _Semantics(asn1.Sequence):
    _fields = [('semanticsIdentifier', asn1.ObjectIdentifier, {'optional': True})]


class _Statement(asn1.Sequence):
    _fields = [('statementId', asn1.ObjectIdentifier), ('statementInfo', asn1.Any, {'optional': True})]


class _Statements(asn1.SequenceOf):
    _child_spec = _Statement


def _statement(oid, info=None):
    return _Statement({'statementId': oid, 'statementInfo': info}) if info is not None \
        else _Statement({'statementId': oid})


def build_qc_statements_der(qc: dict) -> bytes:
    """DER of the QCStatements for a validated ``qc_statements`` dict."""
    items = []
    if qc.get('compliance'):
        items.append(_statement(OID_COMPLIANCE))
    if qc.get('limit_value'):
        lv = qc['limit_value']
        items.append(_statement(OID_LIMIT_VALUE, _MonetaryValue({
            'currency': _Currency(name='alphabetic', value=lv['currency']),
            'amount': lv['amount'], 'exponent': lv['exponent']})))
    if qc.get('retention_period'):
        items.append(_statement(OID_RETENTION, asn1.Integer(qc['retention_period'])))
    if qc.get('sscd'):
        items.append(_statement(OID_SSCD))
    if qc.get('pds'):
        items.append(_statement(OID_PDS, _PdsLocations([
            {'url': p['url'], 'language': p['language']} for p in qc['pds']])))
    if qc.get('type'):
        items.append(_statement(OID_TYPE, _Oids([QC_TYPES[qc['type']]])))
    if qc.get('cc_legislation'):
        items.append(_statement(OID_CC_LEGISLATION, _Countries(list(qc['cc_legislation']))))
    if qc.get('semantics'):
        items.append(_statement(OID_QCS_SYNTAX_V2, _Semantics(
            {'semanticsIdentifier': SEMANTICS[qc['semantics']]})))
    return _Statements(items).dump()


def qc_statements_extension(tpl_ext) -> Optional[x509.UnrecognizedExtension]:
    """The non-critical qcStatements extension a template asks for, else None."""
    qc = tpl_ext.get('qc_statements') if isinstance(tpl_ext, dict) else None
    if not has_qc_statements(qc) or validate_qc_statements(qc):
        return None
    return x509.UnrecognizedExtension(QC_STATEMENTS_OID, build_qc_statements_der(qc))


def add_qc_statements(builder: x509.CertificateBuilder, tpl_ext) -> x509.CertificateBuilder:
    """Add the template's qcStatements to *builder* unless it already has them."""
    ext = qc_statements_extension(tpl_ext)
    if ext is None or any(e.oid == QC_STATEMENTS_OID for e in builder._extensions):
        return builder
    return builder.add_extension(ext, critical=False)


# ── certificate policies ────────────────────────────────────────────────────

def template_policy_oids(tpl_ext) -> List[str]:
    """Valid, de-duplicated policy OIDs of a template, in order."""
    raw = tpl_ext.get('certificate_policies') if isinstance(tpl_ext, dict) else None
    if validate_policy_oids(raw) or not raw:
        return []
    return [o.strip() for o in raw]


def build_certificate_policies(cps_uri, cps_oid, extra_oids=()) -> Optional[x509.CertificatePolicies]:
    """The CA's CPS policy first, then *extra_oids* (de-duplicated); None when empty."""
    infos, seen = [], set()
    if cps_uri:
        oid = cps_oid or ANY_POLICY_OID
        infos.append(x509.PolicyInformation(x509.ObjectIdentifier(oid), [cps_uri]))
        seen.add(oid)
    for oid in extra_oids or ():
        if oid not in seen:
            seen.add(oid)
            infos.append(x509.PolicyInformation(x509.ObjectIdentifier(oid), None))
    return x509.CertificatePolicies(infos) if infos else None


def add_certificate_policies(builder, cps_uri, cps_oid, extra_oids=()):
    """Add the CA's CPS policy plus the template's OIDs as one CertificatePolicies."""
    ext = build_certificate_policies(cps_uri, cps_oid, extra_oids)
    return builder if ext is None else builder.add_extension(ext, critical=False)


def carried_policy_oids(certificate, cps_oid) -> List[str]:
    """Qualifier-less policy OIDs of a certificate other than the CA's own (for renewal)."""
    try:
        policies = certificate.extensions.get_extension_for_class(x509.CertificatePolicies).value
    except x509.ExtensionNotFound:
        return []
    own = cps_oid or ANY_POLICY_OID
    return [p.policy_identifier.dotted_string for p in policies
            if not p.policy_qualifiers and p.policy_identifier.dotted_string != own]


# ── decoding ────────────────────────────────────────────────────────────────

def decode_qc_statements(der: bytes) -> Optional[dict]:
    """The template-style dict of a qcStatements extension value, plus ``other``
    (OIDs of statements outside the template vocabulary); None when unparseable."""
    try:
        out, other = {}, []
        for st in _Statements.load(der):
            oid = st['statementId'].dotted
            info = st['statementInfo']
            full = None if isinstance(info, asn1.Void) else info.dump()
            if oid == OID_COMPLIANCE:
                out['compliance'] = True
            elif oid == OID_SSCD:
                out['sscd'] = True
            elif oid == OID_LIMIT_VALUE and full:
                mv = _MonetaryValue.load(full)
                out['limit_value'] = {'currency': str(mv['currency'].chosen.native),
                                      'amount': mv['amount'].native,
                                      'exponent': mv['exponent'].native}
            elif oid == OID_RETENTION and full:
                out['retention_period'] = asn1.Integer.load(full).native
            elif oid == OID_PDS and full:
                out['pds'] = [{'url': p['url'].native, 'language': p['language'].native}
                              for p in _PdsLocations.load(full)]
            elif oid == OID_TYPE and full:
                codes = {v: k for k, v in QC_TYPES.items()}
                types = [codes.get(o.dotted, o.dotted) for o in _Oids.load(full)]
                out['type'] = types[0] if types else None
            elif oid == OID_CC_LEGISLATION and full:
                out['cc_legislation'] = [c.native for c in _Countries.load(full)]
            elif oid == OID_QCS_SYNTAX_V2 and full:
                sem = _Semantics.load(full)['semanticsIdentifier'].native
                out['semantics'] = {v: k for k, v in SEMANTICS.items()}.get(sem, sem)
            else:
                other.append(oid)
        if other:
            out['other'] = other
        return out
    except (ValueError, TypeError, KeyError):
        return None


def describe_qc_extension(ext) -> Optional[dict]:
    """Display form of a certificate's qcStatements extension (``critical`` included)."""
    value = getattr(ext.value, 'value', None)
    decoded = decode_qc_statements(value) if isinstance(value, bytes) else None
    return None if decoded is None else {**decoded, 'critical': ext.critical}
