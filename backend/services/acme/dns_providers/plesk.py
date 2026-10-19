"""Plesk DNS provider using the Plesk XML API."""
import logging
import time
import warnings
import xml.etree.ElementTree as XmlBuilder
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import defusedxml.ElementTree as SafeXml
import requests
from urllib3.exceptions import InsecureRequestWarning

from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class PleskDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "plesk"
    PROVIDER_NAME = "Plesk"
    PROVIDER_DESCRIPTION = "Plesk XML API (self-hosted)"
    REQUIRED_CREDENTIALS = ["server_url", "api_key"]
    OPTIONAL_CREDENTIALS = ["verify_ssl", "propagation_delay_seconds"]

    API_PATH = "/enterprise/control/agent.php"

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self.endpoint = self._build_endpoint(self.credentials["server_url"])
        verify_ssl = self.credentials.get("verify_ssl", True)
        self.verify_ssl = verify_ssl if isinstance(verify_ssl, bool) else str(verify_ssl).lower() not in {"0", "false", "no"}
        try:
            self.propagation_delay_seconds = int(self.credentials.get("propagation_delay_seconds") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("Plesk propagation delay must be a whole number of seconds") from exc
        if self.propagation_delay_seconds < 0:
            raise ValueError("Plesk propagation delay must not be negative")
        self._sites_cache: Optional[List[Dict[str, Any]]] = None
        logger.info("Plesk DNS provider initialized for %s (verify_tls=%s)", self.endpoint, self.verify_ssl)
        if not self.verify_ssl:
            logger.warning(
                "Plesk TLS certificate verification is disabled for %s; enable it after installing a trusted certificate",
                self.endpoint,
            )

    @classmethod
    def _build_endpoint(cls, server_url: str) -> str:
        server_url = server_url.strip().rstrip("/")
        parsed = urlparse(server_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Plesk Server URL must be a valid HTTP or HTTPS URL")
        if parsed.query or parsed.fragment:
            raise ValueError("Plesk Server URL must not contain a query string or fragment")
        if parsed.path.rstrip("/").endswith(cls.API_PATH):
            return server_url
        return f"{server_url}{cls.API_PATH}"

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "text/xml",
            "Accept": "text/xml",
            "KEY": self.credentials["api_key"],
        }

    @staticmethod
    def _request_context(packet: XmlBuilder.Element) -> str:
        operator = next(iter(packet), None)
        operation = next(iter(operator), None) if operator is not None else None
        operator_name = operator.tag if operator is not None else "unknown"
        operation_name = operation.tag if operation is not None else "unknown"
        return f"{operator_name}.{operation_name}"

    def _request(self, packet: XmlBuilder.Element) -> Tuple[bool, Any]:
        payload = XmlBuilder.tostring(packet, encoding="utf-8", xml_declaration=True)
        context = self._request_context(packet)
        started = time.monotonic()
        logger.debug("Plesk XML API %s request to %s", context, self.endpoint)
        try:
            with warnings.catch_warnings():
                if not self.verify_ssl:
                    warnings.simplefilter("ignore", InsecureRequestWarning)
                response = requests.post(
                    self.endpoint,
                    headers=self._headers(),
                    data=payload,
                    timeout=30,
                    verify=self.verify_ssl,
                )
            elapsed_ms = (time.monotonic() - started) * 1000
            if response.status_code >= 400:
                diagnostic = self._error(response)
                logger.error(
                    "Plesk XML API %s failed after %.0f ms: %s",
                    context,
                    elapsed_ms,
                    diagnostic,
                )
                return False, diagnostic
            try:
                root = SafeXml.fromstring(response.text)
                packet_error = self._packet_error(root)
                if packet_error:
                    logger.error(
                        "Plesk XML API %s returned an application error after %.0f ms: %s",
                        context,
                        elapsed_ms,
                        packet_error,
                    )
                    return False, packet_error
                logger.debug(
                    "Plesk XML API %s completed with HTTP %s in %.0f ms (%d response chars)",
                    context,
                    response.status_code,
                    elapsed_ms,
                    len(response.text or ""),
                )
                return True, root
            except SafeXml.ParseError as exc:
                diagnostic = self._error(response, "Invalid XML response: ")
                diagnostic = f"{diagnostic} ({self._failure(exc)})"
                logger.error("Plesk XML API %s returned malformed XML: %s", context, diagnostic)
                return False, diagnostic
        except requests.RequestException as exc:
            diagnostic = self._failure(exc)
            elapsed_ms = (time.monotonic() - started) * 1000
            logger.error(
                "Plesk XML API %s transport failure after %.0f ms: %s",
                context,
                elapsed_ms,
                diagnostic,
            )
            return False, diagnostic

    def _packet_error(self, root: XmlBuilder.Element) -> Optional[str]:
        """Return errors outside an operator result, such as auth failures."""
        candidates = [
            root.find("./system/result"),
            root.find("./system"),
            root.find("./result"),
        ]
        for node in candidates:
            if node is None:
                continue
            if (node.findtext("status") or "").strip().lower() != "error":
                continue
            code = (node.findtext("errcode") or "unknown").strip()
            text = (node.findtext("errtext") or "Unknown Plesk packet error").strip()
            return self.redact_secrets(f"Plesk packet error {code}: {text}")
        return None

    def _operation_error(self, result: XmlBuilder.Element) -> str:
        code = (result.findtext("errcode") or "unknown").strip()
        text = (result.findtext("errtext") or "Unknown Plesk API error").strip()
        return self.redact_secrets(f"Plesk API error {code}: {text}")

    def _first_error(self, results: List[XmlBuilder.Element]) -> Optional[str]:
        for result in results:
            if (result.findtext("status") or "").strip().lower() == "error":
                return self._operation_error(result)
        return None

    @staticmethod
    def _packet(operator: str, operation: str) -> Tuple[XmlBuilder.Element, XmlBuilder.Element]:
        packet = XmlBuilder.Element("packet")
        operator_node = XmlBuilder.SubElement(packet, operator)
        operation_node = XmlBuilder.SubElement(operator_node, operation)
        return packet, operation_node

    def _get_sites(self) -> Tuple[bool, Any]:
        if self._sites_cache is not None:
            logger.debug("Using cached Plesk site list (%d site(s))", len(self._sites_cache))
            return True, self._sites_cache

        packet, operation = self._packet("site", "get")
        XmlBuilder.SubElement(operation, "filter")
        dataset = XmlBuilder.SubElement(operation, "dataset")
        XmlBuilder.SubElement(dataset, "gen_info")

        success, response = self._request(packet)
        if not success:
            logger.error("Plesk site discovery request failed: %s", response)
            return False, response

        results = response.findall("./site/get/result")
        if not results:
            response_xml = XmlBuilder.tostring(response, encoding="unicode")
            response_excerpt = self.redact_secrets(response_xml)[:self.MAX_ERROR_BODY_CHARS]
            logger.debug("Plesk site.get returned no result nodes; response XML: %s", response_excerpt)
        error = self._first_error(results)
        if error:
            logger.error("Plesk site discovery failed: %s", error)
            return False, error

        sites: List[Dict[str, Any]] = []
        for result in results:
            site_id = result.findtext("id")
            name = result.findtext("./data/gen_info/ascii-name") or result.findtext("./data/gen_info/name")
            if site_id and name:
                sites.append({"id": int(site_id), "name": self._normalise_name(name)})
        self._sites_cache = sites
        logger.info("Plesk site discovery found %d accessible site(s)", len(sites))
        logger.debug("Accessible Plesk sites: %s", ", ".join(site["name"] for site in sites) or "none")
        return True, sites

    def _find_site(self, name: str) -> Tuple[bool, Any]:
        success, sites = self._get_sites()
        if not success:
            return False, sites
        if not sites:
            message = (
                "Plesk returned no accessible sites; verify the API key owner has DNS permissions "
                "and remote XML API access is enabled"
            )
            logger.warning(message)
            return False, message
        site = self.find_zone(name, sites, key=lambda item: item["name"])
        if not site:
            message = f"Could not find Plesk site for {name}"
            logger.warning("%s; accessible sites: %s", message, ", ".join(item["name"] for item in sites) or "none")
            return False, message
        logger.debug("Matched %s to Plesk site %s (ID %s)", name, site["name"], site["id"])
        return True, site

    @classmethod
    def _relative_host(cls, record_name: str, zone: str) -> str:
        record_name = cls._normalise_name(record_name)
        zone = cls._normalise_name(zone)
        if record_name == zone:
            return ""
        suffix = f".{zone}"
        if record_name.endswith(suffix):
            return record_name[:-len(suffix)]
        return record_name

    @classmethod
    def _absolute_host(cls, host: str, zone: str) -> str:
        host = cls._normalise_name(host)
        zone = cls._normalise_name(zone)
        if not host or host == "@":
            return zone
        if host == zone or host.endswith(f".{zone}"):
            return host
        return f"{host}.{zone}"

    def create_txt_record(
        self,
        domain: str,
        record_name: str,
        record_value: str,
        ttl: int = 300,
    ) -> Tuple[bool, str]:
        del ttl  # Plesk applies the DNS zone's TTL; add_rec has no TTL field.
        record_name = self._normalise_name(record_name)
        logger.info("Plesk: Creating TXT record %s for domain %s", record_name, domain)
        success, site = self._find_site(record_name or domain)
        if not success:
            logger.error("Plesk: Cannot create TXT record %s: %s", record_name, site)
            return False, str(site)

        packet, operation = self._packet("dns", "add_rec")
        relative_host = self._relative_host(record_name, site["name"])
        logger.debug("Plesk: Using zone-relative host %s in site %s", relative_host or "@", site["name"])
        XmlBuilder.SubElement(operation, "site-id").text = str(site["id"])
        XmlBuilder.SubElement(operation, "type").text = "TXT"
        XmlBuilder.SubElement(operation, "host").text = relative_host
        XmlBuilder.SubElement(operation, "value").text = record_value

        success, response = self._request(packet)
        if not success:
            logger.error("Plesk: Failed to create TXT record %s: %s", record_name, response)
            return False, f"Failed to create record: {response}"
        result = response.find("./dns/add_rec/result")
        if result is None:
            logger.error("Plesk: add_rec returned no result for %s", record_name)
            return False, "Failed to create record: Plesk returned no result"
        if (result.findtext("status") or "").strip().lower() != "ok":
            diagnostic = self._operation_error(result)
            logger.error("Plesk: Failed to create TXT record %s: %s", record_name, diagnostic)
            return False, f"Failed to create record: {diagnostic}"

        record_id = result.findtext("id")
        logger.info("Plesk: Created TXT record %s", record_name)
        if self.propagation_delay_seconds:
            logger.info(
                "Plesk: Waiting %d second(s) for DNS propagation before continuing",
                self.propagation_delay_seconds,
            )
            time.sleep(self.propagation_delay_seconds)
        suffix = f" (ID {record_id})" if record_id else ""
        return True, f"Record created successfully{suffix}"

    def delete_txt_record(self, domain: str, record_name: str) -> Tuple[bool, str]:
        record_name = self._normalise_name(record_name)
        logger.info("Plesk: Deleting TXT record(s) for %s", record_name)
        success, site = self._find_site(record_name or domain)
        if not success:
            logger.error("Plesk: Cannot delete TXT record %s: %s", record_name, site)
            return False, str(site)

        packet, operation = self._packet("dns", "get_rec")
        record_filter = XmlBuilder.SubElement(operation, "filter")
        XmlBuilder.SubElement(record_filter, "site-id").text = str(site["id"])
        success, response = self._request(packet)
        if not success:
            logger.error("Plesk: Failed to list records for %s: %s", record_name, response)
            return False, f"Failed to list records: {response}"

        results = response.findall("./dns/get_rec/result")
        error = self._first_error(results)
        if error:
            logger.error("Plesk: Failed to list records for %s: %s", record_name, error)
            return False, f"Failed to list records: {error}"

        record_ids = []
        for result in results:
            record_type = (result.findtext("./data/type") or "").strip().upper()
            host = self._absolute_host(result.findtext("./data/host"), site["name"])
            record_id = result.findtext("id")
            if record_type == "TXT" and host == record_name and record_id:
                record_ids.append(record_id)

        if not record_ids:
            logger.info("Plesk: No matching TXT records found for %s", record_name)
            return True, "Record not found (already deleted?)"
        logger.debug("Plesk: Found %d matching TXT record(s) for %s", len(record_ids), record_name)

        delete_packet = XmlBuilder.Element("packet")
        dns = XmlBuilder.SubElement(delete_packet, "dns")
        for record_id in record_ids:
            delete_operation = XmlBuilder.SubElement(dns, "del_rec")
            delete_filter = XmlBuilder.SubElement(delete_operation, "filter")
            XmlBuilder.SubElement(delete_filter, "id").text = record_id

        success, response = self._request(delete_packet)
        if not success:
            logger.error("Plesk: Failed to delete TXT record %s: %s", record_name, response)
            return False, f"Failed to delete record: {response}"

        errors = []
        for result in response.findall("./dns/del_rec/result"):
            status = (result.findtext("status") or "").strip().lower()
            code = (result.findtext("errcode") or "").strip()
            if status == "error" and code != "1013":
                errors.append(self._operation_error(result))
        if errors:
            logger.error("Plesk: Failed to delete TXT record %s: %s", record_name, "; ".join(errors))
            return False, f"Failed to delete record: {'; '.join(errors)}"

        logger.info("Plesk: Deleted %d TXT record(s) for %s", len(record_ids), record_name)
        return True, f"Deleted {len(record_ids)} record(s) successfully"

    def test_connection(self) -> Tuple[bool, str]:
        logger.info("Testing Plesk DNS API connection to %s", self.endpoint)
        success, sites = self._get_sites()
        if not success:
            logger.error("Plesk DNS API connection test failed: %s", sites)
            return False, f"Connection failed: {sites}"
        names = [site["name"] for site in sites]
        sample = f": {', '.join(names[:5])}" if names else ""
        logger.info("Plesk DNS API connection test succeeded (%d accessible site(s))", len(sites))
        return True, f"Connected. Found {len(sites)} accessible site(s){sample}"

    @classmethod
    def get_credential_schema(cls) -> List[Dict[str, Any]]:
        return [
            {
                "name": "server_url",
                "label": "Plesk Server URL",
                "type": "text",
                "required": True,
                "help": "Plesk panel URL, for example https://plesk.example.com:8443",
            },
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "help": "Plesk secret key with permission to manage the hosted DNS zones",
            },
            {
                "name": "verify_ssl",
                "label": "Verify TLS Certificate",
                "type": "checkbox",
                "required": False,
                "default": True,
                "help": "Disable only when the Plesk server uses an untrusted self-signed certificate",
            },
            {
                "name": "propagation_delay_seconds",
                "label": "DNS Propagation Delay (seconds)",
                "type": "text",
                "required": False,
                "default": "0",
                "help": "Wait this long after creating the TXT record before starting ACME validation",
            },
        ]