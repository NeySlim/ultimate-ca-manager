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
