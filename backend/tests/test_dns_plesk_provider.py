"""Tests for the Plesk XML API DNS provider."""
import logging
from unittest.mock import MagicMock, patch

import defusedxml.ElementTree as ET
import pytest

from services.acme.dns_providers import PROVIDER_REGISTRY, create_provider, get_provider_class
from services.acme.dns_providers.plesk import PleskDnsProvider


CREDS = {
    "server_url": "https://plesk.example.com:8443",
    "api_key": "secret-api-key-value",
}


def _response(xml: str, status_code: int = 200, reason: str = "OK") -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.reason = reason
    response.text = xml
    return response


def _sites_response(*sites: tuple[int, str]) -> str:
    results = "".join(
        f"""
        <result>
          <status>ok</status><id>{site_id}</id>
          <data><gen_info><name>{name}</name><ascii-name>{name}</ascii-name></gen_info></data>
        </result>
        """
        for site_id, name in sites
    )
    return f"<packet><site><get>{results}</get></site></packet>"


@pytest.fixture
def provider() -> PleskDnsProvider:
    return PleskDnsProvider(dict(CREDS))


class TestRegistration:
    def test_registered_in_registry(self):
        assert PROVIDER_REGISTRY["plesk"] is PleskDnsProvider
        assert get_provider_class("plesk") is PleskDnsProvider
        assert isinstance(create_provider("plesk", dict(CREDS)), PleskDnsProvider)

    def test_metadata_and_credentials(self):
        metadata = PleskDnsProvider.to_dict()
        assert metadata["type"] == "plesk"
        assert metadata["name"] == "Plesk"
        schema = metadata["credentials_schema"]
        assert [field["name"] for field in schema] == [
            "server_url", "api_key", "verify_ssl", "propagation_delay_seconds"
        ]
        assert schema[1]["type"] == "password"
        assert schema[2]["type"] == "checkbox"
        assert schema[3]["type"] == "text"
        assert schema[3]["default"] == "0"

    def test_missing_credentials_rejected(self):
        with pytest.raises(ValueError, match="server_url, api_key"):
            PleskDnsProvider({})

    @pytest.mark.parametrize("delay", ["invalid", -1])
    def test_invalid_propagation_delay_rejected(self, delay):
        with pytest.raises(ValueError, match="propagation delay"):
            PleskDnsProvider({**CREDS, "propagation_delay_seconds": delay})


