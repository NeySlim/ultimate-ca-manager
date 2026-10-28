"""The hourly SKI dedup merges only records holding the same certificate.

A cross-certificate shares the subject and key (hence the SKI) of the root it
cross-signs. Merging the two kept the cross-certified row, copied the root's key
into it and deleted the self-signed root (#400).
"""
import base64
import uuid
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import db, CA
from services.ski_aki_backfill import backfill_ski_aki
from utils.key_codec import store_pem_bytes


def _cert(subject_key, cn, issuer_key=None, issuer_cn=None):
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn or cn)])
    return (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
            .public_key(subject_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(subject_key.public_key()), critical=False)
            .sign(issuer_key or subject_key, hashes.SHA256()))


def _row(cert, key=None, caref=None, crt=None):
    ski = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.key_identifier
    pem_key = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()) if key else None
    row = CA(refid=str(uuid.uuid4()), descr=cert.subject.rfc4514_string(), serial=0,
             crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode() if crt is None else crt,
             prv=store_pem_bytes(pem_key) if pem_key else None, caref=caref,
             subject=cert.subject.rfc4514_string(), issuer=cert.issuer.rfc4514_string(),
             serial_number=str(cert.serial_number), ski=ski.hex(':').upper())
    db.session.add(row)
    db.session.commit()
    return row.id


def test_self_signed_root_survives_its_cross_certificate(app):
    key_a, key_b = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    with app.app_context():
        root_a = db.session.get(CA, _row(_cert(key_a, 'Cross Root A'), key_a))
        self_signed = _cert(key_b, 'Cross Root B')
        b_id = _row(self_signed, key_b)
        cross_id = _row(_cert(key_b, 'Cross Root B', key_a, 'Cross Root A'), caref=root_a.refid)
        b_crt = db.session.get(CA, b_id).crt

        stats = backfill_ski_aki()

        db.session.expire_all()
        b = db.session.get(CA, b_id)
        assert b is not None, 'self-signed root deleted'
        assert b.crt == b_crt and b.caref is None and b.prv
        assert db.session.get(CA, cross_id) is not None
        assert stats['same_key_distinct_certs'] >= 1


def test_identical_duplicates_are_still_merged(app):
    key = ec.generate_private_key(ec.SECP256R1())
    cert = _cert(key, 'Duplicate Root')
    with app.app_context():
        first = _row(cert, key)
        second = _row(cert)

        stats = backfill_ski_aki()

        db.session.expire_all()
        remaining = [i for i in (first, second) if db.session.get(CA, i) is not None]
        assert len(remaining) == 1
        assert db.session.get(CA, remaining[0]).prv
        assert stats['deduplicated'] >= 1


def test_record_without_certificate_is_not_merged(app):
    """The keeper is chosen by parent link and key: merging a record without a
    certificate could keep it and delete the one holding the certificate."""
    key_a, key_b = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    with app.app_context():
        root_a = db.session.get(CA, _row(_cert(key_a, 'Pending Parent'), key_a))
        signed = _cert(key_b, 'Pending Sub', key_a, 'Pending Parent')
        pending = _row(signed, key_b, caref=root_a.refid, crt='')
        imported = _row(signed, caref=root_a.refid)

        backfill_ski_aki()

        db.session.expire_all()
        assert db.session.get(CA, imported).crt
        assert db.session.get(CA, pending) is not None


