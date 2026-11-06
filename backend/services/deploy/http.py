"""HTTP transport for deploy targets (discussion #428).

One request per push: the target's URL and body template are rendered with
the certificate's material, headers carry the API credential. Every value
goes through ``{{ name | filter }}`` so a PEM lands correctly inside JSON,
base64 or a query string.
"""
import base64
import json
import logging
import os
import re
import tempfile
from urllib.parse import quote, urlsplit

from security.encryption import decrypt_text, encrypt_text

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30
MAX_HEADERS = 20
MAX_TEMPLATE_CHARS = 64 * 1024
RESPONSE_TAIL_BYTES = 1024
USER_AGENT = 'UCM-Deploy/1.0'

# The names the admin may use in a template, with the sample value the
# validation renders them with.
VARIABLES = {
    'cert_pem': '-----BEGIN CERTIFICATE-----\nSAMPLE\n-----END CERTIFICATE-----\n',
    'key_pem': '-----BEGIN PRIVATE KEY-----\nSAMPLE\n-----END PRIVATE KEY-----\n',
    'chain_pem': '-----BEGIN CERTIFICATE-----\nISSUER\n-----END CERTIFICATE-----\n',
    'fullchain_pem': ('-----BEGIN CERTIFICATE-----\nSAMPLE\n-----END CERTIFICATE-----\n'
                      '-----BEGIN CERTIFICATE-----\nISSUER\n-----END CERTIFICATE-----\n'),
    'name': 'Sample certificate',
    'refid': 'sample-refid',
    'cn': 'sample.example.net',
    'san_dns': 'sample.example.net,www.example.net',
    'serial': '1234567890',
    'serial_hex': '499602d2',
    'not_before': '2026-01-01T00:00:00Z',
    'not_after': '2027-01-01T00:00:00Z',
    'fingerprint_sha256': '00' * 32,
    'certificate_id': '1',
    'event': 'manual',
}
FILTERS = ('raw', 'json', 'b64', 'urlencode')
_VAR_RE = re.compile(r'\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\|\s*([A-Za-z0-9]+)\s*)?\}\}')
_HEADER_NAME_RE = re.compile(r'^[!#$%&\'*+\-.^_`|~0-9A-Za-z]+$')
# Set by the transport itself or meaningless as a stored value.
RESERVED_HEADERS = {'host', 'content-length', 'transfer-encoding', 'connection', 'expect'}


class DeployHTTPError(Exception):
    """A push that did not succeed and may be retried."""


# ------------------------------------------------------------------ template

def template_variables(template: str):
    """(name, filter) pairs named by *template*; ValueError on an unknown one."""
    found = []
    for match in _VAR_RE.finditer(template or ''):
        name, flt = match.group(1), (match.group(2) or 'raw').lower()
        if name not in VARIABLES:
            raise ValueError(f"Unknown template variable: {name}")
        if flt not in FILTERS:
            raise ValueError(f"Unknown template filter: {flt} (use json, b64 or urlencode)")
        found.append((name, flt))
    return found


def _apply(value: str, flt: str) -> str:
    if flt == 'json':
        return json.dumps(value)
    if flt == 'b64':
        return base64.b64encode(value.encode()).decode()
    if flt == 'urlencode':
        return quote(value, safe='')
    return value


def render(template: str, variables: dict, default_filter: str = 'raw') -> str:
    """Substitute every ``{{ name | filter }}``; a variable the certificate
    cannot provide (no private key) raises ValueError."""
    def substitute(match):
        name, flt = match.group(1), (match.group(2) or default_filter).lower()
        value = variables.get(name)
        if value is None:
            raise ValueError(f"Template variable {name} is not available for this certificate")
        return _apply(value, flt)
    return _VAR_RE.sub(substitute, template or '')


def content_type_for(headers: dict, body: str) -> str:
    """The explicit Content-Type header, else JSON when the body looks like it."""
    for name, value in headers.items():
        if name.lower() == 'content-type':
            return value
    return 'application/json' if body.lstrip()[:1] in ('{', '[') else 'text/plain; charset=utf-8'


def validate_template(template: str, headers: dict, allow_private_key: bool) -> None:
    """Refuse at save time what would fail at push time: unknown names, a
    private key without the opt-in, a JSON body that does not parse."""
    if len(template or '') > MAX_TEMPLATE_CHARS:
        raise ValueError(f"body_template is too long (max {MAX_TEMPLATE_CHARS} chars)")
    names = {name for name, _ in template_variables(template)}
    if 'key_pem' in names and not allow_private_key:
        raise ValueError("body_template uses key_pem: enable 'send private key' on this target first")
    sample = render(template, VARIABLES)
    if 'json' in content_type_for(headers, sample).lower():
        try:
            json.loads(sample)
        except ValueError:
            raise ValueError("body_template does not render valid JSON: write PEM values as "
                             "{{cert_pem|json}} (quotes included) or set a Content-Type header")


def validate_url(url: str, allow_private_key: bool) -> str:
    url = str(url or '').strip()
    if not url or len(url) > 2048:
        raise ValueError('url is required (max 2048 chars)')
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError('url must be an http:// or https:// URL with a host')
    if allow_private_key and parts.scheme != 'https':
        raise ValueError('The private key may only be sent over https')
    if _VAR_RE.search(parts.netloc):
        raise ValueError('Template variables are allowed in the URL path and query, not in the host')
    template_variables(url)
    return url


def url_host_port(url: str):
    parts = urlsplit(url)
    return parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80)


# ------------------------------------------------------------------- headers

