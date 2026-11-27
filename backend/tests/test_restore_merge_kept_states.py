"""A merge never undoes a revocation made here, whatever the row: the archive can only revoke more.

Each case takes an archive while the row is live, revokes the row here, merges the archive back
and expects the revocation to stand; an archive that revokes a row live here still revokes it.
Tables: SSH certificates (and so their KRL), SSH hosts, cross-certificates, API keys,
authentication certificates, ACME accounts, EAB credentials (revoked or used), DNS UPDATE keys,
key recovery requests (recovered, rejected, cancelled), approval requests (rejected, expired,
cancelled), SCEP requests (rejected). SQLite and PostgreSQL.
"""
import base64
import copy
import os
import uuid
from datetime import datetime

import pytest

from models import db
from tests.fresh_app import fresh_app_fixtures
from tests.test_backup_cross_installation import PASSWORD, Keys, _installation, _only
from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
ENGINES = [
    'sqlite',
    pytest.param('postgresql', marks=[
        pytest.mark.postgres,
        pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]),
]
_WHEN = datetime(2026, 6, 1, 12, 0, 0)


@pytest.fixture(scope='module', params=ENGINES)
def installation(request, app, tmp_path_factory):
    directory = tmp_path_factory.mktemp('kept-states')
    keys = Keys(directory, f'kept-states-{request.param}')
    if request.param == 'sqlite':
        with _installation(app, f"sqlite:///{directory / 'target.db'}", keys), app.app_context():
            yield request.param
        return
    with _a_schema_of_our_own(f'kept_states_{uuid.uuid4().hex[:10]}') as url:
        with _installation(app, url, keys, is_postgresql=True), app.app_context():
            yield request.param
            db.session.rollback()


def _tag():
    return uuid.uuid4().hex[:10]


def _pubkey():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    return ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()


def _user():
    from models import User
    tag = _tag()
    user = User(username=f'kept-{tag}', email=f'kept-{tag}@example.test', password_hash='x', role='admin')
    db.session.add(user)
    db.session.flush()
    return user


def _ssh_ca(kind):
    from services.ssh_ca_service import SSHCAService
    return SSHCAService.create_ca(descr=f'kept {kind} {_tag()}', ca_type=kind, key_type='ed25519',
                                  username='t', allow_any_principal=True).id


# --- one entry per table: make a live row, revoke it here, read what the revocation is ----------

def _make_ssh_certificate():
    from services.ssh_cert import SSHCertificateService
    ca_id = _ssh_ca('user')
    return SSHCertificateService.sign_certificate(ca_id, _pubkey(), 'user', ['kept']).id


def _revoke_ssh_certificate(row_id):
    from services.ssh_cert import SSHCertificateService
    SSHCertificateService.revoke_certificate(row_id, reason='keyCompromise', username='t')


def _make_ssh_host():
    from models.ssh import SSHHost
    from services.ssh_cert import SSHCertificateService
    ca_id = _ssh_ca('host')
    key = _pubkey()
    cert = SSHCertificateService.sign_certificate(ca_id, key, 'host', ['kept.example.test'])
    host = SSHHost(ssh_ca_id=ca_id, name=f'kept-{_tag()}', principals='["kept.example.test"]',
                   public_key=key, key_type='ed25519', fingerprint=cert.fingerprint,
                   certificate_id=cert.id, auto_renew=True)
    db.session.add(host)
    db.session.commit()
    return host.id


def _revoke_ssh_host(row_id):
    from services.ssh_host_service import revoke_host
    revoke_host(row_id, username='t')


def _make_cross_certificate():
    from models.ca_cross_certificate import CACrossCertificate
    from tests.test_restore_replace_dependents import _authority_row
    ca, _key, _cert = _authority_row(f'kept-ca-{_tag()}')
    row = CACrossCertificate(ca_id=ca.id, crt=base64.b64encode(b'cross').decode(),
                             fingerprint_sha256=uuid.uuid4().hex * 2, serial_number='0a', served=True)
    db.session.add(row)
    db.session.commit()
    return row.id


