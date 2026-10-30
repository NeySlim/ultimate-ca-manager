"""Policy rules on key types and signature hashes, on every issuance path (#397).

``allowed_digests`` restricts the signature hash; a hash nobody chose yields to
the weakest allowed one, a chosen one is refused. Key types and hashes now bind
CSR signing, ACME, EST, WSTEP, SCEP, CA creation, renewals, mTLS, TSA and OCSP
responder certificates, and an Ed25519 key no longer slips past the key list.
"""
import base64
import json
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, mldsa, rsa
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db
from models.certificate_template import CertificateTemplate
from models.policy import CertificatePolicy
from services.policy_service import (PolicyEvaluationService, PolicyViolation,
                                     key_label_for_public_key)
from tests.conftest import get_json

CONTENT_JSON = 'application/json'


def _policy(app, name, ca_id=None, rules=None, template_id=None):
    with app.app_context():
        pol = CertificatePolicy(name=name, policy_type='issuance', ca_id=ca_id,
                                template_id=template_id, requires_approval=False,
                                min_approvers=1, is_active=True, priority=100)
        pol.set_rules(rules or {})
        db.session.add(pol)
        db.session.commit()
        return pol.id


def _drop(app, model, *ids):
    with app.app_context():
        for row_id in ids:
            row = db.session.get(model, row_id)
            if row is not None:
                db.session.delete(row)
        db.session.commit()


def _pol(rules, name='p'):
    pol = CertificatePolicy(name=name)
    pol.set_rules(rules)
    return pol


def _csr(key=None, cn='algo.policy.test'):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    algorithm = None if isinstance(key, ed25519.Ed25519PrivateKey) else hashes.SHA256()
    return (x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
            .sign(key, algorithm))


def _store_csr(app, csr, descr='algo-csr'):
    with app.app_context():
        row = Certificate(refid=str(uuid.uuid4()), descr=descr,
                          csr=base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode(),
                          source='manual')
        db.session.add(row)
        db.session.commit()
        return row.id


def _signed(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        return x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend())


class TestRuleHelpers:

    def test_digest_rule_refuses_and_names_the_policy(self):
        pol = _pol({'allowed_digests': ['SHA-384', 'sha512']}, 'strong-only')
        v, _, _ = PolicyEvaluationService.enforce_rules([pol], digest='sha256')
        assert len(v) == 1 and 'SHA256' in v[0] and 'strong-only' in v[0] and 'SHA384' in v[0]
        assert PolicyEvaluationService.enforce_rules([pol], digest=hashes.SHA384())[0] == []
        # No hash (Ed25519 signer) is not checked
        assert PolicyEvaluationService.enforce_rules([pol], digest=None)[0] == []

    def test_implicit_digest_takes_the_weakest_allowed_by_all(self):
        a = _pol({'allowed_digests': ['sha384', 'sha512']}, 'a')
        b = _pol({'allowed_digests': ['sha512']}, 'b')
        assert PolicyEvaluationService.choose_digest([], 'sha256') == 'sha256'
        assert PolicyEvaluationService.choose_digest([a], 'sha256') == 'sha384'
        assert PolicyEvaluationService.choose_digest([a], 'sha512') == 'sha512'
        assert PolicyEvaluationService.choose_digest([a, b], 'sha256') == 'sha512'

    def test_explicit_digest_is_checked_not_replaced(self):
        pol = _pol({'allowed_digests': ['sha384']})
        key = ec.generate_private_key(ec.SECP256R1())
        sign_hash, v = PolicyEvaluationService.checked_signing_hash([pol], key, 'sha256')
        assert sign_hash.name == 'sha256' and len(v) == 1
        sign_hash, v = PolicyEvaluationService.checked_signing_hash(
            [pol], key, 'sha256', explicit=False)
        assert sign_hash.name == 'sha384' and v == []

    @pytest.mark.parametrize('make_key', [ed25519.Ed25519PrivateKey.generate, mldsa.MLDSA65PrivateKey.generate])
    @pytest.mark.parametrize('explicit', [True, False])
    def test_a_key_without_digest_signs_with_none_when_none_is_asked(self, make_key, explicit):
        pol = _pol({'allowed_digests': ['sha384']})
        assert PolicyEvaluationService.checked_signing_hash(
            [pol], make_key(), None, explicit=explicit) == (None, [])

    def test_every_key_gets_a_label(self):
        assert key_label_for_public_key(
            rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()) == 'RSA-2048'
        assert key_label_for_public_key(ec.generate_private_key(ec.SECP384R1()).public_key()) == 'EC-P384'
        assert key_label_for_public_key(ed25519.Ed25519PrivateKey.generate().public_key()) == 'ED25519'
        pol = _pol({'allowed_key_types': ['RSA-2048']})
        v, _, _ = PolicyEvaluationService.enforce_rules([pol], key_type='ED25519')
        assert len(v) == 1 and 'ED25519' in v[0]


