"""A template without a key type, when the policies refuse every default key: creating or
importing it is a 400, and WSTEP and XCEP leave it out instead of failing the whole CA."""
import io
import json
import uuid
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from lxml import etree

from models import CertificatePolicy, db
from services.policy_service import PolicyViolation
from tests.fixtures.templates import templates_created_here_removed
from utils import issuance_defaults


@pytest.fixture(autouse=True, scope='module')
def _templates_stay_in_this_module(app):
    with templates_created_here_removed(app):
        yield


@pytest.fixture
def rsa4096_only(app):
    with app.app_context():
        pol = CertificatePolicy(name=f'rsa4096-only-{uuid.uuid4().hex[:8]}', policy_type='issuance',
                                requires_approval=False, min_approvers=1, is_active=True, priority=100)
        pol.set_rules({'allowed_key_types': ['RSA-4096']})
        db.session.add(pol)
        db.session.commit()
        pid = pol.id
    yield
    with app.app_context():
        db.session.delete(db.session.get(CertificatePolicy, pid))
        db.session.commit()


def test_creating_a_template_without_key_is_a_400(auth_client, rsa4096_only):
    r = auth_client.post('/api/v2/templates', content_type='application/json', data=json.dumps(
        {'name': f'no-key-{uuid.uuid4().hex[:6]}', 'template_type': 'web_server'}))
    assert r.status_code == 400, r.get_json()
    assert 'no default key type is allowed' in json.dumps(r.get_json())


def test_importing_a_template_without_key_is_a_400(auth_client, rsa4096_only):
    body = json.dumps({'name': f'no-key-import-{uuid.uuid4().hex[:6]}', 'template_type': 'custom'})
    r = auth_client.post('/api/v2/templates/import', content_type='multipart/form-data',
                         data={'file': (io.BytesIO(body.encode()), 'tpl.json')})
    assert r.status_code == 400, r.get_json()
    assert 'no default key type is allowed' in json.dumps(r.get_json())


def test_the_service_refuses_a_template_without_key_as_a_value_error(app, rsa4096_only):
    from services.template_service import TemplateService
    with app.app_context():
        with pytest.raises(ValueError, match='no default key type is allowed'):
            TemplateService.create_template({'name': f'no-key-svc-{uuid.uuid4().hex[:6]}'}, 'tester')
        db.session.rollback()


def _tpl(tid, key_type):
    return SimpleNamespace(
        id=tid, name=f'T{tid}', template_type='client_auth', key_type=key_type, digest='sha256',
        validity_days=365, autoenroll_enabled=True, ad_derived_subject=False, is_active=True,
        extensions_template=json.dumps({'key_usage': ['digitalSignature'],
                                        'extended_key_usage': ['clientAuth']}))


def _refuse_default_of(template_id):
    real = issuance_defaults.default_issue_key_type

    def default(ca_id=None, profile=None, template_id_=None, **kw):
        tid = kw.get('template_id', template_id_)
        if tid == template_id:
            raise PolicyViolation('Policy violation: no default key type is allowed (test)')
        return real(ca_id, profile, tid)
    return default


def _csr(cn='wstep-no-key.example.test', template_name=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
               .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False))
    if template_name:
        from asn1crypto import core
        builder = builder.add_extension(x509.UnrecognizedExtension(
            x509.ObjectIdentifier('1.3.6.1.4.1.311.20.2'), core.BMPString(template_name).dump()),
            critical=False)
    return builder.sign(key, hashes.SHA256())


def test_wstep_match_leaves_out_a_template_whose_default_is_refused(app, monkeypatch):
    from services.wstep import wstep_service
    from services.xcep import policy_builder
    keyless, keyed = _tpl(9001, ''), _tpl(9002, 'RSA-2048')
    monkeypatch.setattr(wstep_service, 'default_issue_key_type', _refuse_default_of(9001))
    monkeypatch.setattr(policy_builder, '_resolve_templates_for_ca', lambda ca, rows: [keyless, keyed])
    ca = SimpleNamespace(id=None, refid='ca-wstep', template_pins=[])
    with app.app_context():
        assert wstep_service._match_template(ca, _csr()) == (keyed, None)
        template, refusal = wstep_service._match_template(ca, _csr(template_name='T9001'))
    assert template is None and 'T9001' in refusal and 'key type' in refusal


def test_xcep_leaves_out_a_template_whose_default_is_refused(app, monkeypatch):
    from services.xcep import policy_builder
    def refused(*_a, **_k):
        raise PolicyViolation('Policy violation: no default key type is allowed (test)')
    monkeypatch.setattr(issuance_defaults, 'default_issue_key_type', refused)
    ca = SimpleNamespace(id=None, refid='ca-xcep', descr='Test CA', crt=None, template_pins=[])
    with app.app_context():
        root = etree.fromstring(policy_builder.build_get_policies_response(
            ca, [_tpl(9101, None), _tpl(9102, 'RSA-2048')]))
    names = [e.text for e in root.iter(f'{{{policy_builder.XCEP_NS}}}commonName')]
    assert names == ['T9102']
