"""
Certificates Export Routes
/api/v2/certificates/export - Export all or single certificate
"""

import base64
import json
import logging
import os
import subprocess
import tempfile
import zipfile
from flask import Response, request, g
from auth.unified import require_auth, has_permission
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import pkcs12

from models import Certificate, CA
from models.truststore import TrustedCertificate
from utils.response import success_response, error_response
from utils.sanitize import sanitize_filename
from utils.key_codec import load_pem_bytes
from . import bp

logger = logging.getLogger(__name__)


def _split_pem_certs(pem_bytes):
    """Return every PEM certificate block found in *pem_bytes* as x509 objects."""
    certs = []
    marker = b'-----END CERTIFICATE-----'
    for chunk in pem_bytes.split(marker):
        if b'-----BEGIN CERTIFICATE-----' not in chunk:
            continue
        block = chunk[chunk.index(b'-----BEGIN CERTIFICATE-----'):] + marker + b'\n'
        try:
            certs.append(x509.load_pem_x509_certificate(block, default_backend()))
        except Exception:
            continue
    return certs


def _resolve_issuer_cert(cert):
    """Find the issuer certificate of *cert* among locally known sources.

    Looks up managed CAs (by AKI→SKI, then issuer DN) and then the Trust Store
    (by issuer DN). Returns the issuer x509.Certificate or None. Used to fill in
    a missing chain when it is neither stored inline nor reachable via `caref`.
    """
    issuer_dn = cert.issuer.rfc4514_string()

    aki = None
    try:
        aki_ext = cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)
        if aki_ext.value.key_identifier:
            aki = aki_ext.value.key_identifier.hex()
    except x509.ExtensionNotFound:
        pass

    # 1. Managed CAs — prefer AKI→SKI, then subject DN
    ca = None
    if aki:
        ca = CA.query.filter(CA.ski == aki).first()
    if ca is None:
        ca = CA.query.filter(CA.subject == issuer_dn).first()
    if ca is not None and ca.crt:
        try:
            return x509.load_pem_x509_certificate(base64.b64decode(ca.crt), default_backend())
        except Exception:
            pass

    # 2. Trust Store — by issuer DN
    tc = TrustedCertificate.query.filter_by(subject=issuer_dn).first()
    if tc is not None and tc.certificate_pem:
        try:
            return x509.load_pem_x509_certificate(tc.certificate_pem.encode(), default_backend())
        except Exception:
            pass
    return None


def _build_ca_chain(certificate, cert_pem):
    """Build the issuing CA chain (excluding the leaf) for chain-aware exports.

    Order of preference:
      1. The chain already stored inline with the certificate (ACME / imported
         full-chain certs store leaf + intermediates in `crt`).
      2. The managed CA chain walked via `certificate.caref`.
      3. If the chain is still missing or incomplete, reconstruct it from locally
         known issuers (managed CAs + Trust Store) by walking issuer DNs up to a
         self-signed root.
    """
    inline = _split_pem_certs(cert_pem)
    leaf = inline[0] if inline else None
    chain = inline[1:] if len(inline) > 1 else []

    # 2. Managed CA walk via caref (only when nothing came inline)
    if not chain and certificate.caref:
        ca = CA.query.filter_by(refid=certificate.caref).first()
        while ca:
            if ca.crt:
                try:
                    chain.append(
                        x509.load_pem_x509_certificate(base64.b64decode(ca.crt), default_backend())
                    )
                except Exception:
                    pass
            ca = CA.query.filter_by(refid=ca.caref).first() if ca.caref else None

    # 3. Extend/complete the chain using locally known issuers until we reach a
    #    self-signed root (or can no longer resolve the next issuer).
    seen = {c.fingerprint(hashes.SHA256()) for c in chain}
    top = chain[-1] if chain else leaf
    guard = 0
    while top is not None and guard < 10:
        guard += 1
        if top.subject.rfc4514_string() == top.issuer.rfc4514_string():
            break  # self-signed root reached
        nxt = _resolve_issuer_cert(top)
        if nxt is None:
            break
        fp = nxt.fingerprint(hashes.SHA256())
        if fp in seen:
            break  # cycle / already present
        seen.add(fp)
        chain.append(nxt)
        top = nxt

    return chain


def _named_cas(ca_certs):
    """Wrap CA certs as PKCS12Certificate objects carrying a friendlyName.

    Without an explicit friendlyName, keystore tools (XCA, keytool, certmgr)
    auto-label intermediate/root entries as ``<leaf>_ca_0``, ``_ca_1``, ...
    Tagging each CA with its Common Name (falling back to the full subject DN)
    makes them display under their real name.
    """
    if not ca_certs:
        return None
    named = []
    for c in ca_certs:
        try:
            attrs = c.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            fname = attrs[0].value if attrs else c.subject.rfc4514_string()
        except Exception:
            fname = c.subject.rfc4514_string()
        named.append(pkcs12.PKCS12Certificate(c, fname.encode()))
    return named


