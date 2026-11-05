"""A replacing restore removes rows the same way on SQLite and on PostgreSQL.

What points at a removed row is cleared (regenerable tables), unlinked (data
no archive carries yet) or refused, never left as an orphan on SQLite while
PostgreSQL rolls the restore back. Removals run before the writes, so a name
or a slug the removed row held is free for the archived row.
"""
import json
import os
import uuid
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import exists, select

from models import db
from services.backup.errors import BackupSchemaError
from services.backup.manifest import SECTIONS
from services.backup.restore.replace import (
    CLOSED_WITH_TARGET, DEPENDENT_TABLES, _foreign_keys_into,
)
from services.backup.export_generic import load_model
from tests.test_backup_cross_installation import (
    PASSWORD, Keys, _authority, _installation, _leaf, _only, _service,
    _stored_certificate, _stored_key,
)
from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
from utils.datetime_utils import utc_now

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
ENGINES = [
    'sqlite',
    pytest.param('postgresql', marks=[
        pytest.mark.postgres,
        pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]),
]


@contextmanager
def _target(app, engine, directory, schema):
    keys = Keys(directory, f'replace-{engine}')
    if engine == 'sqlite':
        with _installation(app, f"sqlite:///{directory / 'target.db'}", keys), app.app_context():
            yield
        return
    with _a_schema_of_our_own(schema) as url:
        with _installation(app, url, keys, is_postgresql=True), app.app_context():
            yield
            db.session.rollback()


@pytest.fixture(params=ENGINES)
def target(request, app, tmp_path):
    """An installation of the test's own, on each engine."""
    schema = f'replace_deps_{uuid.uuid4().hex[:12]}'
    with _target(app, request.param, tmp_path, schema):
        yield request.param


# -- rows ---------------------------------------------------------------------

def _authority_row(refid):
    from models import CA
    key, certificate = _authority(refid)
    row = CA(refid=refid, descr=refid, url_slug=refid, crt=_stored_certificate(certificate),
             prv=_stored_key(key), subject=certificate.subject.rfc4514_string(),
             issuer=certificate.issuer.rfc4514_string(),
             serial_number=format(certificate.serial_number, 'x'),
             valid_from=certificate.not_valid_before, valid_to=certificate.not_valid_after)
    db.session.add(row)
    db.session.flush()
    return row, key, certificate


def _certificate_row(refid, issuer):
    from models import Certificate
    ca, ca_key, ca_certificate = issuer
    key, certificate = _leaf(f'{refid}.example.test', ca_key, ca_certificate)
    row = Certificate(refid=refid, descr=refid, caref=ca.refid,
                      crt=_stored_certificate(certificate), prv=_stored_key(key),
                      subject_cn=f'{refid}.example.test',
                      serial_number=format(certificate.serial_number, 'x'),
                      valid_from=certificate.not_valid_before,
                      valid_to=certificate.not_valid_after)
    db.session.add(row)
    db.session.flush()
    return row


def _user(username):
    from models import User
    row = User(username=username, email=f'{username}@example.test',
               password_hash='x' * 32, role='admin', active=True)
    db.session.add(row)
    db.session.flush()
    return row


def _snapshot(*sections):
    db.session.commit()
    if sections:
        return _service().create_backup(PASSWORD, include=_only(*sections))
    return _service().create_backup(PASSWORD)


def _orphans():
    """Every row whose foreign key names a row that does not exist.

    A closed recovery request keeps its certificate's number for the audit trail.
    """
    found = []
    seen = set(CLOSED_WITH_TARGET)
    for referred in list(db.metadata.tables):
        for dependent, column, named in _foreign_keys_into(referred):
            if (dependent.name, column.name) in seen:
                continue
            seen.add((dependent.name, column.name))
            query = select(column).where(
                column.isnot(None),
                ~exists().where(named == column))
            for row in db.session.execute(query).all():
                found.append(f'{dependent.name}.{column.name}={row[0]}')
    return found


def _restore(blob, mode='replace'):
    results = _service().restore_backup(blob, PASSWORD, mode=mode)
    db.session.expire_all()
    return results


