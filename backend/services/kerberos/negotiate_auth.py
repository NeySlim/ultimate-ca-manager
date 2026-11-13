"""
HTTP Negotiate/SPNEGO (RFC 4559) authentication for MS-XCEP/MS-WSTEP's
Kerberos binding (``ADPolicyProvider_CEP_Kerberos`` /
``ADCertificateService_CES_Kerberos``).

Unlike the UsernamePassword and Certificate bindings — where credentials are
carried inside the SOAP body via WS-Security (``services/wstep/soap_envelope.py``,
``services/wstep/ws_security.py``) — Kerberos authentication for CEP/CES
happens at the HTTP transport layer, exactly like IIS Windows Integrated
Authentication or Apache ``mod_auth_gssapi``: an ``Authorization: Negotiate
<base64 SPNEGO token>`` header, verified against a keytab via GSSAPI.
Confirmed against a real-world writeup of Linux CES/CEP Kerberos enrollment
(``requests-kerberos`` client side, keytab-backed GSSAPI acceptor server
side) since, as with phases 1-2, the published MS-XCEP/MS-WSTEP spec text
doesn't spell out which binding is transport-level vs message-level.

Real SPNEGO negotiation is *not* always a single round trip, even for
Kerberos-only. Confirmed against the lab with a real domain admin ticket:
Windows' NegTokenInit listed its legacy MS-KRB5 OID ahead of the standard
KRB5 OID, which didn't match this acceptor's own preferred mech, so SPNEGO's
RFC 4178 anti-downgrade rule kicked in and the acceptor had to respond with
``negState: request-mic`` instead of completing outright -- a third leg
(client sends a mechListMIC, acceptor confirms) is mandatory in that case,
not an artifact of any configurable pyspnego option. So this module keeps
in-progress ``spnego`` contexts across requests, keyed by the client's source
IP (``REMOTE_ADDR`` -- gunicorn here runs a single worker, so an in-process
dict is safe). Confirmed against the lab that a real WCF client
(``MS-WebServices/1.0``, what GPMC's policy-server "Validate" and GPO
autoenrollment both use) opens a *new* TCP connection -- a new ``REMOTE_PORT``
every time -- for each leg of the handshake rather than reusing one, unlike
a browser or ``requests``/``curl``; keying on the full ``(REMOTE_ADDR,
REMOTE_PORT)`` tuple (as real NTLM connection-binding would require and as
this module's first version did) meant every leg missed its predecessor's
pending context and the handshake could never complete against that client.
IP-only keying tolerates that. Entries expire after a short TTL so an
abandoned handshake can't leak memory; the small residual risk -- two
distinct clients negotiating concurrently from behind the same source IP
(e.g. NAT) momentarily colliding on the same pending context -- fails
closed (the wrong context's crypto just won't verify, forcing a retry),
not open.

This module relies on the underlying krb5 library's own replay cache
(enabled by default in both MIT and Heimdal krb5, and not something this
code disables or configures) to reject a captured/replayed
AP-REQ -- gss_accept_sec_context() only ever sees a token once per
legitimate exchange, so there is no additional replay protection at this
layer, nor in _pending_contexts (which key on source IP for
handshake-continuation, not on ticket identity). Do not disable the krb5
replay cache (e.g. via KRB5RCACHETYPE=none) on a host running this
acceptor.

Lives outside ``services/xcep``/``services/wstep`` because one keytab/SPN
authenticates both protocols' Kerberos endpoints — they run on the same host
under the same identity, the same way a single machine's Kerberos identity
backs every SPN-registered service on it.
"""
import functools
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

from config.settings import DATA_DIR
from models import SystemConfig

logger = logging.getLogger(__name__)

# Composed from the keytabs of every profile, enabled or not; the acceptor names it in its credential
# store, never through KRB5_KTNAME, which a Kerberos MSCA connection may rewrite (A12)
KEYTAB_PATH = DATA_DIR / 'kerberos.keytab'

# In-progress (not yet `complete`) SPNEGO contexts, keyed by the client's
# source IP -- see the module docstring for why a multi-leg exchange is
# sometimes unavoidable and why IP-only (not the full connection tuple) is
# the key that actually works against a real-world client here.
_pending_contexts = {}
_PENDING_CONTEXT_TTL_SECONDS = 30


