"""Certificate linting against X.509 standards.

Runs issued or imported certificates through conformance linters and returns
structured, *informative* findings (it never blocks issuance). Two profiles
are supported:

- ``rfc5280`` — IETF RFC 5280 profile (always relevant, even for a private PKI).
- ``cabf``    — CA/Browser Forum Baseline Requirements for TLS server certs
                (mostly meaningful for public-facing certificates; expect noise
                on internal certs).
- ``etsi``    — ETSI EN 319 412 (qualified and non-qualified certificate
                profiles); the profile is detected from the certificate.

``pkilint`` (a pure-Python linter) is an optional dependency: if it is not
installed the service degrades gracefully and reports the linter as
unavailable rather than raising. ``zlint`` is used as a second opinion when
its binary is found on ``PATH``.
"""
from __future__ import annotations

import base64
import json
import logging
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

PROFILE_RFC5280 = 'rfc5280'
PROFILE_CABF = 'cabf'
PROFILE_ETSI = 'etsi'
VALID_PROFILES = (PROFILE_RFC5280, PROFILE_CABF, PROFILE_ETSI)

# Severity ordering, highest first — used for sorting and summaries.
_SEVERITY_ORDER = ['fatal', 'error', 'warning', 'notice', 'info']


def _normalize_pem(cert: str) -> str:
    """Accept a PEM string or a base64-wrapped PEM (DB storage form)."""
    text = (cert or '').strip()
    if text.startswith('-----BEGIN'):
        return text
    # DB stores the PEM base64-encoded a second time.
    return base64.b64decode(text).decode('utf-8')


def _pkilint_available() -> bool:
    try:
        import pkilint  # noqa: F401
        return True
    except Exception:
        return False


def linters_status() -> Dict[str, bool]:
    """Report which linters are usable in this deployment."""
    return {
        'pkilint': _pkilint_available(),
        'zlint': shutil.which('zlint') is not None,
    }


def is_available() -> bool:
    status = linters_status()
    return any(status.values())


# ── pkilint ─────────────────────────────────────────────────────────────────

def _build_pkilint_validator(profile: str, cert_doc):
    from pkilint.pkix import certificate, name, extension

    if profile == PROFILE_CABF:
        from pkilint.cabf import serverauth
        cert_type = serverauth.determine_certificate_type(cert_doc)
        validator = certificate.create_pkix_certificate_validator_container(
            serverauth.create_decoding_validators(),
            serverauth.create_validators(cert_type),
        )
        finding_filters = serverauth.create_serverauth_finding_filters(cert_type)
        return validator, finding_filters, cert_type.to_option_str

    if profile == PROFILE_ETSI:
        from pkilint import etsi
        cert_type = etsi.determine_certificate_type(cert_doc)
        validator = certificate.create_pkix_certificate_validator_container(
            etsi.create_decoding_validators(cert_type),
            etsi.create_validators(cert_type),
        )
        return validator, etsi.create_etsi_finding_filters(cert_type), cert_type.to_option_str

    validator = certificate.create_pkix_certificate_validator_container(
        certificate.create_decoding_validators(
            name.ATTRIBUTE_TYPE_MAPPINGS, extension.EXTENSION_MAPPINGS),
        [
            certificate.create_issuer_validator_container([]),
            certificate.create_validity_validator_container(),
            certificate.create_subject_validator_container([]),
            certificate.create_extensions_validator_container([]),
            certificate.create_spki_validator_container([]),
        ],
    )
    return validator, [], None


def _lint_pkilint(pem: str, profile: str) -> Dict:
    from pkilint import loader

    cert_doc = loader.load_pem_certificate(pem, 'cert')
    validator, finding_filters, detected_type = _build_pkilint_validator(profile, cert_doc)
    results = validator.validate(cert_doc.root)

    # Apply profile finding filters (e.g. CABF suppresses non-applicable lints).
    if finding_filters:
        from pkilint import finding_filter
        results, _ = finding_filter.filter_results(finding_filters, results)

    findings: List[Dict] = []
    for result in results:
        node_path = getattr(getattr(result, 'node', None), 'path', None)
        for fd in result.finding_descriptions:
            findings.append({
                'source': 'pkilint',
                'severity': fd.finding.severity.name.lower(),
                'code': fd.finding.code,
                'message': fd.message or None,
                'node': node_path,
            })
    return {'findings': findings, 'detected_type': detected_type}


# ── zlint (optional external binary) ────────────────────────────────────────

_ZLINT_SEVERITY = {
    'fatal': 'fatal',
    'error': 'error',
    'warn': 'warning',
    'warning': 'warning',
    'notice': 'notice',
    'info': 'info',
}


def _lint_zlint(pem: str) -> List[Dict]:
    """Run the zlint binary if present; best-effort, never raises."""
    binary = shutil.which('zlint')
    if not binary:
        return []
    try:
        with tempfile.NamedTemporaryFile('w', suffix='.pem', delete=True) as fh:
            fh.write(pem)
            fh.flush()
            proc = subprocess.run(
                [binary, '-format', 'pem', fh.name],
                capture_output=True, text=True, timeout=30,
            )
        data = json.loads(proc.stdout or '{}')
    except Exception as exc:  # noqa: BLE001 — second-opinion linter must not break the request
        logger.warning('zlint invocation failed: %s', exc)
        return []

    findings: List[Dict] = []
    for code, res in data.items():
        if not isinstance(res, dict):
            continue
        result = str(res.get('result', '')).lower()
        if result in ('pass', 'na', 'ne', ''):
            continue
        findings.append({
            'source': 'zlint',
            'severity': _ZLINT_SEVERITY.get(result, 'notice'),
            'code': code,
            'message': res.get('details') or None,
            'node': None,
        })
    return findings


# ── public entry point ──────────────────────────────────────────────────────

def lint_certificate_pem(cert: str, profile: str = PROFILE_RFC5280) -> Dict:
    """Lint a certificate and return structured findings.

    Returns a dict with ``available`` (whether any linter ran), ``profile``,
    ``linters`` (which ran), ``summary`` (per-severity counts) and the sorted
    ``findings`` list. Raises ``ValueError`` only for an unparseable
    certificate or an invalid profile.
    """
    if profile not in VALID_PROFILES:
        raise ValueError(f'Unknown lint profile: {profile}')

    status = linters_status()
    if not any(status.values()):
        return {
            'available': False,
            'profile': profile,
            'linters': [],
            'summary': {s: 0 for s in _SEVERITY_ORDER},
            'findings': [],
        }

    try:
        pem = _normalize_pem(cert)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f'Could not decode certificate: {exc}') from exc

    findings: List[Dict] = []
    ran: List[str] = []
    detected_type: Optional[str] = None

    if status['pkilint']:
        try:
            res = _lint_pkilint(pem, profile)
            findings.extend(res['findings'])
            detected_type = res.get('detected_type')
            ran.append('pkilint')
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning('pkilint failed: %s', exc)

    if status['zlint']:
        z = _lint_zlint(pem)
        findings.extend(z)
        ran.append('zlint')

    summary = {s: 0 for s in _SEVERITY_ORDER}
    for f in findings:
        summary[f['severity']] = summary.get(f['severity'], 0) + 1

    findings.sort(key=lambda f: (
        _SEVERITY_ORDER.index(f['severity']) if f['severity'] in _SEVERITY_ORDER else 99,
        f['source'], f['code'],
    ))

    out = {
        'available': bool(ran),
        'profile': profile,
        'linters': ran,
        'summary': summary,
        'findings': findings,
    }
    if detected_type:
        out['detected_type'] = detected_type
    return out