# -- P2-5: what points at a removed row ---------------------------------------

def test_what_points_at_a_removed_row_is_cleared_or_unlinked_never_orphaned(target):
    from models import CA, Certificate, User
    from models.acme_models import AcmeClientOrder
    from models.crl import CRLMetadata
    from models.ocsp import OCSPResponse
    from models.policy import ApprovalRequest
    from models.sso import SSOProvider, SSOSession
    from models.user import UserSession

    _user('replace-admin')
    kept = _authority_row('replace-kept-ca')
    blob = _snapshot()

    # Added after the snapshot: the restore takes them away
    gone_ca, _key, _cert = _authority_row('replace-gone-ca')
    gone_cert = _certificate_row('replace-gone-cert', kept)
    gone_user = _user('replace-gone-user')
    provider = SSOProvider(name='replace-gone-sso', provider_type='oauth2')
    db.session.add(provider)
    db.session.flush()
    now = utc_now()
    db.session.add_all([
        CRLMetadata(ca_id=gone_ca.id, crl_number=1, this_update=now,
                    next_update=now + timedelta(days=1), crl_pem='x', crl_der=b'x'),
        OCSPResponse(ca_id=gone_ca.id, cert_serial='01', response_der=b'x', status='good',
                     this_update=now, next_update=now + timedelta(days=1)),
        UserSession(user_id=gone_user.id, session_id='replace-session'),
        SSOSession(user_id=gone_user.id, provider_id=provider.id, session_id='replace-sso'),
        AcmeClientOrder(domains='["replace.example.test"]', certificate_id=gone_cert.id),
        ApprovalRequest(request_type='renewal', certificate_id=gone_cert.id,
                        requester_id=gone_user.id),
    ])
    db.session.commit()

    results = _restore(blob)

    assert CA.query.filter_by(refid='replace-gone-ca').first() is None
    assert Certificate.query.filter_by(refid='replace-gone-cert').first() is None
    assert User.query.filter_by(username='replace-gone-user').first() is None
    assert CRLMetadata.query.count() == 0 and OCSPResponse.query.count() == 0
    assert UserSession.query.count() == 0 and SSOSession.query.count() == 0
    assert ApprovalRequest.query.count() == 0
    order = AcmeClientOrder.query.one()
    assert order.certificate_id is None
    assert results['unlinked_dependents'] == {'acme_client_orders.certificate_id': 1}
    assert {'crl_metadata', 'ocsp_responses', 'user_sessions', 'pro_sso_sessions',
            'approval_requests'} <= set(results['cleared_dependents'])
    assert _orphans() == []

    from services.backup.restore_report import with_restore_warnings
    message = with_restore_warnings('Restored', results)
    assert 'were deleted: ' in message and 'approval_requests (1)' in message
    assert 'acme_client_orders.certificate_id (1)' in message


def test_a_kept_row_that_names_a_removed_one_is_pointed_elsewhere_first(target):
    """The domain is kept and its provider is not: the provider waits for the writes."""
    from models.acme_models import AcmeDomain, DnsProvider

    _user('replace-admin')
    archived = DnsProvider(name='replace-archived-dns', provider_type='manual')
    db.session.add(archived)
    db.session.flush()
    domain = AcmeDomain(domain='replace.example.test', dns_provider_id=archived.id)
    db.session.add(domain)
    blob = _snapshot()

    other = DnsProvider(name='replace-later-dns', provider_type='manual')
    db.session.add(other)
    db.session.flush()
    domain.dns_provider_id = other.id
    db.session.flush()
    db.session.delete(archived)
    db.session.commit()

    results = _restore(blob)

    assert [p.name for p in DnsProvider.query.all()] == ['replace-archived-dns']
    restored = AcmeDomain.query.filter_by(domain='replace.example.test').one()
    assert restored.dns_provider.name == 'replace-archived-dns'
    assert results['removed'].get('dns_providers') == 1
    assert _orphans() == []


