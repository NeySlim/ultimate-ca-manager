"""One place that says what a system setting means when nobody set it.

`SystemConfig` is a bare key/value table: no defaults, no types, no list of
what exists. Every reader hand-rolled its own query, its own coercion and its
own fallback, and with a dozen readers the fallbacks drifted. The settings API
drifted furthest, because it restates the defaults as literals in its GET
handler rather than asking the code that actually uses them -- so the screen
said the timestamping service was off while `/tsa` was serving, and said the
lockout lasted 300 seconds while the enforcer locked for 900.

What follows is deliberately **not** a tidy-up. Each entry records what the
reader that *decides* already does, so adopting the registry changes what the
API reports and nothing else. One entry is an exception, `mtls_enabled`,
where the deciding reader was itself wrong.

Why several flavours of boolean, rather than one:

* `permissive` reads `yes` / `on` / `1` as true, which is what most runtime
  readers do and what an operator hand-editing the table expects;
* `strict` accepts only the exact string `true`, which is what the readers
  that configure a socket or grandfather a protocol endpoint do;
* `strict_off` refuses only on the exact string `false`, for a safeguard that
  must stay on when its row is garbled (the dedicated TSA signer).

Picking one flavour for everything would silently flip real behaviour. A key
whose deciding reader is strict keeps strict; the flavour is part of what the
key means, so it is written down here instead of being re-derived per caller.
"""

import json
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_TRUE_WORDS = frozenset({'true', '1', 'yes', 'on'})
_FALSE_WORDS = frozenset({'false', '0', 'no', 'off'})

# The date styles the SPA can actually render (`stores/dateFormatStore.js`
# VALID_FORMATS). It drops anything else on the floor and keeps the previous
# style, while the settings dropdown -- which has exactly these options --
# shows no selection at all. So the row may only hold one of them.
DATE_FORMATS = ('short', 'iso', 'eu', 'us', 'long')


def as_boolean_word(value) -> Optional[str]:
    """`'true'` / `'false'` for anything that reads as a boolean, else None.

    The settings API converted `True`/`False` and nothing else, so a client
    sending `0` -- `isinstance(0, bool)` is False in Python -- stored the
    string `"0"`, which one reader called on and the other called off.
    """
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return 'true' if value else 'false'
    if isinstance(value, str):
        word = value.strip().lower()
        if word in _TRUE_WORDS:
            return 'true'
        if word in _FALSE_WORDS:
            return 'false'
    return None


# ----------------------------------------------------------------- coercions

def bool_permissive(raw: str, default: bool) -> bool:
    word = str(raw).strip().lower()
    if word in _TRUE_WORDS:
        return True
    if word in _FALSE_WORDS:
        return False
    return default


def bool_strict(raw: str, default: bool) -> bool:
    """Only the exact word `true` enables. Anything else disables."""
    return str(raw).strip().lower() == 'true'


def bool_strict_off(raw: str, default: bool) -> bool:
    """Only the exact word `false` disables. Anything else enables (fails closed)."""
    return str(raw).strip().lower() != 'false'


def integer(raw: str, default: int) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def text(raw: str, default: Optional[str]) -> Optional[str]:
    value = str(raw).strip()
    return value or default


def json_list(raw: str, default):
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return default
    return parsed if isinstance(parsed, list) else default


class Setting:
    """A key's default and how a stored value is read.

    `default` may be a callable for the settings whose fallback is computed
    (the ACME public port follows the HTTPS port unless it is pinned).
    """

    __slots__ = ('default', 'coerce', 'why')

    def __init__(self, default, coerce: Callable, why: str = ''):
        self.default = default
        self.coerce = coerce
        self.why = why

    def fallback(self):
        return self.default() if callable(self.default) else self.default

    def read(self, raw) -> Any:
        fallback = self.fallback()
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return fallback
        return self.coerce(raw, fallback)


def _https_port_default() -> int:
    from utils.public_endpoints import _https_port
    return _https_port()


