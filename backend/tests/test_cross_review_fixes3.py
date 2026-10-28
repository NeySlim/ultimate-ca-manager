"""Third review pass on the cross-certificate chain consumers (#400)."""
import base64
from datetime import timedelta
from types import SimpleNamespace

import pytest

from cryptography.hazmat.primitives.serialization import Encoding

from models import CA, Certificate, CertificatePolicy, DeployBinding, db
from models.ca_cross_certificate import CACrossCertificate
from tests.fixtures.cross_world import build_world, set_served
from tests.test_cross_chain_paths import _der, _loads
from utils.datetime_utils import utc_now


@pytest.fixture
def world(app, auth_client):
    return build_world(app, auth_client)


def _export(client, w, **body):
    return client.post(f'/api/v2/cas/{w.b_id}/export', json=body)


@pytest.mark.parametrize('fmt', ['der', 'pem'])
def test_a_default_ca_export_keeps_the_self_signed_certificate_though_a_cross_is_served(auth_client, world, fmt):
    set_served(auth_client, world, True)
    r = _export(auth_client, world, format=fmt, include_chain=True)
    assert r.status_code == 200, r.data
    if fmt == 'der':
        assert r.data == _der(world.pki.root_b)
    else:
        assert [_der(c) for c in _loads(r.data)] == [_der(world.pki.root_b)]


def test_a_pkcs12_ca_export_keeps_the_self_signed_certificate(app, auth_client, world):
    from cryptography.hazmat.primitives.serialization import pkcs12
    from tests.fixtures.cross_pki import key_pem
    from utils.key_codec import store_pem_bytes
    with app.app_context():
        db.session.get(CA, world.b_id).prv = store_pem_bytes(key_pem(world.pki.key_b).encode())
        db.session.commit()
    set_served(auth_client, world, True)
    r = _export(auth_client, world, format='pkcs12', include_chain=True, include_key=True, password='Sup3r-secret-pw!')
    assert r.status_code == 200, r.data
    _key, cert, _extra = pkcs12.load_key_and_certificates(r.data, b'Sup3r-secret-pw!')
    assert _der(cert) == _der(world.pki.root_b)


def test_an_explicit_variant_still_swaps_the_ca_certificate(auth_client, world):
    r = _export(auth_client, world, format='der', include_chain=True, chain_variant=f'cross:{world.xid}')
    assert r.data == _der(world.pki.cross_b)


def test_the_chain_status_stays_complete_when_the_cross_issuer_is_not_held(app, auth_client, world):
    set_served(auth_client, world, True)
    with app.app_context():
        db.session.delete(db.session.get(CA, world.a_id))
        db.session.commit()
    status = auth_client.get(f'/api/v2/certificates/{world.leaf_id}').get_json()['data']['chain_status']
    assert status['status'] == 'complete'
    assert status['trust_anchor'] == world.pki.name_b


def _revoke(client, w):
    r = client.post(f'/api/v2/cas/{w.b_id}/cross-certificates/{w.xid}/revoke', json={'reason': 'keyCompromise'})
    assert r.status_code == 200, r.data


def test_a_binding_refuses_a_revoked_cross_certificate(auth_client, world):
    from tests.test_cross_chain_variant import _binding
    _revoke(auth_client, world)
    assert _binding(auth_client, world, chain_variant=f'cross:{world.xid}').status_code == 400


def test_a_binding_whose_cross_certificate_was_revoked_fails_instead_of_pushing_it(app, auth_client, world):
    from services.deploy.service import DeployService
    from utils.ca_chain import ChainVariantError
    _revoke(auth_client, world)
    with app.app_context():
        binding = DeployBinding(fullchain_path='/srv/fullchain.pem', include_root=True,
                                chain_variant=f'cross:{world.xid}')
        with pytest.raises(ChainVariantError):
            DeployService.resolve_files(binding, db.session.get(Certificate, world.leaf_id))


def test_a_cross_certificate_not_yet_valid_is_neither_served_nor_presented(app, auth_client, world):
    with app.app_context():
        db.session.get(CACrossCertificate, world.xid).valid_from = utc_now() + timedelta(days=200)
        db.session.commit()
    r = auth_client.patch(f'/api/v2/cas/{world.b_id}/cross-certificates/{world.xid}', json={'served': True})
    assert r.status_code == 409, r.data
    with app.app_context():
        from utils.ca_chain import issuer_chain
        row = db.session.get(CACrossCertificate, world.xid)
        row.served = True
        db.session.commit()
        assert all(link.cross is None for link in issuer_chain(db.session.get(CA, world.int_id)))


# --- approval scope over the records of one key ---------------------------------------------------------------

@pytest.fixture
def sibling_records(app, world):
    """Root B's cross-signed record Bx beside the self-signed record; a policy on the latter."""
    with app.app_context():
        a = db.session.get(CA, world.a_id)
        bs = db.session.get(CA, world.b_id)
        bx = CA(refid='bx-' + world.pki.tag, descr='Bx ' + world.pki.tag,
                subject=world.pki.cross_b.subject.rfc4514_string(),
                issuer=world.pki.cross_b.issuer.rfc4514_string(), caref=a.refid,
                crt=base64.b64encode(world.pki.cross_b.public_bytes(Encoding.PEM)).decode())
        db.session.add(bx)
        policy = CertificatePolicy(name='sib-' + world.pki.tag, ca_id=bs.id, requires_approval=True,
                                   min_approvers=1, is_active=True, priority=100)
        policy.set_rules({})
        policy.set_operations(['revocation'])
        db.session.add(policy)
        db.session.commit()
        yield SimpleNamespace(bx_id=bx.id, policy_id=policy.id)
        db.session.delete(db.session.get(CertificatePolicy, policy.id))
        db.session.delete(db.session.get(CA, bx.id))
        db.session.commit()


def test_a_revocation_policy_on_the_self_signed_record_governs_a_certificate_under_its_sibling(
        app, world, sibling_records):
    from services.approval_gate import revocation_policy_for
    with app.app_context():
        leaf = db.session.get(Certificate, world.leaf_id)
        leaf.caref = db.session.get(CA, sibling_records.bx_id).refid
        policy = revocation_policy_for(leaf)
        assert policy is not None and policy.id == sibling_records.policy_id
        db.session.rollback()


def test_a_ca_revocation_is_held_by_the_policy_on_the_sibling_record_of_its_parent(app, world, sibling_records):
    from services.approval_gate import queue_ca_revocation
    with app.app_context():
        parent = db.session.get(CA, sibling_records.bx_id)
        child = db.session.get(CA, world.int_id)
        policy, approval = queue_ca_revocation(SimpleNamespace(role='operator', id=None), child, parent,
                                               reason='keyCompromise')
        assert policy is not None and policy.id == sibling_records.policy_id
        db.session.rollback()
