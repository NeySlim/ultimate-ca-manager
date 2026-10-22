"""Signature, horizon, HSM, TSA and advisory rules of the policy engine (3.2).

The rules come from the compliance profiles (``anssi``, ``bsi``, ``eu-acm``)
and from ordinary policies. Each issuing path gets one case: certificate form,
CSR signing, renewal, CA creation, TSA signer, SCEP, OCSP responder, the
service trunks (``create_certificate``, ``sign_csr``) and PKCS#12 export.
"""
import base64
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

import compliance_profiles
from models import CA, Certificate, SystemConfig, db
from models.policy import CertificatePolicy
from services import compliance_signer
from services.policy_service import PolicyEvaluationService, PolicyViolation, SystemPolicy
from tests.conftest import get_json

JSON = 'application/json'


# ---- helpers -----------------------------------------------------------------

def _pol(name, rules):
    return SystemPolicy(name, rules)


def _enforce(rules, **kwargs):
    """Violations of a policy holding *rules* alone, advisories in the second slot."""
    notices = []
    v, _, _ = PolicyEvaluationService.enforce_rules(
        [_pol('p', rules)], notify=False, notices=notices, **kwargs)
    return v, notices


def _set_profile(app, ca_id, name):
    with app.app_context():
        db.session.get(CA, ca_id).compliance_profile = name
        db.session.commit()


def _days_until(day):
    return (day - datetime.now(timezone.utc).date()).days


def _past_anssi_horizon():
    """Validity days that end after the ANSSI RSA-2048 horizon (2030-12-31)."""
    return _days_until(date(2030, 12, 31)) + 30


def _within_anssi_horizon():
    return _days_until(date(2030, 12, 31)) - 30


def _leaf(auth_client, ca_id, cn, **extra):
    body = {'cn': cn, 'ca_id': ca_id, 'validity_days': 30, **extra}
    return auth_client.post('/api/v2/certificates', content_type=JSON, data=json.dumps(body))


def _new_ca(create_ca, app, name, profile=None, **kwargs):
    ca = create_ca(cn=name, **kwargs)
    if profile:
        _set_profile(app, ca['id'], profile)
    return ca


def _store_csr(app, key, cn):
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName(cn)]), critical=False)
           .sign(key, hashes.SHA256()))
    with app.app_context():
        row = Certificate(refid=str(uuid.uuid4()), descr=cn, source='manual',
                          csr=base64.b64encode(csr.public_bytes(serialization.Encoding.PEM)).decode())
        db.session.add(row)
        db.session.commit()
        return row.id, csr


def _rsa(bits):
    return rsa.generate_private_key(public_exponent=65537, key_size=bits)


# ---- the rules on their own --------------------------------------------------

class TestHorizons:

    def test_a_certificate_ending_after_the_horizon_is_refused(self):
        rules = {'key_type_horizons': {'RSA-2048': '2030-12-31'}}
        v, _ = _enforce(rules, key_type='RSA-2048', not_after=date(2031, 1, 1))
        assert len(v) == 1 and 'RSA-2048' in v[0] and '2030-12-31' in v[0]
        assert _enforce(rules, key_type='RSA-2048', not_after=date(2030, 12, 31))[0] == []
        # Another key type is not bound by the label's horizon
        assert _enforce(rules, key_type='RSA-3072', not_after=date(2040, 1, 1))[0] == []

    def test_the_end_is_the_capped_validity_when_no_date_is_given(self):
        rules = {'key_type_horizons': {'RSA-2048': '2030-12-31'}}
        far = _days_until(date(2030, 12, 31)) + 100
        assert len(_enforce(rules, key_type='RSA-2048', validity_days=far)[0]) == 1
        capped = [_pol('cap', {'max_validity_days': 30}), _pol('h', rules)]
        v, days, _ = PolicyEvaluationService.enforce_rules(
            capped, key_type='RSA-2048', validity_days=far, notify=False)
        assert v == [] and days == 30  # the cap comes first, the shorter certificate fits

    def test_issuance_is_refused_after_the_issue_until_date(self):
        past = {'key_type_issue_until': {'RSA-2048': '2000-01-01'}}
        v, _ = _enforce(past, key_type='RSA-2048')
        assert len(v) == 1 and '2000-01-01' in v[0]
        future = {'key_type_issue_until': {'RSA-2048': '2999-01-01'}}
        assert _enforce(future, key_type='RSA-2048')[0] == []
        assert _enforce(past, key_type='EC-P256')[0] == []

    def test_a_malformed_date_in_a_stored_policy_binds_nothing(self):
        assert _enforce({'key_type_horizons': {'RSA-2048': 'soon'}},
                        key_type='RSA-2048', not_after=date(2099, 1, 1))[0] == []