def _revoke_cross_certificate(row):
    row.revoked, row.revoked_at, row.revoke_reason, row.served = True, _WHEN, 'keyCompromise', False


def _make_api_key():
    from models.api_key import APIKey
    row = APIKey(key_hash=uuid.uuid4().hex, user_id=_user().id, name='kept', permissions='["*"]')
    db.session.add(row)
    db.session.commit()
    return row.id


def _make_auth_certificate():
    from models.auth_certificate import AuthCertificate
    row = AuthCertificate(user_id=_user().id, cert_serial=uuid.uuid4().hex, cert_subject='CN=kept',
                          cert_issuer='CN=kept issuer', cert_fingerprint=uuid.uuid4().hex * 2)
    db.session.add(row)
    db.session.commit()
    return row.id


def _make_acme_account():
    from models.acme_models import AcmeAccount
    row = AcmeAccount(account_id=_tag(), jwk='{"kty":"EC"}', jwk_thumbprint=uuid.uuid4().hex)
    db.session.add(row)
    db.session.commit()
    return row.id


def _make_eab():
    from models.acme_models import AcmeEabCredential
    row = AcmeEabCredential(kid=f'kept-{_tag()}', status='active')
    row.hmac_key_b64 = base64.urlsafe_b64encode(os.urandom(32)).decode()
    db.session.add(row)
    db.session.commit()
    return row.id


def _revoke_eab(row):
    row.status, row.revoked_at = 'revoked', _WHEN


def _use_eab(row):
    row.status, row.used_at, row.used_by_account_id = 'used', _WHEN, 'acct-here'


def _make_dns_update_key():
    from models.acme_client_account import AcmeClientAccount
    from models.acme_dns_update import AcmeDnsUpdateKey
    tag = _tag()
    account = AcmeClientAccount(label=f'kept-{tag}', email='ops@example.test',
                                directory_url=f'https://ca-{tag}.example.test/directory',
                                account_url=f'https://ca-{tag}.example.test/acct/1', proxy_slug=f'kept-{tag}')
    db.session.add(account)
    db.session.flush()
    row = AcmeDnsUpdateKey(acme_client_account_id=account.id, name=f'kept-{tag}.example.test.')
    row.secret = 'c2VjcmV0LXNlY3JldC1zZWNyZXQtc2VjcmV0'
    db.session.add(row)
    db.session.commit()
    return row.id


def _make_key_recovery_request():
    from models.key_recovery import KeyRecoveryRequest
    from tests.test_restore_replace_dependents import _authority_row, _certificate_row
    tag = _tag()
    certificate = _certificate_row(f'kept-krr-{tag}', _authority_row(f'kept-krr-ca-{tag}'))
    row = KeyRecoveryRequest(cert_id=certificate.id, cert_refid=certificate.refid, reason='kept',
                             status='approved', requested_by='t', requested_at=_WHEN,
                             decided_by='u', decided_at=_WHEN)
    db.session.add(row)
    db.session.commit()
    return row.id


def _make_approval_request():
    from models.policy import ApprovalRequest
    row = ApprovalRequest(request_type='certificate', requester_comment=f'kept-{_tag()}',
                          status='pending', created_at=datetime(2026, 5, 1, 12, 0, 0,
                                                                 int.from_bytes(os.urandom(2), 'big')))
    db.session.add(row)
    db.session.commit()
    return row.id


def _make_scep_request():
    from models.scep import SCEPRequest
    from tests.test_restore_replace_dependents import _authority_row
    tag = _tag()
    # A transaction id is unique per CA: without one the archived row is not this row
    ca, _key, _cert = _authority_row(f'kept-scep-ca-{tag}')
    row = SCEPRequest(transaction_id=f'kept-{tag}', ca_refid=ca.refid,
                      csr=base64.b64encode(b'csr').decode(), status='pending')
    db.session.add(row)
    db.session.commit()
    return row.id


