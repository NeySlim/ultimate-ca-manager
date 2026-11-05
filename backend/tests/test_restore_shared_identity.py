"""Two rows here sharing an identity: the oldest is the archive's, the others are told and dealt with.

The index of the restore plan kept one row per identity, whichever the query
returned last: the archive could land on either, and the other was neither
updated nor removed by a replacing restore, without a word.
"""
import pytest
from sqlalchemy import UniqueConstraint
from sqlalchemy import inspect as sa_inspect

from models import db
from services.backup import manifest
from services.backup.export_generic import IdentityIndex, export_section, load_model
from services.backup.restore import RestorePlan
from services.backup.restore.replace import replace_sections, rows_to_remove
from tests.test_backup_contract_matrix import _any_existing, _remove, _seed_all, _value_for


def _identity_without_unique_constraint(name):
    section = manifest.SECTIONS[name]
    table = load_model(section).__table__
    uniques = [{c.name} for c in table.columns if c.unique or c.primary_key]
    uniques += [{c.name for c in i.columns} for i in table.indexes if i.unique]
    uniques += [{c.name for c in k.columns} for k in table.constraints if isinstance(k, UniqueConstraint)]
    return not any(u <= set(section.identity) for u in uniques)


SHARED = sorted(name for name, section in manifest.SECTIONS.items()
                if isinstance(section.identity, tuple) and section.identity != ('id',)
                and name not in ('configuration', 'https_server')
                and _identity_without_unique_constraint(name))


def test_the_sections_whose_identity_the_database_does_not_hold():
    assert SHARED == [
        'acme_client_orders', 'approval_requests', 'audit_logs', 'auth_certificates',
        'ca_template_pins', 'discovered_certificates', 'key_recovery_requests', 'msca_requests',
        'revoked_serials', 'role_permissions', 'scan_runs', 'ssh_certificates',
    ]


@pytest.fixture(scope='module')
def seeded(app, create_ca, create_cert):
    authority = create_ca(cn='zzcontract-shared-identity-ca.test')
    create_cert(cn='zzcontract-shared-identity-leaf.test', ca_id=authority['id'])
    with app.app_context():
        rows, _failures, order, _secrets = _seed_all()
        seeded = {name: row.id for name, row in rows.items() if hasattr(row, 'id')}
        extra = _seed_by_hand(authority['id'])
        seeded.update({name: row.id for name, row in extra.items()})
        yield seeded
        db.session.rollback()
        for row in reversed(list(extra.values())):
            type(row).query.filter_by(id=row.id).delete()
        db.session.commit()
        _remove(order)


def _seed_by_hand(ca_id):
    """The sections the generic factory cannot build: a revocation record, an SSH certificate."""
    from datetime import datetime
    from models import CA, RevokedSerial
    from models.ssh import SSHCertificate, SSHCertificateAuthority
    from tests.test_restore_extended_secrets import _ssh_key_material
    revoked = RevokedSerial(caref=db.session.get(CA, ca_id).refid, serial_number='zzcontract-shared-serial',
                            valid_to=datetime(2030, 1, 1))
    authority = SSHCertificateAuthority(
        refid='zzcontract-shared-sshca', descr='zzcontract shared SSH CA', ca_type='user',
        public_key='ssh-ed25519 AAAA zzcontract', private_key=_ssh_key_material(),
        key_type='ed25519', fingerprint='SHA256:zzcontract-shared', serial_counter=3)
    db.session.add_all([revoked, authority])
    db.session.flush()
    certificate = SSHCertificate(
        refid='zzcontract-shared-sshcert', descr='zzcontract shared SSH certificate',
        ssh_ca_id=authority.id, cert_type='user', key_id='zzcontract-key',
        public_key='ssh-ed25519 AAAA zzcontract', certificate='ssh-ed25519-cert-v01@openssh.com AAAA',
        principals='["ucm"]', serial=77, valid_from=datetime(2026, 1, 1), valid_to=datetime(2030, 1, 1),
        key_type='ed25519', fingerprint='SHA256:zzcontract-shared-cert', source='web')
    db.session.add(certificate)
    db.session.commit()
    return {'revoked_serials': revoked, 'ssh_ca': authority, 'ssh_certificates': certificate}


