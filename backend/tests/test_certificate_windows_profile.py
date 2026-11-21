"""A certificate says which Windows enrollment profile issued it, at a flat query cost."""
import threading
import uuid

from sqlalchemy import event

from models import CA, Certificate, WindowsEnrollmentProfile, db


def _profile(name):
    profile = WindowsEnrollmentProfile(name=f'{name}-{uuid.uuid4().hex[:6]}', enabled=True)
    db.session.add(profile)
    db.session.flush()
    return profile.id


def _certs(root, n, profile_ids):
    ids = []
    for i in range(n):
        cert = Certificate(refid=uuid.uuid4().hex, descr=f'wp-{uuid.uuid4().hex[:6]}-{i}', caref=root.refid,
                           crt=root.crt, subject=root.subject, issuer=root.issuer,
                           windows_profile_id=profile_ids[i % len(profile_ids)] if profile_ids else None)
        db.session.add(cert)
        db.session.flush()
        ids.append(cert.id)
    db.session.commit()
    return ids


def _statements(app, client, url):
    seen, mine = [], threading.get_ident()

    def hook(conn, cursor, statement, *rest):
        if threading.get_ident() == mine:
            seen.append(statement)

    from utils.admin_allowlist import invalidate_cache
    with app.app_context():
        invalidate_cache()
        event.listen(db.engine, 'before_cursor_execute', hook)
        try:
            response = client.get(url)
        finally:
            event.remove(db.engine, 'before_cursor_execute', hook)
    assert response.status_code == 200, response.data
    return seen, response.get_json()['data']


def _drop(app, cert_ids, profile_ids):
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(cert_ids)).delete(synchronize_session=False)
        WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.id.in_(profile_ids)).delete(
            synchronize_session=False)
        db.session.commit()


def test_detail_and_list_carry_the_profile_id_and_name(app, auth_client, create_ca):
    root = create_ca(cn='WP Root')
    with app.app_context():
        pid = _profile('wp-one')
        name = db.session.get(WindowsEnrollmentProfile, pid).name
        ca = db.session.get(CA, root['id'])
        cids = _certs(ca, 2, [pid])
        plain = _certs(ca, 1, [])[0]
    try:
        detail = auth_client.get(f'/api/v2/certificates/{cids[0]}').get_json()['data']
        assert detail['windows_profile_id'] == pid and detail['windows_profile_name'] == name
        none = auth_client.get(f'/api/v2/certificates/{plain}').get_json()['data']
        assert none['windows_profile_id'] is None and none['windows_profile_name'] is None
        # Its CA alone: certificates other files left must not push it off the page
        _, rows = _statements(app, auth_client, f"/api/v2/certificates?per_page=100&ca_id={root['id']}")
        row = next(r for r in rows if r['id'] == cids[0])
        assert row['windows_profile_name'] == name
        # The profile is gone, the certificate keeps its id: the name is null
        with app.app_context():
            WindowsEnrollmentProfile.query.filter_by(id=pid).delete()
            db.session.commit()
        gone = auth_client.get(f'/api/v2/certificates/{cids[0]}').get_json()['data']
        assert gone['windows_profile_id'] == pid and gone['windows_profile_name'] is None
    finally:
        _drop(app, cids + [plain], [pid])
        with app.app_context():
            CA.query.filter_by(id=root['id']).delete()
            db.session.commit()


def _counts_by_size(app, auth_client, create_ca, cn, url_of):
    root = create_ca(cn=cn)
    counts = {}
    all_certs, all_profiles = [], []
    try:
        for label, n in (('few', 3), ('many', 24)):
            with app.app_context():
                pids = [_profile('wp-q') for _ in range(3)]
                cids = _certs(db.session.get(CA, root['id']), n, pids)
            all_certs += cids
            all_profiles += pids
            seen, rows = _statements(app, auth_client, url_of(root['id']))
            counts[label] = len(seen)
            mine = [r for r in rows if r['id'] in cids]
            assert len(mine) == n and all(r['windows_profile_name'] for r in mine), mine
            if label == 'few':
                _drop(app, cids, pids)
                all_certs, all_profiles = [], []
        return counts
    finally:
        _drop(app, all_certs, all_profiles)
        with app.app_context():
            CA.query.filter_by(id=root['id']).delete()
            db.session.commit()


def test_list_statements_do_not_grow_with_profile_certificates(app, auth_client, create_ca):
    counts = _counts_by_size(app, auth_client, create_ca, 'WP Root 2',
                             lambda ca: f'/api/v2/certificates?per_page=100&ca_id={ca}')
    assert counts['many'] == counts['few'], counts


def test_ca_list_statements_do_not_grow_with_profile_certificates(app, auth_client, create_ca):
    counts = _counts_by_size(app, auth_client, create_ca, 'WP Root 3',
                             lambda ca_id: f'/api/v2/cas/{ca_id}/certificates?per_page=100')
    assert counts['many'] == counts['few'], counts
