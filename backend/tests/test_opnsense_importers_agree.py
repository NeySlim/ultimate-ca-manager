"""Both OPNsense importers store a key the same way (DUP-PKI-015).

UCM carries two importers for the same appliance data. The live one is the
``/api/v2/import/opnsense/*`` blueprint the Operations page calls. The other,
``services/opnsense/`` behind the ``services/opnsense_import`` shim, is
reachable from no route, no worker and no command — only from a test — and it
assigned the appliance's base64 PEM straight to ``prv``, so the same key was
encrypted at rest through one importer and readable through the other.

The service was left in place: a test still exercises it (the key-mirror rule
from the plaintext-key-files work), so the evidence of death is incomplete and
removing it would take that regression test with it. What it can no longer do
is store a private key in the clear.
"""
import base64
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from models import db, CA, Certificate

CERT_B64 = base64.b64encode(
    b'-----BEGIN CERTIFICATE-----\nnot-a-real-cert\n-----END CERTIFICATE-----'
).decode()


@pytest.fixture
def appliance_row():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    return base64.b64encode(pem).decode(), pem


def test_the_legacy_service_encrypts_like_the_route(
    app, encryption_enabled, appliance_row, monkeypatch, tmp_path
):
    from api.v2.import_opnsense import _encoded_private_key
    from security.encryption import decrypt_private_key
    from services.opnsense import importer

    encoded_key, plain_pem = appliance_row
    ca_refid = str(uuid.uuid4())
    cert_refid = str(uuid.uuid4())
    row = {'crt': CERT_B64, 'prv': encoded_key, 'descr': 'OPNsense import'}

    through_the_route = _encoded_private_key(dict(row))

    with app.app_context():
        assert importer.ImportMixin().import_cas(
            [dict(row, refid=ca_refid, is_root=True)])['imported'] == 1
        assert importer.ImportMixin().import_certificates(
            [dict(row, refid=cert_refid)])['imported'] == 1
        try:
            ca_prv = CA.query.filter_by(refid=ca_refid).first().prv
            cert_prv = Certificate.query.filter_by(refid=cert_refid).first().prv

            for stored in (ca_prv, cert_prv):
                # Same wire format as the route: base64("ENC:" + token).
                assert base64.b64decode(stored).startswith(b'ENC:')
                assert base64.b64decode(stored) != plain_pem
                # And still readable: the column round-trips to the key.
                assert base64.b64decode(decrypt_private_key(stored)) == plain_pem

            assert base64.b64decode(through_the_route).startswith(b'ENC:')
        finally:
            CA.query.filter_by(refid=ca_refid).delete()
            Certificate.query.filter_by(refid=cert_refid).delete()
            db.session.commit()


def test_a_row_without_a_key_still_imports(app, monkeypatch, tmp_path):
    """OPNsense exports plenty of certificates it holds no key for."""
    from services.opnsense import importer

    refid = str(uuid.uuid4())
    with app.app_context():
        result = importer.ImportMixin().import_certificates(
            [{'refid': refid, 'descr': 'Keyless', 'crt': CERT_B64}])
        try:
            assert result['imported'] == 1
            assert Certificate.query.filter_by(refid=refid).first().prv is None
        finally:
            Certificate.query.filter_by(refid=refid).delete()
            db.session.commit()


def test_the_legacy_service_is_still_reachable_from_nothing_but_tests():
    """The reason it was kept rather than deleted — recheck it, don't assume."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    callers = []
    for path in root.rglob('*.py'):
        parts = path.parts
        if '__pycache__' in parts or 'tests' in parts:
            continue
        if path.name == 'opnsense_import.py' or 'opnsense' in path.parent.name:
            continue  # the package itself and its backward-compat shim
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, 'module', '') or ''
                names = [a.name for a in node.names]
                if 'opnsense_import' in module or 'services.opnsense' in module \
                        or any('OPNsenseImportService' in n for n in names):
                    callers.append(f'{path.relative_to(root)}:{node.lineno}')
    assert callers == [], (
        'a production caller appeared: the deletion decision can be revisited, '
        'and until then this importer must keep matching the route: ' + ', '.join(callers)
    )
