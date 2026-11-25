"""A global setting that names a CA, by number or by refid, never outlives it.

SQLite gives the number of a deleted CA to the next one created, so a setting
left behind would choose an authority nobody chose; one naming a refid would
dangle. Deleting the CA is refused while such a setting names it.
"""
import json
import re

import pytest

from models import CA, SystemConfig, db
from services.backup.manifest import CA_REFID_SETTINGS, SETTING_REFERENCES
from services.deletion_blockers import CA_SETTING_WORDING, ca_deletion_blockers, first_blocker

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

CA_SECTION = 'certificate_authorities'


def _fixed_key(pattern):
    """The one key a declaration without wildcards matches."""
    key = re.sub(r'\\(.)', r'\1', pattern)
    assert re.fullmatch(pattern, key), f'{pattern} is not a fixed key: give the test a sample key'
    return key


NUMBERED = [_fixed_key(r.pattern) for r in SETTING_REFERENCES if r.value == CA_SECTION]
BY_REFID = [_fixed_key(r.pattern) for r in CA_REFID_SETTINGS if r.value == CA_SECTION]
# 'padded' is a number the readers' int() still parses to the CA ('05', ' +5 ')
CASES = ([(key, form) for key in NUMBERED for form in ('id', 'padded')]
         + [(key, 'refid') for key in NUMBERED + BY_REFID])
_FORMS = {'id': lambda ca: str(ca.id), 'padded': lambda ca: f' +0{ca.id} ', 'refid': lambda ca: ca.refid}


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    before = None if row is None else row.value
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()
    return before


def _put_back(key, before):
    row = SystemConfig.query.filter_by(key=key).first()
    if before is None:
        if row is not None:
            db.session.delete(row)
    else:
        row.value = before
    db.session.commit()


def test_every_setting_the_manifest_declares_has_its_wording():
    """A new declaration naming a CA is blocked by the manifest itself; its message must say where to change it."""
    assert set(NUMBERED) >= {'scep_ca_id', 'acme.issuing_ca_id'}
    assert set(NUMBERED + BY_REFID) == set(CA_SETTING_WORDING)


def test_the_settings_cross_repair_moves_are_all_declared():
    from services.ca.cross_repair import _SETTINGS
    assert set(_SETTINGS) <= set(NUMBERED + BY_REFID)


@pytest.mark.parametrize('key,form', CASES)
def test_a_ca_named_by_a_setting_is_not_deleted(app, auth_client, create_ca, key, form):
    ca = create_ca(cn=f'Named by {key} {form}')
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        before = _set(key, _FORMS[form](row))
    try:
        r = auth_client.delete(f"/api/v2/cas/{ca['id']}")
        assert r.status_code == 409, r.data
        label, screen = CA_SETTING_WORDING[key]
        assert r.get_json()['message'] == (
            f'Cannot delete CA: it is {label}. Clear it or choose another one in {screen} first.')
        with app.app_context():
            assert db.session.get(CA, ca['id']) is not None
    finally:
        with app.app_context():
            _put_back(key, before)
    assert auth_client.delete(f"/api/v2/cas/{ca['id']}").status_code == 204


def test_the_scep_message_is_unchanged(app, create_ca):
    ca = create_ca(cn='Default SCEP wording')
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        before = _set('scep_ca_id', str(row.id))
        try:
            blocker = first_blocker(ca_deletion_blockers(row))
            assert blocker.message == ('Cannot delete CA: it is the default SCEP CA. '
                                       'Clear it or choose another one in the SCEP settings first.')
            assert blocker.brief == 'default SCEP CA'
        finally:
            _put_back('scep_ca_id', before)


def test_another_ca_named_by_the_setting_does_not_block(app, auth_client, create_ca):
    other = create_ca(cn='The ACME issuing CA')
    ca = create_ca(cn='Not the ACME issuing CA')
    with app.app_context():
        before = _set('acme.issuing_ca_id', db.session.get(CA, other['id']).refid)
    try:
        assert auth_client.delete(f"/api/v2/cas/{ca['id']}").status_code == 204
    finally:
        with app.app_context():
            _put_back('acme.issuing_ca_id', before)


def test_bulk_refuses_the_named_ca_and_deletes_the_others(app, auth_client, create_ca):
    named = create_ca(cn='Bulk named by the ACME setting')
    free = create_ca(cn='Bulk free CA')
    with app.app_context():
        before = _set('acme.issuing_ca_id', str(named['id']))
    try:
        r = auth_client.post('/api/v2/cas/bulk/delete', json={'ids': [named['id'], free['id']]})
        assert r.status_code == 200, r.data
        data = r.get_json()['data']
        assert data['success'] == [free['id']]
        assert data['failed'] == [{'id': named['id'], 'error': 'default ACME issuing CA'}]
        with app.app_context():
            assert db.session.get(CA, named['id']) is not None
    finally:
        with app.app_context():
            _put_back('acme.issuing_ca_id', before)


