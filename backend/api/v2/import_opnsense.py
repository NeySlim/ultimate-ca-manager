"""
OPNsense Import API
Handles testing connection and importing CAs/Certs from OPNsense
"""
import base64
import json
import logging
from contextlib import contextmanager
import requests
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID
from flask import Blueprint, request, g
from auth.unified import require_auth, has_permission
from models import db, CA, Certificate
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from utils.key_codec import store_pem_bytes
from utils.safe_requests import create_session
from utils.ssrf_protection import (
    pin_host, validate_url_not_cloud_metadata, validated_addresses)
from services.audit_service import AuditService
from services.ca import cross_certs

# Setup logging
logger = logging.getLogger(__name__)

bp = Blueprint('import_opnsense', __name__)

# How long a call to the appliance may take. Named rather than inline so a
# test can reach an unreachable host without waiting the full ten seconds.
REQUEST_TIMEOUT_SECONDS = 10


def _clean(value):
    return value.strip() if isinstance(value, str) else value


def _item_id(row):
    return row.get('uuid') or row.get('refid') or ''


def _refid(row):
    # OPNsense references certificates by refid/caref internally. uuid is only
    # the MVC API row identifier and must not be stored as UCM's refid.
    return row.get('refid') or row.get('uuid') or ''


def _display_name(row, default):
    return row.get('descr') or row.get('name') or row.get('commonname') or default


def _encoded_cert(row):
    if row.get('crt'):
        return row.get('crt')
    if row.get('crt_payload'):
        return base64.b64encode(row['crt_payload'].encode('utf-8')).decode('ascii')
    return ''


def _encoded_private_key(row):
    if row.get('prv'):
        return store_pem_bytes(row.get('prv'))
    if row.get('prv_payload'):
        return store_pem_bytes(row['prv_payload'].encode('utf-8'))
    return None


def _is_self_signed(encoded_crt):
    try:
        cert = x509.load_pem_x509_certificate(base64.b64decode(encoded_crt))
        return cert.subject == cert.issuer
    except Exception:
        return False


def _parse_cert(encoded_crt):
    info = {
        'subject': '',
        'issuer': '',
        'serial_number': '',
        'valid_from': None,
        'valid_to': None,
        'ski': None,
        'aki': None,
        'san_dns': [],
        'san_ip': [],
        'san_email': [],
        'san_uri': [],
    }
    if not encoded_crt:
        return info

    try:
        cert_pem = base64.b64decode(encoded_crt)
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        info.update({
            'subject': cert.subject.rfc4514_string(),
            'issuer': cert.issuer.rfc4514_string(),
            'serial_number': str(cert.serial_number),
            'valid_from': cert.not_valid_before_utc.replace(tzinfo=None),
            'valid_to': cert.not_valid_after_utc.replace(tzinfo=None),
        })
        try:
            ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
            info['ski'] = ext.value.key_identifier.hex(':').upper()
        except x509.ExtensionNotFound:
            pass
        try:
            ext = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
            if ext.value.key_identifier:
                info['aki'] = ext.value.key_identifier.hex(':').upper()
        except x509.ExtensionNotFound:
            pass
        try:
            ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            for name in ext.value:
                if isinstance(name, x509.DNSName):
                    info['san_dns'].append(name.value)
                elif isinstance(name, x509.IPAddress):
                    info['san_ip'].append(str(name.value))
                elif isinstance(name, x509.RFC822Name):
                    info['san_email'].append(name.value)
                elif isinstance(name, x509.UniformResourceIdentifier):
                    info['san_uri'].append(name.value)
        except x509.ExtensionNotFound:
            pass
    except Exception as e:
        logger.warning(f"Failed to parse OPNsense certificate: {e}")
    return info


