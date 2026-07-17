"""
Discussion #207 — CRL / cert UX gaps.

- Full CRL validity vs publish schedule + next_publish
- Configurable CRL signature digest
- Human-readable CRL Content-Disposition filename
- Template digest honored + template_id persisted + usage_count
- notBefore clock-skew backdate
- HTTP protocol port may be 80 (privileged)
"""
import base64
import json
import os
import sys
from datetime import timedelta
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes

from tests.conftest import assert_success, get_json
from utils.datetime_utils import DEFAULT_CERT_NOT_BEFORE_SKEW_MINUTES, cert_not_before, utc_now
from utils.sanitize import crl_download_filename, slugify_filename_component

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTENT_JSON = 'application/json'


def _post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


class TestSanitizeCrlFilename:
    def test_slugify_and_download_name(self):
        assert slugify_filename_component('My Root CA!') == 'My-Root-CA'
        ca = SimpleNamespace(descr='Corp Root CA', refid='abcdef12-9999')
        assert crl_download_filename(ca) == 'Corp-Root-CA-abcdef12.crl'
        assert crl_download_filename(ca, delta=True) == 'Corp-Root-CA-abcdef12-delta.crl'


class TestCertNotBeforeSkew:
    def test_default_skew_is_fifteen_minutes(self):
        before = utc_now()
        nb = cert_not_before()
        after = utc_now()
        assert nb <= after - timedelta(minutes=DEFAULT_CERT_NOT_BEFORE_SKEW_MINUTES - 1)
        assert nb >= before - timedelta(minutes=DEFAULT_CERT_NOT_BEFORE_SKEW_MINUTES + 1)


class TestCrlValidityPublishDigest:
    def test_config_and_next_publish(self, app, auth_client, create_ca):
        ca = create_ca(cn='CRL Config CA')
        ca_id = ca['id']

        r = auth_client.get(f'/api/v2/crl/{ca_id}/config')
        cfg = assert_success(r)
        assert cfg['crl_validity_days'] == 7
        assert cfg['crl_publish_interval_hours'] == 168
        assert cfg['crl_digest'] == 'sha256'

        r = _post_json(auth_client, f'/api/v2/crl/{ca_id}/config', {
            'crl_validity_days': 14,
            'crl_publish_interval_hours': 24,
            'crl_digest': 'sha384',
        })
        updated = assert_success(r)
        assert updated['crl_validity_days'] == 14
        assert updated['crl_publish_interval_hours'] == 24
        assert updated['crl_digest'] == 'sha384'

        with app.app_context():
            from models import CA, db
            row = db.session.get(CA, ca_id)
            row.cdp_enabled = True
            db.session.commit()

        r = auth_client.post(f'/api/v2/crl/{ca_id}/regenerate')
        meta = assert_success(r)
        assert meta.get('next_publish')
        assert meta.get('next_update')

        this_update = meta['this_update'].replace('Z', '')
        next_update = meta['next_update'].replace('Z', '')
        next_publish = meta['next_publish'].replace('Z', '')
        from datetime import datetime
        tu = datetime.fromisoformat(this_update)
        nu = datetime.fromisoformat(next_update)
        np = datetime.fromisoformat(next_publish)
        assert abs((nu - tu).days - 14) <= 1
        assert abs((np - tu).total_seconds() / 3600 - 24) < 1

        r = auth_client.get(f'/api/v2/crl/{ca_id}')
        data = assert_success(r)
        crl = x509.load_pem_x509_crl(data['crl_pem'].encode(), default_backend())
        assert isinstance(crl.signature_hash_algorithm, hashes.SHA384)

    def test_scheduler_uses_next_publish(self, app, auth_client, create_ca):
        ca = create_ca(cn='CRL Publish Due CA')
        ca_id = ca['id']
        with app.app_context():
            from models import CA, db
            row = db.session.get(CA, ca_id)
            row.cdp_enabled = True
            row.crl_validity_days = 30
            row.crl_publish_interval_hours = 1
            db.session.commit()

        assert_success(auth_client.post(f'/api/v2/crl/{ca_id}/regenerate'))

        with app.app_context():
            from models.crl import CRLMetadata
            from services.crl_scheduler_task import CRLSchedulerTask
            latest = CRLMetadata.query.filter_by(ca_id=ca_id, is_delta=False).order_by(
                CRLMetadata.crl_number.desc()
            ).first()
            latest.next_publish = utc_now() - timedelta(minutes=1)
            from models import db
            db.session.commit()
            should, reason = CRLSchedulerTask.should_regenerate_crl(ca_id)
            assert should is True
            assert 'publish due' in (reason or '').lower()


