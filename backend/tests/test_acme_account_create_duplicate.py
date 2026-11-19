"""Creating a local ACME account refuses an e-mail already used, and only that one.

`_` and `%` in the new address are literal characters, not LIKE wildcards.
"""
import json
import uuid

import pytest

from models import db, AcmeAccount, SystemConfig


@pytest.fixture
def existing(app):
    def make(email):
        with app.app_context():
            db.session.add(AcmeAccount(jwk='{}', jwk_thumbprint=f'dup-{uuid.uuid4().hex[:12]}',
                                       status='valid', contact=json.dumps([f'mailto:{email}'])))
            db.session.commit()
    yield make
    with app.app_context():
        rows = AcmeAccount.query.filter(db.func.lower(AcmeAccount.contact).like('%@dup-check.example.test%')).all()
        for row in rows:
            SystemConfig.query.filter_by(key=f'acme.account.{row.account_id}.private_key').delete()
            db.session.delete(row)
        db.session.commit()


def _create(auth_client, email):
    return auth_client.post('/api/v2/acme/accounts', json={'email': email, 'agree_tos': True})


@pytest.mark.parametrize('stored, asked', [
    ('axb@dup-check.example.test', 'a_b@dup-check.example.test'),
    ('a_b@dup-check.example.test', 'axb@dup-check.example.test'),
    ('ab@dup-check.example.test', 'a%b@dup-check.example.test'),
])
def test_a_wildcard_character_is_not_a_duplicate(auth_client, existing, stored, asked):
    existing(stored)
    r = _create(auth_client, asked)
    assert r.status_code == 200, r.data[:300]


def test_the_same_address_is_a_duplicate(auth_client, existing):
    existing('same@dup-check.example.test')
    r = _create(auth_client, 'same@dup-check.example.test')
    assert r.status_code == 409, r.data[:300]


def test_an_address_that_ends_another_is_not_a_duplicate(auth_client, existing):
    existing('ab@dup-check.example.test')
    r = _create(auth_client, 'b@dup-check.example.test')
    assert r.status_code == 200, r.data[:300]


def test_an_address_inside_another_is_not_a_duplicate(auth_client, existing):
    existing('same@dup-check.example.test.other')
    r = _create(auth_client, 'same@dup-check.example.test')
    assert r.status_code == 200, r.data[:300]


@pytest.mark.parametrize('stored, asked', [
    ('case@dup-check.example.test', 'CASE@DUP-CHECK.example.test'),
    ('UPPER@DUP-CHECK.example.test', 'upper@dup-check.example.test'),
])
def test_the_same_address_in_another_case_is_a_duplicate(auth_client, existing, stored, asked):
    existing(stored)
    r = _create(auth_client, asked)
    assert r.status_code == 409, r.data[:300]


def test_an_address_among_several_contacts_is_a_duplicate(app, auth_client, existing):
    with app.app_context():
        db.session.add(AcmeAccount(
            jwk='{}', jwk_thumbprint=f'dup-{uuid.uuid4().hex[:12]}', status='valid',
            contact=json.dumps(['mailto:first@dup-check.example.test', 'mailto:second@dup-check.example.test'])))
        db.session.commit()
    r = _create(auth_client, 'second@dup-check.example.test')
    assert r.status_code == 409, r.data[:300]
