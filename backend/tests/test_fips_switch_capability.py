"""Outside FIPS mode, the readiness check judges EdDSA and ML-DSA by the module the switch
will load: the one the -fips image queried at build, or none (listed as refused)."""
import datetime
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import ed25519, mldsa
from cryptography.x509.oid import NameOID

import fips_mode

ALL = list(fips_mode.MODULE_DEPENDENT_SIGNATURES)


def _self_signed(key):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'switch capability')])
    now = datetime.datetime.now(datetime.timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=1)).sign(key, None))


@pytest.fixture
def fips_off(monkeypatch, tmp_path):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)
    monkeypatch.setattr(fips_mode, 'module_approves', lambda alg: False)
    monkeypatch.setattr(fips_mode, 'BUILD_CAPABILITY_FILE', str(tmp_path / 'fips-module.json'))
    return tmp_path / 'fips-module.json'


def _built(path, approved):
    path.write_text(json.dumps({'provider': {'name': 'OpenSSL FIPS Provider', 'version': '3.5.9'},
                                'approved_signatures': approved}))


class TestSwitchApproves:
    def test_built_capability_approving(self, fips_off):
        _built(fips_off, ALL)
        assert all(fips_mode.switch_approves(a) for a in ALL)
        assert fips_mode.switch_approves('ml-dsa-65')

    def test_built_capability_not_approving(self, fips_off):
        _built(fips_off, [])
        assert not any(fips_mode.switch_approves(a) for a in ALL)

    def test_without_a_built_capability_the_loaded_module_answers(self, fips_off, monkeypatch):
        assert not fips_mode.switch_approves('ED25519')
        monkeypatch.setattr(fips_mode, 'module_approves', lambda alg: alg == 'ED25519')
        assert fips_mode.switch_approves('ED25519')

    def test_an_unreadable_capability_falls_back_to_the_loaded_module(self, fips_off, monkeypatch):
        fips_off.write_text('{not json')
        assert fips_mode.build_capability() is None
        assert not fips_mode.switch_approves('ED25519')
        monkeypatch.setattr(fips_mode, 'module_approves', lambda alg: alg == 'ED25519')
        assert fips_mode.switch_approves('ED25519')

    def test_in_fips_mode_the_loaded_module_answers_not_the_file(self, fips_off, monkeypatch):
        _built(fips_off, ALL)
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        assert not fips_mode.switch_approves('ED25519')

    def test_write_build_capability_records_the_module_answer(self, fips_off, monkeypatch):
        monkeypatch.setattr(fips_mode, 'module_approves', lambda alg: alg in ('ED25519', 'ML-DSA-65'))
        monkeypatch.setattr(fips_mode, 'provider_info', lambda: {'name': 'OpenSSL FIPS Provider',
                                                                  'version': '3.5.9', 'buildinfo': ''})
        fips_mode.write_build_capability(str(fips_off))
        assert fips_mode.build_capability() == frozenset({'ED25519', 'ML-DSA-65'})

    def test_write_build_capability_needs_a_loaded_module(self, fips_off, monkeypatch):
        monkeypatch.setattr(fips_mode, 'provider_info', lambda: None)
        with pytest.raises(RuntimeError):
            fips_mode.write_build_capability(str(fips_off))
        assert not fips_off.exists()


class TestPreflightBeforeTheSwitch:
    @pytest.mark.parametrize('approved,expected', [(ALL, True), ([], False)])
    def test_certificate_key(self, fips_off, approved, expected):
        from services.fips_preflight import certificate_key
        _built(fips_off, approved)
        assert certificate_key(_self_signed(ed25519.Ed25519PrivateKey.generate())) == ('Ed25519', expected)
        assert certificate_key(_self_signed(mldsa.MLDSA65PrivateKey.generate())) == ('ML-DSA-65', expected)

    @pytest.mark.parametrize('approved,expected', [(ALL, True), ([], False)])
    def test_stored_labels(self, fips_off, approved, expected):
        from services.fips_preflight import stored_label_approved
        _built(fips_off, approved)
        assert stored_label_approved('Ed25519') is expected
        assert stored_label_approved('ML-DSA-87') is expected
        assert stored_label_approved('EC-P256') is True

    def test_ssh_detectors(self, fips_off):
        from services import fips_preflight
        _built(fips_off, ALL)
        assert fips_preflight._ssh_eddsa('ed25519', None) is None
        assert not fips_preflight._ssh_cert_key_refused('ed25519')
        _built(fips_off, [])
        assert fips_preflight._ssh_eddsa('ed25519', None) == 'Ed25519'
        assert fips_preflight._ssh_cert_key_refused('ed448')


class TestReportSaysWhichModuleJudged:
    """The standard image has no build record: its report says it judged without a module."""

    def test_without_record_nor_module_the_report_says_so(self, fips_off, monkeypatch, app):
        from services import fips_preflight
        monkeypatch.setattr(fips_mode, 'provider_info', lambda: None)
        assert fips_mode.switch_module_known() is False
        with app.app_context():
            assert fips_preflight.run(detectors=[])['module_known'] is False

    @pytest.mark.parametrize('how', ['record', 'loaded', 'fips_mode'])
    def test_a_record_or_a_module_judges(self, how, fips_off, monkeypatch, app):
        from services import fips_preflight
        monkeypatch.setattr(fips_mode, 'provider_info', lambda: None)
        if how == 'record':
            _built(fips_off, [])
        elif how == 'loaded':
            monkeypatch.setattr(fips_mode, 'provider_info', lambda: {'name': 'OpenSSL FIPS Provider',
                                                                      'version': '3.1.2', 'buildinfo': ''})
        else:
            monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        assert fips_mode.switch_module_known() is True
        with app.app_context():
            assert fips_preflight.run(detectors=[])['module_known'] is True

    def test_the_text_report_tells_to_use_the_fips_image(self):
        from scripts.fips_preflight import render_text
        report = {'fips_active': False, 'module_known': False, 'findings': [], 'errors': [],
                  'summary': {'blocker': 0, 'warning': 0, 'info': 0}}
        assert '-fips image' in render_text(report)
        assert '-fips image' not in render_text({**report, 'module_known': True})
