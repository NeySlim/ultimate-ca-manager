"""What a replacing restore leaves behind: names the archive gives, no ACME state without its account.

Each case runs on its own installation, on SQLite and on PostgreSQL (which enforces the keys).
"""
import json
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

import pytest

from models import db
from services.backup.export_generic import load_model
from services.backup.manifest import SECTIONS
from tests.test_backup_cross_installation import Keys, PASSWORD, _installation, _service
from tests.test_restore_replace_dependents import (
    ENGINES, _authority_row, _orphans, _restore, _snapshot, _target, _user,
)

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()


@pytest.fixture(params=ENGINES)
def target(request, app, tmp_path):
    schema = f'replace_matrix_{uuid.uuid4().hex[:12]}'
    with _target(app, request.param, tmp_path, schema):
        yield request.param


# -- names --------------------------------------------------------------------

T1, T2 = 'one', 'two'


def _webhook(name, thing):
    from services.webhook_service import WebhookEndpoint
    return WebhookEndpoint(name=name, url=f'https://hook-{thing}.example.test/', events='["*"]')


def _provider(name, thing):
    from models.acme_models import DnsProvider
    return DnsProvider(name=name, provider_type={T1: 'cloudflare', T2: 'route53'}[thing])


def _account(name, thing):
    from models.acme_client_account import AcmeClientAccount
    return AcmeClientAccount(label=name, email='ops@example.test',
                             directory_url=f'https://ca-{thing}.example.test/directory',
                             account_url=f'https://ca-{thing}.example.test/acct/1',
                             proxy_slug=f'slug-{thing}')


def _domain_on(provider):
    from models.acme_models import AcmeDomain
    row = AcmeDomain(domain='matrix.example.test', dns_provider_id=provider.id)
    db.session.add(row)
    return row


def _update_key_on(account):
    from models.acme_dns_update import AcmeDnsUpdateKey
    row = AcmeDnsUpdateKey(acme_client_account_id=account.id, name='matrix-key.example.test.')
    row.secret = 'c2VjcmV0LXNlY3JldC1zZWNyZXQtc2VjcmV0'
    db.session.add(row)
    return row


@dataclass(frozen=True)
class _Table:
    section: str
    column: str
    make: Callable
    thing: Callable              # the row's identity, names aside, as T1 or T2
    archived_as: Callable        # edits an archived row into the other thing
    # A row of another section that cannot exist without one of these: (make, holder of)
    dependent: Optional[tuple] = None
    # Whether a row is found again under another name (names.py RULES key)
    keyed: bool = True

    def model(self):
        return load_model(SECTIONS[self.section])


def _hook_thing(row):
    return T1 if 'hook-one' in row.url else T2


def _provider_thing(row):
    return T1 if row.provider_type == 'cloudflare' else T2


def _account_thing(row):
    return T1 if 'ca-one' in row.directory_url else T2


def _as_second_hook(row):
    row['url'] = 'https://hook-two.example.test/'


def _as_second_provider(row):
    row['provider_type'] = 'route53'


def _as_second_account(row):
    row['directory_url'] = 'https://ca-two.example.test/directory'
    row['account_url'] = 'https://ca-two.example.test/acct/1'
    row['proxy_slug'] = 'slug-two'


def _provider_of(domain):
    from models.acme_models import DnsProvider
    return db.session.get(DnsProvider, domain.dns_provider_id)


def _account_of(key):
    from models.acme_client_account import AcmeClientAccount
    return db.session.get(AcmeClientAccount, key.acme_client_account_id)


TABLES = {
    'webhook_endpoints': _Table('webhook_endpoints', 'name', _webhook, _hook_thing,
                                _as_second_hook),
    'dns_providers': _Table('dns_providers', 'name', _provider, _provider_thing,
                            _as_second_provider, (_domain_on, _provider_of), keyed=False),
    'acme_client_accounts': _Table('acme_client_accounts', 'label', _account, _account_thing,
                                   _as_second_account, (_update_key_on, _account_of)),
}

N, M = 'matrix', 'matrix-renamed'
SUFFIXED = f'{N} (2)'
HELD_HERE = 'name held here by a different row'
HELD_IN_ARCHIVE = 'name held by another row of the archive'