def _cleanup_expired_contexts():
    now = time.monotonic()
    expired = [key for key, (_ctx, expires_at) in _pending_contexts.items() if expires_at < now]
    for key in expired:
        del _pending_contexts[key]


@functools.lru_cache(maxsize=1)
def is_library_available():
    """Whether pyspnego and its GSSAPI backend are importable.

    Checks ``gssapi`` explicitly, not just ``spnego``: the base ``spnego``
    package is importable even without it (it ends up installed anyway as a
    transitive dependency of ``requests-ntlm``, already required for the
    WinRM admin channel), but pyspnego's Kerberos support always goes
    through GSSAPI (see module docstring) -- without it, negotiation fails
    at request time with "GSSAPIProxy requires the Python gssapi library"
    instead of the clean 503 this check is supposed to guarantee (GH #229).

    Cached: this is checked on every Kerberos-bound request and the answer
    can't change mid-process (a ``pip install`` while UCM is running
    wouldn't be picked up by already-imported ``sys.modules`` anyway).
    Mirrors the lazy-import-with-graceful-degradation pattern already used
    for ``pkilint`` and the WinRM admin channel: pyspnego's ``kerberos``
    extra pulls a C extension (``gssapi``) needing ``libkrb5-dev``, so it's
    kept out of the default requirement set (see ``requirements.txt``).
    """
    try:
        import gssapi  # noqa: F401
        import spnego  # noqa: F401
    except ImportError:
        return False
    return True


def _config(key, default=None):
    row = SystemConfig.query.filter_by(key=key).first()
    return row.value if row and row.value is not None else default


def is_enabled():
    return (_config('kerberos_enabled', 'false') or 'false').lower() == 'true'


def get_spn():
    return _config('kerberos_spn', '') or ''


def _parse_spn(spn):
    """Split a ``service/hostname@REALM`` SPN into ``(service, hostname)``.

    Needed because pyspnego's acceptor credential lookup is keyed off the
    exact ``hostname``/``service`` passed to ``spnego.server()`` — leaving
    ``hostname`` at its ``"unspecified"`` default makes GSSAPI look for an
    acceptor credential matching ``HTTP/unspecified`` instead of what's
    actually in the keytab, failing with ``GSS_S_NO_CRED`` even though the
    keytab and the client's ticket are both fine (confirmed against the lab:
    ticket acquisition for the real SPN succeeded every time; only the
    server's own credential lookup was targeting the wrong name).
    """
    spn = (spn or '').split('@', 1)[0]  # drop @REALM, not needed here
    if '/' not in spn:
        return None
    service, hostname = spn.split('/', 1)
    if not service or not hostname:
        return None
    return service, hostname


def is_configured():
    """Enabled, SPN set, and a keytab has actually been uploaded.

    Deliberately does *not* check ``is_library_available()`` — callers that
    need "can this endpoint actually work" should check both explicitly
    (``xcep_protocol.py``'s CAURI advertising does), so the two failure
    modes ("nobody configured Kerberos" vs "Kerberos is configured but the
    optional dependency isn't installed") stay distinguishable in logs.
    """
    return not_configured_reason() is None


def not_configured_reason():
    """Why the Kerberos binding authenticates nobody, None when it is configured. Which
    profile serves an authenticated principal is decided after, by its realm."""
    if not is_enabled():
        return 'Kerberos is disabled'
    if not get_spn():
        return 'no SPN set'
    if not KEYTAB_PATH.exists():
        return 'no keytab uploaded'
    return None


def sync_keytab_file(raw_bytes):
    """Atomically write ``raw_bytes`` to ``KEYTAB_PATH`` with 0600 perms.

    Write-to-temp-then-``os.replace`` rather than writing the target path
    directly: the keytab only changes when an admin uploads a new one (rare,
    API-triggered — see ``api/v2/kerberos.py``), but GSSAPI re-reads
    whatever's on disk on every request (``_new_acceptor``, below), so a
    request landing mid-write would otherwise risk reading a truncated file.
    """
    KEYTAB_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix='.kerberos-keytab-', dir=str(KEYTAB_PATH.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw_bytes)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, KEYTAB_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_stored_keytab():
    """``KEYTAB_PATH`` holds the keytab stored in the database, or is removed when none is.

    Returns 'written', 'unchanged', 'removed' or None (nothing stored, no file).
    Raises ValueError when the stored keytab cannot be decrypted on this node.
    """
    from services import shared_files
    data = shared_files.read_file(shared_files.KERBEROS_KEYTAB)
    if data is None:
        if KEYTAB_PATH.exists():
            KEYTAB_PATH.unlink()
            return 'removed'
        return None
    try:
        if KEYTAB_PATH.read_bytes() == data:
            return 'unchanged'
    except FileNotFoundError:
        pass
    sync_keytab_file(data)
    return 'written'


