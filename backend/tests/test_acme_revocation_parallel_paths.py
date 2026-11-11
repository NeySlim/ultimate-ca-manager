"""Every path that revokes a certificate obtained over ACME tells the CA that issued it.

The certificate routes, the bulk route and the approvals sent the revocation to
the ACME CA; revoking an enrolled user certificate, removing an enrolment or its
user, a revokeCert at UCM's own ACME server and the related member of a pair
revoked it in UCM only. Each now goes through the same propagation and says the
same thing: revoked at the CA, owed, or local only.
"""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from models import db
from tests.test_acme_revocation_reaches_upstream import _answer, _owed, bench  # noqa: F401


def _enrol(app, bench, username):  # noqa: F811
    """An enrolment of ``username`` bound to the bench's ACME certificate."""
    from models import User
    from models.auth_certificate import AuthCertificate
    row = bench.row()
    owner = User.query.filter_by(username=username).first()
    enrolment = AuthCertificate(
        user_id=owner.id, cert_pem=bench.old_pem, cert_serial=row.serial_number,
        cert_subject=row.subject or f'CN={bench.name}', cert_issuer=row.issuer or '',
        cert_fingerprint='', name=bench.name, enabled=True)
    db.session.add(enrolment)
    db.session.commit()
    return enrolment.id


@pytest.fixture
def owner(create_user):
    name = f'acme_enrolled_{uuid.uuid4().hex[:6]}'
    return create_user(username=name, role='viewer'), name


def _drop_enrolment(enrolment_id):
    from models.auth_certificate import AuthCertificate
    row = db.session.get(AuthCertificate, enrolment_id)
    if row is not None:
        db.session.delete(row)
        db.session.commit()


class TestRevokingAUserCertificate:
    def _revoke(self, auth_client, enrolment_id, reason):
        answer = auth_client.post(f'/api/v2/user-certificates/{enrolment_id}/revoke',
                                  data=json.dumps({'reason': reason}),
                                  content_type='application/json')
        assert answer.status_code == 200, answer.data[:300]
        return json.loads(answer.data)

    def test_the_ca_is_told(self, app, auth_client, bench, owner):  # noqa: F811
        enrolment_id = _enrol(app, bench, owner[1])
        try:
            body = self._revoke(auth_client, enrolment_id, 'keyCompromise')
            sent = bench.client.revoke_certificate.call_args
            assert sent.args[0] == bench.old_pem and sent.kwargs == {'reason': 1}
            assert body['meta'] == {'acme_ca_revoked': True}
        finally:
            _drop_enrolment(enrolment_id)

    def test_a_ca_that_does_not_answer_is_owed_and_said(self, app, auth_client, bench, owner):  # noqa: F811
        bench.client.revoke_certificate = MagicMock(return_value=_answer(503))
        enrolment_id = _enrol(app, bench, owner[1])
        try:
            body = self._revoke(auth_client, enrolment_id, 'keyCompromise')
            assert body['meta']['acme_local_only'] is True
            assert body['meta']['acme_upstream_pending'] is True
            assert 'sent again automatically' in body['message']
            assert [e['serial'] for e in _owed(bench)] == [bench.old_serial]
        finally:
            _drop_enrolment(enrolment_id)

    def test_a_hold_is_never_sent(self, app, auth_client, bench, owner):  # noqa: F811
        enrolment_id = _enrol(app, bench, owner[1])
        try:
            body = self._revoke(auth_client, enrolment_id, 'certificateHold')
            bench.client.revoke_certificate.assert_not_called()
            assert 'hold' in body['message'] and _owed(bench) == []
        finally:
            _drop_enrolment(enrolment_id)


def _user_id(username):
    from models import User
    return User.query.filter_by(username=username).first().id


