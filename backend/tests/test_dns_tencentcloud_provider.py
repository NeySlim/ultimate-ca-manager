"""Tests for the Tencent Cloud DNSPod DNS provider (PR #284).

All HTTP is mocked; no real Tencent API calls.
"""
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest

from services.acme.dns_providers import PROVIDER_REGISTRY, get_provider_class, create_provider
from services.acme.dns_providers.tencentcloud import TencentCloudDnsProvider

CREDS = {"secret_id": "AKIDTEST123", "secret_key": "sk-test-value-abc"}


def _resp(payload):
    """Fake requests.Response carrying a Tencent-shaped JSON body."""
    r = MagicMock()
    r.json.return_value = payload
    r.status_code = 200
    return r


def _error_resp(code="AuthFailure", message="signature error"):
    return _resp({"Response": {"Error": {"Code": code, "Message": message}}})


def _requests_router(handlers):
    """Return a requests.post replacement dispatching on X-TC-Action header."""
    def _fake_post(url, headers=None, data=None, timeout=None):
        action = headers.get("X-TC-Action")
        handler = handlers.get(url, {}).get(action)
        if handler is None:
            raise AssertionError(f"Unexpected request: {url} action={action}")
        return handler(url, headers, json.loads(data))
    return _fake_post


@pytest.fixture
def provider():
    return TencentCloudDnsProvider(dict(CREDS))


class TestRegistration:
    def test_registered_in_registry(self):
        assert "tencentcloud" in PROVIDER_REGISTRY
        assert get_provider_class("tencentcloud") is TencentCloudDnsProvider

    def test_create_provider_factory(self):
        p = create_provider("tencentcloud", dict(CREDS))
        assert isinstance(p, TencentCloudDnsProvider)

    def test_missing_credentials_rejected(self):
        with pytest.raises(ValueError, match="Missing required credentials"):
            TencentCloudDnsProvider({})

    def test_credential_schema(self):
        schema = TencentCloudDnsProvider.get_credential_schema()
        assert [f["name"] for f in schema] == ["secret_id", "secret_key"]
        assert schema[0]["type"] == "text" and schema[0]["required"]
        assert schema[1]["type"] == "password" and schema[1]["required"]

    def test_to_dict_metadata(self):
        d = TencentCloudDnsProvider.to_dict()
        assert d["type"] == "tencentcloud"
        assert d["name"] == "Tencent Cloud DNSPod"


class TestSignature:
    def test_headers_shape(self, provider):
        headers = provider._make_headers("DescribeDomainList", '{"Offset":0,"Limit":1}')
        assert headers["X-TC-Action"] == "DescribeDomainList"
        assert headers["X-TC-Version"] == "2021-03-23"
        assert headers["X-TC-Timestamp"].isdigit()
        assert headers["Host"] == "dnspod.tencentcloudapi.com"
        auth = headers["Authorization"]
        assert auth.startswith("TC3-HMAC-SHA256 Credential=AKIDTEST123/")
        assert "/dnspod/tc3_request" in auth
        assert "SignedHeaders=content-type;host" in auth

    def test_signature_matches_tc3_spec(self, provider):
        """Recompute the TC3-HMAC-SHA256 signature from headers and cross-check."""
        timestamp = 1700000000
        with patch("services.acme.dns_providers.tencentcloud.time.time", return_value=timestamp):
            headers = provider._make_headers("TestAction", "{}")
        date = "2023-11-14"
        payload = "{}"
        canonical_headers = "content-type:application/json\nhost:dnspod.tencentcloudapi.com\n"
        hashed_payload = hashlib.sha256(payload.encode()).hexdigest()
        canonical_request = "\n".join(
            ["POST", "/", "", canonical_headers, "content-type;host", hashed_payload]
        )
        credential_scope = f"{date}/dnspod/tc3_request"
        string_to_sign = "\n".join([
            "TC3-HMAC-SHA256", str(timestamp), credential_scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ])
        k_date = hmac.new(("TC3" + CREDS["secret_key"]).encode(), date.encode(), hashlib.sha256).digest()
        k_svc = hmac.new(k_date, b"dnspod", hashlib.sha256).digest()
        k_sign = hmac.new(k_svc, b"tc3_request", hashlib.sha256).digest()
        expected = hmac.new(k_sign, string_to_sign.encode(), hashlib.sha256).hexdigest()
        assert f"Signature={expected}" in headers["Authorization"]

    def test_host_follows_base_url(self, provider):
        provider.BASE_URL = TencentCloudDnsProvider._INTL_ENDPOINT
        headers = provider._make_headers("TestAction", "{}")
        assert headers["Host"] == "dnspod.intl.tencentcloudapi.com"


