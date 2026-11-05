"""An archive from before the port 0 repair must not bring those URLs back: the migration has run."""
import pytest

from models import CA, db


def _service():
    from services.backup_service import BackupService
    return BackupService()


@pytest.mark.parametrize('delete_first', [True, False], ids=['new row', 'existing row'])
def test_a_restored_ca_loses_port_zero_and_keeps_the_rest(app, create_ca, delete_first):
    ca = create_ca(cn=f'Port zero restore {delete_first}')
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        row.cdp_url = 'http://pki.example.com:0/cdp/x.crl'
        row.set_ocsp_urls(['http://pki.example.com:0/ocsp', 'http://other.example.com:8080/ocsp'])
        row.aia_ca_issuers_url = 'http://pki.example.com:8080/ca/x.cer'
        db.session.commit()
        svc = _service()
        refid = row.refid
        data = next(c for c in svc._export_cas(True) if c['refid'] == refid)
        if delete_first:
            db.session.delete(row)
            db.session.commit()
        svc._restore_cas({'certificate_authorities': [data]}, {'cas': 0, 'certificates': 0}, master_key=None)
        db.session.commit()
        db.session.expire_all()
        restored = CA.query.filter_by(refid=refid).first()
        assert restored.get_cdp_urls() == ['http://pki.example.com/cdp/x.crl']
        assert restored.get_ocsp_urls() == ['http://pki.example.com/ocsp', 'http://other.example.com:8080/ocsp']
        assert restored.get_aia_urls() == ['http://pki.example.com:8080/ca/x.cer']