_REJECTED = '[{"user_id": 1, "username": "u", "action": "reject"}]'


def _set(**values):
    def revoke(row):
        for name, value in values.items():
            setattr(row, name, value)
    return revoke


def _model(path):
    module, name = path.split(':')
    return getattr(__import__(module, fromlist=[name]), name)


# section[:variant]: (model, sections archived, make, revoke here (id or row), columns of the revocation,
#           is the row revoked, archive row edit that revokes it)
CASES = {
    'ssh_certificates': (
        'models.ssh:SSHCertificate', ('ssh_cas', 'ssh_certificates'), _make_ssh_certificate,
        ('id', _revoke_ssh_certificate), ('revoked', 'revoked_at', 'revoke_reason'),
        lambda row: row.revoked,
        {'revoked': True, 'revoked_at': '2026-06-01T12:00:00', 'revoke_reason': 'superseded'}),
    'ssh_hosts': (
        'models.ssh:SSHHost', ('ssh_cas', 'ssh_certificates', 'ssh_hosts'), _make_ssh_host,
        ('id', _revoke_ssh_host), ('revoked_at', 'auto_renew', 'challenge'),
        lambda row: row.revoked_at is not None and not row.auto_renew,
        {'revoked_at': '2026-06-01T12:00:00', 'auto_renew': False}),
    'ca_cross_certificates': (
        'models.ca_cross_certificate:CACrossCertificate', ('ca_cross_certificates',),
        _make_cross_certificate, ('row', _revoke_cross_certificate),
        ('revoked', 'revoked_at', 'revoke_reason', 'served'), lambda row: row.revoked and not row.served,
        {'revoked': True, 'revoked_at': '2026-06-01T12:00:00', 'revoke_reason': 'superseded',
         'served': False}),
    'api_keys': (
        'models.api_key:APIKey', ('api_keys',), _make_api_key, ('row', _set(is_active=False)),
        ('is_active',), lambda row: row.is_active is False, {'is_active': False}),
    'auth_certificates': (
        'models.auth_certificate:AuthCertificate', ('auth_certificates',), _make_auth_certificate,
        ('row', _set(enabled=False)), ('enabled',), lambda row: row.enabled is False, {'enabled': False}),
    'acme_accounts': (
        'models.acme_models:AcmeAccount', ('acme_accounts',), _make_acme_account,
        ('row', _set(status='deactivated')), ('status',), lambda row: row.status == 'deactivated',
        {'status': 'deactivated'}),
    'acme_eab_credentials': (
        'models.acme_models:AcmeEabCredential', ('acme_eab_credentials',), _make_eab,
        ('row', _revoke_eab), ('status', 'revoked_at'), lambda row: row.status == 'revoked',
        {'status': 'revoked', 'revoked_at': '2026-06-01T12:00:00'}),
    # Single-use: a credential consumed here never registers a second account
    'acme_eab_credentials:used': (
        'models.acme_models:AcmeEabCredential', ('acme_eab_credentials',), _make_eab,
        ('row', _use_eab), ('status', 'used_at', 'used_by_account_id'),
        lambda row: row.status == 'used',
        {'status': 'used', 'used_at': '2026-06-01T12:00:00', 'used_by_account_id': 'acct-archive'}),
    # A recovered key is handed out once; a cancelled request is never reopened
    'key_recovery_requests': (
        'models.key_recovery:KeyRecoveryRequest', ('key_recovery_requests',), _make_key_recovery_request,
        ('row', _set(status='recovered', recovered_by='t', recovered_at=_WHEN)),
        ('status', 'recovered_by', 'recovered_at'), lambda row: row.status == 'recovered',
        {'status': 'recovered', 'recovered_by': 'v', 'recovered_at': '2026-06-01T12:00:00'}),
    'key_recovery_requests:cancelled': (
        'models.key_recovery:KeyRecoveryRequest', ('key_recovery_requests',), _make_key_recovery_request,
        ('row', _set(status='cancelled', decision_note='no')), ('status', 'decision_note'),
        lambda row: row.status == 'cancelled', {'status': 'cancelled', 'decision_note': 'no'}),
    # A request refused or closed here is never pending again, to be approved after all
    'approval_requests': (
        'models.policy:ApprovalRequest', ('approval_requests',), _make_approval_request,
        ('row', _set(status='rejected', resolved_at=_WHEN, approvals=_REJECTED)),
        ('status', 'resolved_at', 'approvals'), lambda row: row.status == 'rejected',
        {'status': 'rejected', 'resolved_at': '2026-06-01T12:00:00', 'approvals': _REJECTED}),
    'approval_requests:expired': (
        'models.policy:ApprovalRequest', ('approval_requests',), _make_approval_request,
        ('row', _set(status='expired', resolved_at=_WHEN)), ('status', 'resolved_at'),
        lambda row: row.status == 'expired', {'status': 'expired', 'resolved_at': '2026-06-01T12:00:00'}),
    'approval_requests:cancelled': (
        'models.policy:ApprovalRequest', ('approval_requests',), _make_approval_request,
        ('row', _set(status='cancelled', resolved_at=_WHEN)), ('status', 'resolved_at'),
        lambda row: row.status == 'cancelled',
        {'status': 'cancelled', 'resolved_at': '2026-06-01T12:00:00'}),
    'scep_requests': (
        'models.scep:SCEPRequest', ('scep_requests',), _make_scep_request,
        ('row', _set(status='rejected', rejection_reason='no', approved_by='t', approved_at=_WHEN)),
        ('status', 'rejection_reason', 'approved_by', 'approved_at'),
        lambda row: row.status == 'rejected',
        {'status': 'rejected', 'rejection_reason': 'no', 'approved_by': 'v',
         'approved_at': '2026-06-01T12:00:00'}),
    'acme_dns_update_keys': (
        'models.acme_dns_update:AcmeDnsUpdateKey', ('acme_dns_update_keys',), _make_dns_update_key,
        ('row', _set(status='revoked', revoked_at=_WHEN)), ('status', 'revoked_at'),
        lambda row: row.status == 'revoked', {'status': 'revoked', 'revoked_at': '2026-06-01T12:00:00'}),
}


