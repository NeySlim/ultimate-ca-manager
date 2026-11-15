"""Claims in docs/API_REFERENCE.md checked against the application."""
import json
import os

_REF = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'docs', 'API_REFERENCE.md')


def _doc():
    with open(_REF, encoding='utf-8') as fh:
        return fh.read()


def test_protocol_routes_are_registered_and_the_doc_says_so(app):
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert '/tsa' in rules
    assert any(r.startswith('/.well-known/est') for r in rules)
    assert 'is not registered' not in _doc()


def test_rate_limit_switch_turns_off_both_limiters_in_the_doc():
    doc = _doc()
    assert 'Fixed in code' not in doc
    assert 'turns off both limiters' in doc


def test_mtls_list_routes_accept_api_keys_and_the_doc_says_so(auth_client, app):
    r = auth_client.post('/api/v2/account/apikeys',
                         data=json.dumps({'name': 'mtls-doc',
                                          'permissions': ['read:certificates']}),
                         content_type='application/json')
    key = r.get_json()['data']['key']
    c = app.test_client()
    for path in ('/api/v2/mtls/certificates', '/api/v2/mtls/available-certificates'):
        assert c.get(path, headers={'X-API-Key': key}).status_code != 403, path
    assert ('Except for the two settings routes and the two GET lists '
            '(certificates, available-certificates)') in _doc()