SETTINGS = {
    # --- absent means "on", and only the exact word turns it off -----------
    'tsa_enabled': Setting(
        True, bool_strict,
        'the row did not exist before 2.200, so a missing row is an enabled '
        'service; services/tsa_service.tsa_is_enabled decides and is strict'),

    # --- absent means "on", and only the exact word turns it off: RFC 3161 §2.3 wants a
    # dedicated signer; a 2.x TSA signing with its CA had the explicit false written (step 162)
    'tsa_require_dedicated_cert': Setting(
        True, bool_strict_off,
        'services/tsa_service decides: the CA certificate signs timestamps only '
        'when the operator wrote false'),

    # --- absent means "on", read forgivingly ------------------------------
    'hsts_enabled': Setting(
        True, bool_permissive,
        'utils/hsts decides: anything that is not an explicit off is on'),
    'hsts_include_subdomains': Setting(True, bool_permissive,
                                       'same rule as hsts_enabled'),
    'acme.enabled': Setting(
        True, bool_permissive,
        'the dashboard and the documented intent default to enabled; '
        'api/v2/acme.py read only the exact word and disagreed on "yes"'),
    'show_time': Setting(
        True, bool_permissive,
        'auth/session_payload serves the preference to the UI and reads it '
        'through this entry, so the screen and the session cannot disagree'),
    'date_format': Setting(
        'short', lambda raw, default: (
            raw if raw in DATE_FORMATS else default),
        'stores/dateFormatStore.js honours these five names and ignores '
        'anything else, so a word outside the list is the default here too'),

    # --- absent means "off" ------------------------------------------------
    'mtls_enabled': Setting(
        False, bool_strict,
        'gunicorn_config configures the TLS socket on the exact word; a '
        'reader that says yes where the socket says no claims a client '
        'certificate is required when none is asked for'),
    'crl_auto_delete_expired_revoked': Setting(
        False, bool_permissive,
        'services/crl/query decides and reads true/1/yes/on'),
    'crl_auto_purge_stale_serials': Setting(False, bool_permissive,
                                            'same rule as the delete flag'),

    # --- numbers -----------------------------------------------------------
    'lockout_duration': Setting(
        900, integer,
        'api/v2/sso/helpers is the enforcer; the settings screen showed 300 '
        'while accounts were locked for 900'),
    'auto_renewal_days': Setting(
        30, integer,
        'the scheduler and services/acme/ari._DEFAULT_RENEW_BEFORE_DAYS held '
        'the same 30 in two places; one number now'),
    'acme_public_port': Setting(
        _https_port_default, integer,
        'utils/public_endpoints builds the advertised directory URL and '
        'follows the HTTPS port; the settings screen showed a flat 443'),

    # --- values whose absence is itself meaningful -------------------------
    'ct_log_urls': Setting(
        None, json_list,
        'utils/ct_client reads absent as "use the built-in log list"; the '
        'settings screen reported an empty list, which reads as "no logs"'),
    # Not a divergence to collapse: the settings API answers "what did the
    # operator configure" (absent, so nothing) while the client service
    # answers "what address do I register with". An installation that never
    # set the key still has to be able to create its account row, and the
    # address is overwritten at registration, so the placeholder stays.
    'acme.client.email': Setting(
        'admin@localhost', text,
        'services/acme/acme_client_service registers with this when the '
        'operator set no address; readers that can refuse keep treating an '
        'absent row as "not configured"'),

    # --- how long delivery history is kept --------------------------------
    # Two windows, because the two kinds of row answer different questions.
    # Zero or less keeps that kind for ever, which is how one window is
    # turned off without turning the task off.
    'deliveries.retention.succeeded_days': Setting(
        30, integer,
        'services/delivery_retention: a delivered row is history; the '
        'operator reads the endpoint, not the thirty-first copy of a '
        'successful POST'),
    'deliveries.retention.failed_days': Setting(
        90, integer,
        'services/delivery_retention: a failed row is what gets opened when '
        'someone asks why a notification never arrived, so it outlives the '
        'successful ones'),
}


def effective(key: str):
    """The value this setting has right now, default included.

    Raises KeyError for a key with no registry entry, so a typo is a failure
    here rather than a silent default somewhere far away.
    """
    setting = SETTINGS[key]
    try:
        from models import SystemConfig
        row = SystemConfig.query.filter_by(key=key).first()
    except Exception as exc:                       # no table yet, no app, ...
        logger.debug('settings registry could not read %s: %s', key, exc)
        return setting.fallback()
    return setting.read(row.value if row else None)


def default_for(key: str):
    """What this setting falls back to, without touching the database."""
    return SETTINGS[key].fallback()
