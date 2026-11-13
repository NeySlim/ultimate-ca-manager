"""XCEP announces each template's szOID_CERTIFICATE_TEMPLATE extension (MS-WCCE 2.2.2.7.7.2).

CertEnroll copies a policy's announced extensions into its PKCS#10 and names no template
otherwise: without it two templates sharing their EKUs were told apart by template id only."""
import base64

from asn1crypto import core as asn1_core
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree

from models import CA, db
from services.xcep.policy_builder import XCEP_NS, build_get_policies_response
from tests.test_wstep_issue import ISSUE_URL, _basic_auth, _build_rst, wstep_config  # noqa: F401
from tests.test_wstep_protocol_conformance import _fault, _fault_code
from tests.test_wstep_requested_template import TWINS, _oid_of
from tests.test_wstep_subject_source import _issue, subject_ca  # noqa: F401
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

TEMPLATE_EXT_OID = '1.3.6.1.4.1.311.21.7'


class _CertificateTemplateOID(asn1_core.Sequence):
    _fields = [('template_id', asn1_core.ObjectIdentifier),
               ('major', asn1_core.Integer, {'optional': True}),
               ('minor', asn1_core.Integer, {'optional': True})]


def _x(el, path):
    return el.find(path.replace('x:', f'{{{XCEP_NS}}}'))


def _announced(app, ca_id):
    """{template name: {'oid', 'revision', 'extensions': [(oid, critical, der)]}} from GetPolicies."""
    with app.app_context():
        root = etree.fromstring(build_get_policies_response(db.session.get(CA, ca_id), []))
    oids = {int(_x(o, 'x:oIDReferenceID').text): (_x(o, 'x:value').text, int(_x(o, 'x:group').text))
            for o in root.iter(f'{{{XCEP_NS}}}oID')}
    policies = {}
    for policy in root.iter(f'{{{XCEP_NS}}}policy'):
        exts = [(oids[int(_x(e, 'x:oIDReference').text)], _x(e, 'x:critical').text == 'true',
                 base64.b64decode(_x(e, 'x:value').text))
                for e in policy.iter(f'{{{XCEP_NS}}}extension')]
        policies[_x(policy, 'x:attributes/x:commonName').text] = {
            'oid': oids[int(_x(policy, 'x:policyOIDReference').text)][0],
            'revision': (int(_x(policy, 'x:attributes/x:revision/x:majorRevision').text),
                         int(_x(policy, 'x:attributes/x:revision/x:minorRevision').text)),
            'extensions': exts}
    return policies


def _csr_copying(extensions, cn='copy.example.test'):
    """A PKCS#10 carrying a policy's announced extensions verbatim, as CertEnroll builds it."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
    for (oid, _group), critical, der in extensions:
        builder = builder.add_extension(
            x509.UnrecognizedExtension(x509.ObjectIdentifier(oid), der), critical=critical)
    return builder.sign(key, hashes.SHA256())


def test_each_policy_announces_its_template_extension(app, subject_ca):
    ca_id = subject_ca('Tplext announce CA', TWINS)
    policies = _announced(app, ca_id)
    assert set(policies) == {f'Tplext announce CA {n}' for n in TWINS}
    for name, policy in policies.items():
        template_exts = [e for e in policy['extensions'] if e[0][0] == TEMPLATE_EXT_OID]
        assert len(template_exts) == 1, name
        (_oid, group), critical, der = template_exts[0]
        assert group == 6 and critical is False  # MS-XCEP group 6: extension; MS-WCCE: SHOULD be FALSE
        value = _CertificateTemplateOID.load(der)
        assert value['template_id'].dotted == policy['oid'] == _oid_of(app, ca_id, name)
        # MS-WCCE 3.1.2.4.2.2.1.9 / 3.1.2.4.2.2.2.4: the versions are the policy's revision
        # Pinned: a higher revision than the issued certificates' makes every client re-enroll
        assert (value['major'].native, value['minor'].native) == policy['revision'] == (100, 0)


def test_a_template_of_capped_ekus_only_is_not_announced(app, subject_ca):
    """WSTEP refuses it: Windows is not offered a template it cannot enroll under."""
    ca_id = subject_ca('Tplext capped CA', {**TWINS, 'OCSP': ('ocsp', ['ocspSigning'], False, 'RSA-2048')})
    assert set(_announced(app, ca_id)) == {f'Tplext capped CA {n}' for n in TWINS}

def test_a_request_copying_the_announced_extensions_is_issued_under_its_template(app, subject_ca):
    """Two clientAuth templates: the EKU match alone always picked the older one."""
    ca_id = subject_ca('Tplext twin CA', TWINS)
    policy = _announced(app, ca_id)['Tplext twin CA VPNUser']
    cert, err = _issue(app, ca_id, _csr_copying(policy['extensions']))
    assert err is None, err
    issued = cert.extensions.get_extension_for_oid(x509.ObjectIdentifier(TEMPLATE_EXT_OID))
    assert issued.value.template_id.dotted_string == policy['oid']
    announced = [der for (oid, _g), _c, der in policy['extensions'] if oid == TEMPLATE_EXT_OID]
    assert [issued.value.public_bytes()] == announced and issued.critical is False


def test_a_wstep_client_error_is_a_sender_fault(client, wstep_config):
    """SOAP 1.2: a fault the request's content causes is env:Sender, which its HTTP binding sends as 400."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'fault.example.test')])).add_extension(
        x509.MSCertificateTemplate(x509.ObjectIdentifier('1.2.3.4.5'), 100, 0), critical=False,
    ).sign(key, hashes.SHA256())
    r = client.post(ISSUE_URL, data=_build_rst(csr), headers=_basic_auth())
    assert r.status_code == 400
    assert _fault(r.data)[0] == 'Certificate template 1.2.3.4.5 is not offered by this CA'
    assert _fault_code(r.data) == 's:Sender'
    r = client.post(ISSUE_URL, data=_build_rst(csr), headers={'Authorization': 'Basic Zm9vOmJhcg=='})
    assert r.status_code == 400
    assert _fault_code(r.data) == 's:Sender'
