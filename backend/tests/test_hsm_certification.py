"""Declared certification of an HSM provider (migration 108) and the eu-acm rule
``hsm_certifications`` that reads it. The certification is the operator's claim
about the hardware; UCM verifies nothing.
"""
import importlib
import json
import os
import sqlite3
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

import compliance_profiles
from models import CA, HsmKey, HsmProvider, db
from services import compliance_signer
from services.policy_service import PolicyEvaluationService, SystemPolicy
from tests.conftest import get_json

PG_URL = os.getenv('UCM_TEST_PG_URL')
JSON = 'application/json'
HSM = '/api/v2/hsm/providers'
VALUES = ('cc-eal4+', 'eucc-high', 'fips-140-3-l3', 'fips-140-2-l3', 'other')
RULE = {'cc-eal4+': None, 'eucc-high': None, 'fips-140-3-l3': '2030-12-31'}


def _enforce(rules, **kwargs):
    v, _, _ = PolicyEvaluationService.enforce_rules(
        [SystemPolicy('p', rules)], notify=False, **kwargs)
    return v


def _body(**extra):
    return json.dumps({'name': f'cert-{uuid.uuid4().hex[:8]}', 'type': 'pkcs11',
                       'config': {'module_path': '/opt/vendor/lib.so'}, **extra})


def _post(auth_client, **extra):
    return auth_client.post(HSM, data=_body(**extra), content_type=JSON)


def _put(auth_client, pid, **body):
    return auth_client.put(f'{HSM}/{pid}', data=json.dumps(body), content_type=JSON)


# ---- migration -----------------------------------------------------------------

def test_sqlite_migration_adds_the_column_and_leaves_providers_undeclared():
    m = importlib.import_module('migrations.108_hsm_provider_certification')
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE hsm_providers (id INTEGER PRIMARY KEY, name TEXT)')
    conn.execute("INSERT INTO hsm_providers VALUES (1, 'old')")
    m.upgrade(conn)
    m.upgrade(conn)
    assert conn.execute('SELECT certification FROM hsm_providers').fetchone()[0] is None
    m.upgrade(sqlite3.connect(':memory:'))  # no table: a no-op


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_migration_adds_the_column_and_leaves_providers_undeclared():
    m = importlib.import_module('migrations.108_hsm_provider_certification')
    schema = f"migtest_108_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        conn.execute(text(f'CREATE SCHEMA {schema}'))
        conn.execute(text(f'SET search_path TO {schema}'))
        conn.execute(text('CREATE TABLE hsm_providers (id INTEGER PRIMARY KEY, name TEXT)'))
        conn.execute(text("INSERT INTO hsm_providers VALUES (1, 'old')"))
        m.upgrade(conn)
        m.upgrade(conn)
        assert conn.execute(text('SELECT certification FROM hsm_providers')).scalar() is None
    finally:
        conn.rollback()
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        conn.commit()
        conn.close()
        engine.dispose()


# ---- API -----------------------------------------------------------------------

