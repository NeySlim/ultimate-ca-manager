"""Revoking ten certificates does what revoking one does, ten times.

A certificate UCM obtained from a Microsoft CA has no ``caref``: UCM is not
its issuer, so it publishes no CRL entry and no OCSP answer for it, and the
Windows CA's own CRL is the only place its revocation can show up. The
``certutil -revoke`` that puts it there lived in the single-certificate route
as a function returning a Flask response, which the bulk route could not
reuse and did not.

``POST /api/v2/certificates/bulk/revoke`` therefore flipped three columns,
answered ``1 certificates revoked``, and left the certificate valid to every
relying party, reachable from the operations page in two clicks.
"""
import json

import pytest

from tests.conftest import get_json
from tests.test_msca_admin_channel import _make_msca_cert

CERTS = '/api/v2/certificates'


def post_json(client, url, data=None):
    return client.post(url, data=json.dumps(data or {}), content_type='application/json')


def _spy_admin_channel(monkeypatch, fail_with=None):
    """Record the PowerShell the admin channel would run. No host is contacted."""
    scripts = []

    def fake_run_ps(msca, script):
        scripts.append(script)
        if fail_with:
            from services.msca.admin_channel import MSCAAdminChannelError
            raise MSCAAdminChannelError(fail_with)
        return 'ok'

    from services.msca.admin_channel import MicrosoftCAAdminChannelMixin
    monkeypatch.setattr(MicrosoftCAAdminChannelMixin, '_run_ps', staticmethod(fake_run_ps))
    return scripts


class TestBulkRevokeReachesTheWindowsCA:

    def test_it_runs_the_certutil_the_single_route_runs(self, app, auth_client, monkeypatch):
        _, cert_id, serial = _make_msca_cert(app, 'bulk-revoke.test.local')
        scripts = _spy_admin_channel(monkeypatch)

        r = post_json(auth_client, f'{CERTS}/bulk/revoke',
                      {'ids': [cert_id], 'reason': 'keyCompromise'})

        assert r.status_code == 200, r.data
        assert scripts, 'the bulk revoke never reached the Windows CA'
        assert f'-revoke {serial.lower()} 1' in scripts[0]
        assert '-crl' in scripts[0]

    def test_both_routes_send_the_same_command(self, app, auth_client, monkeypatch):
        """Same certificate, same reason, same instruction to the CA."""
        _, single_id, single_serial = _make_msca_cert(app, 'parity-single.test.local')
        _, bulk_id, bulk_serial = _make_msca_cert(app, 'parity-bulk.test.local')
        scripts = _spy_admin_channel(monkeypatch)

        post_json(auth_client, f'{CERTS}/{single_id}/revoke', {'reason': 'cACompromise'})
        post_json(auth_client, f'{CERTS}/bulk/revoke',
                  {'ids': [bulk_id], 'reason': 'cACompromise'})

        assert len(scripts) == 2
        assert (scripts[0].replace(single_serial.lower(), '<serial>')
                == scripts[1].replace(bulk_serial.lower(), '<serial>'))

    def test_it_records_the_same_audit_entry(self, app, auth_client, monkeypatch):
        _, cert_id, _ = _make_msca_cert(app, 'bulk-audit.test.local')
        _spy_admin_channel(monkeypatch)

        post_json(auth_client, f'{CERTS}/bulk/revoke',
                  {'ids': [cert_id], 'reason': 'keyCompromise'})

        with app.app_context():
            from models.audit_log import AuditLog
            entries = AuditLog.query.filter_by(
                action='msca.revoke_on_ca', resource_id=str(cert_id)).all()
            assert len(entries) == 1, 'the propagation left no trace in the audit log'

    def test_many_certificates_are_each_carried_over(self, app, auth_client, monkeypatch):
        ids = []
        for n in range(3):
            _, cert_id, _ = _make_msca_cert(app, f'bulk-many-{n}.test.local')
            ids.append(cert_id)
        scripts = _spy_admin_channel(monkeypatch)

        r = post_json(auth_client, f'{CERTS}/bulk/revoke',
                      {'ids': ids, 'reason': 'keyCompromise'})

        assert get_json(r)['data']['success'] == ids
        assert len(scripts) == 3


