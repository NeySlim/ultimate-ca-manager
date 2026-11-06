"""A restore puts a row back, whether or not the row is already here.

The restore used to apply a hand-picked subset of fields to a CA or a
certificate it found on the target: description, the PEMs, the key and the
revocation state. Everything else -- subject, serial, SANs, source, template,
CRL cadence, name constraints, url_slug, renewal history -- kept whatever
value the target happened to hold, so restoring an archive left an instance
matching neither the archive nor its own previous state.

These tests pin the symmetry: the same columns are written on an existing row
and on a new one, and they are the archive's.

Each backup is limited to the sections under test (`_only`): a full archive
restored into the session database would rewrite rows the rest of the suite
is looking at.
"""
import pytest

from models import db, CA, Certificate
from services.backup import manifest

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    """An include map that carries just these sections."""
    return {name: name in names for name in manifest.SECTIONS}


def _archived(svc, blob, section, identity, value):
    """The row a section of this archive holds, by its stable identity."""
    _key, data = svc._decrypt_framed(blob, PASSWORD)
    return next(row for row in data[section] if row[identity] == value)


class TestAnExistingAuthorityGoesBackToTheArchive:
    def test_every_changed_field_is_restored(self, app, create_ca):
        created = create_ca(cn='Restore Symmetry CA')
        with app.app_context():
            row = db.session.get(CA, created['id'])
            row.url_slug = 'restore-symmetry'
            row.path_length = 2
            row.name_constraints_permitted = '[{"type": "dns", "value": ".example.test"}]'
            row.crl_publish_interval_hours = 12
            db.session.commit()

            svc = _service()
            blob = svc.create_backup(PASSWORD, include=_only('certificate_authorities'))
            refid = db.session.get(CA, created['id']).refid
            archived = _archived(svc, blob, 'certificate_authorities', 'refid', refid)

            # Drift, of the kind an operator or an incident produces between
            # the backup and the restore.
            row = db.session.get(CA, created['id'])
            row.descr = 'drifted description'
            row.subject = 'CN=Drifted, O=Elsewhere'
            row.serial = 9999
            row.url_slug = 'drifted-slug'
            row.path_length = 0
            row.name_constraints_permitted = '[{"type": "dns", "value": ".evil.test"}]'
            row.crl_publish_interval_hours = 1
            db.session.commit()

            svc.restore_backup(blob, PASSWORD)
            db.session.expire_all()

            back = db.session.get(CA, created['id'])
            assert back.descr == archived['descr']
            assert back.subject == archived['subject']
            assert back.serial == archived['serial']
            assert back.url_slug == archived['url_slug'] == 'restore-symmetry'
            assert back.path_length == archived['path_length'] == 2
            assert back.name_constraints_permitted == \
                archived['name_constraints_permitted']
            assert back.crl_publish_interval_hours == \
                archived['crl_publish_interval_hours'] == 12

    def test_the_row_keeps_its_own_primary_key(self, app, create_ca):
        """The id is the one field a restore must not carry over: it is what
        every other row on this installation already points at."""
        created = create_ca(cn='Restore Keeps Its Key CA')
        with app.app_context():
            svc = _service()
            blob = svc.create_backup(PASSWORD, include=_only('certificate_authorities'))
            row = db.session.get(CA, created['id'])
            refid, before = row.refid, row.id
            row.descr = 'drifted'
            db.session.commit()

            svc.restore_backup(blob, PASSWORD)
            db.session.expire_all()

            back = CA.query.filter_by(refid=refid).first()
            assert back.id == before
            assert back.descr != 'drifted'


class TestAnExistingCertificateGoesBackToTheArchive:
    def test_every_changed_field_is_restored(self, app, create_ca, create_cert):
        ca = create_ca(cn='Restore Symmetry Cert CA')
        created = create_cert(cn='restore-symmetry.example.com', ca_id=ca['id'])
        with app.app_context():
            row = db.session.get(Certificate, created['id'])
            row.template_overrides = '["digest"]'
            row.renewed_times = 2
            db.session.commit()

            svc = _service()
            blob = svc.create_backup(PASSWORD, include=_only('certificates'))
            refid = db.session.get(Certificate, created['id']).refid
            archived = _archived(svc, blob, 'certificates', 'refid', refid)

            row = db.session.get(Certificate, created['id'])
            row.subject = 'CN=drifted.example.com'
            row.serial_number = 'DEADBEEF'
            row.san_dns = '["drifted.example.com"]'
            row.source = 'scep'
            row.renewed_times = 41
            row.template_overrides = '["validity_days"]'
            db.session.commit()

            svc.restore_backup(blob, PASSWORD)
            db.session.expire_all()

            back = db.session.get(Certificate, created['id'])
            assert back.id == created['id'], 'the target row kept its own key'
            assert back.subject == archived['subject']
            assert back.serial_number == archived['serial_number']
            assert back.san_dns == archived['san_dns']
            assert back.source == archived['source']
            assert back.renewed_times == archived['renewed_times'] == 2
            assert back.template_overrides == archived['template_overrides'] \
                == '["digest"]'


class TestANewAuthorityIsStillCreatedWithEverything:
    """Symmetry must not have been bought by breaking the create path."""

    def test_a_missing_authority_comes_back_whole(self, app, create_ca):
        created = create_ca(cn='Restore Recreates CA')
        with app.app_context():
            row = db.session.get(CA, created['id'])
            row.url_slug = 'restore-recreates'
            row.path_length = 1
            row.crl_publish_interval_hours = 6
            db.session.commit()

            svc = _service()
            blob = svc.create_backup(PASSWORD, include=_only('certificate_authorities'))
            refid = db.session.get(CA, created['id']).refid
            archived = _archived(svc, blob, 'certificate_authorities', 'refid', refid)

            CA.query.filter_by(refid=refid).delete()
            db.session.commit()
            assert CA.query.filter_by(refid=refid).first() is None

            try:
                svc.restore_backup(blob, PASSWORD)
                back = CA.query.filter_by(refid=refid).first()
                assert back is not None, 'the authority was not recreated'
                assert back.descr == archived['descr']
                assert back.subject == archived['subject']
                assert back.serial_number == archived['serial_number']
                assert back.url_slug == 'restore-recreates'
                assert back.path_length == 1
                assert back.crl_publish_interval_hours == 6
                assert back.valid_to is not None
                assert back.crt and back.prv, 'the key material was not restored'
            finally:
                CA.query.filter_by(refid=refid).delete()
                db.session.commit()