class TestSignatureSchemes:

    def test_v15_is_refused_with_the_way_out(self):
        rules = {'allowed_signature_schemes': ['rsa_pss', 'ecdsa']}
        v, _ = _enforce(rules, signer_scheme='rsa_pkcs1v15')
        assert len(v) == 1 and 'RSA-PSS' in v[0] and 'rsa_pkcs1v15' in v[0]
        assert _enforce(rules, signer_scheme='rsa_pss')[0] == []
        assert _enforce(rules, signer_scheme='ecdsa')[0] == []
        assert len(_enforce(rules, signer_scheme='eddsa')[0]) == 1
        assert _enforce(rules)[0] == []  # no signer, nothing to judge

    def test_the_scheme_is_read_from_a_ca_row_and_from_its_key(self, app, create_ca):
        ca = create_ca(cn='Scheme read CA')
        with app.app_context():
            row = db.session.get(CA, ca['id'])
            assert compliance_signer.describe(row) == ('rsa_pkcs1v15', 'software')
            row.signature_scheme = 'pss'
            assert compliance_signer.describe(row) == ('rsa_pss', 'software')
            from services.hsm.ca_key_loader import get_ca_signing_key
            assert compliance_signer.describe(get_ca_signing_key(row)) == ('rsa_pss', 'software')
            key = ec.generate_private_key(ec.SECP256R1())
            assert compliance_signer.describe(key) == ('ecdsa', 'software')
            db.session.rollback()


class TestHsmAndTsa:

    def test_software_and_softhsm_keys_are_refused_where_an_hsm_is_required(self):
        rules = {'require_hsm_ca_key': True}
        assert 'software key' in _enforce(rules, signer_storage='software')[0][0]
        assert 'SoftHSM' in _enforce(rules, signer_storage='softhsm')[0][0]
        assert _enforce(rules, signer_storage='hsm')[0] == []
        assert _enforce({'require_hsm_ca_key': False}, signer_storage='software')[0] == []

    def test_softhsm_is_told_by_the_pkcs11_module_or_its_name(self):
        def provider(kind, module, name='HSM'):
            return SimpleNamespace(type=kind, name=name, get_config=lambda: {'module_path': module})
        assert compliance_signer.softhsm_provider(provider('pkcs11', '/usr/lib/softhsm/libsofthsm2.so'))
        assert compliance_signer.softhsm_provider(provider('pkcs11', '/usr/lib/softhsm/libpkcs11.so'))
        assert compliance_signer.softhsm_provider(provider('pkcs11', '/opt/lab/libtoken.so', 'SoftHSM lab'))
        assert not compliance_signer.softhsm_provider(provider('pkcs11', '/opt/vendor/libcs_pkcs11_R3.so'))
        assert not compliance_signer.softhsm_provider(provider('openbao', '/usr/lib/softhsm/libsofthsm2.so'))
        assert not compliance_signer.softhsm_provider(None)

    def test_a_key_row_that_cannot_be_read_is_not_an_hsm(self):
        assert compliance_signer.storage_for_hsm_key(None) == 'software'
        assert compliance_signer.storage_for_hsm_key(SimpleNamespace(provider=None)) == 'software'

        def broken():
            raise ValueError('config unreadable')
        unreadable = SimpleNamespace(type='pkcs11', name='HSM', get_config=broken)
        assert compliance_signer.storage_for_hsm_key(SimpleNamespace(provider=unreadable)) == 'software'
        vendor = SimpleNamespace(type='pkcs11', name='HSM', get_config=lambda: {'module_path': '/opt/v/lib.so'})
        assert compliance_signer.storage_for_hsm_key(SimpleNamespace(provider=vendor)) == 'hsm'

    def test_a_planned_ca_on_a_missing_hsm_row_is_not_an_hsm(self, app):
        from services.ca.ca_creation import _planned_signer
        with app.app_context():
            assert _planned_signer('EC-P256', None, 987654, None) == ('ecdsa', 'software')
            assert _planned_signer('EC-P256', None, None, 987654) == ('ecdsa', 'software')

    def test_a_tsa_signer_must_have_an_allowed_key_type(self):
        rules = {'tsa_signer_key_types': ['EC-P256', 'EC-P384']}
        v, _ = _enforce(rules, key_type='RSA-3072', tsa_signer=True)
        assert len(v) == 1 and 'EC signer' in v[0] and 'RSA-3072' in v[0]
        assert _enforce(rules, key_type='EC-P256', tsa_signer=True)[0] == []
        assert _enforce(rules, key_type='RSA-3072')[0] == []  # not a TSA certificate
        assert _enforce({'tsa_signer_key_types': []}, key_type='RSA-3072', tsa_signer=True)[0] == []

    def test_a_standalone_post_quantum_key_is_refused_unless_paired(self):
        rules = {'pq_standalone': True}
        v, _ = _enforce(rules, key_type='ML-DSA-65')
        assert len(v) == 1 and 'ML-DSA-65' in v[0]
        assert len(_enforce(rules, signer_scheme='ml_dsa')[0]) == 1
        assert _enforce(rules, key_type='ML-DSA-65', pq_hybrid=True)[0] == []
        assert _enforce({'pq_standalone': False}, key_type='ML-DSA-65')[0] == []
        assert _enforce(rules, key_type='RSA-3072')[0] == []