class TestWhatTheOperatorIsTold:

    def test_a_certificate_left_local_only_is_named(self, app, auth_client):
        """No admin channel: the revocation is real in UCM and nowhere else,
        and the answer says which certificates that applies to."""
        _, cert_id, _ = _make_msca_cert(app, 'bulk-nochan.test.local', winrm=False)

        r = post_json(auth_client, f'{CERTS}/bulk/revoke',
                      {'ids': [cert_id], 'reason': 'unspecified'})

        body = get_json(r)
        assert r.status_code == 200
        assert body['data']['success'] == [cert_id]
        assert body['data']['msca_local_only'] == [cert_id]

    def test_a_refused_admin_channel_is_named_too(self, app, auth_client, monkeypatch):
        _, cert_id, _ = _make_msca_cert(app, 'bulk-refused.test.local')
        _spy_admin_channel(monkeypatch, fail_with='WinRM refused')

        r = post_json(auth_client, f'{CERTS}/bulk/revoke',
                      {'ids': [cert_id], 'reason': 'keyCompromise'})

        body = get_json(r)
        assert body['data']['success'] == [cert_id]
        assert body['data']['msca_local_only'] == [cert_id]
        with app.app_context():
            from models import Certificate, db
            assert db.session.get(Certificate, cert_id).revoked is True

    def test_an_ordinary_certificate_is_unchanged(self, app, auth_client, create_ca,
                                                  create_cert, monkeypatch):
        """The contract for everything that is not an msca certificate: same
        payload as before, and nothing reaches for a Windows CA."""
        scripts = _spy_admin_channel(monkeypatch)
        ca = create_ca(cn='Bulk Plain CA')
        cert = create_cert(cn='plain-bulk.example.com', ca_id=ca['id'])

        r = post_json(auth_client, f'{CERTS}/bulk/revoke',
                      {'ids': [cert['id']], 'reason': 'keyCompromise'})

        body = get_json(r)
        assert r.status_code == 200
        assert body['message'] == '1 certificates revoked'
        assert set(body['data']) == {'success', 'failed'}
        assert body['data']['success'] == [cert['id']]
        assert scripts == []


class TestTheSingleRouteKeepsItsWording:
    """The propagation moved into a shared service; the three answers the
    single-certificate route gives are read by clients and did not."""

    def test_propagated(self, app, auth_client, monkeypatch):
        _, cert_id, _ = _make_msca_cert(app, 'word-ok.test.local')
        _spy_admin_channel(monkeypatch)

        body = get_json(post_json(auth_client, f'{CERTS}/{cert_id}/revoke',
                                  {'reason': 'keyCompromise'}))

        assert body['meta'] == {'msca_ca_revoked': True}
        assert body['message'] == 'Certificate revoked in UCM and on the Microsoft CA'

    def test_no_channel(self, app, auth_client):
        _, cert_id, _ = _make_msca_cert(app, 'word-nochan.test.local', winrm=False)

        body = get_json(post_json(auth_client, f'{CERTS}/{cert_id}/revoke',
                                  {'reason': 'unspecified'}))

        assert body['meta'] == {'msca_local_only': True}
        assert body['message'] == (
            'Certificate revoked in UCM only, no Microsoft CA admin channel '
            'is configured, so the Windows CA was not notified. Enable the '
            'WinRM admin channel on the connection, or revoke it on the CA.')

    def test_channel_refused(self, app, auth_client, monkeypatch):
        _, cert_id, _ = _make_msca_cert(app, 'word-refused.test.local')
        _spy_admin_channel(monkeypatch, fail_with='WinRM refused')

        body = get_json(post_json(auth_client, f'{CERTS}/{cert_id}/revoke',
                                  {'reason': 'keyCompromise'}))

        assert body['meta']['msca_local_only'] is True
        assert body['meta']['msca_ca_error'] == 'WinRM refused'
        assert body['message'] == (
            'Certificate revoked in UCM, but propagating the revocation to '
            'the Windows CA failed: WinRM refused. Revoke it on the CA manually.')
