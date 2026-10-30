"""Every DNS-01 TXT write and cleanup runs under the per-name lock, not only the proxy publish."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.acme import acme_client_service as client_mod
from services.acme import acme_proxy_service as proxy_mod
from services.acme.acme_client_service import AcmeClientService
from services.acme.acme_proxy_service import AcmeProxyService

NAME = '_acme-challenge.example.com'


@pytest.fixture
def held():
    names = []

    @contextmanager
    def _recording(name):
        names.append(name)
        yield
        names.remove(name)
    return names, _recording


def _provider(held_names, calls):
    provider = MagicMock()
    provider.create_txt_record.side_effect = lambda *a, **k: calls.append(('create', list(held_names))) or (True, 'ok')
    provider.delete_txt_record.side_effect = lambda *a, **k: calls.append(('delete', list(held_names))) or (True, 'ok')
    return provider


def _order(provider_id):
    return SimpleNamespace(challenge_type='dns-01', dns_provider_id=provider_id,
                           challenges_dict={'*.example.com': {'dns_txt_name': NAME, 'dns_txt_value': 'v'}})


def test_client_setup_and_cleanup_hold_the_lock(app, monkeypatch, held):
    from models import db
    from models.acme_models import DnsProvider

    names, recording = held
    calls = []
    monkeypatch.setattr(client_mod, 'txt_record_lock', recording)
    monkeypatch.setattr(client_mod, 'create_provider', lambda *_a: _provider(names, calls))
    svc = AcmeClientService.__new__(AcmeClientService)
    with app.app_context():
        row = DnsProvider(name='lock-paths', provider_type='cloudflare', credentials='{}')
        db.session.add(row)
        db.session.commit()
        ok, _msg, _info = svc.setup_dns_challenge(_order(row.id))
        assert ok
        assert svc.cleanup_dns_challenge(_order(row.id))[0]
    assert calls == [('create', [NAME]), ('delete', [NAME])]


def test_proxy_cleanup_holds_the_lock(monkeypatch, held):
    names, recording = held
    calls = []
    monkeypatch.setattr(proxy_mod, '_txt_record_lock', recording)
    AcmeProxyService._delete_dns_record(_provider(names, calls), 'example.com', NAME)
    assert calls == [('delete', [NAME])]
