"""A deploy binding pinned to a cross-certificate follows it through a restore (#400).

Cross-certificates are renumbered on restore; the binding's `cross:<id>` is found
again through the certificate's fingerprint, or falls back to `auto`.
"""
import logging

import pytest
from cryptography.hazmat.primitives import hashes

from models import db, CA
from models.ca_cross_certificate import CACrossCertificate
from models.deploy import DeployBinding, DeployTarget
from services.backup import manifest

PASSWORD = 'Correct-Horse-Battery-9'


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    return {name: name in names for name in manifest.SECTIONS}


def _fingerprint(cert):
    return cert.fingerprint(hashes.SHA256()).hex()


@pytest.fixture
def pinned(app, auth_client, create_cert):
    """A binding pinned to the second of two cross-certificates, after the first was detached."""
    from services.ca import cross_certs
    from tests.fixtures.cross_pki import build_cross_pki, make_cert, new_key, pem
    pki = build_cross_pki()
    key_c = new_key()
    first = make_cert(pki.root_b.subject.rfc4514_string().split('=', 1)[1], pki.key_b,
                      f'Cross Root C {pki.tag}', key_c, days=300)
    cert = create_cert()
    with app.app_context():
        for root in (pki.root_a, pki.root_b):
            r = auth_client.post('/api/v2/cas/import', data={'pem_content': pem(root)},
                                 content_type='multipart/form-data')
            assert r.status_code in (200, 201), r.data
        ca = CA.query.filter(CA.subject == pki.root_b.subject.rfc4514_string()).first()
        hole, _ = cross_certs.attach_certificate(ca, first, 'test')
        row, _ = cross_certs.attach_certificate(ca, pki.cross_b, 'test')
        cross_certs.detach(hole)
        target = DeployTarget(name=f'cv-target-{pki.tag}', host='h.example', username='u', private_key='k')
        db.session.add(target)
        db.session.commit()
        binding = DeployBinding(target_id=target.id, certificate_id=cert['id'],
                                chain_variant=f'cross:{row.id}')
        db.session.add(binding)
        db.session.commit()
        state = {'target': target.id, 'cert': cert['id'], 'cross_id': row.id,
                 'fingerprint': _fingerprint(pki.cross_b), 'ca': ca.id}
    yield state
    with app.app_context():
        DeployBinding.query.filter_by(target_id=state['target']).delete()
        DeployTarget.query.filter_by(id=state['target']).delete()
        db.session.commit()


def _binding(state):
    return DeployBinding.query.filter_by(target_id=state['target'], certificate_id=state['cert']).one()


def _backup(app):
    return _service().create_backup(PASSWORD, include=_only(
        'certificate_authorities', 'certificates', 'deploy_targets', 'deploy_bindings', 'ca_cross_certificates'))


def test_binding_follows_its_cross_certificate_to_the_new_id(app, pinned):
    with app.app_context():
        blob = _backup(app)
        CACrossCertificate.query.filter_by(id=pinned['cross_id']).delete()
        _binding(pinned).chain_variant = 'auto'
        db.session.commit()
        _service().restore_backup(blob, PASSWORD)
        db.session.expire_all()
        restored = CACrossCertificate.query.filter_by(fingerprint_sha256=pinned['fingerprint']).one()
        assert restored.id != pinned['cross_id'], 'the test needs the id to move'
        assert _binding(pinned).chain_variant == f'cross:{restored.id}'


def test_binding_without_its_cross_certificate_falls_back_to_auto(app, pinned, caplog):
    with app.app_context():
        blob = _service().create_backup(PASSWORD, include=_only(
            'certificate_authorities', 'certificates', 'deploy_targets', 'deploy_bindings'))
        CACrossCertificate.query.filter_by(id=pinned['cross_id']).delete()
        db.session.commit()
        with caplog.at_level(logging.WARNING):
            _service().restore_backup(blob, PASSWORD)
        db.session.expire_all()
        assert _binding(pinned).chain_variant == 'auto'
        assert any('chain_variant' in r.getMessage() for r in caplog.records)


def test_other_variants_are_restored_as_they_are(app, pinned):
    with app.app_context():
        _binding(pinned).chain_variant = 'primary'
        db.session.commit()
        blob = _backup(app)
        _binding(pinned).chain_variant = 'auto'
        db.session.commit()
        _service().restore_backup(blob, PASSWORD)
        db.session.expire_all()
        assert _binding(pinned).chain_variant == 'primary'
