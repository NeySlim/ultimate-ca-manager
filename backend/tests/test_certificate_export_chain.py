"""Adversarial chain-building tests for certificate exports."""

import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from api.v2.certificates.export import _build_ca_chain, _resolve_issuer_cert
from models import CA, db


def _name(common_name):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _key_id(public_key):
    return x509.SubjectKeyIdentifier.from_public_key(public_key).digest


def _certificate(subject, issuer, public_key, signing_key, *, ca, aki):
    now = datetime.now(timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier(aki, None, None), critical=False,
        )
        .sign(signing_key, hashes.SHA256())
    )


def _ca_row(cert, label):
    ski = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier).value.digest
    return CA(
        refid=str(uuid4()),
        descr=label,
        crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        ski=ski.hex(':').upper(),
    )


def test_resolve_issuer_verifies_homonymous_ca_signature(app):
    name = _name('Homonymous export issuer')
    right_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    right = _certificate(name, name, right_key.public_key(), right_key, ca=True,
                         aki=_key_id(right_key.public_key()))
    wrong = _certificate(name, name, wrong_key.public_key(), wrong_key, ca=True,
                         aki=_key_id(wrong_key.public_key()))
    leaf = _certificate(_name('leaf.example.test'), name, leaf_key.public_key(), right_key,
                        ca=False, aki=_key_id(right_key.public_key()))

    with app.app_context():
        rows = [_ca_row(wrong, 'wrong same-DN CA'), _ca_row(right, 'real issuer CA')]
        # Imported CAs may persist SKI without UCM's usual separators/casing.
        rows[1].ski = rows[1].ski.replace(':', '').lower()
        db.session.add_all(rows)
        db.session.commit()
        try:
            resolved = _resolve_issuer_cert(leaf)
            assert resolved is not None
            assert resolved.fingerprint(hashes.SHA256()) == right.fingerprint(hashes.SHA256())
        finally:
            for row in rows:
                db.session.delete(row)
            db.session.commit()


def test_excluding_root_keeps_self_issued_cross_certificate(app):
    shared_name = _name('Rollover CA')
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rollover_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root = _certificate(shared_name, shared_name, root_key.public_key(), root_key, ca=True,
                        aki=_key_id(root_key.public_key()))
    # Same subject and issuer DN, but signed by the previous key: self-issued,
    # not self-signed, and therefore not a trust anchor.
    rollover = _certificate(
        shared_name, shared_name, rollover_key.public_key(), root_key, ca=True,
        aki=_key_id(root_key.public_key()),
    )
    leaf = _certificate(
        _name('rollover-leaf.example.test'), shared_name, leaf_key.public_key(),
        rollover_key, ca=False, aki=_key_id(rollover_key.public_key()),
    )

    with app.app_context():
        row = _ca_row(root, 'rollover trust anchor')
        db.session.add(row)
        db.session.commit()
        try:
            inline = (
                leaf.public_bytes(serialization.Encoding.PEM)
                + rollover.public_bytes(serialization.Encoding.PEM)
            )
            chain = _build_ca_chain(SimpleNamespace(caref=None), inline, include_root=False)
            assert [c.fingerprint(hashes.SHA256()) for c in chain] == [
                rollover.fingerprint(hashes.SHA256())
            ]
        finally:
            db.session.delete(row)
            db.session.commit()


def test_export_rejects_non_boolean_json_options(auth_client, create_cert):
    cert = create_cert(cn='strict-export-options.example.test')
    url = f'/api/v2/certificates/{cert["id"]}/export'
    for option in ('include_key', 'include_chain', 'include_root', 'legacy'):
        response = auth_client.post(url, json={
            'format': 'pem',
            option: 'false',
        })
        assert response.status_code == 400, (option, response.get_json())
        assert option in response.get_json()['message']
