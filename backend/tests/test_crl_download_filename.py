"""Human-readable CRL Content-Disposition filename (#207)."""

import json
import os
import sys
from types import SimpleNamespace

from tests.conftest import assert_success

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.sanitize import crl_download_filename, slugify_filename_component

CONTENT_JSON = 'application/json'


def _post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


class TestSanitizeCrlFilename:
    def test_slugify_and_download_name(self):
        assert slugify_filename_component('My Root CA!') == 'My-Root-CA'
        ca = SimpleNamespace(descr='Corp Root CA', refid='abcdef12-9999')
        assert crl_download_filename(ca) == 'Corp-Root-CA-abcdef12.crl'
        assert (
            crl_download_filename(ca, delta=True)
            == 'Corp-Root-CA-abcdef12-delta.crl'
        )


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

        assert_success(auth_client.post(f'/api/v2/crl/{ca["id"]}/regenerate'))
        r = auth_client.get(f'/cdp/{refid}.crl')
        assert r.status_code == 200, r.data
        cd = r.headers.get('Content-Disposition', '')
        assert 'Slug-Filename-CA-' in cd
        assert refid[:8] in cd
        assert cd.endswith('.crl"') or '.crl"' in cd
