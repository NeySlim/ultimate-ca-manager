"""DNS provider credentials are encrypted at rest (GHSA-38cv-3c4g-w55w).

The credentials column stores domain-control API keys; it must never be
persisted as plaintext, while staying transparently readable (including legacy
plaintext rows written before the fix).
"""

from __future__ import annotations

import json
import uuid

from models import db
from models.acme_models import DnsProvider


def _make(app, creds):
    with app.app_context():
        dp = DnsProvider(name=f'cf-{uuid.uuid4().hex[:8]}', provider_type='cloudflare')
        dp.credentials = json.dumps(creds)
        db.session.add(dp)
        db.session.commit()
        pid = dp.id
    return pid


class TestCredentialEncryption:
    def test_roundtrip_returns_plaintext(self, app):
        creds = {'api_token': 'super-secret-token'}
        pid = _make(app, creds)
        with app.app_context():
            dp = db.session.get(DnsProvider, pid)
            assert json.loads(dp.credentials) == creds

    def test_stored_column_is_not_plaintext(self, app):
        secret = 'cf-token-do-not-store-plain'
        pid = _make(app, {'api_token': secret})
        with app.app_context():
            dp = db.session.get(DnsProvider, pid)
            raw = dp._credentials  # the actual DB column value
            assert secret not in raw
            assert raw.startswith('gAAAAA')  # Fernet token

    def test_legacy_plaintext_row_reads_transparently(self, app):
        # Simulate a pre-fix row: raw plaintext JSON written straight to the column
        creds = {'api_key': 'legacy-plain'}
        with app.app_context():
            dp = DnsProvider(name=f'legacy-{uuid.uuid4().hex[:8]}', provider_type='route53')
            dp._credentials = json.dumps(creds)  # bypass the encrypting setter
            db.session.add(dp)
            db.session.commit()
            pid = dp.id
        with app.app_context():
            dp = db.session.get(DnsProvider, pid)
            assert json.loads(dp.credentials) == creds

    def test_constructor_kwarg_encrypts(self, app):
        # The restore path builds DnsProvider(credentials=...) via kwargs; the
        # property setter MUST run so restore does not re-introduce plaintext.
        secret = 'ctor-kwarg-secret'
        with app.app_context():
            dp = DnsProvider(
                name=f'ctor-{uuid.uuid4().hex[:8]}', provider_type='cloudflare',
                credentials=json.dumps({'api_token': secret}),
            )
            db.session.add(dp)
            db.session.commit()
            pid = dp.id
        with app.app_context():
            dp = db.session.get(DnsProvider, pid)
            assert dp._credentials.startswith('gAAAAA')
            assert secret not in dp._credentials
            assert json.loads(dp.credentials)['api_token'] == secret

    def test_none_credentials(self, app):
        with app.app_context():
            dp = DnsProvider(name=f'empty-{uuid.uuid4().hex[:8]}', provider_type='manual')
            dp.credentials = None
            db.session.add(dp)
            db.session.commit()
            pid = dp.id
        with app.app_context():
            dp = db.session.get(DnsProvider, pid)
            assert dp.credentials is None

    def test_to_dict_exposes_only_key_names(self, app):
        pid = _make(app, {'api_token': 'secret', 'zone_id': 'z1'})
        with app.app_context():
            dp = db.session.get(DnsProvider, pid)
            d = dp.to_dict(include_credentials=True)
            assert set(d['credential_keys']) == {'api_token', 'zone_id'}
            assert 'secret' not in json.dumps(d)
