"""In-place renewal routine (services.cert.renewal): what a renewal changes,
what it records, what it refuses before writing anything, and the effects
it runs once committed."""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed25519, ed448, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID

import fips_mode
from models import CA, Certificate, RevokedSerial, SystemConfig, db
from models.policy import ApprovalRequest, CertificatePolicy
from services.cert import renewal
from services.cert.renewal import RenewalError, renew_certificate_in_place
from utils import key_algorithms
from utils.key_codec import load_pem_bytes, store_pem_bytes
from utils.datetime_utils import utc_now
from utils.validity import MAX_VALIDITY_DAYS


# --------------------------------------------------------------- helpers

def _now():
    return datetime.now(timezone.utc)


def _ca_parts(app, ca_id):
    from services.hsm.ca_key_loader import get_ca_signing_key
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        return ca.refid, x509.load_pem_x509_certificate(base64.b64decode(ca.crt)), get_ca_signing_key(ca)


def _install_ca_cert(app, ca_id, *, not_before, not_after, extra=()):
    """Replace the CA's certificate by a self-signed one on the same key."""
    _, old, key = _ca_parts(app, ca_id)
    builder = (
        x509.CertificateBuilder().subject_name(old.subject).issuer_name(old.subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(not_before).not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
    )
    for ext in extra:
        builder = builder.add_extension(ext, critical=True)
    cert = builder.sign(key, hashes.SHA256())
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        ca.crt = base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()
        db.session.commit()
    return cert


def _pkcs8(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _leaf(app, ca_id, cn, *, key=None, days=30, issued_days_ago=1, sans=None, extra=(),
          with_key=True, source='manual', digest=hashes.SHA256(), lifetime=None):
    """A leaf signed by the CA's key, stored with a decimal serial."""
    refid, ca_cert, ca_key = _ca_parts(app, ca_id)
    key = key or rsa.generate_private_key(65537, 2048)
    start = _now() - timedelta(days=issued_days_ago)
    end = start + lifetime if lifetime is not None else _now() + timedelta(days=days)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .issuer_name(ca_cert.subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start).not_valid_after(end)
        .add_extension(x509.SubjectAlternativeName(sans or [x509.DNSName(cn)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    )
    for ext, critical in extra:
        builder = builder.add_extension(ext, critical)
    cert = builder.sign(ca_key, digest)
    with app.app_context():
        row = Certificate(
            refid=str(uuid.uuid4()), descr=cn, caref=refid,
            crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
            prv=store_pem_bytes(_pkcs8(key)) if with_key else None,
            cert_type='server_cert', subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(), serial_number=str(cert.serial_number),
            valid_from=start.replace(tzinfo=None), valid_to=end.replace(tzinfo=None),
            source=source, created_by='admin',
        )
        db.session.add(row)
        db.session.commit()
        return row.id


def _x509(row):
    return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


def _state(app, cid):
    with app.app_context():
        db.session.expire_all()
        row = db.session.get(Certificate, cid)
        return {
            'id': row.id, 'refid': row.refid, 'created_at': row.created_at, 'crt': row.crt,
            'prv': row.prv, 'serial': row.serial_number, 'valid_to': row.valid_to,
            'renewed_times': row.renewed_times, 'renewed_at': row.renewed_at,
            'revoked': row.revoked, 'superseded': RevokedSerial.query.filter_by(certificate_id=cid).count(),
        }


def _renew(app, cid, **kwargs):
    kwargs.setdefault('username', 'admin')
    with app.app_context():
        return renew_certificate_in_place(db.session.get(Certificate, cid), **kwargs)


def _refusal(app, cid, **kwargs):
    with pytest.raises(RenewalError) as exc:
        _renew(app, cid, **kwargs)
    return exc.value


def _policy(app, ca_id, rules, *, approval=False):
    with app.app_context():
        pol = CertificatePolicy(name=f'renew-in-place-{uuid.uuid4().hex[:8]}', policy_type='issuance',
                                ca_id=ca_id, requires_approval=approval, min_approvers=1,
                                is_active=True, priority=100)
        pol.set_rules(rules)
        db.session.add(pol)
        db.session.commit()
        return pol.id


def _drop_certificates(query):
    """Delete certificate rows, their superseded serials, SCTs and files."""
    from utils.file_naming import cert_cert_path, cert_key_path
    for row in query.all():
        for path in (cert_cert_path(row), cert_key_path(row)):
            path.unlink(missing_ok=True)
        RevokedSerial.query.filter_by(certificate_id=row.id).delete()
        SystemConfig.query.filter_by(key=f'cert_scts_{row.id}').delete()
        db.session.delete(row)


@pytest.fixture
def rows(app, auth_client):
    """Certificate, policy and user ids to drop after the test, failed or not."""
    made = {'certs': [], 'policies': [], 'users': []}
    yield made
    with app.app_context():
        db.session.rollback()
        for pid in made['policies']:
            ApprovalRequest.query.filter_by(policy_id=pid).delete()
            pol = db.session.get(CertificatePolicy, pid)
            if pol:
                db.session.delete(pol)
        _drop_certificates(Certificate.query.filter(Certificate.id.in_(made['certs'])))
        db.session.commit()
    for uid in made['users']:
        auth_client.delete(f'/api/v2/users/{uid}')


@pytest.fixture
def ca(app, create_ca):
    """A CA of its own per test, deleted with everything under it by refid."""
    created = create_ca(cn=f'Renew in place {uuid.uuid4().hex[:8]}')
    refid = created['refid']
    yield created
    from services.ca.ca_crud import CAcrudMixin
    with app.app_context():
        db.session.rollback()
        row = CA.query.filter_by(refid=refid).first()
        if row is None:
            return
        _drop_certificates(Certificate.query.filter_by(caref=refid))
        RevokedSerial.query.filter_by(caref=refid).delete()
        for pol in CertificatePolicy.query.filter_by(ca_id=row.id).all():
            ApprovalRequest.query.filter_by(policy_id=pol.id).delete()
            db.session.delete(pol)
        SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{row.id}').delete()
        db.session.commit()
        CAcrudMixin.delete_ca(row.id, username='test')
        db.session.commit()
        assert CA.query.filter_by(refid=refid).first() is None


@pytest.fixture
def leaf(app, ca, rows):
    def make(cn=None, **kwargs):
        cid = _leaf(app, ca['id'], cn or f'{uuid.uuid4().hex[:10]}.renew.test', **kwargs)
        rows['certs'].append(cid)
        return cid
    return make


# --------------------------------------------------- what a renewal writes

class TestInPlace:
    def test_identity_kept_and_old_serial_superseded(self, app, ca, leaf):
        cid = leaf()
        before = _state(app, cid)
        result = _renew(app, cid)
        after = _state(app, cid)
        assert (after['id'], after['refid'], after['created_at']) == \
            (before['id'], before['refid'], before['created_at'])
        assert before['renewed_times'] == 0 and after['renewed_times'] == 1
        assert after['renewed_at'].tzinfo is None
        assert abs(after['renewed_at'] - utc_now()) < timedelta(minutes=1)
        with app.app_context():
            record = RevokedSerial.query.filter_by(certificate_id=cid).one()
            ca_row = db.session.get(CA, ca['id'])
            assert record.serial_number == before['serial']
            assert record.revoke_reason == 'superseded'
            assert record.caref == ca_row.refid
            assert record.valid_to == before['valid_to']
            assert record.revoked_at == after['renewed_at']
        assert result['cert_id'] == cid and result['old_serial'] == before['serial']
        assert result['new_serial'] == after['serial'] and result['rekeyed'] is True
        assert result['ca_id'] == ca['id'] and result['notices'] == []

    def test_second_renewal_records_the_intermediate_serial(self, app, leaf):
        cid = leaf()
        first = _state(app, cid)['serial']
        _renew(app, cid)
        middle = _state(app, cid)['serial']
        _renew(app, cid)
        after = _state(app, cid)
        assert after['renewed_times'] == 2
        with app.app_context():
            recorded = sorted(r.serial_number for r in RevokedSerial.query.filter_by(certificate_id=cid))
        assert recorded == sorted([first, middle]) and first != middle

    def test_an_existing_record_for_the_serial_is_updated_not_duplicated(self, app, ca, leaf):
        cid = leaf()
        before = _state(app, cid)
        with app.app_context():
            refid = db.session.get(CA, ca['id']).refid
            db.session.add(RevokedSerial(caref=refid, serial_number=before['serial'],
                                         revoke_reason='unspecified', certificate_id=None,
                                         valid_to=datetime(2001, 1, 1)))
            db.session.commit()
        _renew(app, cid)
        with app.app_context():
            records = RevokedSerial.query.filter_by(caref=refid, serial_number=before['serial']).all()
            assert len(records) == 1
            assert records[0].revoke_reason == 'superseded' and records[0].certificate_id == cid
            assert records[0].valid_to == before['valid_to']

    def test_columns_follow_the_new_certificate(self, app, ca, leaf):
        from utils.upn_san import build_upn_other_name
        import ipaddress
        sans = [x509.DNSName('cols.renew.test'), x509.IPAddress(ipaddress.ip_address('192.0.2.7')),
                x509.RFC822Name('ops@renew.test'), x509.UniformResourceIdentifier('https://renew.test/x'),
                build_upn_other_name('svc@corp.test')]
        cid = leaf('cols.renew.test', sans=sans)
        with app.app_context():
            row = db.session.get(Certificate, cid)
            # Columns that disagree with the certificate, and a stale state
            row.san_dns = json.dumps(['stale.example.test'])
            row.san_email = row.san_uri = row.san_upn = row.san_ip = None
            row.archived = True
            row.revoked_at = datetime(2020, 1, 1)
            row.revoke_reason = 'superseded'
            row.invalidity_at = datetime(2020, 1, 1)
            db.session.commit()
        _renew(app, cid)
        _, ca_cert, _ = _ca_parts(app, ca['id'])
        with app.app_context():
            row = db.session.get(Certificate, cid)
            cert = _x509(row)
            assert json.loads(row.san_dns) == ['cols.renew.test']
            assert json.loads(row.san_ip) == ['192.0.2.7']
            assert json.loads(row.san_email) == ['ops@renew.test']
            assert json.loads(row.san_uri) == ['https://renew.test/x']
            assert json.loads(row.san_upn) == ['svc@corp.test']
            assert (row.revoked, row.revoked_at, row.revoke_reason, row.invalidity_at, row.archived) == \
                (False, None, None, None, False)
            assert row.serial_number == format(cert.serial_number, 'x')
            assert row.issuer == ca_cert.subject.rfc4514_string()
            ski = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
            assert ski == x509.SubjectKeyIdentifier.from_public_key(cert.public_key()).digest
            assert row.ski == ski.hex(':')
            issuer_ski = ca_cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
            assert row.aki == issuer_ski.hex(':')
            assert row.valid_from == cert.not_valid_before_utc.replace(tzinfo=None)
            assert row.valid_to == cert.not_valid_after_utc.replace(tzinfo=None)

    def test_new_key_stored_encrypted_like_issuance(self, app, leaf, monkeypatch):
        seen = []
        real = renewal.encrypt_private_key

        def spy(value):
            seen.append(value)
            return real(value)
        monkeypatch.setattr(renewal, 'encrypt_private_key', spy)
        cid = leaf()
        before = _state(app, cid)
        _renew(app, cid)
        with app.app_context():
            row = db.session.get(Certificate, cid)
            key = serialization.load_pem_private_key(load_pem_bytes(row.prv, context='t'), None)
            assert key.public_key().public_numbers() == _x509(row).public_key().public_numbers()
            assert row.prv != before['prv'] and len(seen) == 1

    def test_same_key_when_not_rekeyed(self, app, leaf):
        cid = leaf()
        before = _state(app, cid)
        old_key = x509.load_pem_x509_certificate(base64.b64decode(before['crt'])).public_key()
        result = _renew(app, cid, rekey=False)
        after = _state(app, cid)
        new_key = x509.load_pem_x509_certificate(base64.b64decode(after['crt'])).public_key()
        assert new_key.public_numbers() == old_key.public_numbers()
        assert after['prv'] == before['prv'] and result['rekeyed'] is False

    def test_key_algo_matches_what_an_import_writes(self, app, leaf, rows):
        from services.cert_service import CertificateService
        cid = leaf(key=ec.generate_private_key(ec.SECP384R1()))
        _renew(app, cid)
        with app.app_context():
            row = db.session.get(Certificate, cid)
            renewed_pem = base64.b64decode(row.crt).decode()
            key_pem = load_pem_bytes(row.prv, context='t').decode()
            imported = CertificateService.import_certificate(f'import-{cid}', renewed_pem, key_pem)
            rows['certs'].append(imported.id)
            assert row.key_algo == imported.key_algo == 'EC secp384r1'

    def test_extensions_carried_and_issuer_owned_ones_rebuilt(self, app, ca, leaf):
        custom = x509.UnrecognizedExtension(x509.ObjectIdentifier('1.3.6.1.4.1.55555.1'), b'\x05\x00')
        stale_aia = x509.AuthorityInformationAccess([x509.AccessDescription(
            x509.oid.AuthorityInformationAccessOID.OCSP,
            x509.UniformResourceIdentifier('http://stale.example.test/ocsp'))])
        cid = leaf(extra=[(custom, False), (stale_aia, False)])
        with app.app_context():
            ca_row = db.session.get(CA, ca['id'])
            ca_row.ocsp_enabled = False
            ca_row.aia_ca_issuers_enabled = False
            db.session.commit()
        _renew(app, cid)
        with app.app_context():
            cert = _x509(db.session.get(Certificate, cid))
        assert cert.extensions.get_extension_for_oid(custom.oid).value.value == b'\x05\x00'
        with pytest.raises(x509.ExtensionNotFound):
            cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)

    def test_scts_follow_the_renewed_certificate(self, app, leaf, monkeypatch):
        import utils.ct_client as ct_client
        cid = leaf()
        key = f'cert_scts_{cid}'
        with app.app_context():
            db.session.add(SystemConfig(key=key, value=json.dumps([{'log': 'of the old serial'}])))
            db.session.commit()
        monkeypatch.setattr(ct_client, 'apply_ct_policy',
                            lambda cert, issuer, issuer_key: (cert, [{'log': 'new'}]))
        _renew(app, cid)
        with app.app_context():
            assert json.loads(SystemConfig.query.filter_by(key=key).one().value) == [{'log': 'new'}]
        monkeypatch.setattr(ct_client, 'apply_ct_policy', lambda cert, issuer, issuer_key: (cert, []))
        _renew(app, cid)
        with app.app_context():
            assert SystemConfig.query.filter_by(key=key).first() is None

    def test_ocsp_responder_gains_nocheck(self, app, leaf):
        eku = x509.ExtendedKeyUsage([ExtendedKeyUsageOID.OCSP_SIGNING])
        cid = leaf(extra=[(eku, False)])
        _renew(app, cid)
        with app.app_context():
            cert = _x509(db.session.get(Certificate, cid))
        cert.extensions.get_extension_for_oid(ExtensionOID.OCSP_NO_CHECK)

    def test_original_hash_is_kept_when_policies_allow_it(self, app, leaf):
        cid = leaf(digest=hashes.SHA384())
        _renew(app, cid)
        with app.app_context():
            assert isinstance(_x509(db.session.get(Certificate, cid)).signature_hash_algorithm,
                              hashes.SHA384)

    def test_names_the_ca_now_excludes_stay_renewable(self, app, ca, leaf):
        cid = leaf('par.excluded.test')
        _install_ca_cert(app, ca['id'], not_before=_now() - timedelta(days=1),
                         not_after=_now() + timedelta(days=400),
                         extra=[x509.NameConstraints(permitted_subtrees=None,
                                                     excluded_subtrees=[x509.DNSName('excluded.test')])])
        _renew(app, cid)
        assert _state(app, cid)['renewed_times'] == 1


# ----------------------------------------------------------------- duration

class TestDuration:
    def test_requested_duration_or_the_original_one(self, app, leaf):
        cid = leaf(days=90, issued_days_ago=0)
        _renew(app, cid, validity_days=30)
        with app.app_context():
            cert = _x509(db.session.get(Certificate, cid))
            assert (cert.not_valid_after_utc - _now()).days in (29, 30)
        # Without a duration: the original's 90 days
        other = leaf(lifetime=timedelta(days=90))
        _renew(app, other)
        with app.app_context():
            cert = _x509(db.session.get(Certificate, other))
            assert 89 < (cert.not_valid_after_utc - _now()).total_seconds() / 86400 <= 90.01

    def test_less_than_a_day_renews_for_the_default_year(self, app, leaf):
        cid = leaf(lifetime=timedelta(hours=6), issued_days_ago=0)
        _renew(app, cid)
        with app.app_context():
            cert = _x509(db.session.get(Certificate, cid))
            assert 364 < (cert.not_valid_after_utc - _now()).total_seconds() / 86400 <= 365.01

    def test_bounded_by_the_shared_ceiling(self, app, ca, leaf):
        _install_ca_cert(app, ca['id'], not_before=_now() - timedelta(days=1),
                         not_after=_now() + timedelta(days=30 * 365))
        cid = leaf()
        _renew(app, cid, validity_days=MAX_VALIDITY_DAYS + 100)
        with app.app_context():
            cert = _x509(db.session.get(Certificate, cid))
            span = (cert.not_valid_after_utc - _now()).total_seconds() / 86400
            assert MAX_VALIDITY_DAYS - 1 < span <= MAX_VALIDITY_DAYS + 0.01

    def test_policy_cap_gives_one_notice(self, app, ca, leaf, rows):
        cid = leaf(days=90, issued_days_ago=0)
        rows['policies'].append(_policy(app, ca['id'], {'max_validity_days': 30}))
        result = _renew(app, cid)
        with app.app_context():
            cert = _x509(db.session.get(Certificate, cid))
            assert (cert.not_valid_after_utc - _now()).total_seconds() / 86400 <= 30.01
        assert len(result['notices']) == 1 and 'caps validity at 30' in result['notices'][0]
        # Under the cap: nothing shortened, nothing said
        assert _renew(app, cid, validity_days=10)['notices'] == []

    def test_ca_expiry_caps_with_one_notice(self, app, ca, leaf):
        cid = leaf(days=30)
        ca_cert = _install_ca_cert(app, ca['id'], not_before=_now() - timedelta(days=1),
                                   not_after=_now() + timedelta(days=10))
        result = _renew(app, cid)
        with app.app_context():
            row = db.session.get(Certificate, cid)
            assert row.valid_to == ca_cert.not_valid_after_utc.replace(tzinfo=None)
        assert len(result['notices']) == 1 and 'issuing CA certificate expires' in result['notices'][0]


# ------------------------------------------------------- refusals, no writes

class TestRefusals:
    def test_revoked_or_suspended_is_refused(self, app, leaf):
        for reason in ('keyCompromise', 'certificateHold'):
            cid = leaf()
            with app.app_context():
                row = db.session.get(Certificate, cid)
                row.revoked, row.revoke_reason, row.revoked_at = True, reason, utc_now()
                db.session.commit()
            before = _state(app, cid)
            err = _refusal(app, cid)
            assert err.status == 409 and 'revoked' in err.message
            assert _state(app, cid) == before

    def test_preconditions_in_order(self, app, leaf):
        cid = leaf()
        with app.app_context():
            row = db.session.get(Certificate, cid)
            row.source, row.revoked = 'msca', True
            db.session.commit()
        # Revoked before Microsoft
        assert _refusal(app, cid).status == 409
        with app.app_context():
            db.session.get(Certificate, cid).revoked = False
            db.session.commit()
        err = _refusal(app, cid)
        assert (err.status, err.message) == (
            400, 'Microsoft CA certificates must be renewed through the AD CS connector')
        with app.app_context():
            row = db.session.get(Certificate, cid)
            row.crt, row.revoked = None, True
            db.session.commit()
        err = _refusal(app, cid)
        assert (err.status, err.message) == (400, 'Certificate data not available')

    def test_device_held_key_is_refused(self, app, leaf):
        cid = leaf(with_key=False, source='scep')
        before = _state(app, cid)
        err = _refusal(app, cid)
        assert err.status == 409 and 'enrollment protocol' in err.message
        assert _state(app, cid) == before

    @pytest.mark.parametrize('change, status, message', [
        ('no_key', 400, 'CA private key not available. Cannot renew without CA private key.'),
        ('pending', 400, 'Issuing CA is awaiting its certificate'),
        ('offline', 400, 'CA is offline; restore it before renewing'),
        ('revoked', 400, 'CA is revoked and can no longer renew certificates'),
        ('bad_key', 500, 'Failed to load CA signing key'),
    ])
    def test_ca_that_cannot_sign(self, app, ca, leaf, change, status, message):
        cid = leaf()
        before = _state(app, cid)
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            if change == 'no_key':
                row.prv, row.hsm_key_id = None, None
            elif change == 'pending':
                row.crt = ''
            elif change == 'offline':
                row.offline = True
            elif change == 'revoked':
                row.revoked = True
            else:
                row.prv = base64.b64encode(b'not a key').decode()
            db.session.commit()
        err = _refusal(app, cid)
        assert (err.status, err.message) == (status, message)
        assert _state(app, cid) == before

    def test_missing_ca_is_a_404(self, app, leaf, monkeypatch):
        cid = leaf()
        before = _state(app, cid)
        monkeypatch.setattr(renewal, 'resolve_issuing_ca', lambda cert: None)
        err = _refusal(app, cid)
        assert err.status == 404 and err.message.startswith('Issuing CA not found')
        assert _state(app, cid) == before

    def test_fips_refusal_of_the_ca_key_keeps_its_problem_type(self, app, leaf, monkeypatch):
        cid = leaf()

        def refuse(ca, **_):
            raise fips_mode.FipsRestricted('Ed25519 keys not available in FIPS mode')
        import services.hsm.ca_key_loader as loader
        monkeypatch.setattr(loader, 'get_ca_signing_key', refuse)
        err = _refusal(app, cid)
        assert (err.status, err.problem_type) == (400, fips_mode.PROBLEM_TYPE)

    def test_expired_ca_is_refused(self, app, ca, leaf):
        cid = leaf()
        _install_ca_cert(app, ca['id'], not_before=_now() - timedelta(days=30),
                         not_after=_now() - timedelta(days=1))
        err = _refusal(app, cid)
        assert err.status == 400 and 'expired' in err.message

    def test_ct_refusal_is_a_400(self, app, leaf, monkeypatch):
        import utils.ct_client as ct_client
        cid = leaf()
        before = _state(app, cid)

        def refuse(cert, issuer_cert, issuer_key):
            raise ValueError('no CT log accepted the pre-certificate')
        monkeypatch.setattr(ct_client, 'apply_ct_policy', refuse)
        err = _refusal(app, cid)
        assert (err.status, err.message) == (400, 'Cannot renew: no CT log accepted the pre-certificate')
        assert _state(app, cid) == before

    def test_violations_are_reported_together_before_any_key(self, app, ca, leaf, rows, monkeypatch):
        cid = leaf('one.renew.test', sans=[x509.DNSName('one.renew.test'), x509.DNSName('two.renew.test')])
        rows['policies'].append(_policy(app, ca['id'], {
            'allowed_key_types': ['EC-P256'], 'san_restrictions': {'max_dns_names': 1}}))
        _forbid_key_generation(monkeypatch)
        before = _state(app, cid)
        err = _refusal(app, cid)
        assert err.status == 400 and err.message.startswith('Policy violation: ')
        assert 'RSA-2048' in err.message and '2 DNS names exceed' in err.message and '; ' in err.message
        assert _state(app, cid) == before

    def test_template_san_types_refuse_an_email(self, app, leaf):
        from models import CertificateTemplate
        with app.app_context():
            tpl = CertificateTemplate(
                name=f'renew-dns-only-{uuid.uuid4().hex[:8]}', template_type='custom',
                key_type='RSA-2048', validity_days=30, digest='sha256',
                dn_template=json.dumps({'CN': '{cn}'}),
                extensions_template=json.dumps({'san_types': ['dns']}), enforce_san_types=True)
            db.session.add(tpl)
            db.session.commit()
            tpl_id = tpl.id
        try:
            bad = leaf('mail.renew.test', sans=[x509.DNSName('mail.renew.test'),
                                                x509.RFC822Name('ops@renew.test')])
            good = leaf('dns.renew.test')
            with app.app_context():
                for cid in (bad, good):
                    db.session.get(Certificate, cid).template_id = tpl_id
                db.session.commit()
            err = _refusal(app, bad)
            assert err.status == 400 and err.message.startswith('Policy violation: ')
            _renew(app, good)
            assert _state(app, good)['renewed_times'] == 1
        finally:
            with app.app_context():
                for cid in (bad, good):
                    row = db.session.get(Certificate, cid)
                    if row:
                        row.template_id = None
                db.session.delete(db.session.get(CertificateTemplate, tpl_id))
                db.session.commit()


def _forbid_key_generation(monkeypatch):
    def no_key(*_a, **_k):
        raise AssertionError('a key was generated for a refused renewal')
    monkeypatch.setattr(renewal, 'generate_rsa', no_key)
    monkeypatch.setattr(renewal, 'generate_ec', no_key)
    monkeypatch.setattr(key_algorithms.KeyAlgorithm, 'generate', no_key)
    monkeypatch.setattr(ed25519.Ed25519PrivateKey, 'generate', no_key)
    monkeypatch.setattr(ed448.Ed448PrivateKey, 'generate', no_key)


# ------------------------------------------------------------- key families

class TestKeyFamilies:
    @pytest.mark.parametrize('make, same', [
        (lambda: ec.generate_private_key(ec.SECP384R1()),
         lambda k: isinstance(k, ec.EllipticCurvePublicKey) and k.curve.name == 'secp384r1'),
        (lambda: rsa.generate_private_key(65537, 3072),
         lambda k: isinstance(k, rsa.RSAPublicKey) and k.key_size == 3072),
        (lambda: ed25519.Ed25519PrivateKey.generate(),
         lambda k: isinstance(k, ed25519.Ed25519PublicKey)),
    ], ids=['P-384', 'RSA-3072', 'Ed25519'])
    def test_rekey_keeps_the_family(self, app, leaf, make, same):
        key = make()
        cid = leaf(key=key)
        _renew(app, cid)
        with app.app_context():
            new_key = _x509(db.session.get(Certificate, cid)).public_key()
        assert same(new_key)
        assert new_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) != \
            key.public_key().public_bytes(serialization.Encoding.DER,
                                          serialization.PublicFormat.SubjectPublicKeyInfo)

    def test_dsa_is_refused_before_any_key(self, app, leaf, monkeypatch):
        cid = leaf(key=dsa.generate_private_key(2048), digest=hashes.SHA256())
        before = _state(app, cid)
        _forbid_key_generation(monkeypatch)
        err = _refusal(app, cid)
        assert err.status == 400
        assert err.message == ('Cannot renew: a DSAPublicKey key cannot be regenerated; '
                               'issue a new certificate instead')
        assert _state(app, cid) == before

    def test_fips_mode_refuses_a_stored_ed25519_key(self, app, leaf, monkeypatch):
        cid = leaf(key=ed25519.Ed25519PrivateKey.generate())
        before = _state(app, cid)
        _forbid_key_generation(monkeypatch)
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        for rekey in (True, False):
            err = _refusal(app, cid, rekey=rekey)
            assert (err.status, err.problem_type) == (400, fips_mode.PROBLEM_TYPE)
        assert _state(app, cid) == before


# -------------------------------------------------------------- concurrency

class TestConcurrency:
    def test_two_renewals_from_the_same_serial(self, app, leaf):
        cid = leaf()
        known = _state(app, cid)['serial']
        _renew(app, cid, known_serial=known)
        after_first = _state(app, cid)
        err = _refusal(app, cid, known_serial=known, trigger='auto')
        assert (err.status, err.message) == (409, 'Certificate was renewed by another request')
        assert _state(app, cid) == after_first

    def test_serial_taken_meanwhile_is_refused_and_rolled_back(self, app, leaf, monkeypatch):
        cid = leaf()
        before = _state(app, cid)
        real = renewal.resolve_issuing_ca

        def renewed_elsewhere(cert):
            db.session.query(Certificate).filter(Certificate.id == cid).update(
                {Certificate.serial_number: 'feedface'}, synchronize_session=False)
            return real(cert)
        monkeypatch.setattr(renewal, 'resolve_issuing_ca', renewed_elsewhere)
        with app.app_context():
            with pytest.raises(RenewalError) as exc:
                renew_certificate_in_place(db.session.get(Certificate, cid), username='admin')
            assert exc.value.message == 'Certificate was renewed by another request; reload it and retry'
            # Left clean: committing now writes nothing of the failed attempt
            db.session.commit()
        assert _state(app, cid) == before

    def test_deleted_row_is_a_404(self, app, leaf):
        cid = leaf()
        with app.app_context():
            row = db.session.get(Certificate, cid)
            db.session.query(Certificate).filter(Certificate.id == cid).delete(synchronize_session=False)
            db.session.commit()
            with pytest.raises(RenewalError) as exc:
                renew_certificate_in_place(row, username='admin')
            assert (exc.value.status, exc.value.message) == (404, 'Certificate no longer exists')

    def test_failure_discards_the_callers_pending_changes(self, app, ca, leaf):
        cid = leaf()
        with app.app_context():
            db.session.get(CA, ca['id']).offline = True
            db.session.commit()
            row = db.session.get(Certificate, cid)
            row.descr = 'changed by the caller'
            with pytest.raises(RenewalError):
                renew_certificate_in_place(row, username='admin')
            db.session.commit()
            db.session.expire_all()
            assert db.session.get(Certificate, cid).descr != 'changed by the caller'

    def test_failed_commit_changes_nothing(self, app, leaf, monkeypatch):
        cid = leaf()
        before = _state(app, cid)
        with app.app_context():
            session = db.session
            real_commit = session.commit
            calls = []

            def failing_commit():
                calls.append(1)
                if len(calls) == 1:
                    raise RuntimeError('disk full')
                return real_commit()
            monkeypatch.setattr(session, 'commit', failing_commit)
            with pytest.raises(RenewalError) as exc:
                renew_certificate_in_place(db.session.get(Certificate, cid), username='admin')
            monkeypatch.undo()
            assert (exc.value.status, exc.value.message) == (500, 'Failed to renew certificate')
        assert _state(app, cid) == before


# ------------------------------------------------------ effects after commit

def _audit_ids(app, cid):
    """Ids of the renewal entries about this id (SQLite reuses row ids)."""
    from models import AuditLog
    with app.app_context():
        return {a.id for a in AuditLog.query.filter_by(action='certificate_renewed', resource_id=str(cid))}


class TestEffects:
    def test_pending_request_closed_as_approved(self, app, ca, leaf, rows, create_user):
        from models import User
        from services.policy_service import PolicyEvaluationService
        operator = create_user(role='operator')
        rows['users'].append(operator['id'])
        pid = _policy(app, ca['id'], {}, approval=True)
        rows['policies'].append(pid)
        for trigger, reason in (('manual', 'Renewed directly'), ('auto', 'Renewed by the scheduler')):
            cid = leaf()
            with app.app_context():
                request = PolicyEvaluationService.create_approval_request(
                    db.session.get(CertificatePolicy, pid), {'certificate_id': cid, 'cn': 'x'},
                    requester_id=operator['id'], request_type='renewal')
                request_id = request.id
                admin = User.query.filter_by(username='admin').first()
                admin_id = admin.id
            _renew(app, cid, actor_user_id=admin_id, trigger=trigger, rekey=trigger != 'auto')
            with app.app_context():
                request = db.session.get(ApprovalRequest, request_id)
                assert request.status == 'approved' and request.certificate_id == cid
                vote = request.get_approvals()[-1]
                assert (vote['username'], vote['user_id'], vote['comment']) == ('admin', admin_id, reason)

    def test_audit_and_webhook_once(self, app, ca, leaf, monkeypatch):
        import services.webhook_service as webhooks
        from models import AuditLog
        events = []

        def renewed(cert, ca_refid=None, actor=None):
            events.append(('renewed', cert['id'], ca_refid, actor))
        monkeypatch.setattr(webhooks, 'emit_cert_renewed', renewed)
        for other in ('emit_cert_revoked', 'emit_cert_deleted'):
            monkeypatch.setattr(webhooks, other, lambda *a, _n=other, **k: events.append((_n,)))
        cid = leaf()
        before = _state(app, cid)
        seen = _audit_ids(app, cid)
        result = _renew(app, cid, username='admin', trigger='bulk')
        with app.app_context():
            refid = db.session.get(CA, ca['id']).refid
            logs = [db.session.get(AuditLog, i) for i in _audit_ids(app, cid) - seen]
        assert events == [('renewed', cid, refid, 'admin')]
        assert len(logs) == 1 and logs[0].username == 'admin'
        for fragment in ('bulk', 'rekeyed', before['serial'], result['new_serial']):
            assert fragment in logs[0].details

    def test_ocsp_caches_dropped(self, app, ca, leaf):
        from models import OCSPResponse
        from utils.serial_format import serial_to_int
        cid = leaf()
        old = _state(app, cid)['serial']
        now = utc_now()

        def cached(serial_hex):
            return OCSPResponse(ca_id=ca['id'], cert_serial=serial_hex, response_der=b'x', status='good',
                                this_update=now, next_update=now + timedelta(hours=1))
        with app.app_context():
            db.session.add_all([cached(format(serial_to_int(old), 'x')), cached('abcdef01')])
            db.session.commit()
        _renew(app, cid)
        with app.app_context():
            assert [r.cert_serial for r in OCSPResponse.query.filter_by(ca_id=ca['id'])] == ['abcdef01']
            # A delegated responder: every cached answer of its CA goes
            db.session.add(SystemConfig(key=f'ocsp_responder_cert_{ca["id"]}', value=str(cid)))
            db.session.commit()
        try:
            _renew(app, cid)
            with app.app_context():
                assert OCSPResponse.query.filter_by(ca_id=ca['id']).count() == 0
        finally:
            with app.app_context():
                SystemConfig.query.filter_by(key=f'ocsp_responder_cert_{ca["id"]}').delete()
                db.session.commit()

    def test_crl_regenerated_only_when_asked_and_published(self, app, ca, leaf, monkeypatch):
        from services.crl import CRLService
        calls = []
        monkeypatch.setattr(CRLService, 'generate_crl',
                            staticmethod(lambda ca_id, validity_days=None, username='system': calls.append(ca_id)))
        cid = leaf()
        with app.app_context():
            db.session.get(CA, ca['id']).cdp_enabled = False
            db.session.commit()
        _renew(app, cid)
        assert calls == []
        with app.app_context():
            db.session.get(CA, ca['id']).cdp_enabled = True
            db.session.commit()
        _renew(app, cid, regenerate_crl=False)
        assert calls == []
        _renew(app, cid)
        assert calls == [ca['id']]

    def test_files_written_and_mirror_failure_is_a_warning(self, app, leaf, monkeypatch):
        from utils.file_naming import cert_cert_path
        cid = leaf()

        def broken(*_a, **_k):
            raise OSError('read-only file system')
        monkeypatch.setattr(renewal, 'mirror_private_key', broken)
        _renew(app, cid)
        with app.app_context():
            row = db.session.get(Certificate, cid)
            assert cert_cert_path(row).read_bytes() == base64.b64decode(row.crt)

    def test_a_failing_effect_stops_neither_the_renewal_nor_the_next(self, app, leaf, monkeypatch):
        import services.approval_gate as gate
        import services.webhook_service as webhooks
        from services.ocsp_service import OCSPService

        def broken(*_a, **_k):
            raise RuntimeError('database is locked')
        monkeypatch.setattr(gate, 'resolve_moot_requests', broken)
        monkeypatch.setattr(OCSPService, 'responder_cas_for_certificate', staticmethod(broken))
        monkeypatch.setattr(OCSPService, 'invalidate_cached_responses', staticmethod(broken))
        events = []
        monkeypatch.setattr(webhooks, 'emit_cert_renewed', lambda *a, **k: events.append(1))
        cid = leaf()
        seen = _audit_ids(app, cid)
        _renew(app, cid)
        assert len(_audit_ids(app, cid) - seen) == 1
        assert events == [1] and _state(app, cid)['renewed_times'] == 1

    def test_old_serial_answers_revoked_at_once(self, app, ca, leaf):
        """Needs the B.6 responder."""
        from services.ocsp_service import OCSPService
        from utils.serial_format import serial_to_int
        cid = leaf()
        old = serial_to_int(_state(app, cid)['serial'])
        with app.app_context():
            OCSPService().generate_response(db.session.get(CA, ca['id']), old)
        _renew(app, cid)
        with app.app_context():
            _, status = OCSPService().generate_response(db.session.get(CA, ca['id']), old)
        assert status == 'revoked'
