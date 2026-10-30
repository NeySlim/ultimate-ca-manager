"""
Certificates Export Routes
/api/v2/certificates/export - Export all or single certificate
"""

import base64
import json
import logging
import zipfile
from flask import Response, request, g
from auth.unified import require_auth, has_permission
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import pkcs12
from utils.pkcs12_export import legacy_flag, pkcs12_encryption
from utils.algorithm_refusal import refuse_unexportable_key
from utils.p7b import p7b_from_pems
import fips_mode
from fips_mode import FipsRestricted

from models import db, Certificate, CA
from utils.cert_status import issued_certificates
from models.truststore import TrustedCertificate
from utils.response import success_response, error_response
from utils.export_password import (export_password_policy,
                                   validate_export_password)
from utils.sanitize import sanitize_filename
from utils.key_codec import load_pem_bytes
from utils.cert_issuer import (
    authority_key_identifier_hex, certificate_signed_by, is_self_signed,
)
from utils.export_options import json_boolean, query_boolean
from services.key_export_audit import audit_key_export
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


def _normalized_key_identifier(value):
    """Normalize a persisted AKI/SKI regardless of case or separators."""
    if not value:
        return None
    return str(value).replace(':', '').replace('-', '').replace(' ', '').lower()


def _resolve_issuer_cert(cert):
    """Find the issuer certificate of *cert* among locally known sources.

    Looks up managed CAs (by AKI→SKI, then issuer DN) and then the Trust Store
    (by issuer DN). Returns the issuer x509.Certificate or None. Used to fill in
    a missing chain when it is neither stored inline nor reachable via `caref`.
    """
    issuer_dn = cert.issuer.rfc4514_string()
    aki = authority_key_identifier_hex(cert)
    candidates = []
    seen = set()

    def add_managed(rows):
        for row in rows:
            identity = ('ca', row.id)
            if row.crt and identity not in seen:
                seen.add(identity)
                candidates.append(('managed', row))

    # Imported identifiers are not guaranteed to use UCM's usual upper-case,
    # colon-separated representation. Normalize them before shortlisting. Even
    # an identifier match is only a shortlist: the signature remains decisive.
    if aki:
        normalized_aki = _normalized_key_identifier(aki)
        add_managed(
            row for row in CA.query.filter(CA.ski.isnot(None)).all()
            if _normalized_key_identifier(row.ski) == normalized_aki
        )
    add_managed(CA.query.filter(CA.subject == issuer_dn).all())

    for row in TrustedCertificate.query.filter_by(subject=issuer_dn).all():
        identity = ('trust', row.id)
        if row.certificate_pem and identity not in seen:
            seen.add(identity)
            candidates.append(('trust', row))

    for source, row in candidates:
        try:
            pem = base64.b64decode(row.crt) if source == 'managed' else row.certificate_pem.encode()
            candidate = x509.load_pem_x509_certificate(pem, default_backend())
            if candidate.subject == cert.issuer and certificate_signed_by(cert, candidate):
                return candidate
        except Exception:
            continue
    return None