def test_an_est_label_naming_the_ca_blocks(app, auth_client, create_ca):
    ca = create_ca(cn='Reached through an EST label')
    with app.app_context():
        refid = db.session.get(CA, ca['id']).refid
        before = _set('est_labels', json.dumps({'other': 'not-this-ca', 'devices': refid}))
    try:
        r = auth_client.delete(f"/api/v2/cas/{ca['id']}")
        assert r.status_code == 409, r.data
        assert r.get_json()['message'] == (
            'Cannot delete CA: EST label(s) devices route to it. '
            'Remove them or point them at another CA in the EST settings first.')
    finally:
        with app.app_context():
            _put_back('est_labels', before)
    assert auth_client.delete(f"/api/v2/cas/{ca['id']}").status_code == 204


def test_unreadable_est_labels_do_not_block(app, auth_client, create_ca):
    ca = create_ca(cn='EST labels unreadable')
    with app.app_context():
        before = _set('est_labels', '{not json')
    try:
        assert auth_client.delete(f"/api/v2/cas/{ca['id']}").status_code == 204
    finally:
        with app.app_context():
            _put_back('est_labels', before)


def test_the_product_schema_gives_a_deleted_ca_number_again():
    """SQLite reuses the highest number of a table without AUTOINCREMENT: the CA table is one.
    The session database of the tests turns AUTOINCREMENT on, so the next test sets the number."""
    from sqlalchemy.dialects import sqlite
    from sqlalchemy.schema import CreateTable
    assert 'AUTOINCREMENT' not in str(CreateTable(CA.__table__).compile(dialect=sqlite.dialect())).upper()


def test_the_next_ca_never_becomes_the_acme_issuing_ca(app, auth_client, create_ca):
    """The number taking-over is SQLite's; the CA holding it is written with that number here."""
    import uuid
    from services.acme.mixins.issuance import IssuanceMixin
    chosen = create_ca(cn='ACME issuing after the change')
    gone = create_ca(cn='ACME issuing CA to delete')
    with app.app_context():
        before = _set('acme.issuing_ca_id', str(gone['id']))
    try:
        assert auth_client.delete(f"/api/v2/cas/{gone['id']}").status_code == 409
        with app.app_context():
            _set('acme.issuing_ca_id', db.session.get(CA, chosen['id']).refid)
        assert auth_client.delete(f"/api/v2/cas/{gone['id']}").status_code == 204
        with app.app_context():
            source = db.session.get(CA, chosen['id'])
            copied = {c.name: getattr(source, c.name) for c in CA.__table__.columns
                      if c.name not in ('id', 'refid', 'url_slug', 'hsm_key_id', 'descr')}
            db.session.add(CA(id=gone['id'], refid=str(uuid.uuid4()), descr='Created after the deletion',
                              **copied))
            db.session.commit()
            taker = db.session.get(CA, gone['id'])
            assert taker is not None and taker.has_private_key, 'no CA holds the number: nothing is proven'
            resolved = IssuanceMixin()._resolve_ca_for_domains([])
            assert resolved == source.refid
            assert resolved != taker.refid
    finally:
        with app.app_context():
            _put_back('acme.issuing_ca_id', before)


