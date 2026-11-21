"""The policy identity is the profile's (MS-XCEP 3.1.4.1.3.23): its policyID and template OID root
are fixed once, never derived from a CA, so a CA change keeps what enrolled clients registered."""
import json
import re
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from lxml import etree

from models import CA, CATemplatePin, WindowsEnrollmentProfile, WindowsProfileTemplate, db
from models.certificate_template import CertificateTemplate
from services.ca_service import CAService
from services.wstep import wstep_service
from services.xcep.policy_builder import XCEP_NS, _policy_oid_for_template, build_get_policies_response
from tests.fixtures.templates import delete_templates
from tests.test_wstep_renew_tls import _eku_csr, _renew, _template_oid
from tests.windows_profile_support import default_profile
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401
from utils.policy_identity import TEMPLATE_OID_ARC, derived_oid_root, derived_policy_id

URL = '/api/v2/windows-profiles'
ROOT_SHAPE = re.compile(re.escape(TEMPLATE_OID_ARC) + r'(\.\d+){4}')
NS = {'x': XCEP_NS}


@pytest.fixture(autouse=True, scope='module')
def _cas_go_with_the_module(drop_new_cas_and_certificates):
    yield


@pytest.fixture
def template(app):
    """One active clientAuth template, pinned to no CA: every CA without pins offers it."""
    with app.app_context():
        t = CertificateTemplate(name=f'C16 {uuid.uuid4().hex[:6]}', template_type='usr_cert',
                                key_type='RSA-2048', validity_days=30, digest='sha256', is_active=True,
                                extensions_template=json.dumps({'extended_key_usage': ['clientAuth']}))
        db.session.add(t)
        db.session.commit()
        template_id = t.id
    yield template_id
    with app.app_context():
        WindowsProfileTemplate.query.filter_by(template_id=template_id).delete()
        CATemplatePin.query.filter_by(template_id=template_id).delete()
        delete_templates([template_id])
        db.session.commit()


@pytest.fixture
def profiles(app):
    made = []

    def _make(template_id=None, **columns):
        with app.app_context():
            profile = WindowsEnrollmentProfile(name=f'c16-{uuid.uuid4().hex[:8]}', enabled=True,
                                               is_default=False, **columns)
            db.session.add(profile)
            db.session.flush()
            if template_id is not None:
                db.session.add(WindowsProfileTemplate(profile_id=profile.id, template_id=template_id))
            db.session.commit()
            made.append(profile.id)
            return profile.id
    yield _make
    with app.app_context():
        for profile_id in made:
            WindowsProfileTemplate.query.filter_by(profile_id=profile_id).delete()
            WindowsEnrollmentProfile.query.filter_by(id=profile_id).delete()
        db.session.commit()


def _refid(app, ca):
    with app.app_context():
        return db.session.get(CA, ca['id']).refid


def _served(profile_id):
    """(policyID, {template name: OID}) XCEP serves for the profile, as the CEP route builds it."""
    from services.windows_profiles import policy_ca
    profile = db.session.get(WindowsEnrollmentProfile, profile_id)
    templates = CertificateTemplate.query.filter_by(is_active=True).all()
    root = etree.fromstring(build_get_policies_response(policy_ca(profile), templates, profile=profile))
    oids = {o.findtext('x:oIDReferenceID', namespaces=NS): o.findtext('x:value', namespaces=NS)
            for o in root.iterfind('.//x:oIDs/x:oID', NS)}
    names = {p.findtext('x:attributes/x:commonName', namespaces=NS):
             oids[p.findtext('x:policyOIDReference', namespaces=NS)]
             for p in root.iterfind('.//x:policies/x:policy', NS)}
    return root.findtext('.//x:response/x:policyID', namespaces=NS), names


def _csr(template_oid=None, cn='c16.example.test', key=None):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
               .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False))
    if template_oid:
        builder = builder.add_extension(
            x509.MSCertificateTemplate(x509.ObjectIdentifier(template_oid), 100, 0), critical=False)
    return builder.sign(key, hashes.SHA256()), key


