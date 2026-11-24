"""Kerberos sign-in of a Microsoft CA connection, on certsrv and on the WinRM channel.

A saved connection acquires its initiator credential from its own keytab into an in-memory
ticket cache of its own, kept while the keytab file and the principal stay the same: no
process-wide ticket cache, environment variable or lock. GSSAPI comes from python-gssapi,
which ``pyspnego[kerberos]`` installs.
"""
import base64
import itertools
import logging
import os
import re
import threading
from urllib.parse import urlparse

from requests.auth import AuthBase
from requests.cookies import extract_cookies_to_jar

logger = logging.getLogger(__name__)

KRB5_MECH = '1.2.840.113554.1.2.2'
MISSING_LIBRARY = ('Kerberos sign-in needs the gssapi library of pyspnego[kerberos] '
                   '(pip install "pyspnego[kerberos]")')
_FILE_TYPES = ('FILE', 'WRFILE')
# KRB5_FCC_NOFILE: a readable client keytab gave MIT no initial credential for the name
_NO_INITIAL_CREDENTIAL = 2529639107
_NEGOTIATE = re.compile(r'(?:^|,)\s*Negotiate(?:\s+([^,\s]+))?\s*(?=,|$)', re.I)


class MSCAKerberosError(Exception):
    """A Kerberos sign-in to the CA failed: the message names the cause, never a secret."""


def gssapi_available():
    try:
        import gssapi  # noqa: F401
    except ImportError:
        return False
    return True


def _gssapi():
    try:
        import gssapi
    except ImportError:
        raise MSCAKerberosError(MISSING_LIBRARY) from None
    return gssapi


def gss_cause(err):
    """The readable part of a GSSAPI error: its mechanism statuses, else its general ones."""
    for code, major in ((getattr(err, 'min_code', 0), False), (getattr(err, 'maj_code', 0), True)):
        if not code:
            continue
        try:
            texts = [t for t in err.get_all_statuses(code, major) if t]
        except Exception:  # noqa: BLE001
            texts = []
        if texts:
            return '; '.join(dict.fromkeys(texts))
    return str(err) or type(err).__name__


def managed_keytab_error(path):
    """Why ``path`` cannot be a client keytab, or None.
    A file of UCM's data folder (the acceptor keytab among them) is never one."""
    if not path or not str(path).strip():
        return None
    value = str(path).strip()
    kind, sep, rest = value.partition(':')
    if sep and kind.upper() in _FILE_TYPES:
        value = rest
    elif sep and not os.path.isabs(value):
        return 'kerberos_keytab_path must be a keytab file path'
    from config.settings import DATA_DIR
    resolved = os.path.realpath(value)
    data_dir = os.path.realpath(str(DATA_DIR))
    if os.path.commonpath([resolved, data_dir]) == data_dir:
        return 'kerberos_keytab_path must not point inside the UCM data folder'
    return None


def _keytab_file(keytab):
    kind, sep, rest = keytab.partition(':')
    return rest if sep and kind.upper() in _FILE_TYPES else keytab


def _destroy_ccache(name):
    try:
        import krb5
        ctx = krb5.init_context()
        krb5.cc_destroy(ctx, krb5.cc_resolve(ctx, name.encode()))
    except Exception:  # noqa: BLE001 - best effort: an in-memory cache dies with the process anyway
        pass


class Credential:
    """An initiator credential and the in-memory ticket cache that only it uses (None: the default)."""

    def __init__(self, creds, ccache=None):
        self.creds = creds
        self.ccache = ccache

    def __del__(self):
        # Released last by whoever held it, a sign-in in flight included
        self.creds = None
        try:
            if self.ccache:
                _destroy_ccache(self.ccache)
        except Exception:  # noqa: BLE001 - interpreter shutdown
            pass


_HELD = {}                      # (connection id, channel) -> (fingerprint, Credential)
_HELD_LOCK = threading.Lock()   # guards the dictionary only: no KDC exchange runs under it
_SERIAL = itertools.count(1)


def forget(connection_id):
    """Drop the credentials a deleted connection holds."""
    with _HELD_LOCK:
        for key in [k for k in _HELD if k[0] == connection_id]:
            del _HELD[key]


