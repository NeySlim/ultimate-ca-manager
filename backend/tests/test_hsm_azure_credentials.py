"""Azure Key Vault uses the credentials typed in the form.

The form sends tenant, client id and secret but never `use_managed_identity`,
which defaulted to true: the provider authenticated with the ambient identity
and the typed credentials were ignored.
"""
from unittest.mock import MagicMock

import pytest

from services.hsm import azure_provider
from services.hsm.base_provider import HsmConfigError

pytestmark = pytest.mark.skipif(not azure_provider.AZURE_AVAILABLE, reason='azure libraries not installed')

VAULT = 'https://example-vault.vault.azure.net/'


def _connect(monkeypatch, config):
    default, secret = MagicMock(name='DefaultAzureCredential'), MagicMock(name='ClientSecretCredential')
    monkeypatch.setattr(azure_provider, 'DefaultAzureCredential', default)
    monkeypatch.setattr(azure_provider, 'ClientSecretCredential', secret)
    monkeypatch.setattr(azure_provider, 'KeyClient', MagicMock())
    azure_provider.AzureKeyVaultProvider({'vault_url': VAULT, **config}).connect()
    return default, secret


def test_typed_credentials_are_used(monkeypatch):
    default, secret = _connect(monkeypatch, {
        'tenant_id': 'tenant', 'client_id': 'client', 'client_secret': 's3cret'})
    secret.assert_called_once_with(tenant_id='tenant', client_id='client', client_secret='s3cret')
    default.assert_not_called()


def test_no_credentials_uses_the_ambient_identity(monkeypatch):
    default, secret = _connect(monkeypatch, {})
    default.assert_called_once()
    secret.assert_not_called()


def test_explicit_managed_identity_still_wins(monkeypatch):
    default, secret = _connect(monkeypatch, {
        'use_managed_identity': True, 'tenant_id': 't', 'client_id': 'c', 'client_secret': 's'})
    default.assert_called_once()
    secret.assert_not_called()


def test_partial_credentials_are_refused():
    with pytest.raises(HsmConfigError):
        azure_provider.AzureKeyVaultProvider({'vault_url': VAULT, 'tenant_id': 't', 'client_id': 'c'})
