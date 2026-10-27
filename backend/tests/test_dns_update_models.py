"""Data layer of the DNS UPDATE listener: keys, expected values, cleanup."""
import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models import (db, AcmeClientAccount, AcmeClientOrder, AcmeEabCredential,
                    AcmeDnsUpdateKey, AcmeProxyDnsChallenge)
from utils.datetime_utils import utc_now

B64 = 'c2VjcmV0LXNlY3JldC1zZWNyZXQtc2VjcmV0LTEyMw=='


def _uid():
    return uuid.uuid4().hex[:10]


@pytest.fixture(autouse=True)
def _cleanup(app):
    with app.app_context():
        acct_floor = db.session.query(db.func.max(AcmeClientAccount.id)).scalar() or 0
        order_floor = db.session.query(db.func.max(AcmeClientOrder.id)).scalar() or 0
        eab_floor = db.session.query(db.func.max(AcmeEabCredential.id)).scalar() or 0
    yield
    with app.app_context():
        db.session.rollback()
        AcmeProxyDnsChallenge.query.delete()
        AcmeDnsUpdateKey.query.delete()
        AcmeClientOrder.query.filter(AcmeClientOrder.id > order_floor).delete(
            synchronize_session=False)
        AcmeEabCredential.query.filter(AcmeEabCredential.id > eab_floor).delete(
            synchronize_session=False)
        AcmeClientAccount.query.filter(AcmeClientAccount.id > acct_floor).delete(
            synchronize_session=False)
        db.session.commit()


def _account():
    acct = AcmeClientAccount(directory_url='https://dnsupd-test.example/directory',
                             label=f'T-{_uid()}', email='ops@example.com',
                             is_default=False)
    db.session.add(acct)
    db.session.commit()
    return acct


def _eab(status='active'):
    cred = AcmeEabCredential(kid=f'kid-{_uid()}', status=status)
    cred.hmac_key_b64 = 'aG1hYw'
    db.session.add(cred)
    db.session.commit()
    return cred


def _key(acct, name=None, eab=None, secret=B64):
    key = AcmeDnsUpdateKey(acme_client_account_id=acct.id,
                           eab_credential_id=eab.id if eab else None,
                           name=name or f'k{_uid()}.example.com.')
    key.secret = secret
    db.session.add(key)
    db.session.commit()
    return key


def _order(acct):
    order = AcmeClientOrder(domains=json.dumps(['x.example.com']), status='pending',
                            is_proxy_order=True, acme_client_account_id=acct.id)
    db.session.add(order)
    db.session.commit()
    return order


def _row(order, value='v' * 43, name='_acme-challenge.x.example.com.', acct=None):
    row = AcmeProxyDnsChallenge(
        order_id=order.id, acme_client_account_id=acct.id if acct else None,
        account_id='acc', client_jwk_thumbprint='tp', identifier='x.example.com',
        record_name=name, txt_value=value, zone_name='example.com.',
        expires_at=utc_now() + timedelta(hours=1))
    db.session.add(row)
    db.session.commit()
    return row


# --- K2 / K7 ---

def test_K2_secret_encrypted_at_rest_pos(app):
    with app.app_context():
        key = _key(_account())
        raw = db.session.execute(
            text("SELECT secret FROM acme_dns_update_keys WHERE id = :i"),
            {'i': key.id}).scalar()
        assert raw != B64 and B64 not in raw
        assert raw.startswith('gAAAAA')
        db.session.expire_all()
        assert db.session.get(AcmeDnsUpdateKey, key.id).secret == B64


def test_K2_corrupt_ciphertext_reads_none_neg(app):
    with app.app_context():
        key = _key(_account())
        stored = key._secret
        key._secret = stored[:-6] + 'AAAAAA'
        assert key.secret is None
        assert key.secret != key._secret


def test_K7_empty_or_plain_secret_reads_none_pos(app):
    with app.app_context():
        key = _key(_account())
        key._secret = ''
        assert key.secret is None
        key._secret = B64  # raw value, never returned
        assert key.secret is None


