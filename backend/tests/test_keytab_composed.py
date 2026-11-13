"""C-03: one keytab per Windows enrollment profile, one composed file for the acceptor.

The acceptor reads the composed file through the GSSAPI credential store, never through the
process' KRB5_KTNAME; an upload holds only HTTP/<host>@<realm of its profile> entries.
"""
import base64
import io
import logging
import sys
import types

import pytest

from models import SharedFile, WindowsEnrollmentProfile, db
from services import cluster_commands as cc
from services import shared_files, windows_profiles
from services.kerberos import keytab_format, negotiate_auth
from tests.keytab_support import keytab, negotiate_header

try:
    import gssapi  # noqa: F401
    import spnego  # noqa: F401
    HAS_GSSAPI = True
except ImportError:
    HAS_GSSAPI = False

requires_gssapi = pytest.mark.skipif(not HAS_GSSAPI, reason='needs pyspnego[kerberos]')

HOST = 'ucm.example.test'
ONE = keytab(f'HTTP/{HOST}@ONE.TEST')
TWO = keytab(f'HTTP/{HOST}@TWO.TEST', (f'HTTP/{HOST}@TWO.TEST', 2, 17))


@pytest.fixture
def profiles(app, monkeypatch, tmp_path):
    """The default profile in ONE.TEST and a profile 'c03-two' in TWO.TEST, both without keytab;
    the node file in tmp_path. Everything is put back afterwards."""
    monkeypatch.setattr(negotiate_auth, 'KEYTAB_PATH', tmp_path / 'kerberos.keytab')
    monkeypatch.setattr(negotiate_auth, 'is_enabled', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'get_spn', lambda: f'HTTP/{HOST}@ONE.TEST')
    if not HAS_GSSAPI:
        # The GSSAPI load alone is replaced: the entries are still read from the bytes
        monkeypatch.setattr(negotiate_auth, '_gssapi_load', lambda target: (
            keytab_format.read_entries(open(target, 'rb').read())[0].principal, None))
    with app.app_context():
        row = db.session.get(SharedFile, shared_files.KERBEROS_KEYTAB)
        saved_file = (row.content, row.updated_at, row.updated_by) if row is not None else None
        shared_files.drop_file(shared_files.KERBEROS_KEYTAB)
        default = windows_profiles.default_profile()
        created = default is None
        if created:
            default = WindowsEnrollmentProfile(name='default', is_default=True, enabled=True)
            db.session.add(default)
        saved = (default.realm, default.keytab, default.enabled)
        default.realm, default.keytab, default.enabled = 'ONE.TEST', None, True
        two = WindowsEnrollmentProfile(name='c03-two', realm='TWO.TEST', enabled=True)
        db.session.add(two)
        db.session.commit()
        ids = types.SimpleNamespace(default=default.id, two=two.id)
    yield ids
    with app.app_context():
        WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.name.like('c03-%')).delete(
            synchronize_session=False)
        default = db.session.get(WindowsEnrollmentProfile, ids.default)
        if created:
            db.session.delete(default)
        else:
            default.realm, default.keytab, default.enabled = saved
        SharedFile.query.filter_by(name=shared_files.KERBEROS_KEYTAB).delete()
        if saved_file is not None:
            db.session.add(SharedFile(name=shared_files.KERBEROS_KEYTAB, content=saved_file[0],
                                      updated_at=saved_file[1], updated_by=saved_file[2]))
        from models import ClusterCommand
        ClusterCommand.query.filter_by(kind=cc.RELOAD_KEYTAB).delete()
        db.session.commit()


def _upload(client, data, profile_id=None):
    form = {'file': (io.BytesIO(data), 'k.keytab')}
    if profile_id is not None:
        form['profile_id'] = str(profile_id)
    return client.post('/api/v2/kerberos/keytab', data=form, content_type='multipart/form-data')


def _principals(data):
    return sorted((e.principal, e.kvno, e.enctype) for e in keytab_format.read_entries(data))


def test_two_profiles_compose_one_file_that_inspect_lists_entry_by_entry(app, auth_client, profiles):
    assert _upload(auth_client, ONE, profiles.default).status_code == 200
    r = _upload(auth_client, TWO, profiles.two)
    assert r.status_code == 200, r.data
    written = negotiate_auth.KEYTAB_PATH.read_bytes()
    assert _principals(written) == sorted(_principals(ONE) + _principals(TWO))
    listed = negotiate_auth.inspect_keytab()['entries']
    assert sorted((e['principal'], e['realm'], e['kvno']) for e in listed) == [
        (f'HTTP/{HOST}@ONE.TEST', 'ONE.TEST', 2), (f'HTTP/{HOST}@TWO.TEST', 'TWO.TEST', 2),
        (f'HTTP/{HOST}@TWO.TEST', 'TWO.TEST', 2)]
    body = r.get_json()['data']
    assert body['keytab_valid'] and body['keytab_spn_matches']
    assert {e['realm'] for e in body['keytab_entries']} == {'ONE.TEST', 'TWO.TEST'}
    with app.app_context():
        assert shared_files.read_file(shared_files.KERBEROS_KEYTAB) == written