def _twin(name, row_id):
    """Ids of `row_id` and of a newer row with its identity, the identity filled in first.

    The twin differs on the columns of any other unique constraint."""
    section = manifest.SECTIONS[name]
    model = load_model(section)
    row = db.session.get(model, row_id)
    table = sa_inspect(model).local_table
    for index, field in enumerate(section.identity):
        if getattr(row, field) not in (None, ''):
            continue
        column = table.columns[field]
        if column.foreign_keys:
            reference = list(column.foreign_keys)[0]
            parent_name = next(n for n, s in manifest.SECTIONS.items()
                               if load_model(s).__table__.name == reference.column.table.name)
            setattr(row, field, getattr(_any_existing(parent_name), reference.column.name))
        else:
            setattr(row, field, _value_for(column, 9000 + index))
    db.session.commit()
    primary = {k.key for k in sa_inspect(model).primary_key}
    values = {c.key: getattr(row, c.key) for c in sa_inspect(model).column_attrs if c.key not in primary}
    uniques = [[c] for c in table.columns if c.unique and not c.primary_key]
    uniques += [list(i.columns) for i in table.indexes if i.unique]
    uniques += [list(k.columns) for k in table.constraints if isinstance(k, UniqueConstraint)]
    for columns in uniques:
        free = [c for c in columns if c.name not in section.identity and not c.foreign_keys]
        if free:
            attribute = sa_inspect(model).get_property_by_column(free[0]).key
            values[attribute] = f'{values[attribute] or ""}-twin'
    twin = model(**values)
    db.session.add(twin)
    db.session.commit()
    return row.id, twin.id


def _archived(name, *ids):
    """The archive's rows of these ids, in that order."""
    archived = export_section(name, IdentityIndex())
    plan = RestorePlan.build({name: archived})
    by_id = {plan.existing_id(name, row): row for row in archived}
    return [by_id[row_id] for row_id in ids]


@pytest.mark.parametrize('name', SHARED)
def test_the_oldest_row_is_the_archives_and_the_others_are_told(app, seeded, name):
    if name not in seeded:
        pytest.skip(f'{name}: the factory could not build a row here')
    model = load_model(manifest.SECTIONS[name])
    with app.app_context():
        oldest, newer = _twin(name, seeded[name])
        try:
            assert oldest < newer
            [archived] = _archived(name, oldest)

            merge = RestorePlan.build({name: [archived]})
            assert merge.existing_id(name, archived) == oldest
            told = [w for w in merge.warnings if w.startswith(f'{name} ') and f'id {oldest}, {newer})' in w]
            assert told and told[0].endswith(f'the others (id {newer}) are left as they are')

            replace = RestorePlan.build({name: [archived]}, pruned={name})
            assert not any(w.startswith(f'{name} ') for w in replace.warnings)
            doomed = rows_to_remove(name, [archived], replace)
            assert newer in doomed and oldest not in doomed
            assert replace.warnings[-1].endswith(f'the others (id {newer}) are removed')
            with db.session.begin_nested() as savepoint:
                replace_sections({name: [archived]}, replace, {name})
                assert db.session.get(model, oldest) is not None
                assert db.session.get(model, newer) is None
                savepoint.rollback()
        finally:
            db.session.rollback()
            model.query.filter_by(id=newer).delete()
            db.session.commit()


@pytest.mark.parametrize('name', SHARED)
def test_an_archive_of_both_rows_puts_each_back_on_its_own(app, seeded, name):
    if name not in seeded:
        pytest.skip(f'{name}: the factory could not build a row here')
    model = load_model(manifest.SECTIONS[name])
    with app.app_context():
        oldest, newer = _twin(name, seeded[name])
        try:
            first, second = _archived(name, oldest, newer)
            plan = RestorePlan.build({name: [first, second]}, pruned={name})
            assert [plan.existing_id(name, r) for r in (first, second)] == [oldest, newer]
            doomed = rows_to_remove(name, [first, second], plan)
            assert oldest not in doomed and newer not in doomed
        finally:
            db.session.rollback()
            model.query.filter_by(id=newer).delete()
            db.session.commit()


def _restore_only(name, keep, mode='merge', changes=None):
    """Archive the section, keep the rows of the ids in `keep`, change the first, restore."""
    from tests.test_backup_restore_failfast import PASSWORD, _only, _reseal, _service
    svc = _service()
    blob = svc.create_backup(PASSWORD, include=_only(name))
    _key, data = svc._decrypt_framed(blob, PASSWORD)
    plan = RestorePlan.build({name: data[name]})
    by_id = {plan.existing_id(name, row): row for row in data[name]}
    data[name] = [by_id[row_id] for row_id in keep]
    data[name][0].update(changes or {})
    return svc.restore_backup(_reseal(blob, data), PASSWORD, mode=mode)


