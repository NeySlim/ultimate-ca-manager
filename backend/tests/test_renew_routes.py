"""The renew route and the bulk renew route drive the shared in-place renewal
routine: arguments passed, refusals translated, notices reported, one CRL per
CA after a bulk renewal.
"""
import json

import pytest

import fips_mode
from api.v2.certificates import bulk as bulk_mod
from api.v2.certificates import cert_renew as renew_mod
from models import CA, Certificate, User, db
from models.policy import CertificatePolicy
from services.cert.renewal import RenewalError
from services.crl import CRLService
from tests.test_approval_on_sign_and_renew import _cert_row, _drop_policy, _drop_rows, _json, _operator

BAD_DURATION = 'validity_days must be an integer from 1 to 3650'


def _row(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        return {'serial': row.serial_number, 'renewed': row.renewed_times or 0, 'revoked': row.revoked}


def _policy(app, ca_id, name, *, approval, rules=None):
    with app.app_context():
        pol = CertificatePolicy(name=f'{name}-{ca_id}', policy_type='issuance', ca_id=ca_id,
                                requires_approval=approval, min_approvers=1, is_active=True, priority=100)
        pol.set_rules(rules or {})
        db.session.add(pol)
        db.session.commit()
        return pol.id, pol.name


def _set_cdp(app, ca_id, enabled):
    with app.app_context():
        db.session.get(CA, ca_id).cdp_enabled = enabled
        db.session.commit()


@pytest.fixture
def spy_routine(monkeypatch):
    """Record the keyword arguments of every routine call, then run it."""
    calls = []

    def wrap(module):
        real = module.renew_certificate_in_place

        def spy(cert, *args, **kwargs):
            calls.append(kwargs)
            return real(cert, *args, **kwargs)
        monkeypatch.setattr(module, 'renew_certificate_in_place', spy)
    wrap(renew_mod)
    wrap(bulk_mod)
    return calls


@pytest.fixture
def spy_crl(monkeypatch):
    calls = []
    real = CRLService.generate_crl

    def spy(ca_id, *args, **kwargs):
        calls.append((ca_id, kwargs.get('username')))
        return real(ca_id, *args, **kwargs)
    monkeypatch.setattr(CRLService, 'generate_crl', staticmethod(spy))
    return calls


def _admin_id(app):
    with app.app_context():
        return User.query.filter_by(username='admin').first().id


class TestSingleRenew:

    @pytest.mark.parametrize('bad', [True, 0, 3651, 'abc', 12.5])
    def test_invalid_duration_is_refused_without_writing(self, app, auth_client, create_ca, spy_routine, bad):
        ca = create_ca(cn='Renew route bad duration CA')
        cert_id = _cert_row(app, ca['id'], 'renew-route-bad.example.test')
        try:
            before = _row(app, cert_id)
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew', {'validity_days': bad})
            assert r.status_code == 400
            assert r.get_json()['message'] == BAD_DURATION
            assert _row(app, cert_id) == before
            assert spy_routine == []
        finally:
            _drop_rows(app, cert_id)

    @pytest.mark.parametrize('empty', [None, ''])
    def test_empty_duration_keeps_the_original(self, app, auth_client, create_ca, spy_routine, empty):
        ca = create_ca(cn='Renew route empty duration CA')
        cert_id = _cert_row(app, ca['id'], 'renew-route-empty.example.test')
        try:
            before = _row(app, cert_id)
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew', {'validity_days': empty})
            assert r.status_code == 200, r.get_json()
            assert spy_routine[-1]['validity_days'] is None
            assert _row(app, cert_id)['serial'] != before['serial']
        finally:
            _drop_rows(app, cert_id)

    def test_routine_is_called_as_a_manual_rekeying_renewal(self, app, auth_client, create_ca, spy_routine):
        ca = create_ca(cn='Renew route args CA')
        cert_id = _cert_row(app, ca['id'], 'renew-route-args.example.test')
        try:
            before = _row(app, cert_id)
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew', {'validity_days': 12})
            assert r.status_code == 200, r.get_json()
            body = r.get_json()
            assert body['message'] == 'Certificate renewed successfully'
            assert body['data']['id'] == cert_id
            after = _row(app, cert_id)
            assert body['data']['serial_number'] == after['serial'] != before['serial']
            assert spy_routine == [{
                'username': 'admin', 'actor_user_id': _admin_id(app), 'rekey': True,
                'regenerate_crl': True, 'trigger': 'manual', 'validity_days': 12,
            }]
        finally:
            _drop_rows(app, cert_id)

    def test_routine_refusal_answers_its_status_and_message(self, app, auth_client, create_ca, monkeypatch):
        ca = create_ca(cn='Renew route refusal CA')
        cert_id = _cert_row(app, ca['id'], 'renew-route-refusal.example.test')

        def refuse(cert, **kwargs):
            raise RenewalError('Certificate was renewed by another request; reload it and retry', 409)
        monkeypatch.setattr(renew_mod, 'renew_certificate_in_place', refuse)
        try:
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew')
            assert r.status_code == 409
            assert r.get_json()['message'] == 'Certificate was renewed by another request; reload it and retry'
        finally:
            _drop_rows(app, cert_id)

    def test_fips_refusal_carries_the_fips_problem_type(self, app, auth_client, create_ca, monkeypatch):
        ca = create_ca(cn='Renew route FIPS CA')
        cert_id = _cert_row(app, ca['id'], 'renew-route-fips.example.test')

        def refuse(cert, **kwargs):
            raise RenewalError.from_fips(fips_mode.FipsRestricted('Ed25519 key of certificate x is not allowed in FIPS mode'))
        monkeypatch.setattr(renew_mod, 'renew_certificate_in_place', refuse)
        try:
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew')
            assert r.status_code == 400
            body = r.get_json()
            assert body['type'] == fips_mode.PROBLEM_TYPE, body
            assert 'Ed25519' in body['message']
        finally:
            _drop_rows(app, cert_id)

    def test_unexpected_failure_is_a_500_without_internals(self, app, auth_client, create_ca, monkeypatch):
        ca = create_ca(cn='Renew route crash CA')
        cert_id = _cert_row(app, ca['id'], 'renew-route-crash.example.test')
        rolled_back = []
        real_rollback = db.session.rollback

        def crash(cert, **kwargs):
            raise RuntimeError('secret internal detail')
        monkeypatch.setattr(renew_mod, 'renew_certificate_in_place', crash)
        monkeypatch.setattr(db.session, 'rollback', lambda: (rolled_back.append(1), real_rollback())[1])
        try:
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew')
            assert r.status_code == 500
            assert r.get_json()['message'] == 'Failed to renew certificate'
            assert 'secret' not in r.get_data(as_text=True)
            assert rolled_back
        finally:
            monkeypatch.undo()
            _drop_rows(app, cert_id)

    def test_revoked_certificate_is_refused_with_409(self, app, auth_client, create_ca):
        ca = create_ca(cn='Renew route revoked CA')
        cert_id = _cert_row(app, ca['id'], 'renew-route-revoked.example.test')
        try:
            with app.app_context():
                db.session.get(Certificate, cert_id).revoked = True
                db.session.commit()
            before = _row(app, cert_id)
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew')
            assert r.status_code == 409
            assert _row(app, cert_id) == before
        finally:
            _drop_rows(app, cert_id)


class TestApproval:

    def test_operator_is_queued_and_admin_renews(self, app, auth_client, create_ca, create_user):
        ca = create_ca(cn='Renew route approval CA')
        pid, pname = _policy(app, ca['id'], 'renew-route-approval', approval=True)
        cert_id = _cert_row(app, ca['id'], 'renew-route-approval.example.test')
        operator = _operator(app, create_user)
        try:
            before = _row(app, cert_id)
            r = _json(operator, 'post', f'/api/v2/certificates/{cert_id}/renew')
            assert r.status_code == 200, r.get_json()
            data = r.get_json()['data']
            assert data['status'] == 'pending_approval' and data['approval_id']
            assert data['policy_name'] == pname
            assert _row(app, cert_id) == before

            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew')
            assert r.status_code == 200, r.get_json()
            assert r.get_json()['message'] == 'Certificate renewed successfully'
            assert _row(app, cert_id)['serial'] != before['serial']
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, cert_id)

    def test_bulk_queues_the_renewable_and_fails_the_other(self, app, create_ca, create_user):
        ca = create_ca(cn='Bulk renew approval CA')
        pid, pname = _policy(app, ca['id'], 'bulk-renew-approval', approval=True)
        ids = [_cert_row(app, ca['id'], f'bulk-renew-approval-{i}.example.test') for i in range(3)]
        operator = _operator(app, create_user)
        try:
            with app.app_context():
                db.session.get(Certificate, ids[1]).revoked = True
                db.session.commit()
            r = _json(operator, 'post', '/api/v2/certificates/bulk/renew', {'ids': ids})
            assert r.status_code == 200, r.get_json()
            data = r.get_json()['data']
            assert data['success'] == []
            assert [p['id'] for p in data['pending_approval']] == [ids[0], ids[2]]
            assert all(p['approval_id'] and p['policy_name'] == pname for p in data['pending_approval'])
            assert data['failed'] == [{'id': ids[1], 'error':
                                       'Cannot renew a revoked certificate. Issue a new certificate instead.'}]
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, *ids)