def test_a_table_the_archive_does_not_carry_is_never_orphaned(target):
    """An archive of the authorities alone cannot remove one that certificates use."""
    from models import CA, Certificate

    _user('replace-admin')
    _authority_row('replace-kept-ca')
    blob = _snapshot('certificate_authorities')

    gone = _authority_row('replace-gone-ca')
    _certificate_row('replace-cert-of-gone', gone)
    db.session.commit()

    with pytest.raises(BackupSchemaError) as refused:
        _restore(blob)
    db.session.rollback()
    message = str(refused.value)
    assert 'replace-gone-ca' in message and "'certificates'" in message
    assert 'Nothing has been changed' in message
    assert CA.query.filter_by(refid='replace-gone-ca').first() is not None
    assert Certificate.query.filter_by(refid='replace-cert-of-gone').first() is not None


# -- P2-6: removals before writes ---------------------------------------------

def _scep_profile(name, slug, ca_refid):
    from models.scep import ScepProfile
    row = ScepProfile(name=name, url_slug=slug, ca_refid=ca_refid, enabled=True)
    db.session.add(row)
    db.session.flush()
    return row


def test_a_slug_held_by_a_removed_row_is_free_for_the_archived_one(target):
    from models.scep import ScepProfile

    _user('replace-admin')
    ca, _key, _cert = _authority_row('replace-scep-ca')
    profile = _scep_profile('replace-scep-a', 'replace-slug', ca.refid)
    blob = _snapshot()

    profile.name = 'replace-scep-renamed'
    db.session.commit()

    _restore(blob)

    assert [(p.name, p.url_slug) for p in ScepProfile.query.all()] == [
        ('replace-scep-a', 'replace-slug')]


def test_a_conflict_left_after_the_removals_names_the_row(target):
    """Merging keeps the row here: the database refuses, and the answer says where."""
    from models.scep import ScepProfile

    _user('replace-admin')
    ca, _key, _cert = _authority_row('replace-scep-ca')
    profile = _scep_profile('replace-scep-a', 'replace-slug', ca.refid)
    blob = _snapshot()

    profile.name = 'replace-scep-renamed'
    db.session.commit()

    with pytest.raises(BackupSchemaError) as refused:
        _restore(blob, mode='merge')
    db.session.rollback()
    message = str(refused.value)
    assert "table 'scep_profiles'" in message
    assert 'replace-scep-a' in message
    assert 'Nothing has been changed' in message
    assert [p.name for p in ScepProfile.query.all()] == ['replace-scep-renamed']


def test_a_homonym_replacing_the_row_here_keeps_its_name(target):
    """Lot 3 suffixes a homonym; a replacing restore that removes the row here does not."""
    from models.acme_models import DnsProvider

    _user('replace-admin')
    archived = DnsProvider(name='replace-dns', provider_type='cloudflare')
    archived.credentials = json.dumps({'api_token': 'archived'})
    db.session.add(archived)
    blob = _snapshot()

    db.session.delete(archived)
    db.session.flush()
    here = DnsProvider(name='replace-dns', provider_type='route53')
    here.credentials = json.dumps({'api_token': 'here'})
    db.session.add(here)
    db.session.commit()

    results = _restore(blob)

    rows = DnsProvider.query.all()
    assert [(p.name, p.provider_type, json.loads(p.credentials)['api_token'])
            for p in rows] == [('replace-dns', 'cloudflare', 'archived')]
    assert results['renamed'] == []
    assert _orphans() == []


def test_a_homonym_a_kept_domain_still_needs_is_suffixed(target):
    """The domain here points at the homonym until the writes: its name is not handed over."""
    from models.acme_models import AcmeDomain, DnsProvider

    _user('replace-admin')
    archived = DnsProvider(name='replace-dns', provider_type='cloudflare')
    db.session.add(archived)
    db.session.flush()
    db.session.add(AcmeDomain(domain='replace.example.test', dns_provider_id=archived.id))
    blob = _snapshot()

    here = DnsProvider(name='replace-dns-here', provider_type='route53')
    db.session.add(here)
    db.session.flush()
    AcmeDomain.query.one().dns_provider_id = here.id
    db.session.flush()
    db.session.delete(archived)
    db.session.flush()
    here.name = 'replace-dns'
    db.session.commit()

    results = _restore(blob)

    assert [(p.name, p.provider_type) for p in DnsProvider.query.all()] == [
        ('replace-dns (2)', 'cloudflare')]
    assert AcmeDomain.query.one().dns_provider.provider_type == 'cloudflare'
    assert [entry['to'] for entry in results['renamed']] == ['replace-dns (2)']
    assert _orphans() == []