def _expected(mode, table, collision, kept):
    """(rows after the restore as (name, thing), renamed as (from, to, reason))."""
    if collision == 'same_thing_other_name':
        if mode == 'replace':
            return [(N, T1)], []
        if table.keyed:
            return [(M, T1)], [(N, M, 'same row here under this name')]
        return sorted([(M, T1), (N, T1)]), []
    if collision == 'same_name_other_thing':
        if mode == 'replace' and kept != 'yes':
            return [(N, T1)], []
        both = [(N, T2), (SUFFIXED, T1)] if mode == 'merge' else [(SUFFIXED, T1)]
        return sorted(both), [(N, SUFFIXED, HELD_HERE)]
    if collision == 'archive_duplicate':
        return sorted([(N, T1), (SUFFIXED, T2)]), [(N, SUFFIXED, HELD_IN_ARCHIVE)]
    return [(N, T1)], []     # same name same thing, or no collision at all


def _cases():
    for mode in ('merge', 'replace'):
        for name, table in TABLES.items():
            for collision in ('same_name_same_thing', 'same_thing_other_name',
                              'same_name_other_thing', 'archive_duplicate', 'none'):
                # A kept row can need the row holding the name, or the same thing renamed here
                if (collision in ('same_name_other_thing', 'same_thing_other_name')
                        and table.dependent):
                    kepts = ('yes', 'no')
                else:
                    kepts = ('n/a',)
                for kept in kepts:
                    yield pytest.param(mode, name, collision, kept,
                                       id=f'{mode}-{name}-{collision}-kept_{kept}')


def _duplicated(blob, table):
    """The archive with a second row of the same name, another thing: an archive older than 124."""
    from tests.test_backup_hostile_corpus import _reseal
    _key, data = _service()._decrypt_framed(blob, PASSWORD)
    rows = data[table.section]
    twin = dict(next(r for r in rows if r[table.column] == N))
    table.archived_as(twin)
    rows.append(twin)
    return _reseal(blob, data)


@pytest.mark.parametrize('mode,table_name,collision,kept', list(_cases()))
def test_every_restored_row_bears_the_name_the_archive_gives(target, mode, table_name,
                                                             collision, kept):
    table = TABLES[table_name]
    model = table.model()
    _user('replace-admin')
    archived = table.make(N, T1)
    db.session.add(archived)
    db.session.flush()
    archived_id = archived.id
    dependent = None
    if kept == 'yes':
        dependent = table.dependent[0](archived)
        db.session.flush()
    blob = _snapshot()

    if collision == 'same_thing_other_name':
        setattr(archived, table.column, M)
    elif collision == 'same_name_other_thing':
        holder = table.make(f'{N}-here', T2)
        db.session.add(holder)
        db.session.flush()
        if dependent is not None:
            setattr(dependent, 'dns_provider_id' if table_name == 'dns_providers'
                    else 'acme_client_account_id', holder.id)
            db.session.flush()
        db.session.delete(archived)
        db.session.flush()
        setattr(holder, table.column, N)
    elif collision in ('archive_duplicate', 'none'):
        db.session.delete(archived)
        if collision == 'archive_duplicate':
            blob = _duplicated(blob, table)
    db.session.commit()

    results = _restore(blob, mode=mode)

    rows = model.query.all()
    names = [getattr(row, table.column) for row in rows]
    assert len(names) == len(set(names)), names
    expected_rows, expected_renamed = _expected(mode, table, collision, kept)
    assert sorted((getattr(row, table.column), table.thing(row)) for row in rows) == expected_rows
    assert sorted((entry['from'], entry['to'], entry['reason'])
                  for entry in results['renamed']) == sorted(expected_renamed)
    if collision == 'same_name_same_thing' or (
            collision == 'same_thing_other_name' and mode == 'replace' and table.keyed):
        assert [row.id for row in rows] == [archived_id]    # updated in place
    if kept == 'yes':
        restored = type(dependent).query.one()
        assert table.thing(table.dependent[1](restored)) == T1
    assert _orphans() == []


@pytest.mark.parametrize('table_name', ['webhook_endpoints', 'acme_client_accounts'])
def test_a_renamed_row_takes_its_name_back_from_another_thing(target, table_name):
    """Renamed here, its archived name now held by another thing: the holder goes."""
    table = TABLES[table_name]
    _user('replace-admin')
    archived = table.make(N, T1)
    db.session.add(archived)
    db.session.flush()
    archived_id = archived.id
    if table_name == 'acme_client_accounts':
        _update_key_on(archived)     # kept by the archive: the account cannot go first
    blob = _snapshot()
    setattr(archived, table.column, M)
    db.session.flush()
    db.session.add(table.make(N, T2))
    db.session.commit()

    results = _restore(blob)

    rows = table.model().query.all()
    assert [(row.id, getattr(row, table.column), table.thing(row)) for row in rows] == [
        (archived_id, N, T1)]
    assert results['renamed'] == []
    assert _orphans() == []


