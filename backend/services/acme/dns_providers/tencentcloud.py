"""
Tencent Cloud DNSPod Provider
https://cloud.tencent.com/document/product/1427
Auto-detects CN vs INT endpoint.
"""
import hashlib
import hmac
import json
import time
import datetime
import logging
from typing import Tuple, Dict, Any, Optional

import requests
from .base import BaseDnsProvider

logger = logging.getLogger(__name__)


class TencentCloudDnsProvider(BaseDnsProvider):
    PROVIDER_TYPE = "tencentcloud"
    PROVIDER_NAME = "Tencent Cloud DNSPod"
    PROVIDER_DESCRIPTION = "Tencent Cloud DNSPod API v3"
    PROVIDER_GROUP = "popular"
    REQUIRED_CREDENTIALS = ["secret_id", "secret_key"]
    OPTIONAL_CREDENTIALS = []

    # Both endpoints to try
    _CN_ENDPOINT = "https://dnspod.tencentcloudapi.com"
    _INTL_ENDPOINT = "https://dnspod.intl.tencentcloudapi.com"

    SERVICE = "dnspod"
    VERSION = "2021-03-23"

    # Unicode escapes: pure ASCII source, no GBK encoding issues
    _RECORD_LINE_CN = "\u9ed8\u8ba4"    # Default (CN)
    _RECORD_LINE_INT = "Default"         # Default (INT)

    _MIN_TTL = 600

    def __init__(self, credentials: Dict[str, Any]):
        super().__init__(credentials)
        self._zone_cache: Dict[str, Dict] = {}
        self.BASE_URL = self._CN_ENDPOINT
        self._record_line = self._RECORD_LINE_CN
        self._endpoint_detected = False

    def _ensure_endpoint(self):
        """Lazy auto-detect: try CN first, fall back to INT on auth failure."""
        if self._endpoint_detected:
            return
        self._endpoint_detected = True

        for url in [self._CN_ENDPOINT, self._INTL_ENDPOINT]:
            self.BASE_URL = url
            try:
                success, _ = self._post("DescribeDomainList", {"Offset": 0, "Limit": 1})
                if success:
                    is_intl = url == self._INTL_ENDPOINT
                    self._record_line = self._RECORD_LINE_INT if is_intl else self._RECORD_LINE_CN
                    logger.info(f"TencentCloud: detected endpoint {url}")
                    return
            except Exception:
                continue

        # Both failed — keep CN as default
        logger.warning("TencentCloud: endpoint auto-detect failed, staying on CN")

    # ─── Signature ───────────────────────────────────

    def _sign(self, key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _make_headers(self, action: str, payload: str) -> dict:
        secret_id = self.credentials["secret_id"]
        secret_key = self.credentials["secret_key"]
        timestamp = int(time.time())
        date = datetime.datetime.fromtimestamp(timestamp, datetime.UTC).strftime("%Y-%m-%d")

        host = self.BASE_URL.split("://")[1]
        canonical_headers = f"content-type:application/json\nhost:{host}\n"
        signed_headers = "content-type;host"
        hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        canonical_request = "\n".join([
            "POST", "/", "", canonical_headers, signed_headers, hashed_payload
        ])

        algorithm = "TC3-HMAC-SHA256"
        credential_scope = f"{date}/{self.SERVICE}/tc3_request"
        hashed_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = "\n".join([algorithm, str(timestamp), credential_scope, hashed_request])

        secret_date = self._sign(("TC3" + secret_key).encode("utf-8"), date)
        secret_service = self._sign(secret_date, self.SERVICE)
        secret_signing = self._sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        return {
            "Authorization": f"{algorithm} Credential={secret_id}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}",
            "Content-Type": "application/json",
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": self.VERSION,
        }

    # ─── Generic request ────────────────────────────

    def _post(self, action: str, params: dict) -> Tuple[bool, Any]:
        payload = json.dumps(params)
        headers = self._make_headers(action, payload)
        try:
            resp = requests.post(self.BASE_URL, headers=headers, data=payload, timeout=30)
            data = resp.json()
            if "Error" in data.get("Response", {}):
                err = data["Response"]["Error"]
                msg = f"{err.get('Code')}: {err.get('Message')}"
                logger.error(f"TencentCloud API error ({action}): {msg}")
                return False, msg
            return True, data["Response"]
        except Exception as e:
            msg = self.redact_secrets(str(e))
            logger.error(f"TencentCloud request error: {msg}")
            return False, msg

    # ─── Zone lookup with cache ─────────────────────

    def _get_zone(self, domain: str) -> Optional[Dict]:
        self._ensure_endpoint()

        if domain in self._zone_cache:
            return self._zone_cache[domain]

        parts = domain.split(".")
        for i in range(len(parts)):
            candidate = ".".join(parts[i:])
            success, result = self._post("DescribeDomain", {"Domain": candidate})
            if success:
                zone = {"name": candidate, "id": candidate}
                self._zone_cache[domain] = zone
                return zone

        return None

    # ─── Core interface ─────────────────────────────

    def create_txt_record(self, domain: str, record_name: str, record_value: str, ttl: int = 600) -> Tuple[bool, str]:
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find zone for domain {domain}"

        relative = self.get_relative_record_name(record_name, zone["name"]).rstrip(".")

        # Clamp TTL: DNSPod free/personal plans require TTL >= 600
        if ttl < self._MIN_TTL:
            ttl = self._MIN_TTL

        params = {
            "Domain": zone["name"],
            "RecordType": "TXT",
            "RecordLine": self._record_line,
            "RecordLineId": "0",
            "Value": record_value,
            "TTL": ttl,
            "SubDomain": relative,
        }

        success, result = self._post("CreateRecord", params)
        if not success:
            return False, f"Failed to create TXT record: {result}"

        record_id = result.get("RecordId")
        logger.info(f"TencentCloud: Created TXT record {record_name} (ID: {record_id})")
        return True, f"Record created successfully (ID: {record_id})"

    def delete_txt_record(self, domain: str, record_name: str, record_value: str) -> Tuple[bool, str]:
        zone = self._get_zone(domain)
        if not zone:
            return False, f"Could not find zone for domain {domain}"

        relative = self.get_relative_record_name(record_name, zone["name"]).rstrip(".")

        success, result = self._post("DescribeRecordList", {
            "Domain": zone["name"],
            "Subdomain": relative,
            "RecordType": "TXT",
        })

        # Empty record list is not an error
        if not success:
            err_msg = str(result)
            if any(kw in err_msg for kw in ("NoDataOfRecord", "ResourceNotFound", "NotFound")):
                return True, "Record not found (already deleted?)"
            return False, f"Failed to list records: {result}"

        records = [rec for rec in result.get("RecordList", [])
                   if self.txt_matches(rec.get("Value"), record_value)]
        if not records:
            return True, "Record not found (already deleted?)"

        deleted = []
        for rec in records:
            rec_id = rec.get("RecordId")
            ok, _ = self._post("DeleteRecord", {"Domain": zone["name"], "RecordId": rec_id})
            if ok:
                deleted.append(str(rec_id))

        if not deleted:
            return False, "Failed to delete any TXT records"
        logger.info(f"TencentCloud: Deleted TXT records {deleted} for {record_name}")
        return True, f"Deleted record IDs: {', '.join(deleted)}"

    def test_connection(self) -> Tuple[bool, str]:
        self._ensure_endpoint()
        try:
            success, result = self._post("DescribeDomainList", {"Offset": 0, "Limit": 5})
            if not success:
                return False, f"Connection failed: {result}"
            domains = result.get("DomainList", [])
            names = [d.get("Domain", d.get("Name", "")) for d in domains]
            endpoint_label = "INT" if self._INTL_ENDPOINT in self.BASE_URL else "CN"
            return True, f"Connected ({endpoint_label}). Found {len(domains)} domain(s): {', '.join(names[:5])}"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    @classmethod
    def get_credential_schema(cls) -> list:
        return [
            {"name": "secret_id", "label": "SecretId", "type": "text", "required": True,
             "help": "Tencent Cloud API SecretId"},
            {"name": "secret_key", "label": "SecretKey", "type": "password", "required": True,
             "help": "Tencent Cloud API SecretKey"},
        ]