def _archive(sections):
    from services.backup_service import BackupService
    service = BackupService()
    blob = service.create_backup(PASSWORD, include=_only(*sections))
    return service._decrypt_framed(blob, PASSWORD)


def _merge(master, payload):
    from services.backup_service import BackupService
    return BackupService()._restore_payload(copy.deepcopy(payload), master, 'merge')


def _state(model, row_id, columns):
    db.session.expire_all()
    row = db.session.get(model, row_id)
    return row, {column: getattr(row, column) for column in columns}


def _revoke_here(model, row_id, how):
    kind, revoke = how
    if kind == 'id':
        revoke(row_id)
    else:
        revoke(db.session.get(model, row_id))
    db.session.commit()


def _krl(row_id):
    from models.ssh import SSHCertificate
    from services.ssh_krl_service import SSHKRLService
    ca_id = db.session.get(SSHCertificate, row_id).ssh_ca_id
    return SSHKRLService.published(ca_id)['version']


@pytest.mark.parametrize('section', sorted(CASES))
def test_a_merge_keeps_a_revocation_made_after_the_archive(installation, section):
    path, sections, make, how, columns, revoked, _edit = CASES[section]
    section = section.split(':')[0]
    model = _model(path)
    row_id = make()
    master, payload = _archive(sections)
    _revoke_here(model, row_id, how)
    row, before = _state(model, row_id, columns)
    assert revoked(row), before
    krl = _krl(row_id) if section == 'ssh_certificates' else None

    _merge(master, payload)

    row, after = _state(model, row_id, columns)
    assert revoked(row) and after == before, (before, after)
    if krl is not None:
        # The KRL still lists the serial: no rebuild, no higher version an agent would install
        assert _krl(row_id) == krl