@bp.route('/api/v2/certificates/export', methods=['GET', 'POST'])
@require_auth(['read:certificates'])
def export_all_certificates():
    """Export all certificates in various formats"""

    # Support both GET (query params) and POST (body) for security
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        export_format = data.get('format', 'pem').lower()
        include_chain = bool(data.get('include_chain', False))
        password = data.get('password')
    else:
        export_format = request.args.get('format', 'pem').lower()
        include_chain = request.args.get('include_chain', 'false').lower() == 'true'
        password = request.args.get('password')

    certificates = Certificate.query.filter(Certificate.crt.isnot(None)).all()
    if not certificates:
        return error_response('No certificates to export', 404)

    try:
        if export_format == 'pem':
            # Concatenate all PEM certificates
            pem_data = b''
            for cert in certificates:
                if cert.crt:
                    pem_data += base64.b64decode(cert.crt)
                    if not pem_data.endswith(b'\n'):
                        pem_data += b'\n'

            return Response(
                pem_data,
                mimetype='application/x-pem-file',
                headers={'Content-Disposition': 'attachment; filename="certificates.pem"'}
            )

        elif export_format == 'pkcs7' or export_format == 'p7b':
            # Create temp file with all PEM certs
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                for cert in certificates:
                    if cert.crt:
                        f.write(base64.b64decode(cert.crt))
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
                    headers={'Content-Disposition': 'attachment; filename="certificates.p7b"'}
                )
            finally:
                os.unlink(pem_file)

        else:
            return error_response(f'Bulk export only supports PEM and P7B formats. Use individual export for DER/PKCS12/PFX', 400)

    except Exception as e:
        logger.error(f"Bulk export failed: {e}")
        return error_response('Export failed', 500)