class TestProviderApi:

    @pytest.mark.parametrize('value', VALUES)
    def test_a_listed_certification_is_stored_and_returned(self, auth_client, value):
        r = _post(auth_client, certification=value)
        assert r.status_code == 201, r.data
        created = get_json(r)['data']
        assert created['certification'] == value
        shown = get_json(auth_client.get(f"{HSM}/{created['id']}"))['data']
        assert shown['certification'] == value
        listed = get_json(auth_client.get(HSM))['data']
        assert next(p for p in listed if p['id'] == created['id'])['certification'] == value

    def test_no_certification_means_not_declared(self, auth_client):
        for extra in ({}, {'certification': None}, {'certification': ''}, {'certification': '  '}):
            data = get_json(_post(auth_client, **extra))['data']
            assert data['certification'] is None

    @pytest.mark.parametrize('bad', ['fips-140-3', 'EAL4', 'CC-EAL4+ ', 7, ['other'], True])
    def test_an_unlisted_certification_is_refused_on_create(self, auth_client, bad):
        r = _post(auth_client, certification=bad)
        assert r.status_code == 400, r.data
        assert 'certification' in get_json(r)['message']

    def test_update_sets_keeps_and_clears(self, auth_client):
        pid = get_json(_post(auth_client))['data']['id']
        assert get_json(_put(auth_client, pid, certification='eucc-high'))['data']['certification'] == 'eucc-high'
        # absent and null leave it alone
        assert get_json(_put(auth_client, pid, name=f'renamed-{pid}'))['data']['certification'] == 'eucc-high'
        assert get_json(_put(auth_client, pid, certification=None))['data']['certification'] == 'eucc-high'
        assert get_json(_put(auth_client, pid, certification='fips-140-2-l3'))['data']['certification'] == 'fips-140-2-l3'
        # an empty string clears it
        assert get_json(_put(auth_client, pid, certification=''))['data']['certification'] is None

    def test_an_unlisted_certification_is_refused_on_update_and_changes_nothing(self, auth_client):
        pid = get_json(_post(auth_client, certification='other'))['data']['id']
        r = _put(auth_client, pid, name=f'must-not-rename-{pid}', certification='gold')
        assert r.status_code == 400, r.data
        shown = get_json(auth_client.get(f'{HSM}/{pid}'))['data']
        assert shown['certification'] == 'other' and not shown['name'].startswith('must-not')

    def test_a_certification_only_update_keeps_the_configuration(self, auth_client):
        pid = get_json(_post(auth_client))['data']['id']
        _put(auth_client, pid, certification='cc-eal4+')
        config = get_json(auth_client.get(f'{HSM}/{pid}'))['data']['config']
        assert config['module_path'] == '/opt/vendor/lib.so'


# ---- the signer carries its provider's certification ----------------------------

def _provider(certification=None, kind='pkcs11', module='/opt/vendor/lib.so'):
    row = HsmProvider(name=f'sig-{uuid.uuid4().hex[:8]}', type=kind,
                      config=json.dumps({'module_path': module}), certification=certification)
    db.session.add(row)
    db.session.flush()
    return row


def _hsm_key(provider):
    key = HsmKey(provider_id=provider.id, key_identifier=uuid.uuid4().hex, label='k',
                 algorithm='EC-P384', key_type='asymmetric', purpose='signing')
    db.session.add(key)
    db.session.flush()
    return key


class TestSignerCertification:

    def test_a_key_row_gives_the_certification_of_its_provider(self, app):
        with app.app_context():
            key = _hsm_key(_provider('eucc-high'))
            assert compliance_signer.certification_for_hsm_key(key) == 'eucc-high'
            assert compliance_signer.certification_for_hsm_key(_hsm_key(_provider())) is None
            assert compliance_signer.certification_for_hsm_key(None) is None
            assert compliance_signer.certification_for_hsm_key(SimpleNamespace(provider=None)) is None
            db.session.rollback()

    def test_an_unlisted_stored_value_is_not_a_declaration(self, app):
        with app.app_context():
            key = _hsm_key(_provider('platinum'))
            assert compliance_signer.certification_for_hsm_key(key) is None
            db.session.rollback()

    def test_a_ca_row_and_its_loaded_key_say_it(self, app, create_ca):
        ca = create_ca(cn='Certified CA')
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            assert compliance_signer.certification_of(row) is None  # a software key
            row.hsm_key_id = _hsm_key(_provider('fips-140-3-l3')).id
            db.session.flush()
            assert compliance_signer.certification_of(row) == 'fips-140-3-l3'
            loaded = SimpleNamespace(_hsm_key_id=row.hsm_key_id)
            assert compliance_signer.certification_of(loaded) == 'fips-140-3-l3'
            assert compliance_signer.certification_of(SimpleNamespace()) is None
            assert compliance_signer.certification_of(None) is None
            db.session.rollback()

    def test_the_policy_reads_it_from_the_signer(self, app, create_ca):
        ca = create_ca(cn='Signer read CA')
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            row.hsm_key_id = _hsm_key(_provider('fips-140-2-l3')).id
            db.session.flush()
            v = _enforce({'hsm_certifications': RULE}, signer=row)
            assert len(v) == 1 and 'fips-140-2-l3' in v[0]
            row.hsm_key.provider.certification = 'eucc-high'
            assert _enforce({'hsm_certifications': RULE}, signer=row) == []
            db.session.rollback()

    def test_a_ca_about_to_be_created_takes_the_certification_of_its_provider(self, app):
        from services.ca.ca_creation import _planned_certification
        with app.app_context():
            provider = _provider('cc-eal4+')
            key = _hsm_key(_provider('eucc-high'))
            assert _planned_certification(None, provider.id) == 'cc-eal4+'
            assert _planned_certification(key.id, None) == 'eucc-high'
            assert _planned_certification(key.id, provider.id) == 'eucc-high'
            assert _planned_certification(None, None) is None
            assert _planned_certification(987654, None) is None
            assert _planned_certification(None, 987654) is None
            db.session.rollback()