class TestAdvisories:

    RULES = {'allowed_key_types': ['RSA-3072'],
             'advisories': {'allowed_key_types': ['RSA-4096'],
                            'allowed_signature_schemes': ['rsa_pss'],
                            'key_type_horizons': {'RSA-3072': '2030-01-01'}}}

    def test_an_advisory_is_a_notice_and_never_a_refusal(self):
        v, notices = _enforce(self.RULES, key_type='RSA-3072', signer_scheme='rsa_pkcs1v15',
                              not_after=date(2031, 1, 1))
        assert v == []
        assert len(notices) == 3 and all('not recommended' in n for n in notices)
        assert any('RSA-PSS' in n for n in notices)

    def test_a_request_that_meets_the_advisories_has_no_notice(self):
        v, notices = _enforce({'advisories': self.RULES['advisories']}, key_type='RSA-4096',
                              signer_scheme='rsa_pss', not_after=date(2029, 1, 1))
        assert v == [] and notices == []

    def test_the_rules_beside_the_advisories_still_refuse(self):
        v, _ = _enforce(self.RULES, key_type='RSA-2048')
        assert len(v) == 1 and 'not allowed' in v[0]

    def test_without_a_notice_list_nothing_is_collected(self):
        v, _, _ = PolicyEvaluationService.enforce_rules(
            [_pol('p', self.RULES)], key_type='RSA-3072', notify=False)
        assert v == []


# ---- the rules reach the effective view and the policy form -------------------

class TestEffectiveAndValidation:

    def test_effective_exposes_the_schemes_and_the_horizons(self, app, auth_client, create_ca):
        ca = _new_ca(create_ca, app, 'Effective rules CA', profile='eu-acm')
        data = get_json(auth_client.get(f"/api/v2/policies/effective?ca_id={ca['id']}"))['data']
        assert data['allowed_signature_schemes'] == ['rsa_pkcs1v15', 'rsa_pss', 'ecdsa']
        assert data['key_type_horizons'] == {'RSA-2048': '2028-12-31'}
        assert data['key_type_issue_until'] == {'RSA-2048': '2026-12-31'}
        assert data['require_hsm_ca_key'] is True
        plain = create_ca(cn='Effective plain CA')
        data = get_json(auth_client.get(f"/api/v2/policies/effective?ca_id={plain['id']}"))['data']
        assert data['allowed_signature_schemes'] is None and data['key_type_horizons'] == {}
        assert data['require_hsm_ca_key'] is False

    @pytest.mark.parametrize('rules', [
        {'allowed_signature_schemes': ['rsa_pss', 'ecdsa'],
         'key_type_horizons': {'RSA-2048': '2030-12-31'},
         'key_type_issue_until': {'rsa-2048': '2026-12-31'},
         'require_hsm_ca_key': True, 'pq_standalone': True,
         'tsa_signer_key_types': ['EC-P256'],
         'advisories': {'allowed_signature_schemes': ['rsa_pss'],
                        'key_type_horizons': {'RSA-3072': '2035-12-31'}}},
    ])
    def test_a_policy_accepts_the_new_rules(self, auth_client, rules):
        r = auth_client.post('/api/v2/policies', content_type=JSON, data=json.dumps({
            'name': f'rules-ok-{uuid.uuid4().hex[:6]}', 'is_active': False, 'rules': rules}))
        assert r.status_code in (200, 201), r.data
        stored = get_json(r)['data']['rules']
        assert stored['key_type_issue_until'] == {'RSA-2048': '2026-12-31'}
        assert stored['advisories']['allowed_signature_schemes'] == ['rsa_pss']

    @pytest.mark.parametrize('rules, fragment', [
        ({'allowed_signature_schemes': ['rsa_pss', 'rot13']}, 'rot13'),
        ({'allowed_signature_schemes': 'rsa_pss'}, 'must be a list'),
        ({'key_type_horizons': {'RSA-2048': '31/12/2030'}}, 'YYYY-MM-DD'),
        ({'key_type_horizons': {'RSA-2048': '2030-02-30'}}, 'YYYY-MM-DD'),
        ({'key_type_horizons': {'RSA-2048': 2030}}, 'YYYY-MM-DD'),
        ({'key_type_horizons': {'nonsense': '2030-12-31'}}, 'Unknown key type'),
        ({'key_type_horizons': ['RSA-2048']}, 'must be an object'),
        ({'key_type_issue_until': {'RSA-2048': None}}, 'YYYY-MM-DD'),
        ({'tsa_signer_key_types': ['bogus']}, 'Unknown key type'),
        ({'require_hsm_ca_key': 'yes'}, 'true or false'),
        ({'pq_standalone': 1}, 'true or false'),
        ({'advisories': ['x']}, 'must be an object'),
        ({'advisories': {'max_validity_days': 10}}, 'advisories cannot hold'),
        ({'advisories': {'allowed_signature_schemes': ['nope']}}, 'nope'),
    ])
    def test_a_policy_refuses_what_it_cannot_read(self, auth_client, rules, fragment):
        r = auth_client.post('/api/v2/policies', content_type=JSON, data=json.dumps({
            'name': f'rules-bad-{uuid.uuid4().hex[:6]}', 'is_active': False, 'rules': rules}))
        assert r.status_code == 400, r.data
        assert fragment in get_json(r)['message']