class TestEndpointDetection:
    def test_cn_success_keeps_cn(self, provider):
        h = {TencentCloudDnsProvider._CN_ENDPOINT: {
            "DescribeDomainList": lambda u, h_, b: _resp({"Response": {"TotalCount": 0, "DomainList": []}})
        }}
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)):
            provider._ensure_endpoint()
        assert provider.BASE_URL == TencentCloudDnsProvider._CN_ENDPOINT
        assert provider._record_line == "默认"

    def test_cn_auth_failure_falls_back_to_intl(self, provider):
        h = {
            TencentCloudDnsProvider._CN_ENDPOINT: {
                "DescribeDomainList": lambda u, h_, b: _error_resp("AuthFailure", "invalid secret")
            },
            TencentCloudDnsProvider._INTL_ENDPOINT: {
                "DescribeDomainList": lambda u, h_, b: _resp({"Response": {"TotalCount": 0, "DomainList": []}})
            },
        }
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)):
            provider._ensure_endpoint()
        assert provider.BASE_URL == TencentCloudDnsProvider._INTL_ENDPOINT
        assert provider._record_line == "Default"

    def test_detection_runs_once(self, provider):
        h = {TencentCloudDnsProvider._CN_ENDPOINT: {
            "DescribeDomainList": lambda u, h_, b: _resp({"Response": {"TotalCount": 0, "DomainList": []}})
        }}
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)) as m:
            provider._ensure_endpoint()
            provider._ensure_endpoint()
        assert m.call_count == 1


class TestCreateTxtRecord:
    def _handlers(self):
        h = {TencentCloudDnsProvider._CN_ENDPOINT: {}}
        cn = h[TencentCloudDnsProvider._CN_ENDPOINT]
        cn["DescribeDomainList"] = lambda u, h_, b: _resp({"Response": {"TotalCount": 0, "DomainList": []}})

        def describe_domain(u, h_, b):
            domain = b["Domain"]
            if domain == "example.com":
                return _resp({"Response": {"DomainInfo": {"Domain": "example.com"}}})
            return _error_resp("ResourceNotFound.NoDataOfRecord", "404")

        cn["DescribeDomain"] = describe_domain

        captured = {}

        def create_record(u, h_, b):
            captured.update(b)
            return _resp({"Response": {"RecordId": 12345}})

        cn["CreateRecord"] = create_record
        return h, captured

    def test_create_success(self, provider):
        h, captured = self._handlers()
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)):
            ok, msg = provider.create_txt_record(
                "example.com", "_acme-challenge.example.com", "txtvalue", ttl=300
            )
        assert ok, msg
        assert "12345" in msg
        assert captured["Domain"] == "example.com"
        assert captured["SubDomain"] == "_acme-challenge"
        assert captured["Value"] == "txtvalue"
        assert captured["RecordType"] == "TXT"
        assert captured["RecordLine"] == "默认"

    def test_ttl_clamped_to_600(self, provider):
        h, captured = self._handlers()
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)):
            ok, _ = provider.create_txt_record(
                "example.com", "_acme-challenge.example.com", "txtvalue", ttl=60
            )
        assert ok
        assert captured["TTL"] == 600

    def test_zone_not_found(self, provider):
        h, _ = self._handlers()
        cn = h[TencentCloudDnsProvider._CN_ENDPOINT]
        cn["DescribeDomain"] = lambda u, h_, b: _error_resp("ResourceNotFound.NoDataOfRecord", "404")
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)):
            ok, msg = provider.create_txt_record(
                "unknown.tld", "_acme-challenge.unknown.tld", "v"
            )
        assert not ok
        assert "Could not find zone" in msg

    def test_create_api_error(self, provider):
        h, _ = self._handlers()
        h[TencentCloudDnsProvider._CN_ENDPOINT]["CreateRecord"] = (
            lambda u, h_, b: _error_resp("LimitExceeded", "too many records")
        )
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)):
            ok, msg = provider.create_txt_record(
                "example.com", "_acme-challenge.example.com", "v"
            )
        assert not ok
        assert "LimitExceeded" in msg

    def test_zone_cache(self, provider):
        h, _ = self._handlers()
        counter = {"n": 0}
        describe = h[TencentCloudDnsProvider._CN_ENDPOINT]["DescribeDomain"]

        def counting(u, h_, b):
            counter["n"] += 1
            return describe(u, h_, b)

        h[TencentCloudDnsProvider._CN_ENDPOINT]["DescribeDomain"] = counting
        describe_calls_before = counter["n"]
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)):
            provider.create_txt_record("example.com", "_acme-challenge.example.com", "v1")
            first_calls = counter["n"] - describe_calls_before
            provider.create_txt_record("example.com", "_acme-challenge.example.com", "v2")
        # Second call must hit the cache — no additional DescribeDomain
        assert counter["n"] - describe_calls_before == first_calls
        assert "example.com" in provider._zone_cache


