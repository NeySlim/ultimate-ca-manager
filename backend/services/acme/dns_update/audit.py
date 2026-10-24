"""Bounded audit sink of the DNS UPDATE listener (F7, N6, N7, N12, N13).

An attacker on the network can send any number of bad packets. The sink
writes at most one row per (peer IP, reason) per window and at most N rows per
reason per window. Dropped events are counted and reported in ONE summary row
when the next window opens. ``record`` never raises.
"""

import collections
import json
import logging
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_WINDOW_S = 60.0
_MAX_TEXT = 255
SUPPRESSED_ACTION = 'acme.dns_update.suppressed'


def sanitize_text(value, limit: int = _MAX_TEXT) -> str:
    """Text for an audit field: truncated, printable ASCII only."""
    if isinstance(value, bytes):
        text = value.decode('latin-1')
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)
    text = text[:limit]
    return ''.join(c if 0x20 <= ord(c) < 0x7f else '?' for c in text)


def _sanitize_details(value):
    if isinstance(value, dict):
        return {sanitize_text(k): _sanitize_details(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_details(v) for v in value]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return sanitize_text(value)


class AuditSink:
    def __init__(self, per_ip_per_minute: int = 1, global_per_reason_per_minute: int = 20,
                 max_ips: int = 4096, clock=time.monotonic):
        self._per_ip = per_ip_per_minute
        self._global = global_per_reason_per_minute
        self._max_ips = max_ips
        self._clock = clock
        self._lock = threading.Lock()
        # (ip, reason) -> list of write times, LRU ordered
        self._ip_hits: "collections.OrderedDict[tuple, list]" = collections.OrderedDict()
        # reason -> [window_start, written, dropped]
        self._windows: Dict[str, list] = {}

    def record(self, *, action: str, reason: str, peer_ip: str, keyname: Optional[str],
               success: bool, details: dict) -> bool:
        try:
            return self._record(action, reason, peer_ip, keyname, success, details)
        except Exception as e:
            try:
                logger.warning("DNS UPDATE audit record failed: %s", type(e).__name__)
            except Exception:
                pass
            return False

    def _record(self, action, reason, peer_ip, keyname, success, details) -> bool:
        reason_s = sanitize_text(reason)
        ip_s = sanitize_text(peer_ip, 45)
        summary_dropped = 0
        with self._lock:
            now = self._clock()
            win = self._windows.get(reason_s)
            if win is None or now - win[0] >= _WINDOW_S:
                summary_dropped = win[2] if win else 0
                win = [now, 0, 0]
                self._windows[reason_s] = win
            # per-IP limit
            ip_key = (ip_s, reason_s)
            hits = self._ip_hits.get(ip_key)
            if hits is not None:
                hits[:] = [t for t in hits if now - t < _WINDOW_S]
                self._ip_hits.move_to_end(ip_key)
            allowed = True
            if hits is not None and len(hits) >= self._per_ip:
                allowed = False
            if allowed and win[1] >= self._global:
                win[2] += 1
                allowed = False
            if allowed:
                win[1] += 1
                if hits is None:
                    hits = []
                    self._ip_hits[ip_key] = hits
                    while len(self._ip_hits) > self._max_ips:
                        self._ip_hits.popitem(last=False)
                hits.append(now)
        if summary_dropped:
            self._write(SUPPRESSED_ACTION, None, False,
                        {'reason': reason_s, 'dropped': summary_dropped}, ip=None)
        if not allowed:
            return False
        self._write(action, keyname, success, details or {}, ip=ip_s)
        return True

    @staticmethod
    def _write(action, keyname, success, details, ip) -> None:
        from services.audit import AuditService
        key_s = sanitize_text(keyname) if keyname else None
        AuditService.log_action(
            action=sanitize_text(action),
            resource_type='acme_dns_update',
            resource_name=key_s or 'unauthenticated',
            details=json.dumps(_sanitize_details(details)),
            success=success,
            username=f"dns-update:{key_s}" if key_s else "dns-update:unauthenticated",
            ip_address=ip,
        )


audit_sink = AuditSink()
