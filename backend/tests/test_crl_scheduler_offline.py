"""Regression: the CRL scheduler must skip offline CAs.

A CA taken offline in password_protected mode keeps a (passphrase-encrypted)
key in the DB, so ``has_private_key`` is true while signing is impossible.
The scheduler used to attempt regeneration anyway and raised
"Password was not given but private key is encrypted" on every cycle.
"""
import json
from unittest.mock import patch

from models import db, CA
from tests.conftest import get_json


class TestCrlSchedulerSkipsOfflineCas:

    def _prepare_offline_ca(self, app, auth_client, create_ca):
        ca = create_ca(cn='CRL Offline CA')
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            row.cdp_enabled = True
            db.session.commit()
        r = auth_client.post(
            f"/api/v2/cas/{ca['id']}/offline",
            data=json.dumps({'password': 'Str0ng!Passw0rd-42',
                             'mode': 'password_protected'}),
            content_type='application/json',
        )
        assert r.status_code == 200, r.data
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            assert row.offline is True
            assert row.has_private_key  # key still present, just protected
        return ca

    def test_offline_ca_is_not_regenerated(self, app, auth_client, create_ca):
        ca = self._prepare_offline_ca(app, auth_client, create_ca)
        with app.app_context():
            from services.crl_scheduler_task import CRLSchedulerTask
            with patch.object(CRLSchedulerTask, 'regenerate_crl') as regen:
                CRLSchedulerTask.execute()
            called_ids = [c.args[0] for c in regen.call_args_list]
            assert ca['id'] not in called_ids

    def test_online_ca_still_considered(self, app, auth_client, create_ca):
        ca = create_ca(cn='CRL Online CA')
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            row.cdp_enabled = True
            db.session.commit()
            from services.crl_scheduler_task import CRLSchedulerTask
            with patch.object(CRLSchedulerTask, 'should_regenerate_crl',
                              return_value=(True, 'test')) as should, \
                 patch.object(CRLSchedulerTask, 'regenerate_crl',
                              return_value=True) as regen:
                CRLSchedulerTask.execute()
            checked_ids = [c.args[0] for c in should.call_args_list]
            assert ca['id'] in checked_ids