def test_changing_the_policy_then_the_issuing_ca_keeps_the_identity_served(app, create_ca, template, profiles):
    """Criterion 1: policyID and template OIDs stay; a request naming the old OID is issued by the new CA."""
    first, second, third = (create_ca(cn=f'C16 move {n} {uuid.uuid4().hex[:5]}') for n in range(3))
    profile_id = profiles(template, issuing_ca_refid=_refid(app, first))
    with app.app_context():
        name = db.session.get(CertificateTemplate, template).name
        before = _served(profile_id)
        assert list(before[1]) == [name]
        profile = db.session.get(WindowsEnrollmentProfile, profile_id)
        profile.policy_ca_refid = _refid(app, second)
        db.session.commit()
        assert _served(profile_id) == before
        profile.policy_ca_refid, profile.issuing_ca_refid = None, _refid(app, third)
        db.session.commit()
        assert _served(profile_id) == before
        assert before[0] not in {derived_policy_id(_refid(app, ca)) for ca in (first, second, third)}

    csr, _key = _csr(before[1][name])
    with app.app_context():
        pem, err = wstep_service.issue(db.session.get(CA, third['id']), csr.public_bytes(serialization.Encoding.DER),
                                       30, profile=db.session.get(WindowsEnrollmentProfile, profile_id))
        assert err is None, err
        cert = x509.load_pem_x509_certificate(pem.encode())
        third_ca = x509.load_pem_x509_certificate(
            __import__('base64').b64decode(db.session.get(CA, third['id']).crt))
    assert cert.issuer == third_ca.subject
    assert _template_oid(cert).dotted_string == before[1][name]


def test_a_template_oid_derived_from_a_ca_is_not_offered_at_issuance(app, create_ca, template, profiles):
    """The OID is recognised under the profile's root alone, not under one of its CAs."""
    ca = create_ca(cn=f'C16 derived {uuid.uuid4().hex[:5]}')
    profile_id = profiles(template, issuing_ca_refid=_refid(app, ca))
    with app.app_context():
        record = db.session.get(CA, ca['id'])
        derived = _policy_oid_for_template(record, db.session.get(CertificateTemplate, template))
        csr, _key = _csr(derived)
        pem, err = wstep_service.issue(record, csr.public_bytes(serialization.Encoding.DER), 30,
                                       profile=db.session.get(WindowsEnrollmentProfile, profile_id))
    assert pem is None
    assert err == f'Certificate template {derived} is not offered by this CA'


UPGRADE_TEMPLATE_OIDS = (
    'Windows enrollment, template OIDs: with an XCEP CA apart from the WSTEP CA, 2.x also issued a request '
    'naming the template OID derived from the WSTEP CA, which its policy never announced. 3.0 issues only '
    'the template OIDs the policy of the profile announces (for the profile `default` of an upgrade, those '
    '2.x announced, derived from its XCEP CA) and refuses any other with `Certificate template <OID> is not '
    'offered by this CA`; the renewal of a certificate carrying such an OID is accepted as before.')


def test_a_profile_holding_the_2254_identity_refuses_the_issuing_ca_oid(
        app, create_ca, template, profiles):
    """The upgrade note, frozen: 2.254 announced the XCEP CA's OIDs; the WSTEP CA's one, which only
    a hand-written request could name, is refused at issuance (renewal: the CA-derived test below)."""
    from pathlib import Path
    policy, issuing = (create_ca(cn=f'C16 split {n} {uuid.uuid4().hex[:5]}') for n in ('policy', 'issuing'))
    policy_refid, issuing_refid = _refid(app, policy), _refid(app, issuing)
    profile_id = profiles(template, issuing_ca_refid=issuing_refid, policy_ca_refid=policy_refid,
                          policy_id=derived_policy_id(policy_refid), policy_oid_root=derived_oid_root(policy_refid))
    with app.app_context():
        t = db.session.get(CertificateTemplate, template)
        record = db.session.get(CA, issuing['id'])
        announced = _policy_oid_for_template(db.session.get(CA, policy['id']), t)
        assert _served(profile_id)[1] == {t.name: announced}
        results = {}
        for oid in (announced, _policy_oid_for_template(record, t)):
            csr, _key = _csr(oid)
            results[oid] = wstep_service.issue(record, csr.public_bytes(serialization.Encoding.DER), 30,
                                               profile=db.session.get(WindowsEnrollmentProfile, profile_id))[1]
    refused = _policy_oid_for_template(record, t)
    assert results == {announced: None, refused: f'Certificate template {refused} is not offered by this CA'}
    note = ' '.join((Path(__file__).resolve().parents[2] / 'UPGRADE.md').read_text().split())
    assert UPGRADE_TEMPLATE_OIDS in note