def _canonical_host(host):
    """The host written the way the HTTP client will resolve it, or None.

    The deny-list resolves through `socket.getaddrinfo`, which converts a
    unicode name with IDNA 2003; urllib3 converts it with IDNA 2008. The two
    disagree: the name `fa` followed by a sharp s and `.example.com` is
    `fass.example.com` for one and `xn--fa-hia.example.com` for the other. A
    caller owning both records has a name checked as one host and reached as
    another, with no hostile resolver and no race -- the very shape of defect
    this function exists to close, one notch further along.

    So the name is converted once, here, with the encoder the client uses,
    and everything downstream works on the converted form. Addresses are left
    alone: they are not names, and the converter refuses them.
    """
    import ipaddress
    import re

    if not isinstance(host, str):
        # `_clean` hands back a non-string unchanged, and the caller would
        # have met an AttributeError and a server error rather than a
        # refusal naming the field.
        return None

    given = host.strip()
    if not given:
        return None

    bracketed = given.startswith('[') and given.endswith(']')
    bare = given[1:-1] if bracketed else given
    try:
        address = ipaddress.ip_address(bare)
    except ValueError:
        if bracketed:
            # Brackets mean an address literal. Dropping them and treating
            # the contents as a name would make the checked string differ
            # from the requested one all over again.
            return None
    else:
        if getattr(address, 'scope_id', None):
            # A zone identifier names an interface of this machine, which an
            # appliance's address has no business carrying, and it makes the
            # checked value differ from the reached one twice over: since
            # Python 3.9 two addresses differing only by their zone are
            # unequal, so `fd00:ec2::254%251` is not the metadata address as
            # far as the deny-list is concerned, while the client decodes the
            # zone as RFC 6874 asks and hands the resolver `fd00:ec2::254%1`,
            # which is exactly it.
            return None
        return f'[{address}]' if address.version == 6 else str(address)

    if bare.isascii():
        canonical = bare.lower()
    else:
        try:
            import idna
            canonical = idna.encode(bare.lower(), strict=True,
                                    std3_rules=True).decode()
        except Exception:
            return None

    # Letters, digits, hyphens, dots, and the underscore that internal
    # networks use. Written down rather than left to the resolver: the HTTP
    # client percent-decodes the authority and `urlparse` does not, so
    # `a%2eb.example.test` is one name for the check above and another for
    # the connection. Nothing reachable comes of it today, because the C
    # library refuses a name outside this set without asking anyone, but the
    # invariant belongs in the code rather than in whichever resolver the
    # image happens to ship.
    if not re.fullmatch(r'[A-Za-z0-9._-]+', canonical):
        return None
    return canonical


def _appliance_base_url(host, port):
    """The URL the appliance will actually be asked for, or a refusal.

    Both routes checked `https://{host}` against the deny-list and then
    connected to `https://{host}:{port}`. Those are two different strings, and
    the port arrives from the request body: an authority accepts far more than
    a number, so `443@169.254.169.254` turns everything before the `@` into
    userinfo and the address after it into the host. The deny-list saw the
    name that was typed and the connection went to the metadata service, in a
    single request, under a permission the operator role holds.

    So the port is required to be a port, the host to be nothing but a host
    written the way the client will resolve it, and the deny-list is asked
    about the URL that will be requested rather than about a prefix of it.

    Returns ((base_url, pin), None) or (None, error response), where `pin`
    is the host and the addresses it was vetted on: the name is resolved once
    here, and the connection is made to what was vetted rather than to
    whatever a second lookup answers.
    """
    from urllib.parse import urlparse

    try:
        number = int(str(port).strip())
    except (TypeError, ValueError):
        return None, error_response(
            'Port must be a number between 1 and 65535', 400)
    if not 1 <= number <= 65535:
        return None, error_response(
            'Port must be a number between 1 and 65535', 400)

    malformed = error_response(
        'Host must be a hostname or an IP address, without a port, a path '
        'or credentials', 400)

    canonical = _canonical_host(host)
    if canonical is None:
        return None, malformed

    base_url = f"https://{canonical}:{number}"
    try:
        parsed = urlparse(base_url)
        # `hostname` is lower-cased and stripped of its brackets, so an
        # address literal is compared without them on both sides.
        if (parsed.hostname != canonical.strip('[]') or parsed.port != number
                or parsed.username or parsed.password or parsed.path):
            return None, malformed
    except ValueError:
        # A bracketed value that is not an address: urlparse raises rather
        # than answering, and the caller would have seen a server error.
        return None, malformed

    try:
        # By name first: `validated_addresses` judges the addresses a name
        # resolves to, and the deny-list also knows a handful of names that
        # are metadata endpoints whatever they resolve to. Nothing is reachable
        # without this -- those names answer addresses the next check refuses
        # anyway, and a name that does not resolve fails closed -- but losing
        # the layer would not have shown up anywhere.
        validate_url_not_cloud_metadata(base_url)
        pin = validated_addresses(base_url)
    except ValueError as exc:
        logger.warning(f"OPNsense SSRF blocked: {exc}")
        return None, error_response(
            'OPNsense host must not target cloud metadata services or '
            'loopback', 400)

    return (base_url, pin), None