def test_K7_decrypt_failure_reads_none_neg(app, monkeypatch):
    with app.app_context():
        key = _key(_account())
        monkeypatch.setattr('utils.encryption.decrypt_value', lambda v: None)
        assert key.secret is None
        monkeypatch.setattr('utils.encryption.decrypt_value',
                            lambda v: (_ for _ in ()).throw(RuntimeError('x')))
        assert key.secret is None


def test_K7_empty_secret_cannot_be_stored_neg(app):
    with app.app_context():
        key = AcmeDnsUpdateKey(acme_client_account_id=1, name='a.example.')
        with pytest.raises(ValueError):
            key.secret = ''


# --- K5 ---

def test_K5_normalize_name_accepts_pos():
    assert AcmeDnsUpdateKey.normalize_name('Key1.Example.COM') == 'key1.example.com.'
    assert AcmeDnsUpdateKey.normalize_name(' key.example. ') == 'key.example.'
    assert AcmeDnsUpdateKey.normalize_name('a' * 63 + '.example.') == 'a' * 63 + '.example.'
    # Generated names (<slug>-<hex>.) and underscore labels stay valid.
    assert AcmeDnsUpdateKey.normalize_name('proxy-1-1a2b3c4d.') == 'proxy-1-1a2b3c4d.'
    assert AcmeDnsUpdateKey.normalize_name('_tsig.example.') == '_tsig.example.'
    # A non-ASCII name becomes IDNA (punycode): ASCII only, safe in the snippets.
    assert AcmeDnsUpdateKey.normalize_name('k\u00e4y.example.').isascii()


@pytest.mark.parametrize('bad', [
    'a' * 64 + '.example.com',
    '.'.join(['a' * 60] * 5),
    'a..b.example.',
    '.',
    '',
    '   ',
    '.example.com',
    # Characters that would act in the shell/PowerShell snippets of the clients.
    'a`id`.example.',
    "a'b.example.",
    'a|b.example.',
    'a&b.example.',
    'a b.example.',
    'a$b.example.',
    '-ab.example.',
    'ab-.example.',
])
def test_K5_normalize_name_rejects_neg(bad):
    with pytest.raises(ValueError):
        AcmeDnsUpdateKey.normalize_name(bad)


def test_K5_unique_name_pos_neg(app):
    with app.app_context():
        acct = _account()
        _key(acct, name=AcmeDnsUpdateKey.normalize_name('key.example.'))
        _key(acct, name=AcmeDnsUpdateKey.normalize_name('other.example.'))  # pos
        dup = AcmeDnsUpdateKey(acme_client_account_id=acct.id,
                               name=AcmeDnsUpdateKey.normalize_name('KEY.example.'))
        dup.secret = B64
        db.session.add(dup)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


# --- K3 ---

def test_K3_to_dict_has_metadata_pos(app):
    with app.app_context():
        key = _key(_account())
        d = key.to_dict()
        assert {'id', 'acme_client_account_id', 'eab_credential_id', 'eab_bound', 'name', 'algorithm',
                'status', 'created_at', 'created_by_user_id', 'last_used_at',
                'revoked_at', 'notes'} <= set(d)
        assert d['status'] == 'active' and d['algorithm'] == 'hmac-sha256'


def test_K3_to_dict_has_no_secret_neg(app):
    with app.app_context():
        key = _key(_account())
        d = key.to_dict()
        assert not any('secret' in k for k in d)
        assert B64 not in json.dumps(d) and key._secret not in json.dumps(d)


# --- K8 ---

@pytest.mark.parametrize('status', ['used', 'revoked'])
def test_K8_eab_delete_removes_linked_key_pos(app, auth_client, status):
    with app.app_context():
        acct = _account()
        cred = _eab(status)
        key = _key(acct, eab=cred)
        key_id, cred_id = key.id, cred.id
    resp = auth_client.delete(f'/api/v2/acme/eab-credentials/{cred_id}')
    assert resp.status_code in (200, 204)
    with app.app_context():
        assert db.session.get(AcmeDnsUpdateKey, key_id) is None


def test_K8_eab_soft_revoke_revokes_linked_key_pos(app, auth_client):
    # An active credential is only soft-revoked: its key stays, revoked (B5).
    with app.app_context():
        acct = _account()
        cred = _eab('active')
        key = _key(acct, eab=cred)
        key_id, cred_id = key.id, cred.id
    assert auth_client.delete(f'/api/v2/acme/eab-credentials/{cred_id}').status_code == 200
    with app.app_context():
        assert db.session.get(AcmeDnsUpdateKey, key_id).status == 'revoked'


