"""An archive written by the paged export carries the rows the previous release wrote.

The four sections with a dedicated exporter were built whole, then completed
by `_merge_with_manifest` (frozen below as the release before it wrote it).
A reader of that release finds the same rows in an archive written now:
same keys, same values, the private key aside since it is sealed afresh.
"""
import json
from datetime import datetime

import pytest

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Dedicated-Rows-Frozen-41'
SEALED = ('private_key_pem_encrypted', '_private_key_plaintext', '_key_mismatch')


def _previous_merge(section_name, rows, index):
    """`BackupService._merge_with_manifest` as the release before the paged export had it."""
    from services.backup.export_generic import export_section
    from services.backup.manifest import SECTIONS
    section = SECTIONS[section_name]
    generic = export_section(section_name, index)
    by_identity = {tuple(str(row.get(name)) for name in section.identity): row for row in generic}
    merged = []
    for row in rows:
        key = tuple(str(row.get(name)) for name in section.identity)
        merged.append({**by_identity.get(key, {}), **row})
    return merged


def _previous_rows(service, index):
    from models import CA, Certificate
    from models.revoked_serial import RevokedSerial
    from models.ssh import SSHCertificateAuthority
    dedicated = {
        'certificate_authorities': [service._ca_row(row) for row in CA.query.order_by(CA.id)],
        'certificates': [service._certificate_row(row)
                         for row in Certificate.query.order_by(Certificate.id)],
        'revoked_serials': [service._revoked_serial_row(row)
                            for row in RevokedSerial.query.order_by(RevokedSerial.id)],
        'ssh_cas': [service._ssh_ca_row(row)
                    for row in SSHCertificateAuthority.query.order_by(SSHCertificateAuthority.id)],
    }
    return {name: _previous_merge(name, rows, index) for name, rows in dedicated.items()}


def _comparable(rows):
    return [json.loads(json.dumps({k: v for k, v in row.items() if k not in SEALED}, default=str))
            for row in rows]


@pytest.fixture(scope='module')
def populated(app, create_ca, create_cert):
    from models import CA, db
    from models.revoked_serial import RevokedSerial
    from models.ssh import SSHCertificateAuthority
    from tests.test_restore_extended_secrets import _ssh_key_material
    ca = create_ca(cn='Frozen Rows CA')
    for index in range(3):
        create_cert(cn=f'frozen-rows-{index}.example.com', ca_id=ca['id'])
    with app.app_context():
        # Read as None by the generic columns and False by the dedicated row: the latter wins
        db.session.get(CA, ca['id']).offline = None
        db.session.add_all([
            RevokedSerial(caref=db.session.get(CA, ca['id']).refid,
                          serial_number='frozen-rows-serial', valid_to=datetime(2030, 1, 1)),
            SSHCertificateAuthority(
                refid='frozen-rows-sshca', descr='frozen rows SSH CA', ca_type='user',
                public_key='ssh-ed25519 AAAA frozen', private_key=_ssh_key_material(),
                key_type='ed25519', fingerprint='SHA256:frozen-rows', serial_counter=3),
        ])
        db.session.commit()


def test_the_dedicated_sections_carry_the_previous_rows(app, populated):
    from services.backup.export_generic import IdentityIndex
    from services.backup_service import BackupService
    with app.app_context():
        service = BackupService()
        archive = b''.join(service.iter_backup(PASSWORD, kdf='pbkdf2'))
        _key, written = service._decrypt_framed(archive, PASSWORD)
        expected = _previous_rows(service, IdentityIndex())
        from services.backup.export_generic import export_section
        generic_cas = export_section('certificate_authorities', IdentityIndex())
    frozen = next(row for row in written['certificate_authorities']
                  if row['descr'] == 'Frozen Rows CA')
    generic = next(row for row in generic_cas if row['refid'] == frozen['refid'])
    assert generic['offline'] is None and frozen['offline'] is False
    for name, rows in expected.items():
        assert rows, name
        assert _comparable(written[name]) == _comparable(rows), name
    sealed = [row for row in written['certificates'] if row.get('private_key_pem_encrypted')]
    assert len(sealed) >= 3
