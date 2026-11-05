"""Deleting a CA on PostgreSQL met the foreign keys the blockers did not know
(SCEP requests, SCEP profiles, ACME domains, policies) after the files were
already gone; SQLite let the rows rot instead."""
import base64

import pytest

from models import CA, db
from models.acme_models import AcmeLocalDomain
from models.policy import CertificatePolicy
from models.scep import ScepProfile, SCEPRequest
from tests.conftest import assert_success
from utils.file_naming import ca_cert_path, ca_key_path


def _row(app, ca_id):
    with app.app_context():
        return db.session.get(CA, ca_id)


def test_scep_requests_go_with_their_ca(app, auth_client, create_ca):
    ca = create_ca(cn='SCEP history CA')
    with app.app_context():
        refid = db.session.get(CA, ca['id']).refid
        for n in range(2):
            db.session.add(SCEPRequest(transaction_id=f'hist-{n}', ca_refid=refid,
                                       csr=base64.b64encode(b'csr').decode(), status='approved',
                                       subject='CN=device'))
        db.session.commit()
    r = auth_client.delete(f"/api/v2/cas/{ca['id']}")
    assert r.status_code == 204, r.data
    with app.app_context():
        assert SCEPRequest.query.filter_by(ca_refid=refid).count() == 0


@pytest.mark.parametrize("binding", ["scep_profile", "acme_local_domain", "policy"])
def test_a_ca_still_referenced_is_refused_with_409(app, auth_client, create_ca, binding):
    ca = create_ca(cn=f'Referenced CA {binding}')
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        if binding == "scep_profile":
            bound = ScepProfile(name=f'bound-{ca["id"]}', url_slug=f'bound-{ca["id"]}',
                                ca_refid=row.refid, auto_approve=True)
            expected = 'SCEP profile'
        elif binding == "acme_local_domain":
            bound = AcmeLocalDomain(domain=f'bound-{ca["id"]}.example.test', issuing_ca_id=row.id)
            expected = 'ACME domain'
        else:
            bound = CertificatePolicy(name=f'scoped-{ca["id"]}', ca_id=row.id, rules='{}')
            expected = 'policy'
        db.session.add(bound)
        db.session.commit()
        bound_id, bound_cls = bound.id, type(bound)
    try:
        r = auth_client.delete(f"/api/v2/cas/{ca['id']}")
        assert r.status_code == 409, r.data
        assert expected in r.get_data(as_text=True)
        assert_success(auth_client.get(f"/api/v2/cas/{ca['id']}"))
    finally:
        # The binding and its CA must not outlive the test: the dashboard
        # counts enabled SCEP profiles across the shared database
        with app.app_context():
            db.session.delete(db.session.get(bound_cls, bound_id))
            db.session.commit()
        auth_client.delete(f"/api/v2/cas/{ca['id']}")


def test_files_survive_a_refused_commit(app, auth_client, create_ca, monkeypatch):
    ca = create_ca(cn='Files after commit CA')
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        # The key only reaches the disk on installs that mirror it; the
        # certificate always does
        files = [p for p in (ca_cert_path(row), ca_key_path(row)) if p.exists()]
    assert files

    def _refuse():
        raise RuntimeError('commit refused')
    monkeypatch.setattr(db.session, 'commit', _refuse, raising=False)
    r = auth_client.delete(f"/api/v2/cas/{ca['id']}")
    monkeypatch.undo()
    assert r.status_code == 500, r.data
    assert all(p.exists() for p in files), 'the files went before the row did'

    r = auth_client.delete(f"/api/v2/cas/{ca['id']}")
    assert r.status_code == 204, r.data
    assert not any(p.exists() for p in files)


def test_settings_numbered_after_the_ca_go_with_it(app, auth_client, create_ca):
    """A SCEP challenge or a responder binding kept under the number would
    belong to the next CA SQLite gives that number to."""
    from models import SystemConfig
    ca = create_ca(cn='Numbered settings CA')
    keys = (f"scep_challenge_{ca['id']}", f"scep_challenge_{ca['id']}_generated_at",
            f"ocsp_responder_cert_{ca['id']}")
    with app.app_context():
        for key in keys:
            db.session.add(SystemConfig(key=key, value='kept-by-mistake'))
        db.session.commit()
    r = auth_client.delete(f"/api/v2/cas/{ca['id']}")
    assert r.status_code == 204, r.data
    with app.app_context():
        assert SystemConfig.query.filter(SystemConfig.key.in_(keys)).count() == 0
