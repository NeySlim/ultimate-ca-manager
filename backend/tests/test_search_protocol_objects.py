"""The global search finds ACME accounts and SCEP profiles, as the mockup's palette does (app.js
moduleSearch), each to the readers of its protocol only."""
import json
import uuid

import pytest

from models import CA, db
from models.acme_models import AcmeAccount
from models.scep import ScepProfile

pytestmark = pytest.mark.usefixtures('drop_new_users', 'drop_new_cas_and_certificates')


@pytest.fixture
def objects(app, create_ca):
    ca = create_ca(cn='Palette Search CA')
    with app.app_context():
        refid = db.session.get(CA, ca['id']).refid
        account = AcmeAccount(contact=json.dumps(['mailto:pal_acme@example.com']), jwk='{}',
                              jwk_thumbprint=uuid.uuid4().hex)
        decoy = AcmeAccount(contact=json.dumps(['mailto:palXacme@example.com']), jwk='{}',
                            jwk_thumbprint=uuid.uuid4().hex)
        bare = AcmeAccount(account_id='pal_bare_' + uuid.uuid4().hex[:8], jwk='{}',
                           jwk_thumbprint=uuid.uuid4().hex)
        profile = ScepProfile(name='Pal_scep devices', url_slug='pal-devices', ca_refid=refid,
                              description='phones of the palette test')
        db.session.add_all([account, decoy, bare, profile])
        db.session.commit()
        made = {'account': account.id, 'decoy': decoy.id, 'bare': bare.id,
                'bare_name': bare.account_id, 'profile': profile.id}
    yield made
    with app.app_context():
        AcmeAccount.query.filter(AcmeAccount.id.in_([made['account'], made['decoy'], made['bare']])).delete(
            synchronize_session=False)
        ScepProfile.query.filter_by(id=made['profile']).delete(synchronize_session=False)
        db.session.commit()


def _search(client, q):
    r = client.get(f'/api/v2/search?q={q}&limit=20')
    assert r.status_code == 200
    return r.get_json()['data']


def test_acme_account_found_by_contact_named_by_it(auth_client, objects):
    got = _search(auth_client, 'pal_acme')['acme_accounts']
    # `_` is a literal, the decoy palXacme is not a match
    assert [(a['id'], a['name'], a['type']) for a in got] == [(objects['account'], 'pal_acme@example.com', 'acme_account')]


def test_acme_account_without_contact_found_and_named_by_its_id(auth_client, objects):
    got = _search(auth_client, 'pal_bare_')['acme_accounts']
    assert [(a['id'], a['name']) for a in got] == [(objects['bare'], objects['bare_name'])]


def test_scep_profile_found_by_name_slug_or_description(auth_client, objects):
    for q in ('Pal_scep', 'pal-devices', 'palette test'):
        got = _search(auth_client, q)['scep_profiles']
        assert [(p['id'], p['name'], p['url_slug'], p['type']) for p in got] == [
            (objects['profile'], 'Pal_scep devices', 'pal-devices', 'scep_profile')], q


def test_protocol_objects_hidden_without_their_read_permission(viewer_client, objects):
    """The viewer role holds neither read:acme nor read:scep: no account, no profile."""
    data = _search(viewer_client, 'pal')
    assert data['acme_accounts'] == []
    assert data['scep_profiles'] == []


def test_short_query_lists_the_new_groups_empty(auth_client):
    data = _search(auth_client, 'p')
    assert data['acme_accounts'] == [] and data['scep_profiles'] == []
