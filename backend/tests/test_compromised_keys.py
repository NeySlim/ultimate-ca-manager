"""Keys revoked as compromised are kept whatever CA issued them (migration 129): a certificate
of an external ACME CA, revoked as compromised then deleted, keeps its key refused."""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from models import Certificate, db
from models.compromised_key import CompromisedKeyRecord, remember_compromised_key
from services.acme import compromised_keys
from services.acme.compromised_keys import COMPROMISED_CSR
from services.cert_service import CertificateService
from tests.acme_fake_ca import key_pem
from tests.test_acme_renewal_in_place import Bench, _restore_config, _set_config
from utils.spki_digest import public_key_sha256


@pytest.fixture
def bench(app):
    with app.app_context():
        email = _set_config('acme.client.email', 'compromised@example.com')
        revoke = _set_config('acme.revoke_on_renewal', 'true')
        b = Bench(f'compromised-{uuid.uuid4().hex[:8]}.example.com')
        yield b
        b.cleanup()
        CompromisedKeyRecord.query.filter_by(
            public_key_sha256=public_key_sha256(b.key.public_key())).delete()
        db.session.commit()
        _restore_config('acme.revoke_on_renewal', revoke)
        _restore_config('acme.client.email', email)


def _csr(key, name):
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, name)]))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            .sign(key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM).decode())


def _record(bench):
    db.session.expire_all()
    return CompromisedKeyRecord.query.filter_by(
        public_key_sha256=public_key_sha256(bench.key.public_key())).one_or_none()


def _request(auth_client, bench):
    client = MagicMock()
    with patch('services.acme.acme_client_service.AcmeClientService.for_issuance', return_value=client):
        answer = auth_client.post('/api/v2/acme/client/request', json={
            'domains': [bench.name], 'email': 'x@example.com', 'challenge_type': 'http-01',
            'key_source': 'csr', 'csr_pem': _csr(bench.key, bench.name)})
    return answer, client


def test_an_external_ca_key_revoked_as_compromised_then_deleted_is_refused(app, auth_client, bench):
    assert db.session.get(Certificate, bench.cert_id).caref is None  # no CA of this installation
    answer = auth_client.post(f'/api/v2/certificates/{bench.cert_id}/revoke', json={'reason': 'keyCompromise'})
    assert answer.status_code == 200, answer.get_json()
    record = _record(bench)
    assert record is not None and record.source == 'acme_client' and record.cert_refid == bench.refid
    assert auth_client.delete(f'/api/v2/certificates/{bench.cert_id}').status_code == 204
    assert db.session.get(Certificate, bench.cert_id) is None and _record(bench) is not None
    answer, client = _request(auth_client, bench)
    assert answer.status_code == 409 and answer.get_json()['message'] == COMPROMISED_CSR
    client.create_order.assert_not_called()


def test_a_row_revoked_before_the_table_leaves_its_key_at_deletion(bench):
    row = db.session.get(Certificate, bench.cert_id)
    row.revoked, row.revoke_reason = True, 'key_compromise'
    db.session.commit()
    assert _record(bench) is None
    assert CertificateService.delete_certificate(bench.cert_id, username='admin')
    assert compromised_keys.key_revoked_as_compromised(bench.key.public_key())
    assert _record(bench).source == 'acme_client'


def test_a_renewal_in_place_keeps_the_compromised_key_it_overwrites(bench):
    row = db.session.get(Certificate, bench.cert_id)
    row.revoked, row.revoke_reason = True, 'keyCompromise'
    db.session.commit()
    assert bench.renew()[0]
    assert bench.client.revoke_certificate.call_args.kwargs == {'reason': 1}
    assert _record(bench).source == 'acme_client'
    assert compromised_keys.key_revoked_as_compromised(bench.key.public_key())


def test_a_renewal_keeps_the_compromised_key_before_the_ca_is_asked(bench):
    row = db.session.get(Certificate, bench.cert_id)
    row.revoked, row.revoke_reason = True, 'keyCompromise'
    db.session.commit()
    bench.client.create_order = MagicMock(return_value=(False, 'rate limited by the CA', None))
    try:
        bench.renew()
    except Exception:
        pass
    assert _record(bench).source == 'acme_client'


@pytest.mark.parametrize('caref, source, kept', [(True, 'acme_client', 'local'), (False, 'manual', 'external'),
                                                 (False, 'acme_client', 'acme_client'), (False, 'msca', 'msca')])
def test_the_source_says_who_issued_the_certificate(bench, create_ca, caref, source, kept):
    row = db.session.get(Certificate, bench.cert_id)
    row.source = source
    if caref:
        row.caref = create_ca()['refid']
    db.session.commit()
    CertificateService.revoke_certificate(bench.cert_id, reason='keyCompromise', username='admin')
    assert _record(bench).source == kept