class TestTransport:
    def test_posts_xml_to_plesk_endpoint(self, provider, caplog):
        with caplog.at_level(logging.DEBUG, logger="services.acme.dns_providers.plesk"):
            with patch(
                "services.acme.dns_providers.plesk.requests.post",
                return_value=_response(_sites_response((1, "example.com"))),
            ) as post:
                ok, message = provider.test_connection()

        assert ok, message
        assert "example.com" in message
        call = post.call_args
        assert call.args[0] == "https://plesk.example.com:8443/enterprise/control/agent.php"
        assert call.kwargs["headers"]["KEY"] == CREDS["api_key"]
        assert call.kwargs["headers"]["Content-Type"] == "text/xml"
        assert call.kwargs["timeout"] == 30
        assert call.kwargs["verify"] is True
        packet = ET.fromstring(call.kwargs["data"])
        assert packet.find("./site/get/filter") is not None
        assert packet.find("./site/get/dataset/gen_info") is not None
        assert "site.get" in caplog.text
        assert "HTTP 200" in caplog.text
        assert CREDS["api_key"] not in caplog.text

    def test_accepts_full_endpoint_and_tls_opt_out(self):
        provider = PleskDnsProvider({
            **CREDS,
            "server_url": "https://plesk.example.com:8443/enterprise/control/agent.php",
            "verify_ssl": "false",
        })
        with patch(
            "services.acme.dns_providers.plesk.requests.post",
            return_value=_response(_sites_response()),
        ) as post:
            assert provider.test_connection()[0]

        assert post.call_args.args[0].endswith("/enterprise/control/agent.php")
        assert post.call_args.kwargs["verify"] is False

    def test_tls_opt_out_logs_controlled_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="services.acme.dns_providers.plesk"):
            PleskDnsProvider({**CREDS, "verify_ssl": False})

        assert "TLS certificate verification is disabled" in caplog.text

    def test_rejects_malformed_url(self):
        with pytest.raises(ValueError, match="valid HTTP or HTTPS URL"):
            PleskDnsProvider({**CREDS, "server_url": "plesk.example.com"})

    def test_handles_http_xml_and_parse_errors_without_leaking_key(self, provider, caplog):
        responses = [
            _response(f"refused {CREDS['api_key']}", 401, "Unauthorized"),
            _response("<packet><site><get><result><status>error</status><errcode>1006</errcode>"
                      f"<errtext>Permission denied for {CREDS['api_key']}</errtext>"
                      "</result></get></site></packet>"),
            _response("not xml"),
        ]
        with caplog.at_level(logging.DEBUG, logger="services.acme.dns_providers.plesk"):
            with patch("services.acme.dns_providers.plesk.requests.post", side_effect=responses):
                http_ok, http_message = provider.test_connection()
                xml_ok, xml_message = provider.test_connection()
                parse_ok, parse_message = provider.test_connection()

        assert not http_ok and CREDS["api_key"] not in http_message and "***" in http_message
        assert not xml_ok and "1006" in xml_message and "Permission denied" in xml_message
        assert CREDS["api_key"] not in xml_message and "***" in xml_message
        assert not parse_ok and "XML" in parse_message
        assert "HTTP 401 Unauthorized" in caplog.text
        assert "Plesk API error 1006" in caplog.text
        assert "Invalid XML response" in caplog.text
        assert CREDS["api_key"] not in caplog.text

    def test_reports_packet_level_system_error(self, provider, caplog):
        response = """
        <packet version="1.6.9.1"><system><status>error</status><errcode>1003</errcode>
          <errtext>Authentication failed</errtext></system></packet>
        """
        with caplog.at_level(logging.ERROR, logger="services.acme.dns_providers.plesk"):
            with patch("services.acme.dns_providers.plesk.requests.post", return_value=_response(response)):
                ok, message = provider.test_connection()

        assert not ok
        assert "packet error 1003" in message
        assert "Authentication failed" in message
        assert message.removeprefix("Connection failed: ") in caplog.text

    def test_empty_site_list_returns_actionable_message(self, provider):
        with patch(
            "services.acme.dns_providers.plesk.requests.post",
            return_value=_response(_sites_response()),
        ):
            ok, message = provider.create_txt_record(
                "example.com", "_acme-challenge.example.com", "value"
            )

        assert not ok
        assert "no accessible sites" in message.lower()
        assert "DNS permissions" in message


class TestCreateTxtRecord:
    def test_uses_longest_site_match_and_escapes_xml(self, provider):
        responses = [
            _response(_sites_response((1, "example.com"), (2, "sub.example.com"))),
            _response("<packet><dns><add_rec><result><status>ok</status><id>42</id>"
                      "</result></add_rec></dns></packet>"),
        ]
        with patch("services.acme.dns_providers.plesk.requests.post", side_effect=responses) as post:
            ok, message = provider.create_txt_record(
                "sub.example.com",
                "_acme-challenge.sub.example.com.",
                "token<&value",
                ttl=120,
            )

        assert ok, message
        assert "42" in message
        packet = ET.fromstring(post.call_args_list[1].kwargs["data"])
        operation = packet.find("./dns/add_rec")
        assert operation.findtext("site-id") == "2"
        assert operation.findtext("type") == "TXT"
        assert operation.findtext("host") == "_acme-challenge"
        assert operation.findtext("value") == "token<&value"
        assert operation.find("ttl") is None

    def test_waits_configured_delay_after_successful_create(self):
        provider = PleskDnsProvider({**CREDS, "propagation_delay_seconds": "15"})
        responses = [
            _response(_sites_response((1, "example.com"))),
            _response("<packet><dns><add_rec><result><status>ok</status><id>42</id>"
                      "</result></add_rec></dns></packet>"),
        ]
        with patch("services.acme.dns_providers.plesk.requests.post", side_effect=responses):
            with patch("services.acme.dns_providers.plesk.time.sleep") as sleep:
                ok, message = provider.create_txt_record(
                    "example.com", "_acme-challenge.example.com", "value"
                )

        assert ok, message
        sleep.assert_called_once_with(15)

    def test_reports_unknown_zone(self, provider, caplog):
        with caplog.at_level(logging.WARNING, logger="services.acme.dns_providers.plesk"):
            with patch(
                "services.acme.dns_providers.plesk.requests.post",
                return_value=_response(_sites_response((1, "example.com"))),
            ):
                ok, message = provider.create_txt_record("unknown.test", "_acme-challenge.unknown.test", "value")

        assert not ok
        assert "Could not find Plesk site" in message
        assert message in caplog.text


