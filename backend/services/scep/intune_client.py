"""
Microsoft Intune SCEP challenge validation client (issue #228 part 2).

Intune doesn't support a static SCEP challenge password: it issues a
per-device, per-request encrypted+signed challenge blob that only Intune's
own API can validate. This module talks to that API on behalf of an
Intune-enabled ScepProfile.

There is no published REST spec for this -- Microsoft ships a reference
client library instead (Java/C#) and documents only its method signatures
(https://learn.microsoft.com/en-us/intune/fundamentals/certificates/ref-scep-api).
The wire contract below was read directly out of Microsoft's own MIT-licensed
reference implementation
(github.com/microsoft/Intune-Resource-Access, src/CsrValidation/csharp/ScepValidation/
IntuneClient.cs, IntuneServiceLocationProvider.cs, IntuneScepValidator.cs, MsalClient.cs)
rather than reconstructed from the summary docs, so behavior here should match
that reference client call-for-call:

1. Auth: OAuth2 client-credentials grant against
   ``https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token``. Two
   different scopes are needed for two different downstream calls: a Graph
   token for service discovery, and an Intune-resource token for the actual
   ScepActions/* calls.
2. Service discovery: GET Graph's
   ``servicePrincipals/appId={INTUNE_APP_ID}/endpoints`` (Intune's own
   well-known first-party app id) to find the tenant-specific, sharded base
   URL for the "ScepRequestValidationFEService". This is NOT a fixed URL --
   it varies per tenant/region and must be discovered, then cached.
3. ScepActions/validateRequest, ScepActions/successNotification,
   ScepActions/failureNotification: POSTs to that discovered base URL, bearer
   auth with the Intune-resource token, ``api-version: 2018-02-20``.

The INTUNE_RESOURCE_URL scope literally becomes
``"https://api.manage.microsoft.com/" + "/.default"`` in the reference
client (a double slash, since the constant already ends in "/") -- kept
byte-for-byte here rather than "fixed", since this is the exact string
Microsoft's own client sends and AAD scope strings are opaque to us.
"""

import base64
import logging
import time
import uuid
from datetime import timezone
from enum import Enum
from typing import Optional

import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes

from config.settings import Config

logger = logging.getLogger(__name__)

AUTHORITY = "https://login.microsoftonline.com/"
GRAPH_RESOURCE_URL = "https://graph.microsoft.com/"
INTUNE_RESOURCE_URL = "https://api.manage.microsoft.com/"
INTUNE_APP_ID = "0000000a-0000-0000-c000-000000000000"

VALIDATION_SERVICE_NAME = "sceprequestvalidationfeservice"  # lowercased providerName
API_VERSION = "2018-02-20"
VALIDATE_URL = "ScepActions/validateRequest"
NOTIFY_SUCCESS_URL = "ScepActions/successNotification"
NOTIFY_FAILURE_URL = "ScepActions/failureNotification"

# Refresh a cached token this many seconds before its real expiry, same
# defensive margin any client-credentials cache needs against clock skew /
# in-flight request latency.
TOKEN_EXPIRY_MARGIN_SECONDS = 60

REQUEST_TIMEOUT_SECONDS = 30


