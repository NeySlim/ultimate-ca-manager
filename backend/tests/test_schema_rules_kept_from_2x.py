"""Rules the 2.x migrations 101 to 134 put in place, checked on the schema the models create
(fresh install) and on the live application: they hold whether a database was upgraded or not."""
import base64
import hashlib
import hmac
import json
import os

import pytest
from sqlalchemy import Text, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from models import CA, SystemConfig, db
from models.acme_client_account import AcmeClientAccount
from models.acme_dns_update import AcmeProxyDnsChallenge
from models.acme_models import AcmeEabCredential, DnsProvider
from models.auth_certificate import AuthCertificate
from models.crl import CRLMetadata, CRLNumberCounter
from services.acme.acme_service import AcmeService
from services.webhook_service import WebhookEndpoint


# --- 124: names of DNS providers, ACME accounts and webhooks are unique -------------------------

TABLES = (
    (DnsProvider.__tablename__, 'name'),
    (AcmeClientAccount.__tablename__, 'label'),
    (WebhookEndpoint.__tablename__, 'name'),
)


def test_provider_account_and_webhook_names_are_unique():
    engine = create_engine('sqlite://')
    for model in (DnsProvider, AcmeClientAccount, WebhookEndpoint):
        model.__table__.create(engine)
    with engine.connect() as conn:
        for table, column in TABLES:
            indexes = {row[1] for row in conn.execute(text(f"PRAGMA index_list({table})"))}
            assert f'uq_{table}_{column}' in indexes, table
    rows = {
        DnsProvider: dict(name='same', provider_type='manual'),
        AcmeClientAccount: dict(label='same', directory_url='https://a.example/d',
                                email='a@example.com', account_key_algorithm='ES256',
                                is_default=False, proxy_enabled=False, order_poll_timeout_sec=1,
                                order_poll_interval_sec=1, http_timeout_sec=1),
        WebhookEndpoint: dict(name='same', url='https://a.example/h', auth_type='none'),
    }
    for model, values in rows.items():
        with engine.begin() as conn:
            conn.execute(model.__table__.insert().values(**values))
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(model.__table__.insert().values(**values))


# --- 130: an enrolment certificate's serial is unique per issuer ---------------------------------

AUTH_CERTS = AuthCertificate.__tablename__


def test_an_auth_certificate_serial_is_unique_per_issuer():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
    AuthCertificate.__table__.create(engine)
    with engine.connect() as conn:
        indexes = {r[1]: r[2] for r in conn.execute(text(f"PRAGMA index_list({AUTH_CERTS})"))}
    assert indexes[f'uq_{AUTH_CERTS}_issuer_serial'] == 1 and indexes[f'ix_{AUTH_CERTS}_cert_serial'] == 0
    insert = AuthCertificate.__table__.insert()
    values = dict(user_id=1, cert_serial='42', cert_subject='CN=c', enabled=True)
    with engine.begin() as conn:
        conn.execute(insert.values(cert_issuer='CN=A', **values))
        conn.execute(insert.values(cert_issuer='CN=B', **values))
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(insert.values(cert_issuer='CN=A', **values))


# --- 133: free-text audit columns are TEXT on PostgreSQL ------------------------------------------

AUDIT_TEXT_COLUMNS = {'username', 'resource_id', 'resource_name', 'user_agent'}


