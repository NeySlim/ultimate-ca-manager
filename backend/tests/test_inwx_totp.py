"""INWX two-factor code: the shared secret is base32 (RFC 4648), the code RFC 6238 TOTP."""
from unittest.mock import patch

import pytest

# RFC 6238 appendix B: the SHA-1 seed "12345678901234567890", 32 base32 characters
RFC6238_SECRET = 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
# bytes 0x01..0x10 in base32 without padding: 26 characters
SHORT_PADDED_SECRET = 'AEBAGBAFAYDQQCIKBMGA2DQPCA'


@pytest.mark.parametrize('secret, at, code', [
    (RFC6238_SECRET, 59, '287082'),
    (RFC6238_SECRET, 1111111109, '081804'),
    (SHORT_PADDED_SECRET, 1111111109, '275318'),
])
def test_totp_matches_rfc_6238(secret, at, code):
    from services.acme.dns_providers.inwx import InwxDnsProvider
    provider = InwxDnsProvider({'username': 'u', 'password': 'p', 'shared_secret': secret})
    with patch('time.time', return_value=float(at)):
        assert provider._generate_totp(secret) == code
