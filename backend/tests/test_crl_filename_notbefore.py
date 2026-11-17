"""Tests for discussion #207 points 3 and 4.

3. CDP download filename is readable ({slug}-{refid8}.crl) — URLs unchanged.
4. Issued certificates backdate notBefore by a fixed clock-skew offset.
"""
import base64
import json
import re
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.backends import default_backend

from tests.conftest import get_json

CONTENT_JSON = 'application/json'


class TestCrlDownloadFilename:

    def test_cdp_filename_readable(self, auth_client, client, create_ca):
        ca = create_ca(cn='Filename Test CA')
        r = auth_client.post(f"/api/v2/crl/{ca['id']}/regenerate")
        assert r.status_code == 200, r.data

        refid = get_json(auth_client.get(f"/api/v2/cas/{ca['id']}"))['data']['refid']
        r = client.get(f'/cdp/{refid}.crl')  # URL keeps the refid
        assert r.status_code == 200
        disposition = r.headers['Content-Disposition']
        m = re.search(r'filename="([^"]+)"', disposition)
        assert m, disposition
        filename = m.group(1)
        assert filename.endswith('.crl')
        assert 'filename-test-ca' in filename
        assert refid[:8] in filename

    def test_filename_helper_sanitizes(self):
        from utils.sanitize import crl_download_filename

        class FakeCA:
            descr = 'Wéird/CA "name"\r\n<script>'
            refid = 'abcd1234-rest'

        name = crl_download_filename(FakeCA())
        assert name.endswith('-abcd1234.crl')
        assert '/' not in name and '"' not in name and '\r' not in name

        delta = crl_download_filename(FakeCA(), delta=True)
        assert delta.endswith('-abcd1234-delta.crl')


class TestNotBeforeSkew:

    def _load_cert(self, app, cert_id):
        with app.app_context():
            from models import Certificate, db
            row = db.session.get(Certificate, cert_id)
            pem = base64.b64decode(row.crt)
        return x509.load_pem_x509_certificate(pem, default_backend())

    def test_issued_cert_backdated(self, app, auth_client, create_ca):
        from utils.datetime_utils import utc_now, CERT_NOT_BEFORE_SKEW

        ca = create_ca(cn='Skew CA')
        r = auth_client.post('/api/v2/certificates', data=json.dumps({
            'cn': 'skew.test', 'ca_id': ca['id'], 'key_type': 'rsa',
            'key_size': 2048, 'validity_days': 90,
        }), content_type=CONTENT_JSON)
        assert r.status_code in (200, 201), r.data
        cert = self._load_cert(app, get_json(r)['data']['id'])

        now = utc_now()
        not_before = cert.not_valid_before_utc.replace(tzinfo=None)
        backdate = now - not_before
        # ~15 minutes back, with a minute of test tolerance either side
        assert CERT_NOT_BEFORE_SKEW - timedelta(minutes=1) <= backdate
        assert backdate <= CERT_NOT_BEFORE_SKEW + timedelta(minutes=1)

        # notAfter stays anchored on now + validity (backdating must not
        # extend the total lifetime past the requested window)
        not_after = cert.not_valid_after_utc.replace(tzinfo=None)
        assert not_after <= now + timedelta(days=90, minutes=1)
