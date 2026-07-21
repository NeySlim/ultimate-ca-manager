"""EST CA labels (RFC 7030 §3.2.2).

``/.well-known/est/<label>/<operation>`` selects a specific CA. Labels are
opt-in: only CAs listed in the ``est_labels`` setting are reachable, so the
feature never silently exposes every CA to EST enrollment. The unlabelled
paths keep serving the single configured EST CA.
"""
import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs7

from models import CA, db
from models.system_config import SystemConfig

from tests.test_est_rfc7030 import (  # reuse the EST harness
    EST_BASE, _basic_auth, _make_csr, _post_csr, _set_config, est_config,  # noqa: F401
)


@pytest.fixture(autouse=True)
def _est_on(app, est_config):
    """Guarantee EST is enabled for every test here.

    The suite shares one session-scoped database, and other EST modules own a
    module-scoped fixture that restores (i.e. removes) `est_enabled` on
    teardown — so relying on that alone makes these tests order-dependent.
    """
    with app.app_context():
        _set_config('est_enabled', 'true')
    yield


@pytest.fixture
def labelled_ca(app, create_ca, est_config):
    """A second CA reachable under the label 'secondary'."""
    ca_data = create_ca(cn='EST Labelled CA')
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        refid = ca.refid
        _set_config('est_labels', json.dumps({'secondary': refid}))
    yield {'refid': refid, 'data': ca_data}
    with app.app_context():
        row = SystemConfig.query.filter_by(key='est_labels').first()
        if row:
            db.session.delete(row)
            db.session.commit()


def _cacerts_subjects(response):
    """Subject CNs carried by a certs-only PKCS#7 response."""
    der = base64.b64decode(response.data)
    certs = pkcs7.load_der_pkcs7_certificates(der)
    return [
        c.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
        for c in certs
    ]


class TestLabelRouting:

    def test_unlabelled_cacerts_still_serves_default_ca(self, client, est_config):
        r = client.get(f'{EST_BASE}/cacerts')
        assert r.status_code == 200
        assert 'EST RFC 7030 CA' in _cacerts_subjects(r)

    def test_labelled_cacerts_serves_the_mapped_ca(self, client, labelled_ca):
        r = client.get(f'{EST_BASE}/secondary/cacerts')
        assert r.status_code == 200
        assert 'EST Labelled CA' in _cacerts_subjects(r)

    def test_unknown_label_is_not_served(self, client, labelled_ca):
        """An unmapped label must not silently fall back to the default CA."""
        r = client.get(f'{EST_BASE}/nope/cacerts')
        assert r.status_code == 404

    def test_labels_absent_by_default(self, client, est_config):
        """With no est_labels configured, no label resolves."""
        r = client.get(f'{EST_BASE}/secondary/cacerts')
        assert r.status_code == 404

    def test_csrattrs_available_under_a_label(self, client, labelled_ca):
        r = client.get(f'{EST_BASE}/secondary/csrattrs')
        assert r.status_code == 200


class TestLabelConfigHardening:

    def test_malformed_label_config_is_ignored(self, app, client, est_config):
        with app.app_context():
            _set_config('est_labels', '{not json')
        r = client.get(f'{EST_BASE}/secondary/cacerts')
        assert r.status_code == 404
        with app.app_context():
            row = SystemConfig.query.filter_by(key='est_labels').first()
            db.session.delete(row)
            db.session.commit()

    def test_invalid_label_names_are_dropped(self, app, client, est_config, create_ca):
        """Labels outside the safe charset never become routable."""
        ca_data = create_ca(cn='EST Bad Label CA')
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            _set_config('est_labels', json.dumps({
                'bad label': ca.refid,      # space
                'also/bad': ca.refid,       # path separator
                'good-one': ca.refid,       # valid
            }))
        assert client.get(f'{EST_BASE}/good-one/cacerts').status_code == 200
        assert client.get(f'{EST_BASE}/bad label/cacerts').status_code == 404
        with app.app_context():
            row = SystemConfig.query.filter_by(key='est_labels').first()
            db.session.delete(row)
            db.session.commit()

    def test_label_pointing_at_missing_ca_is_404(self, app, client, est_config):
        with app.app_context():
            _set_config('est_labels', json.dumps({'ghost': 'no-such-refid'}))
        r = client.get(f'{EST_BASE}/ghost/cacerts')
        assert r.status_code == 404
        with app.app_context():
            row = SystemConfig.query.filter_by(key='est_labels').first()
            db.session.delete(row)
            db.session.commit()

    def test_disabled_est_blocks_labelled_paths_too(self, app, client, labelled_ca):
        with app.app_context():
            _set_config('est_enabled', 'false')
        try:
            assert client.get(f'{EST_BASE}/secondary/cacerts').status_code == 503
        finally:
            with app.app_context():
                _set_config('est_enabled', 'true')


class TestLabelledEnrollment:

    def test_enroll_under_a_label_is_signed_by_that_ca(self, client, labelled_ca):
        csr, _key = _make_csr(common_name='labelled-device.example.test')
        r = _post_csr(client, 'secondary/simpleenroll', csr, headers=_basic_auth())
        assert r.status_code == 200, r.data[:300]

        issued = pkcs7.load_der_pkcs7_certificates(base64.b64decode(r.data))[0]
        issuer_cn = issued.issuer.get_attributes_for_oid(
            x509.oid.NameOID.COMMON_NAME)[0].value
        assert issuer_cn == 'EST Labelled CA'

    def test_enroll_under_unknown_label_is_refused(self, client, labelled_ca):
        csr, _key = _make_csr(common_name='ghost-device.example.test')
        r = _post_csr(client, 'unmapped/simpleenroll', csr, headers=_basic_auth())
        assert r.status_code == 404