# ---- one case per issuing path ------------------------------------------------

class TestCertificateForm:

    def test_a_leaf_ending_after_the_horizon_is_refused(self, app, auth_client, create_ca):
        ca = _new_ca(create_ca, app, 'Form horizon CA', profile='anssi')
        r = _leaf(auth_client, ca['id'], 'late.horizon.test', validity_days=_past_anssi_horizon())
        assert r.status_code == 400, r.get_json()
        assert 'RSA-2048' in r.get_json()['message'] and '2030-12-31' in r.get_json()['message']
        r = _leaf(auth_client, ca['id'], 'inside.horizon.test', validity_days=_within_anssi_horizon())
        assert r.status_code == 201, r.get_json()

    def test_an_advisory_travels_with_the_response(self, app, auth_client, create_ca):
        ca = _new_ca(create_ca, app, 'Form advisory CA', profile='anssi')
        r = _leaf(auth_client, ca['id'], 'advice.horizon.test')
        assert r.status_code == 201, r.get_json()
        notices = get_json(r)['meta']['notices']
        assert any('RSA-2048' in n and 'not recommended' in n for n in notices), notices
        r = _leaf(auth_client, ca['id'], 'strong.horizon.test', key_type='rsa', key_size=3072)
        assert r.status_code == 201
        assert not any('RSA-3072' in n for n in (get_json(r).get('meta') or {}).get('notices', []))

    def test_a_v15_ca_cannot_issue_under_bsi_until_it_signs_pss(self, app, auth_client, create_ca):
        ca = _new_ca(create_ca, app, 'Form scheme CA', profile='bsi', keySize=3072)
        r = _leaf(auth_client, ca['id'], 'v15.bsi.test', key_type='ec', curve='P-256')
        assert r.status_code == 400, r.get_json()
        assert 'RSA-PSS' in r.get_json()['message']
        with app.app_context():
            db.session.get(CA, ca['id']).signature_scheme = 'pss'
            db.session.commit()
        r = _leaf(auth_client, ca['id'], 'pss.bsi.test', key_type='ec', curve='P-256')
        assert r.status_code == 201, r.get_json()

    def test_a_software_ca_key_cannot_issue_under_eu_acm(self, app, auth_client, create_ca):
        ca = _new_ca(create_ca, app, 'Form hsm CA', profile='eu-acm', keySize=3072)
        r = _leaf(auth_client, ca['id'], 'soft.eu.test', key_type='ec', curve='P-256')
        assert r.status_code == 400, r.get_json()
        assert 'HSM' in r.get_json()['message']

    def test_a_tsa_certificate_with_an_rsa_key_is_refused_under_bsi(self, app, auth_client, create_ca):
        ca = _new_ca(create_ca, app, 'Form tsa CA', profile='bsi', keySize=3072, signatureScheme='pss')
        body = {'cert_type': 'custom', 'extra_ekus': ['timeStamping'], 'key_type': 'rsa',
                'key_size': 3072}
        r = _leaf(auth_client, ca['id'], 'rsa.tsa.test', **body)
        assert r.status_code == 400, r.get_json()
        assert 'EC signer' in r.get_json()['message']
        r = _leaf(auth_client, ca['id'], 'ec.tsa.test', **{**body, 'key_type': 'ec', 'curve': 'P-256',
                                                           'key_size': None})
        assert r.status_code == 201, r.get_json()

    def test_a_policy_not_a_profile_carries_the_same_rules(self, app, auth_client, create_ca):
        ca = create_ca(cn='Form plain policy CA')
        with app.app_context():
            pol = CertificatePolicy(name=f'rules-{uuid.uuid4().hex[:6]}', policy_type='issuance',
                                    ca_id=ca['id'], is_active=True, priority=100,
                                    requires_approval=False, min_approvers=1)
            pol.set_rules({'key_type_horizons': {'RSA-2048': '2027-01-01'},
                           'advisories': {'allowed_key_types': ['RSA-3072']}})
            db.session.add(pol)
            db.session.commit()
            pid = pol.id
        try:
            assert _leaf(auth_client, ca['id'], 'plain.ok.test', validity_days=30).status_code in (200, 201) \
                or _days_until(date(2027, 1, 1)) < 30
            r = _leaf(auth_client, ca['id'], 'plain.late.test', validity_days=_days_until(date(2027, 1, 1)) + 5)
            assert r.status_code == 400 and '2027-01-01' in r.get_json()['message']
        finally:
            with app.app_context():
                db.session.delete(db.session.get(CertificatePolicy, pid))
                db.session.commit()