def test_a_webhook_renamed_in_place_keeps_its_deliveries(target):
    """The id alone proves nothing on SQLite, which gives a deleted id back: the deliveries do."""
    from models.webhook_delivery import WebhookDelivery
    _user('replace-admin')
    hook = _webhook(N, T1)
    db.session.add(hook)
    db.session.flush()
    blob = _snapshot()
    hook.name = M
    db.session.add(WebhookDelivery(endpoint_id=hook.id, event_type='certificate.issued',
                                   payload='{}', event_timestamp='2026-01-01T00:00:00Z'))
    db.session.commit()

    _restore(blob)

    try:
        assert [(row.name, _hook_thing(row)) for row in TABLES['webhook_endpoints'].model().query.all()] == [
            (N, T1)]
        assert WebhookDelivery.query.count() == 1
    finally:
        WebhookDelivery.query.delete()
        db.session.commit()


@pytest.mark.parametrize('table_name', ['webhook_endpoints', 'acme_client_accounts'])
def test_two_rows_that_traded_names_take_the_archives_back(target, table_name):
    table = TABLES[table_name]
    _user('replace-admin')
    first, second = table.make(N, T1), table.make(M, T2)
    db.session.add_all([first, second])
    db.session.flush()
    ids = {T1: first.id, T2: second.id}
    blob = _snapshot()
    setattr(first, table.column, 'trading')
    db.session.flush()
    setattr(second, table.column, N)
    db.session.flush()
    setattr(first, table.column, M)
    db.session.commit()

    results = _restore(blob)

    rows = table.model().query.all()
    assert sorted((getattr(row, table.column), table.thing(row), row.id) for row in rows) == sorted(
        [(N, T1, ids[T1]), (M, T2, ids[T2])])
    assert results['renamed'] == []
    assert _orphans() == []


@pytest.mark.parametrize('table_name', ['webhook_endpoints', 'acme_client_accounts'])
def test_three_rows_whose_names_went_round_take_the_archives_back(target, table_name):
    """a->b->c->a: each kept row is renamed in place. What points at each row proves it was
    not removed and written again, which a reused id on SQLite would hide."""
    from models.acme_dns_update import AcmeDnsUpdateKey
    from models.webhook_delivery import WebhookDelivery
    table = TABLES[table_name]
    _user('replace-admin')
    things = (T1, T2, 'three')
    rows = {thing: table.make(name, thing) for thing, name in zip(things, 'abc')}
    db.session.add_all(rows.values())
    db.session.flush()
    ids = {thing: row.id for thing, row in rows.items()}
    keys = {}
    if table_name == 'acme_client_accounts':
        for thing, row in rows.items():
            key = AcmeDnsUpdateKey(acme_client_account_id=row.id, name=f'cycle-{thing}.example.test.')
            key.secret = 'c2VjcmV0LXNlY3JldC1zZWNyZXQtc2VjcmV0'
            db.session.add(key)
            db.session.flush()
            keys[key.id] = thing
    blob = _snapshot()
    for thing, name in ((T1, 'tmp'), ('three', 'a'), (T2, 'c'), (T1, 'b')):
        setattr(rows[thing], table.column, name)
        db.session.flush()
    if table_name == 'webhook_endpoints':
        db.session.add_all(WebhookDelivery(endpoint_id=ids[thing], event_type='certificate.issued',
                                           payload=json.dumps({'thing': thing}),
                                           event_timestamp='2026-01-01T00:00:00Z') for thing in things)
    db.session.commit()

    try:
        results = _restore(blob)

        assert _state(table) == sorted(zip('abc', things, (ids[t] for t in things)))
        assert results['renamed'] == []
        if table_name == 'webhook_endpoints':
            held = {(json.loads(d.payload)['thing'], d.endpoint_id) for d in WebhookDelivery.query}
            assert held == {(thing, ids[thing]) for thing in things}
        else:
            held = {(k.id, _thing_of(_account_of(k))) for k in AcmeDnsUpdateKey.query}
            assert held == set(keys.items())
        assert _orphans() == []
    finally:
        WebhookDelivery.query.delete()
        db.session.commit()