# ---- the rule -------------------------------------------------------------------

class TestRule:

    def test_a_listed_certification_passes(self):
        for value in ('cc-eal4+', 'eucc-high', 'fips-140-3-l3'):
            assert _enforce({'hsm_certifications': RULE}, signer_storage='hsm',
                            signer_certification=value) == []

    def test_an_undeclared_certification_is_refused_with_the_way_out(self):
        v = _enforce({'hsm_certifications': RULE}, signer_storage='hsm')
        assert len(v) == 1
        assert 'declare' in v[0] and 'cc-eal4+, eucc-high, fips-140-3-l3' in v[0]

    @pytest.mark.parametrize('value', ['fips-140-2-l3', 'other'])
    def test_a_certification_outside_the_list_is_refused(self, value):
        v = _enforce({'hsm_certifications': RULE}, signer_storage='hsm', signer_certification=value)
        assert len(v) == 1 and value in v[0] and 'accepted' in v[0]

    def test_a_certification_past_its_date_is_refused_on_the_day_after(self, monkeypatch):
        from services import policy_service
        rule = {'hsm_certifications': {'fips-140-3-l3': '2030-12-31'}}

        def at(day):
            monkeypatch.setattr(policy_service, 'utc_now',
                                lambda: SimpleNamespace(date=lambda: day))
            return _enforce(rule, signer_storage='hsm', signer_certification='fips-140-3-l3')

        assert at(date(2030, 12, 31)) == []
        v = at(date(2031, 1, 1))
        assert len(v) == 1 and '2030-12-31' in v[0] and 'fips-140-3-l3' in v[0]

    def test_a_certification_without_an_end_never_expires(self, monkeypatch):
        from services import policy_service
        monkeypatch.setattr(policy_service, 'utc_now',
                            lambda: SimpleNamespace(date=lambda: date(2099, 1, 1)))
        assert _enforce({'hsm_certifications': RULE}, signer_storage='hsm',
                        signer_certification='eucc-high') == []

    @pytest.mark.parametrize('storage', ['software', 'softhsm', None])
    def test_only_an_hsm_key_is_judged(self, storage):
        assert _enforce({'hsm_certifications': RULE}, signer_storage=storage) == []

    def test_an_empty_or_unreadable_rule_binds_nothing(self):
        for rule in ({}, None, 'cc-eal4+', ['cc-eal4+']):
            assert _enforce({'hsm_certifications': rule}, signer_storage='hsm') == []

    def test_a_stored_rule_with_a_bad_date_fails_closed(self):
        v = _enforce({'hsm_certifications': {'eucc-high': 'soon'}}, signer_storage='hsm',
                     signer_certification='eucc-high')
        assert len(v) == 1

    def test_the_advisory_form_is_a_notice(self):
        notices = []
        v, _, _ = PolicyEvaluationService.enforce_rules(
            [SystemPolicy('p', {'advisories': {'hsm_certifications': RULE}})],
            notify=False, notices=notices, signer_storage='hsm')
        assert v == [] and len(notices) == 1 and 'not recommended' in notices[0]

    def test_policies_intersect_with_the_earliest_date(self):
        a = SystemPolicy('a', {'hsm_certifications': {'eucc-high': None, 'fips-140-3-l3': '2030-12-31'}})
        b = SystemPolicy('b', {'hsm_certifications': {'fips-140-3-l3': '2029-06-30', 'cc-eal4+': None}})
        eff = PolicyEvaluationService.signature_rules_of([a, b])['hsm_certifications']
        assert eff == {'fips-140-3-l3': '2029-06-30'}
        none = PolicyEvaluationService.signature_rules_of([SystemPolicy('c', {})])
        assert none['hsm_certifications'] is None

    def test_eu_acm_carries_the_rule_and_the_others_do_not(self):
        assert compliance_profiles.PROFILES['eu-acm']['rules']['hsm_certifications'] == RULE
        for name in ('anssi', 'bsi'):
            assert 'hsm_certifications' not in compliance_profiles.PROFILES[name]['rules']

    def test_a_ca_under_eu_acm_is_judged_through_its_profile(self, app, create_ca):
        ca = create_ca(cn='Profile hsm cert CA')
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            row.compliance_profile = 'eu-acm'
            row.hsm_key_id = _hsm_key(_provider()).id
            db.session.flush()
            v, _, _ = PolicyEvaluationService.enforce_rules([], notify=False, ca_id=row.id, signer=row)
            assert len(v) == 1 and 'declare' in v[0]
            row.hsm_key.provider.certification = 'cc-eal4+'
            assert PolicyEvaluationService.enforce_rules(
                [], notify=False, ca_id=row.id, signer=row)[0] == []
            db.session.rollback()


