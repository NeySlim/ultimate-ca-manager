"""The OPNsense import writes under DATA_DIR only, and a start repairs what it left in the code tree."""
import base64
import uuid
from pathlib import Path

import pytest

from config.settings import BACKEND_DIR, Config
from models import CA, Certificate, db
from tests.fixtures.cross_pki import key_pem, make_cert, new_key, pem
from utils.file_naming import ca_cert_path, ca_key_path, cert_cert_path, cert_key_path

TREE_DIRS = tuple(BACKEND_DIR / 'data' / sub for sub in ('ca', 'certs', 'private'))


def _files(dirs):
    return {p for d in dirs if d.is_dir() for p in d.iterdir()}


@pytest.fixture
def plaintext_mirrors(monkeypatch):
    from security.encryption import key_encryption
    monkeypatch.setattr(key_encryption, '_enabled', False)


@pytest.fixture(autouse=True)
def _forget_rows(app):
    with app.app_context():
        cas = {c.id for c in CA.query.all()}
        certs = {c.id for c in Certificate.query.all()}
    yield
    with app.app_context():
        db.session.rollback()
        for model, before in ((Certificate, certs), (CA, cas)):
            for row in model.query.filter(~model.id.in_(before)).all():
                db.session.delete(row)
        db.session.commit()


def _pair(tag):
    ca_key, leaf_key = new_key(), new_key()
    ca = make_cert(f'OPN data CA {tag}', ca_key)
    leaf = make_cert(f'opn-data-{tag}.example.test', leaf_key, f'OPN data CA {tag}', ca_key, ca=False)
    return ca, ca_key, leaf, leaf_key


def _b64(text):
    return base64.b64encode(text.encode()).decode()


def test_opnsense_import_writes_canonical_files_under_data_dir_only(app, plaintext_mirrors):
    from services.opnsense.importer import ImportMixin
    tag = uuid.uuid4().hex[:8]
    ca, ca_key, leaf, leaf_key = _pair(tag)
    ca_refid, cert_refid = uuid.uuid4().hex[:13], uuid.uuid4().hex[:13]
    tree_before = _files(TREE_DIRS)
    assert Path(Config.DATA_DIR).resolve() != (BACKEND_DIR / 'data').resolve()
    try:
        with app.app_context():
            assert ImportMixin().import_cas([{
                'refid': ca_refid, 'descr': f'opn ca {tag}', 'is_root': True,
                'crt': _b64(pem(ca)), 'prv': _b64(key_pem(ca_key)),
                'subject': ca.subject.rfc4514_string(), 'issuer': ca.issuer.rfc4514_string(),
            }])['imported'] == 1
            assert ImportMixin().import_certificates([{
                'refid': cert_refid, 'caref': ca_refid, 'descr': f'opn leaf {tag}',
                'crt': _b64(pem(leaf)), 'prv': _b64(key_pem(leaf_key)),
            }])['imported'] == 1
            ca_row = CA.query.filter_by(refid=ca_refid).one()
            cert_row = Certificate.query.filter_by(refid=cert_refid).one()
            # The same files, at the same paths, as any other CA or certificate
            assert ca_cert_path(ca_row).read_bytes() == pem(ca).encode()
            assert ca_key_path(ca_row).read_bytes() == key_pem(ca_key).encode()
            assert cert_cert_path(cert_row).read_bytes() == pem(leaf).encode()
            assert cert_key_path(cert_row).read_bytes() == key_pem(leaf_key).encode()
            for directory in (Config.CA_DIR, Config.CERT_DIR, Config.PRIVATE_DIR):
                assert not any(p.name.startswith((ca_refid, cert_refid))
                               for p in Path(directory).iterdir())
    finally:
        created = _files(TREE_DIRS) - tree_before
        for path in created:
            path.unlink()
    assert created == set(), 'the import wrote into the code tree'
