"""A WSTEP certificate names its matched template (``Certificate.template_id``), renewals included."""
import pytest
from cryptography.x509.oid import ExtendedKeyUsageOID

from models import Certificate, db
from models.certificate_template import CertificateTemplate
from tests import test_wstep_renew_tls as renew_tls
from tests.test_wstep_renew_tls import USER_AND_CODESIGN, _eku_csr, _issue, _renew, _template_oid, _wstep_issued

templated_ca = renew_tls.templated_ca


def _template_of(app, cert):
    with app.app_context():
        return Certificate.query.filter_by(serial_number=str(cert.serial_number)).one().template_id


def _template_id(app, name):
    with app.app_context():
        return CertificateTemplate.query.filter_by(name=name).one().id


@pytest.fixture
def unbind_templates(app):
    """The templated_ca teardown deletes templates: the rows naming them let go first."""
    yield
    with app.app_context():
        Certificate.query.filter(Certificate.template_id.isnot(None),
                                 Certificate.subject.like('CN=wstep-tid-%')).update(
            {'template_id': None}, synchronize_session=False)
        db.session.commit()


def test_issuance_records_the_matched_template(app, templated_ca, unbind_templates):
    ca_id = templated_ca('WSTEP template id CA', USER_AND_CODESIGN)
    cert, _key = _wstep_issued(app, ca_id, 'wstep-tid-issue.example.test')
    assert _template_oid(cert) is not None
    assert _template_of(app, cert) == _template_id(app, 'WSTEP template id CA User')


@pytest.mark.parametrize('path', ['tls', 'xml'])
def test_renewal_records_the_template_it_keeps(app, templated_ca, unbind_templates, path):
    ca_id = templated_ca(f'WSTEP template id renew CA {path}', USER_AND_CODESIGN)
    old_cert, old_key = _wstep_issued(app, ca_id, f'wstep-tid-renew-{path}.example.test')
    cert, err = _renew(app, ca_id, path, old_cert, old_key,
                       _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH))
    assert err is None, err
    assert _template_of(app, cert) == _template_id(app, f'WSTEP template id renew CA {path} User')


def test_a_legacy_renewal_records_the_template_it_is_stamped_with(app, templated_ca, unbind_templates):
    ca_id = templated_ca('WSTEP template id legacy CA', USER_AND_CODESIGN)
    old_cert, old_key = _issue(app, ca_id, 'wstep-tid-legacy.example.test')
    assert _template_of(app, old_cert) is None
    cert, err = _renew(app, ca_id, 'tls', old_cert, old_key,
                       _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH))
    assert err is None, err
    assert _template_of(app, cert) == _template_id(app, 'WSTEP template id legacy CA User')


def test_a_renewal_stamped_with_no_template_records_none(app, templated_ca, unbind_templates):
    ca_id = templated_ca('WSTEP template id broad CA', {'Broad': (['clientAuth', 'emailProtection'], None)})
    old_cert, old_key = _issue(app, ca_id, 'wstep-tid-broad.example.test')
    cert, err = _renew(app, ca_id, 'tls', old_cert, old_key,
                       _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH))
    assert err is None, err
    assert _template_oid(cert) is None and _template_of(app, cert) is None


def test_a_template_holding_wstep_certificates_is_not_deleted(app, auth_client, templated_ca, unbind_templates):
    ca_id = templated_ca('WSTEP template id delete CA', USER_AND_CODESIGN)
    _wstep_issued(app, ca_id, 'wstep-tid-delete.example.test')
    template_id = _template_id(app, 'WSTEP template id delete CA User')
    r = auth_client.delete(f'/api/v2/templates/{template_id}')
    assert r.status_code == 409, r.get_json()
    assert auth_client.get(f'/api/v2/templates/{template_id}').get_json()['data']['usage_count'] == 1