@pytest.mark.parametrize('dangling', ['no-such-ca-refid', '987654321'])
def test_an_issuing_ca_already_gone_issues_nothing(app, monkeypatch, create_ca, dangling):
    """A database where the setting names a CA deleted before the blocker: no other CA signs."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from services.acme.acme_service import AcmeService
    from tests.test_acme_profile_template import TestFinalizeWithBoundTemplate
    from utils import caa_checker

    create_ca(cn='A CA able to sign')
    with app.app_context():
        before = _set('acme.issuing_ca_id', dangling)
        try:
            order = TestFinalizeWithBoundTemplate._order(None)
            service = AcmeService(base_url='http://localhost')
            monkeypatch.setattr(caa_checker, 'check_caa_for_domains', lambda *a, **k: (True, 'allowed'))
            key = ec.generate_private_key(ec.SECP256R1())
            csr = (x509.CertificateSigningRequestBuilder()
                   .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'web.example.com')]))
                   .add_extension(x509.SubjectAlternativeName([x509.DNSName('web.example.com')]), False)
                   .sign(key, hashes.SHA256()))
            service.begin_order_processing(order)
            service._finalizing_order_id = order.order_id
            success, error = service.finalize_order(
                order.order_id, csr.public_bytes(serialization.Encoding.PEM).decode())
            service._finalizing_order_id = None
            assert not success
            assert 'ACME settings' in error, error
            db.session.refresh(order)
            assert order.certificate_id is None
        finally:
            _put_back('acme.issuing_ca_id', before)


def test_a_padded_number_sent_to_the_acme_settings_still_blocks(app, auth_client, create_ca):
    """The settings route stores '05' as sent and issuance reads it as CA 5."""
    from services.acme.mixins.issuance import IssuanceMixin
    ca = create_ca(cn='ACME issuing CA by padded number')
    with app.app_context():
        before = _set('acme.issuing_ca_id', '')
    try:
        r = auth_client.patch('/api/v2/acme/settings', json={'issuing_ca_id': f"0{ca['id']}"})
        assert r.status_code == 200, r.data
        with app.app_context():
            assert IssuanceMixin()._resolve_ca_for_domains([]) == db.session.get(CA, ca['id']).refid
        r = auth_client.delete(f"/api/v2/cas/{ca['id']}")
        assert r.status_code == 409, r.data
    finally:
        with app.app_context():
            _put_back('acme.issuing_ca_id', before)
    assert auth_client.delete(f"/api/v2/cas/{ca['id']}").status_code == 204


def test_the_check_reads_only_the_declared_settings(app, create_ca):
    """Deleting a CA does not load every setting row: the declared keys are looked up by name."""
    from sqlalchemy import event
    ca = create_ca(cn='Checked without a scan')
    with app.app_context():
        extra = [SystemConfig(key=f'unrelated.setting.{n}', value=str(n)) for n in range(40)]
        db.session.add_all(extra)
        db.session.commit()
        db.session.expunge_all()
        row = db.session.get(CA, ca['id'])
        loaded = []
        listener = lambda target, context: loaded.append(target.key)  # noqa: E731
        event.listen(SystemConfig, 'load', listener)
        try:
            list(ca_deletion_blockers(row))
        finally:
            event.remove(SystemConfig, 'load', listener)
            SystemConfig.query.filter(SystemConfig.key.like('unrelated.setting.%')).delete(synchronize_session=False)
            db.session.commit()
        assert not [key for key in loaded if key.startswith('unrelated.setting.')]


@pytest.mark.parametrize('key', ['scep_ca_id', 'acme.issuing_ca_id', 'est_ca_refid', 'tsa_ca_refid',
                                 'mtls_trusted_ca_id'])
def test_each_ca_setting_blocks_by_its_name(app, auth_client, create_ca, key):
    """Listed by hand, not from the manifest: a declaration dropped there still fails here."""
    ca = create_ca(cn=f'Named by {key}')
    with app.app_context():
        before = _set(key, db.session.get(CA, ca['id']).refid)
    try:
        r = auth_client.delete(f"/api/v2/cas/{ca['id']}")
        assert r.status_code == 409, r.data
        assert CA_SETTING_WORDING[key][0] in r.get_json()['message']
    finally:
        with app.app_context():
            _put_back(key, before)
    assert auth_client.delete(f"/api/v2/cas/{ca['id']}").status_code == 204


def test_a_number_left_by_an_older_version_names_the_ca_now_holding_it(app, auth_client, create_ca):
    """State left before the blocker: the setting names a free number, a CA created later takes it.
    Nothing tells that CA from one the administrator chose: it is the issuing CA, and is not deleted."""
    import uuid
    from services.acme.mixins.issuance import IssuanceMixin
    source = create_ca(cn='Source of the copied key')
    with app.app_context():
        free = (db.session.query(db.func.max(CA.id)).scalar() or 0) + 1000
        before = _set('acme.issuing_ca_id', str(free))
    try:
        with app.app_context():
            row = db.session.get(CA, source['id'])
            copied = {c.name: getattr(row, c.name) for c in CA.__table__.columns
                      if c.name not in ('id', 'refid', 'url_slug', 'hsm_key_id', 'descr')}
            db.session.add(CA(id=free, refid=str(uuid.uuid4()), descr='Took the free number', **copied))
            db.session.commit()
            taker = db.session.get(CA, free)
            assert IssuanceMixin()._resolve_ca_for_domains([]) == taker.refid
        assert auth_client.delete(f'/api/v2/cas/{free}').status_code == 409
    finally:
        with app.app_context():
            _put_back('acme.issuing_ca_id', before)
    assert auth_client.delete(f'/api/v2/cas/{free}').status_code == 204