class TestRemovingAnEnrolment:
    """The enrolment's certificate is revoked for cessationOfOperation, then deleted."""

    @pytest.mark.parametrize('route', ['user-certificates', 'mtls', 'users'])
    def test_the_ca_is_told_whichever_route_removes_it(
            self, app, auth_client, bench, owner, route):  # noqa: F811
        enrolment_id = _enrol(app, bench, owner[1])
        url = {'user-certificates': f'/api/v2/user-certificates/{enrolment_id}',
               'mtls': f'/api/v2/mtls/certificates/{enrolment_id}',
               'users': f'/api/v2/users/{_user_id(owner[1])}/mtls/certificates/{enrolment_id}'}[route]
        try:
            answer = auth_client.delete(url)
            assert answer.status_code == 200, answer.data[:300]
            sent = bench.client.revoke_certificate.call_args
            assert sent.args[0] == bench.old_pem and sent.kwargs == {'reason': 5}
            assert json.loads(answer.data)['meta'] == {'acme_ca_revoked': True}
        finally:
            _drop_enrolment(enrolment_id)

    def test_a_ca_that_does_not_answer_keeps_it_owed_after_the_deletion(
            self, app, auth_client, bench, owner):  # noqa: F811
        bench.client.revoke_certificate = MagicMock(return_value=_answer(503))
        enrolment_id = _enrol(app, bench, owner[1])
        try:
            answer = auth_client.delete(f'/api/v2/user-certificates/{enrolment_id}')
            assert answer.status_code == 200, answer.data[:300]
            body = json.loads(answer.data)
            assert body['meta']['acme_upstream_pending'] is True
            assert 'sent again automatically' in body['message']
            assert bench.row() is None
            assert [e['serial'] for e in _owed(bench)] == [bench.old_serial]
        finally:
            _drop_enrolment(enrolment_id)

    def test_a_certificate_not_from_acme_still_answers_no_content(
            self, app, auth_client, bench, owner):  # noqa: F811
        from models import Certificate
        row = db.session.get(Certificate, bench.cert_id)
        row.source = 'import'
        db.session.commit()
        enrolment_id = _enrol(app, bench, owner[1])
        try:
            answer = auth_client.delete(f'/api/v2/user-certificates/{enrolment_id}')
            assert answer.status_code == 204, answer.data[:300]
            bench.client.revoke_certificate.assert_not_called()
        finally:
            _drop_enrolment(enrolment_id)


class TestDeletingAUser:
    def test_the_ca_is_told(self, app, auth_client, bench, owner):  # noqa: F811
        enrolment_id = _enrol(app, bench, owner[1])
        try:
            answer = auth_client.delete(f"/api/v2/users/{owner[0]['id']}")
            assert answer.status_code == 200, answer.data[:300]
            assert bench.client.revoke_certificate.call_args.kwargs == {'reason': 5}
            assert 'meta' not in json.loads(answer.data)
        finally:
            _drop_enrolment(enrolment_id)

    def test_a_ca_that_does_not_answer_is_said(self, app, auth_client, bench, owner):  # noqa: F811
        bench.client.revoke_certificate = MagicMock(return_value=_answer(503))
        enrolment_id = _enrol(app, bench, owner[1])
        try:
            answer = auth_client.delete(f"/api/v2/users/{owner[0]['id']}")
            assert answer.status_code == 200, answer.data[:300]
            body = json.loads(answer.data)
            assert body['meta'] == {'acme_local_only': [bench.cert_id],
                                    'acme_upstream_pending': [bench.cert_id]}
            assert f'#{bench.cert_id}' in body['message']
            assert 'sent again automatically' in body['message']
            assert [e['serial'] for e in _owed(bench)] == [bench.old_serial]
        finally:
            _drop_enrolment(enrolment_id)

    def test_the_bulk_deletion_lists_what_the_ca_was_not_told(
            self, app, auth_client, bench, owner):  # noqa: F811
        bench.client.revoke_certificate = MagicMock(return_value=_answer(503))
        enrolment_id = _enrol(app, bench, owner[1])
        try:
            answer = auth_client.post('/api/v2/users/bulk/delete',
                                      data=json.dumps({'ids': [owner[0]['id']]}),
                                      content_type='application/json')
            assert answer.status_code == 200, answer.data[:300]
            data = json.loads(answer.data)['data']
            assert data['success'] == [owner[0]['id']]
            assert data['acme_local_only'] == [bench.cert_id]
            assert data['acme_upstream_pending'] == [bench.cert_id]
        finally:
            _drop_enrolment(enrolment_id)
