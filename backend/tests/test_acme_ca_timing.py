"""Per-CA ACME timing settings and authorization invalid handling."""
import json
from unittest.mock import MagicMock, patch

import pytest

from models import db, AcmeClientAccount
from services.acme.acme_client_service import AcmeClientService, AUTHZ_INVALID_USER_MSG


@pytest.fixture
def custom_ca_account(app):
    with app.app_context():
        AcmeClientAccount.query.delete()
        db.session.commit()
        acct = AcmeClientAccount(
            directory_url='https://acme.example.com/directory',
            label='Custom CA',
            email='admin@test.local',
            order_poll_timeout_sec=240,
            order_poll_interval_sec=5,
            http_timeout_sec=90,
            is_default=True,
        )
        db.session.add(acct)
        db.session.commit()
        yield acct
        db.session.delete(acct)
        db.session.commit()


def test_ca_account_to_dict_includes_timing(custom_ca_account):
    d = custom_ca_account.to_dict()
    assert d['order_poll_timeout_sec'] == 240
    assert d['order_poll_interval_sec'] == 5
    assert d['http_timeout_sec'] == 90


def test_patch_ca_timing(auth_client, custom_ca_account):
    res = auth_client.patch(
        f'/api/v2/acme/client/accounts/{custom_ca_account.id}',
        json={'order_poll_timeout_sec': 300, 'http_timeout_sec': 60},
    )
    assert res.status_code == 200
    data = res.get_json()['data']
    assert data['order_poll_timeout_sec'] == 300
    assert data['http_timeout_sec'] == 60


def test_patch_ca_timing_rejects_out_of_range(auth_client, custom_ca_account):
    res = auth_client.patch(
        f'/api/v2/acme/client/accounts/{custom_ca_account.id}',
        json={'order_poll_timeout_sec': 9999},
    )
    assert res.status_code == 400


def test_get_poll_settings_from_account(custom_ca_account):
    svc = AcmeClientService(account=custom_ca_account)
    assert svc.get_poll_settings() == {
        'order_poll_timeout_sec': 240,
        'order_poll_interval_sec': 5,
        'http_timeout_sec': 90,
    }


def test_verify_challenge_rejects_invalid_authz(app, custom_ca_account):
    svc = AcmeClientService(account=custom_ca_account)
    order = MagicMock()
    order.challenge_type = 'dns-01'
    order.challenges_dict = {
        'test.example.com': {
            'url': 'https://ca/challenge/1',
            'authz_url': 'https://ca/authz/1',
            'status': 'pending',
        }
    }
    order.set_challenges_dict = MagicMock()

    invalid_authz = {
        'status': 'invalid',
        'error': {'detail': 'DNS validation failed'},
        'challenges': [],
    }
    with patch.object(svc, '_post') as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: invalid_authz)
        ok, msg = svc.verify_challenge(order, 'test.example.com')
    assert ok is False
    assert AUTHZ_INVALID_USER_MSG in msg
