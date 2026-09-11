"""In-place renewal produces what issuance would: the issuer's own
extensions rebuilt from the CA's configuration, a Key Usage the key type can
honour, a key at least as strong as issuance requires, the CT policy applied,
the real issuer resolved by signature, and never a certificate whose key the
device holds.
"""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtensionOID, NameOID

from models import CA, Certificate, RevokedSerial, db
from services.cert.renewal import RenewalError, renew_certificate_in_place, resolve_issuing_ca
from utils.key_codec import load_pem_bytes, store_pem_bytes

SCT_LIST_OID = x509.ObjectIdentifier('1.3.6.1.4.1.11129.2.4.2')


def _ca_material(app, ca_id):
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        ca_cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt), default_backend())
        ca_key = serialization.load_pem_private_key(
            load_pem_bytes(ca.prv, context='test'), password=None, backend=default_backend())
        return ca.refid, ca_cert, ca_key


def _craft_row(app, ca_id, key, cn, *, key_usage=None, extra=(), caref='auto', with_key=True,
               source='manual', days=30):
    """A leaf signed by the CA row's key, stored the way older issuance did."""
    refid, ca_cert, ca_key = _ca_material(app, ca_id)
    now = datetime.now(timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .issuer_name(ca_cert.subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    )
    if key_usage is not None:
        builder = builder.add_extension(key_usage, critical=True)
    for ext, critical in extra:
        builder = builder.add_extension(ext, critical)
    cert = builder.sign(ca_key, hashes.SHA256())
    with app.app_context():
        row = Certificate(
            refid=f'renew-{cn}'[:36], descr=cn,
            caref=(refid if caref == 'auto' else caref),
            crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
            prv=store_pem_bytes(key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption())) if with_key else None,
            cert_type='server_cert', subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(), serial_number=str(cert.serial_number),
            valid_from=(now - timedelta(days=1)).replace(tzinfo=None),
            valid_to=(now + timedelta(days=days)).replace(tzinfo=None),
            source=source, created_by='admin',
        )
        db.session.add(row)
        db.session.commit()
        return row.id


def _renew(app, row_id, **kwargs):
    with app.app_context():
        row = db.session.get(Certificate, row_id)
        result = renew_certificate_in_place(row, username='admin', **kwargs)
        db.session.commit()
        row = db.session.get(Certificate, row_id)
        return result, x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend())


def _drop(app, *row_ids):
    with app.app_context():
        for rid in row_ids:
            row = db.session.get(Certificate, rid)
            if row:
                RevokedSerial.query.filter_by(certificate_id=rid).delete()
                db.session.delete(row)
        db.session.commit()


def _ku(**flags):
    base = dict(digital_signature=False, key_encipherment=False, content_commitment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False)
    base.update(flags)
    return x509.KeyUsage(**base)