class TestPolicyApi:

    def test_rules_are_validated_and_normalised(self, app, auth_client):
        r = auth_client.post('/api/v2/policies', data=json.dumps({
            'name': 'algo-bad-digest', 'rules': {'allowed_digests': ['md5']}}),
            content_type=CONTENT_JSON)
        assert r.status_code == 400 and b'md5' in r.data
        r = auth_client.post('/api/v2/policies', data=json.dumps({
            'name': 'algo-bad-key', 'rules': {'allowed_key_types': ['DSA-1024']}}),
            content_type=CONTENT_JSON)
        assert r.status_code == 400 and b'DSA-1024' in r.data
        r = auth_client.post('/api/v2/policies', data=json.dumps({
            'name': 'algo-normalised', 'is_active': False,
            'rules': {'allowed_digests': ['SHA-384'], 'allowed_key_types': ['rsa:4096', 'ed25519']}}),
            content_type=CONTENT_JSON)
        assert r.status_code in (200, 201), r.data
        data = get_json(r)['data']
        try:
            assert data['rules']['allowed_digests'] == ['sha384']
            assert data['rules']['allowed_key_types'] == ['RSA-4096', 'ED25519']
            # A refused update changes nothing, the name included
            r = auth_client.put(f"/api/v2/policies/{data['id']}", data=json.dumps({
                'name': 'algo-renamed', 'rules': {'allowed_digests': ['sha1']}}),
                content_type=CONTENT_JSON)
            assert r.status_code == 400
            with app.app_context():
                assert db.session.get(CertificatePolicy, data['id']).name == 'algo-normalised'
        finally:
            _drop(app, CertificatePolicy, data['id'])

    def test_effective_algorithms_intersect_the_policies_in_scope(self, app, auth_client, create_ca):
        ca = create_ca(cn='Algo effective CA')
        a = _policy(app, 'algo-eff-a', ca['id'], {'allowed_key_types': ['RSA-3072', 'EC-P384'],
                                                  'allowed_digests': ['sha384', 'sha512']})
        b = _policy(app, 'algo-eff-b', ca['id'], {'allowed_key_types': ['EC-P384', 'EC-P521']})
        # Narrowed by a DNS pattern: binds only some names, left out of the form
        c = _policy(app, 'algo-eff-c', ca['id'], {'allowed_digests': ['sha512'],
                                                  'san_restrictions': {'dns_pattern': '.corp.test'}})
        try:
            r = auth_client.get(f"/api/v2/policies/effective?ca_id={ca['id']}")
            assert r.status_code == 200
            data = get_json(r)['data']
            assert (data['allowed_key_types'], data['allowed_digests']) == (
                ['EC-P384'], ['sha384', 'sha512'])
            other = create_ca(cn='Algo unrestricted CA')
            data = get_json(auth_client.get(f"/api/v2/policies/effective?ca_id={other['id']}"))['data']
            assert (data['allowed_key_types'], data['allowed_digests']) == (None, None)
        finally:
            _drop(app, CertificatePolicy, a, b, c)


