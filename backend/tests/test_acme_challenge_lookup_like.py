"""The challenge a POST names is the one at the request URL (RFC 8555 section 7.5.1):
% and _ in the path are characters, never LIKE wildcards matching another account's challenge."""
import json
import secrets

import pytest

from models import db
from models.acme_models import AcmeAccount, AcmeAuthorization, AcmeChallenge, AcmeOrder
from tests.test_acme_security_paths import _build_jws, _gen_key_and_jwk, _nonce, _thumbprint

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


@pytest.fixture
def victim_challenge(app):
    """A pending challenge of an account the caller does not hold."""
    _key, jwk = _gen_key_and_jwk()
    with app.app_context():
        acct = AcmeAccount(jwk=json.dumps(jwk), jwk_thumbprint=_thumbprint(jwk), status='valid')
        db.session.add(acct)
        db.session.commit()
        order = AcmeOrder(account_id=acct.account_id, status='pending',
                          identifiers=json.dumps([{'type': 'dns', 'value': 'v.example.com'}]))
        db.session.add(order)
        db.session.commit()
        authz = AcmeAuthorization(order_id=order.order_id, account_id=acct.account_id,
                                  identifier=json.dumps({'type': 'dns', 'value': 'v.example.com'}),
                                  status='pending')
        db.session.add(authz)
        db.session.commit()
        # Hex only: the id holds no _ or - of its own
        chall = AcmeChallenge(challenge_id=f'r31a{secrets.token_hex(12)}',
                              authorization_id=authz.authorization_id, type='http-01',
                              status='pending', url='http://localhost/acme/challenge/placeholder')
        db.session.add(chall)
        db.session.commit()
        chall.url = f'http://localhost/acme/challenge/{chall.challenge_id}'
        db.session.commit()
        ids = (chall.challenge_id, authz.authorization_id, order.order_id, acct.account_id)
    yield ids[0]
    with app.app_context():
        AcmeChallenge.query.filter_by(challenge_id=ids[0]).delete()
        AcmeAuthorization.query.filter_by(authorization_id=ids[1]).delete()
        AcmeOrder.query.filter_by(order_id=ids[2]).delete()
        AcmeAccount.query.filter_by(account_id=ids[3]).delete()
        db.session.commit()


def _probe(client, path_id):
    key, jwk = _gen_key_and_jwk()
    jws = _build_jws(f'http://localhost/acme/challenge/{path_id}', {}, key, jwk=jwk,
                     nonce=_nonce(client))
    return client.post(f'/acme/challenge/{path_id}', data=json.dumps(jws),
                       content_type='application/jose+json')


@pytest.mark.parametrize('pattern', ['%25', '{first}%25', '_{rest}'])
def test_a_wildcard_in_the_path_finds_no_other_challenge(client, victim_challenge, pattern):
    path_id = pattern.format(first=victim_challenge[:1], rest=victim_challenge[1:])
    r = _probe(client, path_id)
    assert r.status_code == 404, r.get_data(as_text=True)
    assert 'Challenge not found' in r.get_json()['detail']
    assert victim_challenge not in r.get_data(as_text=True)


def test_the_exact_id_is_still_found(client, victim_challenge):
    r = _probe(client, victim_challenge)
    # Found, then refused for the JWS of a key that is no account
    assert 'Challenge not found' not in r.get_json()['detail'], r.get_json()
