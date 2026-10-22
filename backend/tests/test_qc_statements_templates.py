"""Template API: qc_statements and certificate_policies are validated and
survive create, update, clone, export and import."""
import io
import json
import itertools

from tests.conftest import get_json

_SEQ = itertools.count(1)
QC = {'compliance': True, 'type': 'esign',
      'pds': [{'url': 'https://pki.example.test/pds.pdf', 'language': 'en'}]}


def _payload(ext, **over):
    data = {'name': f'qc-api-{next(_SEQ)}', 'template_type': 'custom', 'key_type': 'RSA-2048',
            'validity_days': 90, 'digest': 'sha256', 'extensions_template': ext}
    data.update(over)
    return data


def _create(client, ext, **over):
    return client.post('/api/v2/templates', json=_payload(ext, **over))


class TestCreate:
    def test_valid_is_stored_as_sent(self, auth_client):
        r = _create(auth_client, {'qc_statements': QC, 'certificate_policies': ['0.4.0.194112.1.2']})
        assert r.status_code in (200, 201), r.get_json()
        ext = get_json(r)['data']['extensions_template']
        assert ext['qc_statements'] == QC
        assert ext['certificate_policies'] == ['0.4.0.194112.1.2']

    def test_unknown_qc_key_is_refused(self, auth_client):
        r = _create(auth_client, {'qc_statements': {**QC, 'qc_ident_method': True}})
        assert r.status_code == 400
        assert 'qc_ident_method' in r.get_json()['message']

    def test_non_eu_qualified_template_is_accepted(self, auth_client):
        r = _create(auth_client, {'qc_statements': {'compliance': True, 'cc_legislation': ['CH']}})
        assert r.status_code == 201, r.get_json()

    def test_bad_oid_is_refused(self, auth_client):
        r = _create(auth_client, {'certificate_policies': ['not-an-oid']})
        assert r.status_code == 400
        assert 'not-an-oid' in r.get_json()['message']

    def test_eu_qualified_pds_without_english_is_refused(self, auth_client):
        r = _create(auth_client, {'qc_statements': {
            'compliance': True, 'pds': [{'url': 'https://x.test/p', 'language': 'fr'}]}})
        assert r.status_code == 400
        assert 'English' in r.get_json()['message']

    def test_json_string_extensions_are_validated_too(self, auth_client):
        r = _create(auth_client, json.dumps({'qc_statements': {'type': 'nope'}}))
        assert r.status_code == 400


class TestUpdateCloneExport:
    def test_update_validates(self, auth_client):
        tpl = get_json(_create(auth_client, {'qc_statements': QC}))['data']
        r = auth_client.put(f"/api/v2/templates/{tpl['id']}",
                            json={'extensions_template': {'qc_statements': {'type': 'nope'}}})
        assert r.status_code == 400
        r = auth_client.put(f"/api/v2/templates/{tpl['id']}",
                            json={'extensions_template': {'qc_statements': {**QC, 'type': 'eseal'}}})
        assert r.status_code == 200, r.get_json()
        assert get_json(r)['data']['extensions_template']['qc_statements']['type'] == 'eseal'

    def test_export_then_import_roundtrip(self, auth_client):
        tpl = get_json(_create(auth_client, {'qc_statements': QC,
                                             'certificate_policies': ['0.4.0.194112.1.0']}))['data']
        exported = auth_client.get(f"/api/v2/templates/{tpl['id']}/export")
        assert exported.status_code == 200
        body = json.loads(exported.data)
        assert auth_client.delete(f"/api/v2/templates/{tpl['id']}").status_code in (200, 204)
        r = auth_client.post('/api/v2/templates/import',
                             data={'json_content': json.dumps(body)})
        assert r.status_code == 200, r.get_json()
        listed = auth_client.get('/api/v2/templates', query_string={'search': tpl['name']})
        ext = get_json(listed)['data'][0]['extensions_template']
        assert ext['qc_statements'] == QC
        assert ext['certificate_policies'] == ['0.4.0.194112.1.0']

    def test_import_skips_an_invalid_template_and_says_why(self, auth_client):
        bad = _payload({'qc_statements': {'type': 'nope'}})
        r = auth_client.post('/api/v2/templates/import', data={'json_content': json.dumps([bad])})
        assert r.status_code == 200, r.get_json()
        assert bad['name'] in json.dumps(get_json(r))
        listed = auth_client.get('/api/v2/templates', query_string={'search': bad['name']})
        assert get_json(listed)['data'] == []

    def test_clone_keeps_the_qualification(self, auth_client):
        tpl = get_json(_create(auth_client, {'qc_statements': QC}))['data']
        r = auth_client.post(f"/api/v2/templates/{tpl['id']}/duplicate",
                             json={'name': f'qc-clone-{next(_SEQ)}'})
        assert r.status_code in (200, 201), r.get_json()
        assert get_json(r)['data']['extensions_template']['qc_statements'] == QC
