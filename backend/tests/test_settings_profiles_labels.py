"""Administration APIs for ACME profiles and EST CA labels.

Both features are opt-in and were previously only settable by writing
SystemConfig directly; these endpoints make them manageable from the UI.
"""
import json

import pytest

from models import CA, SystemConfig, db
from services.acme import profiles as acme_profiles


def patch_json(client, url, payload):
    return client.patch(url, data=json.dumps(payload),
                        content_type='application/json')


@pytest.fixture(autouse=True)
def _clean_config(app):
    yield
    with app.app_context():
        for key in (acme_profiles.CONFIG_KEY, 'est_labels'):
            row = SystemConfig.query.filter_by(key=key).first()
            if row:
                db.session.delete(row)
        db.session.commit()


class TestAcmeProfilesSettings:
    URL = '/api/v2/acme/settings'

    def test_profiles_empty_by_default(self, auth_client):
        body = auth_client.get(self.URL).get_json()['data']
        assert body['profiles'] == {}

    def test_round_trip(self, auth_client):
        r = patch_json(auth_client, self.URL, {'profiles': {
            'short': {'description': '7-day', 'validity_days': 7, 'digest': 'sha384'},
        }})
        assert r.status_code == 200, r.data

        body = auth_client.get(self.URL).get_json()['data']
        assert body['profiles']['short'] == {
            'description': '7-day', 'validity_days': 7, 'digest': 'sha384',
        }

    def test_defaults_are_filled_in_on_read(self, auth_client):
        """A profile with only a description reads back with usable defaults."""
        patch_json(auth_client, self.URL, {'profiles': {'bare': {}}})
        profile = auth_client.get(self.URL).get_json()['data']['profiles']['bare']
        assert profile['validity_days'] == 90
        assert profile['digest'] == 'sha256'
        assert profile['description'] == 'bare'

    @pytest.mark.parametrize('payload,fragment', [
        ({'nope': {'validity_days': 0}}, 'validity_days'),
        ({'nope': {'validity_days': 99999}}, 'validity_days'),
        ({'nope': {'digest': 'md5'}}, 'digest'),
        ({'nope': 'not-an-object'}, 'must be an object'),
        ({'x' * 80: {}}, 'too long'),
    ])
    def test_invalid_profiles_are_rejected(self, auth_client, payload, fragment):
        r = patch_json(auth_client, self.URL, {'profiles': payload})
        assert r.status_code == 400
        assert fragment in r.get_json()['message']

    def test_rejected_config_is_not_persisted(self, auth_client):
        patch_json(auth_client, self.URL, {'profiles': {'good': {'validity_days': 30}}})
        patch_json(auth_client, self.URL, {'profiles': {'bad': {'digest': 'md5'}}})
        profiles = auth_client.get(self.URL).get_json()['data']['profiles']
        assert 'good' in profiles and 'bad' not in profiles

    def test_clearing_profiles(self, auth_client):
        patch_json(auth_client, self.URL, {'profiles': {'x': {}}})
        patch_json(auth_client, self.URL, {'profiles': {}})
        assert auth_client.get(self.URL).get_json()['data']['profiles'] == {}

    def test_requires_write_permission(self, client):
        assert patch_json(client, self.URL, {'profiles': {}}).status_code in (401, 403)


class TestEstLabelsSettings:
    URL = '/api/v2/est/config'

    def test_labels_empty_by_default(self, auth_client):
        body = auth_client.get(self.URL).get_json()['data']
        assert body['labels'] == {}

    def test_round_trip_reports_ca_name(self, app, auth_client, create_ca):
        ca_data = create_ca(cn='EST Label Settings CA')
        with app.app_context():
            refid = db.session.get(CA, ca_data['id']).refid

        r = patch_json(auth_client, self.URL, {'labels': {'branch': refid}})
        assert r.status_code == 200, r.data

        labels = auth_client.get(self.URL).get_json()['data']['labels']
        assert labels['branch']['ca_refid'] == refid
        assert labels['branch']['ca_name'] == 'EST Label Settings CA'

    def test_accepts_the_enriched_shape_it_returns(self, app, auth_client, create_ca):
        """A client can PATCH back exactly what GET gave it."""
        ca_data = create_ca(cn='EST Roundtrip CA')
        with app.app_context():
            refid = db.session.get(CA, ca_data['id']).refid
        patch_json(auth_client, self.URL, {'labels': {'a': refid}})
        read_back = auth_client.get(self.URL).get_json()['data']['labels']

        r = patch_json(auth_client, self.URL, {'labels': read_back})
        assert r.status_code == 200
        assert auth_client.get(self.URL).get_json()['data']['labels']['a']['ca_refid'] == refid

    @pytest.mark.parametrize('idx,label', list(enumerate(
        ['bad label', 'has/slash', '', 'x' * 80]
    )))
    def test_invalid_label_names_rejected(self, app, auth_client, create_ca, idx, label):
        # CN is derived from the index, not the label: some labels under test
        # contain characters a CA common name legitimately refuses.
        ca_data = create_ca(cn=f'EST Bad Label CA {idx}')
        with app.app_context():
            refid = db.session.get(CA, ca_data['id']).refid
        r = patch_json(auth_client, self.URL, {'labels': {label: refid}})
        assert r.status_code == 400

    def test_unknown_ca_is_rejected(self, auth_client):
        r = patch_json(auth_client, self.URL, {'labels': {'ghost': 'no-such-refid'}})
        assert r.status_code == 404
        assert 'CA not found' in r.get_json()['message']

    def test_label_without_ca_is_rejected(self, auth_client):
        r = patch_json(auth_client, self.URL, {'labels': {'empty': ''}})
        assert r.status_code == 400

    def test_clearing_labels(self, app, auth_client, create_ca):
        ca_data = create_ca(cn='EST Clear Labels CA')
        with app.app_context():
            refid = db.session.get(CA, ca_data['id']).refid
        patch_json(auth_client, self.URL, {'labels': {'gone': refid}})
        patch_json(auth_client, self.URL, {'labels': {}})
        assert auth_client.get(self.URL).get_json()['data']['labels'] == {}

    def test_requires_write_permission(self, client):
        assert patch_json(client, self.URL, {'labels': {}}).status_code in (401, 403)