class TestCsrSigning:

    def test_a_csr_signed_past_the_horizon_is_refused_and_advised(self, app, auth_client, create_ca):
        ca = _new_ca(create_ca, app, 'Csr horizon CA', profile='anssi')
        csr_id, _ = _store_csr(app, _rsa(2048), 'csr-late.horizon.test')
        r = auth_client.post(f"/api/v2/csrs/{csr_id}/sign", content_type=JSON, data=json.dumps({
            'ca_id': ca['id'], 'validity_days': _past_anssi_horizon(), 'cert_type': 'server'}))
        assert r.status_code == 400, r.get_json()
        assert '2030-12-31' in r.get_json()['message']
        r = auth_client.post(f"/api/v2/csrs/{csr_id}/sign", content_type=JSON, data=json.dumps({
            'ca_id': ca['id'], 'validity_days': _within_anssi_horizon(), 'cert_type': 'server'}))
        assert r.status_code == 200, r.get_json()
        assert any('not recommended' in n for n in get_json(r)['meta']['notices'])

    def test_the_bulk_route_refuses_a_v15_signer_under_bsi(self, app, auth_client, create_ca):
        ca = _new_ca(create_ca, app, 'Csr bulk scheme CA', profile='bsi', keySize=3072)
        csr_id, _ = _store_csr(app, _rsa(3072), 'csr-bulk.scheme.test')
        r = auth_client.post('/api/v2/csrs/bulk/sign', content_type=JSON, data=json.dumps({
            'ids': [csr_id], 'ca_id': ca['id'], 'validity_days': 30}))
        assert r.status_code == 200, r.data
        failed = get_json(r)['data']['failed']
        assert failed and 'RSA-PSS' in failed[0]['error'], failed

    def test_sign_csr_trunk_refuses_a_key_past_its_horizon(self, app, create_ca):
        from services.cert_service import CertificateService
        ca = _new_ca(create_ca, app, 'Csr trunk CA', profile='anssi')
        csr_id, _ = _store_csr(app, _rsa(2048), 'csr-trunk.horizon.test')
        with app.app_context():
            refid = db.session.get(CA, ca['id']).refid
            with pytest.raises(PolicyViolation, match='2030-12-31'):
                CertificateService.sign_csr(cert_id=csr_id, caref=refid,
                                            validity_days=_past_anssi_horizon())
            db.session.rollback()

    def test_sign_csr_trunk_refuses_a_tsa_signer_with_an_rsa_key(self, app, create_ca):
        from services.cert_service import CertificateService
        ca = _new_ca(create_ca, app, 'Csr trunk tsa CA', profile='bsi', keySize=3072,
                     signatureScheme='pss')
        csr_id, _ = _store_csr(app, _rsa(3072), 'csr-trunk.tsa.test')
        with app.app_context():
            refid = db.session.get(CA, ca['id']).refid
            with pytest.raises(PolicyViolation, match='EC signer'):
                CertificateService.sign_csr(cert_id=csr_id, caref=refid, validity_days=30,
                                            extra_ekus=['timeStamping'], allow_sensitive_ekus=True)
            db.session.rollback()


class TestRenewal:

    def test_renewal_is_issuance_for_the_horizon(self, app, auth_client, create_ca):
        ca = create_ca(cn='Renew horizon CA')
        r = _leaf(auth_client, ca['id'], 'renew.horizon.test')
        assert r.status_code == 201
        cert_id = get_json(r)['data']['id']
        _set_profile(app, ca['id'], 'anssi')
        r = auth_client.post(f'/api/v2/certificates/{cert_id}/renew', content_type=JSON,
                             data=json.dumps({'validity_days': _past_anssi_horizon()}))
        assert r.status_code == 400, r.get_json()
        assert '2030-12-31' in r.get_json()['message']
        r = auth_client.post(f'/api/v2/certificates/{cert_id}/renew', content_type=JSON,
                             data=json.dumps({'validity_days': _within_anssi_horizon()}))
        assert r.status_code == 200, r.get_json()
        assert any('not recommended' in n for n in get_json(r)['meta']['notices'])