class TestNotices:

    def test_shortened_renewal_reports_a_notice(self, app, auth_client, create_ca):
        ca = create_ca(cn='Renew route notice CA')
        pid, _ = _policy(app, ca['id'], 'renew-route-cap', approval=False, rules={'max_validity_days': 5})
        cert_id = _cert_row(app, ca['id'], 'renew-route-notice.example.test')
        try:
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew')
            assert r.status_code == 200, r.get_json()
            notices = r.get_json()['meta']['notices']
            assert notices and all(isinstance(n, str) for n in notices)
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, cert_id)

    def test_full_renewal_has_no_notice(self, app, auth_client, create_ca):
        ca = create_ca(cn='Renew route no notice CA')
        cert_id = _cert_row(app, ca['id'], 'renew-route-no-notice.example.test')
        try:
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew')
            assert r.status_code == 200, r.get_json()
            assert 'notices' not in (r.get_json().get('meta') or {})
        finally:
            _drop_rows(app, cert_id)


class TestBulkRenew:

    def test_duration_is_refused_and_nothing_renewed(self, app, auth_client, create_ca, spy_routine):
        ca = create_ca(cn='Bulk renew duration CA')
        cert_id = _cert_row(app, ca['id'], 'bulk-renew-duration.example.test')
        try:
            before = _row(app, cert_id)
            r = _json(auth_client, 'post', '/api/v2/certificates/bulk/renew',
                      {'ids': [cert_id], 'validity_days': 30})
            assert r.status_code == 400
            assert _row(app, cert_id) == before and spy_routine == []
        finally:
            _drop_rows(app, cert_id)

    def test_items_are_renewed_as_bulk_with_one_crl_per_ca(self, app, auth_client, create_ca, spy_routine, spy_crl):
        ca = create_ca(cn='Bulk renew CRL CA')
        _set_cdp(app, ca['id'], True)
        ids = [_cert_row(app, ca['id'], f'bulk-renew-crl-{i}.example.test') for i in range(2)]
        try:
            before = [_row(app, i) for i in ids]
            r = _json(auth_client, 'post', '/api/v2/certificates/bulk/renew', {'ids': ids})
            assert r.status_code == 200, r.get_json()
            body = r.get_json()
            assert body['data'] == {'success': ids, 'failed': []}
            assert body['message'] == '2 certificates renewed'
            assert all(_row(app, i)['serial'] != b['serial'] for i, b in zip(ids, before))
            assert spy_crl == [(ca['id'], 'admin')]
            expected = {'username': 'admin', 'actor_user_id': _admin_id(app), 'rekey': True,
                        'regenerate_crl': False, 'trigger': 'bulk'}
            assert spy_routine == [expected, expected]
        finally:
            _drop_rows(app, *ids)

    def test_no_crl_when_the_cdp_is_off(self, app, auth_client, create_ca, spy_crl):
        ca = create_ca(cn='Bulk renew no CDP CA')
        _set_cdp(app, ca['id'], False)
        cert_id = _cert_row(app, ca['id'], 'bulk-renew-nocdp.example.test')
        try:
            r = _json(auth_client, 'post', '/api/v2/certificates/bulk/renew', {'ids': [cert_id]})
            assert r.get_json()['data']['success'] == [cert_id]
            assert spy_crl == []
        finally:
            _drop_rows(app, cert_id)

    def test_crl_failure_leaves_the_answer_unchanged(self, app, auth_client, create_ca, monkeypatch):
        ca = create_ca(cn='Bulk renew CRL failure CA')
        _set_cdp(app, ca['id'], True)
        cert_id = _cert_row(app, ca['id'], 'bulk-renew-crlfail.example.test')

        called = []

        def boom(ca_id, **kwargs):
            called.append(ca_id)
            raise RuntimeError('crl down')
        monkeypatch.setattr(CRLService, 'generate_crl', staticmethod(boom))
        try:
            r = _json(auth_client, 'post', '/api/v2/certificates/bulk/renew', {'ids': [cert_id]})
            assert r.status_code == 200
            assert r.get_json()['data'] == {'success': [cert_id], 'failed': []}
            assert called == [ca['id']]
        finally:
            _drop_rows(app, cert_id)

    def test_a_refused_item_does_not_stop_the_next(self, app, auth_client, create_ca, monkeypatch):
        ca = create_ca(cn='Bulk renew refusal CA')
        ids = [_cert_row(app, ca['id'], f'bulk-renew-refusal-{i}.example.test') for i in range(3)]
        real = bulk_mod.renew_certificate_in_place

        def routine(cert, **kwargs):
            if cert.id == ids[0]:
                raise RenewalError('Policy violation: nope', 400)
            if cert.id == ids[1]:
                raise RuntimeError('secret internal detail')
            return real(cert, **kwargs)
        monkeypatch.setattr(bulk_mod, 'renew_certificate_in_place', routine)
        try:
            r = _json(auth_client, 'post', '/api/v2/certificates/bulk/renew', {'ids': ids + [999999]})
            assert r.status_code == 200
            data = r.get_json()['data']
            assert data['success'] == [ids[2]]
            assert data['failed'] == [
                {'id': ids[0], 'error': 'Policy violation: nope'},
                {'id': ids[1], 'error': 'Renewal failed'},
                {'id': 999999, 'error': 'Not found'},
            ]
            assert 'pending_approval' not in data
        finally:
            _drop_rows(app, *ids)
