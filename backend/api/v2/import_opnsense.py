"""
OPNsense Import API
Handles testing connection and importing CAs/Certs from OPNsense
"""
import base64
import json
import logging
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
from utils.ssrf_protection import validate_url_not_cloud_metadata
from services.audit_service import AuditService

# Setup logging
logger = logging.getLogger(__name__)

bp = Blueprint('import_opnsense', __name__)


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


def _fetch_rows(session, base_url, api_key, api_secret, resource):
    response = session.get(
        f"{base_url}/api/trust/{resource}/search",
        auth=(api_key, api_secret),
        timeout=10
    )
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
        "verify_ssl": false
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
    verify_ssl = data.get('verify_ssl', False)
    
    logger.info(f"OpnSense test connection: host={host}, port={port}, verify_ssl={verify_ssl}")
    
    if not all([host, api_key, api_secret]):
        logger.warning(f"OpnSense test failed: missing required fields")
        return error_response("Missing required fields: host, api_key, api_secret", 400)
    
    # Narrow SSRF guard — OPNsense is by design a LAN firewall (RFC1918).
    # Block only cloud metadata + loopback.
    try:
        validate_url_not_cloud_metadata(f"https://{host}")
    except ValueError as e:
        logger.warning(f"OPNsense SSRF blocked: {e}")
        return error_response("OPNsense host must not target cloud metadata services or loopback", 400)
    
    base_url = f"https://{host}:{port}"
    
    try:
        session = create_session(verify_ssl=verify_ssl)

        items = []

        ca_rows = _fetch_rows(session, base_url, api_key, api_secret, 'ca')
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

        cert_rows = _fetch_rows(session, base_url, api_key, api_secret, 'cert')
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
        "verify_ssl": false,
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
    verify_ssl = data.get('verify_ssl', False)
    items = data.get('items', [])
    
    logger.info(f"OpnSense import: host={host}, port={port}, items_count={len(items)}")
    
    if not all([host, api_key, api_secret]):
        logger.warning("OpnSense import failed: missing required fields")
        return error_response("Missing required fields", 400)
    
    # Narrow SSRF guard — OPNsense is LAN firewall, RFC1918 expected.
    try:
        validate_url_not_cloud_metadata(f"https://{host}")
    except ValueError as e:
        logger.warning(f"OPNsense SSRF blocked: {e}")
        return error_response("OPNsense host must not target cloud metadata services or loopback", 400)
    
    if items is None:
        logger.warning("OpnSense import failed: no items specified")
        return error_response("No items selected for import", 400)
    
    # Fetch data from OPNsense
    session = create_session(verify_ssl=verify_ssl)
    base_url = f"https://{host}:{port}"
    
    stats = {
        "cas_imported": 0,
        "cas_skipped": 0,
        "certs_imported": 0,
        "certs_skipped": 0,
        "errors": []
    }
    
    try:
        ca_rows = _fetch_rows(session, base_url, api_key, api_secret, 'ca')
        cert_rows = _fetch_rows(session, base_url, api_key, api_secret, 'cert')

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

        # Import CAs first so certificate caref links can resolve in the same transaction.
        for item_id in selected_ids:
            if item_id not in all_cas:
                continue

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
            "skipped": stats['cas_skipped'] + stats['certs_skipped'],
            "errors": stats['errors']
        })
    
    except Exception as e:
        db.session.rollback()
        logger.exception(f"OpnSense import failed: {str(e)}")
        return error_response("Import failed", 500)