def restore_keytab_at_start(app):
    """Startup: the default profile takes a keytab it does not hold yet (a single node's file
    from 2.x, or the one stored before profiles), else the stored keytab is rebuilt from the
    profile when it differs; then it is written to disk. Never raises."""
    from models import SharedFile, db
    from services import shared_files, windows_profiles
    from services.windows_profiles.legacy import warn_without_realm
    from utils.ha import ha_enabled
    with app.app_context():
        try:
            profile = windows_profiles.default_profile()
            # A keytab held by any profile, enabled or not, means the import has been done
            if not windows_profiles.keytab_holders():
                data = None
                if db.session.get(SharedFile, shared_files.KERBEROS_KEYTAB) is not None:
                    data = shared_files.read_file(shared_files.KERBEROS_KEYTAB)
                elif KEYTAB_PATH.exists() and ha_enabled():
                    # Two nodes may hold different files: the operator uploads the right one
                    logger.warning("Kerberos keytab found on this node only: upload it again "
                                   "to serve it from every node")
                elif KEYTAB_PATH.exists():
                    data = KEYTAB_PATH.read_bytes()
                if data:
                    profile = profile or windows_profiles.default_for_write('system', fill=False)
                    profile.set_keytab(data)
                    windows_profiles.fill_realm(profile)
                    warn_without_realm(profile.realm, is_enabled(), get_spn(), data)
                    windows_profiles.publish_keytab()
                    db.session.commit()
                    logger.info("Kerberos keytab stored in the default Windows enrollment profile")
                elif profile is not None and profile.realm is None and windows_profiles.keytab_absent(profile):
                    # No keytab to take and none anywhere: A1's last resort applies
                    windows_profiles.fill_realm(profile)
                    if profile.realm is not None:
                        db.session.commit()
            else:
                # The profiles are the source: a file they do not compose is rebuilt, everywhere
                from services import cluster_commands
                if _rebuild_shared_keytab():
                    cluster_commands.emit(cluster_commands.RELOAD_KEYTAB)
                    logger.info("Kerberos keytab rebuilt from the Windows enrollment profiles")
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Kerberos keytab not restored from the database: {type(e).__name__}: {e}")
        # Apart: a failed rebuild above still leaves this node the stored keytab's file
        try:
            if db.session.get(SharedFile, shared_files.KERBEROS_KEYTAB) is not None:
                if write_stored_keytab() == 'written':
                    logger.info("Kerberos keytab written from the database")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Kerberos keytab file not written: {type(e).__name__}: {e}")
        finally:
            db.session.remove()


def _rebuild_shared_keytab():
    """The shared keytab set to the profiles' composition (None: removed); True when this node changed it.
    Composed under the row lock, so an upload or a node starting at the same time is neither
    overwritten with a stale composition nor reloaded twice; a concurrent insert is undone alone."""
    from sqlalchemy.exc import IntegrityError
    from models import SharedFile, db
    from services import shared_files, windows_profiles
    name = shared_files.KERBEROS_KEYTAB
    for attempt in (1, 2):
        row = (db.session.query(SharedFile).filter_by(name=name)
               .with_for_update().populate_existing().first())
        data = windows_profiles.composed_keytab()
        if row is None and data is None:
            return False
        if row is not None and data is None:
            return shared_files.drop_file(name)
        if row is not None and shared_files.read_file(name) == data:
            return False
        try:
            with db.session.begin_nested():
                shared_files.store_file(name, data, actor='system')
            return True
        except IntegrityError:
            if attempt == 2:
                raise
    return False