class TestDeleteTxtRecord:
    def test_deletes_only_matching_txt_record_ids(self, provider):
        records = """
        <packet><dns><get_rec>
          <result><status>ok</status><id>10</id><data><site-id>1</site-id><type>TXT</type>
            <host>_acme-challenge.example.com</host><value>first</value></data></result>
          <result><status>ok</status><id>11</id><data><site-id>1</site-id><type>A</type>
            <host>_acme-challenge.example.com</host><value>192.0.2.1</value></data></result>
          <result><status>ok</status><id>12</id><data><site-id>1</site-id><type>TXT</type>
            <host>other.example.com</host><value>keep</value></data></result>
          <result><status>ok</status><id>13</id><data><site-id>1</site-id><type>TXT</type>
                        <host>_acme-challenge</host><value>second</value></data></result>
        </get_rec></dns></packet>
        """
        deleted = """
        <packet><dns>
          <del_rec><result><status>ok</status><id>10</id></result></del_rec>
          <del_rec><result><status>ok</status><id>13</id></result></del_rec>
        </dns></packet>
        """
        responses = [_response(_sites_response((1, "example.com"))), _response(records), _response(deleted)]
        with patch("services.acme.dns_providers.plesk.requests.post", side_effect=responses) as post:
            ok, message = provider.delete_txt_record("example.com", "_acme-challenge.example.com")

        assert ok, message
        packet = ET.fromstring(post.call_args_list[2].kwargs["data"])
        assert [node.text for node in packet.findall("./dns/del_rec/filter/id")] == ["10", "13"]

    def test_no_matching_record_is_success(self, provider):
        responses = [
            _response(_sites_response((1, "example.com"))),
            _response("<packet><dns><get_rec/></dns></packet>"),
        ]
        with patch("services.acme.dns_providers.plesk.requests.post", side_effect=responses) as post:
            ok, message = provider.delete_txt_record("example.com", "_acme-challenge.example.com")

        assert ok
        assert "not found" in message.lower()
        assert post.call_count == 2

    def test_1013_delete_error_is_idempotent(self, provider):
        records = """
        <packet><dns><get_rec><result><status>ok</status><id>10</id><data><type>TXT</type>
          <host>_acme-challenge.example.com</host><value>value</value></data></result></get_rec></dns></packet>
        """
        deleted = """
        <packet><dns><del_rec><result><status>error</status><errcode>1013</errcode>
          <errtext>DNS record does not exist.</errtext><id>10</id></result></del_rec></dns></packet>
        """
        responses = [_response(_sites_response((1, "example.com"))), _response(records), _response(deleted)]
        with patch("services.acme.dns_providers.plesk.requests.post", side_effect=responses):
            ok, message = provider.delete_txt_record("example.com", "_acme-challenge.example.com")

        assert ok, message

    def test_site_lookup_is_cached(self, provider):
        records = "<packet><dns><get_rec/></dns></packet>"
        responses = [_response(_sites_response((1, "example.com"))), _response(records), _response(records)]
        with patch("services.acme.dns_providers.plesk.requests.post", side_effect=responses) as post:
            assert provider.delete_txt_record("example.com", "_acme-challenge.example.com")[0]
            assert provider.delete_txt_record("example.com", "_acme-challenge.example.com")[0]

        assert post.call_count == 3