class TestCaCreation:

    def _post(self, auth_client, cn, **kwargs):
        data = {'type': 'root', 'commonName': cn, 'keyAlgo': 'RSA', 'keySize': 3072,
                'validityYears': 3, 'hashAlgorithm': 'sha256', **kwargs}
        return auth_client.post('/api/v2/cas', data=json.dumps(data), content_type=JSON)

    def test_a_v15_root_is_refused_under_bsi_with_the_way_out(self, app, auth_client):
        r = self._post(auth_client, 'Create v15 bsi', complianceProfile='bsi')
        assert r.status_code == 400, r.get_json()
        assert 'RSA-PSS' in r.get_json()['message']
        with app.app_context():
            assert CA.query.filter_by(descr='Create v15 bsi').first() is None
        assert self._post(auth_client, 'Create pss bsi', complianceProfile='bsi',
                          signatureScheme='pss').status_code == 201

    def test_a_ca_cannot_end_after_the_horizon_of_its_key(self, app, auth_client):
        years = _past_anssi_horizon() // 365 + 1
        r = self._post(auth_client, 'Create late anssi', keySize=2048, validityYears=years,
                       complianceProfile='anssi')
        assert r.status_code == 400 and '2030-12-31' in r.get_json()['message']
        r = self._post(auth_client, 'Create late anssi 3072', keySize=3072, validityYears=years,
                       complianceProfile='anssi')
        assert r.status_code == 201, r.get_json()

    def test_a_software_key_is_refused_for_eu_acm(self, app, auth_client):
        r = self._post(auth_client, 'Create soft eu', complianceProfile='eu-acm')
        assert r.status_code == 400 and 'HSM' in r.get_json()['message']
        with app.app_context():
            assert CA.query.filter_by(descr='Create soft eu').first() is None

    def test_a_child_ends_before_the_horizon_of_its_parents_profile(self, app, auth_client, create_ca):
        parent = _new_ca(create_ca, app, 'Create anssi parent', profile='anssi', keySize=3072)
        years = _past_anssi_horizon() // 365 + 1
        r = self._post(auth_client, 'Create late child', type='intermediate', parentCAId=parent['id'],
                       keySize=2048, validityYears=years)
        assert r.status_code == 400 and '2030-12-31' in r.get_json()['message'], r.get_json()
        r = self._post(auth_client, 'Create early child', type='intermediate', parentCAId=parent['id'],
                       keySize=2048, validityYears=2)
        assert r.status_code == 201, r.get_json()

    def test_an_intermediate_under_a_v15_parent_is_refused_under_bsi(self, app, auth_client, create_ca):
        parent = _new_ca(create_ca, app, 'Create bsi parent', profile='bsi', keySize=3072)
        r = self._post(auth_client, 'Create bsi child', type='intermediate', parentCAId=parent['id'],
                       signatureScheme='pss')
        assert r.status_code == 400 and 'RSA-PSS' in r.get_json()['message'], r.get_json()


class TestApproval:

    def _approved(self, ca_id, cn, **data):
        from models import User
        gate = CertificatePolicy(name=f'tsa-gate-{uuid.uuid4().hex[:8]}', policy_type='issuance',
                                 requires_approval=True, min_approvers=1, is_active=False)
        db.session.add(gate)
        db.session.commit()
        requester = User.query.filter_by(role='admin').first()
        approval = PolicyEvaluationService.create_approval_request(
            policy=gate, requester_id=requester.id, request_type='certificate',
            request_data={'cn': cn, 'ca_id': ca_id, 'validity_days': 30, **data})
        approval.status = 'approved'
        db.session.commit()
        return approval

    def test_an_approved_rsa_tsa_signer_is_refused_under_bsi(self, app, create_ca):
        from api.v2.policies import _issue_approved_certificate
        ca = _new_ca(create_ca, app, 'Approval tsa CA', profile='bsi', keySize=3072, signatureScheme='pss')
        body = {'cert_type': 'custom', 'extra_ekus': ['timeStamping']}
        with app.app_context():
            rsa_ap = self._approved(ca['id'], 'rsa.approved.tsa.test', key_type='rsa', key_size=3072, **body)
            with pytest.raises(PolicyViolation, match='EC signer'):
                _issue_approved_certificate(rsa_ap)
            db.session.rollback()
            ec_ap = self._approved(ca['id'], 'ec.approved.tsa.test', key_type='ec', curve='P-256', **body)
            assert _issue_approved_certificate(ec_ap)['id']
            db.session.commit()


