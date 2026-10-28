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


def test_children_of_a_root_link_to_its_self_signed_record(app, pki):
    """With the root and its cross-certificate both stored, an issued CA and a leaf hang under the root."""
    from tests.fixtures.cross_pki import make_cert, new_key
    int_key, leaf_key = new_key(), new_key()
    int_c = make_cert(f'Direct Int {pki.tag}', int_key, pki.name_b, pki.key_b)
    leaf = make_cert(f'direct-{pki.tag}.example', leaf_key, pki.name_b, pki.key_b, ca=False)
    with app.app_context():
        SmartImporter().execute(_bundle(pki.root_a, pki.cross_b))
        SmartImporter().execute(_bundle(pki.root_b))
        rows = _rows(pki.name_b)
        assert len(rows) == 2
        root = next(r for r, c in rows if c.subject == c.issuer)
        SmartImporter().execute(_bundle(int_c))
        SmartImporter().execute(_bundle(leaf))
        assert CA.query.filter_by(descr=f'Direct Int {pki.tag}').one().caref == root.refid
        from models import Certificate
        assert Certificate.query.filter(Certificate.descr.contains(f'direct-{pki.tag}')).one().caref == root.refid


@pytest.mark.parametrize('order', ['root_first', 'cross_first'])
def test_cross_certificate_record_is_linked_to_its_issuing_root(app, pki, order):
    certs = [pki.root_a, pki.cross_b] if order == 'root_first' else [pki.cross_b, pki.root_a]
    with app.app_context():
        result = SmartImporter().execute(_bundle(*certs))
        assert result.success, result.errors
        cross = _rows(pki.name_b)[0][0]
        assert cross.caref == _rows(pki.name_a)[0][0].refid
