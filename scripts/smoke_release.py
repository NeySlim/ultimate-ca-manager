#!/usr/bin/env python3
"""
UCM release smoke test — generic, parameterised.

Verifies a deployed UCM instance:
  1. /api/v2/health returns expected version (and is NOT a release candidate).
  2. /api/v2/auth/login/password returns 200 with csrf_token + permissions.
  3. /acme/proxy/directory returns ACME directory with newNonce.
  4. /acme/proxy/new-nonce returns 200/204 with Replay-Nonce header.
  5. /acme/proxy/directory called twice (regression: KeyEncryption.decrypt
     must tolerate legacy plaintext PEM keys; second call must not crash).

Usage:
  smoke_release.py --base-url https://host:port --version 2.143
  smoke_release.py --target DEB=https://host1:8445 --target RPM=https://host2:8443 \\
                   --version 2.143
  smoke_release.py --targets-file targets.txt --version 2.143

  targets.txt format: one "label=url" per line, '#' comments allowed.

Exit code: 0 if all targets pass, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


@dataclass
class Target:
    label: str
    base_url: str


def _request(
    base: str,
    path: str,
    method: str = "GET",
    body: Optional[dict] = None,
    headers: Optional[dict] = None,
    cookie: Optional[str] = None,
    timeout: int = 20,
) -> tuple[int, dict, bytes]:
    h = dict(headers or {})
    if cookie:
        h["Cookie"] = cookie
    if body is not None:
        h["Content-Type"] = "application/json"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{base}{path}", data=data, method=method, headers=h)
    try:
        resp = urllib.request.urlopen(req, context=_SSL_CTX, timeout=timeout)
        return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()


def health_version(body: bytes) -> str:
    """The version string /health reports ('' when the body is not the health JSON)."""
    try:
        return str(json.loads(body).get("version", ""))
    except (ValueError, AttributeError):
        return ""


def smoke_one(
    target: Target,
    expected_version: str,
    admin_user: str,
    admin_password: str,
    allow_rc: bool = False,
) -> None:
    """Run the smoke checks against a single target. Raises AssertionError on any failure."""
    base = target.base_url.rstrip("/")
    print(f"\n=== {target.label} ({base}) ===")

    # 1. Health + version
    status, _, body = _request(base, "/api/v2/health")
    snippet = body[:160].decode(errors="replace")
    print(f"  health: {status} {snippet}")
    assert status == 200, f"health endpoint returned {status}"
    assert health_version(body) == expected_version, (
        f"version mismatch: expected {expected_version!r}, health reports {health_version(body)!r}"
    )
    if not allow_rc:
        assert b"-rc" not in body, "health body contains '-rc' (release candidate built as stable?)"

    # 2. Login -> csrf_token + permissions
    status, headers, body = _request(
        base,
        "/api/v2/auth/login/password",
        "POST",
        {"username": admin_user, "password": admin_password},
    )
    print(f"  login: {status}")
    assert status == 200, f"login failed: {body[:200]!r}"
    cookie = headers.get("Set-Cookie", "").split(";")[0]
    payload = json.loads(body)
    csrf = payload.get("data", {}).get("csrf_token")
    perms = payload.get("data", {}).get("permissions", [])
    assert csrf, "login response missing csrf_token (auth contract regression)"
    assert perms, "login response missing permissions (auth contract regression)"
    print(f"  csrf+perms OK ({len(perms)} permissions)")

    # 3. ACME directory
    status, _, body = _request(base, "/acme/proxy/directory")
    print(f"  acme/directory: {status}")
    assert status == 200, f"acme directory failed: {body[:200]!r}"
    directory = json.loads(body)
    assert "newNonce" in directory, "acme directory missing newNonce"

    # 4. ACME new-nonce
    status, headers, _ = _request(base, "/acme/proxy/new-nonce")
    nonce = headers.get("Replay-Nonce", "")
    print(f"  acme/new-nonce: {status} nonce={nonce[:24]}...")
    assert status in (200, 204), f"new-nonce failed with {status}"
    assert nonce, "new-nonce response missing Replay-Nonce header"

    # 5. ACME directory replay
    # Regression guard: if KeyEncryption.decrypt() is intolerant of plaintext
    # PEM private keys (issue #105), the second call decrypts an already-loaded
    # account key and crashes inside the proxy service.
    status, _, body = _request(base, "/acme/proxy/directory")
    assert status == 200 and b"newNonce" in body, (
        "acme directory replay failed (KeyEncryption regression?)"
    )
    print("  acme/directory replay: OK (KeyEncryption.decrypt tolerance)")

    print(f"  --> {target.label} PASS")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke-test a deployed UCM release.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Expected release version (e.g. 2.143). Must appear in /api/v2/health.",
    )
    parser.add_argument(
        "--base-url",
        action="append",
        default=[],
        help="Single target URL (can be repeated). Label defaults to the URL.",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="LABEL=URL",
        help="Labelled target (can be repeated). e.g. DEB=https://host:8445",
    )
    parser.add_argument(
        "--targets-file",
        help='File with one "label=url" target per line ("#" comments allowed).',
    )
    parser.add_argument(
        "--admin-user",
        default="admin",
        help="Admin username for login probe (default: admin).",
    )
    parser.add_argument(
        "--admin-password",
        default="changeme123",
        help="Admin password for login probe (default: changeme123).",
    )
    parser.add_argument(
        "--allow-rc",
        action="store_true",
        help="Allow '-rc' in version string (use when smoke-testing a release candidate).",
    )
    return parser.parse_args(argv)


def collect_targets(args: argparse.Namespace) -> list[Target]:
    targets: list[Target] = []
    for url in args.base_url:
        targets.append(Target(label=url, base_url=url))
    for entry in args.target:
        if "=" not in entry:
            raise SystemExit(f"--target expects LABEL=URL, got: {entry!r}")
        label, url = entry.split("=", 1)
        targets.append(Target(label=label.strip(), base_url=url.strip()))
    if args.targets_file:
        with open(args.targets_file, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    raise SystemExit(
                        f"{args.targets_file}: expected label=url, got: {line!r}"
                    )
                label, url = line.split("=", 1)
                targets.append(Target(label=label.strip(), base_url=url.strip()))
    if not targets:
        raise SystemExit(
            "No targets supplied. Use --base-url, --target LABEL=URL, "
            "or --targets-file."
        )
    return targets


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    targets = collect_targets(args)

    failures: list[tuple[str, str]] = []
    for target in targets:
        try:
            smoke_one(
                target,
                expected_version=args.version,
                admin_user=args.admin_user,
                admin_password=args.admin_password,
                allow_rc=args.allow_rc,
            )
        except AssertionError as exc:
            print(f"  FAIL: {exc}")
            failures.append((target.label, str(exc)))
        except Exception as exc:  # network/SSL/etc.
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            failures.append((target.label, f"{type(exc).__name__}: {exc}"))

    total = len(targets)
    passed = total - len(failures)
    print(f"\n=== RESULT: {passed}/{total} PASS ===")
    if failures:
        for label, msg in failures:
            print(f"  - {label}: {msg}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
