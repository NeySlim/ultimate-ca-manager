"""
CAs Export Operations
"""

from . import bp
from flask import request, Response, g
import base64
import subprocess
import tempfile
import os
import logging

from auth.unified import require_auth, has_permission
from utils.response import success_response, error_response
from utils.sanitize import sanitize_filename
from utils.datetime_utils import utc_isoformat
from models import CA, Certificate, db
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from utils.pkcs12_export import legacy_flag, pkcs12_encryption
import fips_mode
from fips_mode import FipsRestricted
from utils.key_codec import load_pem_bytes

from utils.export_password import validate_export_password
from services.key_export_audit import audit_key_export

logger = logging.getLogger(__name__)


def _parent_cas(ca):
    """The CAs above *ca*, nearest first, skipping any without a certificate.

    Every export format walked the hierarchy itself, and none of the five
    copies had a loop guard: a ``caref`` pointing back down the chain kept
    appending forever — filling memory, and for the p7b branch filling the
    temporary file it never got to unlink.
    """
    from utils.ca_chain import walk_ca_chain
    return [parent for parent in walk_ca_chain(ca, include_start=False) if parent.crt]


# The bounds, and the reason for the ceiling, now live in
# utils/export_password next to the five other routes that hand out an
# encrypted bundle. This one used to allow four characters where the export
# dialog required eight, and was the only route with a ceiling at all.
def _validate_export_password(password):
    """Return error string or None. Empty means "do not encrypt"."""
    return validate_export_password(password, allow_empty=True)


def _audit_key_export(ca, export_format, password):
    audit_key_export('ca', ca.id, ca.descr or ca.refid, export_format, password)


@bp.route('/api/v2/cas/export', methods=['GET', 'POST'])
@require_auth(['read:cas'])
def export_all_cas():
    """Export all CA certificates in various formats"""

    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        export_format = data.get('format', 'pem').lower()
    else:
        export_format = request.args.get('format', 'pem').lower()

    cas = CA.query.filter(CA.crt.isnot(None), CA.crt != '').all()
    if not cas:
        return error_response('No CAs to export', 404)

    try:
        if export_format == 'pem':
            pem_data = b''
            for ca in cas:
                if ca.crt:
                    pem_data += base64.b64decode(ca.crt)
                    if not pem_data.endswith(b'\n'):
                        pem_data += b'\n'

            return Response(
                pem_data,
                mimetype='application/x-pem-file',
                headers={'Content-Disposition': 'attachment; filename="ca-certificates.pem"'}
            )

        elif export_format == 'pkcs7' or export_format == 'p7b':
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                for ca in cas:
                    if ca.crt:
                        f.write(base64.b64decode(ca.crt))
                        f.write(b'\n')
                pem_file = f.name

            try:
                p7b_output = subprocess.check_output([
                    'openssl', 'crl2pkcs7', '-nocrl',
                    '-certfile', pem_file,
                    '-outform', 'DER'
                ], stderr=subprocess.DEVNULL, timeout=30)

                return Response(
                    p7b_output,
                    mimetype='application/x-pkcs7-certificates',
                    headers={'Content-Disposition': 'attachment; filename="ca-certificates.p7b"'}
                )
            finally:
                os.unlink(pem_file)

        else:
            return error_response(f'Bulk export only supports PEM and P7B formats. Use individual export for DER/PKCS12/PFX', 400)

    except Exception as e:
        logger.error(f"Export failed: {e}")
        return error_response('Export failed', 500)