@pytest.mark.parametrize('stray', [f'HTTP/{HOST}@ONE.TEST', f'host/{HOST}@TWO.TEST',
                                   'HTTP/other.example.test@TWO.TEST', 'HTTP@TWO.TEST'],
                         ids=['other-realm', 'other-service', 'other-host', 'no-host'])
def test_an_entry_outside_the_profile_is_refused(app, auth_client, profiles, stray):
    assert _upload(auth_client, ONE, profiles.default).status_code == 200
    before = negotiate_auth.KEYTAB_PATH.read_bytes()
    r = _upload(auth_client, keytab(f'HTTP/{HOST}@TWO.TEST', stray), profiles.two)
    assert r.status_code == 400, r.data
    assert stray in r.get_json()['message']
    assert negotiate_auth.KEYTAB_PATH.read_bytes() == before
    with app.app_context():
        assert db.session.get(WindowsEnrollmentProfile, profiles.two).keytab is None


def test_an_unknown_profile_is_404(auth_client, profiles):
    assert _upload(auth_client, TWO, 999999).status_code == 404


def test_two_kvno_of_one_principal_live_side_by_side(auth_client, profiles):
    """A password rotated in a forest: the old key serves until every ticket is renewed."""
    rotated = keytab(f'HTTP/{HOST}@TWO.TEST', (f'HTTP/{HOST}@TWO.TEST', 3))
    assert _upload(auth_client, ONE, profiles.default).status_code == 200
    assert _upload(auth_client, rotated, profiles.two).status_code == 200
    kvnos = [e['kvno'] for e in negotiate_auth.inspect_keytab()['entries'] if e['realm'] == 'TWO.TEST']
    assert sorted(kvnos) == [2, 3]


@pytest.mark.parametrize('how', ['disabled', 'deleted'])
def test_a_profile_disabled_or_deleted_leaves_the_file_at_reload(app, profiles, how):
    with app.app_context():
        db.session.get(WindowsEnrollmentProfile, profiles.default).set_keytab(ONE)
        db.session.get(WindowsEnrollmentProfile, profiles.two).set_keytab(TWO)
        windows_profiles.publish_keytab()
        db.session.commit()
        assert negotiate_auth.write_stored_keytab() == 'written'
        assert {e.realm for e in keytab_format.read_entries(negotiate_auth.KEYTAB_PATH.read_bytes())} \
            == {'ONE.TEST', 'TWO.TEST'}
        two = db.session.get(WindowsEnrollmentProfile, profiles.two)
        if how == 'disabled':
            two.enabled = False
        else:
            db.session.delete(two)
        db.session.commit()
    # The start recomposes from the profiles, then the reload writes what it stored
    negotiate_auth.restore_keytab_at_start(app)
    with app.app_context():
        negotiate_auth.write_stored_keytab()
    assert negotiate_auth.KEYTAB_PATH.read_bytes() == ONE


@requires_gssapi
def test_the_acceptor_reads_the_composed_file_whatever_krb5_ktname_says(app, profiles, monkeypatch,
                                                                        tmp_path):
    """A12: a Kerberos MSCA connection pointing KRB5_KTNAME at its keytab between two handshakes."""
    import gssapi
    negotiate_auth.KEYTAB_PATH.write_bytes(ONE)
    msca = tmp_path / 'msca.keytab'
    msca.write_bytes(keytab('HTTP/msca.example.test@MSCA.TEST'))
    monkeypatch.setenv('KRB5_KTNAME', f'FILE:{tmp_path / "unset.keytab"}')
    seen = []
    real = gssapi.SecurityContext

    def recording(*args, **kwargs):
        seen.append(str(kwargs['creds'].name) if kwargs.get('creds') is not None else None)
        return real(*args, **kwargs)
    monkeypatch.setattr(gssapi, 'SecurityContext', recording)
    negotiate_auth._pending_contexts.clear()
    header = negotiate_header('ONE.TEST')
    with app.app_context():
        assert negotiate_auth.authenticate_negotiate(header, '192.0.2.1').status == 'failed'
        monkeypatch.setenv('KRB5_KTNAME', f'FILE:{msca}')
        assert negotiate_auth.authenticate_negotiate(header, '192.0.2.2').status == 'failed'
    assert seen == [f'HTTP/{HOST}@ONE.TEST'] * 2


