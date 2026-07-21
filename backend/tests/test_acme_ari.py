"""Tests for ACME Renewal Information (ARI) — RFC 9773."""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from models import db, Certificate
from models.acme_models import AcmeAccount, AcmeOrder
from services.acme import ari
from utils.serial_format import serial_to_int


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def _certid_for(cert: Certificate) -> str:
    aki_bytes = bytes.fromhex(cert.aki.replace(':', ''))
    n = serial_to_int(cert.serial_number)
    serial_bytes = n.to_bytes((n.bit_length() + 7) // 8 or 1, 'big')
    return f'{_b64url(aki_bytes)}.{_b64url(serial_bytes)}'


@pytest.fixture
def issued_cert(app, create_cert):
    info = create_cert(cn='ari-test.example.com', validity_days=90)
    cert_id = info.get('id') or info.get('certificate', {}).get('id')
    with app.app_context():
        cert = db.session.get(Certificate, cert_id) if cert_id else None
        if cert is None:
            cert = Certificate.query.filter(
                Certificate.crt.isnot(None)).order_by(Certificate.id.desc()).first()
        assert cert is not None and cert.aki, 'created cert has no AKI'
        return {
            'id': cert.id,
            'certid': _certid_for(cert),
            'aki': cert.aki,
            'serial_int': serial_to_int(cert.serial_number),
        }


class TestParseCertID:
    def test_roundtrip(self):
        aki = bytes.fromhex('a0c6f9a8883ee6d180b9b62d1a7918d722ca9bfa')
        serial = 0x305b6d7cbda085997bda3dba701b367f7eca2f2c
        sbytes = serial.to_bytes((serial.bit_length() + 7) // 8, 'big')
        certid = f'{_b64url(aki)}.{_b64url(sbytes)}'
        parsed = ari.parse_certid(certid)
        assert parsed is not None
        assert parsed[0] == aki.hex()
        assert parsed[1] == serial

    def test_rejects_no_dot(self):
        assert ari.parse_certid('abcdef') is None

    def test_rejects_two_dots(self):
        assert ari.parse_certid('a.b.c') is None

    def test_rejects_empty_part(self):
        assert ari.parse_certid('.abc') is None
        assert ari.parse_certid('abc.') is None


class TestSuggestedWindow:
    def _cert(self, lifetime_days, revoked=False):
        now = datetime(2026, 1, 1)
        c = Certificate(
            valid_from=now,
            valid_to=now + timedelta(days=lifetime_days),
            revoked=revoked,
        )
        return c

    def test_window_inside_validity(self):
        c = self._cert(90)
        start, end = ari.suggested_window(c, renew_before_days=30)
        assert c.valid_from < start < end <= c.valid_to

    def test_short_cert_not_renewed_immediately(self):
        # 6-day cert with a 30-day policy: clamp to 1/3 of lifetime.
        c = self._cert(6)
        start, end = ari.suggested_window(c, renew_before_days=30)
        # renewal point must be after at least 1/3 of the lifetime elapsed
        assert start > c.valid_from + timedelta(days=1)

    def test_revoked_window_in_past(self):
        c = self._cert(90, revoked=True)
        start, end = ari.suggested_window(c, renew_before_days=30)
        assert end <= datetime.utcnow() + timedelta(minutes=1)


class TestRenewalInfoEndpoint:
    def test_returns_window(self, client, issued_cert):
        r = client.get(f"/acme/renewalInfo/{issued_cert['certid']}")
        assert r.status_code == 200
        assert r.headers['Content-Type'].startswith('application/json')
        assert 'Retry-After' in r.headers
        body = json.loads(r.data)
        assert 'suggestedWindow' in body
        assert body['suggestedWindow']['start'].endswith('Z')
        assert body['suggestedWindow']['end'].endswith('Z')
        assert body['suggestedWindow']['start'] < body['suggestedWindow']['end']

    def test_unauthenticated(self, client, issued_cert):
        # No JWS, no auth header — must still succeed (RFC 9773 §4.1).
        r = client.get(f"/acme/renewalInfo/{issued_cert['certid']}")
        assert r.status_code == 200

    def test_replaced_certificate_gets_past_window(
        self, app, client, issued_cert
    ):
        with app.app_context():
            account = AcmeAccount(
                account_id='ari-replacement-account',
                jwk='{}',
                jwk_thumbprint='ari-replacement-thumbprint',
                status='valid',
            )
            db.session.add(account)
            db.session.flush()
            db.session.add(AcmeOrder(
                account_id=account.account_id,
                status='valid',
                identifiers=json.dumps([
                    {'type': 'dns', 'value': 'ari-test.example.com'}
                ]),
                replaces=issued_cert['certid'],
            ))
            db.session.commit()

        response = client.get(
            f"/acme/renewalInfo/{issued_cert['certid']}"
        )

        assert response.status_code == 200
        end = datetime.fromisoformat(
            response.get_json()['suggestedWindow']['end'].replace('Z', '+00:00')
        )
        assert end <= datetime.now(timezone.utc)

    def test_malformed_certid(self, client):
        r = client.get('/acme/renewalInfo/not-a-valid-certid')
        assert r.status_code == 400

    def test_unknown_certificate(self, client):
        aki = _b64url(bytes.fromhex('010203'))
        serial = _b64url(bytes.fromhex('9999'))
        fake = f'{aki}.{serial}'
        r = client.get(f'/acme/renewalInfo/{fake}')
        assert r.status_code == 404

    def test_directory_advertises_renewalinfo(self, client):
        r = client.get('/acme/directory')
        assert r.status_code == 200
        body = json.loads(r.data)
        assert 'renewalInfo' in body
        assert body['renewalInfo'].endswith('/acme/renewalInfo')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