def test_merging_a_duplicate_leaves_no_orphan_rows(app):
    """CRL, OCSP and pin rows of the deleted record go with it; its issued state moves to the keeper."""
    from models import CertificateTemplate, CATemplatePin, CRLMetadata, OCSPResponse
    from models.certificate import Certificate
    from models.revoked_serial import RevokedSerial

    key = ec.generate_private_key(ec.SECP256R1())
    cert = _cert(key, 'Orphan Root')
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with app.app_context():
        keeper_id = _row(cert, key)
        dupe_id = _row(cert)
        keeper, dupe = db.session.get(CA, keeper_id), db.session.get(CA, dupe_id)
        keeper_refid, dupe_refid = keeper.refid, dupe.refid
        template = CertificateTemplate(name=f'orphan-{uuid.uuid4().hex[:8]}', template_type='server',
                                       extensions_template='{}')
        db.session.add(template)
        db.session.flush()
        db.session.add_all([
            CRLMetadata(ca_id=dupe_id, crl_number=1, this_update=now, next_update=now + timedelta(days=1),
                        crl_pem='x', crl_der=b'x'),
            OCSPResponse(ca_id=dupe_id, cert_serial='01', response_der=b'x', status='good',
                         this_update=now, next_update=now + timedelta(days=1)),
            CATemplatePin(ca_id=dupe_id, template_id=template.id),
            RevokedSerial(caref=dupe_refid, serial_number='02', valid_to=now + timedelta(days=30)),
            Certificate(refid=str(uuid.uuid4()), descr='issued', caref=dupe_refid, crt='', subject='CN=issued',
                        serial_number='03'),
        ])
        db.session.commit()

        backfill_ski_aki()

        db.session.expire_all()
        assert db.session.get(CA, dupe_id) is None
        assert CRLMetadata.query.filter_by(ca_id=dupe_id).count() == 0
        assert OCSPResponse.query.filter_by(ca_id=dupe_id).count() == 0
        assert CATemplatePin.query.filter_by(ca_id=dupe_id).count() == 0
        assert RevokedSerial.query.filter_by(caref=dupe_refid).count() == 0
        assert RevokedSerial.query.filter_by(caref=keeper_refid, serial_number='02').count() == 1
        assert Certificate.query.filter_by(descr='issued').one().caref == keeper_refid
        assert CATemplatePin.query.filter_by(ca_id=keeper_id, template_id=template.id).count() == 1


def test_merging_a_duplicate_moves_child_cas_and_crl_rows(app):
    """caref columns carry no foreign key: children and legacy CRL rows still follow the keeper."""
    from models.crl_list import CRL

    key, child_key = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    cert = _cert(key, 'Caref Root')
    with app.app_context():
        keeper_id = _row(cert, key)
        dupe_id = _row(cert)
        dupe_refid = db.session.get(CA, dupe_id).refid
        keeper_refid = db.session.get(CA, keeper_id).refid
        child_id = _row(_cert(child_key, 'Caref Child', key, 'Caref Root'), child_key, caref=dupe_refid)
        db.session.add(CRL(caref=dupe_refid, descr='legacy', text='x'))
        db.session.commit()

        backfill_ski_aki()

        db.session.expire_all()
        assert db.session.get(CA, dupe_id) is None
        assert db.session.get(CA, child_id).caref == keeper_refid
        assert CRL.query.filter_by(descr='legacy').one().caref == keeper_refid


def test_duplicates_bound_to_the_same_deploy_target_are_merged(app):
    from models.deploy import CRLDeployBinding, DeployTarget

    key = ec.generate_private_key(ec.SECP256R1())
    cert = _cert(key, 'Binding Root')
    with app.app_context():
        keeper_id = _row(cert, key)
        dupe_id = _row(cert)
        target = DeployTarget(name=f'bind-{uuid.uuid4().hex[:8]}', host='h', username='u', private_key='k')
        db.session.add(target)
        db.session.flush()
        db.session.add_all([CRLDeployBinding(target_id=target.id, ca_id=i, crl_path=f'/c{i}.crl')
                            for i in (keeper_id, dupe_id)])
        db.session.commit()

        stats = backfill_ski_aki()

        db.session.expire_all()
        assert db.session.get(CA, dupe_id) is None
        assert stats['deduplicated'] >= 1
        assert CRLDeployBinding.query.filter_by(target_id=target.id).count() == 1


def test_merge_carries_the_duplicates_crl_numbers_to_the_keeper(app):
    """CRL numbers stay monotonic for a CA key: the keeper continues after the duplicate's last one."""
    from models import CRLMetadata
    key = ec.generate_private_key(ec.SECP256R1())
    cert = _cert(key, 'Crl Number Root')
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with app.app_context():
        keeper_id = _row(cert, key)
        dupe_id = _row(cert)
        db.session.add(CRLMetadata(ca_id=dupe_id, crl_number=12, this_update=now,
                                   next_update=now + timedelta(days=1), crl_pem='x', crl_der=b'x'))
        db.session.commit()

        backfill_ski_aki()

        db.session.expire_all()
        assert db.session.get(CA, dupe_id) is None
        assert [m.crl_number for m in CRLMetadata.query.filter_by(ca_id=keeper_id)] == [12]
