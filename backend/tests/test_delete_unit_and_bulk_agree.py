"""Deleting one row and deleting a hundred ask the same question.

Every deletable resource is reachable through `DELETE /<id>` and through
`POST /bulk/delete`. The two were written separately and drifted:

* a template bound to a SCEP profile was refused by the unit route and
  deleted by the bulk one, leaving a profile pointing at an id the next
  template created would inherit;
* deleting a certificate authority in bulk left its certificate and key
  files on disk and its `revoked_serials` rows behind -- rows that carry a
  real foreign key, so PostgreSQL refuses the delete outright while SQLite,
  which does not enforce them, keeps emitting the orphans into CRLs;
* only the CA routes capped their id list, so a bulk certificate delete
  turned an arbitrary list into that many transactions, and a JSON string
  was iterated character by character;
* the template bulk loop returned mid-flight when a commit failed, so the
  caller got no results body, the ids already committed were silently gone
  and the ids after it were never attempted.

`services/deletion_blockers.py` is where the question lives now.
"""
import json
from datetime import timedelta

from models import db, CA
from models.revoked_serial import RevokedSerial
from models.scep import ScepProfile
from models.certificate_template import CertificateTemplate
from utils.datetime_utils import utc_now
from utils.file_naming import ca_cert_path
import pytest
from tests.fixtures.templates import templates_created_here_removed


@pytest.fixture(autouse=True, scope='module')
def _templates_stay_in_this_module(app):
    with templates_created_here_removed(app):
        yield


def _mk_template(app, name):
    with app.app_context():
        t = CertificateTemplate(name=name, description='parity check',
                                template_type='custom', extensions_template='{}',
                                is_system=False)
        db.session.add(t)
        db.session.commit()
        return t.id


def _bulk(auth_client, resource, ids):
    return auth_client.post(f'/api/v2/{resource}/bulk/delete',
                            data=json.dumps({'ids': ids}),
                            content_type='application/json')


class TestBothPathsRefuseTheSameRows:
    def test_a_ca_with_a_crl_deployment_is_refused_by_both(
            self, app, auth_client, create_ca):
        from models.deploy import DeployTarget, CRLDeployBinding
        from security.encryption import encrypt_text
        ca = create_ca(cn='Parity CRL Deployment CA')
        with app.app_context():
            target = DeployTarget(name='parity-crl-target', host='crl.test',
                                  username='deploy', private_key=encrypt_text('k'))
            db.session.add(target)
            db.session.flush()
            db.session.add(CRLDeployBinding(
                target_id=target.id, ca_id=ca['id'], crl_path='/tmp/ca.crl'))
            db.session.commit()

        unit = auth_client.delete(f"/api/v2/cas/{ca['id']}")
        assert unit.status_code == 409, unit.data
        assert b'CRL is deployed to 1 target' in unit.data

        bulk = _bulk(auth_client, 'cas', [ca['id']])
        assert json.loads(bulk.data)['data']['failed'] == [
            {'id': ca['id'], 'error': 'CRL deployed to 1 target(s)'}]

    def test_a_template_bound_to_a_scep_profile_is_refused_by_both(
            self, app, auth_client, create_ca):
        create_ca(cn='Parity SCEP Anchor CA')
        tid = _mk_template(app, 'parity-scep-tpl')
        with app.app_context():
            ca = CA.query.first()
            db.session.add(ScepProfile(name='parity-scep', url_slug='parity-scep',
                                       ca_refid=ca.refid, template_id=tid))
            db.session.commit()

        unit = auth_client.delete(f'/api/v2/templates/{tid}')
        assert unit.status_code == 409, unit.data
        assert b'SCEP profile' in unit.data

        bulk = _bulk(auth_client, 'templates', [tid])
        assert bulk.status_code == 200, bulk.data
        body = json.loads(bulk.data)['data']
        assert body['success'] == []
        assert body['failed'] == [{'id': tid, 'error': 'Bound to 1 SCEP profile(s)'}]

        with app.app_context():
            assert db.session.get(CertificateTemplate, tid) is not None

    def test_a_system_template_is_refused_by_both(self, app, auth_client):
        tid = _mk_template(app, 'parity-system-tpl')
        with app.app_context():
            db.session.get(CertificateTemplate, tid).is_system = True
            db.session.commit()

        unit = auth_client.delete(f'/api/v2/templates/{tid}')
        assert unit.status_code == 403, unit.data

        bulk = _bulk(auth_client, 'templates', [tid])
        assert json.loads(bulk.data)['data']['failed'] == [
            {'id': tid, 'error': 'Cannot delete system template'}]

    def test_a_valid_certificate_is_refused_by_both(self, auth_client, create_cert):
        cert = create_cert(cn='parity-valid.example.com')

        bulk = _bulk(auth_client, 'certificates', [cert['id']])
        assert json.loads(bulk.data)['data']['failed'] == [
            {'id': cert['id'],
             'error': 'Cannot delete a valid certificate: revoke it first'}]

        unit = auth_client.delete(f"/api/v2/certificates/{cert['id']}")
        assert unit.status_code == 409, unit.data
        assert b'revoke it first' in unit.data

    def test_a_ca_with_issued_certificates_is_refused_by_both(
            self, auth_client, create_ca, create_cert):
        ca = create_ca(cn='Parity Busy CA')
        create_cert(cn='parity-busy.example.com', ca_id=ca['id'])

        unit = auth_client.delete(f"/api/v2/cas/{ca['id']}")
        assert unit.status_code == 409, unit.data

        bulk = _bulk(auth_client, 'cas', [ca['id']])
        failed = json.loads(bulk.data)['data']['failed']
        assert failed == [{'id': ca['id'], 'error': '1 certificate(s) issued by it'}]


