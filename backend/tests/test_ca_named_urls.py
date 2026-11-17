"""Tests for opt-in named protocol URLs (discussion #207, migration 060).

A CA created with namedUrls=true gets an immutable unique slug; CDP/AIA
resolve by slug AND refid; embedded URLs use the slug; default stays refid.
"""
import base64
import json

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID

from tests.conftest import get_json

CONTENT_JSON = 'application/json'


def _create_ca(auth_client, cn, **extra):
    data = {
        'type': 'root', 'commonName': cn, 'organization': 'Test Org',
        'country': 'US', 'state': 'CA', 'locality': 'Test City',
        'keyType': 'RSA', 'keySize': 2048, 'validityYears': 10,
        'hashAlgorithm': 'sha256',
    }
    data.update(extra)
    r = auth_client.post('/api/v2/cas', data=json.dumps(data),
                         content_type=CONTENT_JSON)
    assert r.status_code in (200, 201), r.data
    body = get_json(r)
    return body.get('data', body)


class TestNamedUrlSlug:

    def test_slug_generated_when_opted_in(self, auth_client):
        ca = _create_ca(auth_client, 'Named Urls Root CA', namedUrls=True)
        assert ca['url_slug'] == 'named-urls-root-ca'

    def test_no_slug_by_default(self, auth_client):
        ca = _create_ca(auth_client, 'Refid Only CA')
        assert ca['url_slug'] is None

    def test_slug_collision_suffixed(self, auth_client):
        ca1 = _create_ca(auth_client, 'Twin Named CA', namedUrls=True)
        ca2 = _create_ca(auth_client, 'Twin-Named CA', namedUrls=True)
        assert ca1['url_slug'] == 'twin-named-ca'
        assert ca2['url_slug'] == 'twin-named-ca-2'

    def test_delta_suffix_reserved(self, auth_client):
        ca = _create_ca(auth_client, 'Weird Delta', namedUrls=True)
        assert not ca['url_slug'].endswith('-delta')


class TestNamedUrlResolution:

    def test_cdp_resolves_by_slug_and_refid(self, auth_client, client):
        ca = _create_ca(auth_client, 'Slug CDP CA', namedUrls=True)
        r = auth_client.post(f"/api/v2/crl/{ca['id']}/regenerate")
        assert r.status_code == 200, r.data

        by_slug = client.get(f"/cdp/{ca['url_slug']}.crl")
        by_refid = client.get(f"/cdp/{ca['refid']}.crl")
        assert by_slug.status_code == 200
        assert by_refid.status_code == 200
        assert by_slug.data == by_refid.data

    def test_aia_resolves_by_slug(self, auth_client, client):
        ca = _create_ca(auth_client, 'Slug AIA CA', namedUrls=True)
        r = client.get(f"/ca/{ca['url_slug']}.pem")
        if r.status_code == 404:
            r = client.get(f"/aia/{ca['url_slug']}.pem")
        assert r.status_code == 200, r.status_code


class TestNamedUrlEmbedded:

    def _issued_cdp_uris(self, app, cert_id):
        with app.app_context():
            from models import Certificate, db
            row = db.session.get(Certificate, cert_id)
            cert = x509.load_pem_x509_certificate(
                base64.b64decode(row.crt), default_backend())
        try:
            ext = cert.extensions.get_extension_for_oid(
                ExtensionOID.CRL_DISTRIBUTION_POINTS)
        except x509.ExtensionNotFound:
            return []
        uris = []
        for dp in ext.value:
            for name in (dp.full_name or []):
                uris.append(name.value)
        return uris

    def test_issued_cert_embeds_slug_url(self, app, auth_client, client):
        ca = _create_ca(auth_client, 'Slug Embed CA', namedUrls=True)
        r = auth_client.post(f"/api/v2/crl/{ca['id']}/auto-regen",
                             data=json.dumps({'enabled': True}),
                             content_type=CONTENT_JSON)
        assert r.status_code == 200, r.data

        r = auth_client.post('/api/v2/certificates', data=json.dumps({
            'cn': 'slug-embed.test', 'ca_id': ca['id'], 'key_type': 'rsa',
            'key_size': 2048, 'validity_days': 90,
        }), content_type=CONTENT_JSON)
        assert r.status_code in (200, 201), r.data

        uris = self._issued_cdp_uris(app, get_json(r)['data']['id'])
        assert uris, 'expected a CDP URI in the issued certificate'
        assert any(ca['url_slug'] in u for u in uris), uris
        assert all(ca['refid'] not in u for u in uris), uris


