#!/usr/bin/env python3
"""Lab: generate a CRL and verify AKI / extensions with openssl crl -text.

Loads SECRET_KEY from repo-root ``.env.lab`` (gitignored). If missing, generates
ephemeral keys for this run only (create_app refuses INSTALL_TIME_PLACEHOLDER).

Usage:
  python3 scripts/lab_crl_openssl_verify.py
"""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'
ENV_LAB = ROOT / '.env.lab'


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, val = line.partition('=')
        os.environ.setdefault(key.strip(), val.strip())


def _ensure_secrets() -> None:
    _load_dotenv(ENV_LAB)
    if not os.environ.get('SECRET_KEY') or os.environ['SECRET_KEY'] == 'INSTALL_TIME_PLACEHOLDER':
        import secrets
        os.environ['SECRET_KEY'] = secrets.token_urlsafe(48)
        os.environ.setdefault('JWT_SECRET_KEY', secrets.token_urlsafe(48))
        print('NOTE: no usable SECRET_KEY — using ephemeral key for this run')
        print(f'      create {ENV_LAB} (gitignored) for a stable lab secret')
    else:
        print(f'Loaded secrets from {ENV_LAB}')
    os.environ.setdefault('JWT_SECRET_KEY', os.environ['SECRET_KEY'])
    os.environ.setdefault('UCM_ENV', 'lab')
    os.environ.setdefault('HTTP_REDIRECT', 'false')
    os.environ.setdefault('CSRF_DISABLED', 'true')
    os.environ.setdefault('UCM_DEV_MODE', 'true')
    os.environ.setdefault('INITIAL_ADMIN_PASSWORD', 'changeme123')


def main() -> int:
    _ensure_secrets()

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        os.environ['UCM_DATABASE_PATH'] = f.name
        temp_db = f.name

    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)

    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509.oid import ExtensionOID
    from app import create_app
    from models import db
    from services.ca_service import CAService
    from services.crl_service import CRLService

    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['FQDN'] = 'ucm.lab.local'

    try:
        with app.app_context():
            db.create_all()

            root = CAService.create_internal_ca(
                descr='Lab Root CA',
                dn={'CN': 'Lab Root CA', 'O': 'Lab', 'C': 'US'},
                key_type='2048',
                validity_days=3650,
                username='lab',
            )
            inter = CAService.create_internal_ca(
                descr='Lab Intermediate CA',
                dn={'CN': 'Lab Intermediate CA', 'O': 'Lab', 'C': 'US'},
                key_type='2048',
                validity_days=1825,
                caref=root.refid,
                username='lab',
            )

            inter.cdp_enabled = True
            inter.delta_crl_enabled = True
            inter.set_cdp_urls([f'http://cdp.lab.local/cdp/{inter.refid}.crl'])
            db.session.commit()

            full_meta = CRLService.generate_crl(inter.id, username='lab')
            delta_meta = CRLService.generate_delta_crl(inter.id, username='lab')

            ca_cert = x509.load_pem_x509_certificate(
                base64.b64decode(inter.crt), default_backend()
            )
            ski = ca_cert.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_KEY_IDENTIFIER
            ).value.digest.hex()
            ca_aki = ca_cert.extensions.get_extension_for_oid(
                ExtensionOID.AUTHORITY_KEY_IDENTIFIER
            ).value.key_identifier.hex()

            print(f'Intermediate SKI: {ski}')
            print(f'Intermediate AKI (parent): {ca_aki}')
            assert ski != ca_aki, 'lab setup broken: intermediate AKI==SKI'

            for label, pem in (('full', full_meta.crl_pem), ('delta', delta_meta.crl_pem)):
                crl = x509.load_pem_x509_crl(pem.encode(), default_backend())
                crl_aki = crl.extensions.get_extension_for_oid(
                    ExtensionOID.AUTHORITY_KEY_IDENTIFIER
                ).value.key_identifier.hex()
                match = 'MATCH' if crl_aki == ski else 'MISMATCH'
                print(f'CRL ({label}) AKI: {crl_aki} → {match} vs SKI')
                if crl_aki != ski:
                    return 1
                assert crl.is_signature_valid(ca_cert.public_key())

                with tempfile.NamedTemporaryFile('w', suffix='.crl', delete=False) as tf:
                    tf.write(pem)
                    path = tf.name
                try:
                    out = subprocess.run(
                        ['openssl', 'crl', '-in', path, '-text', '-noout'],
                        capture_output=True, text=True, check=True,
                    ).stdout
                finally:
                    os.unlink(path)

                print(f'--- openssl crl -text ({label}) ---')
                for line in out.splitlines():
                    if any(k in line for k in (
                        'Authority Key', 'Key Identifier', 'CRL Number',
                        'Freshest', 'Delta CRL', 'Issuing Distribution',
                    )):
                        print(line.rstrip())
                if 'X509v3 Authority Key Identifier' not in out:
                    print('ERROR: missing AKI in openssl output')
                    return 1
                if label == 'delta' and 'Delta CRL Indicator' not in out:
                    print('ERROR: missing Delta CRL Indicator')
                    return 1

            print('LAB OK')
            return 0
    finally:
        if os.path.exists(temp_db):
            os.unlink(temp_db)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'LAB FAILED: {exc}', file=sys.stderr)
        raise