class TestBulkDeletesAsThoroughlyAsTheUnitRoute:
    def test_deleting_a_ca_in_bulk_unlinks_its_files_and_purges_its_serials(
            self, app, auth_client, create_ca):
        unit_ca = create_ca(cn='Parity Unit CA')
        bulk_ca = create_ca(cn='Parity Bulk CA')

        paths = {}
        with app.app_context():
            for label, d in (('unit', unit_ca), ('bulk', bulk_ca)):
                ca = db.session.get(CA, d['id'])
                paths[label] = ca_cert_path(ca)
                db.session.add(RevokedSerial(
                    caref=ca.refid, serial_number=f'0b0c0d{label}',
                    revoked_at=utc_now(), valid_to=utc_now() + timedelta(days=30)))
            db.session.commit()

        assert paths['unit'].exists() and paths['bulk'].exists()

        assert auth_client.delete(
            f"/api/v2/cas/{unit_ca['id']}").status_code in (200, 204)
        bulk = _bulk(auth_client, 'cas', [bulk_ca['id']])
        assert json.loads(bulk.data)['data']['success'] == [bulk_ca['id']]

        with app.app_context():
            for label in ('unit', 'bulk'):
                assert not paths[label].exists(), \
                    f'{label} delete left the CA certificate file on disk'
                assert RevokedSerial.query.filter_by(
                    serial_number=f'0b0c0d{label}').count() == 0, \
                    f'{label} delete left revoked_serials behind'


class TestEveryBulkListIsBounded:
    # The five bulk delete routes. `csrs` and `users` read the list
    # themselves and capped nothing, so a JSON string was iterated character
    # by character and a list of any length became that many transactions.
    BULK_ROUTES = ('cas', 'certificates', 'templates', 'csrs', 'users')

    # And the routes that are not deletions: revoking, renewing, exporting
    # and signing cost more per id than a delete does, not less.
    OTHER_BULK = ('certificates/bulk/revoke', 'certificates/bulk/renew',
                  'certificates/bulk/export', 'cas/bulk/export',
                  'csrs/bulk/sign')

    def test_an_oversized_id_list_is_refused_everywhere(self, auth_client):
        many = list(range(900000, 900000 + 101))
        for resource in self.BULK_ROUTES:
            r = _bulk(auth_client, resource, many)
            assert r.status_code == 400, (resource, r.data)
            assert b'max 100 per request' in r.data, resource

    def test_a_list_that_is_not_a_list_is_refused_everywhere(self, auth_client):
        for resource in self.BULK_ROUTES:
            r = _bulk(auth_client, resource, 'abc')
            assert r.status_code == 400, (resource, r.data)
            assert b'must be an array' in r.data, resource

    def test_every_other_bulk_route_is_bounded_too(self, auth_client):
        many = list(range(900000, 900000 + 101))
        for route in self.OTHER_BULK:
            r = auth_client.post(f'/api/v2/{route}',
                                 data=json.dumps({'ids': many}),
                                 content_type='application/json')
            assert r.status_code == 400, (route, r.data[:200])
            assert b'max 100 per request' in r.data, route

    def test_a_list_at_the_cap_is_still_accepted(self, auth_client):
        r = _bulk(auth_client, 'certificates', list(range(900000, 900100)))
        assert r.status_code == 200, r.data
        assert len(json.loads(r.data)['data']['failed']) == 100


class TestOneFailureDoesNotAbandonTheRest:
    def test_a_failing_template_commit_still_reports_and_continues(
            self, app, auth_client, monkeypatch):
        ids = [_mk_template(app, f'parity-loop-{i}') for i in range(3)]

        import api.v2.templates as tmod
        real = tmod.safe_commit
        calls = {'n': 0}

        def flaky(logger_instance, msg='x'):
            calls['n'] += 1
            if calls['n'] == 2:
                db.session.rollback()
                from utils.response import error_response
                return False, error_response('Delete template', 500)
            return real(logger_instance, msg)

        monkeypatch.setattr(tmod, 'safe_commit', flaky)

        r = _bulk(auth_client, 'templates', ids)
        assert r.status_code == 200, r.data
        body = json.loads(r.data)['data']

        assert body['success'] == [ids[0], ids[2]], body
        assert body['failed'] == [{'id': ids[1], 'error': 'Deletion failed'}], body
        with app.app_context():
            assert db.session.get(CertificateTemplate, ids[1]) is not None
            assert db.session.get(CertificateTemplate, ids[2]) is None
