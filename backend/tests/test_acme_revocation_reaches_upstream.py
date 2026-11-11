"""Revoking a certificate UCM obtained over ACME tells the CA that issued it.

The revoke routes (single, bulk, approved request) carried a revocation to
the issuing CA only for Microsoft CA certificates: a public ACME CA kept
answering "good" while UCM said "revoked successfully". They now send it
over RFC 8555 §7.6, keep it owed for the scheduler when the CA does not
confirm, and say when the revocation stayed local.
"""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from models import db
from models.acme_models import AcmeClientOrder
from services import acme_renewal_service as renew_mod
from tests.test_acme_renewal_in_place import Bench, _restore_config, _set_config

ERROR = 'urn:ietf:params:acme:error:'


def _answer(status, problem=None):
    body = {'type': ERROR + problem, 'detail': problem} if problem else {}
    return SimpleNamespace(status_code=status, json=lambda: body, headers={})


@pytest.fixture
def bench(app):
    with app.app_context():
        email = _set_config('acme.client.email', 'upstream-revoke@example.com')
        b = Bench(f'upstream-revoke-{uuid.uuid4().hex[:8]}.example.com')
        with patch('services.acme.acme_client_service.AcmeClientService.for_order',
                   return_value=b.client):
            yield b
        b.cleanup()
        _restore_config('acme.client.email', email)


def _owed(bench):
    db.session.expire_all()
    return bench.parent().upstream_revocations_list


def _revoke(auth_client, bench, reason):
    answer = auth_client.post(f'/api/v2/certificates/{bench.cert_id}/revoke',
                              data=json.dumps({'reason': reason}),
                              content_type='application/json')
    assert answer.status_code == 200, answer.data[:300]
    return json.loads(answer.data)


class TestTheSingleRoute:
    def test_the_ca_is_told_with_the_reason(self, auth_client, bench):
        body = _revoke(auth_client, bench, 'keyCompromise')
        sent = bench.client.revoke_certificate.call_args
        assert sent.args[0] == bench.old_pem and sent.kwargs == {'reason': 1}
        assert body['meta'] == {'acme_ca_revoked': True}
        assert _owed(bench) == []

    def test_unspecified_leaves_the_optional_reason_out(self, auth_client, bench):
        _revoke(auth_client, bench, 'unspecified')
        assert bench.client.revoke_certificate.call_args.kwargs == {'reason': None}

    def test_a_ca_that_does_not_answer_is_owed_and_retried(self, auth_client, bench):
        bench.client.revoke_certificate = MagicMock(return_value=_answer(503))
        body = _revoke(auth_client, bench, 'cessationOfOperation')
        assert body['meta']['acme_local_only'] is True
        assert body['meta']['acme_upstream_pending'] is True
        assert 'HTTP 503' in body['meta']['acme_ca_error']
        owed = _owed(bench)
        assert [e['serial'] for e in owed] == [bench.old_serial]
        assert owed[0]['reason'] == 5 and owed[0]['attempts'] == 1

        bench.client.revoke_certificate.return_value = _answer(200)
        renew_mod.retry_upstream_revocations()
        assert _owed(bench) == []

    def test_an_account_that_no_longer_exists_revokes_locally_and_says_so(
            self, auth_client, bench):
        order = bench.parent()
        order.account_url = f'https://gone-{uuid.uuid4().hex[:6]}.example/acct/1'
        db.session.commit()
        body = _revoke(auth_client, bench, 'keyCompromise')
        assert body['data']['revoked'] is True
        assert body['meta']['acme_local_only'] is True
        assert 'acme_upstream_pending' not in body['meta']
        assert 'no longer exists' in body['message']
        bench.client.revoke_certificate.assert_not_called()
        assert _owed(bench) == []

    def test_a_certificate_whose_order_was_deleted_says_the_account_is_unknown(
            self, auth_client, bench):
        from services.acme.order_housekeeping import delete_order
        delete_order(bench.parent())
        db.session.commit()
        body = _revoke(auth_client, bench, 'keyCompromise')
        assert body['meta']['acme_local_only'] is True
        assert 'no longer exists' not in body['message']
        assert 'no longer has the ACME order' in body['message']
        bench.client.revoke_certificate.assert_not_called()

    def test_a_held_certificate_renewed_into_a_new_row_is_still_revoked_at_the_ca(
            self, auth_client, bench):
        _revoke(auth_client, bench, 'certificateHold')
        ok, message = bench.renew()
        assert ok, message
        db.session.expire_all()
        assert bench.parent().certificate_id != bench.cert_id
        bench.client.revoke_certificate.reset_mock()
        body = _revoke(auth_client, bench, 'keyCompromise')
        sent = bench.client.revoke_certificate.call_args
        assert sent.args[0] == bench.old_pem and sent.kwargs == {'reason': 1}
        assert body['meta'] == {'acme_ca_revoked': True}

    def test_a_proxy_order_naming_no_upstream_account_is_not_revoked_with_another(
            self, auth_client, bench):
        order = bench.parent()
        order.is_proxy_order = True
        db.session.commit()
        body = _revoke(auth_client, bench, 'keyCompromise')
        assert body['meta']['acme_local_only'] is True
        assert 'no longer exists' not in body['message']
        assert 'proxy client' in body['message']
        bench.client.revoke_certificate.assert_not_called()

    def test_a_proxy_order_under_an_upstream_account_is_revoked_there(
            self, auth_client, bench):
        order = bench.parent()
        order.is_proxy_order = True
        order.account_url = 'https://ca.example/acct/1'
        db.session.commit()
        with patch('services.acme.acme_client_service.AcmeClientService.order_account',
                   return_value=object()):
            body = _revoke(auth_client, bench, 'keyCompromise')
        assert body['meta'] == {'acme_ca_revoked': True}
        assert bench.client.revoke_certificate.call_args.kwargs == {'reason': 1}

    def test_a_local_hold_is_never_sent_to_the_ca(self, auth_client, bench):
        body = _revoke(auth_client, bench, 'certificateHold')
        bench.client.revoke_certificate.assert_not_called()
        assert body['meta']['acme_local_only'] is True
        assert 'hold' in body['message']
        assert _owed(bench) == []

    def test_a_certificate_not_from_acme_is_left_alone(
            self, app, auth_client, bench, create_ca, create_cert):
        from services.ca_service import CAService
        from services.cert_service import CertificateService
        # A CA of its own: the session's default CA is shared and never deleted
        ca = create_ca(cn='Not ACME upstream CA')
        other = None
        try:
            other = create_cert(cn='not-acme-upstream.example', ca_id=ca['id'])
            answer = auth_client.post(f"/api/v2/certificates/{other['id']}/revoke",
                                      data=json.dumps({'reason': 'keyCompromise'}),
                                      content_type='application/json')
            assert answer.status_code == 200
            assert 'meta' not in json.loads(answer.data)
            bench.client.revoke_certificate.assert_not_called()
        finally:
            with app.app_context():
                # The certificate before its CA: PostgreSQL enforces the foreign key
                if other is not None:
                    assert CertificateService.delete_certificate(other['id'], username='admin')
                assert CAService.delete_ca(ca['id'], username='admin')


