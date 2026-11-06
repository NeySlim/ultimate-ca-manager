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
        'acme_client_orders', 'approval_requests', 'audit_logs',
        'ca_template_pins', 'key_recovery_requests', 'msca_requests',
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
            assert any(w.startswith(f'{name} ') and w.endswith(f'the others (id {newer}) are removed')
                       for w in replace.warnings)
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
DEDICATED = ['revoked_serials', 'ssh_certificates', 'approval_requests', 'acme_client_orders',
             'key_recovery_requests']


@pytest.mark.parametrize('name, column', [
    ('role_permissions', None),
    ('revoked_serials', 'revoke_reason'),
    ('ssh_certificates', 'descr'),
    ('approval_requests', None),
    ('acme_client_orders', None),
    ('key_recovery_requests', None),
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


# A column each twin holds its own value in, where the section has one
OWN_COLUMN = {'revoked_serials': 'revoke_reason', 'ssh_certificates': 'descr',
              'approval_requests': 'requester_comment', 'acme_client_orders': 'order_url',
              'key_recovery_requests': 'decision_note'}


@pytest.mark.parametrize('name', ['role_permissions'] + DEDICATED)
def test_an_archive_of_both_rows_restores_each_on_its_own_row(app, seeded, name):
    model = load_model(manifest.SECTIONS[name])
    column = OWN_COLUMN.get(name)
    with app.app_context():
        oldest, newer = _twin(name, seeded[name])
        if column:
            for row_id in (oldest, newer):
                setattr(db.session.get(model, row_id), column, f'zz-own-{row_id}')
            db.session.commit()
        count = model.query.count()
        try:
            _restore_only(name, [oldest, newer])
            db.session.expire_all()
            assert model.query.count() == count
            assert db.session.get(model, oldest) is not None and db.session.get(model, newer) is not None
            if column:
                assert [getattr(db.session.get(model, i), column) for i in (oldest, newer)] == \
                    [f'zz-own-{oldest}', f'zz-own-{newer}']
        finally:
            db.session.rollback()
            model.query.filter_by(id=newer).delete()
            db.session.commit()


def test_a_second_archived_row_of_one_identity_here_is_added(app, seeded):
    """One row here, the archive holding its identity twice: the second is a new row."""
    name = 'role_permissions'
    model = load_model(manifest.SECTIONS[name])
    with app.app_context():
        mine = seeded[name]
        count = model.query.count()
        from tests.test_backup_restore_failfast import PASSWORD, _only, _reseal, _service
        svc = _service()
        blob = svc.create_backup(PASSWORD, include=_only(name))
        _key, data = svc._decrypt_framed(blob, PASSWORD)
        plan = RestorePlan.build({name: data[name]})
        archived = next(row for row in data[name] if plan.existing_id(name, row) == mine)
        data[name] = [archived, dict(archived)]
        try:
            svc.restore_backup(_reseal(blob, data), PASSWORD, mode='merge')
            db.session.expire_all()
            assert model.query.count() == count + 1
            assert db.session.get(model, mine) is not None
        finally:
            db.session.rollback()
            extra = [row.id for row in model.query.order_by(model.id) if row.id > mine][-1:]
            model.query.filter(model.id.in_(extra)).delete()
            db.session.commit()


def test_endpoints_restored_in_another_order_keep_their_names(app):
    """One certificate at one endpoint under two SNI names: its identity is the endpoint's."""
    from models.discovered_certificate import DiscoveredCertificate
    from tests.test_backup_restore_failfast import PASSWORD, _only, _reseal, _service
    with app.app_context():
        rows = [DiscoveredCertificate(target='zz-shared-endpoint.test', port=443, sni_hostname=sni,
                                      fingerprint_sha256='zz-shared-fp') for sni in ('', 'b.example.test')]
        db.session.add_all(rows)
        db.session.commit()
        ids = {row.sni_hostname: row.id for row in rows}
        try:
            svc = _service()
            blob = svc.create_backup(PASSWORD, include=_only('discovered_certificates'))
            _key, data = svc._decrypt_framed(blob, PASSWORD)
            data['discovered_certificates'] = [r for r in data['discovered_certificates']
                                               if r['target'] == 'zz-shared-endpoint.test'][::-1]
            data['discovered_certificates'][0]['fingerprint_sha256'] = 'zz-renewed-fp'
            svc.restore_backup(_reseal(blob, data), PASSWORD, mode='merge')
            db.session.expire_all()
            back = {r.sni_hostname: (r.id, r.fingerprint_sha256) for r in
                    DiscoveredCertificate.query.filter_by(target='zz-shared-endpoint.test')}
            assert back == {'': (ids[''], 'zz-shared-fp'), 'b.example.test': (ids['b.example.test'], 'zz-renewed-fp')}
        finally:
            db.session.rollback()
            DiscoveredCertificate.query.filter_by(target='zz-shared-endpoint.test').delete()
            db.session.commit()


@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_enrolments_without_fingerprint_keep_their_own_user(app, create_user, mode):
    """Rows the archive cannot tell apart by identity still each come back on their own."""
    from models.auth_certificate import AuthCertificate
    from tests.test_backup_restore_failfast import PASSWORD, _only, _reseal, _service
    other = create_user(username=f'zzrelink-{mode}', role='operator')['id']
    with app.app_context():
        mine = [AuthCertificate(user_id=user_id, cert_serial=f'zzrelink-{mode}-{n}', cert_subject='CN=zzrelink',
                                cert_issuer=None, cert_fingerprint=None, name=f'zzrelink-{n}', enabled=True)
                for n, user_id in enumerate((1, other))]
        db.session.add_all(mine)
        db.session.commit()
        try:
            svc = _service()
            blob = svc.create_backup(PASSWORD, include=_only('auth_certificates'))
            _key, data = svc._decrypt_framed(blob, PASSWORD)
            if mode == 'merge':
                data['auth_certificates'] = [r for r in data['auth_certificates'] if r['cert_subject'] == 'CN=zzrelink']
            svc.restore_backup(_reseal(blob, data), PASSWORD, mode=mode)
            db.session.expire_all()
            back = {r.name: r.user_id for r in AuthCertificate.query.filter_by(cert_subject='CN=zzrelink')}
            assert back == {'zzrelink-0': 1, 'zzrelink-1': other}
        finally:
            db.session.rollback()
            AuthCertificate.query.filter_by(cert_subject='CN=zzrelink').delete()
            db.session.commit()


def test_a_replacement_removes_every_row_without_a_complete_identity(app):
    from models.auth_certificate import AuthCertificate
    from tests.test_backup_restore_failfast import PASSWORD, _only, _reseal, _service
    with app.app_context():
        kept = AuthCertificate(user_id=1, cert_serial='zzincomplete-kept', cert_subject='CN=zzincomplete',
                               cert_issuer='CN=zz complete', name='kept', enabled=True)
        db.session.add(kept)
        db.session.commit()
        svc = _service()
        blob = svc.create_backup(PASSWORD, include=_only('auth_certificates'))
        _key, data = svc._decrypt_framed(blob, PASSWORD)
        try:
            gone = [AuthCertificate(user_id=1, cert_serial=f'zzincomplete-{n}', cert_subject='CN=zzincomplete',
                                    cert_issuer='', name=f'gone {n}', enabled=True) for n in range(3)]
            db.session.add_all(gone)
            db.session.commit()
            ids = sorted(row.id for row in gone)
            results = svc.restore_backup(_reseal(blob, data), PASSWORD, mode='replace')
            db.session.expire_all()
            assert [r.name for r in AuthCertificate.query.filter_by(cert_subject='CN=zzincomplete')] == ['kept']
            told = [w for w in results['warnings'] if w.startswith('auth_certificates: ') and 'are removed, then those the archive carries' in w]
            listed = told[0].split('(id ', 1)[1].split(')', 1)[0].split(', ') if told else []
            assert set(map(str, ids)) <= set(listed)
        finally:
            db.session.rollback()
            AuthCertificate.query.filter_by(cert_subject='CN=zzincomplete').delete()
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


def test_a_replacement_keeps_the_enrolment_its_issuer_and_serial_name(app):
    """The fingerprint spelled otherwise by another route: still the same row, never removed and re-added."""
    from models.auth_certificate import AuthCertificate
    from tests.test_backup_restore_failfast import PASSWORD, _only, _reseal, _service
    with app.app_context():
        row, later = [AuthCertificate(user_id=1, cert_serial=f'zzsame-serial-{n}', cert_subject='CN=zzsame',
                                      cert_issuer='CN=zz same issuer', cert_fingerprint=f'AB:CD:EF:0{n}',
                                      name=f'zzsame {n}', enabled=True) for n in (1, 2)]
        db.session.add_all([row, later])   # a later row: SQLite gives a removed last id again
        db.session.commit()
        row_id = row.id
        try:
            svc = _service()
            blob = svc.create_backup(PASSWORD, include=_only('auth_certificates'))
            _key, data = svc._decrypt_framed(blob, PASSWORD)
            next(r for r in data['auth_certificates'] if r['name'] == 'zzsame 1')['cert_fingerprint'] = 'abcdef01'
            svc.restore_backup(_reseal(blob, data), PASSWORD, mode='replace')
            db.session.expire_all()
            back = AuthCertificate.query.filter_by(name='zzsame 1').one()
            assert (back.id, back.cert_fingerprint) == (row_id, 'abcdef01')
        finally:
            db.session.rollback()
            AuthCertificate.query.filter_by(cert_subject='CN=zzsame').delete()
            db.session.commit()


def test_a_second_pass_finds_the_row_an_archived_row_was_written_to(app, seeded):
    """`relink_references` asks the plan again: it answers with the row written, not a namesake."""
    from services.backup.restore.apply import apply_columns
    name = 'role_permissions'
    model = load_model(manifest.SECTIONS[name])
    with app.app_context():
        oldest, newer = _twin(name, seeded[name])
        try:
            [archived] = _archived(name, oldest)
            plan = RestorePlan.build({name: [archived]})
            assert apply_columns(db.session.get(model, newer), name, archived, plan)
            db.session.flush()
            assert plan.existing_id(name, archived) == newer
        finally:
            db.session.rollback()
            model.query.filter_by(id=newer).delete()
            db.session.commit()


def test_enrolments_sharing_a_fingerprint_each_come_back_on_their_own(app):
    from models.auth_certificate import AuthCertificate
    from tests.test_backup_restore_failfast import PASSWORD, _only, _reseal, _service
    with app.app_context():
        rows = [AuthCertificate(user_id=1, cert_serial=f'zzdupfp-{n}', cert_subject='CN=zzdupfp',
                                cert_issuer='CN=zz dup fp', cert_fingerprint='ZZ-DUP-FP', name=f'zzdupfp {n}',
                                enabled=True) for n in (1, 2)]
        db.session.add_all(rows)
        db.session.commit()
        ids = {row.name: row.id for row in rows}
        try:
            svc = _service()
            blob = svc.create_backup(PASSWORD, include=_only('auth_certificates'))
            _key, data = svc._decrypt_framed(blob, PASSWORD)
            data['auth_certificates'] = [r for r in data['auth_certificates'] if r['cert_subject'] == 'CN=zzdupfp']
            svc.restore_backup(_reseal(blob, data), PASSWORD, mode='merge')
            db.session.expire_all()
            assert {r.name: (r.id, r.cert_serial) for r in AuthCertificate.query.filter_by(cert_subject='CN=zzdupfp')} \
                == {name: (row_id, f'zzdupfp-{name[-1]}') for name, row_id in ids.items()}
        finally:
            db.session.rollback()
            AuthCertificate.query.filter_by(cert_subject='CN=zzdupfp').delete()
            db.session.commit()