class TestOperatorPaths:

    def test_issue_form_default_digest_yields_template_digest_is_refused(
            self, app, auth_client, create_ca):
        ca = create_ca(cn='Algo issue CA')
        pid = _policy(app, 'algo-issue', ca['id'], {'allowed_digests': ['sha384']})
        with app.app_context():
            tpl = CertificateTemplate(name=f'algo-tpl-{uuid.uuid4().hex[:6]}', template_type='web_server',
                                      key_type='RSA-2048', digest='sha256', validity_days=90,
                                      extensions_template='{}')
            db.session.add(tpl)
            db.session.commit()
            tpl_id = tpl.id
        try:
            payload = {'cn': 'issue.algo.test', 'ca_id': ca['id'], 'key_type': 'rsa',
                       'key_size': 2048, 'validity_days': 90, 'cert_type': 'server'}
            r = auth_client.post('/api/v2/certificates', data=json.dumps(payload),
                                 content_type=CONTENT_JSON)
            assert r.status_code in (200, 201), r.data
            cert = _signed(app, get_json(r)['data']['id'])
            assert isinstance(cert.signature_hash_algorithm, hashes.SHA384)

            payload['template_id'] = tpl_id
            r = auth_client.post('/api/v2/certificates', data=json.dumps(payload),
                                 content_type=CONTENT_JSON)
            assert r.status_code == 400 and b'SHA256' in r.data and b'algo-issue' in r.data
        finally:
            _drop(app, CertificatePolicy, pid)
            _drop(app, CertificateTemplate, tpl_id)

    def test_sign_csr_takes_the_allowed_digest(self, app, auth_client, create_ca):
        ca = create_ca(cn='Algo sign CSR CA')
        pid = _policy(app, 'algo-csr', ca['id'], {'allowed_digests': ['sha512']})
        csr_id = _store_csr(app, _csr())
        try:
            r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', data=json.dumps({'ca_id': ca['id']}),
                                 content_type=CONTENT_JSON)
            assert r.status_code in (200, 201), r.data
            assert isinstance(_signed(app, csr_id).signature_hash_algorithm, hashes.SHA512)
        finally:
            _drop(app, CertificatePolicy, pid)

    def test_ed25519_csr_no_longer_bypasses_the_key_list(self, app, auth_client, create_ca):
        ca = create_ca(cn='Algo Ed25519 CA')
        pid = _policy(app, 'algo-ed', ca['id'], {'allowed_key_types': ['RSA-2048']})
        csr_id = _store_csr(app, _csr(ed25519.Ed25519PrivateKey.generate()))
        try:
            r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', data=json.dumps({'ca_id': ca['id']}),
                                 content_type=CONTENT_JSON)
            assert r.status_code == 400, r.data
            assert b'ED25519' in r.data
        finally:
            _drop(app, CertificatePolicy, pid)
            _drop(app, Certificate, csr_id)

    def test_renewal_takes_the_allowed_digest(self, app, create_ca):
        from services.cert.renewal import renew_certificate_in_place
        from services.cert_service import CertificateService
        ca = create_ca(cn='Algo renewal CA')
        with app.app_context():
            ca_row = db.session.get(CA, ca['id'])
            row = CertificateService.create_certificate(
                descr='algo-renew', caref=ca_row.refid, dn={'CN': 'renew.algo.test'},
                cert_type='server_cert', validity_days=30)
            db.session.commit()
            cert_id = row.id
        pid = _policy(app, 'algo-renew', ca['id'], {'allowed_digests': ['sha384']})
        try:
            with app.app_context():
                renew_certificate_in_place(db.session.get(Certificate, cert_id))
            assert isinstance(_signed(app, cert_id).signature_hash_algorithm, hashes.SHA384)
        finally:
            _drop(app, CertificatePolicy, pid)

    def test_service_create_certificate_refuses_a_disallowed_key(self, app, create_ca):
        from services.cert_service import CertificateService
        ca = create_ca(cn='Algo mTLS CA')
        pid = _policy(app, 'algo-mtls', ca['id'], {'allowed_key_types': ['EC-P256']})
        try:
            with app.app_context():
                ca_row = db.session.get(CA, ca['id'])
                with pytest.raises(PolicyViolation, match='RSA-2048'):
                    CertificateService.create_certificate(
                        descr='algo-mtls', caref=ca_row.refid, dn={'CN': 'mtls.algo.test'},
                        cert_type='usr_cert', key_type='2048')
                db.session.rollback()
        finally:
            _drop(app, CertificatePolicy, pid)


