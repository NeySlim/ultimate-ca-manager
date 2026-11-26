"""The public KRL of an SSH CA (issue #451): /ssh/krl/<refid>, without authentication, keeps
its version until the revocations change, answers 304 to a matching If-None-Match, takes a
revocation at once and serves what the database holds, so every HA node serves the same KRL."""
import shutil
import subprocess

import pytest

from models import db
from models.ssh import SSHKRL, SSHCertificateAuthority
from services.ssh_krl_service import SSHKRLService
import services.ssh_krl_service as krl_service
from tests.test_ssh import _create_ssh_ca, _generate_test_ssh_key, post_json
from tests.ssh_cleanup import ssh_rows_stay_in_their_module  # noqa: F401

pytestmark = pytest.mark.skipif(not shutil.which('ssh-keygen'), reason='ssh-keygen not available')


def _issue(auth_client, ca, name='alice'):
    r = post_json(auth_client, '/api/v2/ssh/certificates', {
        'ca_id': ca['id'], 'public_key': _generate_test_ssh_key(), 'cert_type': 'user',
        'principals': [name], 'validity_seconds': 3600})
    assert r.status_code == 201, r.data
    return r.get_json()['data']


def _revoke(auth_client, cert):
    r = post_json(auth_client, f"/api/v2/ssh/certificates/{cert['id']}/revoke", {'reason': 'key_compromise'})
    assert r.status_code == 200, r.data