def _named_in_archive(blob, table, thing, name):
    """The archive with the row of that thing under `name`: an archive older than 124."""
    from tests.test_backup_hostile_corpus import _reseal
    _key, data = _service()._decrypt_framed(blob, PASSWORD)
    row = next(r for r in data[table.section]
               if any(f'-{thing}.' in str(value) for value in r.values()))
    row[table.column] = name
    return _reseal(blob, data)


def _thing_of(row):
    return next(thing for thing in (T1, T2, 'three')
                if f'-{thing}.' in (getattr(row, 'url', None) or getattr(row, 'directory_url', '')))


def _state(table):
    return sorted((getattr(row, table.column), _thing_of(row), row.id)
                  for row in table.model().query.all())


def _renamed(results):
    return sorted((e['from'], e['to'], e['reason']) for e in results['renamed'])


SAME_HERE = 'same row here under this name'


@pytest.mark.parametrize('table_name', ['webhook_endpoints', 'acme_client_accounts'])
def test_a_name_kept_here_by_a_row_that_cannot_move_is_not_taken(target, table_name):
    """T2 cannot take X (another archived row has it), so T1 cannot take N from T2."""
    table = TABLES[table_name]
    _user('replace-admin')
    one, two, three = table.make(N, T1), table.make('x', T2), table.make('y', 'three')
    db.session.add_all([one, two, three])
    db.session.flush()
    ids = {T1: one.id, T2: two.id, 'three': three.id}
    blob = _named_in_archive(_snapshot(), table, 'three', 'x')
    for row, name in ((two, 'tmp'), (three, 'x'), (one, M), (two, N)):
        setattr(row, table.column, name)
        db.session.flush()
    db.session.commit()

    results = _restore(blob)

    assert _state(table) == sorted([(M, T1, ids[T1]), (N, T2, ids[T2]),
                                    ('x', 'three', ids['three'])])
    assert _renamed(results) == sorted([(N, M, SAME_HERE), ('x', N, SAME_HERE)])
    assert _orphans() == []


@pytest.mark.parametrize('table_name', ['webhook_endpoints', 'acme_client_accounts'])
def test_two_renamed_rows_wanting_one_archived_name_do_not_both_take_it(target, table_name):
    table = TABLES[table_name]
    _user('replace-admin')
    one, two = table.make(N, T1), table.make('z', T2)
    db.session.add_all([one, two])
    db.session.flush()
    ids = {T1: one.id, T2: two.id}
    blob = _named_in_archive(_snapshot(), table, T2, N)
    setattr(one, table.column, 'a')
    setattr(two, table.column, 'b')
    db.session.commit()

    results = _restore(blob)

    assert _state(table) == sorted([(N, T1, ids[T1]), ('b', T2, ids[T2])])
    assert _renamed(results) == [(N, 'b', SAME_HERE)]
    assert _orphans() == []


@pytest.mark.parametrize('table_name', ['webhook_endpoints', 'acme_client_accounts'])
def test_the_name_a_renamed_row_leaves_is_free_for_the_archive(target, table_name):
    table = TABLES[table_name]
    _user('replace-admin')
    one, other = table.make(N, T1), table.make(M, 'three')
    db.session.add_all([one, other])
    db.session.flush()
    one_id = one.id
    blob = _snapshot()
    db.session.delete(other)
    db.session.flush()
    setattr(one, table.column, M)
    db.session.commit()

    results = _restore(blob)

    assert [(name, thing) for name, thing, _id in _state(table)] == sorted(
        [(N, T1), (M, 'three')])
    assert db.session.get(table.model(), one_id).__getattribute__(table.column) == N
    assert results['renamed'] == []
    assert _orphans() == []


def test_a_name_a_kept_row_needs_here_is_not_taken_by_a_renamed_row(target):
    """The holder of N carries a kept update key: N stays with it until the writes."""
    table = TABLES['acme_client_accounts']
    _user('replace-admin')
    one = table.make(N, T1)
    db.session.add(one)
    db.session.flush()
    one_id = one.id
    key = _update_key_on(one)
    db.session.flush()
    blob = _snapshot()
    setattr(one, table.column, M)
    holder = table.make(N, T2)
    db.session.add(holder)
    db.session.flush()
    key.acme_client_account_id = holder.id
    db.session.commit()

    results = _restore(blob)

    assert _state(table) == [(M, T1, one_id)]
    assert _renamed(results) == [(N, M, SAME_HERE)]
    assert _account_of(type(key).query.one()).id == one_id
    assert _orphans() == []


# -- ACME server state --------------------------------------------------------