def test_two_profiles_on_one_policy_ca_serve_distinct_identities(app, create_ca, template, profiles):
    """Criterion 2: the same policyID requires the same response (MS-XCEP 3.1.4.1.3.23)."""
    refid = _refid(app, create_ca(cn=f'C16 shared {uuid.uuid4().hex[:5]}'))
    one, two = (profiles(template, issuing_ca_refid=refid, policy_ca_refid=refid) for _ in range(2))
    with app.app_context():
        (id_one, oids_one), (id_two, oids_two) = _served(one), _served(two)
    assert id_one != id_two
    assert set(oids_one.values()).isdisjoint(oids_two.values())
    for policy_id in (id_one, id_two):
        assert uuid.UUID(policy_id).version == 4


def test_the_api_shows_the_identity_and_never_changes_it(app, auth_client, create_ca):
    """Criterion 6: read-only, ignored by a PUT like the other fields no route writes."""
    refid, other = _refid(app, create_ca(cn='C16 api one')), _refid(app, create_ca(cn='C16 api two'))
    r = auth_client.post(URL, json={'name': f'c16-api-{uuid.uuid4().hex[:6]}', 'issuing_ca_refid': refid})
    assert r.status_code == 201, r.data
    created = r.get_json()['data']
    try:
        assert uuid.UUID(created['policy_id']).version == 4
        assert ROOT_SHAPE.fullmatch(created['policy_oid_root'])
        r = auth_client.put(f"{URL}/{created['id']}", json={
            'policy_id': str(uuid.uuid4()), 'policy_oid_root': f'{TEMPLATE_OID_ARC}.1.2.3.4',
            'policy_ca_refid': other})
        assert r.status_code == 200, r.data
        shown = auth_client.get(f"{URL}/{created['id']}").get_json()['data']
        assert (shown['policy_id'], shown['policy_oid_root']) == (created['policy_id'], created['policy_oid_root'])
        assert shown['policy_ca_refid'] == other
        listed = auth_client.get(f'{URL}?per_page=200').get_json()['data']
        assert any(p['id'] == created['id'] and p['policy_id'] == created['policy_id'] for p in listed)
    finally:
        assert auth_client.delete(f"{URL}/{created['id']}").status_code == 200


@pytest.mark.parametrize('method', ['put', 'patch'])
def test_a_write_naming_the_identity_leaves_what_xcep_serves(app, auth_client, create_ca, template, method):
    """No route applies the two fields, at creation or on an update: XCEP serves what was drawn."""
    refid = _refid(app, create_ca(cn=f'C16 write {method} {uuid.uuid4().hex[:5]}'))
    forged = {'policy_id': str(uuid.uuid4()), 'policy_oid_root': f'{TEMPLATE_OID_ARC}.1.2.3.4'}
    r = auth_client.post(URL, json={'name': f'c16-w-{uuid.uuid4().hex[:6]}', 'issuing_ca_refid': refid,
                                    'template_ids': [template], **forged})
    assert r.status_code == 201, r.data
    created = r.get_json()['data']
    try:
        with app.app_context():
            served = _served(created['id'])
        assert served[0] == created['policy_id'] != forged['policy_id']
        assert all(o.startswith(created['policy_oid_root'] + '.') for o in served[1].values()) and served[1]
        r = getattr(auth_client, method)(f"{URL}/{created['id']}", json={**forged, 'validity_days': 40})
        assert r.status_code == 200, r.data
        with app.app_context():
            assert db.session.get(WindowsEnrollmentProfile, created['id']).validity_days == 40
            assert _served(created['id']) == served
    finally:
        assert auth_client.delete(f"{URL}/{created['id']}").status_code == 200