@bp.route('/api/v2/certificates/<int:cert_id>/export', methods=['GET', 'POST'])
@require_auth(['read:certificates'])
def export_certificate(cert_id):
    """
    Export certificate in various formats

    Query params:
        format: pem (default), der, pkcs12, jks
        include_key: bool - Include private key (PEM only)
        include_chain: bool - Include CA chain (PEM only)
        password: string - Required for PKCS12 and JKS
    """

    certificate = Certificate.query.get(cert_id)
    if not certificate:
        return error_response('Certificate not found', 404)

    if not certificate.crt:
        return error_response('Certificate data not available', 400)

    # Support both GET (query params) and POST (body) for security
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        export_format = data.get('format', 'pem').lower()
        include_key = bool(data.get('include_key', False))
        include_chain = bool(data.get('include_chain', False))
        password = data.get('password')
    else:
        export_format = request.args.get('format', 'pem').lower()
        include_key = request.args.get('include_key', 'false').lower() == 'true'
        include_chain = request.args.get('include_chain', 'false').lower() == 'true'
        password = request.args.get('password')
        # SECURITY: never accept passwords via query string
        if password or export_format in ('pkcs12', 'pfx', 'jks'):
            if password:
                logger.warning(
                    "Rejected certificate export with password in query string "
                    "(cert_id=%s) — client must POST with JSON body",
                    cert_id,
                )
            return error_response(
                'Password must be sent via POST body (JSON), not query string',
                400,
            )

    # Private key export requires write permission
    if include_key or export_format in ('pkcs12', 'pfx', 'key', 'jks'):
        if not has_permission('write:certificates', g.permissions):
            return error_response('Private key export requires write:certificates permission', 403)

    try:
        cert_pem = base64.b64decode(certificate.crt)

        # Private key only export
        if export_format == 'key':
            if not certificate.prv:
                return error_response('Certificate has no private key', 400)
            key_pem = load_pem_bytes(certificate.prv, context=f"certificate {certificate.id}")
            if password:
                private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
                key_pem = private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
                )
            return Response(
                key_pem,
                mimetype='application/x-pem-file',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(certificate.descr or certificate.refid)}.key"'}
            )

        if export_format == 'pem':
            result = cert_pem
            content_type = 'application/x-pem-file'
            filename = f"{sanitize_filename(certificate.descr or certificate.refid)}.crt"

            # Include private key if requested
            if include_key and certificate.prv:
                key_pem = load_pem_bytes(certificate.prv, context=f"certificate {certificate.id}")
                if not result.endswith(b'\n'):
                    result += b'\n'
                result += key_pem
                filename = f"{sanitize_filename(certificate.descr or certificate.refid)}_with_key.pem"

            # Include CA chain if requested
            if include_chain and certificate.caref:
                ca = CA.query.filter_by(refid=certificate.caref).first()
                while ca:
                    if ca.crt:
                        ca_cert = base64.b64decode(ca.crt)
                        if not result.endswith(b'\n'):
                            result += b'\n'
                        result += ca_cert
                    if ca.caref:
                        ca = CA.query.filter_by(refid=ca.caref).first()
                    else:
                        break
                if include_key:
                    filename = f"{sanitize_filename(certificate.descr or certificate.refid)}_full_chain.pem"
                else:
                    filename = f"{sanitize_filename(certificate.descr or certificate.refid)}_chain.pem"

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
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(certificate.descr or certificate.refid)}.der"'}
            )

        elif export_format == 'pkcs12':
            if not password:
                return error_response('Password required for PKCS12 export', 400)
            if not certificate.prv:
                return error_response('Certificate has no private key for PKCS12 export', 400)

            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem = load_pem_bytes(certificate.prv, context=f"certificate {certificate.id}")
            private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())

            # Build CA chain if requested (inline stored chain or managed CA)
            ca_certs = _build_ca_chain(certificate, cert_pem) if include_chain else []

            p12_bytes = pkcs12.serialize_key_and_certificates(
                name=(certificate.descr or certificate.refid).encode(),
                key=private_key,
                cert=cert,
                cas=_named_cas(ca_certs),
                encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
            )

            return Response(
                p12_bytes,
                mimetype='application/x-pkcs12',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(certificate.descr or certificate.refid)}.p12"'}
            )

        elif export_format == 'pkcs7' or export_format == 'p7b':
            # Create temporary PEM file
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.pem', delete=False) as f:
                f.write(cert_pem)
                # Include CA chain if requested
                if include_chain and certificate.caref:
                    ca = CA.query.filter_by(refid=certificate.caref).first()
                    while ca:
                        if ca.crt:
                            f.write(b'\n')
                            f.write(base64.b64decode(ca.crt))
                        if ca.caref:
                            ca = CA.query.filter_by(refid=ca.caref).first()
                        else:
                            break
                pem_file = f.name

            try:
                # Convert to PKCS7 using OpenSSL
                p7b_output = subprocess.check_output([
                    'openssl', 'crl2pkcs7', '-nocrl',
                    '-certfile', pem_file,
                    '-outform', 'DER'
                ], stderr=subprocess.DEVNULL, timeout=30)

                return Response(
                    p7b_output,
                    mimetype='application/x-pkcs7-certificates',
                    headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(certificate.descr or certificate.refid)}.p7b"'}
                )
            finally:
                os.unlink(pem_file)

        elif export_format == 'pfx':
            # PFX is same as PKCS12
            if not password:
                return error_response('Password required for PFX export', 400)
            if not certificate.prv:
                return error_response('Certificate has no private key for PFX export', 400)

            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem = load_pem_bytes(certificate.prv, context=f"certificate {certificate.id}")
            private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())

            # Build CA chain if requested (inline stored chain or managed CA)
            ca_certs = _build_ca_chain(certificate, cert_pem) if include_chain else []

            p12_bytes = pkcs12.serialize_key_and_certificates(
                name=(certificate.descr or certificate.refid).encode(),
                key=private_key,
                cert=cert,
                cas=_named_cas(ca_certs),
                encryption_algorithm=serialization.BestAvailableEncryption(password.encode())
            )

            return Response(
                p12_bytes,
                mimetype='application/x-pkcs12',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(certificate.descr or certificate.refid)}.pfx"'}
            )

        elif export_format == 'jks':
            if not password:
                return error_response('Password required for JKS export', 400)
            if not certificate.prv:
                return error_response('Certificate has no private key for JKS export', 400)

            import jks as pyjks
            import time

            cert_obj = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem_data = load_pem_bytes(certificate.prv, context=f"certificate {certificate.id}")
            private_key = serialization.load_pem_private_key(key_pem_data, password=None, backend=default_backend())

            cert_der = cert_obj.public_bytes(serialization.Encoding.DER)
            key_pkcs8 = private_key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()
            )

            cert_chain = [("X.509", cert_der)]

            if include_chain:
                for ca_cert in _build_ca_chain(certificate, cert_pem):
                    cert_chain.append(("X.509", ca_cert.public_bytes(serialization.Encoding.DER)))

            ts = int(time.time() * 1000)
            pke = pyjks.PrivateKeyEntry(
                alias=(certificate.descr or certificate.refid).lower().replace(' ', '-'),
                cert_chain=cert_chain,
                pkey_pkcs8=key_pkcs8,
                timestamp=ts,
            )

            keystore = pyjks.KeyStore.new("jks", [pke])
            jks_bytes = keystore.saves(password)

            return Response(
                jks_bytes,
                mimetype='application/x-java-keystore',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(certificate.descr or certificate.refid)}.jks"'}
            )

        else:
            return error_response(f'Unsupported format: {export_format}', 400)

    except Exception as e:
        logger.error(f"Certificate export failed: {e}")
        return error_response('Export failed', 500)
