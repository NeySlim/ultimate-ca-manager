"""Smart import keeps a root and its cross certificate apart, whatever the file order (#400)."""
import base64

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes

from models import CA, db
from services.smart_import.chain_builder import ChainBuilder
from services.smart_import.importer import SmartImporter
from services.smart_import.parser import SmartParser
from tests.fixtures.cross_pki import build_cross_pki, pem


def _bundle(*certs):
    return ''.join(pem(c) for c in certs)


def _rows(name):
    rows = CA.query.filter(CA.descr == name).all()
    return [(r, x509.load_pem_x509_certificate(base64.b64decode(r.crt))) for r in rows]


@pytest.fixture
def pki():
    return build_cross_pki()


@pytest.mark.parametrize('order', ['root_first', 'cross_first'])
@pytest.mark.parametrize('skip_duplicates', [True, False])
def test_bundle_keeps_the_self_signed_root_only(app, pki, order, skip_duplicates):
    certs = [pki.root_a, pki.root_b, pki.cross_b]
    if order == 'cross_first':
        certs = [pki.root_a, pki.cross_b, pki.root_b]
    with app.app_context():
        result = SmartImporter().execute(_bundle(*certs), options={'skip_duplicates': skip_duplicates})
        assert result.success, result.errors
        rows = _rows(pki.name_b)
        assert len(rows) == 1, 'the cross certificate became a second record'
        record, stored = rows[0]
        assert stored.fingerprint(hashes.SHA256()) == pki.root_b.fingerprint(
            hashes.SHA256())
        assert record.caref is None
        codes = [w['code'] for w in result.to_dict()['warning_details']]
        assert codes == ['cross_certificate_skipped']


def test_cross_certificate_alone_is_skipped_against_a_stored_root(app, pki):
    with app.app_context():
        SmartImporter().execute(_bundle(pki.root_a, pki.root_b))
        before = _rows(pki.name_b)[0][0].crt
        result = SmartImporter().execute(_bundle(pki.cross_b), options={'skip_duplicates': False})
        rows = _rows(pki.name_b)
        assert len(rows) == 1 and rows[0][0].crt == before
        assert [w['code'] for w in result.to_dict()['warning_details']] == ['cross_certificate_skipped']


def test_self_signed_root_is_imported_when_only_its_cross_certificate_is_stored(app, pki):
    with app.app_context():
        SmartImporter().execute(_bundle(pki.root_a, pki.cross_b))
        assert len(_rows(pki.name_b)) == 1
        result = SmartImporter().execute(_bundle(pki.root_b))
        assert result.success, result.errors
        fingerprints = {c.fingerprint(hashes.SHA256()) for _, c in _rows(pki.name_b)}
        assert pki.root_b.fingerprint(hashes.SHA256()) in fingerprints


@pytest.mark.parametrize('order', ['root_first', 'cross_first'])
def test_chain_of_a_leaf_ends_on_the_self_signed_root(pki, order):
    certs = [pki.leaf, pki.int_b, pki.root_b, pki.cross_b, pki.root_a]
    if order == 'cross_first':
        certs = [pki.leaf, pki.int_b, pki.cross_b, pki.root_b, pki.root_a]
    objects = SmartParser().parse(_bundle(*certs))
    chains = ChainBuilder().build_chains(objects)
    assert len(chains) == 1
    root = chains[0].root
    assert root is not None and root.is_self_signed
    assert str(root.serial_number) == str(pki.root_b.serial_number)