class TestRenewalMatchesIssuance:

    def test_ec_key_loses_key_encipherment_on_renewal(self, app, create_ca):
        ca = create_ca(cn='Renewal KU CA')
        key = ec.generate_private_key(ec.SECP256R1())
        rid = _craft_row(app, ca['id'], key, 'ku.example.test',
                         key_usage=_ku(digital_signature=True, key_encipherment=True))
        try:
            _, renewed = _renew(app, rid, rekey=True)
            ku = renewed.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value
            assert ku.digital_signature and not ku.key_encipherment
        finally:
            _drop(app, rid)

    def test_pointer_extensions_follow_the_ca_configuration(self, app, create_ca):
        ca = create_ca(cn='Renewal CDP CA')
        stale = x509.CRLDistributionPoints([x509.DistributionPoint(
            full_name=[x509.UniformResourceIdentifier('http://old.example.test/ca.crl')],
            relative_name=None, reasons=None, crl_issuer=None)])
        # a syntactically valid, empty SCT list (OCTET STRING of a 0-length TLS list)
        sct = x509.UnrecognizedExtension(SCT_LIST_OID, b'\x04\x02\x00\x00')
        rid = _craft_row(app, ca['id'], rsa.generate_private_key(65537, 2048), 'cdp.example.test',
                         key_usage=_ku(digital_signature=True, key_encipherment=True),
                         extra=[(stale, False), (sct, False)])
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            row.cdp_enabled = True
            row.set_cdp_urls(['http://ca.example.test/{ca_refid}.crl'])
            db.session.commit()
            expected = 'http://ca.example.test/' + row.url_ref + '.crl'
        try:
            _, renewed = _renew(app, rid)
            cdp = renewed.extensions.get_extension_for_oid(ExtensionOID.CRL_DISTRIBUTION_POINTS).value
            assert [n.value for dp in cdp for n in dp.full_name] == [expected]
            with pytest.raises(x509.ExtensionNotFound):
                renewed.extensions.get_extension_for_oid(SCT_LIST_OID)
            assert renewed.not_valid_before_utc < datetime.now(timezone.utc)
        finally:
            _drop(app, rid)

    def test_weak_key_is_refused(self, app, create_ca):
        ca = create_ca(cn='Renewal weak key CA')
        rid = _craft_row(app, ca['id'], rsa.generate_private_key(65537, 1024), 'weak.example.test',
                         key_usage=_ku(digital_signature=True, key_encipherment=True))
        try:
            with pytest.raises(RenewalError):
                _renew(app, rid, rekey=False)
            with pytest.raises(RenewalError):
                _renew(app, rid, rekey=True)
        finally:
            _drop(app, rid)

    def test_ct_policy_applies(self, app, create_ca, monkeypatch):
        ca = create_ca(cn='Renewal CT CA')
        rid = _craft_row(app, ca['id'], rsa.generate_private_key(65537, 2048), 'ct.example.test',
                         key_usage=_ku(digital_signature=True, key_encipherment=True))
        import utils.ct_client as ct_client

        def refuse(cert, issuer_cert, issuer_key):
            raise ValueError('ct_required: no SCT could be obtained')
        monkeypatch.setattr(ct_client, 'apply_ct_policy', refuse)
        try:
            with pytest.raises(RenewalError, match='SCT'):
                _renew(app, rid)
        finally:
            _drop(app, rid)


class TestIssuerResolution:

    def test_signature_decides_between_homonymous_cas(self, app, create_ca):
        first = create_ca(cn='Homonym CA')
        second = create_ca(cn='Homonym CA')
        with app.app_context():
            a, b = db.session.get(CA, first['id']), db.session.get(CA, second['id'])
            assert a.subject == b.subject
        rid = _craft_row(app, second['id'], rsa.generate_private_key(65537, 2048), 'homonym.example.test',
                         key_usage=_ku(digital_signature=True, key_encipherment=True), caref=None)
        try:
            with app.app_context():
                row = db.session.get(Certificate, rid)
                assert resolve_issuing_ca(row).id == second['id']
            result, _ = _renew(app, rid)
            with app.app_context():
                row = db.session.get(Certificate, rid)
                assert row.caref == db.session.get(CA, second['id']).refid
                superseded = RevokedSerial.query.filter_by(certificate_id=rid).first()
                assert superseded is not None and superseded.caref == row.caref
        finally:
            _drop(app, rid)

    def test_a_certificate_no_ca_signed_is_not_renewed_by_a_namesake(self, app, create_ca):
        create_ca(cn='Namesake CA')
        foreign_key = rsa.generate_private_key(65537, 2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Namesake CA')])
        now = datetime.now(timezone.utc)
        leaf = (x509.CertificateBuilder().subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'foreign.example.test')]))
            .issuer_name(name).public_key(foreign_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
            .sign(foreign_key, hashes.SHA256()))
        with app.app_context():
            row = Certificate(refid='renew-foreign', descr='foreign', caref=None,
                              crt=base64.b64encode(leaf.public_bytes(serialization.Encoding.PEM)).decode(),
                              cert_type='server_cert', subject=leaf.subject.rfc4514_string(),
                              issuer=leaf.issuer.rfc4514_string(), serial_number=str(leaf.serial_number),
                              valid_from=(now - timedelta(days=1)).replace(tzinfo=None),
                              valid_to=(now + timedelta(days=30)).replace(tzinfo=None), source='manual')
            db.session.add(row)
            db.session.commit()
            rid = row.id
        try:
            with app.app_context():
                assert resolve_issuing_ca(db.session.get(Certificate, rid)) is None
        finally:
            _drop(app, rid)