def initiator_credential(connection_id, principal, keytab, channel='certsrv'):
    """The credential a connection signs in with.

    With a keytab: acquired from that keytab alone into a memory cache of its own, and acquired
    again whenever the keytab file, its path or the principal changes; ``connection_id`` None
    (a form being tested) keeps nothing. Without a keytab: the tickets the process holds.
    """
    gssapi = _gssapi()
    error = managed_keytab_error(keytab)
    if error:
        raise ValueError(error)
    mech = gssapi.OID.from_int_seq(KRB5_MECH)
    try:
        name = gssapi.Name(principal, gssapi.NameType.kerberos_principal) if principal else None
        if not keytab:
            if name is None:
                return Credential(None)
            return Credential(gssapi.Credentials(name=name, usage='initiate', mechs=[mech]))
    except gssapi.exceptions.GSSError as e:
        raise MSCAKerberosError(f'Kerberos sign-in failed: {gss_cause(e)}') from None

    key = (connection_id, channel)
    try:
        st = os.stat(_keytab_file(keytab))
        with open(_keytab_file(keytab), 'rb'):
            pass
    except OSError as e:
        if connection_id is not None:
            with _HELD_LOCK:
                _HELD.pop(key, None)
        raise MSCAKerberosError(f'Kerberos sign-in failed: the keytab {keytab} cannot be read '
                                f'({e.strerror or e})') from None
    fingerprint = (principal or '', keytab, st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    if connection_id is not None:
        with _HELD_LOCK:
            held = _HELD.get(key)
        if held is not None and held[0] == fingerprint:
            return held[1]

    ccache = f'MEMORY:ucm-msca-{connection_id if connection_id is not None else "unsaved"}-{next(_SERIAL)}'
    try:
        creds = gssapi.Credentials(name=name, usage='initiate', mechs=[mech],
                                   store={'client_keytab': keytab, 'ccache': ccache})
    except gssapi.exceptions.GSSError as e:
        _destroy_ccache(ccache)
        if connection_id is not None:
            with _HELD_LOCK:
                _HELD.pop(key, None)
        if getattr(e, 'min_code', 0) == _NO_INITIAL_CREDENTIAL:
            raise MSCAKerberosError(f'Kerberos sign-in failed: the keytab {keytab} holds no key for '
                                    f'{principal or "a principal"}') from None
        raise MSCAKerberosError(f'Kerberos sign-in failed: {gss_cause(e)}') from None
    credential = Credential(creds, ccache)
    if connection_id is not None:
        with _HELD_LOCK:
            _HELD[key] = (fingerprint, credential)
    return credential


def _negotiate_token(response):
    """The Negotiate token of a response: None without a Negotiate challenge, b'' for a bare one."""
    match = _NEGOTIATE.search(response.headers.get('www-authenticate') or '')
    if match is None:
        return None
    try:
        return base64.b64decode(match.group(1)) if match.group(1) else b''
    except ValueError:
        return b''


def _channel_bindings(response):
    """tls-server-end-point (RFC 5929) of the server certificate, as requests-kerberos sends it."""
    try:
        der = response.raw._fp.fp.raw._sock.getpeercert(True)
    except AttributeError:
        return None
    if not der:
        return None
    from cryptography import x509
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives import hashes
    try:
        algorithm = x509.load_der_x509_certificate(der).signature_hash_algorithm
    except (UnsupportedAlgorithm, ValueError):
        return None
    if algorithm is None:
        return None
    if algorithm.name in ('md5', 'sha1'):
        algorithm = hashes.SHA256()
    digest = hashes.Hash(algorithm)
    digest.update(der)
    from gssapi.raw import ChannelBindings
    return ChannelBindings(application_data=b'tls-server-end-point:' + digest.finalize())


class KerberosAuth(AuthBase):
    """HTTP Negotiate with the Kerberos mechanism, for one connection.

    What requests-kerberos does (a token on a Negotiate 401, the request sent again on its
    connection with its cookies and body rewound, mutual authentication of the answer, channel
    binding over TLS, one context per host, optional preemptive token), but a GSSAPI failure or
    a refused token raises MSCAKerberosError instead of handing back the 401.
    """

    def __init__(self, credential, *, mutual_required=False, preemptive=False, service='HTTP',
                 hostname_override=None, delegate=False, send_cbt=True):
        self._acquire = credential      # callable giving a Credential, called at the first token
        self._credential = None
        self.mutual_required = mutual_required
        self.force_preemptive = preemptive
        self.service = service
        self.hostname_override = hostname_override
        self.delegate = delegate
        self.send_cbt = send_cbt
        self.contexts = {}
        self.auth_done = False
        self.pos = None
        self._cbt = None
        self._cbt_tried = False

    def _token(self, host):
        gssapi = _gssapi()
        if self._credential is None:
            self._credential = self._acquire()
        flags = gssapi.RequirementFlag.mutual_authentication | gssapi.RequirementFlag.out_of_sequence_detection
        if self.delegate:
            flags |= gssapi.RequirementFlag.delegate_to_peer
        try:
            target = gssapi.Name(f'{self.service}@{self.hostname_override or host}',
                                 gssapi.NameType.hostbased_service)
            ctx = gssapi.SecurityContext(name=target, creds=self._credential.creds, usage='initiate',
                                         mech=gssapi.OID.from_int_seq(KRB5_MECH), flags=flags,
                                         channel_bindings=self._cbt)
            self.contexts[host] = ctx
            token = ctx.step(None)
        except gssapi.exceptions.GSSError as e:
            raise MSCAKerberosError(f'Kerberos sign-in to {host} failed: {gss_cause(e)}') from None
        return 'Negotiate ' + base64.b64encode(token or b'').decode('ascii')

    def __call__(self, request):
        if self.force_preemptive and not self.auth_done:
            request.headers['Authorization'] = self._token(urlparse(request.url).hostname)
            # Sent before the TLS socket exists: a refusal may be for the missing channel binding
            request.ucm_unbound_preemptive = self.send_cbt and self._cbt is None
        request.register_hook('response', self.handle_response)
        try:
            self.pos = request.body.tell()
        except AttributeError:
            self.pos = None
        return request

    def handle_response(self, response, **kwargs):
        if self.send_cbt and not self._cbt_tried:
            self._cbt = _channel_bindings(response)
            self._cbt_tried = True
        if self.pos is not None:
            response.request.body.seek(self.pos)
        if response.status_code == 401:
            return self._handle_401(response, **kwargs)
        return self._handle_other(response)

    def _handle_401(self, response, **kwargs):
        host = urlparse(response.url).hostname
        offered = _negotiate_token(response)
        sent = (response.request.headers.get('Authorization') or '').startswith('Negotiate ')
        # One bound ticket after a refused unbound preemptive one, as requests-kerberos retried
        if sent and not (getattr(response.request, 'ucm_unbound_preemptive', False) and self._cbt is not None):
            raise MSCAKerberosError(self._refusal(host, offered))
        if offered is None:
            raise MSCAKerberosError(f'Kerberos sign-in to {host} failed: the server does not offer '
                                    'Negotiate authentication')
        header = self._token(host)
        response.content  # noqa: B018 - read, so the connection serves the next request
        response.raw.release_conn()
        prepared = response.request.copy()
        extract_cookies_to_jar(prepared._cookies, response.request, response.raw)
        prepared.prepare_cookies(prepared._cookies)
        prepared.headers['Authorization'] = header
        retry = response.connection.send(prepared, **kwargs)
        retry.history.append(response)
        retry.request = prepared
        return self.handle_response(retry, **kwargs)

    def _refusal(self, host, token):
        ctx = self.contexts.get(host)
        if ctx is not None and token:
            gssapi = _gssapi()
            try:
                ctx.step(token)  # a KRB-ERROR names the cause (clock skew, unknown key version...)
            except gssapi.exceptions.GSSError as e:
                return f'Kerberos sign-in to {host} failed: {gss_cause(e)}'
            except Exception:  # noqa: BLE001
                pass
        return f'Kerberos sign-in to {host} failed: the server refused the ticket (HTTP 401)'

    def _handle_other(self, response):
        if self.auth_done:
            return response
        host = urlparse(response.url).hostname
        token = _negotiate_token(response)
        if token:
            gssapi = _gssapi()
            ctx = self.contexts.get(host)
            try:
                if ctx is None:
                    raise MSCAKerberosError('no context')
                ctx.step(token)
            except (gssapi.exceptions.GSSError, MSCAKerberosError):
                raise MSCAKerberosError(f'Kerberos sign-in to {host} failed: the server could not be '
                                        'authenticated (mutual authentication)') from None
            self.auth_done = True
            return response
        if response.status_code >= 400 or not self.mutual_required:
            return response
        raise MSCAKerberosError(f'Kerberos sign-in to {host} failed: the server did not authenticate '
                                'itself (mutual authentication)')

    # --- WinRM message encryption (pywinrm's Encryption calls these on session.auth) ---

    winrm_encryption_available = True

    def wrap_winrm(self, host, message):
        from gssapi.raw import IOV, IOVBuffer, IOVBufferType, wrap_iov
        iov = IOV(IOVBuffer(IOVBufferType.header, True, None), IOVBuffer(IOVBufferType.data, False, message),
                  IOVBuffer(IOVBufferType.padding, True, None), std_layout=False)
        wrap_iov(self.contexts[host], iov, confidential=True)
        header, data, padding = (buffer.value or b'' for buffer in iov)
        return data + padding, header

    def unwrap_winrm(self, host, message, header):
        import gssapi.raw as raw
        ctx = self.contexts[host]
        if _mit_mechanism(ctx):
            iov = raw.IOV(raw.IOVBuffer(raw.IOVBufferType.header, False, header),
                          raw.IOVBuffer(raw.IOVBufferType.data, False, message),
                          raw.IOVBuffer(raw.IOVBufferType.data, False, b''), std_layout=False)
            raw.unwrap_iov(ctx, iov)
            return iov[1].value or b''
        return raw.unwrap(ctx, header + message).message


def _mit_mechanism(ctx):
    """MIT unwraps WinRM's layout by IOV; Heimdal only as one token (as pyspnego decides it)."""
    try:
        from gssapi.raw import inquire_saslname_for_mech
        return inquire_saslname_for_mech(ctx.mech).mech_description == b'Kerberos 5 GSS-API Mechanism'
    except Exception:  # noqa: BLE001
        return True