def parse_headers(raw) -> dict:
    """Headers from a JSON object or ``Name: value`` lines; names validated,
    reserved ones refused."""
    if raw in (None, ''):
        return {}
    if isinstance(raw, str):
        pairs = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            if ':' not in line:
                raise ValueError(f"Header line without a colon: {line.strip()[:40]}")
            name, value = line.split(':', 1)
            pairs.append((name.strip(), value.strip()))
    elif isinstance(raw, dict):
        pairs = [(str(k).strip(), str(v).strip()) for k, v in raw.items()]
    else:
        raise ValueError('http_headers must be an object or "Name: value" lines')
    headers = {}
    for name, value in pairs:
        if not _HEADER_NAME_RE.match(name):
            raise ValueError(f"Invalid header name: {name[:40]}")
        if name.lower() in RESERVED_HEADERS:
            raise ValueError(f"Header {name} is set by UCM and cannot be configured")
        if any(c in value for c in '\r\n') or len(value) > 4096:
            raise ValueError(f"Invalid value for header {name}")
        headers[name] = value
    if len(headers) > MAX_HEADERS:
        raise ValueError(f"Too many headers (max {MAX_HEADERS})")
    return headers


def store_headers(headers: dict):
    return encrypt_text(json.dumps(headers)) if headers else None


def load_headers(stored) -> dict:
    if not stored:
        return {}
    try:
        data = json.loads(decrypt_text(stored))
    except ValueError:
        logger.error('Deploy target headers could not be read')
        return {}
    return data if isinstance(data, dict) else {}


def validate_ca_pem(pem: str) -> str:
    pem = str(pem or '').strip()
    if not pem:
        return ''
    from cryptography import x509
    try:
        if not x509.load_pem_x509_certificates(pem.encode()):
            raise ValueError
    except ValueError:
        raise ValueError('tls_ca_pem must hold one or more PEM certificates')
    return pem + '\n'


# ----------------------------------------------------------------- variables

def certificate_variables(certificate, leaf_pem: str, chain_pem: str,
                          key_pem=None, event: str = 'manual') -> dict:
    """The values a template may use for *certificate*; key_pem stays absent
    (not empty) when UCM holds none, so a template naming it fails loudly."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID
    cert = x509.load_pem_x509_certificate(leaf_pem.encode())
    cn = ''
    try:
        cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    except (IndexError, ValueError):
        pass
    san_dns = []
    try:
        san_dns = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        pass
    variables = {
        'cert_pem': leaf_pem,
        'chain_pem': chain_pem,
        'fullchain_pem': leaf_pem + chain_pem,
        'name': certificate.descr or certificate.refid or '',
        'refid': certificate.refid or '',
        'cn': cn,
        'san_dns': ','.join(san_dns),
        'serial': str(cert.serial_number),
        'serial_hex': format(cert.serial_number, 'x'),
        'not_before': cert.not_valid_before_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'not_after': cert.not_valid_after_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'fingerprint_sha256': cert.fingerprint(hashes.SHA256()).hex(),
        'certificate_id': str(certificate.id),
        'event': event,
    }
    if key_pem is not None:
        variables['key_pem'] = key_pem
    return variables


# ----------------------------------------------------------------- transport

def _response_tail(response) -> str:
    try:
        chunk = next(response.iter_content(RESPONSE_TAIL_BYTES), b'')
    except Exception:
        chunk = b''
    finally:
        response.close()
    return chunk.decode('utf-8', 'replace')


def _request(target, method: str, url: str, headers: dict, body):
    """One request through the SSRF-vetted client, redirects refused, the
    target's own CA bundle when it has one. Returns (status, tail)."""
    import requests
    from utils.ssrf_protection import safe_request

    ca_file = None
    verify = True
    try:
        if target.tls_ca_pem:
            fd, ca_file = tempfile.mkstemp(prefix='ucm-deploy-ca-', suffix='.pem')
            with os.fdopen(fd, 'w') as handle:
                handle.write(target.tls_ca_pem)
            verify = ca_file
        try:
            response = safe_request(method, url, headers=headers, data=body,
                                    timeout=TIMEOUT_SECONDS, allow_redirects=False,
                                    verify=verify, stream=True)
        except requests.RequestException as e:
            raise DeployHTTPError(f"Request failed: {e}")
        except ValueError as e:
            raise DeployHTTPError(f"URL rejected: {e}")
        return response.status_code, _response_tail(response)
    finally:
        if ca_file:
            try:
                os.unlink(ca_file)
            except OSError:
                pass


def push(target, variables: dict) -> dict:
    """Render and send; DeployHTTPError unless the API answered 2xx."""
    headers = load_headers(target.http_headers)
    url = render(target.url, variables, default_filter='urlencode')
    body = render(target.body_template or '', variables)
    content_type = content_type_for(headers, body)
    sent = {name: value for name, value in headers.items() if name.lower() != 'content-type'}
    sent['Content-Type'] = content_type
    sent.setdefault('User-Agent', USER_AGENT)
    method = (target.http_method or 'POST').upper()
    status, tail = _request(target, method, url, sent, body.encode())
    detail = {'method': method, 'url': url, 'status': status,
              'variables': sorted(variables.keys()), 'response': tail[:300]}
    if 300 <= status < 400:
        raise DeployHTTPError(f"HTTP {status}: redirects are not followed for a deployment")
    if not 200 <= status < 300:
        raise DeployHTTPError(f"HTTP {status}" + (f": {tail[:200]}" if tail.strip() else ''))
    return detail


def probe(target) -> dict:
    """Reach the API without pushing: a HEAD with the stored headers. Any
    HTTP answer proves the address, the TLS trust and the route."""
    headers = dict(load_headers(target.http_headers))
    headers.setdefault('User-Agent', USER_AGENT)
    url = render(target.url, VARIABLES, default_filter='urlencode')
    status, _ = _request(target, 'HEAD', url, headers, None)
    return {'status_code': status, 'url': url, 'tls_verified': url.lower().startswith('https://')}