class TestCrlDownloadFilenameHeader:
    def test_cdp_content_disposition_uses_slug(self, app, auth_client, create_ca):
        ca = create_ca(cn='Slug Filename CA')
        with app.app_context():
            from models import CA, db
            row = db.session.get(CA, ca['id'])
            row.descr = 'Slug Filename CA'
            row.cdp_enabled = True
            db.session.commit()
            refid = row.refid

        assert_success(auth_client.post(f"/api/v2/crl/{ca['id']}/regenerate"))
        r = auth_client.get(f'/cdp/{refid}.crl')
        assert r.status_code == 200, r.data
        cd = r.headers.get('Content-Disposition', '')
        assert 'Slug-Filename-CA-' in cd
        assert refid[:8] in cd
        assert cd.endswith('.crl"') or '.crl"' in cd


class TestTemplateDigestAndUsage:
    def test_issue_honors_template_digest_and_counts_usage(self, app, auth_client, create_ca):
        ca = create_ca(cn='Template Digest CA')
        r = _post_json(auth_client, '/api/v2/templates', {
            'name': 'Digest SHA384 Template',
            'description': 'test',
            'template_type': 'web_server',
            'key_type': 'RSA-2048',
            'validity_days': 90,
            'digest': 'sha384',
            'dn_template': {'CN': '{hostname}'},
            'extensions_template': {
                'key_usage': ['digitalSignature', 'keyEncipherment'],
                'extended_key_usage': ['serverAuth'],
            },
        })
        tmpl = assert_success(r, status=201)

        r = _post_json(auth_client, '/api/v2/certificates', {
            'cn': 'tmpl-digest.example.test',
            'ca_id': ca['id'],
            'template_id': tmpl['id'],
            'validity_days': 30,
        })
        cert = assert_success(r, status=201)
        assert cert.get('template_id') == tmpl['id']

        with app.app_context():
            from models import Certificate, db
            row = db.session.get(Certificate, cert['id'])
            assert row.template_id == tmpl['id']
            pem = base64.b64decode(row.crt)
            x509_cert = x509.load_pem_x509_certificate(pem, default_backend())
            assert isinstance(x509_cert.signature_hash_algorithm, hashes.SHA384)
            # notBefore should be backdated (~15 min)
            nb = x509_cert.not_valid_before_utc.replace(tzinfo=None)
            assert nb < utc_now() - timedelta(minutes=5)

        r = auth_client.get(f"/api/v2/templates/{tmpl['id']}")
        listed = assert_success(r)
        assert listed.get('usage_count') == 1


class TestHttpProtocolPort80:
    def test_settings_accept_port_80(self, auth_client):
        r = auth_client.patch(
            '/api/v2/settings/general',
            data=json.dumps({'http_protocol_port': 80}),
            content_type=CONTENT_JSON,
        )
        assert r.status_code == 200, r.data

        r = auth_client.get('/api/v2/settings/general')
        assert r.status_code == 200, r.data
        data = get_json(r).get('data', get_json(r))
        assert int(data.get('http_protocol_port')) == 80

        r = auth_client.patch(
            '/api/v2/settings/general',
            data=json.dumps({'http_protocol_port': 8080}),
            content_type=CONTENT_JSON,
        )
        assert r.status_code == 200, r.data


class TestCrlConfigAuthGates:
    def test_config_requires_auth(self, client, create_ca, auth_client):
        ca = create_ca(cn='CRL Config Auth CA')
        r = client.get(f"/api/v2/crl/{ca['id']}/config")
        assert r.status_code == 401
        r = client.post(
            f"/api/v2/crl/{ca['id']}/config",
            data=json.dumps({'crl_digest': 'sha256'}),
            content_type=CONTENT_JSON,
        )
        assert r.status_code == 401