def inspect_keytab(path=None):
    """Load the keytab at ``path`` (default ``KEYTAB_PATH``) with GSSAPI, as the acceptor
    does, and list every entry: ``valid``, ``principal`` (the first entry, as GSSAPI names
    it), ``entries`` (``principal``, ``realm``, ``kvno``, ``enctype`` each) and ``error``.
    Never raises; a missing, unreadable or malformed keytab is ``valid: False``."""
    target = str(path) if path is not None else str(KEYTAB_PATH)
    if not os.path.exists(target):
        return {'valid': False, 'principal': None, 'entries': [], 'error': 'No keytab uploaded'}
    from services.kerberos.keytab_format import read_entries
    try:
        with open(target, 'rb') as f:
            entries = read_entries(f.read())
    except OSError:
        entries = None
    listed = [{'principal': e.principal, 'realm': e.realm, 'kvno': e.kvno, 'enctype': e.enctype}
              for e in entries or ()]
    principal, error = _gssapi_load(target)
    if error is None and entries is None:
        error = 'the entries of the keytab cannot be read'
    return {'valid': error is None, 'principal': principal if error is None else None,
            'entries': listed, 'error': error}


def _gssapi_load(target):
    """(first principal, None) when GSSAPI loads the keytab as an acceptor credential, else (None, reason)."""
    try:
        import gssapi
        creds = gssapi.Credentials(usage='accept', store={'keytab': target})
        return str(creds.name), None
    except Exception as e:
        return None, str(e)


def _new_acceptor(hostname, service):
    """A SPNEGO acceptor whose Kerberos credential is the composed keytab, named in the GSSAPI
    store: never the process' default keytab. pyspnego takes it only through these private
    arguments, checked below, so a version that drops them fails closed instead of reading KRB5_KTNAME."""
    import gssapi
    import spnego
    from spnego._context import GSSMech
    credential = gssapi.Credentials(usage='accept', store={'keytab': f'FILE:{KEYTAB_PATH}'},
                                    mechs=[gssapi.OID.from_int_seq(GSSMech.kerberos.value)])
    kerberos = spnego.server(hostname=hostname, service=service, protocol='kerberos',
                             options=spnego.NegotiateOptions.use_gssapi, _gssapi_credential=credential)
    kerberos._is_wrapped = True
    contexts = {GSSMech.kerberos: kerberos}
    server = spnego.server(hostname=hostname, service=service, protocol='negotiate',
                           _negotiate_contexts=contexts)
    if (getattr(server, '_available_contexts', None) is not contexts
            or getattr(kerberos, '_credential', None) is not credential):
        raise RuntimeError('this pyspnego version does not take the acceptor keytab')
    return server


def _ticket_realm(token):
    """The realm of the service ticket in a NegTokenInit (or raw Kerberos token), else None.
    Read from the clear part of the AP-REQ, only to say which realm has no key."""
    def tlv(data, pos):
        tag, length = data[pos], data[pos + 1]
        pos += 2
        if length & 0x80:
            count = length & 0x7f
            length = int.from_bytes(data[pos:pos + count], 'big')
            pos += count
        if pos + length > len(data):
            raise IndexError('truncated')
        return tag, data[pos:pos + length], pos + length

    def fields(data):
        out, pos = {}, 0
        while pos < len(data):
            tag, value, pos = tlv(data, pos)
            out[tag] = value
        return out

    try:
        tag, body, _ = tlv(token, 0)
        if tag != 0x60:
            return None
        oid_tag, oid, pos = tlv(body, 0)
        if oid == b'\x2b\x06\x01\x05\x05\x02':   # SPNEGO: NegTokenInit, its mechToken
            _, init, _ = tlv(body, pos)
            _, seq, _ = tlv(init, 0)
            mech_token = fields(seq).get(0xa2)
            if mech_token is None:
                return None
            _, inner, _ = tlv(mech_token, 0)
            return _ticket_realm(inner)
        if oid_tag != 0x06 or body[pos:pos + 2] != b'\x01\x00':   # Kerberos: AP-REQ only
            return None
        _, ap_req, _ = tlv(body, pos + 2)
        _, ap_seq, _ = tlv(ap_req, 0)
        _, ticket, _ = tlv(fields(ap_seq)[0xa3], 0)
        _, ticket_seq, _ = tlv(ticket, 0)
        _, realm, _ = tlv(fields(ticket_seq)[0xa1], 0)
        text = realm.decode('ascii')
        return text if text.isprintable() and 0 < len(text) <= 255 else None
    except (IndexError, KeyError, UnicodeDecodeError):
        return None


def _realm_without_key(token):
    """The ticket's realm when the composed keytab holds no entry of it, else None."""
    realm = _ticket_realm(token)
    if realm is None:
        return None
    from services.kerberos.keytab_format import read_entries
    try:
        entries = read_entries(KEYTAB_PATH.read_bytes())
    except OSError:
        entries = None
    return realm if entries is not None and realm not in {e.realm for e in entries} else None