STATES = ('order', 'valid_authorization', 'pre_authorization', 'challenge')


def _acme_account(token):
    from models.acme_models import AcmeAccount
    row = AcmeAccount(account_id=token, jwk=json.dumps({'kty': 'EC', 'kid': token}),
                      jwk_thumbprint=f'thumb-{token}', status='valid')
    db.session.add(row)
    db.session.flush()
    return row


def _acme_state(token, state):
    """In-flight protocol rows of one account: {table: [protocol id, ...]}."""
    from models.acme_models import AcmeAuthorization, AcmeChallenge, AcmeOrder
    identifier = json.dumps({'type': 'dns', 'value': 'matrix.example.test'})
    made = {}
    order = None
    if state != 'pre_authorization':
        order = AcmeOrder(account_id=token, status='pending', identifiers=f'[{identifier}]')
        db.session.add(order)
        db.session.flush()
        made['acme_orders'] = [order.order_id]
    if state == 'order':
        return made
    # Linked by its order alone, by its account alone (RFC 8555 §7.4.1), or by both
    authorization = AcmeAuthorization(
        order_id=order.order_id if order else None,
        account_id=None if state == 'valid_authorization' else token,
        identifier=identifier, status='pending' if state == 'challenge' else 'valid')
    db.session.add(authorization)
    db.session.flush()
    made['acme_authorizations'] = [authorization.authorization_id]
    if state == 'challenge':
        challenge = AcmeChallenge(authorization_id=authorization.authorization_id,
                                  type='http-01', status='pending')
        db.session.add(challenge)
        db.session.flush()
        made['acme_challenges'] = [challenge.challenge_id]
    return made


def _protocol_rows():
    from models.acme_models import AcmeAuthorization, AcmeChallenge, AcmeOrder
    return {
        'acme_orders': {(r.order_id, r.account_id, r.status) for r in AcmeOrder.query},
        'acme_authorizations': {(r.authorization_id, r.order_id, r.account_id, r.status)
                                for r in AcmeAuthorization.query},
        'acme_challenges': {(r.challenge_id, r.authorization_id, r.status)
                            for r in AcmeChallenge.query},
    }


def _archive_of_another_installation(app, directory, token=None):
    """A full archive written by an installation of its own, holding this account or none."""
    db.session.commit()
    keys = Keys(directory, 'matrix-source')
    with _installation(app, f"sqlite:///{directory / 'source.db'}", keys), app.app_context():
        _user('replace-admin')
        if token is not None:
            _acme_account(token)
        blob = _snapshot()
    return blob


@pytest.mark.parametrize('archive', ['same_older', 'other'])
@pytest.mark.parametrize('state', STATES)
@pytest.mark.parametrize('account', ['kept', 'removed'])
def test_no_acme_server_state_outlives_its_account(target, app, tmp_path, archive, state,
                                                   account):
    token = f'matrix-{uuid.uuid4().hex[:16]}'
    _user('replace-admin')
    blob = None
    if archive == 'same_older':
        if account == 'kept':
            _acme_account(token)
        blob = _snapshot()
    if not (archive == 'same_older' and account == 'kept'):
        _acme_account(token)
    made = _acme_state(token, state)
    db.session.commit()
    before = _protocol_rows()
    if archive == 'other':
        blob = _archive_of_another_installation(
            app, tmp_path, token if account == 'kept' else None)

    results = _restore(blob)

    after = _protocol_rows()
    cleared = {k: v for k, v in results['cleared_dependents'].items() if k.startswith('acme_')}
    if account == 'kept':
        assert after == before
        assert cleared == {}
    else:
        assert after == {name: set() for name in after}
        assert cleared == {name: len(ids) for name, ids in made.items()}
    assert _orphans() == []


# -- legacy CRL rows ----------------------------------------------------------

def test_a_legacy_crl_row_goes_with_its_removed_authority(target):
    from models.crl_list import CRL

    _user('replace-admin')
    kept, _key, _cert = _authority_row('replace-crl-kept')
    db.session.add(CRL(caref=kept.refid, descr='kept', text='x'))
    blob = _snapshot()
    gone, _key, _cert = _authority_row('replace-crl-gone')
    db.session.add(CRL(caref=gone.refid, descr='gone', text='x'))
    db.session.commit()

    results = _restore(blob)

    assert [(row.caref, row.descr) for row in CRL.query.all()] == [('replace-crl-kept', 'kept')]
    assert results['cleared_dependents'].get('crls') == 1
    assert _orphans() == []