class TestNamedUrlRetrofit:
    """Post-creation opt-in on an existing CA (discussion #207 follow-up)."""

    def _patch(self, auth_client, ca_id, payload):
        return auth_client.patch(f"/api/v2/cas/{ca_id}",
                                 data=json.dumps(payload),
                                 content_type=CONTENT_JSON)

    def test_enable_on_existing_ca(self, auth_client):
        ca = _create_ca(auth_client, 'Retrofit Plain CA')
        assert ca['url_slug'] is None
        r = self._patch(auth_client, ca['id'], {'namedUrls': True})
        assert r.status_code == 200, r.data
        updated = get_json(r)['data']
        assert updated['url_slug'] == 'retrofit-plain-ca'

    def test_enable_rematerializes_default_urls(self, auth_client):
        ca = _create_ca(auth_client, 'Retrofit Urls CA')
        refid, custom = ca['refid'], 'http://pki.example.com/custom.crl'
        r = self._patch(auth_client, ca['id'], {
            'cdp_urls': [f"http://pki.example.com/cdp/{refid}.crl", custom],
            'aia_ca_issuers_urls': [f"http://pki.example.com/ca/{refid}.cer"],
        })
        assert r.status_code == 200, r.data
        r = self._patch(auth_client, ca['id'], {'namedUrls': True})
        assert r.status_code == 200, r.data
        updated = get_json(r)['data']
        slug = updated['url_slug']
        assert updated['cdp_urls'] == [f"http://pki.example.com/cdp/{slug}.crl", custom]
        assert updated['aia_ca_issuers_urls'] == [f"http://pki.example.com/ca/{slug}.cer"]

    def test_enable_is_idempotent(self, auth_client):
        ca = _create_ca(auth_client, 'Retrofit Twice CA', namedUrls=True)
        r = self._patch(auth_client, ca['id'], {'namedUrls': True})
        assert r.status_code == 200, r.data
        assert get_json(r)['data']['url_slug'] == ca['url_slug']

    def test_cannot_disable_once_enabled(self, auth_client):
        ca = _create_ca(auth_client, 'Retrofit Locked CA', namedUrls=True)
        r = self._patch(auth_client, ca['id'], {'namedUrls': False})
        assert r.status_code == 400

    def test_disable_noop_when_never_enabled(self, auth_client):
        ca = _create_ca(auth_client, 'Retrofit Never CA')
        r = self._patch(auth_client, ca['id'], {'namedUrls': False})
        assert r.status_code == 200, r.data
        assert get_json(r)['data']['url_slug'] is None

    def test_cdp_resolves_by_slug_after_retrofit(self, auth_client, client):
        ca = _create_ca(auth_client, 'Retrofit Resolve CA')
        r = self._patch(auth_client, ca['id'], {'namedUrls': True})
        assert r.status_code == 200, r.data
        slug = get_json(r)['data']['url_slug']
        r = auth_client.post(f"/api/v2/crl/{ca['id']}/regenerate")
        assert r.status_code == 200, r.data
        by_slug = client.get(f"/cdp/{slug}.crl")
        by_refid = client.get(f"/cdp/{ca['refid']}.crl")
        assert by_slug.status_code == 200
        assert by_slug.data == by_refid.data