# ---- policy form and effective view ------------------------------------------------

class TestValidationAndEffective:

    def _policy(self, auth_client, rules):
        return auth_client.post('/api/v2/policies', content_type=JSON, data=json.dumps({
            'name': f'hsmc-{uuid.uuid4().hex[:6]}', 'is_active': False, 'rules': rules}))

    def test_a_policy_accepts_the_rule(self, auth_client):
        r = self._policy(auth_client, {'hsm_certifications': RULE,
                                       'advisories': {'hsm_certifications': {'eucc-high': None}}})
        assert r.status_code in (200, 201), r.data
        stored = get_json(r)['data']['rules']
        assert stored['hsm_certifications'] == RULE
        assert stored['advisories']['hsm_certifications'] == {'eucc-high': None}

    @pytest.mark.parametrize('rules, fragment', [
        ({'hsm_certifications': ['eucc-high']}, 'must be an object'),
        ({'hsm_certifications': {'gold': None}}, 'Unknown certification'),
        ({'hsm_certifications': {'eucc-high': '31/12/2030'}}, 'YYYY-MM-DD'),
        ({'hsm_certifications': {'eucc-high': 2030}}, 'YYYY-MM-DD'),
        ({'hsm_certifications': {'eucc-high': '2030-02-30'}}, 'YYYY-MM-DD'),
        ({'advisories': {'hsm_certifications': 'x'}}, 'must be an object'),
    ])
    def test_a_policy_refuses_what_it_cannot_read(self, auth_client, rules, fragment):
        r = self._policy(auth_client, rules)
        assert r.status_code == 400, r.data
        assert fragment in get_json(r)['message']

    def test_effective_exposes_the_rule(self, app, auth_client, create_ca):
        ca = create_ca(cn='Effective hsm cert CA')
        with app.app_context():
            db.session.get(CA, ca['id']).compliance_profile = 'eu-acm'
            db.session.commit()
        data = get_json(auth_client.get(f"/api/v2/policies/effective?ca_id={ca['id']}"))['data']
        assert data['hsm_certifications'] == RULE
        plain = create_ca(cn='Effective plain hsm CA')
        data = get_json(auth_client.get(f"/api/v2/policies/effective?ca_id={plain['id']}"))['data']
        assert data['hsm_certifications'] is None


# ---- backup and restore ----------------------------------------------------------------