class TestProtocolPaths:

    def test_est_bridge_honours_key_and_digest_rules(self, app, create_ca):
        from services.ca_service import CAService
        ca = create_ca(cn='Algo EST CA')
        pid = _policy(app, 'algo-est', ca['id'], {'allowed_key_types': ['RSA-2048'],
                                                  'allowed_digests': ['sha384']})
        try:
            with app.app_context():
                ca_row = db.session.get(CA, ca['id'])
                pem, _ = CAService.sign_csr_from_crypto(ca=ca_row, csr=_csr(), validity_days=30,
                                                        source='est')
                cert = x509.load_pem_x509_certificate(pem.encode())
                assert isinstance(cert.signature_hash_algorithm, hashes.SHA384)
                with pytest.raises(PolicyViolation, match='EC-P256'):
                    CAService.sign_csr_from_crypto(
                        ca=ca_row, csr=_csr(ec.generate_private_key(ec.SECP256R1())),
                        validity_days=30, source='est')
                db.session.rollback()
        finally:
            _drop(app, CertificatePolicy, pid)

    def test_acme_profile_digest_is_a_choice(self, app, create_ca):
        from services.cert_service import CertificateService
        ca = create_ca(cn='Algo ACME CA')
        pid = _policy(app, 'algo-acme', ca['id'], {'allowed_digests': ['sha384']})
        first = _store_csr(app, _csr(cn='acme1.algo.test'))
        second = _store_csr(app, _csr(cn='acme2.algo.test'))
        try:
            with app.app_context():
                ref = db.session.get(CA, ca['id']).refid
                CertificateService.sign_csr(cert_id=first, caref=ref, validity_days=30,
                                            digest='sha256', digest_explicit=False)
                db.session.commit()
                with pytest.raises(PolicyViolation, match='SHA256'):
                    CertificateService.sign_csr(cert_id=second, caref=ref, validity_days=30,
                                                digest='sha256', digest_explicit=True)
                db.session.rollback()
            assert isinstance(_signed(app, first).signature_hash_algorithm, hashes.SHA384)
        finally:
            _drop(app, CertificatePolicy, pid)
            _drop(app, Certificate, second)

    def test_acme_issuance_params_tell_default_from_choice(self, app):
        from models import SystemConfig
        from services.acme import profiles as acme_profiles
        with app.app_context():
            assert SystemConfig.query.filter_by(key=acme_profiles.DEFAULT_DIGEST_KEY).first() is None
            assert acme_profiles.issuance_params(None)['digest_explicit'] is False

    def test_scep_checks_the_profile_policies(self, app, create_ca):
        from services.scep.scep_service import SCEPService
        ca = create_ca(cn='Algo SCEP CA')
        pid = _policy(app, 'algo-scep', ca['id'], {'allowed_key_types': ['EC-P384'],
                                                   'allowed_digests': ['sha512']})
        try:
            with app.app_context():
                svc = SCEPService(db.session.get(CA, ca['id']).refid)
                sign_hash, v = svc._policy_signing_hash(_csr())
                assert sign_hash.name == 'sha512'
                assert len(v) == 1 and 'RSA-2048' in v[0]
                _, v = svc._policy_signing_hash(_csr(ec.generate_private_key(ec.SECP384R1())))
                assert v == []
        finally:
            _drop(app, CertificatePolicy, pid)


