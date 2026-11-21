"""GET /api/v2/cas costs the same number of statements whatever the number of CAs."""
import threading
import uuid

import pytest
from sqlalchemy import event

from models import CA, db, Certificate


def _count_statements(app, client):
    seen = []
    mine = threading.get_ident()

    def hook(conn, cursor, statement, *rest):
        # The request runs on this thread: another thread's queries on the engine are not its cost
        if threading.get_ident() == mine:
            seen.append(statement)

    from utils.admin_allowlist import invalidate_cache
    with app.app_context():
        # The allowlist cache expires after seconds: read on every counted request, never on one of two
        invalidate_cache()
        event.listen(db.engine, 'before_cursor_execute', hook)
        try:
            response = client.get('/api/v2/cas')
        finally:
            event.remove(db.engine, 'before_cursor_execute', hook)
    assert response.status_code == 200, response.data
    return seen, response.get_json()['data']


def _populate(app, root_id, n):
    """n CAs cloned from the real root: half under it, half free, each with a certificate
    or none, so every branch of the per-CA computation runs."""
    ids, cert_ids = [], []
    with app.app_context():
        root = db.session.get(CA, root_id)
        for i in range(n):
            ca = CA(refid=uuid.uuid4().hex, descr=f'qc-{uuid.uuid4().hex[:6]}-{i}',
                    crt=root.crt, prv=None, subject=root.subject, issuer=root.issuer,
                    caref=root.refid if i % 2 else None)
            db.session.add(ca)
            db.session.flush()
            ids.append(ca.id)
            if i % 3:
                cert = Certificate(refid=uuid.uuid4().hex, descr=f'qc-cert-{i}', caref=ca.refid,
                                   crt=root.crt, subject=root.subject, issuer=root.issuer)
                db.session.add(cert)
                db.session.flush()
                cert_ids.append(cert.id)
        db.session.commit()
    return ids, cert_ids


def _drop_root(app, root_id):
    with app.app_context():
        CA.query.filter_by(id=root_id).delete()
        db.session.commit()


def _drop(app, ids, cert_ids):
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(cert_ids)).delete(synchronize_session=False)
        CA.query.filter(CA.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


def _two_runs(app, auth_client, create_ca, with_root=lambda: None):
    """The statements of a listing with 10 more CAs, then with 40 more."""
    root = create_ca(cn='QC Root')
    try:
        with_root()
        small_ids, small_certs = _populate(app, root['id'], 10)
        try:
            small, _ = _count_statements(app, auth_client)
        finally:
            _drop(app, small_ids, small_certs)
        big_ids, big_certs = _populate(app, root['id'], 40)
        try:
            big, data = _count_statements(app, auth_client)
            mine = [d for d in data if d['id'] in set(big_ids)]
            assert len(mine) == 40
            assert sum(d['certs'] for d in mine) >= len(big_certs)
        finally:
            _drop(app, big_ids, big_certs)
    finally:
        _drop_root(app, root['id'])
    return small, big


def test_statement_count_does_not_grow_with_the_number_of_cas(app, auth_client, create_ca):
    small, big = _two_runs(app, auth_client, create_ca)
    grown = _unexplained(small, big)
    assert not grown, (f'{len(small)} statements for 10 CAs, {len(big)} for 40; '
                       f'one run only: {sorted(grown.items())[:6]}')


def test_crossing_a_batch_boundary_is_not_growth(app, auth_client, create_ca, monkeypatch):
    """The shared database holds what other tests left: the 30 more CAs may be the ones
    that open a second batch."""
    from services.ca import list_prefetch

    def boundary_between_the_runs():
        with app.app_context():
            monkeypatch.setattr(list_prefetch, '_CHUNK', CA.query.count() + 25)
    small, big = _two_runs(app, auth_client, create_ca, with_root=boundary_between_the_runs)
    assert len(big) > len(small)
    assert not _unexplained(small, big)


def _unexplained(small, big):
    """The statements one run issued and the other did not, batches aside.

    The listing reads its facts by batches of ids: the larger run may cross one
    batch boundary, so one more execution of an ``IN (...)`` statement is not growth."""
    import re
    from collections import Counter
    # Either parameter style: ``?`` or ``%(name)s::TYPE``
    shape = lambda statement: re.sub(r'IN \((?:[^()]|\([^()]*\))*\)', 'IN (...)', statement)  # noqa: E731
    few, many = Counter(map(shape, small)), Counter(map(shape, big))
    grown = {s: n for s, n in (many - few).items() if n > 1 or 'IN (...)' not in s}
    grown.update({s: -n for s, n in (few - many).items()})
    return grown


def test_one_more_batch_is_not_growth_and_a_query_per_ca_is():
    batch = 'SELECT 1 FROM t WHERE t.id IN (?, ?, ?)'
    wider = 'SELECT 1 FROM t WHERE t.id IN (?, ?, ?, ?)'
    per_ca = 'SELECT 1 FROM t WHERE t.id = ?'
    assert _unexplained([batch], [wider]) == {}
    named = 'SELECT 1 FROM t WHERE t.id IN (%(id_1_1)s::INTEGER, %(id_1_2)s::INTEGER) GROUP BY t.id'
    assert _unexplained([named], [named.replace(')s::INTEGER)', ')s::INTEGER, %(id_1_3)s::INTEGER)'), named]) == {}
    assert _unexplained([batch], [wider, batch]) == {}
    assert _unexplained([batch], [wider] * 3)
    assert _unexplained([batch, per_ca], [batch, per_ca, per_ca])
    assert _unexplained([batch, per_ca], [batch])


def test_the_listing_answers_what_one_by_one_computation_gave(app, auth_client, create_ca):
    """The grouped queries change the cost, not the answer: parent, counts and the CN fallback."""
    root = create_ca(cn='QC Parity_Root')
    ids, cert_ids = _populate(app, root['id'], 7)
    try:
        _, data = _count_statements(app, auth_client)
        by_id = {d['id']: d for d in data}
        with app.app_context():
            for ca_id in ids + [root['id']]:
                ca = db.session.get(CA, ca_id)
                single = ca.to_dict()
                expected = Certificate.query.filter_by(caref=ca.refid).count()
                if expected == 0 and single['common_name']:
                    cn = single['common_name']
                    expected = Certificate.query.filter(
                        Certificate.issuer.ilike(f'CN={cn},%') |
                        Certificate.issuer.ilike(f'%,CN={cn},%') |
                        Certificate.issuer.ilike(f'%,CN={cn}')).count()
                single['certs'] = expected
                assert by_id[ca_id] == single
    finally:
        _drop(app, ids, cert_ids)
        _drop_root(app, root['id'])