def _build_ca_chain(certificate, cert_pem, include_root=True, variant='auto'):
    """Build the issuing CA chain, preserving the historical full-chain default.

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
        from utils.ca_chain import issuer_chain
        start = CA.query.filter_by(refid=certificate.caref).first()
        for link in issuer_chain(start, variant):
            try:
                chain.append(x509.load_pem_x509_certificate(link.pem, default_backend()))
            except Exception:
                pass

    # 3. Extend/complete the chain using locally known issuers until we reach a
    #    self-signed root (or can no longer resolve the next issuer).
    seen = {c.fingerprint(hashes.SHA256()) for c in chain}
    top = chain[-1] if chain else leaf
    guard = 0
    while top is not None and guard < 10:
        guard += 1
        if is_self_signed(top):
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

    # TLS servers normally send the leaf plus intermediate CA certificates.
    # The self-signed trust anchor belongs in the client's trust store and is
    # excluded by default. Keep an explicit opt-in for packaging/import uses.
    if not include_root and chain:
        top = chain[-1]
        if is_self_signed(top):
            chain.pop()

    return chain


def requested_chain_variant(source, certificate):
    """``(variant, None)`` from ``chain_variant`` in *source*, or ``(None, 400 response)`` when the chain cannot present it."""
    from utils.ca_chain import AUTO, ChainVariantError, parse_variant, variant_ids
    value = source.get('chain_variant') or AUTO
    try:
        parse_variant(value)
        start = CA.query.filter_by(refid=certificate.caref).first() if certificate.caref else None
        if value not in variant_ids(start):
            raise ChainVariantError(f'Chain variant {value} is not part of the chain of this certificate')
    except ChainVariantError as exc:
        return None, error_response(str(exc), 400)
    return value, None


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
        try:
            include_chain = json_boolean(data, 'include_chain', False)
            legacy_value = json_boolean(data, 'legacy', False)
        except ValueError as exc:
            return error_response(str(exc), 400)
        password = data.get('password')
        legacy = legacy_flag(legacy_value)  # 3DES/SHA-1 profile (#331)
    else:
        export_format = request.args.get('format', 'pem').lower()
        try:
            include_chain = query_boolean(request.args, 'include_chain', False)
        except ValueError as exc:
            return error_response(str(exc), 400)
        password = request.args.get('password')
        legacy = False

    certificates = issued_certificates().all()
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
            p7b_output = p7b_from_pems(base64.b64decode(cert.crt) for cert in certificates if cert.crt)
            return Response(
                p7b_output,
                mimetype='application/x-pkcs7-certificates',
                headers={'Content-Disposition': 'attachment; filename="certificates.p7b"'}
            )

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
        include_root: bool - Include self-signed Root CA (default: false)
        password: string - Required for PKCS12 and JKS
    """

    certificate = db.session.get(Certificate, cert_id)
    if not certificate:
        return error_response('Certificate not found', 404)

    if not certificate.crt:
        return error_response('Certificate data not available', 400)

    # Support both GET (query params) and POST (body) for security
    if request.method == 'POST' and request.is_json:
        data = request.get_json()
        export_format = data.get('format', 'pem').lower()
        try:
            include_key = json_boolean(data, 'include_key', False)
            include_chain = json_boolean(data, 'include_chain', False)
            include_root = json_boolean(data, 'include_root', False)
            legacy_value = json_boolean(data, 'legacy', False)
        except ValueError as exc:
            return error_response(str(exc), 400)
        password = data.get('password')
        # PKCS#12 compatibility profile (3DES/SHA-1) for importers that
        # reject the AES-256/SHA-256 default (#331)
        legacy = legacy_flag(legacy_value)
        variant, variant_err = requested_chain_variant(data, certificate)
    else:
        export_format = request.args.get('format', 'pem').lower()
        try:
            include_key = query_boolean(request.args, 'include_key', False)
            include_chain = query_boolean(request.args, 'include_chain', False)
            include_root = query_boolean(request.args, 'include_root', False)
        except ValueError as exc:
            return error_response(str(exc), 400)
        password = request.args.get('password')
        legacy = False
        variant, variant_err = requested_chain_variant(request.args, certificate)
        # SECURITY: never accept passwords via query string
        if password or export_format in ('pkcs12', 'pfx', 'jks'):
            if password:
                logger.warning(
                    "Rejected certificate export with password in query string "
                    "(cert_id=%s): client must POST with JSON body",
                    cert_id,
                )
            return error_response(
                'Password must be sent via POST body (JSON), not query string',
                400,
            )

    if variant_err:
        return variant_err

    # One rule for the password that encrypts the bundle (utils/export_password).
    # This route used to check presence only, so a one-character password
    # produced a PKCS#12 and a 200 while the export dialog refused anything
    # under eight -- the server was the permissive one, and only a script
    # could reach it.
    if export_format in ('pkcs12', 'pfx', 'jks', 'key') or password:
        pw_err = validate_export_password(
            password, allow_empty=(export_format == 'key'))
        if pw_err:
            return error_response(pw_err, 400)

    # Direct private-key export is gated behind the admin-only read:private_keys
    # scope (not write:certificates, which operators hold): otherwise the
    # approval-gated Key Recovery flow would be pointless, since anyone who could
    # request a recovery could just export the key here without approval (#232).
    if include_key or export_format in ('pkcs12', 'pfx', 'key', 'jks'):
        if not has_permission('read:private_keys', g.permissions):
            return error_response(
                'Private key export requires the read:private_keys permission; '
                'roles without it must use the Key Recovery approval flow', 403
            )

    try:
        cert_pem = base64.b64decode(certificate.crt)
        stored_certs = _split_pem_certs(cert_pem)
        leaf_pem = (
            stored_certs[0].public_bytes(serialization.Encoding.PEM)
            if stored_certs else cert_pem
        )

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
            audit_key_export('certificate', certificate.id, certificate.descr or certificate.refid,
                             export_format, password)
            return Response(
                key_pem,
                mimetype='application/x-pem-file',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(certificate.descr or certificate.refid)}.key"'}
            )

        if export_format == 'pem':
            # A stored certificate may already contain an inline full chain.
            # Start with the leaf only so include_chain/include_root are honored.
            result = leaf_pem
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
            if include_chain:
                for ca_cert in _build_ca_chain(
                    certificate, cert_pem, include_root=include_root, variant=variant
                ):
                    if not result.endswith(b'\n'):
                        result += b'\n'
                    result += ca_cert.public_bytes(serialization.Encoding.PEM)
                if include_key:
                    filename = f"{sanitize_filename(certificate.descr or certificate.refid)}_full_chain.pem"
                else:
                    filename = f"{sanitize_filename(certificate.descr or certificate.refid)}_chain.pem"

            if include_key and certificate.prv:
                audit_key_export('certificate', certificate.id, certificate.descr or certificate.refid,
                                 export_format, password)
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
            refuse_unexportable_key(private_key, export_format)

            # Build CA chain if requested (inline stored chain or managed CA)
            ca_certs = (
                _build_ca_chain(certificate, cert_pem, include_root=include_root, variant=variant)
                if include_chain else []
            )

            p12_bytes = pkcs12.serialize_key_and_certificates(
                name=(certificate.descr or certificate.refid).encode(),
                key=private_key,
                cert=cert,
                cas=_named_cas(ca_certs),
                encryption_algorithm=pkcs12_encryption(password, legacy, caref=certificate.caref),
            )

            audit_key_export('certificate', certificate.id, certificate.descr or certificate.refid,
                             export_format, password)
            return Response(
                p12_bytes,
                mimetype='application/x-pkcs12',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(certificate.descr or certificate.refid)}.p12"'}
            )

        elif export_format == 'pkcs7' or export_format == 'p7b':
            pems = [leaf_pem]
            if include_chain:
                pems += [ca_cert.public_bytes(serialization.Encoding.PEM) for ca_cert in _build_ca_chain(
                    certificate, cert_pem, include_root=include_root, variant=variant)]
            return Response(
                p7b_from_pems(pems),
                mimetype='application/x-pkcs7-certificates',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(certificate.descr or certificate.refid)}.p7b"'}
            )

        elif export_format == 'pfx':
            # PFX is same as PKCS12
            if not password:
                return error_response('Password required for PFX export', 400)
            if not certificate.prv:
                return error_response('Certificate has no private key for PFX export', 400)

            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem = load_pem_bytes(certificate.prv, context=f"certificate {certificate.id}")
            private_key = serialization.load_pem_private_key(key_pem, password=None, backend=default_backend())
            refuse_unexportable_key(private_key, export_format)

            # Build CA chain if requested (inline stored chain or managed CA)
            ca_certs = (
                _build_ca_chain(certificate, cert_pem, include_root=include_root, variant=variant)
                if include_chain else []
            )

            p12_bytes = pkcs12.serialize_key_and_certificates(
                name=(certificate.descr or certificate.refid).encode(),
                key=private_key,
                cert=cert,
                cas=_named_cas(ca_certs),
                encryption_algorithm=pkcs12_encryption(password, legacy, caref=certificate.caref),
            )

            audit_key_export('certificate', certificate.id, certificate.descr or certificate.refid,
                             export_format, password)
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
            fips_mode.refuse('JKS export')

            import jks as pyjks
            import time

            cert_obj = x509.load_pem_x509_certificate(cert_pem, default_backend())
            key_pem_data = load_pem_bytes(certificate.prv, context=f"certificate {certificate.id}")
            private_key = serialization.load_pem_private_key(key_pem_data, password=None, backend=default_backend())
            refuse_unexportable_key(private_key, 'jks')

            cert_der = cert_obj.public_bytes(serialization.Encoding.DER)
            key_pkcs8 = private_key.private_bytes(
                serialization.Encoding.DER,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()
            )

            cert_chain = [("X.509", cert_der)]

            if include_chain:
                for ca_cert in _build_ca_chain(
                    certificate, cert_pem, include_root=include_root, variant=variant
                ):
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

            audit_key_export('certificate', certificate.id, certificate.descr or certificate.refid,
                             export_format, password)
            return Response(
                jks_bytes,
                mimetype='application/x-java-keystore',
                headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(certificate.descr or certificate.refid)}.jks"'}
            )

        else:
            return error_response(f'Unsupported format: {export_format}', 400)

    except FipsRestricted:
        raise  # the app handler answers 400 with the FIPS problem type
    except Exception as e:
        logger.error(f"Certificate export failed: {e}")
        return error_response('Export failed', 500)


@bp.route('/api/v2/export/password-policy', methods=['GET'])
@require_auth()
def get_export_password_policy():
    """The length rule every export route applies to its password.

    Published so the export dialog states the rule instead of restating it.
    It used to carry its own floor of eight and no ceiling, which made it
    stricter than one route and more permissive than another at the same
    time (utils/export_password).
    """
    return success_response(data=export_password_policy())
