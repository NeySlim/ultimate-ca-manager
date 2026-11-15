"""A backup reads each section a page at a time, whatever the size of the table.

The exporters built every section whole, three times over for the
certificates (the rows, the manifest's columns of them, the identity index),
so the memory of a backup grew with the number of certificates. These tests
freeze what bounds it now: the memory traced while an archive is written does
not grow with the rows, and the queries grow with the pages, not the rows.
"""
import tracemalloc
import uuid

import pytest
from sqlalchemy import event

from models import Certificate, db
from services.backup import export_generic

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'
PAGE = 20
SMALL, LARGE = 60, 300


@pytest.fixture(scope='module')
def template(app, create_ca, create_cert):
    ca = create_ca(cn='Bounded Export CA')
    issued = create_cert(cn='bounded-export.example.com', ca_id=ca['id'])
    with app.app_context():
        row = db.session.get(Certificate, issued['id'])
        assert row.prv and row.crt
        return {column.key: getattr(row, column.key) for column in Certificate.__table__.columns
                if column.key not in ('id', 'refid', 'serial_number')}


def _fill(app, template, count):
    """`count` copies of the issued certificate, each naming the previous one as related."""
    with app.app_context():
        mine = Certificate.query.filter(Certificate.descr == 'bounded-export-copy').count()
        previous = None
        for index in range(mine, count):
            row = Certificate(**template, refid=str(uuid.uuid4()), serial_number=f'7{index:09d}')
            row.descr = 'bounded-export-copy'
            row.related_certificate_id = previous
            db.session.add(row)
            db.session.flush()
            previous = row.id
        db.session.commit()


@pytest.fixture(autouse=True)
def _remove_copies(app):
    yield
    with app.app_context():
        Certificate.query.filter(Certificate.descr == 'bounded-export-copy').delete()
        db.session.commit()


@pytest.fixture
def small_pages(monkeypatch):
    from services.backup_service import BackupService
    monkeypatch.setattr(export_generic, 'EXPORT_BATCH', PAGE, raising=False)
    # The smallest chunk the format allows: the writer's buffer is not what is measured
    monkeypatch.setattr(BackupService, 'CHUNK_MAX', 64 * 1024)


def _write(app):
    """Peak memory traced and statements reading the certificates table, for one archive."""
    from services.backup_service import BackupService
    statements = []

    def count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT') and 'FROM certificates' in statement:
            statements.append(statement)

    with app.app_context():
        engine = db.engine
        event.listen(engine, 'before_cursor_execute', count)
        tracemalloc.start()
        try:
            size = sum(len(chunk) for chunk in BackupService().iter_backup(PASSWORD, kdf='pbkdf2'))
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
            event.remove(engine, 'before_cursor_execute', count)
    return peak, len(statements), size


def test_memory_does_not_grow_with_the_certificates(app, template, small_pages):
    _fill(app, template, SMALL)
    _write(app)    # caches a first archive fills (compiled statements, imports) are not rows
    small_peak, _, small_size = _write(app)
    _fill(app, template, LARGE)
    large_peak, _, large_size = _write(app)

    assert large_size > 3 * small_size
    # What the extra rows weigh in the archive: a section held whole costs several times that
    added = large_size - small_size
    assert large_peak - small_peak < added / 4, (
        f"peak {small_peak / 2**20:.1f} MiB at {SMALL} certificates, "
        f"{large_peak / 2**20:.1f} MiB at {LARGE}")


def test_queries_grow_with_the_pages_not_the_rows(app, template, small_pages):
    _fill(app, template, SMALL)
    _, small_queries, _ = _write(app)
    _fill(app, template, LARGE)
    _, large_queries, _ = _write(app)

    pages = (LARGE - SMALL) // PAGE
    # A page reads its rows, then the related certificates it names: two statements
    assert large_queries - small_queries <= 2 * pages + 2, (small_queries, large_queries)


def test_each_related_certificate_is_carried_by_identity(app, template, small_pages):
    from services.backup.export_generic import IdentityIndex, iter_section
    _fill(app, template, SMALL)
    with app.app_context():
        rows = [row for row in iter_section('certificates', IdentityIndex())
                if row.get('descr') == 'bounded-export-copy']
        by_id = {row.id: row.refid for row in Certificate.query.filter_by(descr='bounded-export-copy')}
    assert len(rows) >= SMALL
    linked = [row for row in rows if row['related_certificate_id'] is not None]
    assert len(linked) == len(rows) - 1
    for row in linked:
        assert row['related_certificate_id_ref'] == {'refid': by_id[row['related_certificate_id']]}


def test_the_identity_index_holds_one_page_of_certificates(app, template, small_pages):
    from services.backup.export_generic import IdentityIndex, iter_section
    sizes = []
    for count in (SMALL, LARGE):
        _fill(app, template, count)
        with app.app_context():
            index = IdentityIndex()
            assert sum(1 for _ in iter_section('certificates', index)) >= count
            sizes.append(len(index._by_section['certificates']))
    # The previous page's identities are forgotten: the index never grows with the table
    assert all(size <= PAGE for size in sizes), sizes


def test_identities_are_read_without_the_key_material(app, template, small_pages):
    from services.backup.export_generic import IdentityIndex
    _fill(app, template, SMALL)
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    with app.app_context():
        ids = [row.id for row in Certificate.query.filter_by(descr='bounded-export-copy')]
        engine = db.engine
        event.listen(engine, 'before_cursor_execute', record)
        try:
            index = IdentityIndex()
            index.prefetch('certificates', ids)
        finally:
            event.remove(engine, 'before_cursor_execute', record)
        refids = {row.id: row.refid for row in Certificate.query.filter(Certificate.id.in_(ids))}
    assert {key: value['refid'] for key, value in index._by_section['certificates'].items()} == refids
    selects = [s for s in statements if 'FROM certificates' in s]
    assert selects and not any('certificates.prv' in s or 'certificates.crt' in s for s in selects)
