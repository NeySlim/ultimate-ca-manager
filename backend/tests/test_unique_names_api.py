"""A name already taken is refused with 409, on creation and on rename (migration 124)."""
import uuid
from tests.acme_rows import delete_client_accounts

import pytest

from models import db
from models.acme_client_account import AcmeClientAccount
from models.acme_models import DnsProvider
from services.webhook_service import WebhookEndpoint


def _name(kind):
    return f'uniq-{kind}-{uuid.uuid4().hex[:8]}'


KINDS = {
    'dns': dict(
        collection='/api/v2/dns-providers', rename='patch', field='name', model=DnsProvider,
        body=lambda name: {'name': name, 'provider_type': 'manual', 'credentials': {}}),
    'webhook': dict(
        collection='/api/v2/webhooks', rename='put', field='name', model=WebhookEndpoint,
        body=lambda name: {'name': name, 'url': 'https://hooks.example.com/unique',
                           'events': ['certificate.issued']}),
    'acme_account': dict(
        collection='/api/v2/acme/client/accounts', rename='patch', field='label',
        model=AcmeClientAccount,
        body=lambda name: {'label': name, 'directory_url': 'https://acme.example.com/directory',
                           'email': 'ops@example.com'}),
}


@pytest.mark.parametrize('kind', sorted(KINDS))
def test_a_taken_name_is_refused(app, auth_client, kind):
    spec = KINDS[kind]
    first, second = _name(kind), _name(kind)
    created = [auth_client.post(spec['collection'], json=spec['body'](n)) for n in (first, second)]
    assert [r.status_code for r in created] == [201, 201], created[0].data[:300]
    ids = [r.get_json()['data']['id'] for r in created]
    try:
        again = auth_client.post(spec['collection'], json=spec['body'](first))
        assert again.status_code == 409, again.data[:300]

        rename = getattr(auth_client, spec['rename'])
        clash = rename(f"{spec['collection']}/{ids[1]}", json={spec['field']: first})
        assert clash.status_code == 409, clash.data[:300]
        same = rename(f"{spec['collection']}/{ids[0]}", json={spec['field']: first})
        assert same.status_code == 200, same.data[:300]

        with app.app_context():
            column = getattr(spec['model'], spec['field'])
            assert spec['model'].query.filter(column.in_([first, second])).count() == 2
            assert getattr(db.session.get(spec['model'], ids[1]), spec['field']) == second
    finally:
        with app.app_context():
            spec['model'].query.filter(spec['model'].id.in_(ids)).delete(
                synchronize_session=False)
            db.session.commit()


def test_a_placeholder_account_does_not_take_an_operator_label(app, caplog):
    from services.acme.acme_client_service import AcmeClientService

    directory = f'https://{uuid.uuid4().hex[:12]}.example/directory'
    label = f'Custom ({directory[:40]})'
    with app.app_context():
        mine = AcmeClientAccount(directory_url='https://elsewhere.example/directory',
                                 label=label, email='ops@example.com')
        db.session.add(mine)
        db.session.commit()
        ids = [mine.id]
        try:
            account = AcmeClientService._resolve_account(None, directory, None)
            ids.append(account.id)
            assert (account.label, account.directory_url) == (f'{label} (2)', directory)
            assert f'Created placeholder ACME account: {label} (2) ({directory})' in caplog.text
        finally:
            db.session.rollback()
            delete_client_accounts(AcmeClientAccount.query.filter(AcmeClientAccount.id.in_(ids)), synchronize_session=False)
            db.session.commit()