@bp.route('/api/v2/cas/<int:ca_id>/export', methods=['GET', 'POST'])
@require_auth(['read:cas'])
def export_ca(ca_id):
    """
    Export CA certificate in various formats

    Params (query or POST body):
        format: pem (default), der, pkcs12
        include_key: bool - Include private key
        include_chain: bool - Include parent CA chain
        password: string - Required for PKCS12
    """

    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)

    if not ca.crt:
        return error_response('CA certificate data not available', 400)

    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        export_format = data.get('format', 'pem').lower()
        include_key = bool(data.get('include_key', False))
        include_chain = bool(data.get('include_chain', False))
        password = data.get('password')
        legacy = legacy_flag(data.get('legacy'))  # 3DES/SHA-1 profile (#331)
    else:
        export_format = request.args.get('format', 'pem').lower()
        include_key = request.args.get('include_key', 'false').lower() == 'true'
        include_chain = request.args.get('include_chain', 'false').lower() == 'true'
        password = request.args.get('password')
        legacy = False
        # Passwords and key-bearing formats must not travel in the URL
        if password or include_key or export_format in ('pkcs12', 'p12', 'pfx', 'jks', 'key'):
            if password:
                logger.warning("Rejected CA %s export with password in query string", ca_id)
            return error_response(
                'Password and private key exports must use POST with a JSON body, '
                'not the query string', 400)

    # A CA key leaves UCM only with read:private_keys, as a certificate key does
    if include_key or export_format in ('pkcs12', 'pfx', 'key', 'jks'):
        if not (has_permission('write:cas', g.permissions)
                and has_permission('read:private_keys', g.permissions)):
            return error_response(
                'Private key export requires the write:cas and read:private_keys permissions', 403)
        # HSM-backed CAs cannot export their private key — it never leaves the HSM
        if ca.uses_hsm:
            return error_response('Cannot export HSM-backed key', 409)

    # Cap export password length (PKCS12/PFX/JKS or PEM-encrypted key)
    pw_err = _validate_export_password(password)
    if pw_err:
        return error_response(pw_err, 400)

    try:
        cert_pem = base64.b64decode(ca.crt)

        # Private key only export
        if export_format == 'key':
            if not ca.prv:
                return error_response('CA has no private key', 400)
            key_pem = load_pem_bytes(ca.prv, context=f"CA {ca.id}")
            if password:
                private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
                key_pem = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
                )
            _audit_key_export(ca, export_format, password)
            return Response(
                key_pem,
                mimetype='application/x-pem-file',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.key"'}
            )

        if export_format == 'pem':
            result = cert_pem
            content_type = 'application/x-pem-file'
            filename = f"{sanitize_filename(ca.descr or ca.refid)}.crt"

            # Include private key if requested
            if include_key and ca.prv:
                key_pem = load_pem_bytes(ca.prv, context=f"CA {ca.id}")
                if not result.endswith(b'\n'):
                    result += b'\n'
                result += key_pem
                filename = f"{sanitize_filename(ca.descr or ca.refid)}_with_key.pem"

            # Include parent CA chain if requested
            if include_chain and ca.caref:
                for parent in _parent_cas(ca):
                    parent_cert = base64.b64decode(parent.crt)
                    if not result.endswith(b'\n'):
                        result += b'\n'
                    result += parent_cert
                if include_key:
                    filename = f"{sanitize_filename(ca.descr or ca.refid)}_full_chain.pem"
                else:
                    filename = f"{sanitize_filename(ca.descr or ca.refid)}_chain.pem"

            if include_key and ca.prv:
                _audit_key_export(ca, export_format, password)
            return Response(
                result,
                mimetype=content_type,
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )

        elif export_format == 'der':

            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            der_bytes = cert.public_bytes(serialization.Encoding.DER)

            return Response(
                der_bytes,
                mimetype='application/x-x509-ca-cert',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.der"'}
            )

        elif export_format == 'pkcs12':
            if not password:
                return error_response('Password required for PKCS12 export', 400)
            if not ca.prv:
                return error_response('CA has no private key for PKCS12 export', 400)

            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem = load_pem_bytes(ca.prv, context=f"CA {ca.id}")
            private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())

            # Build parent CA chain if available and requested
            ca_certs = []
            if include_chain and ca.caref:
                for parent in _parent_cas(ca):
                    ca_certs.append(x509.load_pem_x509_certificate(
                        base64.b64decode(parent.crt), default_backend()
                    ))

            p12_bytes = pkcs12.serialize_key_and_certificates(
                name=(ca.descr or ca.refid).encode(),
                key=private_key,
                cert=cert,
                cas=ca_certs if ca_certs else None,
                encryption_algorithm=pkcs12_encryption(password, legacy)
            )

            _audit_key_export(ca, export_format, password)
            return Response(
                p12_bytes,
                mimetype='application/x-pkcs12',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.p12"'}
            )

        elif export_format == 'pkcs7' or export_format == 'p7b':

            # Create temporary PEM file with CA chain
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                f.write(cert_pem)
                # Include parent chain
                if include_chain and ca.caref:
                    for parent in _parent_cas(ca):
                        f.write(b'\n')
                        f.write(base64.b64decode(parent.crt))
                pem_file = f.name

            try:
                p7b_output = subprocess.check_output([
                    'openssl', 'crl2pkcs7', '-nocrl',
                    '-certfile', pem_file,
                    '-outform', 'DER'
                ], stderr=subprocess.DEVNULL, timeout=30)

                return Response(
                    p7b_output,
                    mimetype='application/x-pkcs7-certificates',
                    headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.p7b"'}
                )
            finally:
                os.unlink(pem_file)

        elif export_format == 'pfx':
            # PFX is same as PKCS12
            if not password:
                return error_response('Password required for PFX export', 400)
            if not ca.prv:
                return error_response('CA has no private key for PFX export', 400)

            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem_data = load_pem_bytes(ca.prv, context=f"CA {ca.id}")
            private_key = serialization.load_pem_private_key(key_pem_data, password=None, backend=default_backend())

            # Build parent CA chain if available and requested
            ca_certs = []
            if include_chain and ca.caref:
                for parent in _parent_cas(ca):
                    ca_certs.append(x509.load_pem_x509_certificate(
                        base64.b64decode(parent.crt), default_backend()
                    ))

            p12_bytes = pkcs12.serialize_key_and_certificates(
                name=(ca.descr or ca.refid).encode(),
                key=private_key,
                cert=cert,
                cas=ca_certs if ca_certs else None,
                encryption_algorithm=pkcs12_encryption(password, legacy)
            )

            _audit_key_export(ca, export_format, password)
            return Response(
                p12_bytes,
                mimetype='application/x-pkcs12',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.pfx"'}
            )

        elif export_format == 'jks':
            if not password:
                return error_response('Password required for JKS export', 400)
            if not ca.prv:
                return error_response('CA has no private key for JKS export', 400)
            fips_mode.refuse('JKS export')

            import jks as pyjks
            import time

            cert_obj = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem_data = load_pem_bytes(ca.prv, context=f"CA {ca.id}")
            private_key = serialization.load_pem_private_key(key_pem_data, password=None, backend=default_backend())

            cert_der = cert_obj.public_bytes(serialization.Encoding.DER)
            key_pkcs8 = private_key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()
            )

            cert_chain = [("X.509", cert_der)]

            if include_chain and ca.caref:
                for parent in _parent_cas(ca):
                    parent_cert = x509.load_pem_x509_certificate(
                        base64.b64decode(parent.crt), default_backend()
                    )
                    cert_chain.append(("X.509", parent_cert.public_bytes(serialization.Encoding.DER)))

            ts = int(time.time() * 1000)
            pke = pyjks.PrivateKeyEntry(
                alias=(ca.descr or ca.refid).lower().replace(' ', '-'),
                cert_chain=cert_chain,
                pkey_pkcs8=key_pkcs8,
                timestamp=ts,
            )

            keystore = pyjks.KeyStore.new("jks", [pke])
            jks_bytes = keystore.saves(password)

            _audit_key_export(ca, export_format, password)
            return Response(
                jks_bytes,
                mimetype='application/x-java-keystore',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(ca.descr or ca.refid)}.jks"'}
            )

        else:
            return error_response(f'Unsupported format: {export_format}', 400)

    except FipsRestricted:
        raise  # the app handler answers 400 with the FIPS problem type
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return error_response('Export failed', 500)
