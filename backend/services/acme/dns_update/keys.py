"""TSIG key store of the DNS UPDATE listener, with a short-lived cache.

One pass over the database loads every usable key. The
verifier then calls ``lookup`` for each request without a SQL statement. All
calls must run inside a Flask app context (the load needs one).

A key is usable when it is active, its proxy account exists and has
``proxy_enabled``, its algorithm is allowed, and its secret decrypts to
non-empty base64. Anything else is skipped (fail closed). The module never
logs a secret, only key names.

After ``invalidate()`` (key revoked, EAB deleted, account disabled, restore)
the cache is dirty. A failed reload then empties the cache, so every key is
unknown (BADKEY). After a normal expiry a failed reload keeps the previous
cache (availability). Failed loads are retried after ``_RETRY_S``, with one
warning per attempt.
"""

import base64
import binascii
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

import dns.exception
import dns.name

from .constants import ALLOWED_TSIG_ALGORITHMS
from .tsig import TsigKeyMaterial

logger = logging.getLogger(__name__)

_TOUCH_INTERVAL_S = 60.0
_RETRY_S = 2.0


@dataclass(frozen=True)
class KeyScope:
    """What a key may change: its proxy account and, when bound, its EAB account.
    Fail closed."""

    acme_client_account_id: int
    eab_bound: bool
    eab_account_id: Optional[str]

    def allows(self, row_acme_client_account_id, row_account_id) -> bool:
        if row_acme_client_account_id is None:
            return False
        if row_acme_client_account_id != self.acme_client_account_id:
            return False
        if self.eab_bound:
            if not self.eab_account_id or not row_account_id:
                return False
            return row_account_id == self.eab_account_id
        return True


def _canonical(name: dns.name.Name) -> str:
    return name.to_text().lower()


class KeyStore:
    def __init__(self, max_age_s: float = 30.0, clock=time.monotonic):
        self._max_age = max_age_s
        self._clock = clock
        self._lock = threading.Lock()
        self._materials: Dict[str, TsigKeyMaterial] = {}
        self._scopes: Dict[int, KeyScope] = {}
        self._loaded_at: Optional[float] = None
        self._dirty = False
        self._retry_at: Optional[float] = None
        self._touched: Dict[int, float] = {}

    # -- cache -------------------------------------------------------------
    def invalidate(self) -> None:
        with self._lock:
            self._dirty = True
            self._loaded_at = None
            self._retry_at = None

    def _ensure(self) -> None:
        with self._lock:
            now = self._clock()
            if (not self._dirty and self._loaded_at is not None
                    and (now - self._loaded_at) < self._max_age):
                return
            if self._retry_at is not None and now < self._retry_at:
                if self._dirty:
                    self._materials = {}
                    self._scopes = {}
                return
            try:
                materials, scopes = self._load()
            except Exception as e:
                self._retry_at = now + _RETRY_S
                if self._dirty:
                    # An explicit invalidation means the old cache may hold a
                    # revoked key: fail closed.
                    self._materials = {}
                    self._scopes = {}
                    logger.warning("DNS UPDATE key reload failed, cache emptied: %s",
                                   type(e).__name__)
                else:
                    logger.warning("DNS UPDATE key reload failed, keeping previous cache: %s",
                                   type(e).__name__)
                return
            self._materials = materials
            self._scopes = scopes
            self._dirty = False
            self._retry_at = None
            self._loaded_at = now

    def lookup(self, name: dns.name.Name) -> Optional[TsigKeyMaterial]:
        self._ensure()
        with self._lock:
            return self._materials.get(_canonical(name))

    def scope(self, key_id: int) -> Optional[KeyScope]:
        self._ensure()
        with self._lock:
            return self._scopes.get(key_id)

    # -- last_used_at ------------------------------------------------------
    def touch(self, key_id: int, now: datetime) -> None:
        """Set ``last_used_at``, at most once per 60 s per key. Never raises."""
        try:
            mono = self._clock()
            with self._lock:
                last = self._touched.get(key_id)
                if last is not None and (mono - last) < _TOUCH_INTERVAL_S:
                    return
                self._touched[key_id] = mono
            from models import db
            from models.acme_dns_update import AcmeDnsUpdateKey
            try:
                AcmeDnsUpdateKey.query.filter_by(id=key_id).update(
                    {'last_used_at': now}, synchronize_session=False)
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
        except Exception as e:
            logger.warning("DNS UPDATE last_used_at update failed: %s", type(e).__name__)

    # -- loading -----------------------------------------------------------
    @staticmethod
    def _load():
        from models import db
        from models.acme_client_account import AcmeClientAccount
        from models.acme_dns_update import AcmeDnsUpdateKey
        from models.acme_models import AcmeEabCredential

        materials: Dict[str, TsigKeyMaterial] = {}
        scopes: Dict[int, KeyScope] = {}
        try:
            enabled = {row[0] for row in db.session.query(AcmeClientAccount.id)
                       .filter(AcmeClientAccount.proxy_enabled.is_(True)).all()}
            keys = AcmeDnsUpdateKey.query.filter_by(status='active').all()
            cred_ids = {k.eab_credential_id for k in keys if k.eab_credential_id is not None}
            creds = {}
            if cred_ids:
                creds = {c.id: (c.status, c.used_by_account_id)
                         for c in db.session.query(
                             AcmeEabCredential.id, AcmeEabCredential.status,
                             AcmeEabCredential.used_by_account_id)
                         .filter(AcmeEabCredential.id.in_(cred_ids)).all()}
            for key in keys:
                if key.acme_client_account_id not in enabled:
                    continue
                try:
                    algorithm = dns.name.from_text(key.algorithm)
                    name = dns.name.from_text(key.name)
                except (dns.exception.DNSException, UnicodeError, TypeError):
                    logger.warning("DNS UPDATE key %r skipped: invalid name or algorithm", key.name)
                    continue
                if algorithm not in ALLOWED_TSIG_ALGORITHMS:
                    logger.warning("DNS UPDATE key %r skipped: algorithm not allowed", key.name)
                    continue
                text = key.secret
                secret = b''
                if text:
                    try:
                        secret = base64.b64decode(text, validate=True)
                    except (binascii.Error, ValueError):
                        secret = b''
                if not secret:
                    logger.warning("DNS UPDATE key %r skipped: secret unusable", key.name)
                    continue
                eab_bound = bool(key.eab_bound) or key.eab_credential_id is not None
                eab_account_id = None
                if eab_bound:
                    cred = creds.get(key.eab_credential_id)
                    if cred and cred[0] == 'used' and cred[1]:
                        eab_account_id = cred[1]
                materials[_canonical(name)] = TsigKeyMaterial(key.id, name, algorithm, secret)
                scopes[key.id] = KeyScope(key.acme_client_account_id, eab_bound, eab_account_id)
        finally:
            # Do not leave a read transaction open in the listener thread.
            db.session.rollback()
        return materials, scopes


key_store = KeyStore()


def invalidate_keys() -> None:
    key_store.invalidate()
