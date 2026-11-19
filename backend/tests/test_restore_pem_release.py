"""A restore lets the PEMs of the certificates it wrote go from the session, batch by batch,
and whatever reads one afterwards in the same transaction gets it back from the database."""
from sqlalchemy import inspect as sa_inspect

from models import Certificate, db

PEMS = ('crt', 'prv', 'csr')


def test_restored_certificates_release_their_pems_and_read_them_back(app, create_ca, create_cert,
                                                                     monkeypatch):
    from services.backup import restore_core
    from services.backup_service import BackupService
    monkeypatch.setattr(restore_core, 'PEM_RELEASE_ROWS', 2)
    ca = create_ca(cn='PEM release CA')
    ids = [create_cert(cn=f'pem-release-{i}.example.com', ca_id=ca['id'])['id'] for i in range(3)]
    with app.app_context():
        rows = [db.session.get(Certificate, i) for i in ids]
        expected = {row.refid: tuple(getattr(row, c) for c in PEMS) for row in rows}
        exported = [c for c in BackupService()._export_certificates(True) if c['refid'] in expected]
        assert len(exported) == 3
        try:
            BackupService()._restore_certificates(
                {'certificates': exported}, {'cas': 0, 'certificates': 0}, master_key=None)
            for row in rows:
                assert not set(PEMS) & set(sa_inspect(row).dict), 'a written certificate kept its PEMs'
            for row in rows:
                assert tuple(getattr(row, c) for c in PEMS) == expected[row.refid]
        finally:
            db.session.rollback()
