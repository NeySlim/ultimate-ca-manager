"""The revocation reasons, checked against the standard and not just against
each other.

Four copies of this list existed. Two agreed, and neither of those was
checked against anything: `utils/revocation_reasons.REVOCATION_REASONS` and
the `REVOCATION_REASONS` array in
`frontend/src/components/RevokeCertificateModal.jsx`, byte for byte the same
and nothing holding them there. The third, `docs/openapi.yaml`, had six
names, spelled `cACompromise` as `caCompromise`, and was missing
`certificateHold`, `privilegeWithdrawn` and `aACompromise` -- so a client
generated from it could not place a certificate on hold. (That file is gone;
see tests/test_one_api_description.py.)

The list has an author, and it is not this repository. RFC 5280 §5.3.1
enumerates CRLReason, and that is what the first test below checks against.
Picking the longest copy, or the majority one, would have been a coin toss
that happened to land right.
"""
import json
import os
import re

import pytest

from cryptography import x509

from utils.revocation_reasons import (REASON_FLAGS, REVOCATION_REASONS,
                                      normalize_revocation_reason)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODAL = os.path.join(_REPO, 'frontend', 'src', 'components',
                     'RevokeCertificateModal.jsx')

# RFC 5280 §5.3.1, CRLReason ::= ENUMERATED { ... }. Value 7 is not used.
RFC_5280_CRL_REASONS = {
    'unspecified': 0,
    'keyCompromise': 1,
    'cACompromise': 2,
    'affiliationChanged': 3,
    'superseded': 4,
    'cessationOfOperation': 5,
    'certificateHold': 6,
    'removeFromCRL': 8,
    'privilegeWithdrawn': 9,
    'aACompromise': 10,
}


class TestTheListIsTheStandardsList:
    def test_every_name_is_an_rfc_5280_reason(self):
        unknown = [name for name in REVOCATION_REASONS
                   if name not in RFC_5280_CRL_REASONS]
        assert unknown == [], (
            f'{unknown} are not CRLReason values; RFC 5280 §5.3.1 defines '
            f'{sorted(RFC_5280_CRL_REASONS)}')

    def test_the_spelling_is_the_standards_spelling(self):
        """`cACompromise` and `aACompromise` are odd-looking and are what the
        ASN.1 module says. The API description had `caCompromise`."""
        assert 'cACompromise' in REVOCATION_REASONS
        assert 'aACompromise' in REVOCATION_REASONS
        assert 'caCompromise' not in REVOCATION_REASONS

    def test_only_remove_from_crl_is_left_out_and_on_purpose(self):
        missing = set(RFC_5280_CRL_REASONS) - set(REVOCATION_REASONS)
        assert missing == {'removeFromCRL'}, (
            f'{missing} are RFC 5280 reasons the revocation API will not '
            'accept; only removeFromCRL has a reason to be absent, being '
            'the unhold path rather than a revocation')

    def test_the_absent_one_is_still_understood_where_it_is_written(self):
        assert 'removeFromCRL' in REASON_FLAGS

    def test_each_name_maps_to_the_matching_library_flag(self):
        for name in REVOCATION_REASONS:
            flag = REASON_FLAGS[name]
            assert isinstance(flag, x509.ReasonFlags), name
        # The one that drifted between the CRL builder and the OCSP
        # responder before the table was shared.
        assert REASON_FLAGS['cACompromise'] is x509.ReasonFlags.ca_compromise


class TestTheBrowserHasTheSameList:
    def _browser_list(self):
        assert os.path.exists(MODAL), MODAL
        source = open(MODAL, encoding='utf-8').read()
        match = re.search(
            r'export const REVOCATION_REASONS\s*=\s*\[(.*?)\]',
            source, re.S)
        assert match, 'no REVOCATION_REASONS array in the revoke dialog'
        return re.findall(r"'([^']+)'", match.group(1))

    def test_same_names_in_the_same_order(self):
        assert self._browser_list() == list(REVOCATION_REASONS), (
            'the revoke dialog offers a different set of reasons from the '
            'one the revoke routes accept')

    def test_the_browser_offers_nothing_the_server_refuses(self):
        for name in self._browser_list():
            assert normalize_revocation_reason(name) == name, (
                f'the dialog offers {name!r} and the server does not take it')


class TestTheListIsPublished:
    def test_the_endpoint_answers_with_it(self, auth_client):
        r = auth_client.get('/api/v2/revocation-reasons')
        assert r.status_code == 200, r.data
        reasons = ((r.get_json() or {}).get('data') or {}).get('reasons')
        assert reasons == list(REVOCATION_REASONS)

    def test_everything_it_publishes_is_accepted(self, auth_client, create_cert):
        reasons = ((auth_client.get('/api/v2/revocation-reasons').get_json()
                    or {}).get('data') or {}).get('reasons') or []
        assert reasons
        for reason in reasons:
            cert = create_cert(cn=f'revreason-{reason.lower()}.example.com')
            r = auth_client.post(
                f'/api/v2/certificates/{cert["id"]}/revoke',
                data=json.dumps({'reason': reason}),
                content_type='application/json')
            assert r.status_code in (200, 201), (
                f'{reason} is published and was refused: {r.data[:160]}')

    def test_a_reason_it_does_not_publish_is_refused(
            self, auth_client, create_cert):
        cert = create_cert(cn='revreason-unpublished.example.com')
        r = auth_client.post(
            f'/api/v2/certificates/{cert["id"]}/revoke',
            data=json.dumps({'reason': 'removeFromCRL'}),
            content_type='application/json')
        assert r.status_code == 400, (
            'removeFromCRL is the unhold path, not a revocation reason')
