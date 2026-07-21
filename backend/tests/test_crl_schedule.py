"""Tests for the full CRL schedule (discussion #207, migration 059).

Validity decoupled from publish cadence, configurable signature digest,
next_publish exposure, scheduler publish-interval trigger.
"""
import base64
import json
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.backends import default_backend

from models import db
from models.crl import CRLMetadata
from services.crl_scheduler_task import CRLSchedulerTask
from tests.conftest import get_json
from utils.datetime_utils import utc_now

CONTENT_JSON = 'application/json'


def _post(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type=CONTENT_JSON)


class TestCrlConfigApi:

    def test_defaults(self, auth_client, create_ca):
        ca = create_ca(cn='Sched Default CA')
        r = auth_client.get(f"/api/v2/crl/{ca['id']}/config")
        assert r.status_code == 200
        data = get_json(r)['data']
        assert data['crl_validity_days'] == 7
        assert data['crl_publish_interval_hours'] is None
        assert data['crl_digest'] == 'sha256'
        assert data['next_publish'] is None

    def test_set_and_get_roundtrip(self, auth_client, create_ca):
        ca = create_ca(cn='Sched Config CA')
        r = _post(auth_client, f"/api/v2/crl/{ca['id']}/config",
                  {'validity_days': 2, 'publish_interval_hours': 24,
                   'digest': 'sha384'})
        assert r.status_code == 200, r.data
        data = get_json(r)['data']
        assert data['crl_validity_days'] == 2
        assert data['crl_publish_interval_hours'] == 24
        assert data['crl_digest'] == 'sha384'

    def test_publish_interval_cannot_exceed_validity(self, auth_client, create_ca):
        ca = create_ca(cn='Sched Guard CA')
        r = _post(auth_client, f"/api/v2/crl/{ca['id']}/config",
                  {'validity_days': 1, 'publish_interval_hours': 48})
        assert r.status_code == 400

    def test_invalid_digest_rejected(self, auth_client, create_ca):
        ca = create_ca(cn='Sched Digest CA')
        r = _post(auth_client, f"/api/v2/crl/{ca['id']}/config", {'digest': 'md5'})
        assert r.status_code == 400

    def test_interval_clearable(self, auth_client, create_ca):
        ca = create_ca(cn='Sched Clear CA')
        _post(auth_client, f"/api/v2/crl/{ca['id']}/config",
              {'publish_interval_hours': 12})
        r = _post(auth_client, f"/api/v2/crl/{ca['id']}/config",
                  {'publish_interval_hours': None})
        assert get_json(r)['data']['crl_publish_interval_hours'] is None

    def test_config_requires_auth(self, client):
        assert client.get('/api/v2/crl/1/config').status_code == 401
        assert _post(client, '/api/v2/crl/1/config', {}).status_code == 401


class TestCrlGenerationHonorsSchedule:

    def _latest_crl_obj(self, app, ca_id):
        with app.app_context():
            row = CRLMetadata.query.filter_by(ca_id=ca_id, is_delta=False).order_by(
                CRLMetadata.crl_number.desc()
            ).first()
            assert row is not None
            return x509.load_pem_x509_crl(row.crl_pem.encode(), default_backend()), row

    def test_validity_and_digest_applied(self, app, auth_client, create_ca):
        ca = create_ca(cn='Sched Gen CA')
        _post(auth_client, f"/api/v2/crl/{ca['id']}/config",
              {'validity_days': 3, 'digest': 'sha384'})
        r = auth_client.post(f"/api/v2/crl/{ca['id']}/regenerate")
        assert r.status_code == 200, r.data

        crl, row = self._latest_crl_obj(app, ca['id'])
        assert crl.signature_hash_algorithm.name == 'sha384'
        window = crl.next_update_utc - crl.last_update_utc
        assert window == timedelta(days=3)

    def test_default_stays_sha256_7d(self, app, auth_client, create_ca):
        ca = create_ca(cn='Sched Gen Default CA')
        r = auth_client.post(f"/api/v2/crl/{ca['id']}/regenerate")
        assert r.status_code == 200, r.data
        crl, _ = self._latest_crl_obj(app, ca['id'])
        assert crl.signature_hash_algorithm.name == 'sha256'
        assert crl.next_update_utc - crl.last_update_utc == timedelta(days=7)

    def test_next_publish_in_crl_get(self, app, auth_client, create_ca):
        ca = create_ca(cn='Sched NextPub CA')
        _post(auth_client, f"/api/v2/crl/{ca['id']}/config",
              {'validity_days': 2, 'publish_interval_hours': 24})
        auth_client.post(f"/api/v2/crl/{ca['id']}/regenerate")
        r = auth_client.get(f"/api/v2/crl/{ca['id']}")
        data = get_json(r)['data']
        assert data['next_publish'] is not None


class TestSchedulerPublishInterval:

    def test_recent_delta_does_not_mask_stale_base_crl(
        self, app, auth_client, create_ca
    ):
        ca = create_ca(cn='Sched Delta Isolation CA')
        auth_client.post(f"/api/v2/crl/{ca['id']}/regenerate")

        with app.app_context():
            base = CRLMetadata.query.filter_by(
                ca_id=ca['id'], is_delta=False
            ).first()
            base.next_update = utc_now() - timedelta(hours=1)
            base.created_at = utc_now() - timedelta(hours=2)

            delta = CRLMetadata(
                ca_id=ca['id'],
                crl_number=base.crl_number + 1,
                this_update=utc_now(),
                next_update=utc_now() + timedelta(days=7),
                crl_pem=base.crl_pem,
                crl_der=base.crl_der,
                revoked_count=0,
                is_delta=True,
                base_crl_number=base.crl_number,
                generated_by='test',
            )
            db.session.add(delta)
            db.session.commit()

            should, reason = CRLSchedulerTask.should_regenerate_crl(ca['id'])
            assert should is True
            assert 'stale' in reason.lower()

    def test_interval_triggers_regeneration(self, app, auth_client, create_ca):
        ca = create_ca(cn='Sched Task CA')
        _post(auth_client, f"/api/v2/crl/{ca['id']}/config",
              {'validity_days': 7, 'publish_interval_hours': 6})
        auth_client.post(f"/api/v2/crl/{ca['id']}/regenerate")

        with app.app_context():
            should, _ = CRLSchedulerTask.should_regenerate_crl(ca['id'])
            assert should is False  # fresh CRL, interval not reached

            row = CRLMetadata.query.filter_by(ca_id=ca['id'], is_delta=False).order_by(
                CRLMetadata.crl_number.desc()
            ).first()
            row.this_update = utc_now() - timedelta(hours=7)
            db.session.commit()

            should, reason = CRLSchedulerTask.should_regenerate_crl(ca['id'])
            assert should is True
            assert 'publish interval' in reason.lower()