class TestCaCreation:

    def _create(self, auth_client, **extra):
        data = {'type': 'root', 'commonName': f'Algo CA {uuid.uuid4().hex[:6]}',
                'keyAlgo': 'RSA', 'keySize': 2048, 'validityYears': 5}
        data.update(extra)
        return auth_client.post('/api/v2/cas', data=json.dumps(data), content_type=CONTENT_JSON)

    def test_root_ca_follows_the_global_policies(self, app, auth_client):
        pid = _policy(app, 'algo-global', None, {'allowed_key_types': ['RSA-3072', 'EC-P384'],
                                                 'allowed_digests': ['sha384']})
        try:
            r = self._create(auth_client)
            assert r.status_code == 400 and b'RSA-2048' in r.data
            r = self._create(auth_client, keySize=3072, hashAlgorithm='sha256')
            assert r.status_code == 400 and b'SHA256' in r.data
            r = self._create(auth_client, keySize=3072, hashAlgorithm='auto')
            assert r.status_code in (200, 201), r.data
            with app.app_context():
                row = db.session.get(CA, get_json(r)['data']['id'])
                cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
            assert isinstance(cert.signature_hash_algorithm, hashes.SHA384)
        finally:
            _drop(app, CertificatePolicy, pid)

    def test_intermediate_follows_its_parent_policies(self, app, auth_client, create_ca):
        parent = create_ca(cn='Algo parent CA')
        pid = _policy(app, 'algo-parent', parent['id'], {'allowed_key_types': ['EC-P256']})
        try:
            r = self._create(auth_client, type='intermediate', parentCAId=parent['id'])
            assert r.status_code == 400 and b'algo-parent' in r.data
            # A root is outside that scope
            assert self._create(auth_client).status_code in (200, 201)
        finally:
            _drop(app, CertificatePolicy, pid)

    def test_refusal_comes_before_any_key_is_generated(self, app, auth_client, monkeypatch):
        # An HSM key would be created on the device by the time the real key is checked
        from services.ca.ca_creation import CACreationMixin

        def _no_key(*args, **kwargs):
            raise AssertionError('a key was generated for a refused CA')
        monkeypatch.setattr(CACreationMixin, '_resolve_signing_key', staticmethod(_no_key))
        pid = _policy(app, 'algo-before-key', None, {'allowed_key_types': ['EC-P384']})
        try:
            r = self._create(auth_client, type='external')
            assert r.status_code == 400 and b'algo-before-key' in r.data, r.data
            r = self._create(auth_client)
            assert r.status_code == 400 and b'algo-before-key' in r.data, r.data
        finally:
            _drop(app, CertificatePolicy, pid)


class TestInternalSigners:

    def test_tsa_signer_follows_the_policies(self, app, create_ca):
        from services.tsa_signer_cert import TsaSignerIssueError, issue_tsa_signer_certificate
        ca = create_ca(cn='Algo TSA CA')
        pid = _policy(app, 'algo-tsa', ca['id'], {'allowed_key_types': ['RSA-3072'],
                                                  'allowed_digests': ['sha512']})
        try:
            with app.app_context():
                ca_row = db.session.get(CA, ca['id'])
                with pytest.raises(TsaSignerIssueError, match='RSA-2048'):
                    issue_tsa_signer_certificate(ca=ca_row, key_type='RSA', key_size=2048)
                db.session.rollback()
                row = issue_tsa_signer_certificate(ca=ca_row, key_type='RSA', key_size=3072)
                cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
            assert isinstance(cert.signature_hash_algorithm, hashes.SHA512)
        finally:
            _drop(app, CertificatePolicy, pid)