class TestDeviceHeldKeys:

    def test_manual_renewal_refuses_a_certificate_without_its_key(self, app, create_ca):
        ca = create_ca(cn='Renewal device key CA')
        rid = _craft_row(app, ca['id'], rsa.generate_private_key(65537, 2048), 'scep-device.example.test',
                         key_usage=_ku(digital_signature=True, key_encipherment=True),
                         with_key=False, source='scep')
        try:
            with pytest.raises(RenewalError) as exc:
                _renew(app, rid, rekey=True)
            assert exc.value.status == 409
            with app.app_context():
                row = db.session.get(Certificate, rid)
                assert row.prv is None
                assert RevokedSerial.query.filter_by(certificate_id=rid).count() == 0
        finally:
            _drop(app, rid)

    def test_scheduler_never_selects_a_certificate_without_its_key(self, app, create_ca):
        from services.auto_renewal_service import AutoRenewalService
        ca = create_ca(cn='Renewal scheduler CA')
        rid = _craft_row(app, ca['id'], rsa.generate_private_key(65537, 2048), 'est-device.example.test',
                         key_usage=_ku(digital_signature=True, key_encipherment=True),
                         with_key=False, source='est', days=5)
        try:
            with app.app_context():
                config = AutoRenewalService.get_renewal_config()
                previous = dict(config)
                AutoRenewalService.set_renewal_config({**config, 'enabled': True, 'days_before_expiry': 30,
                                                       'renewal_sources': ['scep', 'acme', 'est']})
                try:
                    selected = [c.id for c in AutoRenewalService.get_certificates_for_renewal()]
                    assert rid not in selected
                finally:
                    AutoRenewalService.set_renewal_config(previous)
        finally:
            _drop(app, rid)

    def test_scheduler_selects_a_certificate_whose_key_it_holds(self, app, create_ca):
        from services.auto_renewal_service import AutoRenewalService
        ca = create_ca(cn='Renewal scheduler keyed CA')
        rid = _craft_row(app, ca['id'], rsa.generate_private_key(65537, 2048), 'keyed.example.test',
                         key_usage=_ku(digital_signature=True, key_encipherment=True),
                         with_key=True, source='manual', days=5)
        try:
            with app.app_context():
                previous = dict(AutoRenewalService.get_renewal_config())
                AutoRenewalService.set_renewal_config({**previous, 'enabled': True, 'days_before_expiry': 30,
                                                       'renewal_sources': ['manual']})
                try:
                    config = AutoRenewalService.get_renewal_config()
                    assert config['renewal_sources'] == ['manual'] and config['days_before_expiry'] == 30
                    assert rid in [c.id for c in AutoRenewalService.get_certificates_for_renewal()]
                finally:
                    AutoRenewalService.set_renewal_config(previous)
        finally:
            _drop(app, rid)


class TestConcurrentRenewal:

    def test_second_renewal_of_a_stale_row_is_refused(self, app, create_ca, monkeypatch):
        ca = create_ca(cn='Renewal race CA')
        rid = _craft_row(app, ca['id'], rsa.generate_private_key(65537, 2048), 'race.example.test',
                         key_usage=_ku(digital_signature=True, key_encipherment=True))
        try:
            with app.app_context():
                row = db.session.get(Certificate, rid)
                # The renewal re-reads the row first (locked on PostgreSQL;
                # SQLite takes no row lock): another worker renews it right
                # after that read, so the serial this worker holds is stale
                # by the time it writes
                import services.cert.renewal as renewal_module
                original_resolve = renewal_module.resolve_issuing_ca

                def resolve_after_concurrent_renewal(cert):
                    db.session.query(Certificate).filter(Certificate.id == rid).update(
                        {Certificate.serial_number: 'deadbeef'}, synchronize_session=False)
                    return original_resolve(cert)
                monkeypatch.setattr(renewal_module, 'resolve_issuing_ca', resolve_after_concurrent_renewal)
                with pytest.raises(RenewalError) as exc:
                    renew_certificate_in_place(row, username='admin')
                assert exc.value.status == 409
                db.session.rollback()
        finally:
            _drop(app, rid)
