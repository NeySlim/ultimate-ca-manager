"""PKCS#11 provider config normalization.

``PKCS11Provider`` expects ``module_path`` and ``user_pin``. Older code paths
(auto_register_softhsm, manual JSON) used ``library_path`` and ``pin``.
"""

from __future__ import annotations

from typing import Any, Dict

_LEGACY_MODULE_KEYS = ('library_path', 'pkcs11_library_path')
_LEGACY_PIN_KEYS = ('pin',)


def normalize_pkcs11_config(config: Dict[str, Any] | None) -> Dict[str, Any]:
    """Return a copy with canonical PKCS#11 keys and legacy aliases removed."""
    if not config or not isinstance(config, dict):
        return {}

    out = dict(config)

    if not out.get('module_path'):
        for key in _LEGACY_MODULE_KEYS:
            if out.get(key):
                out['module_path'] = out[key]
                break

    if not out.get('user_pin'):
        for key in _LEGACY_PIN_KEYS:
            if out.get(key):
                out['user_pin'] = out[key]
                break

    for stale in _LEGACY_MODULE_KEYS + _LEGACY_PIN_KEYS:
        out.pop(stale, None)

    return out


def pkcs11_config_needs_normalization(config: Dict[str, Any] | None) -> bool:
    """True when legacy keys are present or canonical keys are missing."""
    if not config or not isinstance(config, dict):
        return False
    normalized = normalize_pkcs11_config(config)
    if set(normalized.keys()) != set(config.keys()):
        return True
    return any(config.get(k) != normalized.get(k) for k in normalized)
