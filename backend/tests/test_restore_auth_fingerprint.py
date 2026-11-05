"""A client certificate is found again by its fingerprint, as the manifest identifies it.

The restorer looked it up by serial number, which is unique only per issuer:
the same certificate spelled with another serial came back twice, and another
certificate holding the same serial was overwritten by the archive's.
"""
import pytest

from models import User, db
from models.auth_certificate import AuthCertificate
from services.backup.restore.conflict import RestoreConflictError
from tests.test_backup_restore_failfast import PASSWORD, _only, _reseal, _service


def _row(**values):
    admin = User.query.filter_by(username='admin').first()
    row = AuthCertificate(user_id=admin.id, cert_subject='CN=lot7 client', **values)
    db.session.add(row)
    db.session.commit()
    return row


def _archive_with(fingerprint, serial=None, **changes):
    """An archive of the client certificates, the one with `fingerprint` (or `serial`) changed."""
    svc = _service()
    blob = svc.create_backup(PASSWORD, include=_only('auth_certificates'))
    _key, data = svc._decrypt_framed(blob, PASSWORD)
    archived = next(r for r in data['auth_certificates']
                    if (r['cert_serial'] == serial if serial else r['cert_fingerprint'] == fingerprint))
    archived.update(changes)
    return _reseal(blob, data)


@pytest.fixture
def cleanup(app):
    yield
    with app.app_context():
        db.session.rollback()
        AuthCertificate.query.filter(AuthCertificate.cert_subject == 'CN=lot7 client').delete()
        db.session.commit()


def test_the_same_certificate_spelled_with_another_serial_is_updated(app, cleanup):
    with app.app_context():
        _row(cert_serial='LOT7:AB', cert_fingerprint='lot7-same-fp', name='here')
        blob = _archive_with('lot7-same-fp', cert_serial='lot7ab', name='from the archive')
        _service().restore_backup(blob, PASSWORD, mode='merge')
        db.session.expire_all()
        rows = AuthCertificate.query.filter_by(cert_fingerprint='lot7-same-fp').all()
        assert [(r.cert_serial, r.name) for r in rows] == [('lot7ab', 'from the archive')]


def test_another_certificate_with_the_same_serial_is_not_overwritten(app, cleanup):
    with app.app_context():
        _row(cert_serial='lot7-shared', cert_fingerprint='lot7-mine', name='mine')
        blob = _archive_with('lot7-mine', cert_fingerprint='lot7-theirs', name='theirs')
        with pytest.raises(RestoreConflictError) as refusal:
            _service().restore_backup(blob, PASSWORD, mode='merge')
        assert 'auth_certificates' in str(refusal.value)
        db.session.expire_all()
        mine = AuthCertificate.query.filter_by(cert_serial='lot7-shared').one()
        assert (mine.cert_fingerprint, mine.name) == ('lot7-mine', 'mine')


@pytest.mark.parametrize('here, archived', [
    ('', 'lot7-later-fp'),             # enrolled by a route that stored no fingerprint
    ('AB:CD:EF:01', 'abcdef01'),       # the same digest, spelled by another route
])
def test_the_row_of_that_serial_is_updated_when_its_fingerprint_agrees(app, cleanup, here, archived):
    with app.app_context():
        _row(cert_serial='lot7-agree', cert_fingerprint=here, name='here')
        blob = _archive_with(None, serial='lot7-agree', cert_fingerprint=archived, name='archived')
        _service().restore_backup(blob, PASSWORD, mode='merge')
        db.session.expire_all()
        rows = AuthCertificate.query.filter_by(cert_serial='lot7-agree').all()
        assert [(r.cert_fingerprint, r.name) for r in rows] == [(archived, 'archived')]
