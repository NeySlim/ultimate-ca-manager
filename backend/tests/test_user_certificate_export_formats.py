"""The user-certificate export serves every format its dialog offers.

DER, P7B and the bare private key used to come back as PEM under the wrong
name; an unknown format fell through to PEM as well.
"""
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs7

from models import AuditLog
from tests.test_user_certificate_key_export_guard import (
    _enrolment_for, an_operator, somebody_elses_certificate)  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates', 'drop_new_users')


@pytest.fixture
def row_id(app, auth_client, create_user, create_cert):
    create_user(username='uexp_formats_owner', role='viewer')
    rid, _owner = _enrolment_for(app, create_cert, 'uexp_formats_owner', 'uexp-formats')
    return rid


def _export(client, rid, **body):
    return client.post(f'/api/v2/user-certificates/{rid}/export', json=body)


def test_der_is_a_der_certificate(auth_client, row_id):
    r = _export(auth_client, row_id, format='der')
    assert r.status_code == 200, r.data
    assert r.headers['Content-Disposition'].rstrip('"').endswith('.der')
    assert x509.load_der_x509_certificate(r.data)


@pytest.mark.parametrize('fmt', ['pkcs7', 'p7b'])
def test_p7b_holds_certificates_and_no_key(auth_client, row_id, fmt):
    r = _export(auth_client, row_id, format=fmt)
    assert r.status_code == 200, r.data
    assert r.headers['Content-Disposition'].rstrip('"').endswith('.p7b')
    assert pkcs7.load_der_pkcs7_certificates(r.data)
    assert b'PRIVATE KEY' not in r.data


def test_key_is_the_key_alone(auth_client, row_id):
    r = _export(auth_client, row_id, format='key')
    assert r.status_code == 200, r.data
    assert r.headers['Content-Disposition'].rstrip('"').endswith('.key')
    assert b'BEGIN CERTIFICATE' not in r.data
    assert serialization.load_pem_private_key(r.data, None)


def test_key_with_a_password_is_encrypted(auth_client, row_id):
    r = _export(auth_client, row_id, format='key', password='Passw0rd!2026')
    assert r.status_code == 200, r.data
    assert b'ENCRYPTED PRIVATE KEY' in r.data
    assert serialization.load_pem_private_key(r.data, b'Passw0rd!2026')


def test_key_with_a_short_password_is_refused(auth_client, row_id):
    assert _export(auth_client, row_id, format='key', password='x').status_code == 400


def test_key_export_is_audited_as_a_key_export(app, auth_client, row_id):
    assert _export(auth_client, row_id, format='key').status_code == 200
    with app.app_context():
        entry = (AuditLog.query.filter_by(action='private_key_exported')
                 .order_by(AuditLog.id.desc()).first())
    assert entry is not None and 'KEY' in entry.details.upper()


def test_unknown_format_is_a_400(auth_client, row_id):
    r = _export(auth_client, row_id, format='bogus')
    assert r.status_code == 400
    assert 'bogus' in r.get_json()['message']


@pytest.mark.parametrize('fmt, option', [
    ('der', 'include_key'), ('der', 'include_chain'),
    ('pkcs7', 'include_key'), ('p7b', 'include_key'),
])
def test_impossible_option_is_refused(auth_client, row_id, fmt, option):
    r = _export(auth_client, row_id, format=fmt, **{option: True})
    assert r.status_code == 400
    assert option in r.get_json()['message']


def test_pem_is_unchanged(auth_client, row_id):
    r = _export(auth_client, row_id, format='pem')
    assert r.status_code == 200
    assert b'BEGIN CERTIFICATE' in r.data and b'PRIVATE KEY' in r.data


@pytest.mark.parametrize('fmt', ['der', 'key'])
def test_another_users_key_still_needs_the_scope(an_operator, somebody_elses_certificate, fmt):  # noqa: F811
    rid, _owner = somebody_elses_certificate
    r = an_operator.post(f'/api/v2/user-certificates/{rid}/export', json={'format': fmt})
    assert r.status_code == (403 if fmt == 'key' else 200), r.data
