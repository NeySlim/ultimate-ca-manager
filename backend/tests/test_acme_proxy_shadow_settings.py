"""The ACME proxy's account and EAB live on its CA account only.

`acme.proxy.eab_kid`, `acme.proxy.eab_hmac_key` and `acme.proxy.account_url`
were copies kept beside the linked CA account since migration 050: the API
returned the copy when no account was linked, and wrote both, so the two
could disagree while only the account was used.
"""
import json

import pytest

from models import AcmeClientAccount, SystemConfig, db
from services.acme.acme_proxy_account import PROXY_ACCOUNT_ID_KEY

SHADOWS = ('acme.proxy.eab_kid', 'acme.proxy.eab_hmac_key', 'acme.proxy.account_url')


@pytest.fixture
def no_linked_account(app):
    with app.app_context():
        saved = getattr(SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).first(), 'value', None)
        SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).delete()
        db.session.commit()
    yield
    with app.app_context():
        SystemConfig.query.filter(SystemConfig.key.in_(SHADOWS + (PROXY_ACCOUNT_ID_KEY,))).delete(
            synchronize_session=False)
        if saved is not None:
            db.session.add(SystemConfig(key=PROXY_ACCOUNT_ID_KEY, value=saved))
        db.session.commit()


def _patch(auth_client, body):
    return auth_client.patch('/api/v2/acme/client/settings', data=json.dumps(body),
                             content_type='application/json')


def test_shadow_copies_are_not_returned(app, auth_client, no_linked_account):
    with app.app_context():
        for key in SHADOWS:
            db.session.add(SystemConfig(key=key, value='shadow'))
        db.session.commit()
    data = auth_client.get('/api/v2/acme/client/settings').get_json()['data']
    assert data['proxy_eab_kid'] is None
    assert data['proxy_eab_hmac_key_set'] is False
    assert data['proxy_account_url'] is None


def test_eab_without_a_linked_account_is_refused(app, auth_client, no_linked_account):
    r = _patch(auth_client, {'proxy_eab_kid': 'kid-x'})
    assert r.status_code == 400, r.data
    with app.app_context():
        assert SystemConfig.query.filter_by(key='acme.proxy.eab_kid').first() is None


def test_eab_is_written_to_the_linked_account_only(app, auth_client, no_linked_account):
    with app.app_context():
        acct = AcmeClientAccount(directory_url='https://shadow-test.example/directory',
                                 label='Shadow test', email='ops@example.com')
        db.session.add(acct)
        db.session.commit()
        acct_id = acct.id
        db.session.add(SystemConfig(key=PROXY_ACCOUNT_ID_KEY, value=str(acct_id)))
        db.session.commit()
    try:
        r = _patch(auth_client, {'proxy_eab_kid': 'kid-1', 'proxy_eab_hmac_key': 'aG1hYw'})
        assert r.status_code == 200, r.data
        with app.app_context():
            acct = db.session.get(AcmeClientAccount, acct_id)
            assert acct.eab_kid == 'kid-1' and acct.eab_hmac_key == 'aG1hYw'
            assert SystemConfig.query.filter(SystemConfig.key.in_(SHADOWS)).count() == 0
        data = auth_client.get('/api/v2/acme/client/settings').get_json()['data']
        assert data['proxy_eab_kid'] == 'kid-1' and data['proxy_eab_hmac_key_set'] is True
    finally:
        with app.app_context():
            AcmeClientAccount.query.filter_by(id=acct_id).delete()
            db.session.commit()
