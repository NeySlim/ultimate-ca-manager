"""
AIA CA Issuers Routes — Public CA certificate download
Serves CA certificates for AIA CA Issuers extension (RFC 5280 §4.2.2.1).
Supports both refid-based (preferred) and legacy numeric ID-based URLs.
"""
import base64
from flask import Blueprint, Response, abort
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, pkcs7
import logging

from models import db, CA

logger = logging.getLogger(__name__)

aia_bp = Blueprint('aia', __name__)


def _resolve_ca(ca_ref):
    """Resolve CA by refid (UUID) or legacy numeric ID"""
    ca = CA.query.filter_by(refid=ca_ref).first()
    if ca:
        return ca
    # Opt-in named URLs (#207): resolve by immutable slug
    ca = CA.query.filter_by(url_slug=ca_ref).first()
    if ca:
        return ca
    from services.ca.cross_repair import alias_target
    try:
        ca = db.session.get(CA, int(ca_ref))
    except (ValueError, TypeError):
        ca = None
    return ca or alias_target(ca_ref)


# Clients and proxies keep an AIA answer for 24 h: a change of the served cross-certificate
# reaches them only after that delay.
AIA_CACHE_CONTROL = 'public, max-age=86400, must-revalidate'


def _issuer_certificate(ca, ref=None):
    """The certificate AIA presents for *ca*: its served cross-certificate if any, else its own.

    A URL of a converted duplicate (*ref*) keeps presenting the cross-certificate it served."""
    from services.ca import cross_certs
    from services.ca.cross_repair import alias_cross
    row = None
    if ref and ref not in (ca.refid, ca.url_slug):
        row = alias_cross(ref, ca)
    row = row or cross_certs.served_for(ca)
    return cross_certs.certificate_of(row) if row is not None else x509.load_pem_x509_certificate(base64.b64decode(ca.crt))


def _aia_response(body, mimetype, filename):
    return Response(body, status=200, mimetype=mimetype, headers={
        'Content-Disposition': f'inline; filename="{filename}"',
        'Cache-Control': AIA_CACHE_CONTROL,
    })


@aia_bp.route('/<ca_ref>.cer')
def get_ca_cert_der(ca_ref):
    """CA certificate in DER (application/pkix-cert), the standard AIA CA Issuers format (RFC 5280)."""
    ca = _resolve_ca(ca_ref)
    if not ca or not ca.crt:
        abort(404)
    try:
        cert_der = _issuer_certificate(ca, ca_ref).public_bytes(Encoding.DER)
    except Exception as e:
        logger.error(f"AIA: failed to encode CA {ca_ref} certificate: {e}")
        abort(500)
    return _aia_response(cert_der, 'application/pkix-cert', f'{ca.refid}.cer')


@aia_bp.route('/<ca_ref>.pem')
def get_ca_cert_pem(ca_ref):
    """CA certificate in PEM."""
    ca = _resolve_ca(ca_ref)
    if not ca or not ca.crt:
        abort(404)
    try:
        cert_pem = _issuer_certificate(ca, ca_ref).public_bytes(Encoding.PEM)
    except Exception as e:
        logger.error(f"AIA: failed to load CA {ca_ref} certificate: {e}")
        abort(500)
    return _aia_response(cert_pem, 'application/x-pem-file', f'{ca.refid}.pem')


@aia_bp.route('/<ca_ref>.p7c')
def get_ca_certs_p7c(ca_ref):
    """Certs-only CMS bundle (RFC 5280 4.2.2.1): the CA's own certificate and its servable cross-certificates."""
    from services.ca import cross_certs
    ca = _resolve_ca(ca_ref)
    if not ca or not ca.crt:
        abort(404)
    try:
        certs = [x509.load_pem_x509_certificate(base64.b64decode(ca.crt))]
        certs += [cross_certs.certificate_of(row) for row in cross_certs.list_for(ca) if row.servable]
        bundle = pkcs7.serialize_certificates(certs, Encoding.DER)
    except Exception as e:
        logger.error(f"AIA: failed to build the bundle of CA {ca_ref}: {e}")
        abort(500)
    return _aia_response(bundle, 'application/pkcs7-mime', f'{ca.refid}.p7c')


@aia_bp.route('/<ca_ref>/cross/<int:xid>.cer')
def get_ca_cross_cert_der(ca_ref, xid):
    """One cross-certificate of the CA in DER; a revoked, expired or not yet valid one is not published."""
    from services.ca import cross_certs
    from models.ca_cross_certificate import CACrossCertificate
    ca = _resolve_ca(ca_ref)
    row = db.session.get(CACrossCertificate, xid) if ca else None
    if row is None or row.ca_id != ca.id or not row.servable:
        abort(404)
    try:
        cert_der = cross_certs.certificate_of(row).public_bytes(Encoding.DER)
    except Exception as e:
        logger.error(f"AIA: failed to encode cross-certificate {xid} of CA {ca_ref}: {e}")
        abort(500)
    return _aia_response(cert_der, 'application/pkix-cert', f'{ca.refid}-cross-{xid}.cer')
