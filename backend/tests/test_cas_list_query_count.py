"""GET /api/v2/cas costs the same number of statements whatever the number of CAs."""
import uuid

import pytest
from sqlalchemy import event

from models import CA, db, Certificate


def _count_statements(app, client):
    seen = []

    def hook(conn, cursor, statement, *rest):
        seen.append(statement)

    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', hook)
        try:
            response = client.get('/api/v2/cas')
        finally:
            event.remove(db.engine, 'before_cursor_execute', hook)
    assert response.status_code == 200, response.data
    return len(seen), response.get_json()['data']


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


def _drop(app, ids, cert_ids):
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(cert_ids)).delete(synchronize_session=False)
        CA.query.filter(CA.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


def test_statement_count_does_not_grow_with_the_number_of_cas(app, auth_client, create_ca):
    root = create_ca(cn='QC Root')
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
    assert big == small, f'{small} statements for 10 CAs, {big} for 40'


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
