"""EST simplereenroll claims the renewed row by compare-and-set: of two concurrent
re-enrollments with the same certificate, only one is issued."""
from sqlalchemy import update

from models import Certificate, db
from tests.test_final_review_followups import _csr, _enrol, _pem
from tests.test_est_rfc7030 import _post_csr, est_config  # noqa: F401


def test_second_reenroll_loses_the_claim(client, app, est_config, monkeypatch):
    """The row is archived between the status check and the write, as by a concurrent request."""
    import services.cert.issued_lookup as issued_lookup
    leaf, key = _enrol(client, 'reenroll-race.example.test')
    checked = issued_lookup.issued_certificate_status

    def check_then_lose_the_race(ca, cert):
        row, status = checked(ca, cert)
        db.session.execute(update(Certificate).where(Certificate.id == row.id).values(archived=True)
                           .execution_options(synchronize_session=False))
        return row, status

    monkeypatch.setattr(issued_lookup, 'issued_certificate_status', check_then_lose_the_race)
    with app.app_context():
        before = Certificate.query.count()
    csr, _ = _csr('reenroll-race.example.test', key=key)
    r = _post_csr(client, 'simplereenroll', csr, client_cert_pem=_pem(leaf))
    assert r.status_code == 403, r.data
    assert b'superseded' in r.data
    with app.app_context():
        assert Certificate.query.count() == before
