"""Cross-certificates of a CA: attach, serve, revoke, detach, export (#400)."""
from datetime import timedelta

import pytest

from models import CA, RevokedSerial, db
from models.ca_cross_certificate import CACrossCertificate
from services.smart_import.importer import SmartImporter
from tests.fixtures.cross_pki import build_cross_pki, make_cert, new_key, openssl_verify, pem
from utils.datetime_utils import utc_now


@pytest.fixture
def pki():
    return build_cross_pki()


@pytest.fixture
def cas(app, pki):
    """Root A and Root B held; ids of both."""
    with app.app_context():
        SmartImporter().execute(pem(pki.root_a))
        SmartImporter().execute(pem(pki.root_b))
        yield (CA.query.filter_by(descr=pki.name_a).one().id, CA.query.filter_by(descr=pki.name_b).one().id)


def _url(b, xid=None, tail=''):
    return f'/api/v2/cas/{b}/cross-certificates' + (f'/{xid}' if xid else '') + tail


def _attach(client, b, cert, **extra):
    return client.post(_url(b), json={'certificate': pem(cert), **extra})


def test_attach_stores_the_certificate_unserved_beside_the_root(app, auth_client, pki, cas):
    a, b = cas
    r = _attach(auth_client, b, pki.cross_b)
    assert r.status_code == 201, r.data
    body = r.get_json()['data']
    assert body['served'] is False and body['revoked'] is False
    with app.app_context():
        assert body['issuer_caref'] == db.session.get(CA, a).refid
        root = db.session.get(CA, b)
        assert root.issuer == root.subject  # the self-signed certificate is untouched
        assert CACrossCertificate.query.filter_by(ca_id=b).count() == 1


def test_exported_cross_certificate_lets_root_a_alone_verify_the_leaf(auth_client, pki, cas):
    _, b = cas
    xid = _attach(auth_client, b, pki.cross_b).get_json()['data']['id']
    exported = auth_client.get(_url(b, xid, '/export')).data.decode()
    ok, out = openssl_verify(pki.leaf, [pki.root_a], untrusted=[pki.int_b, exported])
    assert ok, out
    ok, _ = openssl_verify(pki.leaf, [pki.root_a], untrusted=[pki.int_b])
    assert not ok
    der = auth_client.get(_url(b, xid, '/export') + '?format=der')
    assert der.status_code == 200 and der.data[:1] == b'\x30'
    assert auth_client.get(_url(b, xid, '/export') + '?format=p12').status_code == 400


def test_attach_refusals(app, auth_client, pki, cas):
    _, b = cas
    other = build_cross_pki()
    foreign = make_cert(pki.name_b, new_key(), pki.name_a, pki.key_a)
    forged = make_cert(pki.name_b, pki.key_b, pki.name_a, new_key())  # A's name, not A's key
    non_ca = make_cert(pki.name_b, pki.key_b, pki.name_a, pki.key_a, ca=False)
    for cert, status, fragment in (
        (other.cross_b, 400, 'subject differs'),
        (foreign, 400, 'key differs'),
        (pki.root_b, 400, 'self-signed'),
        (non_ca, 400, 'Not a CA'),
        (forged, 400, 'signature'),
    ):
        r = _attach(auth_client, b, cert)
        assert r.status_code == status and fragment in r.get_json()['message'], (fragment, r.data)
    assert auth_client.post(_url(b), json={'certificate': 'garbage'}).status_code == 400
    assert _attach(auth_client, b, pki.cross_b).status_code == 201
    assert _attach(auth_client, b, pki.cross_b).status_code == 409
    with app.app_context():
        assert CACrossCertificate.query.filter_by(ca_id=b).count() == 1


def test_issuer_not_held_is_attached_without_a_signature_check(auth_client, pki, app):
    with app.app_context():
        SmartImporter().execute(pem(pki.root_b))
        b = CA.query.filter_by(descr=pki.name_b).one().id
    r = _attach(auth_client, b, pki.cross_b)
    assert r.status_code == 201 and r.get_json()['data']['issuer_caref'] is None


