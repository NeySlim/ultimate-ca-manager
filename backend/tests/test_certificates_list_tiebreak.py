"""Status and compliance sorts settle ties on the id, so paging never repeats or skips a row."""
import uuid

import pytest

from models import Certificate, db

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


@pytest.fixture
def twins(app):
    tag = uuid.uuid4().hex[:8]
    ids = []
    with app.app_context():
        for i in range(7):
            cert = Certificate(refid=str(uuid.uuid4()), descr=f'twin-{tag}', subject=f'CN=twin-{tag}',
                               subject_cn=f'twin-{tag}', source='manual', crt='Zm9v', serial_number=f'{tag}{i}')
            db.session.add(cert)
            db.session.flush()
            ids.append(cert.id)
        db.session.commit()
    yield tag, ids
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


@pytest.mark.parametrize('sort_by', ['status', 'compliance_grade'])
@pytest.mark.parametrize('order', ['asc', 'desc'])
def test_pages_of_tied_rows_walk_the_set_once_in_id_order(auth_client, twins, sort_by, order):
    tag, ids = twins
    seen = []
    for page in (1, 2, 3, 4):
        r = auth_client.get(f'/api/v2/certificates?search=twin-{tag}&sort_by={sort_by}'
                            f'&sort_order={order}&per_page=2&page={page}')
        assert r.status_code == 200, r.data
        seen += [c['id'] for c in r.get_json()['data']]
    assert seen == sorted(ids)