def test_the_app_schema_has_text_audit_columns_on_postgresql(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('SQLite does not enforce VARCHAR lengths')
        columns = {c['name']: c for c in inspect(db.engine).get_columns('audit_logs')}
    for name in AUDIT_TEXT_COLUMNS:
        assert isinstance(columns[name]['type'], Text), name


# --- 134: one CRL per (CA, number), one counter per issuer -------------------------------------

CRLS = CRLMetadata.__tablename__
COUNTERS = CRLNumberCounter.__tablename__


def test_a_crl_number_is_unique_per_ca_and_a_counter_per_issuer():
    engine = create_engine('sqlite://')
    for model in (CA, CRLMetadata, CRLNumberCounter):
        model.__table__.create(engine)
    with engine.connect() as conn:
        crl_indexes = {r[1]: r[2] for r in conn.execute(text(f"PRAGMA index_list({CRLS})"))}
        counter_indexes = {r[1]: r[2] for r in conn.execute(text(f"PRAGMA index_list({COUNTERS})"))}
    assert crl_indexes.get('uix_crl_ca_number') == 1
    assert counter_indexes.get('ix_crl_number_counters_issuer_key') == 1


# --- 111: the expiry index serves the DNS UPDATE listener's snapshot query ----------------------

CHALLENGES = AcmeProxyDnsChallenge.__tablename__


def _challenges():
    engine = create_engine('sqlite://')
    AcmeProxyDnsChallenge.__table__.create(engine)
    return engine


def _plan(conn):
    # The filter of the row snapshot of the listener (records.ActiveRecordCache._load).
    return ' '.join(str(r[-1]) for r in conn.execute(text(
        f"EXPLAIN QUERY PLAN SELECT id FROM {CHALLENGES} WHERE expires_at > :t"), {'t': '2026-01-01 00:00:00'}))


def test_the_expires_index_serves_the_snapshot_query():
    with _challenges().connect() as conn:
        plan = _plan(conn)
    assert plan.startswith('SEARCH') and 'idx_acme_proxy_dns_expires' in plan


def test_the_snapshot_query_scans_without_the_expires_index():
    with _challenges().connect() as conn:
        conn.execute(text('DROP INDEX idx_acme_proxy_dns_expires'))
        # The composite index starts with status: it can only be scanned, not searched.
        plan = _plan(conn)
    assert plan.startswith('SCAN') and 'SEARCH' not in plan


# --- 114: a deploy binding serves the chain UCM serves --------------------------------------------


def test_a_binding_defaults_to_the_served_chain(app):
    from models import Certificate, db
    from models.deploy import DeployBinding, DeployTarget
    with app.app_context():
        target = DeployTarget(name=f'm114-{os.urandom(3).hex()}', host='h', username='u', private_key='k')
        cert = Certificate(refid=os.urandom(8).hex(), descr='m114')
        db.session.add_all([target, cert])
        db.session.flush()
        binding = DeployBinding(target_id=target.id, certificate_id=cert.id)
        db.session.add(binding)
        db.session.flush()
        assert binding.chain_variant == 'auto' and binding.to_dict()['chain_variant'] == 'auto'
        db.session.rollback()


# --- 101: the legacy EAB blob registers nothing -----------------------------------------------------


def _eab(jwk, kid, key, url):
    protected = base64.urlsafe_b64encode(json.dumps(
        {'alg': 'HS256', 'kid': kid, 'url': url}).encode()).rstrip(b'=').decode()
    payload = base64.urlsafe_b64encode(json.dumps(jwk).encode()).rstrip(b'=').decode()
    sig = base64.urlsafe_b64encode(hmac.new(key, f'{protected}.{payload}'.encode(),
                                            hashlib.sha256).digest()).rstrip(b'=').decode()
    return {'protected': protected, 'payload': payload, 'signature': sig}


def test_a_key_left_in_the_blob_no_longer_registers(app):
    jwk = {'kty': 'EC', 'crv': 'P-256', 'x': 'f83OJ3D2xF1Bg8vub9tLe1gHMzV76e8Tus9uPHvRVEU',
           'y': 'x_FEzRu9m36HLN_tue659LNpXW6pCyStikYjKIWI5a0'}
    key = b'blob-only-secret'
    kid = 'blob-only-kid'
    with app.app_context():
        row = SystemConfig.query.filter_by(key='acme_eab_keys').first()
        if row is None:
            row = SystemConfig(key='acme_eab_keys')
            db.session.add(row)
        row.value = json.dumps({kid: base64.urlsafe_b64encode(key).rstrip(b'=').decode()})
        db.session.commit()
        try:
            assert AcmeEabCredential.query.filter_by(kid=kid).first() is None
            url = 'http://localhost/acme/new-account'
            valid, error = AcmeService(base_url='http://localhost').validate_eab(
                _eab(jwk, kid, key, url), jwk, url)
            assert valid is False
            assert error == 'Unknown external account'
        finally:
            db.session.delete(row)
            db.session.commit()