def test_attach_warns_about_constraints(auth_client, pki, cas):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    _, b = cas
    base = pki.cross_b
    builder = (x509.CertificateBuilder().subject_name(base.subject).issuer_name(base.issuer)
               .public_key(base.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(base.not_valid_before_utc).not_valid_after(base.not_valid_after_utc)
               .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
               .add_extension(x509.NameConstraints([x509.DNSName('example.test')], None), critical=True))
    constrained = builder.sign(pki.key_a, hashes.SHA256())
    r = _attach(auth_client, b, constrained)
    assert r.status_code == 201
    assert any('name constraints' in w for w in r.get_json()['data']['warnings'])


def test_at_most_one_served_and_never_an_expired_or_revoked_one(app, auth_client, pki, cas):
    a, b = cas
    second = make_cert(pki.name_b, pki.key_b, pki.name_a, pki.key_a, days=700)
    first_id = _attach(auth_client, b, pki.cross_b, served=True).get_json()['data']['id']
    second_id = _attach(auth_client, b, second).get_json()['data']['id']
    r = auth_client.patch(_url(b, second_id), json={'served': True})
    assert r.status_code == 200 and r.get_json()['data']['served'] is True
    with app.app_context():
        assert db.session.get(CACrossCertificate, first_id).served is False
        assert [x.id for x in CACrossCertificate.query.filter_by(ca_id=b, served=True)] == [second_id]
        from services.ca.cross_certs import served_for
        assert served_for(db.session.get(CA, b)).id == second_id
        db.session.get(CACrossCertificate, second_id).valid_to = utc_now() - timedelta(days=1)
        db.session.commit()
        assert served_for(db.session.get(CA, b)) is None
    assert auth_client.patch(_url(b, second_id), json={'served': True}).status_code == 409
    assert auth_client.post(_url(b, first_id, '/revoke'), json={'reason': 'superseded'}).status_code == 200
    assert auth_client.patch(_url(b, first_id), json={'served': True}).status_code == 409
    assert auth_client.patch(_url(b, first_id), json={'served': 'yes'}).status_code == 400
    # kept and exportable on request
    assert auth_client.get(_url(b, first_id, '/export')).status_code == 200
    assert auth_client.get(_url(b, second_id, '/export')).status_code == 200


def test_revoking_the_cross_certificate_lists_it_at_the_issuer_and_not_the_root(app, auth_client, pki, cas):
    a, b = cas
    xid = _attach(auth_client, b, pki.cross_b, served=True).get_json()['data']['id']
    r = auth_client.post(_url(b, xid, '/revoke'), json={'reason': 'keyCompromise'})
    assert r.status_code == 200, r.data
    with app.app_context():
        issuer, root = db.session.get(CA, a), db.session.get(CA, b)
        record = RevokedSerial.query.filter_by(caref=issuer.refid).one()
        assert record.serial_number == str(pki.cross_b.serial_number)
        assert root.revoked is False
        assert RevokedSerial.query.filter_by(caref=root.refid).count() == 0
        row = db.session.get(CACrossCertificate, xid)
        assert row.revoked is True and row.served is False
    assert auth_client.post(_url(b, xid, '/revoke'), json={}).status_code == 409
    assert auth_client.post(_url(b, xid, '/revoke'), json={'reason': 'nonsense'}).status_code == 400


def test_revoke_needs_the_issuer(app, auth_client, pki):
    with app.app_context():
        SmartImporter().execute(pem(pki.root_b))
        b = CA.query.filter_by(descr=pki.name_b).one().id
    xid = _attach(auth_client, b, pki.cross_b).get_json()['data']['id']
    assert auth_client.post(_url(b, xid, '/revoke'), json={}).status_code == 400


def test_detach_then_reattach_keeps_the_issuers_revocation(app, auth_client, pki, cas):
    _, b = cas
    xid = _attach(auth_client, b, pki.cross_b).get_json()['data']['id']
    auth_client.post(_url(b, xid, '/revoke'), json={})
    assert auth_client.delete(_url(b, xid)).status_code == 204
    again = _attach(auth_client, b, pki.cross_b).get_json()['data']
    assert again['revoked'] is True


def test_row_of_another_ca_is_not_found(auth_client, pki, cas):
    a, b = cas
    xid = _attach(auth_client, b, pki.cross_b).get_json()['data']['id']
    assert auth_client.get(_url(a, xid)).status_code == 404
    assert auth_client.get(_url(999999)).status_code == 404
    assert auth_client.get(_url(b)).get_json()['data'][0]['id'] == xid


def test_deleting_the_ca_removes_its_cross_certificates(app, auth_client, pki, cas):
    _, b = cas
    _attach(auth_client, b, pki.cross_b)
    assert auth_client.delete(f'/api/v2/cas/{b}').status_code == 204
    with app.app_context():
        assert CACrossCertificate.query.filter_by(ca_id=b).count() == 0


def test_attach_audits_and_emits_a_snapshot(app, auth_client, pki, cas, monkeypatch):
    from models import AuditLog
    _, b = cas
    seen = []
    monkeypatch.setattr('services.webhook_service.emit_ca_updated',
                        lambda ca, actor=None, changes=None: seen.append((ca, changes)))
    xid = _attach(auth_client, b, pki.cross_b).get_json()['data']['id']
    assert isinstance(seen[0][0], dict) and seen[0][0]['id'] == b
    assert seen[0][1]['cross_certificate'] == 'attached' and seen[0][1]['cross_certificate_id'] == xid
    with app.app_context():
        assert AuditLog.query.filter_by(action='ca_cross_certificate_attached', resource_id=str(b)).count() == 1


def test_viewer_may_read_but_not_write(viewer_client, auth_client, pki, cas):
    _, b = cas
    xid = _attach(auth_client, b, pki.cross_b).get_json()['data']['id']
    assert viewer_client.get(_url(b)).status_code == 200
    assert viewer_client.post(_url(b), json={'certificate': pem(pki.cross_b)}).status_code == 403
    assert viewer_client.delete(_url(b, xid)).status_code == 403