def _accepted_target(server):
    """The principal of the keytab entry that accepted the ticket, None when GSSAPI does not say."""
    try:
        name = server._context._context.target_name
        return str(name).rstrip('\x00') if name is not None else None
    except Exception:
        return None


def _realm_of(principal):
    return principal.rpartition('@')[2] if principal and '@' in principal else None


def _served_realm_matches(server):
    """Entries are validated as their profile's realm: a client of another realm is refused."""
    target = _accepted_target(server)
    if _realm_of(target) is None:
        return True
    if _realm_of(server.client_principal) == _realm_of(target):
        return True
    logger.warning("Kerberos: client realm %s does not match the realm %s of the key that accepted it",
                   _realm_of(server.client_principal), _realm_of(target))
    return False


def _is_kerberos_negotiated(server):
    """Whether `server.negotiated_protocol` is actually ``'kerberos'``.

    Every "authenticated" return point in ``authenticate_negotiate`` treats
    this acceptor as provably single-mechanism -- "this acceptor only ever
    holds a Kerberos keytab, no NTLM credential is ever configured" -- to
    justify skipping SPNEGO's downgrade-detection MIC round in the
    early-accept branch below. That's only actually true if pyspnego agrees
    Kerberos is what got negotiated; checking here turns the assumption into
    an enforced invariant instead of trusting configuration alone. pyspnego
    resolves `negotiated_protocol` to `'ntlm'`, `'kerberos'`, or `None` (not
    yet resolved) off the exact same internal state as `client_principal`
    (confirmed in pyspnego's source: both are gated on `self._context_list`
    in `_negotiate.py`), so by the time a caller here has a truthy
    `client_principal` to check, this is never `None` for a real Kerberos
    exchange -- only a genuine NTLM negotiation would fail it.
    """
    if server.negotiated_protocol == 'kerberos':
        return True
    logger.warning(
        "Kerberos/SPNEGO: rejecting authenticated context with unexpected "
        "negotiated_protocol=%r (expected 'kerberos')", server.negotiated_protocol,
    )
    return False


@dataclass
class NegotiateResult:
    status: str  # 'challenge', 'continue', 'authenticated', or 'failed'
    client_principal: Optional[str] = None
    response_token_b64: Optional[str] = None
    error: Optional[str] = None