class TestReviewFollowups:

    def test_parent_bound_hash_is_refused_before_a_key_exists(
            self, app, auth_client, create_ca, monkeypatch):
        # An HSM parent may sign with a hash bound to its key (Azure P-384 is SHA-384)
        from cryptography.hazmat.primitives import hashes as h
        from services.ca.ca_creation import CACreationMixin
        import utils.signing_hash

        def _no_key(*args, **kwargs):
            raise AssertionError('a key was generated for a refused CA')
        parent = create_ca(cn='Algo bound-hash parent')
        monkeypatch.setattr(CACreationMixin, '_resolve_signing_key', staticmethod(_no_key))
        monkeypatch.setattr(utils.signing_hash, 'signing_hash_for', lambda key, requested: h.SHA384())
        pid = _policy(app, 'algo-bound', parent['id'], {'allowed_digests': ['sha256']})
        try:
            r = TestCaCreation()._create(auth_client, type='intermediate', parentCAId=parent['id'],
                                         hashAlgorithm='sha256')
            assert r.status_code == 400 and b'SHA384' in r.data, r.data
        finally:
            _drop(app, CertificatePolicy, pid)

    def test_new_hsm_root_key_is_dropped_when_its_hash_is_refused(self, app, monkeypatch):
        from types import SimpleNamespace
        from cryptography.hazmat.primitives import hashes as h
        from services.ca.ca_creation import CACreationMixin
        from services.hsm import HsmService
        import utils.signing_hash
        key = ec.generate_private_key(ec.SECP384R1())
        monkeypatch.setattr(CACreationMixin, '_resolve_signing_key', staticmethod(
            lambda *a, **k: (key, None, SimpleNamespace(id=4242, label='algo-hsm'))))
        monkeypatch.setattr(utils.signing_hash, 'signing_hash_for', lambda k, requested: h.SHA384())
        dropped = []
        monkeypatch.setattr(HsmService, 'delete_key', classmethod(lambda cls, key_id: dropped.append(key_id)))
        pid = _policy(app, 'algo-hsm-root', None, {'allowed_digests': ['sha256']})
        try:
            with app.app_context():
                with pytest.raises(PolicyViolation, match='SHA384'):
                    CACreationMixin.create_internal_ca(
                        descr='algo hsm root', dn={'CN': 'algo hsm root'}, digest='sha256',
                        hsm_provider_id=1, hsm_key_label='algo-hsm', hsm_key_algorithm='EC-P384')
                db.session.rollback()
            assert dropped == [4242]
        finally:
            _drop(app, CertificatePolicy, pid)

    def test_scep_manual_approval_reports_a_policy_violation(self, app, auth_client, create_ca):
        from models import SCEPRequest
        ca = create_ca(cn='Algo SCEP approve CA')
        pid = _policy(app, 'algo-scep-approve', ca['id'], {'allowed_key_types': ['EC-P384']})
        with app.app_context():
            req = SCEPRequest(transaction_id=f'txn-algo-{uuid.uuid4().hex[:8]}',
                              ca_refid=db.session.get(CA, ca['id']).refid,
                              csr=base64.b64encode(_csr().public_bytes(serialization.Encoding.DER)).decode(),
                              status='pending', subject='CN=algo.policy.test')
            db.session.add(req)
            db.session.commit()
            req_id = req.id
        try:
            r = auth_client.post(f'/api/v2/scep/{req_id}/approve', data='{}', content_type=CONTENT_JSON)
            assert r.status_code == 400, r.data
            assert b'Policy violation' in r.data and b'RSA-2048' in r.data
        finally:
            _drop(app, CertificatePolicy, pid)
            _drop(app, SCEPRequest, req_id)

    def test_acme_policy_refusal_is_the_request_fault(self):
        from services.acme.mixins.issuance import IssuanceMixin
        exc = PolicyViolation('Key type RSA-2048 is not allowed by policy "HSM only"')
        assert IssuanceMixin._is_request_failure(exc) is True

    def test_legacy_unknown_key_labels_allow_nothing(self, app, create_ca):
        ca = create_ca(cn='Algo legacy labels CA')
        pid = _policy(app, 'algo-legacy', ca['id'], {'allowed_key_types': ['RSA', 'ECDSA']})
        try:
            with app.app_context():
                assert PolicyEvaluationService.effective_algorithms(ca['id']) == ([], None)
                policies = PolicyEvaluationService.applicable_policies(ca['id'])
                v, _, _ = PolicyEvaluationService.enforce_rules(
                    policies, key_type='RSA-2048', notify=False)
                assert len(v) == 1 and 'no known key type' in v[0] and 'algo-legacy' in v[0]
        finally:
            _drop(app, CertificatePolicy, pid)

    def test_bulk_sign_reports_a_policy_violation(self, app, auth_client, create_ca):
        ca = create_ca(cn='Algo bulk CA')
        pid = _policy(app, 'algo-bulk', ca['id'], {'allowed_key_types': ['RSA-2048'],
                                                   'allowed_digests': ['sha384']})
        csr_id = _store_csr(app, _csr(cn='bulk.algo.test'))
        ed_id = _store_csr(app, _csr(ed25519.Ed25519PrivateKey.generate(), cn='bulk-ed.algo.test'))
        try:
            r = auth_client.post('/api/v2/csrs/bulk/sign', content_type=CONTENT_JSON,
                                 data=json.dumps({'ids': [csr_id, ed_id], 'ca_id': ca['id']}))
            assert r.status_code == 200, r.data
            data = get_json(r)['data']
            assert data['success'] == [csr_id]
            assert [f['id'] for f in data['failed']] == [ed_id]
            assert 'Policy violation' in data['failed'][0]['error'] and 'ED25519' in data['failed'][0]['error']
            assert isinstance(_signed(app, csr_id).signature_hash_algorithm, hashes.SHA384)
        finally:
            _drop(app, CertificatePolicy, pid)
            _drop(app, Certificate, ed_id)

    def test_bulk_sign_reports_a_refusal_from_the_signer(self, app, auth_client, create_ca):
        # Two policies with no hash in common: only the signer itself can refuse
        ca = create_ca(cn='Algo bulk disjoint CA')
        a = _policy(app, 'algo-bulk-a', ca['id'], {'allowed_digests': ['sha384']})
        b = _policy(app, 'algo-bulk-b', ca['id'], {'allowed_digests': ['sha512']})
        csr_id = _store_csr(app, _csr(cn='bulk-disjoint.algo.test'))
        try:
            r = auth_client.post('/api/v2/csrs/bulk/sign', content_type=CONTENT_JSON,
                                 data=json.dumps({'ids': [csr_id], 'ca_id': ca['id']}))
            assert r.status_code == 200, r.data
            failed = get_json(r)['data']['failed']
            assert [f['id'] for f in failed] == [csr_id]
            assert failed[0]['error'].startswith('Policy violation'), failed
        finally:
            _drop(app, CertificatePolicy, a, b)
            _drop(app, Certificate, csr_id)

    def test_ocsp_responder_renewal_takes_the_allowed_digest(self, app, auth_client, create_ca):
        from datetime import timedelta
        from models import SystemConfig
        from services.ocsp_responder_renewal import run_ocsp_responder_renewal
        from utils.datetime_utils import utc_now
        ca = create_ca(cn='Algo OCSP responder CA')
        r = auth_client.post('/api/v2/certificates', content_type=CONTENT_JSON, data=json.dumps({
            'cn': 'ocsp.algo.test', 'ca_id': ca['id'], 'key_type': 'rsa', 'key_size': 2048,
            'validity_days': 90, 'cert_type': 'custom', 'extra_ekus': ['OCSPSigning']}))
        assert r.status_code in (200, 201), r.data
        cert_id = get_json(r)['data']['id']
        pid = _policy(app, 'algo-ocsp', ca['id'], {'allowed_digests': ['sha512']})
        key = f"ocsp_responder_cert_{ca['id']}"
        try:
            with app.app_context():
                db.session.add(SystemConfig(key=key, value=str(cert_id)))
                row = db.session.get(Certificate, cert_id)
                row.valid_from, row.valid_to = utc_now() - timedelta(days=85), utc_now() + timedelta(days=5)
                db.session.commit()
                assert run_ocsp_responder_renewal()['renewed'] == 1
                new_id = int(SystemConfig.query.filter_by(key=key).first().value)
            assert isinstance(_signed(app, new_id).signature_hash_algorithm, hashes.SHA512)
        finally:
            _drop(app, CertificatePolicy, pid)
            with app.app_context():
                row = SystemConfig.query.filter_by(key=key).first()
                if row:
                    db.session.delete(row)
                    db.session.commit()
