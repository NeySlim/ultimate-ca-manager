"""The compliance views are four shapes of one score, not four scores.

Flagged as a duplication to reconcile: the list view carries flat
``compliance_score``/``compliance_grade`` while the detail view carries a
nested ``compliance``. They are not two implementations -- both call
``calculate_compliance_score`` and agree on the number -- and the frontend
reads both shapes, each where it is: the table columns sort on the flat pair,
the detail panel renders the nested breakdown. Renaming either key breaks a
consumer for no gain, so this pins the shapes instead.
"""

import json

import pytest

from services.compliance_service import calculate_compliance_score

CERTIFICATES = '/api/v2/certificates'


@pytest.fixture(scope='module')
def scored_certificate(auth_client, create_ca):
    ca = create_ca(cn='Compliance Views CA')
    ca_id = ca.get('id', ca.get('ca_id'))
    created = auth_client.post(CERTIFICATES, data=json.dumps({
        'cn': 'compliance-views.example.com', 'ca_id': ca_id,
        'validity_days': 90, 'key_type': 'rsa', 'key_size': '2048',
    }), content_type='application/json')
    assert created.status_code == 201
    return created.get_json()['data']['id']


def _detail(auth_client, cert_id):
    r = auth_client.get(f'{CERTIFICATES}/{cert_id}')
    assert r.status_code == 200
    return r.get_json()['data']


def _row(auth_client, cert_id):
    r = auth_client.get(f'{CERTIFICATES}?search=compliance-views&per_page=100')
    assert r.status_code == 200
    rows = r.get_json()['data']
    return next(row for row in rows if row['id'] == cert_id)


def test_the_two_views_report_the_same_score(auth_client, scored_certificate):
    detail = _detail(auth_client, scored_certificate)
    row = _row(auth_client, scored_certificate)

    assert detail['compliance']['score'] == row['compliance_score']
    assert detail['compliance']['grade'] == row['compliance_grade']


def test_the_list_view_keeps_the_flat_pair(auth_client, scored_certificate):
    """The certificates table sorts and renders on these two keys."""
    row = _row(auth_client, scored_certificate)

    assert 'compliance_score' in row
    assert 'compliance_grade' in row
    assert 'compliance' not in row


def test_the_detail_view_keeps_the_nested_object(auth_client, scored_certificate):
    """The detail panel renders grade, score and the per-category breakdown."""
    detail = _detail(auth_client, scored_certificate)

    assert set(detail['compliance']) == {'score', 'grade', 'breakdown'}
    assert 'compliance_score' not in detail
    assert 'compliance_grade' not in detail


def test_the_list_view_omits_the_breakdown(auth_client, scored_certificate):
    """Why the shapes differ: a row carries no per-category detail."""
    row = _row(auth_client, scored_certificate)

    assert not any('breakdown' in key for key in row)


def test_the_score_does_not_depend_on_the_detail_only_fields(auth_client,
                                                             scored_certificate):
    """Detail scores after adding extensions/chain_status; neither is read."""
    detail = _detail(auth_client, scored_certificate)
    stripped = {k: v for k, v in detail.items()
                if k not in ('extensions', 'chain_status', 'ct_scts',
                             'compliance')}

    assert calculate_compliance_score(stripped)['score'] == \
        detail['compliance']['score']


def test_the_aggregate_view_reports_the_same_grades(auth_client,
                                                    scored_certificate):
    """The stats view is the third shape: a distribution, no per-cert key."""
    r = auth_client.get(f'{CERTIFICATES}/compliance')
    assert r.status_code == 200
    data = r.get_json()['data']

    assert set(data) >= {'average_score', 'distribution', 'total'}
    assert _row(auth_client, scored_certificate)['compliance_grade'] in \
        data['distribution']
