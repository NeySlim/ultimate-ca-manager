"""
File naming utilities for human-readable certificate/key filenames.

Format: {cn-slug}-{refid[:8]}.ext
Example: www.example.com-550e8400.crt, MyRootCA-a1b2c3d4.key
"""
import re
import unicodedata
from pathlib import Path
from config.settings import Config


def slugify_cn(cn: str) -> str:
    """Convert a Common Name to a filesystem-safe slug."""
    if not cn:
        return 'unknown'
    # Normalize unicode
    s = unicodedata.normalize('NFKD', cn)
    # Keep alphanumeric, dots, hyphens
    s = re.sub(r'[^\w.\-]', '-', s)
    # Collapse multiple hyphens
    s = re.sub(r'-{2,}', '-', s)
    # Strip leading/trailing hyphens
    s = s.strip('-')
    # Limit length
    s = s[:64]
    return s or 'unknown'


def _get_cn(subject: str) -> str:
    """Extract CN from an X.509 subject string like 'CN=example,O=Org'."""
    if not subject:
        return ''
    for part in subject.split(','):
        part = part.strip()
        if part.upper().startswith('CN='):
            return part[3:].strip()
    return ''


def cert_filename(refid: str, cn: str, ext: str) -> str:
    """Build human-readable filename: {cn-slug}-{refid8}.ext"""
    slug = slugify_cn(cn)
    short_id = refid[:8] if refid else 'norefid'
    return f"{slug}-{short_id}.{ext}"


def ca_cert_path(ca) -> Path:
    """Path for a CA certificate file."""
    cn = _get_cn(ca.subject) or ca.descr or ''
    return Config.CA_DIR / cert_filename(ca.refid, cn, 'crt')


def ca_key_path(ca) -> Path:
    """Path for a CA private key file."""
    cn = _get_cn(ca.subject) or ca.descr or ''
    return Config.PRIVATE_DIR / f"ca_{cert_filename(ca.refid, cn, 'key')}"


def cert_cert_path(certificate) -> Path:
    """Path for a certificate file."""
    cn = _get_cn(certificate.subject) or certificate.descr or ''
    return Config.CERT_DIR / cert_filename(certificate.refid, cn, 'crt')


def cert_key_path(certificate) -> Path:
    """Path for a certificate private key file."""
    cn = _get_cn(certificate.subject) or certificate.descr or ''
    return Config.PRIVATE_DIR / f"cert_{cert_filename(certificate.refid, cn, 'key')}"


def cert_csr_path(certificate) -> Path:
    """Path for a certificate CSR file."""
    cn = _get_cn(certificate.subject) or certificate.descr or ''
    return Config.CERT_DIR / cert_filename(certificate.refid, cn, 'csr')


def find_files_for_refid(directory: Path, refid: str, prefix: str = '', ext: str = 'crt') -> list:
    """Find all files matching a refid (old UUID or new human-readable format)."""
    if not directory.exists():
        return []
    short_id = refid[:8]
    matches = []
    pattern = f"{prefix}*{short_id}*.{ext}" if prefix else f"*{short_id}*.{ext}"
    for f in directory.glob(pattern):
        matches.append(f)
    # Also check old-style exact name
    old_name = directory / f"{prefix}{refid}.{ext}"
    if old_name.exists() and old_name not in matches:
        matches.append(old_name)
    return matches


def cleanup_old_files(ca=None, certificate=None):
    """Remove old-style UUID-named files for a CA or certificate."""
    if ca:
        old_cert = Config.CA_DIR / f"{ca.refid}.crt"
        old_key = Config.PRIVATE_DIR / f"ca_{ca.refid}.key"
        for p in [old_cert, old_key]:
            if p.exists():
                p.unlink()
    if certificate:
        old_cert = Config.CERT_DIR / f"{certificate.refid}.crt"
        old_csr = Config.CERT_DIR / f"{certificate.refid}.csr"
        old_key = Config.PRIVATE_DIR / f"cert_{certificate.refid}.key"
        for p in [old_cert, old_csr, old_key]:
            if p.exists():
                p.unlink()
