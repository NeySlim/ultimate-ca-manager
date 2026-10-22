"""Compliance profiles (anssi, bsi, eu-acm): policies in code bound to a CA.

A profile joins the system policies of the CA that holds it, after FIPS mode
and before the operator's policies; it binds future issuance only.
"""
import importlib
import json
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

import compliance_profiles
import fips_mode
from models import CA, SystemConfig, db
from models.audit_log import AuditLog
from services.policy_service import PolicyEvaluationService, SystemPolicy, with_system_policies

PG_URL = os.getenv('UCM_TEST_PG_URL')
JSON = 'application/json'


def _patch(auth_client, ca_id, **body):
    return auth_client.patch(f'/api/v2/cas/{ca_id}', data=json.dumps(body), content_type=JSON)


def _post_ca(auth_client, cn, **kwargs):
    data = {'type': 'root', 'commonName': cn, 'keyAlgo': 'RSA', 'keySize': 3072,
            'validityYears': 5, 'hashAlgorithm': 'sha256', 'signatureScheme': 'pss', **kwargs}
    return auth_client.post('/api/v2/cas', data=json.dumps(data), content_type=JSON)


def _leaf(auth_client, ca_id, cn, **extra):
    return auth_client.post('/api/v2/certificates', content_type=JSON,
                            data=json.dumps({'cn': cn, 'ca_id': ca_id, 'validity_days': 30, **extra}))


def _profile_names(app, ca_id):
    with app.app_context():
        return [p.name for p in PolicyEvaluationService.applicable_policies(ca_id)
                if isinstance(p, SystemPolicy)]


@pytest.fixture
def set_default(app):
    def _set(value):
        with app.app_context():
            row = SystemConfig.query.filter_by(key=compliance_profiles.DEFAULT_SETTING).first()
            if row is None:
                row = SystemConfig(key=compliance_profiles.DEFAULT_SETTING)
                db.session.add(row)
            row.value = value
            db.session.commit()
    yield _set
    with app.app_context():
        SystemConfig.query.filter_by(key=compliance_profiles.DEFAULT_SETTING).delete()
        db.session.commit()


# ---- the profiles themselves -------------------------------------------------

def test_the_valid_names_and_their_references():
    assert compliance_profiles.PROFILE_NAMES == ('anssi', 'bsi', 'eu-acm')
    refs = {n: compliance_profiles.PROFILES[n]['reference'] for n in compliance_profiles.PROFILE_NAMES}
    assert refs == {'anssi': 'ANSSI-PG-083 3.00', 'bsi': 'BSI-TR-02102-1 2026-01',
                    'eu-acm': 'ECCG-ACM 2.0'}
    assert all(compliance_profiles.PROFILES[n]['url'].startswith('https://') for n in refs)


def test_profile_policy_is_a_named_system_policy():
    policy = compliance_profiles.profile_policy('bsi')
    assert isinstance(policy, SystemPolicy)
    assert policy.name == 'Compliance profile bsi (BSI-TR-02102-1 2026-01)'
    rules = policy.get_rules()
    assert 'RSA-2048' not in rules['allowed_key_types'] and 'ED25519' not in rules['allowed_key_types']
    assert not any('BP' in label for p in compliance_profiles.PROFILES.values()
                   for label in p['rules']['allowed_key_types'])
    rules['allowed_key_types'].append('x')
    rules['advisories']['allowed_key_types'].append('x')
    assert 'x' not in policy.get_rules()['allowed_key_types']
    assert 'x' not in policy.get_rules()['advisories']['allowed_key_types']
    with pytest.raises(ValueError):
        compliance_profiles.profile_policy('etsi')


def test_edwards_keys_follow_the_arbitrage():
    labels = {n: compliance_profiles.PROFILES[n]['rules'] for n in compliance_profiles.PROFILE_NAMES}
    assert 'ED25519' in labels['anssi']['allowed_key_types']
    assert 'ED25519' not in labels['anssi']['advisories']['allowed_key_types']
    assert 'ED25519' not in labels['bsi']['allowed_key_types']
    assert 'ED25519' not in labels['eu-acm']['allowed_key_types']
    assert labels['eu-acm']['require_hsm_ca_key'] is True


# ---- injection ---------------------------------------------------------------

