"""The discovery export follows the filters of the list: status, profile and search."""
import csv
import io
import json
import uuid

import pytest


from models import db, DiscoveredCertificate, ScanProfile


@pytest.fixture
def discovered(app):
    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        profiles = []
        for n in range(2):
            p = ScanProfile(name=f'exp-{tag}-{n}', targets='["example.test"]')
            db.session.add(p)
            profiles.append(p)
        db.session.commit()
        rows = []
        for i, (pi, status) in enumerate([(0, 'managed'), (0, 'unmanaged'), (1, 'unmanaged')]):
            r = DiscoveredCertificate(
                target=f'host-{tag}-{i}.example.test', port=443,
                scan_profile_id=profiles[pi].id, status=status,
                subject=f'CN=svc-{tag}-{i}', fingerprint_sha256=uuid.uuid4().hex * 2)
            db.session.add(r)
            rows.append(r)
        db.session.commit()
        info = {'tag': tag, 'p0': profiles[0].id, 'p1': profiles[1].id}
        ids = [r.id for r in rows]
        pids = [p.id for p in profiles]
    yield info
    with app.app_context():
        DiscoveredCertificate.query.filter(DiscoveredCertificate.id.in_(ids)).delete(
            synchronize_session=False)
        ScanProfile.query.filter(ScanProfile.id.in_(pids)).delete(synchronize_session=False)
        db.session.commit()


def _json(client, query):
    r = client.get(f'/api/v2/discovery/export?format=json&{query}')
    assert r.status_code == 200, r.data
    return json.loads(r.data)


def test_search_narrows_the_export(auth_client, discovered):
    tag = discovered['tag']
    assert len(_json(auth_client, f'search={tag}')) == 3
    rows = _json(auth_client, f'search=svc-{tag}-1')
    assert [r['subject'] for r in rows] == [f'CN=svc-{tag}-1']


def test_status_and_profile_still_narrow_it(auth_client, discovered):
    tag = discovered['tag']
    rows = _json(auth_client, f"search={tag}&status=unmanaged&profile_id={discovered['p0']}")
    assert [r['subject'] for r in rows] == [f'CN=svc-{tag}-1']


def test_the_csv_follows_the_search(auth_client, discovered):
    tag = discovered['tag']
    r = auth_client.get(f'/api/v2/discovery/export?format=csv&search=svc-{tag}-2')
    assert r.status_code == 200
    rows = list(csv.DictReader(io.StringIO(r.get_data(as_text=True))))
    assert [x['subject'] for x in rows] == [f'CN=svc-{tag}-2']
