"""Regression tests for the SSRF cloud-metadata/loopback guard (utils/ssrf_protection).

The guard must not be evadable via:
  * the unspecified address (0.0.0.0 / ::), which routes to loopback on most OSes; or
  * an IPv4-mapped IPv6 encoding of a denied IPv4 target
    (e.g. ::ffff:169.254.169.254 for the cloud metadata service).
It must keep ALLOWING public and RFC1918-private literal IPs — this narrow guard permits
those by design (UCM is commonly pointed at internal infra).
"""
import pytest
from utils.ssrf_protection import validate_url_not_cloud_metadata


@pytest.mark.parametrize("url", [
    "https://0.0.0.0/",                    # unspecified -> loopback
    "https://[::]/",                       # unspecified -> loopback
    "https://127.0.0.1/",                  # loopback
    "https://[::ffff:127.0.0.1]/",         # IPv4-mapped loopback
    "https://169.254.169.254/",            # AWS/Azure/GCP metadata
    "https://[::ffff:169.254.169.254]/",   # metadata via IPv4-mapped IPv6
    "https://100.100.100.200/",            # Alibaba metadata
])
def test_guard_blocks_loopback_and_metadata(url):
    with pytest.raises(ValueError):
        validate_url_not_cloud_metadata(url)


@pytest.mark.parametrize("url", [
    "https://93.184.216.34/",   # public literal IP
    "https://10.0.0.5/",        # RFC1918 private — allowed by this narrow guard by design
    "https://192.168.1.10/",
])
def test_guard_allows_public_and_private_literals(url):
    validate_url_not_cloud_metadata(url)   # must not raise