def authenticate_negotiate(auth_header, connection_key):
    """Perform one HTTP Negotiate leg against ``auth_header`` (the incoming
    request's ``Authorization`` value, or ``None``).

    ``connection_key`` identifies the client for the purpose of continuing an
    in-progress ``spnego`` context across legs (``request.environ['REMOTE_ADDR']``
    -- see the module docstring for why this is keyed on source IP rather than
    the full connection tuple, and why a multi-leg exchange is sometimes
    unavoidable even for Kerberos-only). Result status is one of:

    - ``'challenge'``: no (or non-Negotiate) ``Authorization`` header — the
      caller should respond ``401`` with ``WWW-Authenticate: Negotiate``,
      no token, and not read the request body.
    - ``'continue'``: a valid intermediate token was processed but the
      exchange isn't complete yet. ``response_token_b64`` must be echoed
      back via ``WWW-Authenticate: Negotiate <token>`` on a ``401`` (still no
      body should be read) so the client can send the next leg on the *same*
      connection.
    - ``'authenticated'``: the exchange completed. ``client_principal`` names
      who authenticated; ``response_token_b64``, if set, should be echoed
      back via ``WWW-Authenticate`` on the successful response for mutual
      authentication.
    - ``'failed'``: a token was presented but didn't verify (wrong keytab,
      expired ticket, NTLM attempted, malformed token, ...).

    Uses the default ``protocol='negotiate'`` -- *not* ``protocol='kerberos'``
    despite pyspnego's own docs suggesting the latter for "Kerberos only, no
    NTLM fallback" servers. That advice assumes both ends skip SPNEGO
    wrapping entirely, which is only true if you also control the client.
    A real ``Authorization: Negotiate`` header (RFC 4559) is *always* a
    SPNEGO-wrapped token, from any Windows client, unconditionally --
    confirmed against the lab: ``protocol='kerberos'`` builds a raw-Kerberos
    GSSAPI context that can't unwrap that envelope and fails with a
    ``GSS_S_NO_CRED``-flavored error even though ticket acquisition and the
    keytab were both fine, while ``protocol='negotiate'`` (which does its own
    SPNEGO unwrapping before dispatching to GSSAPI) works. NTLM still isn't
    reachable in practice, since this acceptor only ever has a Kerberos
    keytab, never an NTLM credential.
    """
    import base64

    import spnego
    import spnego.exceptions

    if not auth_header or not auth_header.startswith('Negotiate '):
        return NegotiateResult(status='challenge')

    token_b64 = auth_header[len('Negotiate '):].strip()
    try:
        token = base64.b64decode(token_b64, validate=True)
    except Exception:
        return NegotiateResult(status='failed', error='Malformed Negotiate token')

    _cleanup_expired_contexts()

    pending = _pending_contexts.pop(connection_key, None)
    if pending is not None:
        server = pending[0]
    else:
        parsed_spn = _parse_spn(get_spn())
        if not parsed_spn:
            logger.error("Kerberos: kerberos_spn is not a valid service/hostname@REALM SPN")
            return NegotiateResult(status='failed', error='Kerberos authentication failed')
        service, hostname = parsed_spn

        try:
            server = _new_acceptor(hostname, service)
        except Exception as e:
            logger.warning("Kerberos/SPNEGO context creation failed: %s", e)
            return NegotiateResult(status='failed', error='Kerberos authentication failed')

    try:
        out_token = server.step(token)
    except Exception as e:
        # A realm the keytab lacks is a client of an unserved forest, not a fault of UCM
        realm = _realm_without_key(token)
        if realm is not None:
            logger.warning("Kerberos: no key for this realm (%s) in the keytab", realm)
        elif isinstance(e, spnego.exceptions.SpnegoError):
            logger.warning("Kerberos/SPNEGO authentication failed: %s", e)
        else:
            logger.error("Unexpected error during Kerberos/SPNEGO authentication: %s", e)
        return NegotiateResult(status='failed', error='Kerberos authentication failed')

    if not server.complete and server.client_principal:
        # The underlying Kerberos exchange already succeeded -- pyspnego is
        # only holding out for a mechListMIC round per RFC 4178's
        # anti-downgrade rule (triggered because Windows' NegTokenInit lists
        # its legacy MS-KRB5 OID ahead of the standard KRB5 OID, which
        # doesn't match this acceptor's own preferred order; see the module
        # docstring). Confirmed against the lab that a real WCF client
        # (MS-WebServices/1.0 -- what GPMC's policy-server "Validate" and GPO
        # machine autoenrollment both use) never completes that round: every
        # retry re-sends its *original* token rather than a MIC-only
        # NegTokenResp (three consecutive legs, byte-identical 1869-byte
        # inbound token each time), so waiting for it means the handshake
        # never finishes against this client. Accepting here instead is a
        # deliberate trade: it skips RFC 4178's downgrade-detection MIC, but
        # this acceptor only ever holds a Kerberos keytab -- no NTLM
        # credential is ever configured -- so there is no weaker mechanism
        # for a client to have been downgraded *to*, which is what that MIC
        # exists to detect. _is_kerberos_negotiated below turns "no weaker
        # mechanism configured" into a checked invariant rather than an
        # assumption.
        if not _is_kerberos_negotiated(server) or not _served_realm_matches(server):
            return NegotiateResult(status='failed', error='Kerberos authentication failed')
        return NegotiateResult(status='authenticated', client_principal=server.client_principal)

    if not server.complete:
        if not out_token:
            # Shouldn't happen -- an incomplete exchange with nothing left
            # to send back means neither side can make further progress.
            logger.warning("Kerberos/SPNEGO: negotiation incomplete with no continuation token")
            return NegotiateResult(status='failed', error='Kerberos authentication failed')
        _pending_contexts[connection_key] = (server, time.monotonic() + _PENDING_CONTEXT_TTL_SECONDS)
        return NegotiateResult(status='continue', response_token_b64=base64.b64encode(out_token).decode('ascii'))

    if not _is_kerberos_negotiated(server) or not _served_realm_matches(server):
        return NegotiateResult(status='failed', error='Kerberos authentication failed')
    response_b64 = base64.b64encode(out_token).decode('ascii') if out_token else None
    return NegotiateResult(
        status='authenticated',
        client_principal=server.client_principal,
        response_token_b64=response_b64,
    )
