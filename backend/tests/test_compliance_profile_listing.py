"""GET /api/v2/system/compliance-profiles: what each profile leaves a form to offer."""
import compliance_profiles

URL = '/api/v2/system/compliance-profiles'


def _by_name(client):
    r = client.get(URL)
    assert r.status_code == 200, r.data
    return {p['name']: p for p in r.get_json()['data']}


def test_lists_every_profile_with_its_reference(auth_client):
    profiles = _by_name(auth_client)
    assert set(profiles) == set(compliance_profiles.PROFILE_NAMES)
    for name, entry in profiles.items():
        assert entry['reference'] == compliance_profiles.PROFILES[name]['reference']
        assert entry['title'] == compliance_profiles.PROFILES[name]['title']


def test_bsi_leaves_pss_and_strong_keys_only(auth_client):
    bsi = _by_name(auth_client)['bsi']
    assert bsi['allowed_signature_schemes'] == ['rsa_pss', 'ecdsa']
    assert 'RSA-2048' not in bsi['allowed_key_types']
    assert 'RSA-3072' in bsi['allowed_key_types']
    assert bsi['require_hsm_ca_key'] is False


def test_eu_acm_requires_an_hsm_key_and_dates_rsa_2048(auth_client):
    acm = _by_name(auth_client)['eu-acm']
    assert acm['require_hsm_ca_key'] is True
    assert acm['key_type_horizons'] == {'RSA-2048': '2028-12-31'}
    assert acm['key_type_issue_until'] == {'RSA-2048': '2026-12-31'}


def test_digests_come_weakest_first(auth_client):
    assert _by_name(auth_client)['anssi']['allowed_digests'] == ['sha256', 'sha384', 'sha512']


def test_a_signed_in_user_without_admin_rights_can_read_it(app, create_user):
    import json
    create_user(username='viewer_profiles', role='viewer')
    client = app.test_client()
    client.post('/api/v2/auth/login',
                data=json.dumps({'username': 'viewer_profiles', 'password': 'TestPass123!'}),
                content_type='application/json')
    assert client.get(URL).status_code == 200


def test_anonymous_is_refused(client):
    assert client.get(URL).status_code in (401, 403)