def test_K8_eab_delete_keeps_other_keys_neg(app, auth_client):
    with app.app_context():
        acct = _account()
        cred, other = _eab('used'), _eab('used')
        _key(acct, eab=cred)
        kept = _key(acct, eab=other)
        no_eab = _key(acct)
        cred_id, kept_id, no_eab_id = cred.id, kept.id, no_eab.id
    assert auth_client.delete(f'/api/v2/acme/eab-credentials/{cred_id}').status_code in (200, 204)
    with app.app_context():
        assert db.session.get(AcmeDnsUpdateKey, kept_id) is not None
        assert db.session.get(AcmeDnsUpdateKey, no_eab_id) is not None


# --- K9 ---

def test_K9_account_delete_removes_keys_and_rows_pos(app, auth_client):
    with app.app_context():
        acct = _account()
        _key(acct)
        _row(_order(acct), acct=acct)
        acct_id = acct.id
    resp = auth_client.delete(f'/api/v2/acme/client/accounts/{acct_id}')
    assert resp.status_code == 200
    with app.app_context():
        assert AcmeDnsUpdateKey.query.filter_by(acme_client_account_id=acct_id).count() == 0
        assert AcmeProxyDnsChallenge.query.filter_by(acme_client_account_id=acct_id).count() == 0


def test_K9_account_delete_keeps_other_account_neg(app, auth_client):
    with app.app_context():
        acct, other = _account(), _account()
        _key(acct)
        kept = _key(other)
        row = _row(_order(other), acct=other)
        acct_id, kept_id, row_id = acct.id, kept.id, row.id
    assert auth_client.delete(f'/api/v2/acme/client/accounts/{acct_id}').status_code == 200
    with app.app_context():
        assert db.session.get(AcmeDnsUpdateKey, kept_id) is not None
        assert db.session.get(AcmeProxyDnsChallenge, row_id) is not None


def test_K9_new_account_inherits_no_key_neg(app, auth_client):
    with app.app_context():
        acct = _account()
        _key(acct)
        acct_id = acct.id
    assert auth_client.delete(f'/api/v2/acme/client/accounts/{acct_id}').status_code == 200
    with app.app_context():
        # Force id reuse in SQLite (no AUTOINCREMENT on the model table).
        fresh = AcmeClientAccount(id=acct_id, directory_url='https://dnsupd-test.example/d',
                                  label=f'N-{_uid()}', email='o@example.com')
        db.session.add(fresh)
        db.session.commit()
        assert AcmeDnsUpdateKey.query.filter_by(acme_client_account_id=fresh.id).count() == 0


# --- R model ---

def test_R_model_different_value_same_name_accepted_pos(app):
    with app.app_context():
        order = _order(_account())
        _row(order, value='a' * 43)
        _row(order, value='b' * 43)
        assert AcmeProxyDnsChallenge.query.filter_by(order_id=order.id).count() == 2


def test_R_model_duplicate_rejected_neg(app):
    with app.app_context():
        order = _order(_account())
        _row(order)
        with pytest.raises(IntegrityError):
            _row(order)
        db.session.rollback()


def test_R_model_zone_name_required_neg(app):
    with app.app_context():
        order = _order(_account())
        row = AcmeProxyDnsChallenge(
            order_id=order.id, client_jwk_thumbprint='tp', identifier='x.example.com',
            record_name='_acme-challenge.x.example.com.', txt_value='v' * 43,
            expires_at=utc_now())
        db.session.add(row)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_D1_eab_bound_defaults_false_and_is_in_dict_pos(app):
    with app.app_context():
        d = _key(_account()).to_dict()
        assert d['eab_bound'] is False


def test_D1_eab_bound_can_be_true_without_credential_neg(app):
    from models import db
    with app.app_context():
        key = _key(_account())
        key.eab_bound = True
        db.session.commit()
        assert key.eab_credential_id is None and key.to_dict()['eab_bound'] is True