class TestTheBulkRoute:
    def _bulk(self, auth_client, bench):
        answer = auth_client.post('/api/v2/certificates/bulk/revoke',
                                  data=json.dumps({'ids': [bench.cert_id],
                                                   'reason': 'keyCompromise'}),
                                  content_type='application/json')
        assert answer.status_code == 200, answer.data[:300]
        return json.loads(answer.data)['data']

    def test_the_ca_is_told(self, auth_client, bench):
        data = self._bulk(auth_client, bench)
        assert data['success'] == [bench.cert_id] and 'acme_local_only' not in data
        assert bench.client.revoke_certificate.call_args.kwargs == {'reason': 1}

    def test_a_ca_that_does_not_answer_is_reported_and_owed(self, auth_client, bench):
        bench.client.revoke_certificate = MagicMock(return_value=_answer(500))
        data = self._bulk(auth_client, bench)
        assert data['success'] == [bench.cert_id]
        assert data['acme_local_only'] == [bench.cert_id]
        assert [e['serial'] for e in _owed(bench)] == [bench.old_serial]


class TestAnApprovedRevocation:
    def _approve(self, app, bench):
        from api.v2.policies import _revoke_approved_certificate
        from models.policy import ApprovalRequest
        row = bench.row()
        data = {'certificate_id': row.id, 'serial_number': row.serial_number,
                'reason': 'keyCompromise', 'cn': bench.name}
        approval = ApprovalRequest(request_type='revocation', request_data=json.dumps(data),
                                   status='approved')
        db.session.add(approval)
        db.session.commit()
        try:
            with app.test_request_context():
                return _revoke_approved_certificate(approval, data)
        finally:
            db.session.delete(db.session.get(ApprovalRequest, approval.id))
            db.session.commit()

    def test_the_ca_is_told(self, app, bench):
        result = self._approve(app, bench)
        assert result['acme_local_only'] is False
        assert bench.client.revoke_certificate.call_args.kwargs == {'reason': 1}

    def test_a_ca_that_does_not_answer_is_reported_and_owed(self, app, bench):
        bench.client.revoke_certificate = MagicMock(return_value=_answer(503))
        result = self._approve(app, bench)
        assert result['acme_local_only'] is True
        assert [e['serial'] for e in _owed(bench)] == [bench.old_serial]


def test_a_replaced_certificate_is_matched_by_id_and_serial():
    order = AcmeClientOrder()
    order.add_replaced(SimpleNamespace(id=7, serial_number='12'))
    order.add_replaced(SimpleNamespace(id=7, serial_number='12'))
    assert order.names_replaced(SimpleNamespace(id=7, serial_number='12'))
    # An id the database handed out again names another certificate
    assert not order.names_replaced(SimpleNamespace(id=7, serial_number='13'))
    assert not order.names_replaced(SimpleNamespace(id=17, serial_number='12'))
    assert json.loads(order.replaced_certificates) == [{'certificate_id': 7, 'serial': '12'}]


def test_a_revocation_confirmed_by_the_ca_keeps_the_related_certificate_warning():
    from api.v2.certificates.cert_lifecycle import _acme_answer
    from services.acme.upstream_revocation import REVOKED
    kept = ('Certificate revoked; its related certificate #41 was not revoked, '
            'revoke it separately')
    answer = _acme_answer(REVOKED, None, kept)
    assert 'at the ACME CA' in answer['message']
    assert 'related certificate #41 was not revoked' in answer['message']
    assert answer['meta'] == {'acme_ca_revoked': True}
    plain = _acme_answer(REVOKED, None, 'Certificate revoked successfully')
    assert plain['message'] == 'Certificate revoked in UCM and at the ACME CA'
