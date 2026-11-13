"""HA on PostgreSQL: node A changes the keytab or the HTTPS certificate, node B follows.

Node B is a second applier on the same schema with files of its own; its restart is what
the gunicorn master then does before opening its TLS socket (boot_config.materialize_https).
"""
import io
import secrets
import time
from datetime import timedelta

import pytest

from config.settings import Config
from services import cluster_commands as cc
from services import shared_files
from services.kerberos import negotiate_auth
from tests import pg_app_harness
from tests.keytab_support import keytab
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')

PREFIX = f'sf-{secrets.token_hex(3)}-'
KEYTAB = keytab('HTTP/ucm.example.test@EXAMPLE.TEST')


def wait_for(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


@pytest.fixture
def node_b(app, monkeypatch):
    """HA mode, and node B's applier once started; commands and rows are dropped afterwards."""
    from models import ClusterCommand, db
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(cc, 'GAP_GRACE_SECONDS', 0.3)
    restarts = []
    made = []

    def start():
        applier = cc.CommandApplier(app, PREFIX + 'b', tick=0.05,
                                    started_at=utc_now() - timedelta(seconds=30),
                                    restart_action=lambda: restarts.append('b'))
        made.append(applier.start())
        return applier
    yield start, restarts
    for applier in made:
        applier.stop()
    with app.app_context():
        ClusterCommand.query.delete()
        shared_files.drop_file(shared_files.KERBEROS_KEYTAB)
        from tests.windows_profile_support import default_profile
        if default_profile() is not None:
            default_profile().keytab = None
        db.session.commit()


def test_a_keytab_uploaded_on_a_is_served_by_b_after_the_command(app, auth_client, node_b,
                                                                  tmp_path, monkeypatch):
    start, _restarts = node_b
    monkeypatch.setattr(negotiate_auth, 'inspect_keytab', lambda path=None: {
        'valid': True, 'principal': 'HTTP/ucm.example.test@EXAMPLE.TEST', 'error': None})
    monkeypatch.setattr(negotiate_auth, 'is_enabled', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'get_spn', lambda: 'HTTP/ucm.example.test@EXAMPLE.TEST')
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', tmp_path / 'a.keytab')
    r = auth_client.post('/api/v2/kerberos/keytab',
                         data={'file': (io.BytesIO(KEYTAB), 'ucm.keytab')},
                         content_type='multipart/form-data')
    assert r.status_code == 200, r.data

    on_b = tmp_path / 'b.keytab'
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', on_b)
    # The default profile is read from the database, and takes the SPN's realm
    with app.app_context():
        assert not negotiate_auth.is_configured()
    start()
    assert wait_for(lambda: on_b.exists() and on_b.read_bytes() == KEYTAB)
    with app.app_context():
        assert negotiate_auth.is_configured()


def test_keytabs_of_two_profiles_uploaded_on_a_compose_the_same_file_on_b(app, auth_client, node_b,
                                                                          tmp_path, monkeypatch):
    from models import WindowsEnrollmentProfile, db
    from services.kerberos.keytab_format import read_entries
    start, _restarts = node_b
    monkeypatch.setattr(negotiate_auth, '_gssapi_load', lambda target: ('HTTP/ucm.example.test', None))
    monkeypatch.setattr(negotiate_auth, 'get_spn', lambda: 'HTTP/ucm.example.test@EXAMPLE.TEST')
    on_a = tmp_path / 'a.keytab'
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', on_a)
    with app.app_context():
        other = WindowsEnrollmentProfile(name=PREFIX + 'two', realm='TWO.TEST', enabled=True)
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    try:
        assert _upload_keytab(auth_client, KEYTAB).status_code == 200
        r = _upload_keytab(auth_client, keytab('HTTP/ucm.example.test@TWO.TEST'), other_id)
        assert r.status_code == 200, r.data
        assert {e.realm for e in read_entries(on_a.read_bytes())} == {'EXAMPLE.TEST', 'TWO.TEST'}
        on_b = tmp_path / 'b.keytab'
        monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', on_b)
        start()
        assert wait_for(lambda: on_b.exists() and on_b.read_bytes() == on_a.read_bytes())
    finally:
        with app.app_context():
            WindowsEnrollmentProfile.query.filter_by(id=other_id).delete()
            db.session.commit()


def _upload_keytab(client, data, profile_id=None):
    form = {'file': (io.BytesIO(data), 'ucm.keytab')}
    if profile_id is not None:
        form['profile_id'] = str(profile_id)
    return client.post('/api/v2/kerberos/keytab', data=form, content_type='multipart/form-data')


def test_a_certificate_applied_on_a_restarts_b_which_then_serves_it(
        app, auth_client, node_b, create_cert, tmp_path, monkeypatch):
    import base64
    from boot_config import materialize_https
    from models import Certificate, ClusterCommand, db
    from services.https_binding import set_bound_refid
    start, restarts = node_b
    monkeypatch.setenv('HTTPS_CERT_PATH', str(tmp_path / 'a_cert.pem'))
    monkeypatch.setenv('HTTPS_KEY_PATH', str(tmp_path / 'a_key.pem'))
    cert = create_cert(cn='ha-https.example.test')
    try:
        r = auth_client.post('/api/v2/system/https/apply', json={'cert_id': cert['id']})
        assert r.status_code == 200, r.data
        with app.app_context():
            assert [c.kind for c in ClusterCommand.query.all()] == [cc.RESTART]
            row = db.session.get(Certificate, cert['id'])
            leaf = base64.b64decode(row.crt).decode()

        start()
        assert wait_for(lambda: restarts == ['b'])
        # Node B starting again: its master writes the pair the database names
        monkeypatch.setenv('DATABASE_URL', pg_app_harness.app_url())
        b_cert, b_key = tmp_path / 'b_cert.pem', tmp_path / 'b_key.pem'
        assert materialize_https(str(tmp_path), b_cert, b_key).endswith('from the database')
        assert b_cert.read_text().startswith(leaf)
        assert b_cert.read_text() == (tmp_path / 'a_cert.pem').read_text()
        assert b_key.read_text() == (tmp_path / 'a_key.pem').read_text()
    finally:
        with app.app_context():
            set_bound_refid('')