@contextmanager
def _pinned(pin):
    """Hold connections to the addresses the host was vetted on.

    Required rather than optional: a default of `None` is the exact shape a
    future caller's omission would take, and nothing downstream would notice
    -- the client would simply resolve the name again.
    """
    host, addresses = pin
    with pin_host(host, addresses):
        yield


def _fetch_rows(session, base_url, api_key, api_secret, resource, pin):
    # Redirects are not followed: the appliance answers JSON on its API, so a
    # 3xx there is not a normal condition, and walking it would read the
    # answer of a host the deny-list never saw as if it were the appliance's
    # inventory of certificates and keys. The refusal names where it was
    # being sent, because an operator behind a reverse proxy needs to know
    # that is what happened.
    url = f"{base_url}/api/trust/{resource}/search"
    # Connected to the addresses the deny-list was shown, not to whatever a
    # second lookup answers: the name is resolved once, when it is vetted,
    # and the connection is held to that answer for the length of the call.
    with _pinned(pin):
        response = session.get(
            url,
            auth=(api_key, api_secret),
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    if response.status_code in (301, 302, 303, 307, 308):
        location = response.headers.get('Location', '(no Location header)')
        raise requests.HTTPError(
            f"The appliance redirected {url} to {location}; the import reads "
            "the API of the host it was given, and does not follow it "
            "elsewhere")
    if response.status_code != 200:
        raise requests.HTTPError(f"API returned status {response.status_code}")
    return response.json().get('rows') or []


@bp.route('/api/v2/import/opnsense/test', methods=['POST'])
@require_auth(['write:certificates'])
def test_connection():
    """
    Test connection to OPNsense and fetch available CAs/Certificates
    
    POST /api/v2/import/opnsense/test
    Body: {
        "host": "192.168.1.1",
        "port": 443,
        "api_key": "xxx",
        "api_secret": "xxx",
        "verify_ssl": true
    }
    
    Returns: {
        "success": true,
        "items": [
            {
                "id": "1",
                "type": "CA" | "Certificate",
                "name": "Root CA",
                "subject": "CN=Root CA",
                "issuer": "CN=Root CA",
                "validUntil": "2034-02-15",
                "serialNumber": "01:02:03...",
                "selected": true
            }
        ],
        "stats": {
            "cas": 2,
            "certificates": 5
        }
    }
    """
    data = request.get_json() or {}
    
    # Extract connection details
    host = _clean(data.get('host'))
    port = data.get('port', 443)
    api_key = _clean(data.get('api_key'))
    api_secret = _clean(data.get('api_secret'))
    verify_ssl = data.get('verify_ssl', True)

    logger.info(f"OpnSense test connection: host={host}, port={port}, verify_ssl={verify_ssl}")
    if not verify_ssl:
        logger.warning(
            "OPNsense test connection with TLS verification DISABLED by "
            "request. API credentials travel over a MITM-able channel"
        )
    
    if not all([host, api_key, api_secret]):
        logger.warning(f"OpnSense test failed: missing required fields")
        return error_response("Missing required fields: host, api_key, api_secret", 400)
    
    # Narrow SSRF guard — OPNsense is by design a LAN firewall (RFC1918).
    # Block only cloud metadata + loopback, on the URL actually requested.
    checked, refusal = _appliance_base_url(host, port)
    if refusal is not None:
        return refusal
    base_url, pin = checked
    
    try:
        session = create_session(verify_ssl=verify_ssl)

        items = []

        ca_rows = _fetch_rows(session, base_url, api_key, api_secret, 'ca', pin)
        for row in ca_rows:
            item_id = _item_id(row)
            if not item_id:
                continue
            items.append({
                "id": item_id,
                "refid": _refid(row),
                "type": "CA",
                "name": _display_name(row, 'Unknown CA'),
                "subject": row.get('commonname') or row.get('name') or '',
                "issuer": row.get('caref', ''),
                "validUntil": row.get('valid_to') or row.get('validto_time') or '',
                "serialNumber": row.get('serial', ''),
                "selected": True
            })

        cert_rows = _fetch_rows(session, base_url, api_key, api_secret, 'cert', pin)
        for row in cert_rows:
            item_id = _item_id(row)
            if not item_id:
                continue
            items.append({
                "id": item_id,
                "refid": _refid(row),
                "type": "Certificate",
                "name": _display_name(row, 'Unknown Certificate'),
                "subject": row.get('commonname') or row.get('name') or '',
                "issuer": row.get('caref', ''),
                "validUntil": row.get('valid_to') or row.get('validto_time') or '',
                "serialNumber": row.get('serial', ''),
                "selected": True
            })
        
        logger.info(f"OpnSense test successful: {len(ca_rows)} CAs, {len(cert_rows)} certificates")
        return success_response(data={
            "items": items,
            "stats": {
                "cas": len(ca_rows),
                "certificates": len(cert_rows)
            }
        })
    
    except requests.exceptions.Timeout:
        logger.error(f"OpnSense connection timeout: {host}:{port}")
        return error_response("Connection timeout. Check host and port.", 408)

    # SSLError MUST precede ConnectionError (it is a subclass): the generic
    # handler's "Check host and port." misdiagnoses a certificate failure —
    # the exact case verify-by-default makes common on a stock self-signed
    # OPNsense GUI. Wording matches api/v2/sso/connection_tests.py, naming
    # this form's actual checkbox.
    except requests.exceptions.SSLError as e:
        logger.error(f"OpnSense TLS certificate verification failed: {host}:{port}: {e}")
        return error_response(
            "SSL certificate verification failed. Enable 'Ignore SSL "
            "certificate (self-signed)' or install a certificate trusted "
            "by UCM on the OPNsense GUI.", 400)

    except requests.exceptions.ConnectionError:
        logger.error(f"OpnSense connection failed: {host}:{port}")
        return error_response("Connection failed. Check host and port.", 503)

    except Exception as e:
        logger.exception(f"OpnSense test error: {str(e)}")
        return error_response("Internal error during connection test", 500)


@bp.route('/api/v2/import/opnsense/import', methods=['POST'])
@require_auth(['write:certificates'])
def import_items():
    """
    Import selected CAs and Certificates from OPNsense
    
    POST /api/v2/import/opnsense/import
    Body: {
        "host": "192.168.1.1",
        "port": 443,
        "api_key": "xxx",
        "api_secret": "xxx",
        "verify_ssl": true,
        "items": ["uuid1", "uuid2", ...]
    }
    
    Returns: {
        "success": true,
        "imported": {
            "cas": 2,
            "certificates": 3
        },
        "skipped": 1,
        "errors": []
    }
    """
    data = request.get_json() or {}
    
    # Extract connection details
    host = _clean(data.get('host'))
    port = data.get('port', 443)
    api_key = _clean(data.get('api_key'))
    api_secret = _clean(data.get('api_secret'))
    verify_ssl = data.get('verify_ssl', True)
    items = data.get('items', [])

    logger.info(f"OpnSense import: host={host}, port={port}, items_count={len(items)}")
    if not verify_ssl:
        logger.warning(
            "OPNsense import with TLS verification DISABLED by request. "
            "API credentials and fetched private keys travel over a "
            "MITM-able channel"
        )
    
    if not all([host, api_key, api_secret]):
        logger.warning("OpnSense import failed: missing required fields")
        return error_response("Missing required fields", 400)
    
    # Narrow SSRF guard — OPNsense is LAN firewall, RFC1918 expected. Asked
    # about the URL that will be requested, port included.
    checked, refusal = _appliance_base_url(host, port)
    if refusal is not None:
        return refusal
    base_url, pin = checked
    
    if items is None:
        logger.warning("OpnSense import failed: no items specified")
        return error_response("No items selected for import", 400)
    
    # Fetch data from OPNsense
    session = create_session(verify_ssl=verify_ssl)
    
    stats = {
        "cas_imported": 0,
        "cas_skipped": 0,
        "certs_imported": 0,
        "certs_skipped": 0,
        "errors": []
    }
    
    try:
        ca_rows = _fetch_rows(session, base_url, api_key, api_secret, 'ca', pin)
        cert_rows = _fetch_rows(session, base_url, api_key, api_secret, 'cert', pin)

        selected_ids = set(items)
        if not selected_ids:
            selected_ids = {_item_id(row) for row in ca_rows + cert_rows if _item_id(row)}

        all_cas = {}
        all_certs = {}

        for row in ca_rows:
            all_cas[_item_id(row)] = row

        for row in cert_rows:
            all_certs[_item_id(row)] = row

        ca_selected = any(item_id in all_cas for item_id in selected_ids)
        if ca_selected and not has_permission('write:cas', g.permissions):
            return error_response('write:cas permission required to import CAs', 403)

        # Import CAs first so certificate caref links can resolve in the same transaction;
        # self-signed ones before their cross-certificates, which attach to them.
        attached_cross = []
        for item_id in sorted((i for i in selected_ids if i in all_cas),
                              key=lambda i: not _is_self_signed(_encoded_cert(all_cas[i]))):

            ca_data = all_cas[item_id]
            ca_refid = _refid(ca_data)
            crt = _encoded_cert(ca_data)

            if not ca_refid or not crt:
                stats['cas_skipped'] += 1
                stats['errors'].append(f"CA '{_display_name(ca_data, item_id)}' is missing refid or certificate data")
                continue
            
            # Check if already exists by refid
            existing = CA.query.filter_by(refid=ca_refid).first()
            if existing:
                stats['cas_skipped'] += 1
                continue
            
            # A cross-certificate of a CA already held is attached to it, not stored as a second CA
            try:
                attached = cross_certs.attach_to_counterpart(crt, 'import')
            except cross_certs.CrossCertError as e:
                stats['cas_skipped'] += 1
                stats['errors'].append(f"CA '{ca_data.get('descr')}': {e.message}")
                continue
            if attached:
                attached_cross.append(attached)
                stats['cas_cross_attached'] = stats.get('cas_cross_attached', 0) + 1
                continue

            # Check for duplicate by description (same CA, different refid from OPNsense)
            duplicate_by_name = CA.query.filter_by(
                descr=ca_data.get('descr'),
                imported_from='opnsense'
            ).first()
            
            if duplicate_by_name:
                # Skip duplicate - same CA already imported with different refid
                stats['cas_skipped'] += 1
                stats['errors'].append(f"CA '{ca_data.get('descr')}' already exists with refid {duplicate_by_name.refid}")
                continue
            
            cert_info = _parse_cert(crt)
            try:
                serial = int(ca_data.get('serial') or 0)
            except (TypeError, ValueError):
                serial = 0
             
            # Create CA
            ca = CA(
                refid=ca_refid,
                descr=_display_name(ca_data, 'Imported from OPNsense'),
                crt=crt,
                prv=_encoded_private_key(ca_data),
                serial=serial,
                subject=cert_info['subject'],
                issuer=cert_info['issuer'],
                serial_number=cert_info['serial_number'],
                ski=cert_info['ski'],
                valid_from=cert_info['valid_from'],
                valid_to=cert_info['valid_to'],
                imported_from='opnsense',
                created_by='import'
            )
            
            db.session.add(ca)
            stats['cas_imported'] += 1

        for item_id in selected_ids:
            if item_id in all_certs:
                # Import Certificate
                cert_data = all_certs[item_id]
                cert_refid = _refid(cert_data)
                crt = _encoded_cert(cert_data)

                if not cert_refid or not crt:
                    stats['certs_skipped'] += 1
                    stats['errors'].append(f"Certificate '{_display_name(cert_data, item_id)}' is missing refid or certificate data")
                    continue
                
                # Check if already exists by refid
                existing = Certificate.query.filter_by(refid=cert_refid).first()
                if existing:
                    stats['certs_skipped'] += 1
                    continue
                
                # Check for duplicate by description
                duplicate_by_name = Certificate.query.filter_by(
                    descr=cert_data.get('descr'),
                    imported_from='opnsense'
                ).first()
                
                if duplicate_by_name:
                    # Skip duplicate
                    stats['certs_skipped'] += 1
                    stats['errors'].append(f"Certificate '{cert_data.get('descr')}' already exists with refid {duplicate_by_name.refid}")
                    continue
                
                cert_info = _parse_cert(crt)
                caref = cert_data.get('caref') or None
                if caref and not CA.query.filter_by(refid=caref).first():
                    caref = None
                 
                # Create certificate
                cert = Certificate(
                    refid=cert_refid,
                    descr=_display_name(cert_data, 'Imported from OPNsense'),
                    caref=caref,
                    crt=crt,
                    prv=_encoded_private_key(cert_data),
                    cert_type=cert_data.get('cert_type') or cert_data.get('type') or 'server_cert',
                    subject=cert_info['subject'],
                    issuer=cert_info['issuer'],
                    serial_number=cert_info['serial_number'],
                    aki=cert_info['aki'],
                    ski=cert_info['ski'],
                    valid_from=cert_info['valid_from'],
                    valid_to=cert_info['valid_to'],
                    san_dns=json.dumps(cert_info['san_dns']) if cert_info['san_dns'] else None,
                    san_ip=json.dumps(cert_info['san_ip']) if cert_info['san_ip'] else None,
                    san_email=json.dumps(cert_info['san_email']) if cert_info['san_email'] else None,
                    san_uri=json.dumps(cert_info['san_uri']) if cert_info['san_uri'] else None,
                    imported_from='opnsense',
                    created_by='import'
                )
                
                db.session.add(cert)
                stats['certs_imported'] += 1
        
        # Commit all changes
        ok, _err = safe_commit(logger, "Failed to import OPNsense data")
        if not ok:
            return _err
        for ca, row in attached_cross:
            cross_certs.announce(ca, 'attached', row, 'import')
        
        AuditService.log_action(
            action='opnsense_import',
            resource_type='import',
            resource_name=f'OPNsense ({host})',
            details=f'Imported from OPNsense: {stats["cas_imported"]} CAs, {stats["certs_imported"]} certificates',
            success=True
        )
        
        logger.info(f"OpnSense import complete: {stats['cas_imported']} CAs, {stats['certs_imported']} certificates imported, {stats['cas_skipped'] + stats['certs_skipped']} skipped")
        
        return success_response(data={
            "imported": {
                "cas": stats['cas_imported'],
                "certificates": stats['certs_imported']
            },
            "cross_certificates_attached": stats.get('cas_cross_attached', 0),
            "skipped": stats['cas_skipped'] + stats['certs_skipped'],
            "errors": stats['errors']
        })
    
    except requests.exceptions.SSLError as e:
        # The fetch fails before anything joins the session; the rollback is
        # defensive, keeping this path symmetric with the generic handler.
        db.session.rollback()
        logger.error(f"OpnSense TLS certificate verification failed: {host}:{port}: {e}")
        return error_response(
            "SSL certificate verification failed. Enable 'Ignore SSL "
            "certificate (self-signed)' or install a certificate trusted "
            "by UCM on the OPNsense GUI.", 400)

    except Exception as e:
        db.session.rollback()
        logger.exception(f"OpnSense import failed: {str(e)}")
        return error_response("Import failed", 500)
