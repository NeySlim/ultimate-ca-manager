"""
CDP (CRL Distribution Point) Routes
"""
from flask import Blueprint, send_file, abort
from pathlib import Path
from config.settings import DATA_DIR

cdp_bp = Blueprint('cdp', __name__)


@cdp_bp.route('/<ca_id>.crl')
def get_crl(ca_id):
    """Serve CRL file"""
    crl_path = DATA_DIR / 'crl' / f'{ca_id}.crl'
    
    if not crl_path.exists():
        abort(404)
    
    return send_file(crl_path, mimetype='application/pkix-crl')
