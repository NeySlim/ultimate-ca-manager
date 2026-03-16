"""
CDP (CRL Distribution Point) Routes
Serves CRLs from database (RFC 5280 §4.2.1.13)
Supports both refid-based (preferred) and legacy numeric ID-based URLs.
"""
from flask import Blueprint, Response, abort
import logging

from models import db, CA
from services.crl_service import CRLService

logger = logging.getLogger(__name__)

cdp_bp = Blueprint('cdp', __name__)


def _resolve_ca(ca_ref):
    """Resolve CA by refid (UUID) or legacy numeric ID"""
    # Try refid first (preferred, non-sequential)
    ca = CA.query.filter_by(refid=ca_ref).first()
    if ca:
        return ca
    # Fallback to numeric ID for backwards compatibility
    try:
        ca_id_int = int(ca_ref)
        return CA.query.get(ca_id_int)
    except (ValueError, TypeError):
        return None


@cdp_bp.route('/<ca_ref>.crl')
def get_crl(ca_ref):
    """
    Serve CRL file from database.
    Falls back to generating a fresh CRL if none cached.
    """
    ca = _resolve_ca(ca_ref)
    if not ca:
        abort(404)
    
    # Get latest CRL from database
    crl_meta = CRLService.get_latest_crl(ca.id)
    
    if not crl_meta or not crl_meta.crl_der:
        # No CRL in DB — try to generate one if CA has a private key
        if ca.has_private_key and ca.cdp_enabled:
            try:
                crl_meta = CRLService.generate_crl(ca.id)
            except Exception as e:
                logger.error(f"CDP: failed to generate CRL for CA {ca.refid}: {e}")
                abort(404)
        else:
            abort(404)
    
    return Response(
        crl_meta.crl_der,
        status=200,
        mimetype='application/pkix-crl',
        headers={
            'Content-Disposition': f'attachment; filename="{ca.refid}.crl"',
            'Cache-Control': 'public, max-age=3600, must-revalidate',
            'Last-Modified': crl_meta.this_update.strftime('%a, %d %b %Y %H:%M:%S GMT'),
        }
    )


@cdp_bp.route('/<ca_ref>-delta.crl')
def get_delta_crl(ca_ref):
    """Serve delta CRL file from database"""
    ca = _resolve_ca(ca_ref)
    if not ca:
        abort(404)
    
    delta_crl = CRLService.get_latest_delta_crl(ca.id)
    
    if not delta_crl or not delta_crl.crl_der:
        abort(404)
    
    return Response(
        delta_crl.crl_der,
        status=200,
        mimetype='application/pkix-crl',
        headers={
            'Content-Disposition': f'attachment; filename="{ca.refid}-delta.crl"',
            'Cache-Control': 'public, max-age=900, must-revalidate',
            'Last-Modified': delta_crl.this_update.strftime('%a, %d %b %Y %H:%M:%S GMT'),
        }
    )