def _revoked(tmp_path, krl, certificate):
    krl_path, cert_path = tmp_path / 'krl', tmp_path / 'c-cert.pub'
    krl_path.write_bytes(krl)
    cert_path.write_text(certificate)
    out = subprocess.run(['ssh-keygen', '-Q', '-f', str(krl_path), str(cert_path)],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode in (0, 1), out.stderr
    return out.returncode == 1


def _krl_version(tmp_path, krl):
    path = tmp_path / 'v.krl'
    path.write_bytes(krl)
    out = subprocess.run(['ssh-keygen', '-Q', '-l', '-f', str(path)], capture_output=True, text=True, timeout=30)
    return int(next(line for line in out.stdout.splitlines() if line.startswith('# KRL version')).split()[-1])


class TestThePublicKrl:
    def test_an_unknown_ca_is_404(self, client):
        assert client.get('/ssh/krl/no-such-ca').status_code == 404

    def test_it_needs_no_session_and_carries_its_version(self, app, auth_client, tmp_path):
        ca = _create_ssh_ca(auth_client, descr='Public KRL CA')
        r = app.test_client().get(f"/ssh/krl/{ca['refid']}")
        assert r.status_code == 200
        assert r.mimetype == 'application/octet-stream'
        version = _krl_version(tmp_path, r.data)
        assert r.headers['ETag'] == f'"{version}"'
        assert r.headers['X-KRL-Version'] == str(version)
        assert r.headers['Cache-Control'] == 'public, no-cache'
        assert r.headers['Last-Modified'].endswith('GMT')

    def test_the_version_stays_while_nothing_changes(self, app, auth_client, monkeypatch):
        ca = _create_ssh_ca(auth_client, descr='Stable KRL CA')
        client = app.test_client()
        first = client.get(f"/ssh/krl/{ca['refid']}")
        calls = []
        real = SSHKRLService.generate_krl
        monkeypatch.setattr(SSHKRLService, 'generate_krl', staticmethod(
            lambda *a, **k: calls.append(a) or real(*a, **k)))
        second = client.get(f"/ssh/krl/{ca['refid']}")
        assert second.headers['ETag'] == first.headers['ETag']
        assert second.data == first.data
        assert calls == []

    def test_a_matching_etag_is_304_without_a_body(self, app, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Conditional KRL CA')
        client = app.test_client()
        etag = client.get(f"/ssh/krl/{ca['refid']}").headers['ETag']
        for header in (etag, f'W/{etag}', f'"1", {etag}', '*'):
            r = client.get(f"/ssh/krl/{ca['refid']}", headers={'If-None-Match': header})
            assert r.status_code == 304, header
            assert r.data == b''
            assert r.headers['ETag'] == etag
        assert client.get(f"/ssh/krl/{ca['refid']}", headers={'If-None-Match': '"1"'}).status_code == 200

    def test_a_revocation_is_published_at_once_with_a_higher_version(self, app, auth_client, tmp_path):
        ca = _create_ssh_ca(auth_client, descr='Revoking KRL CA')
        cert = _issue(auth_client, ca)
        client = app.test_client()
        before = client.get(f"/ssh/krl/{ca['refid']}")
        assert not _revoked(tmp_path, before.data, cert['certificate'])
        _revoke(auth_client, cert)
        with app.app_context():
            row = db.session.get(SSHKRL, ca['id'])
            # Stored by the revocation itself, before anyone downloads it
            assert row.digest == SSHKRLService.revocation_digest(db.session.get(SSHCertificateAuthority, ca['id']))
            stored = bytes(row.data)
        after = client.get(f"/ssh/krl/{ca['refid']}", headers={'If-None-Match': before.headers['ETag']})
        assert after.status_code == 200
        assert after.data == stored
        assert int(after.headers['X-KRL-Version']) > int(before.headers['X-KRL-Version'])
        assert _revoked(tmp_path, after.data, cert['certificate'])

    def test_the_authenticated_download_is_the_published_krl(self, app, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Same KRL CA')
        public = app.test_client().get(f"/ssh/krl/{ca['refid']}").data
        assert auth_client.get(f"/api/v2/ssh/cas/{ca['id']}/krl").data == public

    def test_the_database_row_is_what_every_node_serves(self, app, auth_client):
        """A node holds no KRL of its own: it serves the row another node wrote."""
        ca = _create_ssh_ca(auth_client, descr='Shared KRL CA')
        client = app.test_client()
        client.get(f"/ssh/krl/{ca['refid']}")
        with app.app_context():
            row = db.session.get(SSHKRL, ca['id'])
            row.data, row.version = b'written by another node', row.version + 7
            db.session.commit()
            version = row.version
        r = client.get(f"/ssh/krl/{ca['refid']}")
        assert r.data == b'written by another node'
        assert r.headers['ETag'] == f'"{version}"'

    def test_a_concurrent_publication_wins_and_is_served(self, app, auth_client, monkeypatch):
        """Two nodes rebuild at once: the second write is refused by the compare-and-set and the
        node serves the KRL the first one stored, never a third version."""
        ca = _create_ssh_ca(auth_client, descr='Racing KRL CA')
        client = app.test_client()
        client.get(f"/ssh/krl/{ca['refid']}")
        with app.app_context():
            db.session.get(SSHKRL, ca['id']).digest = 'stale'
            db.session.commit()
        real = SSHKRLService.generate_krl
        raced = []

        def racing(ca_id, version=None):
            data = real(ca_id, version=version)
            if not raced:
                # The other node, between this node's read and its write: same revocations, committed first
                raced.append(version)
                row = db.session.get(SSHKRL, ca_id)
                row.digest = SSHKRLService.revocation_digest(db.session.get(SSHCertificateAuthority, ca_id))
                row.data, row.version = b'other node', version + 1000
                db.session.commit()
            return data
        monkeypatch.setattr(SSHKRLService, 'generate_krl', staticmethod(racing))
        r = client.get(f"/ssh/krl/{ca['refid']}")
        assert raced
        assert r.data == b'other node'
        assert r.headers['ETag'] == f'"{raced[0] + 1000}"'

    def test_a_failed_build_is_503_and_keeps_the_published_krl(self, app, auth_client, monkeypatch):
        ca = _create_ssh_ca(auth_client, descr='Failing KRL CA')
        cert = _issue(auth_client, ca)
        client = app.test_client()
        before = client.get(f"/ssh/krl/{ca['refid']}")
        monkeypatch.setattr(krl_service.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(
            a, 1, stdout='', stderr='boom'))
        _revoke(auth_client, cert)
        r = client.get(f"/ssh/krl/{ca['refid']}")
        assert r.status_code == 503
        with app.app_context():
            assert int(db.session.get(SSHKRL, ca['id']).version) == int(before.headers['X-KRL-Version'])

    def test_deleting_the_ca_drops_its_krl(self, app, auth_client):
        ca = _create_ssh_ca(auth_client, descr='Dropped KRL CA')
        app.test_client().get(f"/ssh/krl/{ca['refid']}")
        assert auth_client.delete(f"/api/v2/ssh/cas/{ca['id']}").status_code in (200, 204)
        with app.app_context():
            assert db.session.get(SSHKRL, ca['id']) is None