def test_the_default_profile_made_by_a_settings_write_has_an_identity(app):
    """The configuration routes create the default profile at their first write."""
    from services import windows_profiles
    with app.app_context():
        saved = default_profile()
        if saved is not None:
            saved.is_default = False
            db.session.flush()
        try:
            made = windows_profiles.default_for_write('c16', fill=False)
            db.session.flush()
            assert uuid.UUID(made.policy_id).version == 4 and ROOT_SHAPE.fullmatch(made.policy_oid_root)
        finally:
            db.session.rollback()


@pytest.mark.parametrize('path', ['tls', 'xml'])
def test_a_certificate_carrying_a_ca_derived_oid_renews(app, create_ca, template, path):
    """Criterion 5: issued before profiles held the identity, its OID derives from a CA; the
    renewal accepts it as before and stamps the OID the profile serves now."""
    ca = create_ca(cn=f'C16 renew {path} {uuid.uuid4().hex[:5]}')
    with app.app_context():
        profile = default_profile(create=True)
        db.session.commit()
        record = db.session.get(CA, ca['id'])
        t = db.session.get(CertificateTemplate, template)
        derived = _policy_oid_for_template(record, t)
        served = f'{profile.policy_oid_root}.1.{t.id}'
        csr, key = _csr(cn=f'c16-renew-{path}.example.test')
        pem, _serial = CAService.sign_csr_from_crypto(
            ca=record, csr=csr, validity_days=30, source='wstep', ms_certificate_template_oid=derived,
            cert_type='client_cert', extra_ekus=[ExtendedKeyUsageOID.CLIENT_AUTH.dotted_string],
            template_ekus=[ExtendedKeyUsageOID.CLIENT_AUTH.dotted_string])
    old = x509.load_pem_x509_certificate(pem.encode())
    assert derived != served
    cert, err = _renew(app, ca['id'], path, old, key, _eku_csr(old, key, ExtendedKeyUsageOID.CLIENT_AUTH))
    assert err is None, err
    assert _template_oid(cert).dotted_string == served



# --- Backup and restore (criterion 4) ----------------------------------------------------------

PASSWORD = 'policy-identity-password-0123456789'


def _archive(without_identity=False, monkeypatch=None):
    """An archive of the profiles alone; *without_identity*: as written before these columns."""
    from services.backup import manifest
    from services.backup_service import BackupService
    include = {name: name == 'windows_enrollment_profiles' for name in manifest.SECTIONS}
    if not without_identity:
        return BackupService().create_backup(PASSWORD, include=include)
    with monkeypatch.context() as m:
        exclude = manifest.SECTIONS['windows_enrollment_profiles'].exclude
        for column in ('policy_id', 'policy_oid_root'):
            m.setitem(exclude, column, 'not written before the profiles held their identity')
        return BackupService().create_backup(PASSWORD, include=include)


def _restore(blob, mode):
    from services.backup_service import BackupService
    return BackupService().restore_backup(blob, PASSWORD, mode=mode)


def _identity(name):
    profile = WindowsEnrollmentProfile.query.filter_by(name=name).first()
    return (profile.policy_id, profile.policy_oid_root) if profile is not None else None


def _set_identity(name, policy_id, root):
    profile = WindowsEnrollmentProfile.query.filter_by(name=name).one()
    profile.policy_id, profile.policy_oid_root = policy_id, root
    db.session.commit()


def _drop(name):
    profile = WindowsEnrollmentProfile.query.filter_by(name=name).one()
    WindowsProfileTemplate.query.filter_by(profile_id=profile.id).delete()
    db.session.delete(profile)
    db.session.commit()


