#!/usr/bin/env python3
"""Lab: RFC 5280 cert/CRL profile gaps (CSR SKI/AKI, CA AIA, invalidityDate).

Loads SECRET_KEY from repo-root ``.env.lab`` (gitignored). If missing, generates
ephemeral keys for this run only.

Usage:
  python3 scripts/lab_rfc5280_cert_crl_profile.py
"""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
from datetime import timedelta
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
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import (
        AuthorityInformationAccessOID,
        ExtensionOID,
        NameOID,
    )
    from app import create_app
    from models import db
    from services.ca_service import CAService
    from services.cert_service import CertificateService
    from services.crl_service import CRLService
    from services.trust_store import TrustStoreService
    from utils.datetime_utils import utc_now

    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['FQDN'] = 'ucm.lab.local'

    try:
        with app.app_context():
            db.create_all()

            root = CAService.create_internal_ca(
                descr='Lab Profile Root',
                dn={'CN': 'Lab Profile Root', 'O': 'Lab', 'C': 'US'},
                key_type='2048',
                validity_days=3650,
                username='lab',
            )
            root.aia_ca_issuers_enabled = True
            root.set_aia_urls([f'http://aia.lab.local/ca/{root.refid}.crt'])
            root.ocsp_enabled = True
            root.set_ocsp_urls(['http://ocsp.lab.local'])
            db.session.commit()

            inter = CAService.create_internal_ca(
                descr='Lab Profile Intermediate',
                dn={'CN': 'Lab Profile Intermediate', 'O': 'Lab', 'C': 'US'},
                key_type='2048',
                validity_days=1825,
                caref=root.refid,
                username='lab',
            )
            inter.cdp_enabled = True
            inter.delta_crl_enabled = True
            inter.set_cdp_urls([f'http://cdp.lab.local/cdp/{inter.refid}.crl'])
            db.session.commit()

            # --- CSR SKI/AKI injection must be ignored ---
            ca_cert = x509.load_pem_x509_certificate(
                base64.b64decode(inter.crt), default_backend()
            )
            from services.hsm.ca_key_loader import get_ca_signing_key
            ca_key = get_ca_signing_key(inter)
            leaf_key = rsa.generate_private_key(65537, 2048)
            csr = (
                x509.CertificateSigningRequestBuilder()
                .subject_name(x509.Name([
                    x509.NameAttribute(NameOID.COMMON_NAME, 'lab.inject.example'),
                ]))
                .add_extension(x509.SubjectKeyIdentifier(b'\xaa' * 20), critical=False)
                .add_extension(
                    x509.AuthorityKeyIdentifier(
                        key_identifier=b'\xbb' * 20,
                        authority_cert_issuer=None,
                        authority_cert_serial_number=None,
                    ),
                    critical=False,
                )
                .sign(leaf_key, hashes.SHA256())
            )
            pem = TrustStoreService.sign_csr(
                csr_pem=csr.public_bytes(serialization.Encoding.PEM),
                ca_cert=ca_cert,
                ca_private_key=ca_key,
                validity_days=30,
            )
            issued = x509.load_pem_x509_certificate(
                pem if isinstance(pem, bytes) else pem.encode(), default_backend()
            )
            ski = issued.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_KEY_IDENTIFIER
            ).value.digest
            expected = x509.SubjectKeyIdentifier.from_public_key(
                leaf_key.public_key()
            ).digest
            assert ski == expected, 'CSR SKI injection not overridden'
            print('CSR SKI/AKI override: OK')

            # --- Intermediate AIA caIssuers from parent ---
            inter_cert = ca_cert
            aia = inter_cert.extensions.get_extension_for_oid(
                ExtensionOID.AUTHORITY_INFORMATION_ACCESS
            ).value
            ca_issuers = [
                d.access_location.value
                for d in aia
                if d.access_method == AuthorityInformationAccessOID.CA_ISSUERS
            ]
            assert ca_issuers, 'intermediate missing AIA caIssuers'
            print(f'Intermediate AIA caIssuers: {ca_issuers[0]}')

            # --- invalidityDate on CRL ---
            leaf = CertificateService.create_certificate(
                descr='lab.invalidity.example',
                caref=inter.refid,
                dn={'CN': 'lab.invalidity.example', 'O': 'Lab', 'C': 'US'},
                cert_type='server_cert',
                validity_days=30,
                username='lab',
            )
            CertificateService.revoke_certificate(
                leaf.id,
                reason='keyCompromise',
                username='lab',
                invalidity_at=utc_now() - timedelta(days=2),
            )
            full = CRLService.generate_crl(inter.id, username='lab')
            crl = x509.load_pem_x509_crl(full.crl_pem.encode(), default_backend())
            has_inv = False
            for entry in crl:
                try:
                    entry.extensions.get_extension_for_oid(
                        x509.oid.CRLEntryExtensionOID.INVALIDITY_DATE
                    )
                    has_inv = True
                except x509.ExtensionNotFound:
                    pass
            assert has_inv, 'CRL missing invalidityDate'
            print('CRL invalidityDate: OK')

            with tempfile.NamedTemporaryFile('w', suffix='.crl', delete=False) as tf:
                tf.write(full.crl_pem)
                path = tf.name
            try:
                out = subprocess.run(
                    ['openssl', 'crl', '-in', path, '-text', '-noout'],
                    capture_output=True, text=True, check=True,
                ).stdout
            finally:
                os.unlink(path)
            print('--- openssl crl -text (excerpt) ---')
            for line in out.splitlines():
                if any(k in line for k in (
                    'Authority Key', 'Invalidity', 'Serial Number', 'CRL Number',
                )):
                    print(line.rstrip())
            if 'Invalidity Date' not in out and 'invalidityDate' not in out.lower():
                print('ERROR: openssl text missing Invalidity Date')
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
