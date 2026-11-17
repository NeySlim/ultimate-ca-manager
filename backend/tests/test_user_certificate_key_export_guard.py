"""Exporting somebody else's private key needs the scope that says so.

Three routes export a private key and each asked a different question. The
certificate route gates a key behind `read:private_keys`, and says why in a
comment: without it, the approval-gated Key Recovery flow is pointless,
because anyone who could request a recovery could export the key instead and
skip the approval.

The user-certificate route asked nothing at all, and `include_key` defaults
to true there. The built-in Operator role holds `read:user_certificates` and
not `read:private_keys`, and the access check lets an operator reach any
user's enrolment, so one request returned any user's key in PKCS#12.

What has to keep working is the other half: a person downloading their own
certificate, from their own account page, has always been able to take their
own key with it.
"""
import base64
import json

import pytest

from models import db


@pytest.fixture
def an_operator(app, create_user):
    create_user(username='op_key_export_probe', role='operator')
    client = app.test_client()
    answer = client.post(
        '/api/v2/auth/login',
        data=json.dumps({'username': 'op_key_export_probe',
                         'password': 'TestPass123!'}),
        content_type='application/json')
    assert answer.status_code == 200, answer.data
    return client


def _enrolment_for(app, create_cert, username, label):
    """An enrolment row belonging to `username`, bound to a real certificate."""
    from models import User, Certificate
    from models.auth_certificate import AuthCertificate

    cert = create_cert(cn=f'{label}.example')
    with app.app_context():
        owner = User.query.filter_by(username=username).first()
        issued = db.session.get(Certificate, cert['id'])
        row = AuthCertificate(
            user_id=owner.id,
            cert_serial=issued.serial_number,
            cert_subject=issued.subject or f'CN={label}.example',
            cert_issuer=issued.issuer,
            cert_fingerprint='',
            name=label,
            enabled=True)
        db.session.add(row)
        db.session.commit()
        return row.id, owner.id


@pytest.fixture
def somebody_elses_certificate(app, create_user, create_cert):
    create_user(username='owner_key_export_probe', role='viewer')
    return _enrolment_for(app, create_cert, 'owner_key_export_probe',
                          'key-export-probe')


class TestAnOperatorCannotTakeSomebodyElsesKey:
    def test_pkcs12_is_refused_without_the_private_key_scope(
            self, an_operator, somebody_elses_certificate):
        cert_id, _owner = somebody_elses_certificate
        answer = an_operator.post(
            f'/api/v2/user-certificates/{cert_id}/export',
            data=json.dumps({'format': 'pkcs12', 'password': 'Passw0rd!2026'}),
            content_type='application/json')
        assert answer.status_code == 403, (
            'an operator exported another user\'s private key, which is the '
            'approval flow bypassed: '
            f'{answer.status_code} {answer.data[:120]}')

    def test_the_default_export_does_not_quietly_include_the_key(
            self, an_operator, somebody_elses_certificate):
        """`include_key` defaults to true on this route, so a plain export
        carried the key without anyone asking for it."""
        cert_id, _owner = somebody_elses_certificate
        answer = an_operator.post(
            f'/api/v2/user-certificates/{cert_id}/export',
            data=json.dumps({'format': 'pem'}),
            content_type='application/json')
        if answer.status_code == 200:
            body = answer.data.decode('utf-8', 'replace')
            assert 'PRIVATE KEY' not in body, (
                'a plain export handed over the private key')


class TestTheOwnerKeepsTheirOwnKey:
    def test_a_person_can_still_take_their_own(
            self, app, create_user, create_cert):
        create_user(username='self_key_export_probe', role='viewer')
        row_id, _owner = _enrolment_for(
            app, create_cert, 'self_key_export_probe',
            'self-key-export-probe')

        client = app.test_client()
        signed_in = client.post(
            '/api/v2/auth/login',
            data=json.dumps({'username': 'self_key_export_probe',
                             'password': 'TestPass123!'}),
            content_type='application/json')
        assert signed_in.status_code == 200, signed_in.data

        answer = client.post(
            f'/api/v2/user-certificates/{row_id}/export',
            data=json.dumps({'format': 'pkcs12', 'password': 'Passw0rd!2026'}),
            content_type='application/json')
        assert answer.status_code == 200, (
            'a person can no longer take their own key from their own '
            f'account: {answer.status_code} {answer.data[:150]}')