class TestTsaSigner:

    def _issue(self, auth_client, ca_id, **body):
        return auth_client.post('/api/v2/tsa/signer-certificate', content_type=JSON,
                                data=json.dumps({'ca_id': ca_id, 'select': False, **body}))

    def test_issuing_an_rsa_signer_is_refused_under_bsi(self, app, auth_client, create_ca):
        ca = _new_ca(create_ca, app, 'Tsa issue CA', profile='bsi', keySize=3072, signatureScheme='pss')
        r = self._issue(auth_client, ca['id'], key_type='rsa', key_size='3072')
        assert r.status_code == 400, r.get_json()
        assert 'EC signer' in r.get_json()['message']
        r = self._issue(auth_client, ca['id'], key_type='ec', curve='P-256')
        assert r.status_code == 200, r.get_json()

    def test_issuing_an_rsa_signer_is_an_advisory_matter_under_anssi(self, app, auth_client, create_ca):
        ca = _new_ca(create_ca, app, 'Tsa anssi CA', profile='anssi')
        r = self._issue(auth_client, ca['id'], key_type='rsa', key_size='3072')
        assert r.status_code == 200, r.get_json()

    def test_designating_an_rsa_signer_or_ca_is_refused_under_bsi(self, app, auth_client, create_ca):
        ca = create_ca(cn='Tsa designate CA', keySize=3072, signatureScheme='pss')
        r = self._issue(auth_client, ca['id'], key_type='rsa', key_size='3072')
        assert r.status_code == 200, r.get_json()
        refid = get_json(r)['data']['certificate']['refid']
        _set_profile(app, ca['id'], 'bsi')
        try:
            r = auth_client.patch('/api/v2/tsa/config', content_type=JSON,
                                  data=json.dumps({'signer_cert_refid': refid}))
            assert r.status_code == 400 and 'EC signer' in r.get_json()['message'], r.get_json()
            ca_refid = None
            with app.app_context():
                ca_refid = db.session.get(CA, ca['id']).refid
            r = auth_client.patch('/api/v2/tsa/config', content_type=JSON,
                                  data=json.dumps({'ca_refid': ca_refid}))
            assert r.status_code == 400 and 'EC signer' in r.get_json()['message'], r.get_json()
            # Dropping the dedicated signer hands the tokens to the configured CA
            with app.app_context():
                for key, value in (('tsa_ca_refid', ca_refid), ('tsa_signer_cert_refid', refid)):
                    row = SystemConfig.query.filter_by(key=key).first() or SystemConfig(key=key)
                    row.value = value
                    db.session.add(row)
                db.session.commit()
            r = auth_client.patch('/api/v2/tsa/config', content_type=JSON,
                                  data=json.dumps({'signer_cert_refid': ''}))
            assert r.status_code == 400 and 'EC signer' in r.get_json()['message'], r.get_json()
        finally:
            with app.app_context():
                SystemConfig.query.filter(SystemConfig.key.in_(
                    ['tsa_ca_refid', 'tsa_signer_cert_refid', 'tsa_enabled'])).delete(
                        synchronize_session=False)
                db.session.commit()


class TestScep:

    def test_the_scep_validity_is_refused_past_the_horizon(self, app, create_ca):
        from services.scep.scep_service import SCEPService
        ca = _new_ca(create_ca, app, 'Scep horizon CA', profile='anssi')
        _, csr = _store_csr(app, _rsa(2048), 'scep.horizon.test')
        with app.app_context():
            svc = SCEPService(db.session.get(CA, ca['id']).refid, challenge_password='x')
            with pytest.raises(PolicyViolation, match='2030-12-31'):
                svc._policy_validity(csr, _past_anssi_horizon())
            assert svc._policy_validity(csr, _within_anssi_horizon()) == _within_anssi_horizon()

    def test_the_scep_request_is_refused_under_a_v15_signer(self, app, create_ca):
        from services.scep.scep_service import SCEPService
        ca = _new_ca(create_ca, app, 'Scep scheme CA', profile='bsi', keySize=3072)
        _, csr = _store_csr(app, _rsa(3072), 'scep.scheme.test')
        with app.app_context():
            svc = SCEPService(db.session.get(CA, ca['id']).refid, challenge_password='x')
            _, violations = svc._policy_signing_hash(csr)
            assert any('RSA-PSS' in v for v in violations), violations


class TestServiceTrunk:

    def test_create_certificate_is_refused_past_the_horizon(self, app, create_ca):
        from services.cert_service import CertificateService
        ca = _new_ca(create_ca, app, 'Trunk create CA', profile='anssi')
        with app.app_context():
            refid = db.session.get(CA, ca['id']).refid
            with pytest.raises(PolicyViolation, match='2030-12-31'):
                CertificateService.create_certificate(
                    descr='trunk', caref=refid, dn={'CN': 'trunk.horizon.test'},
                    key_type='2048', validity_days=_past_anssi_horizon())
            db.session.rollback()


