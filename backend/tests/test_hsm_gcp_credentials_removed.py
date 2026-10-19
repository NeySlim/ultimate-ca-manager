"""A Google Cloud KMS provider saved without its key keeps none.

The form leaves `service_account_json` out to fall back on the server's
default credentials, '***' keeps the stored key.
"""
import json

from models.hsm import HsmProvider


def _saved(config):
    provider = HsmProvider(name='gcp', type='google-kms')
    provider.set_config({'project_id': 'p', 'service_account_json': json.dumps({'type': 'service_account'})})
    provider.set_config(config)
    return provider.get_config()


def test_the_mask_keeps_the_stored_key(app):
    with app.app_context():
        assert _saved({'project_id': 'p', 'service_account_json': '***'})['service_account_json']


def test_leaving_it_out_removes_it(app):
    with app.app_context():
        assert 'service_account_json' not in _saved({'project_id': 'p'})
