"""Revocation reasons on the revoke APIs (issue #334).

The web UI never sent a reason and the API stored whatever it received, so
manual revocations were recorded as ``unspecified`` and an unknown string
would have been stored verbatim. The routes now normalise the RFC 5280
reason names (canonical camelCase, snake_case and legacy spellings accepted)
and reject anything else with 400.
"""
import json

import pytest
from cryptography import x509

from services.crl._constants import REASON_MAP
from tests.conftest import get_json
from utils.revocation_reasons import (
    REVOCATION_REASONS, invalid_reason_message, normalize_revocation_reason,
)

BASE = '/api/v2/certificates'


class TestNormalize:

    @pytest.mark.parametrize('value,expected', [
        (None, 'unspecified'), ('', 'unspecified'), ('  ', 'unspecified'),
        ('keyCompromise', 'keyCompromise'), ('KEYCOMPROMISE', 'keyCompromise'),
        ('key_compromise', 'keyCompromise'), ('cACompromise', 'cACompromise'),
        ('CACompromise', 'cACompromise'), ('caCompromise', 'cACompromise'),
        ('ca_compromise', 'cACompromise'), ('certificate_hold', 'certificateHold'),
        ('aa_compromise', 'aACompromise'), ('Superseded', 'superseded'),
    ])
    def test_known_spellings(self, value, expected):
        assert normalize_revocation_reason(value) == expected

    @pytest.mark.parametrize('value', ['bogus', 'removeFromCRL', 42, ['keyCompromise'], {'r': 1}])
    def test_unknown_values(self, value):
        assert normalize_revocation_reason(value) is None

    def test_every_canonical_name_maps_on_the_crl(self):
        for name in REVOCATION_REASONS:
            assert name in REASON_MAP, name

    def test_crl_map_knows_the_acme_spelling(self):
        assert REASON_MAP['cACompromise'] is x509.ReasonFlags.ca_compromise
        assert REASON_MAP['certificate_hold'] is x509.ReasonFlags.certificate_hold

    def test_message_lists_accepted_values(self):
        msg = invalid_reason_message('bogus')
        assert "'bogus'" in msg and 'keyCompromise' in msg and 'certificateHold' in msg


class TestRevokeApi:

    def _cert_reason(self, auth_client, cert_id):
        r = auth_client.get(f'{BASE}/{cert_id}')
        body = get_json(r)
        data = body.get('data', body)
        return data.get('revoked'), data.get('revoke_reason')

    def test_reason_is_stored_canonically(self, auth_client, create_cert):
        cert = create_cert(cn='revoke-reason.example.com')
        r = auth_client.post(f'{BASE}/{cert["id"]}/revoke', json={'reason': 'key_compromise'})
        assert r.status_code == 200, r.data
        assert self._cert_reason(auth_client, cert['id']) == (True, 'keyCompromise')

    @pytest.mark.parametrize('reason', REVOCATION_REASONS)
    def test_every_rfc_reason_is_accepted(self, auth_client, create_cert, reason):
        cert = create_cert(cn=f'revoke-{reason.lower()}.example.com')
        r = auth_client.post(f'{BASE}/{cert["id"]}/revoke', json={'reason': reason})
        assert r.status_code == 200, r.data
        assert self._cert_reason(auth_client, cert['id']) == (True, reason)

    def test_missing_reason_defaults_to_unspecified(self, auth_client, create_cert):
        cert = create_cert(cn='revoke-default.example.com')
        r = auth_client.post(f'{BASE}/{cert["id"]}/revoke', json={})
        assert r.status_code == 200, r.data
        assert self._cert_reason(auth_client, cert['id']) == (True, 'unspecified')

    def test_unknown_reason_is_refused_and_nothing_revoked(self, auth_client, create_cert):
        cert = create_cert(cn='revoke-bogus.example.com')
        r = auth_client.post(f'{BASE}/{cert["id"]}/revoke', json={'reason': 'bogus'})
        assert r.status_code == 400, r.data
        assert 'bogus' in r.get_data(as_text=True)
        assert self._cert_reason(auth_client, cert['id'])[0] is not True

    def test_remove_from_crl_is_not_a_revocation_reason(self, auth_client, create_cert):
        cert = create_cert(cn='revoke-rfc.example.com')
        r = auth_client.post(f'{BASE}/{cert["id"]}/revoke', json={'reason': 'removeFromCRL'})
        assert r.status_code == 400, r.data

    def test_bulk_revoke_validates_the_reason(self, auth_client, create_cert):
        a = create_cert(cn='bulk-a.example.com')
        b = create_cert(cn='bulk-b.example.com')
        r = auth_client.post(f'{BASE}/bulk/revoke', json={'ids': [a['id'], b['id']], 'reason': 'nope'})
        assert r.status_code == 400, r.data
        assert self._cert_reason(auth_client, a['id'])[0] is not True
        r = auth_client.post(f'{BASE}/bulk/revoke', json={'ids': [a['id'], b['id']], 'reason': 'cessation_of_operation'})
        assert r.status_code == 200, r.data
        assert self._cert_reason(auth_client, a['id']) == (True, 'cessationOfOperation')
        assert self._cert_reason(auth_client, b['id']) == (True, 'cessationOfOperation')