class TestDeleteTxtRecord:
    def _handlers(self, records):
        h = {TencentCloudDnsProvider._CN_ENDPOINT: {}}
        cn = h[TencentCloudDnsProvider._CN_ENDPOINT]
        cn["DescribeDomainList"] = lambda u, h_, b: _resp({"Response": {"TotalCount": 0, "DomainList": []}})
        cn["DescribeDomain"] = lambda u, h_, b: _resp({"Response": {"DomainInfo": {"Domain": "example.com"}}} if b["Domain"] == "example.com" else _error_resp("ResourceNotFound.NoDataOfRecord", "404"))
        if records is None:
            cn["DescribeRecordList"] = lambda u, h_, b: _error_resp("ResourceNotFound.NoDataOfRecord", "no record")
        else:
            cn["DescribeRecordList"] = lambda u, h_, b: _resp({"Response": {"RecordList": records}})
        deleted = []

        def delete_record(u, h_, b):
            deleted.append(b["RecordId"])
            return _resp({"Response": {"RequestId": "ok"}})

        cn["DeleteRecord"] = delete_record
        return h, deleted

    def test_delete_only_the_matching_value(self, provider):
        records = [{"RecordId": 101, "Value": "apex"}, {"RecordId": 102, "Value": "wild"},
                   {"RecordId": 103, "Value": "apex"}]
        h, deleted = self._handlers(records)
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)):
            ok, msg = provider.delete_txt_record("example.com", "_acme-challenge.example.com", "apex")
        assert ok, msg
        assert deleted == [101, 103]

    def test_other_value_only_is_already_deleted(self, provider):
        h, deleted = self._handlers([{"RecordId": 102, "Value": "wild"}])
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)):
            ok, msg = provider.delete_txt_record("example.com", "_acme-challenge.example.com", "apex")
        assert ok and "not found" in msg.lower()
        assert deleted == []

    def test_delete_empty_list_is_success(self, provider):
        h, _ = self._handlers(records=[])
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)):
            ok, msg = provider.delete_txt_record("example.com", "_acme-challenge.example.com", "apex")
        assert ok
        assert "not found" in msg.lower()

    def test_delete_not_found_error_is_success(self, provider):
        h, _ = self._handlers(records=None)
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)):
            ok, msg = provider.delete_txt_record("example.com", "_acme-challenge.example.com", "apex")
        assert ok


class TestTestConnection:
    def test_success_lists_domains(self, provider):
        h = {TencentCloudDnsProvider._CN_ENDPOINT: {
            "DescribeDomainList": lambda u, h_, b: _resp({
                "Response": {"TotalCount": 2, "DomainList": [{"Domain": "example.com"}, {"Domain": "test.org"}]}
            })
        }}
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)):
            ok, msg = provider.test_connection()
        assert ok, msg
        assert "CN" in msg and "example.com" in msg

    def test_failure_returns_error(self, provider):
        h = {TencentCloudDnsProvider._CN_ENDPOINT: {
            "DescribeDomainList": lambda u, h_, b: _error_resp("AuthFailure", "invalid secret")
        }, TencentCloudDnsProvider._INTL_ENDPOINT: {
            "DescribeDomainList": lambda u, h_, b: _error_resp("AuthFailure", "invalid secret")
        }}
        with patch("services.acme.dns_providers.tencentcloud.requests.post", side_effect=_requests_router(h)):
            ok, msg = provider.test_connection()
        assert not ok


class TestSecretRedaction:
    def test_credentials_not_leaked_in_errors(self):
        creds = {"secret_id": "AKIDTEST123", "secret_key": "sk-supersecret-xyz789"}
        p = TencentCloudDnsProvider(dict(creds))
        with patch(
            "services.acme.dns_providers.tencentcloud.requests.post",
            side_effect=ConnectionError(f"Connection failed to https://dnspod.tencentcloudapi.com using key sk-supersecret-xyz789"),
        ):
            ok, msg = p._post("DescribeDomainList", {"Offset": 0, "Limit": 1})
        assert not ok
        assert "sk-supersecret-xyz789" not in msg
        assert "***" in msg
