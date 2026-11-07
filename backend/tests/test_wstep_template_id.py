"""A WSTEP certificate names its matched template (``Certificate.template_id``), renewals included."""
import pytest
from cryptography.x509.oid import ExtendedKeyUsageOID

from models import Certificate
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


def test_issuance_records_the_matched_template(app, templated_ca):
    ca_id = templated_ca('WSTEP template id CA', USER_AND_CODESIGN)
    cert, _key = _wstep_issued(app, ca_id, 'wstep-tid-issue.example.test')
    assert _template_oid(cert) is not None
    assert _template_of(app, cert) == _template_id(app, 'WSTEP template id CA User')


@pytest.mark.parametrize('path', ['tls', 'xml'])
def test_renewal_records_the_template_it_keeps(app, templated_ca, path):
    ca_id = templated_ca(f'WSTEP template id renew CA {path}', USER_AND_CODESIGN)
    old_cert, old_key = _wstep_issued(app, ca_id, f'wstep-tid-renew-{path}.example.test')
    cert, err = _renew(app, ca_id, path, old_cert, old_key,
                       _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH))
    assert err is None, err
    assert _template_of(app, cert) == _template_id(app, f'WSTEP template id renew CA {path} User')


def test_a_legacy_renewal_records_the_template_it_is_stamped_with(app, templated_ca):
    ca_id = templated_ca('WSTEP template id legacy CA', USER_AND_CODESIGN)
    old_cert, old_key = _issue(app, ca_id, 'wstep-tid-legacy.example.test')
    assert _template_of(app, old_cert) is None
    cert, err = _renew(app, ca_id, 'tls', old_cert, old_key,
                       _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH))
    assert err is None, err
    assert _template_of(app, cert) == _template_id(app, 'WSTEP template id legacy CA User')


def test_a_renewal_stamped_with_no_template_records_none(app, templated_ca):
    ca_id = templated_ca('WSTEP template id broad CA', {'Broad': (['clientAuth', 'emailProtection'], None)})
    old_cert, old_key = _issue(app, ca_id, 'wstep-tid-broad.example.test')
    cert, err = _renew(app, ca_id, 'tls', old_cert, old_key,
                       _eku_csr(old_cert, old_key, ExtendedKeyUsageOID.CLIENT_AUTH))
    assert err is None, err
    assert _template_oid(cert) is None and _template_of(app, cert) is None


def test_a_template_holding_wstep_certificates_is_not_deleted(app, auth_client, templated_ca):
    ca_id = templated_ca('WSTEP template id delete CA', USER_AND_CODESIGN)
    template_id = _template_id(app, 'WSTEP template id delete CA User')

    def usage():
        return auth_client.get(f'/api/v2/templates/{template_id}').get_json()['data']['usage_count']
    before = usage()
    _wstep_issued(app, ca_id, 'wstep-tid-delete.example.test')
    assert usage() == before + 1
    r = auth_client.delete(f'/api/v2/templates/{template_id}')
    assert r.status_code == 409, r.get_json()


def test_the_template_teardown_lets_its_certificates_go(app, create_ca):
    """SQLite gives a deleted template's id to the next one: no certificate may still name it."""
    import json
    from models import CATemplatePin, db
    from tests.fixtures.templates import delete_templates
    ca_data = create_ca(cn='WSTEP template id teardown CA')
    with app.app_context():
        t = CertificateTemplate(name='WSTEP template id teardown', template_type='usr_cert', key_type='RSA-2048',
                                validity_days=30, digest='sha256', is_active=True,
                                extensions_template=json.dumps({'extended_key_usage': ['clientAuth']}))
        db.session.add(t)
        db.session.flush()
        db.session.add(CATemplatePin(ca_id=ca_data['id'], template_id=t.id))
        db.session.commit()
        template_id = t.id
    cert, _key = _wstep_issued(app, ca_data['id'], 'wstep-tid-teardown.example.test')
    assert _template_of(app, cert) == template_id
    with app.app_context():
        delete_templates([template_id])
        db.session.commit()
        assert Certificate.query.filter_by(template_id=template_id).count() == 0
        assert db.session.get(CertificateTemplate, template_id) is None
        assert CATemplatePin.query.filter_by(template_id=template_id).count() == 0
