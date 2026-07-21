"""Certificate Transparency pre-certificate flow (RFC 6962)."""
import base64
import json
from unittest.mock import patch

import pytest
from cryptography import x509


SCT_LIST_OID = x509.ObjectIdentifier("1.3.6.1.4.1.11129.2.4.2")
CT_POISON_OID = x509.ObjectIdentifier("1.3.6.1.4.1.11129.2.4.3")


def _fake_sct():
    # TLS DigitallySigned: SHA-256 + ECDSA + a minimal DER-shaped signature.
    signature = b"\x04\x03\x00\x02\x30\x00"
    return {
        "sct_version": 0,
        "id": base64.b64encode(b"L" * 32).decode(),
        "timestamp": 1_700_000_000_000,
        "extensions": "",
        "signature": base64.b64encode(signature).decode(),
    }


@pytest.fixture
def ct_config(app):
    """Set CT SystemConfig values and remove them after each test."""
    keys = ("ct_enabled", "ct_auto_submit", "ct_embed_sct", "ct_required", "ct_log_urls")

    def configure(**overrides):
        from models import db, SystemConfig

        values = {
            "ct_enabled": "true",
            "ct_auto_submit": "false",
            "ct_embed_sct": "true",
            "ct_required": "false",
            "ct_log_urls": json.dumps(["https://ct.example.test/"]),
        }
        values.update({key: str(value).lower() if isinstance(value, bool) else value
                       for key, value in overrides.items()})
        with app.app_context():
            SystemConfig.query.filter(SystemConfig.key.in_(keys)).delete(
                synchronize_session=False
            )
            for key, value in values.items():
                db.session.add(SystemConfig(key=key, value=value))
            db.session.commit()

    yield configure

    from models import db, SystemConfig
    with app.app_context():
        SystemConfig.query.filter(SystemConfig.key.in_(keys)).delete(
            synchronize_session=False
        )
        SystemConfig.query.filter(SystemConfig.key.like("cert_scts_%")).delete(
            synchronize_session=False
        )
        db.session.commit()


def test_submit_precertificate_uses_add_pre_chain(monkeypatch):
    from utils.ct_client import submit_precert_to_ct_log

    captured = {}

    class Response:
        def read(self, *_args):
            return json.dumps(_fake_sct()).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request, **kwargs):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = kwargs["timeout"]
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "utils.ssrf_protection.validate_url_not_cloud_metadata", lambda _url: True
    )

    result = submit_precert_to_ct_log(
        "https://ct.example.test/", ["-----BEGIN CERTIFICATE-----\nYWJj\n-----END CERTIFICATE-----"]
    )

    assert result["id"] == _fake_sct()["id"]
    assert captured["url"] == "https://ct.example.test/ct/v1/add-pre-chain"
    assert captured["payload"] == {"chain": ["YWJj"]}
    assert captured["timeout"] == 10


def test_issuance_embeds_sct_and_removes_poison(app, create_ca, ct_config):
    from models import CA, SystemConfig
    from services.cert_service import CertificateService

    ca_data = create_ca(cn="CT Embed Test CA")
    ca_id = ca_data.get("id", ca_data.get("ca_id"))
    ct_config()
    captured = {}

    def fake_collect(chain, log_urls=None):
        precert = x509.load_pem_x509_certificate(chain[0].encode())
        poison = precert.extensions.get_extension_for_oid(CT_POISON_OID)
        assert poison.critical is True
        assert isinstance(poison.value, x509.PrecertPoison)
        with pytest.raises(x509.ExtensionNotFound):
            precert.extensions.get_extension_for_oid(SCT_LIST_OID)
        captured["precert"] = precert
        captured["chain"] = chain
        captured["log_urls"] = log_urls
        return [_fake_sct()]

    with patch("utils.ct_client.collect_precert_scts", side_effect=fake_collect):
        with app.app_context():
            ca = CA.query.filter_by(id=ca_id).first()
            issued = CertificateService.create_certificate(
                descr="CT embedded leaf",
                caref=ca.refid,
                dn={"CN": "ct-embedded.example.com"},
                validity_days=30,
                username="tester",
            )
            cert_id = issued.id
            final_cert = x509.load_pem_x509_certificate(base64.b64decode(issued.crt))

            sct_ext = final_cert.extensions.get_extension_for_oid(SCT_LIST_OID)
            assert sct_ext.critical is False
            assert isinstance(sct_ext.value, x509.PrecertificateSignedCertificateTimestamps)
            assert len(sct_ext.value) == 1
            assert bytes(sct_ext.value[0].log_id) == b"L" * 32
            with pytest.raises(x509.ExtensionNotFound):
                final_cert.extensions.get_extension_for_oid(CT_POISON_OID)

            assert captured["precert"].serial_number == final_cert.serial_number
            assert captured["precert"].subject == final_cert.subject
            assert captured["precert"].public_key().public_numbers() == final_cert.public_key().public_numbers()
            assert len(captured["chain"]) == 2
            assert captured["log_urls"] == ["https://ct.example.test/"]

            stored = SystemConfig.query.filter_by(key=f"cert_scts_{cert_id}").first()
            assert json.loads(stored.value)[0]["id"] == _fake_sct()["id"]


def test_optional_ct_failure_issues_without_sct(app, create_ca, ct_config, caplog):
    from models import CA
    from services.cert_service import CertificateService

    ca_data = create_ca(cn="CT Optional Test CA")
    ca_id = ca_data.get("id", ca_data.get("ca_id"))
    ct_config(ct_required=False)

    with patch("utils.ct_client.collect_precert_scts", return_value=[]):
        with app.app_context(), caplog.at_level("WARNING"):
            ca = CA.query.filter_by(id=ca_id).first()
            issued = CertificateService.create_certificate(
                descr="CT optional leaf",
                caref=ca.refid,
                dn={"CN": "ct-optional.example.com"},
                validity_days=30,
            )
            final_cert = x509.load_pem_x509_certificate(base64.b64decode(issued.crt))
            with pytest.raises(x509.ExtensionNotFound):
                final_cert.extensions.get_extension_for_oid(SCT_LIST_OID)

    assert "issuing without embedded SCT" in caplog.text


def test_required_ct_failure_refuses_issuance(app, create_ca, ct_config):
    from models import CA, Certificate
    from services.cert_service import CertificateService

    ca_data = create_ca(cn="CT Required Test CA")
    ca_id = ca_data.get("id", ca_data.get("ca_id"))
    ct_config(ct_required=True)

    with patch("utils.ct_client.collect_precert_scts", return_value=[]):
        with app.app_context():
            ca = CA.query.filter_by(id=ca_id).first()
            before = Certificate.query.filter_by(descr="CT required leaf").count()
            with pytest.raises(ValueError, match="Certificate Transparency is required"):
                CertificateService.create_certificate(
                    descr="CT required leaf",
                    caref=ca.refid,
                    dn={"CN": "ct-required.example.com"},
                    validity_days=30,
                )
            after = Certificate.query.filter_by(descr="CT required leaf").count()
            assert after == before
