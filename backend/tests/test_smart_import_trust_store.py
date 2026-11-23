"""Smart import finds the issuer of an incomplete chain in the trust store, through the
application's database (SQLite or PostgreSQL), whatever file the database lives in."""
import hashlib

import pytest
from cryptography.hazmat.primitives import serialization

from models import db
from models.truststore import TrustedCertificate
from services.smart_import.chain_builder import ChainBuilder
from services.smart_import.parser import SmartParser
from services.smart_import.validator import ImportValidator
from tests.fixtures.cross_pki import build_cross_pki, make_cert, new_key, pem


def _trust(cert, name, subject):
    der = cert.public_bytes(serialization.Encoding.DER)
    row = TrustedCertificate(name=name, certificate_pem=pem(cert), subject=subject,
                             fingerprint_sha256=hashlib.sha256(der).hexdigest(),
                             purpose='root_ca')
    db.session.add(row)
    db.session.commit()
    return row


def _validate(*certs):
    objects = SmartParser().parse(''.join(pem(c) for c in certs))
    chains = ChainBuilder().build_chains(objects)
    result = ImportValidator().validate_all(objects, chains, check_duplicates=False)
    return result, chains


@pytest.mark.parametrize('stored_subject', ['exact', 'name_only'])
def test_the_issuer_of_an_incomplete_chain_is_found_in_the_trust_store(app, stored_subject):
    pki = build_cross_pki()
    with app.app_context():
        # 'name_only': no subject stored, found by the issuer's CN in the name
        subject = pki.root_b.subject.rfc4514_string() if stored_subject == 'exact' else None
        row = _trust(pki.root_b, f'Trusted {pki.name_b}', subject)
        try:
            result, chains = _validate(pki.leaf, pki.int_b)
            chain = next(c for c in chains if c.leaf is not None)
            assert chain.trust_source == 'trust_store', result.to_dict()
            assert chain.trust_anchor == row.name and chain.is_complete
            assert any('verified against Trust Store' in i for i in result.infos), result.infos
            assert not any('not found in managed CAs or Trust Store' in w for w in result.warnings)
        finally:
            db.session.delete(row)
            db.session.commit()


def test_a_trusted_certificate_that_did_not_sign_the_chain_is_not_its_anchor(app):
    pki = build_cross_pki()
    # Same name as the real issuer, another key: neither its SKI nor its signature matches
    impostor = make_cert(pki.name_b, new_key())
    with app.app_context():
        row = _trust(impostor, f'Trusted {pki.name_b}', impostor.subject.rfc4514_string())
        try:
            result, chains = _validate(pki.leaf, pki.int_b)
            chain = next(c for c in chains if c.leaf is not None)
            assert chain.trust_source is None and chain.trust_anchor is None
            assert any('not found in managed CAs or Trust Store' in w for w in result.warnings)
        finally:
            db.session.delete(row)
            db.session.commit()
