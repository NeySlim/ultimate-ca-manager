"""
HSM Detection and Availability Checking

Detects whether python-pkcs11 and SoftHSM2 are available on the system,
and provides install instructions for the current OS.
"""
import os
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Known SoftHSM library paths across distributions
SOFTHSM_PATHS = [
    "/usr/lib/softhsm/libsofthsm2.so",                        # Debian/Ubuntu
    "/usr/lib64/softhsm/libsofthsm2.so",                      # RHEL/CentOS
    "/usr/lib64/libsofthsm2.so",                               # Fedora
    "/usr/lib64/pkcs11/libsofthsm2.so",                        # Fedora pkcs11
    "/usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so",       # Ubuntu x64
    "/usr/lib/aarch64-linux-gnu/softhsm/libsofthsm2.so",      # Ubuntu ARM64
    "/usr/local/lib/softhsm/libsofthsm2.so",                  # Manual install
    "/opt/softhsm2/lib/softhsm/libsofthsm2.so",               # Custom install
]

INSTALL_COMMANDS = {
    "debian": "sudo apt-get install -y softhsm2",
    "ubuntu": "sudo apt-get install -y softhsm2",
    "rhel": "sudo dnf install -y softhsm",
    "centos": "sudo dnf install -y softhsm",
    "fedora": "sudo dnf install -y softhsm",
    "rocky": "sudo dnf install -y softhsm",
    "alpine": "apk add softhsm",
}


def _detect_os() -> str:
    """Detect OS type from /etc/os-release"""
    try:
        with open("/etc/os-release", "r") as f:
            content = f.read().lower()
        for os_type in ["ubuntu", "debian", "rocky", "centos", "rhel", "fedora", "alpine"]:
            if os_type in content:
                return os_type
    except FileNotFoundError:
        pass
    return "generic"


def _check_pkcs11_lib() -> bool:
    """Check if python-pkcs11 is importable"""
    try:
        import pkcs11  # noqa: F401
        return True
    except ImportError:
        return False


def _find_softhsm() -> Optional[str]:
    """Find SoftHSM library on disk"""
    for path in SOFTHSM_PATHS:
        if os.path.exists(path):
            return path
    return None


def get_hsm_status() -> Dict:
    """Get comprehensive HSM availability status"""
    pkcs11_ok = _check_pkcs11_lib()
    softhsm_path = _find_softhsm()
    os_type = _detect_os()
    ready = pkcs11_ok and softhsm_path is not None

    result = {
        "ready": ready,
        "pkcs11_installed": pkcs11_ok,
        "softhsm_found": softhsm_path is not None,
        "softhsm_path": softhsm_path,
        "os_type": os_type,
    }

    if not ready:
        result["install_command"] = INSTALL_COMMANDS.get(
            os_type, "Install softhsm2 from your package manager"
        )

    return result


def log_hsm_warning():
    """Log a warning at startup if HSM is not fully available"""
    status = get_hsm_status()
    if status["ready"]:
        logger.info(f"HSM ready: SoftHSM found at {status['softhsm_path']}")
        return

    parts = []
    if not status["pkcs11_installed"]:
        parts.append("python-pkcs11 not installed (pip install python-pkcs11)")
    if not status["softhsm_found"]:
        cmd = status.get("install_command", "install softhsm2")
        parts.append(f"SoftHSM not found ({cmd})")

    msg = "HSM unavailable: " + "; ".join(parts)
    logger.warning(msg)