# A section of each restorer: the generic one, and the dedicated ones with their own lookup
@pytest.mark.parametrize('name, column', [
    ('role_permissions', None),
    ('auth_certificates', 'name'),
    ('revoked_serials', 'revoke_reason'),
    ('ssh_certificates', 'descr'),
])
def test_a_merge_updates_the_oldest_and_says_so(app, seeded, name, column):
    model = load_model(manifest.SECTIONS[name])
    with app.app_context():
        oldest, newer = _twin(name, seeded[name])
        before = {c: getattr(db.session.get(model, newer), c) for c in (column,) if c}
        try:
            changes = {column: 'from the archive'} if column else {}
            results = _restore_only(name, [oldest], changes=changes)
            assert any(w.startswith(f'{name} ') and f'id {oldest}, {newer})' in w
                       and w.endswith('are left as they are') for w in results['warnings'])
            db.session.expire_all()
            assert db.session.get(model, newer) is not None
            if column:
                assert getattr(db.session.get(model, oldest), column) == 'from the archive'
                assert getattr(db.session.get(model, newer), column) == before[column]
        finally:
            db.session.rollback()
            model.query.filter_by(id=newer).delete()
            db.session.commit()


def test_a_replacement_removes_the_others_and_lists_them(app, seeded):
    model = load_model(manifest.SECTIONS['role_permissions'])
    with app.app_context():
        oldest, newer = _twin('role_permissions', seeded['role_permissions'])
        try:
            keep = [row.id for row in model.query.order_by(model.id) if row.id != newer]
            results = _restore_only('role_permissions', keep, mode='replace')
            told = [w for w in results['warnings'] if f'id {oldest}, {newer})' in w]
            assert len(told) == 1 and told[0].endswith(f'the others (id {newer}) are removed')
            db.session.expire_all()
            assert db.session.get(model, oldest) is not None and db.session.get(model, newer) is None
        finally:
            db.session.rollback()
            model.query.filter_by(id=newer).delete()
            db.session.commit()


def test_the_rows_of_a_shared_identity_come_back_each_on_its_own(app, seeded):
    """Two endpoints serving one certificate under two SNI names: neither takes the other's."""
    name = 'discovered_certificates'
    model = load_model(manifest.SECTIONS[name])
    with app.app_context():
        oldest, newer = _twin(name, seeded[name])
        sni = {row_id: db.session.get(model, row_id).sni_hostname for row_id in (oldest, newer)}
        try:
            _restore_only(name, [oldest, newer])
            db.session.expire_all()
            assert {row_id: db.session.get(model, row_id).sni_hostname for row_id in sni} == sni
        finally:
            db.session.rollback()
            model.query.filter_by(id=newer).delete()
            db.session.commit()


def test_a_scep_transaction_is_identified_per_ca(app, create_ca):
    """RFC 8894 §3.2.1.1: one client's transaction id at two CAs is two requests."""
    from models import CA
    from models.scep import SCEPRequest
    refids = []
    for n in (1, 2):
        ca_id = create_ca(cn=f'zzcontract-scep-ca-{n}.test')['id']
        with app.app_context():
            refids.append(db.session.get(CA, ca_id).refid)
    with app.app_context():
        rows = [SCEPRequest(transaction_id='zzcontract-shared-txn', ca_refid=refid, csr='x', status='pending')
                for refid in refids]
        db.session.add_all(rows)
        db.session.commit()
        ids = [r.id for r in rows]
        try:
            archived = [r for r in export_section('scep_requests', IdentityIndex())
                        if r['transaction_id'] == 'zzcontract-shared-txn']
            archived.reverse()   # in another order than here: the CA still tells them apart
            plan = RestorePlan.build({'scep_requests': archived}, pruned={'scep_requests'})
            assert {plan.existing_id('scep_requests', r): r['ca_refid'] for r in archived} == dict(zip(ids, refids))
            assert not any(w.startswith('scep_requests ') for w in plan.warnings)
            assert not set(ids) & set(rows_to_remove('scep_requests', archived, plan))
        finally:
            db.session.rollback()
            SCEPRequest.query.filter(SCEPRequest.id.in_(ids)).delete()
            db.session.commit()