@pytest.mark.parametrize('section', sorted(CASES))
def test_an_archive_still_revokes_a_row_live_here(installation, section):
    path, sections, make, _how, columns, revoked, edit = CASES[section]
    section = section.split(':')[0]
    model = _model(path)
    row_id = make()
    master, payload = _archive(sections)
    row = db.session.get(model, row_id)
    assert not revoked(row)
    # A plain payload, as an older archive reads: no section digest for the edit to break
    payload = {name: copy.deepcopy(list(payload[name])) for name in sections}
    archived = [entry for entry in payload[section] if _is(entry, row, section)]
    assert len(archived) == 1, section
    archived[0].update(edit)

    _merge(master, payload)

    row, after = _state(model, row_id, columns)
    assert revoked(row), after


def _is(entry, row, section):
    identity = {
        'ssh_certificates': ('serial', 'fingerprint'), 'ssh_hosts': ('refid',),
        'ca_cross_certificates': ('fingerprint_sha256',), 'api_keys': ('key_hash',),
        'auth_certificates': ('cert_fingerprint',), 'acme_accounts': ('account_id',),
        'acme_eab_credentials': ('kid',), 'acme_dns_update_keys': ('name',),
        'key_recovery_requests': ('cert_refid',), 'approval_requests': ('requester_comment',),
        'scep_requests': ('transaction_id',),
    }[section]
    return all(entry.get(column) == getattr(row, column) for column in identity)


def test_every_section_with_a_revoked_state_is_covered():
    """A table restored in a merge that gains a revocation column joins the guard and these cases."""
    from services.backup import manifest
    from services.backup.restore.kept_states import KEPT_STATES
    from services.backup.export_generic import load_model
    from sqlalchemy import inspect as sa_inspect
    revocable = set()
    for name, section in manifest.SECTIONS.items():
        columns = set(sa_inspect(load_model(section)).local_table.columns.keys())
        if columns & {'revoked', 'revoked_at'}:
            revocable.add(name)
    # X.509 certificates and CAs keep theirs in restore_core (_kept_revocation), with the hold rules;
    # a revoked serial or compromised key is a record of a revocation, added, never lowered
    assert revocable - {'certificates', 'certificate_authorities', 'revoked_serials',
                        'compromised_keys'} <= set(KEPT_STATES)
    assert set(KEPT_STATES) == {name.split(':')[0] for name in CASES}


def test_an_archive_revoking_a_credential_used_here_keeps_its_use(installation):
    """revoked outranks used: the archive's revocation applies, the account bound here stays bound."""
    from models.acme_models import AcmeEabCredential
    row_id = _make_eab()
    master, payload = _archive(('acme_eab_credentials',))
    row = db.session.get(AcmeEabCredential, row_id)
    payload = {'acme_eab_credentials': copy.deepcopy(list(payload['acme_eab_credentials']))}
    archived = [entry for entry in payload['acme_eab_credentials'] if entry.get('kid') == row.kid]
    archived[0].update(status='revoked', revoked_at='2026-07-01T12:00:00')
    _use_eab(row)
    db.session.commit()

    _merge(master, payload)

    _row, after = _state(AcmeEabCredential, row_id,
                         ('status', 'used_at', 'used_by_account_id', 'revoked_at'))
    assert after == {'status': 'revoked', 'used_at': _WHEN, 'used_by_account_id': 'acct-here',
                     'revoked_at': datetime(2026, 7, 1, 12, 0, 0)}, after