def test_a_replacing_restore_never_prunes_the_compromised_keys():
    from services.backup.manifest import SECTIONS
    from services.backup.restore.replace import DEPENDENT_TABLES, MERGED_ONLY
    assert set(MERGED_ONLY) <= set(SECTIONS) and all(MERGED_ONLY.values())
    assert 'compromised_keys' in MERGED_ONLY and 'compromised_keys' not in DEPENDENT_TABLES


@pytest.mark.parametrize('reason', ['superseded', 'certificateHold', 'unspecified'])
def test_another_reason_records_nothing(bench, reason):
    CertificateService.revoke_certificate(bench.cert_id, reason=reason, username='admin')
    assert _record(bench) is None


def test_a_key_is_recorded_once(bench):
    digest = public_key_sha256(bench.key.public_key())
    CertificateService.revoke_certificate(bench.cert_id, reason='keyCompromise', username='admin')
    twin = CertificateService.import_certificate(
        descr=bench.name, cert_pem=bench.ca.issue(bench.key.public_key(), [bench.name]).split(
            '-----END CERTIFICATE-----\n', 1)[0] + '-----END CERTIFICATE-----\n',
        key_pem=key_pem(bench.key), username='system', source='acme_client')
    bench.extra_certs.append(twin.id)
    CertificateService.revoke_certificate(twin.id, reason='keyCompromise', username='admin')
    assert remember_compromised_key(digest, 'local')
    db.session.commit()
    assert CompromisedKeyRecord.query.filter_by(public_key_sha256=digest).count() == 1


def test_a_key_that_cannot_be_read_never_fails_the_revocation(bench):
    with patch('utils.spki_digest.x509.load_pem_x509_certificate', side_effect=RuntimeError('FIPS provider')):
        CertificateService.revoke_certificate(bench.cert_id, reason='keyCompromise', username='admin')
    db.session.expire_all()
    assert db.session.get(Certificate, bench.cert_id).revoked is True
    assert _record(bench) is None


def test_a_record_that_cannot_be_written_never_fails_the_revocation(bench):
    with patch.object(CompromisedKeyRecord, 'query', new_callable=lambda: property(
            lambda _self: (_ for _ in ()).throw(RuntimeError('no table')))):
        CertificateService.revoke_certificate(bench.cert_id, reason='keyCompromise', username='admin')
    db.session.expire_all()
    assert db.session.get(Certificate, bench.cert_id).revoked is True
    assert _record(bench) is None


def test_a_deleted_certificate_leaves_the_table_alone(bench):
    CertificateService.revoke_certificate(bench.cert_id, reason='keyCompromise', username='admin')
    before = CompromisedKeyRecord.query.count()
    assert CertificateService.delete_certificate(bench.cert_id, username='admin')
    assert CompromisedKeyRecord.query.count() == before


def test_a_backup_carries_the_compromised_keys(app, bench):
    from services.backup.export_generic import IdentityIndex, export_section
    from services.backup.restore.apply import apply_section
    from services.backup.restore.plan import RestorePlan
    CertificateService.revoke_certificate(bench.cert_id, reason='keyCompromise', username='admin')
    digest = public_key_sha256(bench.key.public_key())
    rows = [r for r in export_section('compromised_keys', IdentityIndex()) if r['public_key_sha256'] == digest]
    assert len(rows) == 1 and rows[0]['source'] == 'acme_client' and 'id' not in rows[0]
    CompromisedKeyRecord.query.filter_by(public_key_sha256=digest).delete()
    db.session.commit()
    apply_section('compromised_keys', rows, RestorePlan.build({'compromised_keys': rows}))
    db.session.commit()
    assert _record(bench).cert_refid == bench.refid


@pytest.mark.parametrize('reason', ['superseded', 'key_compromise', 'keyCompromise\n', '\tKEYCOMPROMISE '])
def test_the_fallback_scan_reads_only_rows_revoked_as_compromised(app, create_cert, monkeypatch, reason):
    """The scan behind the two tables is not O(revoked): other reasons stay in the database."""
    import base64
    from cryptography.hazmat.primitives.asymmetric import ec
    info = create_cert(cn=f'scan-{reason.strip()}.example.test')
    with app.app_context():
        row = db.session.get(Certificate, info['id'])
        row.revoked, row.revoke_reason = True, reason
        db.session.commit()
        held = x509.load_pem_x509_certificate(base64.b64decode(row.crt)).public_key()
        CompromisedKeyRecord.query.filter_by(public_key_sha256=public_key_sha256(held)).delete()
        db.session.commit()
        read = []
        real = compromised_keys.revoked_as_compromised
        monkeypatch.setattr(compromised_keys, 'revoked_as_compromised',
                            lambda r: read.append(r.id) or real(r))
        assert not compromised_keys.key_revoked_as_compromised(
            ec.generate_private_key(ec.SECP256R1()).public_key())
        compromised = reason != 'superseded'  # a legacy reason with stray whitespace still counts
        assert (info['id'] in read) is compromised
        # The row revoked as compromised still refuses its key
        assert compromised_keys.key_revoked_as_compromised(held) is compromised