def test_applicable_policies_hold_the_profile_of_that_ca_only(app, auth_client, create_ca):
    plain = create_ca(cn='Profile plain CA')
    bsi = create_ca(cn='Profile bsi CA')
    anssi = create_ca(cn='Profile anssi CA')
    assert _patch(auth_client, bsi['id'], complianceProfile='bsi').status_code == 200
    assert _patch(auth_client, anssi['id'], complianceProfile='anssi').status_code == 200
    assert _profile_names(app, plain['id']) == []
    assert _profile_names(app, bsi['id']) == ['Compliance profile bsi (BSI-TR-02102-1 2026-01)']
    assert _profile_names(app, anssi['id']) == ['Compliance profile anssi (ANSSI-PG-083 3.00)']
    assert _profile_names(app, None) == []


def test_the_profile_is_not_doubled(app, auth_client, create_ca):
    ca = create_ca(cn='Profile no double CA')
    _patch(auth_client, ca['id'], complianceProfile='bsi')
    with app.app_context():
        policies = PolicyEvaluationService.applicable_policies(ca['id'])
        again = with_system_policies(policies, ca['id'])
        assert [p.name for p in again] == [p.name for p in policies]
        # A list that already holds a generic system policy still gets the profile once
        mixed = with_system_policies([SystemPolicy('generic', {})], ca['id'])
        assert [p.kind for p in mixed] == ['profile', None]


def test_fips_and_a_profile_intersect(app, auth_client, create_ca, monkeypatch):
    ca = create_ca(cn='Profile fips CA', keySize=3072)
    _patch(auth_client, ca['id'], complianceProfile='anssi')
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
    with app.app_context():
        names = _profile_names(app, ca['id'])
        assert names[0] == 'FIPS mode' and len(names) == 2
        # Ed25519: allowed by the ANSSI profile, refused by FIPS
        v, _, _ = PolicyEvaluationService.enforce_rules(
            PolicyEvaluationService.applicable_policies(ca['id']), key_type='ED25519', notify=False)
        assert any('FIPS mode' in m for m in v) and not any('anssi' in m for m in v)
        # RSA-2048: allowed by FIPS and anssi, refused once the profile is bsi
        key_types, _ = PolicyEvaluationService.effective_algorithms(ca['id'])
        assert 'RSA-2048' in key_types and 'ED25519' not in key_types
    _patch(auth_client, ca['id'], complianceProfile='bsi')
    with app.app_context():
        key_types, digests = PolicyEvaluationService.effective_algorithms(ca['id'])
        assert key_types == ['EC-P256', 'EC-P384', 'EC-P521', 'RSA-3072', 'RSA-4096']
        assert digests == ['sha256', 'sha384', 'sha512']


def test_a_rsa_2048_leaf_is_refused_under_bsi_and_passes_without(app, auth_client, create_ca):
    ca = create_ca(cn='Profile leaf CA', signatureScheme='pss')
    assert _leaf(auth_client, ca['id'], 'before.profile.example.test').status_code == 201
    assert _patch(auth_client, ca['id'], complianceProfile='bsi').status_code == 200
    r = _leaf(auth_client, ca['id'], 'under.bsi.example.test')
    assert r.status_code == 400, r.get_json()
    assert 'RSA-2048' in r.get_json()['message'] and 'bsi' in r.get_json()['message']
    # The same request with a key the profile allows is issued
    ec = _leaf(auth_client, ca['id'], 'rsa3072.bsi.example.test', key_type='rsa', key_size=3072)
    assert ec.status_code == 201, ec.get_json()
    assert _patch(auth_client, ca['id'], complianceProfile=None).status_code == 200
    assert _leaf(auth_client, ca['id'], 'after.profile.example.test').status_code == 201


# ---- API ---------------------------------------------------------------------

def test_create_with_a_profile(app, auth_client):
    r = _post_ca(auth_client, 'Profile created bsi', complianceProfile='bsi')
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['data']['compliance_profile'] == 'bsi'


def test_create_refuses_what_the_profile_forbids(app, auth_client):
    r = _post_ca(auth_client, 'Profile RSA2048 bsi', keySize=2048, complianceProfile='bsi')
    assert r.status_code == 400 and 'RSA-2048' in r.get_json()['message']
    with app.app_context():
        assert CA.query.filter_by(descr='Profile RSA2048 bsi').first() is None
    r = _post_ca(auth_client, 'Profile RSA2048 anssi', keySize=2048, validityDays=30,
                  complianceProfile='anssi')
    assert r.status_code == 201