def test_a_merge_keeps_an_account_key_changed_here(installation):
    """RFC 8555 §7.3.5: the account here is the truth on its key, an old archived one never comes back."""
    from models.acme_models import AcmeAccount
    row_id = _make_acme_account()
    master, payload = _archive(('acme_accounts',))
    row = db.session.get(AcmeAccount, row_id)
    row.jwk, row.jwk_thumbprint = '{"kty":"OKP"}', uuid.uuid4().hex
    db.session.commit()
    _row, before = _state(AcmeAccount, row_id, ('jwk', 'jwk_thumbprint'))

    _merge(master, payload)

    _row, after = _state(AcmeAccount, row_id, ('jwk', 'jwk_thumbprint'))
    assert after == before, (before, after)


def _eab_row(kid, hmac, **values):
    from models.acme_models import AcmeEabCredential
    row = AcmeEabCredential(kid=kid, **values)
    row.hmac_key_b64 = hmac
    db.session.add(row)
    return row


@pytest.mark.parametrize('legacy', [False, True], ids=['with-identities', 'older-archive'])
def test_an_eab_credential_names_its_users_as_the_archive_names_them(installation, app,
                                                                     tmp_path, legacy):
    """Another installation numbers its accounts its own way: the EAB links follow the identity.

    An archive older than the identities names users by the source's number alone: a new row
    gets no link rather than another account's, an existing row keeps its own.
    """
    from models import User
    from models.acme_models import AcmeEabCredential
    tag = _tag()
    hmac = base64.urlsafe_b64encode(os.urandom(32)).decode()
    source_ids = {'creator': 910_000 + int(tag[:4], 16), 'revoker': 930_000 + int(tag[4:8], 16)}
    with _installation(app, f"sqlite:///{tmp_path / 'source.db'}", Keys(tmp_path, f'eab-src-{tag}')), \
            app.app_context():
        for role, user_id in source_ids.items():
            db.session.add(User(id=user_id, username=f'eab-{role}-{tag}', role='admin',
                                email=f'eab-{role}-{tag}@example.test', password_hash='x'))
        db.session.flush()
        for kid in (f'eab-new-{tag}', f'eab-used-{tag}'):
            _eab_row(kid, hmac, status='revoked', revoked_at=_WHEN,
                     created_by_user_id=source_ids['creator'], revoked_by_user_id=source_ids['revoker'])
        db.session.commit()
        master, payload = _archive(('users', 'acme_eab_credentials'))
        payload = {name: copy.deepcopy(list(payload[name])) for name in ('users', 'acme_eab_credentials')}

    if legacy:
        for entry in payload['acme_eab_credentials']:
            entry.pop('created_by_user_id_ref'), entry.pop('revoked_by_user_id_ref')
    # Here, the source's numbers belong to other accounts
    decoys = {role: User(id=user_id, username=f'eab-decoy-{role}-{tag}', role='admin',
                         email=f'eab-decoy-{role}-{tag}@example.test', password_hash='x')
              for role, user_id in source_ids.items()}
    db.session.add_all(decoys.values())
    local = _user()
    used = _eab_row(f'eab-used-{tag}', hmac, status='used', used_at=_WHEN, used_by_account_id='acct-here',
                    created_by_user_id=local.id)
    db.session.commit()
    used_id, local_id = used.id, local.id

    _merge(master, payload)

    db.session.expire_all()
    named = {role: User.query.filter_by(username=f'eab-{role}-{tag}').one().id for role in source_ids}
    assert not set(named.values()) & set(source_ids.values())
    new = AcmeEabCredential.query.filter_by(kid=f'eab-new-{tag}').one()
    used = db.session.get(AcmeEabCredential, used_id)
    if legacy:
        assert (new.created_by_user_id, new.revoked_by_user_id) == (None, None)
        assert used.created_by_user_id == local_id
    else:
        assert (new.created_by_user_id, new.revoked_by_user_id) == (named['creator'], named['revoker'])
        assert used.created_by_user_id == named['creator']
    # revoked outranks used: the archive's revocation, by its revoker, the use made here kept
    assert (used.status, used.used_by_account_id) == ('revoked', 'acct-here')
    assert used.revoked_by_user_id == (None if legacy else named['revoker'])
