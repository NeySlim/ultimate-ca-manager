"""Compliance preflight: each detector against the profile rules, on SQLite and
PostgreSQL, then the route and the command line.

The installation and session fixtures are those of the FIPS preflight tests:
each case seeds inside a transaction it rolls back. The route and the command
line are in test_compliance_preflight_api.py.
"""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import NameOID

import compliance_profiles
from models import (CA, Certificate, CertificatePolicy, CertificateTemplate, HsmKey, HsmProvider,
                    SystemConfig, db)
from services import compliance_preflight, fips_preflight, preflight_core
from tests.test_fips_preflight import installation, session  # noqa: F401  (fixtures)
from utils.datetime_utils import utc_now

_KEYS = {}


def _key(kind):
    if kind not in _KEYS:
        _KEYS[kind] = {
            'rsa2048': lambda: rsa.generate_private_key(public_exponent=65537, key_size=2048),
            'rsa3072': lambda: rsa.generate_private_key(public_exponent=65537, key_size=3072),
            'p256': lambda: ec.generate_private_key(ec.SECP256R1()),
            'p384': lambda: ec.generate_private_key(ec.SECP384R1()),
            'ed25519': ed25519.Ed25519PrivateKey.generate,
        }[kind]()
    return _KEYS[kind]


def _cert(key, cn, days):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    digest = None if isinstance(key, ed25519.Ed25519PrivateKey) else hashes.SHA256()
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=days))
            .sign(key, digest))


def _stored(cert):
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


def _ca(kind, descr, days=365, scheme='pkcs1v15', **extra):
    cert = _cert(_key(kind), descr, days)
    ca = CA(refid=str(uuid.uuid4()), descr=descr, crt=_stored(cert), prv='key', signature_scheme=scheme,
            valid_to=utc_now() + timedelta(days=days), **extra)
    db.session.add(ca)
    db.session.flush()
    return ca


def _leaf(kind, descr, days, ca=None):
    cert = _cert(_key(kind), descr, days)
    row = Certificate(refid=str(uuid.uuid4()), descr=descr, subject_cn=descr, crt=_stored(cert),
                      valid_to=utc_now() + timedelta(days=days), caref=ca.refid if ca else None)
    db.session.add(row)
    db.session.flush()
    return row


def _config(key, value):
    db.session.add(SystemConfig(key=key, value=value))
    db.session.flush()


def _report(profile, ca=None):
    report = compliance_preflight.run(profile, ca.id if ca else None)
    assert report['errors'] == []
    return report


def _finding(report, finding_id):
    return next((f for f in report['findings'] if f['id'] == finding_id), None)


def _assert(report, finding_id, severity, *needles, count=None):
    finding = _finding(report, finding_id)
    assert finding is not None, f'{finding_id} found nothing: {[f["id"] for f in report["findings"]]}'
    assert finding['severity'] == severity
    if count is not None:
        assert finding['count'] == count
    for needle in needles:
        assert any(needle in e for e in finding['examples']), finding['examples']
    return finding


def _years(n):
    return 365 * n + 5


# --- certificate authorities ------------------------------------------------

def test_horizon_catches_a_rsa_2048_authority_valid_until_2036_under_anssi(session):
    _ca('rsa2048', 'old-root', days=_years(10))
    report = _report('anssi')
    _assert(report, 'ca.key_horizon', 'blocker', 'old-root', count=1)
    assert report['ready'] is False


def test_a_short_rsa_2048_authority_has_no_horizon_finding_under_anssi(session):
    _ca('rsa2048', 'short-root', days=365)
    report = _report('anssi')
    assert _finding(report, 'ca.key_horizon') is None
    _assert(report, 'ca.key_type.advisory', 'warning', 'short-root')


def test_key_type_outside_the_profile_is_a_blocker_and_a_clean_authority_passes(session):
    _ca('rsa2048', 'weak')
    _ca('rsa3072', 'fine', scheme='pss')
    report = _report('bsi')
    _assert(report, 'ca.key_type', 'blocker', 'weak', count=1)
    assert _finding(report, 'ca.key_type.advisory') is None
    assert not any('fine' in e for f in report['findings'] for e in f['examples'])


def test_nist_curves_under_bsi_are_allowed_with_a_notice(session):
    _ca('p384', 'ec-root')
    report = _report('bsi')
    assert [f['id'] for f in report['findings']] == ['ca.key_type.advisory']
    assert report['findings'][0]['severity'] == 'warning'
    assert report['ready'] is True


def test_rsa_scheme_follows_the_profile(session):
    _ca('rsa3072', 'v15', scheme='pkcs1v15')
    _ca('rsa3072', 'pss', scheme='pss')
    bsi = _report('bsi')
    _assert(bsi, 'ca.signature_scheme', 'blocker', 'v15', 'rsa_pkcs1v15', count=1)
    anssi = _report('anssi')
    assert _finding(anssi, 'ca.signature_scheme') is None
    _assert(anssi, 'ca.signature_scheme.advisory', 'warning', 'v15', count=1)


