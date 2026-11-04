"""EST simplereenroll claims the renewed row by compare-and-set: of two concurrent
re-enrollments with the same certificate, only one is issued."""
import base64

import pytest
from cryptography.hazmat.primitives import serialization
from sqlalchemy import update

from models import Certificate, db
from tests.test_final_review_followups import _csr, _enrol, _pem
from tests.test_est_rfc7030 import _post_csr, est_config  # noqa: F401


def _twin_row(original, cert, twin):
    columns = {c.name: getattr(original, c.name) for c in Certificate.__table__.columns
               if c.name not in ('id', 'refid')}
    if twin == 'hex_serial':
        columns['serial_number'] = format(cert.serial_number, 'X')
    else:
        pem = cert.public_bytes(serialization.Encoding.PEM).replace(b'\n', b'\r\n')
        columns['crt'] = base64.b64encode(pem).decode()
    row = Certificate(refid=f'{original.refid}-twin', **columns)
    db.session.add(row)
    db.session.commit()
    return row


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


@pytest.mark.parametrize('twin', ['hex_serial', 'crlf_pem'])
def test_a_twin_row_is_superseded_with_the_renewed_one(client, app, est_config, twin):
    """A certificate stored twice renews once, however the twin stores its serial or PEM."""
    cn = f'reenroll-{twin.replace("_", "-")}.example.test'
    leaf, key = _enrol(client, cn)
    with app.app_context():
        original = Certificate.query.filter_by(serial_number=str(leaf.serial_number)).one()
        ids = [original.id, _twin_row(original, leaf, twin).id]
    csr, _ = _csr(cn, key=key)
    assert _post_csr(client, 'simplereenroll', csr, client_cert_pem=_pem(leaf)).status_code == 200
    r = _post_csr(client, 'simplereenroll', csr, client_cert_pem=_pem(leaf))
    assert r.status_code == 403, r.data
    with app.app_context():
        assert [db.session.get(Certificate, i).archived for i in ids] == [True, True]