LOCAL = ('00000000-0000-4000-8000-0000000000c1', f'{TEMPLATE_OID_ARC}.11.22.33.44')


@pytest.mark.parametrize('mode', ['replace', 'merge'])
def test_a_restored_profile_serves_the_identity_it_was_archived_with(app, create_ca, profiles, mode):
    refid = _refid(app, create_ca(cn=f'C16 backup {mode} {uuid.uuid4().hex[:5]}'))
    profile_id = profiles(issuing_ca_refid=refid)
    with app.app_context():
        name = db.session.get(WindowsEnrollmentProfile, profile_id).name
        kept = _identity(name)
        blob = _archive()
        _drop(name)
        _restore(blob, mode)
        assert _identity(name) == kept
        # Restored over the profile it was taken from: unchanged, whatever the mode
        _restore(blob, mode)
        assert _identity(name) == kept
        _drop(name)


def test_a_replacing_restore_puts_the_archived_identity_back(app, create_ca, profiles):
    """The archive becomes the instance: clients enrolled before it registered its identity."""
    profile_id = profiles(issuing_ca_refid=_refid(app, create_ca(cn=f'C16 replace {uuid.uuid4().hex[:5]}')))
    with app.app_context():
        name = db.session.get(WindowsEnrollmentProfile, profile_id).name
        archived = _identity(name)
        blob = _archive()
        _set_identity(name, *LOCAL)
        _restore(blob, 'replace')
        assert _identity(name) == archived
        _drop(name)


def test_a_merge_keeps_the_identity_an_existing_profile_serves(app, create_ca, profiles):
    """The merge adds the archive to the instance: what this profile's clients registered stays."""
    profile_id = profiles(issuing_ca_refid=_refid(app, create_ca(cn=f'C16 merge {uuid.uuid4().hex[:5]}')))
    with app.app_context():
        name = db.session.get(WindowsEnrollmentProfile, profile_id).name
        blob = _archive()
        _set_identity(name, *LOCAL)
        _restore(blob, 'merge')
        assert _identity(name) == LOCAL
        _drop(name)


def test_a_merged_profile_never_takes_an_identity_another_profile_serves(app, create_ca, profiles):
    """Renamed here after the backup: the archived row is a second profile, with an identity of its own."""
    profile_id = profiles(issuing_ca_refid=_refid(app, create_ca(cn=f'C16 renamed {uuid.uuid4().hex[:5]}')))
    with app.app_context():
        profile = db.session.get(WindowsEnrollmentProfile, profile_id)
        name, archived = profile.name, _identity(profile.name)
        blob = _archive()
        profile.name = f'{name}-renamed'
        db.session.commit()
        results = _restore(blob, 'merge')
        restored = _identity(name)
        assert restored is not None and _identity(f'{name}-renamed') == archived
        assert restored[0] != archived[0] and restored[1] != archived[1]
        assert any('gets a new policy identity' in w for w in results['warnings'])
        _drop(name)


@pytest.mark.parametrize('mode', ['replace', 'merge'])
def test_an_archive_without_the_identity_restores_it_derived_from_the_ca(app, create_ca, profiles,
                                                                         monkeypatch, mode):
    """Before these columns: a new profile derives it from its CA, as the upgrade does; an
    existing one keeps the identity it serves."""
    refid = _refid(app, create_ca(cn=f'C16 legacy {mode} {uuid.uuid4().hex[:5]}'))
    profile_id = profiles(issuing_ca_refid=refid)
    with app.app_context():
        name = db.session.get(WindowsEnrollmentProfile, profile_id).name
        kept = _identity(name)
        blob = _archive(without_identity=True, monkeypatch=monkeypatch)
        _restore(blob, mode)
        assert _identity(name) == kept
        _drop(name)
        _restore(blob, mode)
        assert _identity(name) == (derived_policy_id(refid), derived_oid_root(refid))
        _drop(name)