def test_a_homonym_account_a_kept_tsig_key_still_needs_is_suffixed(target):
    from models.acme_client_account import AcmeClientAccount
    from models.acme_dns_update import AcmeDnsUpdateKey

    _user('replace-admin')
    archived = AcmeClientAccount(label='replace-acct', email='a@example.test',
                                 directory_url='https://archived.example.test/directory')
    db.session.add(archived)
    db.session.flush()
    key = AcmeDnsUpdateKey(acme_client_account_id=archived.id, name='replace-key.example.test.')
    key.secret = 'c2VjcmV0LXNlY3JldC1zZWNyZXQtc2VjcmV0'
    db.session.add(key)
    blob = _snapshot()

    here = AcmeClientAccount(label='replace-acct-here', email='h@example.test',
                             directory_url='https://here.example.test/directory')
    db.session.add(here)
    db.session.flush()
    key.acme_client_account_id = here.id
    db.session.flush()
    db.session.delete(archived)
    db.session.flush()
    here.label = 'replace-acct'
    db.session.commit()

    results = _restore(blob)

    assert [(a.label, a.directory_url) for a in AcmeClientAccount.query.all()] == [
        ('replace-acct (2)', 'https://archived.example.test/directory')]
    kept = AcmeDnsUpdateKey.query.one()
    assert db.session.get(AcmeClientAccount, kept.acme_client_account_id).label == 'replace-acct (2)'
    assert [entry['to'] for entry in results['renamed']] == ['replace-acct (2)']
    assert _orphans() == []


def test_merging_the_same_homonym_still_suffixes_it(target):
    from models.acme_models import DnsProvider

    _user('replace-admin')
    archived = DnsProvider(name='replace-dns', provider_type='cloudflare')
    db.session.add(archived)
    blob = _snapshot()

    db.session.delete(archived)
    db.session.flush()
    db.session.add(DnsProvider(name='replace-dns', provider_type='route53'))
    db.session.commit()

    results = _restore(blob, mode='merge')

    assert sorted(p.name for p in DnsProvider.query.all()) == ['replace-dns', 'replace-dns (2)']
    assert [entry['to'] for entry in results['renamed']] == ['replace-dns (2)']


# -- the declaration ----------------------------------------------------------

def test_every_table_pointing_into_an_archive_is_decided(app):
    """A table no archive prunes, holding a key into one it does, must be declared."""
    with app.app_context():
        pruned_always = {load_model(section).__table__.name
                         for section in SECTIONS.values() if not section.optional}
        undecided = set()
        for section in SECTIONS.values():
            for dependent, column, _named in _foreign_keys_into(load_model(section).__table__.name):
                if dependent.name not in pruned_always and dependent.name not in DEPENDENT_TABLES:
                    undecided.add(f'{dependent.name}.{column.name}')
        assert not undecided, sorted(undecided)
        assert set(DEPENDENT_TABLES) <= set(db.metadata.tables)


def test_a_row_still_needed_after_the_writes_is_refused_not_orphaned(target):
    from models.api_key import APIKey
    from services.backup.restore.replace import Replacement, remove_after_writes

    user = _user('replace-still-needed')
    db.session.add(APIKey(user_id=user.id, key_hash='replace-hash', name='k', permissions='[]'))
    db.session.commit()
    waiting = Replacement(order=['users'], doomed={'users': {user.id}},
                          pruned={'users', 'api_keys'}, deferred={'users': {user.id}})

    with pytest.raises(BackupSchemaError) as refused:
        remove_after_writes(waiting)
    db.session.rollback()
    assert 'api_keys key_hash=replace-hash' in str(refused.value)
    assert 'users username=replace-still-needed' in str(refused.value)
    assert db.session.get(type(user), user.id) is not None


# -- integer links without a foreign key --------------------------------------

