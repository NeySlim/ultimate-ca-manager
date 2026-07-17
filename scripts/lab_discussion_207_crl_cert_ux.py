#!/usr/bin/env python3
"""Lab: discussion #207 CRL / cert UX (validity vs publish, digest, skew, filename).

Loads SECRET_KEY from repo-root ``.env.lab`` (gitignored). If missing, generates
ephemeral keys for this run only.

Usage:
  python3 scripts/lab_discussion_207_crl_cert_ux.py
"""
from __future__ import annotations

import base64
import os
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
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID
    from app import create_app
    from models import db
    from models.certificate_template import CertificateTemplate
    from services.ca_service import CAService
    from services.crl_service import CRLService
    from services.crl_scheduler_task import CRLSchedulerTask
    from services.hsm.ca_key_loader import get_ca_signing_key
    from services.trust_store import TrustStoreService
    from utils.datetime_utils import (
        DEFAULT_CERT_NOT_BEFORE_SKEW_MINUTES,
        cert_not_before,
        utc_now,
    )
    from utils.sanitize import crl_download_filename

    app = create_app('testing')
    app.config['TESTING'] = True
    failures = 0

    def check(cond: bool, msg: str) -> None:
        nonlocal failures
        if cond:
            print(f'  OK  {msg}')
        else:
            print(f' FAIL {msg}')
            failures += 1

    try:
        with app.app_context():
            db.create_all()
            print('\n== Discussion #207 lab ==')

            before = utc_now()
            nb = cert_not_before()
            skew = (before - nb).total_seconds() / 60
            check(
                abs(skew - DEFAULT_CERT_NOT_BEFORE_SKEW_MINUTES) < 1.5,
                f'cert_not_before skew ≈{DEFAULT_CERT_NOT_BEFORE_SKEW_MINUTES}m (got {skew:.1f}m)',
            )

            ca = CAService.create_internal_ca(
                descr='Lab 207 Root',
                dn={'CN': 'Lab 207 Root', 'O': 'Lab', 'C': 'US'},
                key_type='2048',
                validity_days=3650,
                username='lab',
            )
            ca.cdp_enabled = True
            ca.crl_validity_days = 14
            ca.crl_publish_interval_hours = 24
            ca.crl_digest = 'sha384'
            ca.set_cdp_urls([f'http://cdp.test.local/cdp/{ca.refid}.crl'])
            db.session.commit()

            fname = crl_download_filename(ca)
            check(
                fname.startswith('Lab-207-Root-') and fname.endswith('.crl'),
                f'CRL download filename slug+refid: {fname}',
            )
            check(ca.refid[:8] in fname, 'filename embeds refid prefix')

            meta = CRLService.generate_crl(ca.id, username='lab')
            check(meta.next_publish is not None, 'next_publish set on full CRL')
            check(
                abs((meta.next_update - meta.this_update).days - 14) <= 1,
                f'nextUpdate ≈14d (got {(meta.next_update - meta.this_update).days}d)',
            )
            check(
                abs((meta.next_publish - meta.this_update).total_seconds() / 3600 - 24) < 1,
                'next_publish ≈24h after thisUpdate',
            )

            crl = x509.load_pem_x509_crl(meta.crl_pem.encode(), default_backend())
            check(
                isinstance(crl.signature_hash_algorithm, hashes.SHA384),
                f'CRL signed with SHA-384 (got {crl.signature_hash_algorithm.name})',
            )

            meta.next_publish = utc_now() - timedelta(minutes=1)
            db.session.commit()
            should, reason = CRLSchedulerTask.should_regenerate_crl(ca.id)
            check(should is True, f'scheduler regenerate on next_publish due ({reason})')

            tpl = CertificateTemplate(
                name='Lab 207 SHA384',
                description='lab',
                template_type='web_server',
                key_type='RSA-2048',
                validity_days=30,
                digest='sha384',
                dn_template='{"CN":"{hostname}"}',
                extensions_template=(
                    '{"key_usage":["digitalSignature"],'
                    '"extended_key_usage":["serverAuth"]}'
                ),
                is_active=True,
                created_by='lab',
            )
            db.session.add(tpl)
            db.session.commit()
            check(tpl.to_dict().get('usage_count') == 0, 'template usage_count starts at 0')

            ca_cert = x509.load_pem_x509_certificate(
                base64.b64decode(ca.crt), default_backend()
            )
            ca_key = get_ca_signing_key(ca)
            subject = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, 'lab207.example.test'),
            ])
            cert_pem, _key_pem = TrustStoreService.create_certificate(
                subject=subject,
                ca_cert=ca_cert,
                ca_private_key=ca_key,
                cert_type='server_cert',
                validity_days=30,
                digest='sha384',
                key_type='2048',
            )
            leaf = x509.load_pem_x509_certificate(cert_pem, default_backend())
            check(
                isinstance(leaf.signature_hash_algorithm, hashes.SHA384),
                'EE cert honors digest=sha384',
            )
            leaf_nb = leaf.not_valid_before_utc.replace(tzinfo=None)
            check(
                leaf_nb < utc_now() - timedelta(minutes=5),
                'EE notBefore backdated for clock skew',
            )
    finally:
        try:
            os.unlink(temp_db)
        except OSError:
            pass

    print(f'\n== Result: {failures} failure(s) ==')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