def test_create_refuses_an_unknown_profile(app, auth_client):
    r = _post_ca(auth_client, 'Profile typo', complianceProfile='etsi')
    assert r.status_code == 400 and 'complianceProfile' in r.get_json()['message']
    with app.app_context():
        assert CA.query.filter_by(descr='Profile typo').first() is None


def test_the_global_default_seeds_new_cas_only(app, auth_client, create_ca, set_default):
    existing = create_ca(cn='Profile default existing')
    set_default('anssi')
    assert _profile_names(app, existing['id']) == []
    seeded = _post_ca(auth_client, 'Profile default seeded')
    assert seeded.get_json()['data']['compliance_profile'] == 'anssi'
    explicit = _post_ca(auth_client, 'Profile default overridden', complianceProfile='bsi')
    assert explicit.get_json()['data']['compliance_profile'] == 'bsi'
    none = _post_ca(auth_client, 'Profile default none', complianceProfile=None)
    assert none.get_json()['data']['compliance_profile'] is None
    set_default('nonsense')
    with app.app_context():
        assert compliance_profiles.default_profile() is None


def test_patch_sets_clears_and_audits(app, auth_client, create_ca):
    ca = create_ca(cn='Profile patch CA')
    r = _patch(auth_client, ca['id'], complianceProfile='eu-acm')
    assert r.status_code == 200 and r.get_json()['data']['compliance_profile'] == 'eu-acm'
    with app.app_context():
        entry = AuditLog.query.filter_by(action='ca_updated', resource_id=str(ca['id'])) \
            .order_by(AuditLog.id.desc()).first()
        assert 'compliance_profile none -> eu-acm' in entry.details
    r = _patch(auth_client, ca['id'], complianceProfile=None)
    assert r.get_json()['data']['compliance_profile'] is None
    with app.app_context():
        entry = AuditLog.query.filter_by(action='ca_updated', resource_id=str(ca['id'])) \
            .order_by(AuditLog.id.desc()).first()
        assert 'compliance_profile eu-acm -> none' in entry.details


def test_patch_refuses_an_unknown_profile_before_any_change(app, auth_client, create_ca):
    ca = create_ca(cn='Profile patch refused CA')
    _patch(auth_client, ca['id'], complianceProfile='bsi')
    r = _patch(auth_client, ca['id'], complianceProfile='etsi', name='renamed by a refused patch')
    assert r.status_code == 400
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        assert row.compliance_profile == 'bsi' and row.descr != 'renamed by a refused patch'


# ---- backups -----------------------------------------------------------------

def test_backups_keep_the_profile(app, auth_client, create_ca):
    from services.backup.backup_service import BackupService
    from services.backup.restore_core import RestoreCoreMixin as RestoreCore
    ca = create_ca(cn='Profile backup CA')
    _patch(auth_client, ca['id'], complianceProfile='bsi')
    with app.app_context():
        exported = next(r for r in BackupService()._export_cas(True) if r['refid'] == ca['refid'])
        assert exported['compliance_profile'] == 'bsi'
        row = db.session.get(CA, ca['id'])
        row.compliance_profile = None
        RestoreCore._apply_ca_fields(row, {'refid': row.refid, 'compliance_profile': 'anssi'})
        assert row.compliance_profile == 'anssi'
        RestoreCore._apply_ca_fields(row, {'refid': row.refid, 'compliance_profile': 'bogus'})
        assert row.compliance_profile == 'anssi'
        db.session.commit()


# ---- migration ---------------------------------------------------------------

def test_sqlite_migration_leaves_existing_cas_without_a_profile():
    m = importlib.import_module('migrations.107_ca_compliance_profile')
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {CA.__tablename__} (id INTEGER PRIMARY KEY, descr TEXT)")
    conn.execute(f"INSERT INTO {CA.__tablename__} VALUES (1, 'old')")
    m.upgrade(conn)
    m.upgrade(conn)
    assert conn.execute(f"SELECT compliance_profile FROM {CA.__tablename__}").fetchone()[0] is None
    m.upgrade(sqlite3.connect(':memory:'))  # no table: a no-op


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_migration_leaves_existing_cas_without_a_profile():
    m = importlib.import_module('migrations.107_ca_compliance_profile')
    schema = f"migtest_107_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        table = CA.__tablename__
        conn.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, descr TEXT)"))
        conn.execute(text(f"INSERT INTO {table} VALUES (1, 'old')"))
        m.upgrade(conn)
        m.upgrade(conn)
        assert conn.execute(text(f"SELECT compliance_profile FROM {table}")).scalar() is None
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