def test_a_reused_certificate_number_reaches_no_request(target):
    """SQLite hands a removed certificate's number to the next one inserted."""
    from api.v2.key_recovery import _requested_certificate
    from models import Certificate
    from models.key_recovery import KeyRecoveryRequest

    _user('replace-admin')
    issuer = _authority_row('replace-kr-ca')
    first = _certificate_row('replace-kr-a', issuer)
    second = _certificate_row('replace-kr-b', issuer)
    blob = _snapshot()

    number = second.id
    db.session.delete(second)
    db.session.flush()
    other = _certificate_row('replace-kr-x', issuer)
    db.session.add(KeyRecoveryRequest(cert_id=other.id, cert_refid=other.refid,
                                      reason='offboarding', status='approved',
                                      requested_by='replace-admin', requested_at=utc_now()))
    db.session.commit()
    if target == 'sqlite':
        assert other.id == number

    results = _restore(blob)

    request = KeyRecoveryRequest.query.one()
    if target == 'sqlite':
        assert db.session.get(Certificate, request.cert_id).refid == 'replace-kr-b'
    assert request.status == 'cancelled'
    assert results['closed_dependents'] == {'key_recovery_requests': 1}
    from services.backup.restore_report import with_restore_warnings
    assert 'were cancelled: key_recovery_requests (1)' in with_restore_warnings('Restored', results)
    assert _requested_certificate(request) is None
    assert _orphans() == []


def test_a_request_on_a_certificate_gone_before_the_export_does_not_hold_the_restore(target):
    """Its number now names a row the restore removes: the request keeps its archived state."""
    from models.key_recovery import KeyRecoveryRequest

    _user('replace-admin')
    issuer = _authority_row('replace-gone-ca')
    gone = _certificate_row('replace-gone-early', issuer)
    db.session.add(KeyRecoveryRequest(cert_id=gone.id, cert_refid=gone.refid,
                                      reason='offboarding', status='rejected',
                                      requested_by='replace-admin', requested_at=utc_now()))
    db.session.flush()
    number = gone.id
    db.session.delete(gone)
    blob = _snapshot('users', 'certificate_authorities', 'certificates', 'key_recovery_requests')

    other = _certificate_row('replace-gone-x', issuer)
    db.session.commit()
    if target == 'sqlite':
        assert other.id == number

    _restore(blob)

    from models import Certificate
    assert Certificate.query.filter_by(refid='replace-gone-x').first() is None
    assert KeyRecoveryRequest.query.one().status == 'rejected'


def test_a_hybrid_partner_is_found_by_refid_not_by_number(target):
    from models import Certificate

    _user('replace-admin')
    issuer = _authority_row('replace-pair-ca')
    classical = _certificate_row('replace-pair-a', issuer)
    pq = _certificate_row('replace-pair-b', issuer)
    classical.related_certificate_id, pq.related_certificate_id = pq.id, classical.id
    blob = _snapshot()

    db.session.delete(pq)
    db.session.flush()
    _certificate_row('replace-pair-x', issuer)
    db.session.commit()

    _restore(blob, mode='merge')

    restored = Certificate.query.filter_by(refid='replace-pair-a').one()
    partner = db.session.get(Certificate, restored.related_certificate_id)
    assert partner.refid == 'replace-pair-b'
    assert db.session.get(Certificate, partner.related_certificate_id).refid == 'replace-pair-a'


def test_a_revocation_record_outlives_its_removed_certificate(target):
    from models.revoked_serial import RevokedSerial

    _user('replace-admin')
    issuer = _authority_row('replace-rs-ca')
    blob = _snapshot('users', 'certificate_authorities', 'certificates')

    gone = _certificate_row('replace-rs-gone', issuer)
    db.session.add(RevokedSerial(caref=issuer[0].refid, serial_number=gone.serial_number,
                                 valid_to=gone.valid_to, certificate_id=gone.id))
    db.session.commit()

    results = _restore(blob)

    record = RevokedSerial.query.one()
    assert record.certificate_id is None
    assert results['unlinked_dependents'] == {'revoked_serials.certificate_id': 1}

