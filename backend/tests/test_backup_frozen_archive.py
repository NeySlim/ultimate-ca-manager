"""An archive written before the export read its sections page by page restores as it did.

The fixture is a v4 archive written by the release before that change: one CA,
three certificates (the last revoked, the first owned by a group and naming the
second as related). The format did not change, so it must restore whole.
"""
from pathlib import Path

import pytest
from cryptography import x509

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

ARCHIVE = Path(__file__).parent / 'fixtures' / 'backup_v4_before_paged_export.ucmbkp'
PASSWORD = 'Frozen-Archive-Pass-27'


@pytest.fixture(scope='module')
def restored(app):
    from services.backup_service import BackupService
    with app.app_context():
        _key, archived = BackupService()._decrypt_framed(ARCHIVE.read_bytes(), PASSWORD)
        results = BackupService().restore_backup_from_path(ARCHIVE, PASSWORD, mode='replace')
    return archived, results


def test_every_certificate_comes_back_with_its_key(app, restored):
    from models import Certificate
    from utils.cert_issuer import stored_private_key_matches
    archived, results = restored
    assert results['certificates'] == len(archived['certificates']) == 3
    with app.app_context():
        for row in archived['certificates']:
            cert = Certificate.query.filter_by(refid=row['refid']).one()
            assert cert.serial_number == row['serial_number']
            pem = x509.load_pem_x509_certificate(row['certificate_pem'].encode())
            assert stored_private_key_matches(cert.prv, pem, context='frozen archive') is True


def test_revocations_and_links_come_back(app, restored):
    from models import Certificate
    from models.group import Group
    from models.revoked_serial import RevokedSerial
    archived, _results = restored
    first, second, revoked = archived['certificates']
    with app.app_context():
        here = {row['refid']: Certificate.query.filter_by(refid=row['refid']).one()
                for row in archived['certificates']}
        assert here[revoked['refid']].revoked and not here[first['refid']].revoked
        assert RevokedSerial.query.filter_by(caref=revoked['caref'],
                                             serial_number=revoked['serial_number']).count() == 1
        assert here[first['refid']].related_certificate_id == here[second['refid']].id
        owner = Group.query.get(here[first['refid']].owner_group_id)
        assert owner is not None and owner.name == 'frozen-archive-owners'