def test_eddsa_authority_is_a_notice_under_anssi_and_a_blocker_elsewhere(session):
    _ca('ed25519', 'ed-root')
    _assert(_report('anssi'), 'ca.eddsa_key.advisory', 'info', 'ed-root')
    assert _finding(_report('anssi'), 'ca.eddsa_key') is None
    for profile in ('bsi', 'eu-acm'):
        _assert(_report(profile), 'ca.eddsa_key', 'blocker', 'ed-root')


def test_hardware_key_is_required_under_eu_acm_only(session):
    _ca('p384', 'software-root')
    provider = HsmProvider(name='Soft', type='pkcs11',
                           config=json.dumps({'module_path': '/usr/lib/softhsm/libsofthsm2.so'}))
    real = HsmProvider(name='Hardware', type='pkcs11',
                       config=json.dumps({'module_path': '/usr/lib/vendor/libhsm.so'}))
    session.add_all([provider, real])
    session.flush()
    keys = []
    for owner in (provider, real):
        key = HsmKey(provider_id=owner.id, key_identifier=owner.name, label=owner.name,
                     algorithm='EC-P384', key_type='asymmetric', purpose='signing')
        session.add(key)
        keys.append(key)
    session.flush()
    _ca('p384', 'soft-hsm-root', hsm_key_id=keys[0].id)
    _ca('p384', 'real-hsm-root', hsm_key_id=keys[1].id)
    finding = _assert(_report('eu-acm'), 'ca.key_protection', 'blocker', 'software-root', 'soft-hsm-root', count=2)
    assert not any('real-hsm-root' in e for e in finding['examples'])
    assert _finding(_report('bsi'), 'ca.key_protection') is None


def test_an_authority_without_a_signing_key_is_left_alone(session):
    ca = _ca('rsa2048', 'trust-anchor', days=_years(10))
    ca.prv = None
    session.flush()
    assert _report('anssi')['findings'] == []


def test_ca_scope_narrows_the_report(session):
    _ca('rsa2048', 'weak-one')
    other = _ca('p384', 'fine-one')
    report = _report('bsi', other)
    assert [f['id'] for f in report['findings']] == ['ca.key_type.advisory']
    assert not any('weak-one' in e for f in report['findings'] for e in f['examples'])
    assert report['ca_id'] == other.id


# --- certificates -----------------------------------------------------------

def test_active_certificates_past_the_horizon(session):
    ca = _ca('p384', 'issuer')
    other = _ca('p384', 'other-issuer')
    _leaf('rsa2048', 'late-leaf', _years(6), ca)
    _leaf('rsa2048', 'early-leaf', 365, ca)
    _leaf('rsa2048', 'foreign-leaf', _years(6), other)
    _leaf('rsa2048', 'self-issued', _years(6))
    report = _report('anssi')
    _assert(report, 'certificates.key_horizon', 'blocker', 'late-leaf', 'foreign-leaf', count=2)
    scoped = _report('anssi', ca)
    _assert(scoped, 'certificates.key_horizon', 'blocker', 'late-leaf', count=1)


def test_a_horizon_advisory_is_a_notice_for_certificates(session):
    ca = _ca('p384', 'issuer')
    _leaf('p256', 'far-leaf', _years(10), ca)
    report = _report('bsi')
    assert _finding(report, 'certificates.key_horizon') is None
    _assert(report, 'certificates.key_horizon.advisory', 'info', 'far-leaf')


# --- templates, policies, ACME ----------------------------------------------

def test_templates_key_type_and_digest(session):
    for name, key_type, digest, active in (('rsa2048-tpl', 'RSA-2048', 'sha256', True),
                                           ('sha1-tpl', 'EC-P256', 'sha1', True),
                                           ('inactive-tpl', 'RSA-2048', 'sha1', False),
                                           ('good-tpl', 'EC-P384', 'sha384', True)):
        session.add(CertificateTemplate(name=name, template_type='custom', key_type=key_type,
                                        digest=digest, is_active=active, extensions_template='{}'))
    session.flush()
    report = _report('bsi')
    _assert(report, 'templates.key_type', 'blocker', 'rsa2048-tpl', count=1)
    _assert(report, 'templates.digest', 'blocker', 'sha1-tpl', count=1)


