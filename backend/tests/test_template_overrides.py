"""Tests for issue #258 — template override tracking at issuance.

When a certificate is issued from a template whose inherited defaults
(key type, validity, digest) were explicitly overridden, the divergence is
recorded on the issued row (Certificate.template_overrides, JSON list) and
surfaced by the API. Inherited-as-default values must NOT be flagged; only
explicit divergences are.
"""
import json

import pytest

from services.template_service import (
    compute_template_overrides,
    _normalize_key_type_label,
)
from tests.conftest import get_json

CONTENT_JSON = 'application/json'

TEMPLATE_2048 = {
    'name': 'override-track-tpl',
    'template_type': 'custom',
    'key_type': 'RSA-2048',
    'validity_days': 90,
    'digest': 'sha384',
    'extensions_template': json.dumps({
        'key_usage': ['digitalSignature', 'keyEncipherment'],
        'extended_key_usage': ['serverAuth'],
    }),
}


def _create_template(auth_client, **overrides):
    data = {**TEMPLATE_2048}
    data.update(overrides)
    r = auth_client.post('/api/v2/templates',
                         data=json.dumps(data), content_type=CONTENT_JSON)
    assert r.status_code in (200, 201), r.data
    body = get_json(r)
    return body.get('data', body)


def _issue_cert(auth_client, ca_id, cn, **extra):
    payload = {'cn': cn, 'ca_id': ca_id}
    payload.update(extra)
    r = auth_client.post('/api/v2/certificates',
                         data=json.dumps(payload), content_type=CONTENT_JSON)
    assert r.status_code in (200, 201), r.data
    return get_json(r)['data']


class TestNormalizeKeyTypeLabel:
    def test_template_format_passthrough(self):
        assert _normalize_key_type_label('RSA-2048') == 'RSA-2048'
        assert _normalize_key_type_label('ec-p384') == 'EC-P384'

    def test_bare_size(self):
        assert _normalize_key_type_label('4096') == 'RSA-4096'
        assert _normalize_key_type_label(2048) == 'RSA-2048'

    def test_curve_names(self):
        assert _normalize_key_type_label('prime256v1') == 'EC-P256'
        assert _normalize_key_type_label('secp384r1') == 'EC-P384'

    def test_unknown_or_empty(self):
        assert _normalize_key_type_label('ed25519') is None
        assert _normalize_key_type_label('') is None
        assert _normalize_key_type_label(None) is None


class TestComputeTemplateOverrides:
    class _T:
        key_type = 'RSA-2048'
        validity_days = 90
        digest = 'sha384'

    def test_all_matching_returns_none(self):
        assert compute_template_overrides(
            self._T(), key_type='2048', validity_days=90, digest='sha384'
        ) is None

    def test_each_field_flagged(self):
        out = json.loads(compute_template_overrides(
            self._T(), key_type='EC-P256', validity_days=30, digest='sha256'
        ))
        assert out == ['key_type', 'validity_days', 'digest']

    def test_unprovided_fields_not_compared(self):
        assert compute_template_overrides(self._T(), validity_days=30) == json.dumps(['validity_days'])

    def test_no_template_returns_none(self):
        assert compute_template_overrides(None, key_type='2048') is None


class TestIssueFromTemplateOverrideTracking:
    def test_inherited_values_not_flagged(self, app, auth_client, create_ca):
        """Request omits key_type/validity → template defaults apply, no flag."""
        ca = create_ca(cn='OvTrack Inherit CA')
        tpl = _create_template(auth_client, name='ovt-inherit')

        issued = _issue_cert(auth_client, ca['id'], 'ovt-inherit.test',
                             template_id=tpl['id'])

        assert issued['template_id'] == tpl['id']
        assert issued['template_name'] == tpl['name']
        assert issued['template_overrides'] == []

    def test_explicit_same_values_not_flagged(self, app, auth_client, create_ca):
        """Explicit values identical to the template are not a divergence."""
        ca = create_ca(cn='OvTrack Match CA')
        tpl = _create_template(auth_client, name='ovt-match')

        issued = _issue_cert(auth_client, ca['id'], 'ovt-match.test',
                             template_id=tpl['id'],
                             key_type='rsa', key_size=2048, validity_days=90)

        assert issued['template_overrides'] == []

    def test_validity_override_flagged(self, app, auth_client, create_ca):
        ca = create_ca(cn='OvTrack Validity CA')
        tpl = _create_template(auth_client, name='ovt-validity')

        issued = _issue_cert(auth_client, ca['id'], 'ovt-validity.test',
                             template_id=tpl['id'],
                             key_type='rsa', key_size=2048, validity_days=30)

        assert issued['template_overrides'] == ['validity_days']

    def test_key_type_override_flagged(self, app, auth_client, create_ca):
        ca = create_ca(cn='OvTrack Key CA')
        tpl = _create_template(auth_client, name='ovt-key')

        issued = _issue_cert(auth_client, ca['id'], 'ovt-key.test',
                             template_id=tpl['id'],
                             key_type='rsa', key_size=4096, validity_days=90)

        assert issued['template_overrides'] == ['key_type']

    def test_ec_curve_override_flagged(self, app, auth_client, create_ca):
        ca = create_ca(cn='OvTrack EC CA')
        tpl = _create_template(auth_client, name='ovt-ec')

        issued = _issue_cert(auth_client, ca['id'], 'ovt-ec.test',
                             template_id=tpl['id'],
                             key_type='ec', curve='secp384r1', validity_days=90)

        assert issued['template_overrides'] == ['key_type']

    def test_no_template_no_flag(self, app, auth_client, create_ca):
        ca = create_ca(cn='OvTrack Free CA')
        issued = _issue_cert(auth_client, ca['id'], 'ovt-free.test',
                             key_type='rsa', key_size=2048, validity_days=90)
        assert issued['template_id'] is None
        assert issued['template_overrides'] == []

    def test_template_modified_list_filter(self, app, auth_client, create_ca):
        ca = create_ca(cn='OvTrack Filter CA')
        tpl = _create_template(auth_client, name='ovt-filter')
        # one divergent, one clean
        _issue_cert(auth_client, ca['id'], 'ovt-f-diverged.test',
                    template_id=tpl['id'], key_type='rsa', key_size=4096, validity_days=90)
        _issue_cert(auth_client, ca['id'], 'ovt-f-clean.test',
                    template_id=tpl['id'],
                    key_type='rsa', key_size=2048, validity_days=90)

        r = auth_client.get('/api/v2/certificates?template_modified=true&per_page=100')
        assert r.status_code == 200
        data = get_json(r)['data']
        items = data.get('items', data) if isinstance(data, dict) else data
        filtered_cns = {c['cn'] for c in items}
        assert 'ovt-f-diverged.test' in filtered_cns
        assert 'ovt-f-clean.test' not in filtered_cns