def test_a_kerberos_msca_connection_leaves_krb5_ktname_alone(monkeypatch):
    from services.msca.connection import MicrosoftCAConnectionMixin
    monkeypatch.setitem(sys.modules, 'certsrv', types.SimpleNamespace(
        Certsrv=lambda **kw: types.SimpleNamespace(session=types.SimpleNamespace(auth=None, verify=True))))
    monkeypatch.setitem(sys.modules, 'requests_kerberos', types.SimpleNamespace(
        HTTPKerberosAuth=lambda **kw: object(), OPTIONAL=1))
    monkeypatch.setenv('KRB5_KTNAME', 'FILE:/acceptor.keytab')
    msca = types.SimpleNamespace(server='ca.example.test', verify_ssl=True, ca_bundle=None,
                                 auth_method='kerberos', kerberos_keytab_path='/msca.keytab',
                                 kerberos_principal='svc@EXAMPLE.TEST')
    MicrosoftCAConnectionMixin._get_client(msca)
    import os
    assert os.environ['KRB5_KTNAME'] == 'FILE:/acceptor.keytab'


@requires_gssapi
def test_a_ticket_of_a_realm_without_key_is_a_warning_without_the_token(app, profiles, caplog):
    negotiate_auth.KEYTAB_PATH.write_bytes(ONE)
    negotiate_auth._pending_contexts.clear()
    header = negotiate_header('NOKEY.TEST')
    with caplog.at_level(logging.DEBUG, logger=negotiate_auth.logger.name), app.app_context():
        result = negotiate_auth.authenticate_negotiate(header, '192.0.2.3')
    assert result.status == 'failed'
    mine = [r for r in caplog.records if r.name == negotiate_auth.logger.name]
    assert [(r.levelno, r.getMessage()) for r in mine] == [
        (logging.WARNING, 'Kerberos: no key for this realm (NOKEY.TEST) in the keytab')]
    token = header.split(' ', 1)[1]
    assert token not in caplog.text and token[:40] not in caplog.text


class _Accepted:
    """An acceptor whose Kerberos context completed for *client* against *target*."""
    def __init__(self, client, target):
        self.complete, self.client_principal, self.negotiated_protocol = True, client, 'kerberos'
        self._context = types.SimpleNamespace(_context=types.SimpleNamespace(target_name=target))

    def step(self, token):
        return None


@pytest.mark.parametrize('client, accepted', [('alice@ONE.TEST', True), ('alice@TWO.TEST', False)])
def test_the_client_realm_is_the_realm_of_the_entry_that_served(monkeypatch, client, accepted):
    monkeypatch.setattr(negotiate_auth, 'get_spn', lambda: f'HTTP/{HOST}@ONE.TEST')
    monkeypatch.setattr(negotiate_auth, '_new_acceptor',
                        lambda hostname, service: _Accepted(client, f'HTTP/{HOST}@ONE.TEST'))
    negotiate_auth._pending_contexts.clear()
    token = base64.b64encode(b'token').decode()
    result = negotiate_auth.authenticate_negotiate(f'Negotiate {token}', '192.0.2.4')
    assert (result.status == 'authenticated') is accepted


def test_a_keytab_set_under_no_autoflush_is_composed(app, profiles):
    """The composition reads the profiles afresh: a keytab not yet flushed is neither left out
    nor lost from the object."""
    newer = keytab((f'HTTP/{HOST}@ONE.TEST', 3))
    with app.app_context():
        default = db.session.get(WindowsEnrollmentProfile, profiles.default)
        default.set_keytab(ONE)
        db.session.commit()
        with db.session.no_autoflush:
            default.set_keytab(newer)
            composed = windows_profiles.composed_keytab()
        assert composed == newer and default.keytab_bytes() == newer
        db.session.rollback()


def test_the_start_composes_every_enabled_profile(app, profiles):
    """A file stored before the second profile took its keytab is recomposed by the start."""
    with app.app_context():
        db.session.get(WindowsEnrollmentProfile, profiles.default).set_keytab(ONE)
        shared_files.store_file(shared_files.KERBEROS_KEYTAB, ONE)
        db.session.get(WindowsEnrollmentProfile, profiles.two).set_keytab(TWO)
        db.session.commit()
    negotiate_auth.restore_keytab_at_start(app)
    assert _principals(negotiate_auth.KEYTAB_PATH.read_bytes()) == sorted(
        _principals(ONE) + _principals(TWO))


def test_the_start_never_gives_the_default_the_keytab_of_another_profile(app, profiles):
    with app.app_context():
        db.session.get(WindowsEnrollmentProfile, profiles.two).set_keytab(TWO)
        windows_profiles.publish_keytab()
        db.session.commit()
    negotiate_auth.restore_keytab_at_start(app)
    with app.app_context():
        assert db.session.get(WindowsEnrollmentProfile, profiles.default).keytab is None
    assert negotiate_auth.KEYTAB_PATH.read_bytes() == TWO