class IntuneScepErrorCode(Enum):
    """Mirrors Microsoft's own ErrorCode enum (IntuneScepServiceException.cs)."""
    UNKNOWN = "Unknown"
    SUCCESS = "Success"
    CERTIFICATE_REQUEST_DECODING_FAILED = "CertificateRequestDecodingFailed"
    CHALLENGE_PASSWORD_MISSING = "ChallengePasswordMissing"
    CHALLENGE_DESERIALIZATION_ERROR = "ChallengeDeserializationError"
    CHALLENGE_DECRYPTION_ERROR = "ChallengeDecryptionError"
    CHALLENGE_DECODING_ERROR = "ChallengeDecodingError"
    CHALLENGE_INVALID_TIMESTAMP = "ChallengeInvalidTimestamp"
    CHALLENGE_EXPIRED = "ChallengeExpired"
    SUBJECT_NAME_MISSING = "SubjectNameMissing"
    SUBJECT_NAME_MISMATCH = "SubjectNameMismatch"
    SUBJECT_ALT_NAME_MISSING = "SubjectAltNameMissing"
    SUBJECT_ALT_NAME_MISMATCH = "SubjectAltNameMismatch"
    KEY_USAGE_MISMATCH = "KeyUsageMismatch"
    KEY_LENGTH_MISMATCH = "KeyLengthMismatch"
    ENHANCED_KEY_USAGE_MISSING = "EnhancedKeyUsageMissing"
    ENHANCED_KEY_USAGE_MISMATCH = "EnhancedKeyUsageMismatch"
    AAD_KEY_IDENTIFIER_LIST_MISSING = "AadKeyIdentifierListMissing"
    REGISTERED_KEY_MISMATCH = "RegisteredKeyMismatch"
    SIGNING_CERT_THUMBPRINT_MISMATCH = "SigningCertThumbprintMismatch"
    SCEP_PROFILE_NO_LONGER_TARGETED = "ScepProfileNoLongerTargetedToTheClient"
    SIGNATURE_VALIDATION_FAILED = "SignatureValidationFailed"
    BAD_CERTIFICATE_REQUEST_ID_IN_CHALLENGE = "BadCertificateRequestIdInChallenge"
    BAD_DEVICE_ID_IN_CHALLENGE = "BadDeviceIdInChallenge"
    BAD_USER_ID_IN_CHALLENGE = "BadUserIdInChallenge"

    @classmethod
    def parse(cls, raw: Optional[str]) -> "IntuneScepErrorCode":
        try:
            return cls(raw)
        except ValueError:
            return cls.UNKNOWN


class IntuneScepError(Exception):
    """Raised for any failure talking to Intune's SCEP validation API --
    covers both a real validation rejection (code != Success) and transport
    failures (network error, malformed response), since both mean the same
    thing to the caller: do not trust this request, do not issue a cert.
    """

    def __init__(self, message: str, code: IntuneScepErrorCode = IntuneScepErrorCode.UNKNOWN,
                 description: str = ''):
        super().__init__(message)
        self.code = code
        self.description = description