class TestBackup:

    def test_the_certification_travels_and_is_restored(self, app):
        from services.backup import manifest
        from tests.test_backup_hsm_and_key_pairs import PASSWORD, _only, _payload, _service
        assert 'certification' not in manifest.SECTIONS['hsm_providers'].exclude
        with app.app_context():
            row = _provider('eucc-high')
            row.name = 'zzhsm-cert-backup'
            db.session.commit()
            pid = row.id
            try:
                blob = _service().create_backup(PASSWORD, include=_only('hsm_providers'))
                item = next(i for i in _payload(blob)['hsm_providers'] if i['name'] == 'zzhsm-cert-backup')
                assert item['certification'] == 'eucc-high'

                row.certification = 'other'
                db.session.commit()
                results = {'hsm_providers': 0}
                _service()._restore_hsm_providers({'hsm_providers': [item]}, results)
                db.session.commit()
                assert db.session.get(HsmProvider, pid).certification == 'eucc-high'
            finally:
                db.session.rollback()
                HsmProvider.query.filter_by(id=pid).delete()
                db.session.commit()


# ---- CA creation -----------------------------------------------------------------------

class TestCaCreation:

    def _create(self, auth_client, provider_id, cn):
        return auth_client.post('/api/v2/cas', content_type=JSON, data=json.dumps({
            'type': 'root', 'commonName': cn, 'complianceProfile': 'eu-acm',
            'keyAlgo': 'EC', 'keySize': 384, 'validityYears': 5, 'hashAlgorithm': 'sha384',
            'hsmProviderId': provider_id, 'hsmKeyLabel': f'k-{cn}', 'hsmKeyAlgorithm': 'EC-P384'}))

    def test_a_new_hsm_ca_under_eu_acm_is_refused_before_a_key_is_generated(self, app, auth_client):
        with app.app_context():
            provider = _provider(None)
            db.session.commit()
            pid = provider.id
        try:
            r = self._create(auth_client, pid, 'undeclared-hsm-ca')
            assert r.status_code == 400, r.data
            assert 'declare the certification' in get_json(r)['message']
            with app.app_context():
                assert HsmKey.query.filter_by(provider_id=pid).count() == 0
        finally:
            with app.app_context():
                HsmProvider.query.filter_by(id=pid).delete()
                db.session.commit()

    def test_a_declared_but_unaccepted_certification_names_itself(self, app, auth_client):
        with app.app_context():
            provider = _provider('fips-140-2-l3')
            db.session.commit()
            pid = provider.id
        try:
            r = self._create(auth_client, pid, 'fips2-hsm-ca')
            assert r.status_code == 400, r.data
            assert 'fips-140-2-l3' in get_json(r)['message']
        finally:
            with app.app_context():
                HsmProvider.query.filter_by(id=pid).delete()
                db.session.commit()

    @pytest.mark.parametrize('kind', ['root', 'external'])
    def test_an_accepted_certification_reaches_the_key_generation(self, app, auth_client, monkeypatch, kind):
        from services.ca.ca_creation import CACreationMixin

        def reached(*args, **kwargs):
            raise RuntimeError('key generation reached')
        monkeypatch.setattr(CACreationMixin, '_resolve_signing_key', staticmethod(reached))
        with app.app_context():
            provider = _provider('eucc-high')
            db.session.commit()
            pid = provider.id
        try:
            body = {'type': kind, 'commonName': f'accepted-{kind}-hsm-ca', 'complianceProfile': 'eu-acm',
                    'keyAlgo': 'EC', 'keySize': 384, 'validityYears': 5, 'hashAlgorithm': 'sha384',
                    'hsmProviderId': pid, 'hsmKeyLabel': f'k-{kind}', 'hsmKeyAlgorithm': 'EC-P384'}
            r = auth_client.post('/api/v2/cas', content_type=JSON, data=json.dumps(body))
            assert r.status_code == 500 and 'certification' not in get_json(r)['message'], r.data
        finally:
            with app.app_context():
                HsmProvider.query.filter_by(id=pid).delete()
                db.session.commit()