class TestOcspResponder:

    def test_a_v15_ca_does_not_renew_a_responder_under_bsi(self, app, auth_client, create_ca):
        from services.ocsp_responder_renewal import run_ocsp_responder_renewal
        from utils.datetime_utils import utc_now
        ca = create_ca(cn='Ocsp scheme CA', keySize=3072)
        r = _leaf(auth_client, ca['id'], 'ocsp.scheme.test', validity_days=90, key_type='ec',
                  curve='P-256', cert_type='custom', extra_ekus=['OCSPSigning'])
        assert r.status_code == 201, r.get_json()
        cert_id = get_json(r)['data']['id']
        key = f"ocsp_responder_cert_{ca['id']}"
        try:
            with app.app_context():
                db.session.add(SystemConfig(key=key, value=str(cert_id)))
                row = db.session.get(Certificate, cert_id)
                row.valid_from, row.valid_to = utc_now() - timedelta(days=85), utc_now() + timedelta(days=5)
                db.session.get(CA, ca['id']).compliance_profile = 'bsi'
                db.session.commit()
                result = run_ocsp_responder_renewal()
                assert result['renewed'] == 0, result
                assert int(SystemConfig.query.filter_by(key=key).first().value) == cert_id
        finally:
            with app.app_context():
                row = SystemConfig.query.filter_by(key=key).first()
                if row:
                    db.session.delete(row)
                    db.session.commit()


    def test_a_responder_is_not_renewed_past_the_horizon_of_its_key(self, app, auth_client, create_ca):
        from services.ocsp_responder_renewal import run_ocsp_responder_renewal
        from utils.datetime_utils import utc_now
        ca = create_ca(cn='Ocsp horizon CA')
        r = _leaf(auth_client, ca['id'], 'ocsp.horizon.test', validity_days=90, cert_type='custom',
                  extra_ekus=['OCSPSigning'])
        assert r.status_code == 201, r.get_json()
        cert_id = get_json(r)['data']['id']
        key = f"ocsp_responder_cert_{ca['id']}"
        try:
            with app.app_context():
                db.session.add(SystemConfig(key=key, value=str(cert_id)))
                row = db.session.get(Certificate, cert_id)
                row.valid_from = utc_now() - timedelta(days=_past_anssi_horizon())
                row.valid_to = utc_now() + timedelta(days=5)
                db.session.get(CA, ca['id']).compliance_profile = 'anssi'
                db.session.commit()
                result = run_ocsp_responder_renewal()
                assert (result['renewed'], result['failed']) == (0, 1), result
        finally:
            with app.app_context():
                row = SystemConfig.query.filter_by(key=key).first()
                if row:
                    db.session.delete(row)
                    db.session.commit()


class TestLegacyPkcs12:

    def _export(self, auth_client, cert_id, legacy):
        return auth_client.post(f'/api/v2/certificates/{cert_id}/export', content_type=JSON,
                                data=json.dumps({'format': 'pkcs12', 'password': 'Sup3r-secret-pw!',
                                                 'legacy': legacy}))

    def test_legacy_pkcs12_is_refused_for_a_certificate_of_a_profiled_ca(self, app, auth_client, create_ca):
        ca = create_ca(cn='P12 profile CA')
        r = _leaf(auth_client, ca['id'], 'p12.profile.test')
        assert r.status_code == 201
        cert_id = get_json(r)['data']['id']
        assert self._export(auth_client, cert_id, True).status_code == 200  # no profile yet
        _set_profile(app, ca['id'], 'anssi')
        refused = self._export(auth_client, cert_id, True)
        assert refused.status_code == 400, refused.data[:200]
        body = refused.get_json()
        assert body['type'] == compliance_profiles.PROBLEM_TYPE
        assert 'anssi' in body['message'] and '3DES' in body['message']
        assert self._export(auth_client, cert_id, False).status_code == 200  # modern stays
        _set_profile(app, ca['id'], None)
        assert self._export(auth_client, cert_id, True).status_code == 200

    def test_a_ca_with_a_profile_does_not_export_in_legacy(self, app, auth_client, create_ca):
        ca = _new_ca(create_ca, app, 'P12 own profile CA', profile='bsi')
        r = auth_client.post(f"/api/v2/cas/{ca['id']}/export", content_type=JSON, data=json.dumps({
            'format': 'pkcs12', 'include_key': True, 'password': 'Sup3r-secret-pw!', 'legacy': True}))
        assert r.status_code == 400 and 'bsi' in r.get_json()['message'], r.data[:200]

    def test_the_service_exports_refuse_legacy_under_a_profile(self, app, auth_client, create_ca):
        from services.ca_service import CAService
        from services.cert_service import CertificateService
        ca = _new_ca(create_ca, app, 'P12 service CA', profile='anssi')
        r = _leaf(auth_client, ca['id'], 'p12.service.test')
        assert r.status_code == 201
        cert_id = get_json(r)['data']['id']
        with app.app_context():
            with pytest.raises(compliance_profiles.ProfileRestricted, match='anssi'):
                CertificateService.export_certificate_with_options(
                    cert_id, 'pkcs12', password='Sup3r-secret-pw!', legacy=True)
            with pytest.raises(compliance_profiles.ProfileRestricted, match='anssi'):
                CAService.export_ca_with_options(ca['id'], 'pkcs12', password='Sup3r-secret-pw!', legacy=True)
            assert CertificateService.export_certificate_with_options(
                cert_id, 'pkcs12', password='Sup3r-secret-pw!')