def test_rsa_2048_issuance_ends_after_its_date_under_eu_acm(session, monkeypatch):
    session.add(CertificateTemplate(name='rsa2048-tpl', template_type='custom', key_type='RSA-2048',
                                    extensions_template='{}'))
    session.flush()
    before = datetime(2026, 6, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(compliance_preflight, 'utc_now', lambda: before)
    assert _finding(_report('eu-acm'), 'templates.key_type') is None
    later = datetime(2027, 3, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(compliance_preflight, 'utc_now', lambda: later)
    _assert(_report('eu-acm'), 'templates.key_type', 'blocker', 'rsa2048-tpl')


def test_policies_key_types_digests_and_unknown_labels(session):
    session.add(CertificatePolicy(name='wide', rules=json.dumps(
        {'allowed_key_types': ['RSA-2048', 'EC-P384'], 'allowed_digests': ['sha1', 'sha256']})))
    session.add(CertificatePolicy(name='unknown-only', rules=json.dumps({'allowed_key_types': ['brainpool']})))
    session.add(CertificatePolicy(name='fine', rules=json.dumps({'allowed_key_types': ['EC-P384']})))
    session.add(CertificatePolicy(name='off', is_active=False,
                                  rules=json.dumps({'allowed_key_types': ['RSA-2048']})))
    session.flush()
    report = _report('bsi')
    _assert(report, 'policies.key_type', 'blocker', 'wide', count=1)
    _assert(report, 'policies.digest', 'blocker', 'wide', count=1)
    _assert(report, 'policies.unknown_key_types_only', 'blocker', 'unknown-only', count=1)


def test_a_policy_for_another_authority_is_out_of_scope(session):
    ca = _ca('p384', 'scoped')
    other = _ca('p384', 'other')
    session.add(CertificatePolicy(name='other-ca', ca_id=other.id,
                                  rules=json.dumps({'allowed_key_types': ['RSA-2048']})))
    session.flush()
    assert _finding(_report('bsi', ca), 'policies.key_type') is None
    assert _finding(_report('bsi', other), 'policies.key_type') is not None


def test_acme_profiles_and_default_digest(session):
    _config('acme_profiles', json.dumps({'old': {'digest': 'sha1'}, 'new': {'digest': 'sha384'},
                                         'inherits': {}}))
    _config('acme_default_digest', 'sha1')
    report = _report('bsi')
    finding = _assert(report, 'acme.digest', 'blocker', 'profile old', 'acme_default_digest')
    assert finding['count'] == 2  # 'inherits' takes the effective default, sha256


# --- signers ----------------------------------------------------------------

def test_ocsp_responder_key(session):
    ca = _ca('p384', 'issuer')
    responder = _leaf('rsa2048', 'weak-responder', 30)
    _config(f'ocsp_responder_cert_{ca.id}', str(responder.id))
    _assert(_report('bsi'), 'ocsp.responder_key', 'blocker', 'weak-responder')
    assert _finding(_report('bsi', _ca('p384', 'unrelated')), 'ocsp.responder_key') is None


def test_tsa_signer_must_be_ec_under_bsi(session):
    signer = _leaf('rsa3072', 'rsa-tsa', 30)
    _config('tsa_signer_cert_refid', signer.refid)
    _config('tsa_enabled', 'true')
    finding = _assert(_report('bsi'), 'tsa.signer_key', 'blocker', 'rsa-tsa')
    assert 'EC-P' in finding['examples'][0]
    assert _finding(_report('anssi'), 'tsa.signer_key') is None
    _assert(_report('anssi'), 'tsa.signer_key.advisory', 'warning', 'rsa-tsa')


def test_a_disabled_tsa_is_not_checked(session):
    signer = _leaf('rsa3072', 'rsa-tsa', 30)
    _config('tsa_signer_cert_refid', signer.refid)
    _config('tsa_enabled', 'false')
    assert _finding(_report('bsi'), 'tsa.signer_key') is None


# --- contract ---------------------------------------------------------------

def test_rules_come_from_the_profiles_not_from_a_copy():
    sources = {d.id for d in compliance_preflight.DETECTORS}
    assert {'ca.key_horizon', 'ca.signature_scheme', 'ca.key_protection', 'tsa.signer_key'} <= sources
    assert compliance_profiles.PROFILES['bsi']['rules']['tsa_signer_key_types']


def test_every_profile_runs_on_an_empty_installation(session):
    for name in compliance_profiles.PROFILE_NAMES:
        report = _report(name)
        assert report['ready'] is True
        assert report['profile']['name'] == name
        assert set(report['checked']) == {d.id for d in compliance_preflight.DETECTORS}


def test_unknown_profile_and_ca_are_refused(session):
    with pytest.raises(ValueError):
        compliance_preflight.run('etsi')
    with pytest.raises(LookupError):
        compliance_preflight.run('bsi', 999999)


def test_a_failing_detector_is_reported_not_raised(session):
    def boom(_ctx):
        raise RuntimeError('boom')
    broken = preflight_core.Detector('x.broken', 'blocker', 't', 'r', boom)
    report = compliance_preflight.run('bsi', detectors=[broken])
    assert report['ready'] is False
    assert report['errors'][0]['id'] == 'x.broken'


def test_the_core_is_what_fips_preflight_runs_on(session):
    assert fips_preflight.Detector is preflight_core.Detector
    assert fips_preflight.DETECTORS is not compliance_preflight.DETECTORS
    broken = preflight_core.Detector('x.broken', 'blocker', 't', 'r', lambda: 1 / 0)
    assert fips_preflight.run([broken])['errors'][0]['id'] == 'x.broken'