class IntuneScepClient:
    """Talks to Microsoft Intune's SCEP challenge validation API for one
    profile's Entra app registration. Construction does no network I/O --
    tokens and the service endpoint are fetched lazily and cached on first
    use.
    """

    def __init__(self, tenant_id: str, client_id: str, client_secret: str,
                 provider_name: Optional[str] = None):
        if not tenant_id or not client_id or not client_secret:
            raise ValueError("tenant_id, client_id and client_secret are all required")
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.provider_name = provider_name or f"UltimateCAManager/{Config.APP_VERSION}"

        self._tokens = {}  # scope -> (token, expires_at_monotonic)
        self._service_endpoint = None

    # ---- Auth ----------------------------------------------------------

    def _get_token(self, scope: str) -> str:
        cached = self._tokens.get(scope)
        if cached and cached[1] > time.monotonic():
            return cached[0]

        resp = requests.post(
            f"{AUTHORITY}{self.tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": scope,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise IntuneScepError(
                f"Failed to acquire Intune/Entra token for scope {scope!r}: {e}"
            ) from e

        body = resp.json()
        token = body.get("access_token")
        if not token:
            raise IntuneScepError(
                f"Entra token response for scope {scope!r} had no access_token"
            )
        expires_in = int(body.get("expires_in", 3600))
        self._tokens[scope] = (
            token,
            time.monotonic() + max(expires_in - TOKEN_EXPIRY_MARGIN_SECONDS, 0),
        )
        return token

    def _graph_token(self) -> str:
        return self._get_token(f"{GRAPH_RESOURCE_URL}.default")

    def _intune_token(self) -> str:
        # Deliberately not "fixed": see module docstring.
        return self._get_token(f"{INTUNE_RESOURCE_URL}/.default")

    # ---- Service discovery ----------------------------------------------

    def _discover_service_endpoint(self) -> str:
        token = self._graph_token()
        resp = requests.get(
            f"{GRAPH_RESOURCE_URL}v1.0/servicePrincipals/appId={INTUNE_APP_ID}/endpoints",
            headers={
                "Authorization": f"Bearer {token}",
                "client-request-id": str(uuid.uuid4()),
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise IntuneScepError(f"Intune service discovery via Graph failed: {e}") from e

        body = resp.json()
        entries = body.get("value")
        if entries is None:
            raise IntuneScepError(
                "Intune service discovery response had no 'value' array"
            )

        for entry in entries:
            name = entry.get("providerName") or entry.get("serviceName") or ""
            if name.lower() == VALIDATION_SERVICE_NAME:
                uri = entry.get("uri")
                if uri:
                    return uri

        raise IntuneScepError(
            f"Intune service discovery did not return an endpoint for "
            f"{VALIDATION_SERVICE_NAME!r} (tenant={self.tenant_id})"
        )

    def _get_service_endpoint(self) -> str:
        if self._service_endpoint:
            return self._service_endpoint
        self._service_endpoint = self._discover_service_endpoint()
        return self._service_endpoint

    def test_connection(self) -> None:
        """Prove the Entra app registration + permissions work, without
        touching a real SCEP request. Token acquisition + service discovery
        only; raises IntuneScepError on any failure.
        """
        self._get_service_endpoint()

    # ---- ScepActions/* ----------------------------------------------------

    def _post(self, url_suffix: str, body: dict) -> dict:
        endpoint = self._get_service_endpoint()
        token = self._intune_token()
        activity_id = str(uuid.uuid4())
        try:
            resp = requests.post(
                f"{endpoint}/{url_suffix}",
                json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "client-request-id": activity_id,
                    "api-version": API_VERSION,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            # The discovered endpoint can go stale (tenant moved shards) --
            # clear it so the next call re-discovers, mirroring the reference
            # client's Clear()-on-failure behavior. One retry only; a second
            # consecutive failure is a real problem, not a stale cache.
            self._service_endpoint = None
            logger.error(
                "Intune SCEP API request failed (activityId=%s url=%s/%s): %s",
                activity_id, endpoint, url_suffix, e,
            )
            raise IntuneScepError(f"Intune SCEP API request failed: {e}") from e

        try:
            return resp.json()
        except ValueError as e:
            raise IntuneScepError(
                f"Intune SCEP API returned non-JSON response (activityId={activity_id})"
            ) from e

    def _check_result(self, result: dict, activity_id: str = ''):
        code = IntuneScepErrorCode.parse(result.get("code"))
        description = result.get("errorDescription") or ''
        if code != IntuneScepErrorCode.SUCCESS:
            raise IntuneScepError(
                f"Intune SCEP API returned {code.value}: {description}",
                code=code, description=description,
            )

    def validate_request(self, transaction_id: str, der_csr: bytes) -> None:
        """Validate a SCEP CSR + Intune challenge blob against Intune's API.

        Raises IntuneScepError on any rejection or transport failure --
        callers must not sign/issue a certificate if this raises.
        """
        body = {
            "request": {
                "transactionId": transaction_id,
                "certificateRequest": base64.b64encode(der_csr).decode(),
                "callerInfo": self.provider_name,
            }
        }
        result = self._post(VALIDATE_URL, body)
        self._check_result(result)

    def send_success_notification(self, transaction_id: str, der_csr: bytes,
                                   cert: x509.Certificate) -> None:
        """Tell Intune a certificate was issued for this request.

        Callers must not hand the certificate to the device unless this
        succeeds -- see the module docstring / scep_service.py's ordering
        (sign, flush, notify, only then commit + respond).
        """
        thumbprint = cert.fingerprint(hashes.SHA1()).hex().upper()
        serial = format(cert.serial_number, "X")
        not_after = cert.not_valid_after_utc.astimezone(timezone.utc)
        expiration = (
            not_after.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{not_after.microsecond // 1000:03d}Z"
        )
        issuing_authority = cert.issuer.rfc4514_string()

        body = {
            "notification": {
                "transactionId": transaction_id,
                "certificateRequest": base64.b64encode(der_csr).decode(),
                "certificateThumbprint": thumbprint,
                "certificateSerialNumber": serial,
                "certificateExpirationDateUtc": expiration,
                "issuingCertificateAuthority": issuing_authority,
                "callerInfo": self.provider_name,
                "caConfiguration": "",
                "certificateAuthority": "",
            }
        }
        result = self._post(NOTIFY_SUCCESS_URL, body)
        self._check_result(result)

    def send_failure_notification(self, transaction_id: str, der_csr: bytes,
                                   hresult: int, description: str) -> None:
        """Best-effort: tell Intune a SCEP request that already passed
        ValidateRequest subsequently failed to issue (e.g. CA signing error).
        """
        body = {
            "notification": {
                "transactionId": transaction_id,
                "certificateRequest": base64.b64encode(der_csr).decode(),
                "hResult": hresult,
                "errorDescription": description[:255],
                "callerInfo": self.provider_name,
            }
        }
        result = self._post(NOTIFY_FAILURE_URL, body)
        self._check_result(result)
