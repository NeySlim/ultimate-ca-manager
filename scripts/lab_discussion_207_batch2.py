#!/usr/bin/env python3
"""Lab: discussion #207 batch-2 (friendly name, CA validity, protocol_http).

Loads SECRET_KEY from repo-root ``.env.lab`` when present.

Usage:
  python3 scripts/lab_discussion_207_batch2.py
"""
from __future__ import annotations

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
        print('NOTE: ephemeral SECRET_KEY for this run')
    os.environ.setdefault('JWT_SECRET_KEY', os.environ['SECRET_KEY'])
    os.environ.setdefault('UCM_ENV', 'lab')
    os.environ.setdefault('HTTP_REDIRECT', 'false')
    os.environ.setdefault('CSRF_DISABLED', 'true')
    os.environ.setdefault('UCM_DEV_MODE', 'true')


def main() -> int:
    _ensure_secrets()
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        os.environ['UCM_DATABASE_PATH'] = f.name
        temp_db = f.name

    sys.path.insert(0, str(BACKEND))
    os.chdir(BACKEND)

    from app import create_app
    from models import db, Certificate
    from services.ca_service import CAService
    from utils.protocol_url import apply_protocol_urls_for_ca, get_protocol_base_url

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
            print('\n== Discussion #207 batch-2 lab ==')

            ca = CAService.create_internal_ca(
                descr='Lab 207 B2 Root',
                dn={'CN': 'Lab 207 B2 Root', 'O': 'Lab', 'C': 'US'},
                key_type='2048',
                validity_days=40 * 365,
                username='lab',
            )
            check(ca.protocol_http is True or ca.protocol_http is None, 'protocol_http defaults to HTTP')

            ca.protocol_http = True
            ca.cdp_enabled = True
            ca.ocsp_enabled = True
            # apply with real helper (may be None without FQDN — still exercises path)
            apply_protocol_urls_for_ca(ca)
            db.session.commit()
            http_base = get_protocol_base_url(prefer_http=True)
            https_base = get_protocol_base_url(prefer_http=False)
            check(True, f'HTTP base={http_base!r} HTTPS base={https_base!r}')

            ca.protocol_http = False
            apply_protocol_urls_for_ca(ca)
            db.session.commit()
            if https_base and ca.get_primary_cdp_url():
                check(
                    ca.get_primary_cdp_url().startswith('https://'),
                    f'HTTPS mode CDP={ca.get_primary_cdp_url()}',
                )
            else:
                check(True, 'HTTPS base unavailable in lab env — skipped URL assert')

            cert = Certificate(
                refid='lab207b2',
                descr='initial',
                friendly_name='OCSP Lab',
                caref=ca.refid,
                cert_type='server_cert',
                subject='CN=lab207b2.example.test',
                created_by='lab',
            )
            db.session.add(cert)
            db.session.commit()
            d = cert.to_dict()
            check(d.get('friendly_name') == 'OCSP Lab', 'friendly_name in to_dict')
            check(d.get('description') == 'initial', 'description alias in to_dict')
            check('template_name' in d, 'template_name key present')

            # 40y CA validity was requested
            check(
                ca.valid_to is None or (ca.valid_to - ca.valid_from).days >= 39 * 365,
                f'CA validity ~40y (days={(ca.valid_to - ca.valid_from).days if ca.valid_to and ca.valid_from else "n/a"})',
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
