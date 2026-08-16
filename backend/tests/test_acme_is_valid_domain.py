"""
Tests for _is_valid_domain in backend/api/v2/acme_local_domains.py

"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.v2.acme_local_domains import _is_valid_domain


# ---- Test cases: (domain, expected_result, reason) ----

VALID_DOMAINS = [
    # Bare TLDs
    ("local",            True,  "bare TLD"),
    ("internal",         True,  "bare TLD"),
    ("lab",              True,  "bare TLD"),
    ("corp",             True,  "bare TLD"),
    ("home",             True,  "bare TLD"),

    # Wildcard bare TLDs
    ("*.local",          True,  "wildcard bare TLD"),
    ("*.internal",       True,  "wildcard bare TLD"),

    # Standard domains
    ("example.com",      True,  "standard domain"),
    ("foo.example.com",  True,  "subdomain"),
    ("bar.foo.example.com", True, "deep subdomain"),

    # Wildcard domains
    ("*.example.com",    True,  "wildcard domain"),
    ("*.foo.example.com", True, "wildcard subdomain"),

    # Hyphens in labels
    ("my-domain.com",    True,  "hyphen in label"),
    ("a-b.example.com",  True,  "hyphen in subdomain"),

    # Numeric labels
    ("123.com",          True,  "numeric label"),
    ("s1.example.com",   True,  "alphanumeric label"),

    # Single-char TLD edge (regex requires [a-zA-Z]{2,} so 2+ chars)
    ("ab",               True,  "two-letter bare TLD"),
]

INVALID_DOMAINS = [
    # Empty / whitespace
    ("",                 False, "empty string"),
    ("   ",              False, "whitespace only"),

    # Wildcard without TLD
    ("*",                False, "bare wildcard"),
    ("*.",               False, "wildcard with dot, no TLD"),

    # Leading/trailing dot
    (".com",             False, "leading dot"),
    ("example.com.",     False, "trailing dot"),

    # Double wildcard
    ("**.example.com",   False, "double asterisk"),
    ("*.*.example.com",  False, "double wildcard labels"),

    # Invalid characters
    ("exa_mple.com",     False, "underscore in label"),
    ("exa mple.com",     False, "space in label"),
    ("example!.com",     False, "special char in label"),

    # Single-char TLD (regex requires 2+ alpha chars)
    ("a",                False, "single-char TLD"),

    # Numeric-only TLD (regex requires [a-zA-Z]{2,})
    ("example.123",      False, "numeric TLD"),

    # Hyphen at start/end of label
    ("-example.com",     False, "leading hyphen in label"),
    ("example-.com",     False, "trailing hyphen in label"),

    # Path traversal attempts
    ("../etc/passwd",    False, "path traversal"),
    ("..",               False, "dot-dot"),

    # Newline injection
    ("example.com\n",    False, "trailing newline"),
    ("ex\nample.com",    False, "embedded newline"),
]


def run_tests():
    """Run all test cases and report results."""
    passed = 0
    failed = 0
    failures = []

    for domain, expected, reason in VALID_DOMAINS:
        result = _is_valid_domain(domain)
        if result == expected:
            passed += 1
        else:
            failed += 1
            failures.append(f"  FAIL: {domain!r:30s} expected={expected} got={result}  ({reason})")

    for domain, expected, reason in INVALID_DOMAINS:
        result = _is_valid_domain(domain)
        if result == expected:
            passed += 1
        else:
            failed += 1
            failures.append(f"  FAIL: {domain!r:30s} expected={expected} got={result}  ({reason})")

    print(f"\n_is_valid_domain tests: {passed} passed, {failed} failed, {passed + failed} total\n")
    if failures:
        print("Failures:")
        for f in failures:
            print(f)
        print()
    return failed == 0


if __name__ == "__main__":
    ok = run_tests()
    sys.exit(0 if ok else 1)
