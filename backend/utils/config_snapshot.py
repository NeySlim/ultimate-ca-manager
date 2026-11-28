"""One-query read of several SystemConfig keys for a request that reads many of them."""
from contextlib import contextmanager
from types import SimpleNamespace

from flask import g, has_app_context

_ATTR = '_config_snapshot'


def config_row(key):
    """The SystemConfig row of *key* (``.value``), or None. Served from the open snapshot
    when it covers the key, so a reader costs no query inside ``config_snapshot``."""
    snapshot = getattr(g, _ATTR, None) if has_app_context() else None
    if snapshot is not None and key in snapshot['keys']:
        return snapshot['rows'].get(key)
    from models import SystemConfig
    return SystemConfig.query.filter_by(key=key).first()


@contextmanager
def config_snapshot(keys):
    """Load *keys* in one query; ``config_row`` answers them from memory until exit."""
    from models import SystemConfig
    keys = frozenset(keys)
    rows = {r.key: SimpleNamespace(key=r.key, value=r.value)
            for r in SystemConfig.query.filter(SystemConfig.key.in_(keys)).all()}
    previous = getattr(g, _ATTR, None)
    setattr(g, _ATTR, {'keys': keys, 'rows': rows})
    try:
        yield
    finally:
        setattr(g, _ATTR, previous)
