"""One ceiling, one idea of a day count (DUP-PKI-003).

``3650`` was spelled out eleven times across the issuance paths. The number
never diverged; the rule around it did. ``{"validity_days": true}`` was a 400
at the mTLS enrolment door — the one place that had thought about booleans —
and a certificate valid until tomorrow at ``POST /api/v2/certificates``,
because ``int(True)`` is ``1``.
"""
import pathlib
import uuid

import pytest

from utils.validity import (MAX_VALIDITY_DAYS, MIN_VALIDITY_DAYS,
                            coerce_validity_days, validity_days_in_range)

# Modules that cap certificate validity. None of them may spell the number.
VALIDITY_MODULES = [
    'api/v2/certificates/cert_create.py',
    'api/v2/csrs.py',
    'api/v2/est.py',
    'api/v2/windows_profiles.py',
    'api/v2/templates.py',
    'api/v2/policies.py',
    'api/v2/mtls.py',
    'api/v2/users/mtls.py',
    'services/tsa_signer_cert.py',
    'services/acme/profiles.py',
    'services/cert/renewal.py',
    'services/mtls_enrollment.py',
]


def test_the_ceiling_is_where_it_has_always_been():
    assert (MIN_VALIDITY_DAYS, MAX_VALIDITY_DAYS) == (1, 3650)


@pytest.mark.parametrize('value,expected', [
    (30, 30),
    (30.0, 30),
    ('30', 30),
    ('  30  ', 30),
    ('-5', -5),        # out of range, reported by the caller, as before
    (-5, -5),
    (0, 0),
    (3650, 3650),
    (5000, 5000),
    (True, None),      # the divergence: int(True) == 1 used to mean one day
    (False, None),
    (30.5, None),
    ('thirty', None),
    ('', None),
    (None, None),
    ([30], None),
])
def test_what_counts_as_a_day_count(value, expected):
    assert coerce_validity_days(value) == expected


def test_range_check_is_separate_from_shape():
    assert validity_days_in_range(1) and validity_days_in_range(3650)
    assert not validity_days_in_range(0) and not validity_days_in_range(3651)


@pytest.mark.parametrize('module', VALIDITY_MODULES)
def test_no_issuance_path_spells_the_ceiling_itself(module):
    root = pathlib.Path(__file__).resolve().parent.parent
    source = (root / module).read_text(encoding='utf-8')
    offenders = [
        f'{module}:{n}: {line.strip()[:80]}'
        for n, line in enumerate(source.splitlines(), 1)
        if '3650' in line
    ]
    assert offenders == [], 'import it from utils.validity: ' + '; '.join(offenders)


def test_a_boolean_is_refused_at_the_certificate_door(auth_client, create_ca):
    ca = create_ca(cn=f'Validity CA {uuid.uuid4().hex[:6]}')
    response = auth_client.post('/api/v2/certificates', json={
        'cn': 'bool.example.com', 'ca_id': ca['id'],
        'cert_type': 'server', 'validity_days': True,
    })
    assert response.status_code == 400
    assert response.get_json()['message'] == 'validity_days must be an integer (1..3650)'


def test_a_boolean_is_refused_at_the_csr_signing_door(auth_client, create_ca):
    ca = create_ca(cn=f'Validity CA sign {uuid.uuid4().hex[:6]}')
    created = auth_client.post('/api/v2/csrs', json={'cn': 'boolsign.example.com'})
    assert created.status_code == 201
    csr_id = created.get_json()['data']['id']

    response = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={
        'ca_id': ca['id'], 'validity_days': True,
    })
    assert response.status_code == 400
    assert response.get_json()['message'] == 'validity_days must be an integer'


def test_a_boolean_is_refused_at_the_mtls_door():
    """The door that was already right; it must stay right."""
    from services.mtls_enrollment import parse_validity_days

    assert parse_validity_days(True) is None
    assert parse_validity_days(30) == 30
    assert parse_validity_days(None) == 365


@pytest.mark.parametrize('value,expected_message', [
    (5000, 'validity_days must be between 1 and 3650'),
    (0, 'validity_days must be between 1 and 3650'),
    ('thirty', 'validity_days must be an integer (1..3650)'),
])
def test_the_certificate_doors_wording_is_unchanged(
    auth_client, create_ca, value, expected_message
):
    ca = create_ca(cn=f'Validity CA msg {uuid.uuid4().hex[:6]}')
    response = auth_client.post('/api/v2/certificates', json={
        'cn': 'range.example.com', 'ca_id': ca['id'],
        'cert_type': 'server', 'validity_days': value,
    })
    assert response.status_code == 400
    assert response.get_json()['message'] == expected_message
