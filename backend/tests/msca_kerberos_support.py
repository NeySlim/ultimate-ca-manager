"""python-gssapi faked at its boundary for the Microsoft CA Kerberos sign-in: no KDC, no keytab read.

``FakeGssapi.install(monkeypatch)`` puts the fake in ``sys.modules``; it records each acquisition
(principal and credential store) and each security context, and fails as told:
``acquire_error`` / ``step_error`` (a minor status text), ``server_token`` for mutual authentication.
"""
import sys
import types


class FakeGSSError(Exception):
    def __init__(self, text, min_code=2529638936, maj_code=851968):
        super().__init__(f'Major ({maj_code}): Unspecified GSS failure, Minor ({min_code}): {text}')
        self.text, self.min_code, self.maj_code = text, min_code, maj_code

    def get_all_statuses(self, code, is_maj):
        return ['Unspecified GSS failure.  Minor code may provide more information'] if is_maj else [self.text]


class FakeCredentials:
    def __init__(self, name=None, usage=None, mechs=None, store=None):
        self.name, self.usage, self.store = name, usage, store


class FakeContext:
    def __init__(self, fake, name, creds, usage, mech, flags, channel_bindings):
        self.fake, self.target, self.creds, self.flags = fake, name, creds, flags
        self.complete = False

    def step(self, token=None):
        if token is None:
            if self.fake.step_error:
                raise FakeGSSError(self.fake.step_error)
            self.fake.tokens.append((self.target, self.creds))
            return b'client-token'
        if token != self.fake.server_token:
            raise FakeGSSError(self.fake.krb_error or 'The server token is not valid')
        self.complete = True
        return None


class FakeGssapi:
    def __init__(self):
        self.acquired = []      # (principal, store) per acquisition
        self.tokens = []        # (target, credentials) per token sent
        self.bindings = []      # channel bindings of each security context
        self.destroyed = []     # memory caches destroyed (krb5.cc_destroy)
        self.acquire_error = None
        self.step_error = None
        self.krb_error = None
        self.server_token = b'server-token'

    def module(self):
        fake = self
        exceptions = types.SimpleNamespace(GSSError=FakeGSSError)

        def credentials(name=None, usage=None, mechs=None, store=None):
            if fake.acquire_error:
                error = fake.acquire_error
                raise error if isinstance(error, Exception) else FakeGSSError(error)
            fake.acquired.append((name[1] if name else None, dict(store) if store else None))
            return FakeCredentials(name, usage, mechs, store)

        def context(name=None, creds=None, usage=None, mech=None, flags=None, channel_bindings=None):
            fake.bindings.append(channel_bindings)
            return FakeContext(fake, name[1], creds, usage, mech, flags, channel_bindings)

        module = types.ModuleType('gssapi')
        module.exceptions = exceptions
        module.OID = types.SimpleNamespace(from_int_seq=lambda dotted: dotted)
        module.NameType = types.SimpleNamespace(kerberos_principal='principal', hostbased_service='service')
        module.RequirementFlag = types.SimpleNamespace(mutual_authentication=2, out_of_sequence_detection=8,
                                                       delegate_to_peer=1)
        module.Name = lambda value, kind: (kind, value)
        module.Credentials = credentials
        module.SecurityContext = context
        return module

    def krb5(self):
        fake = self
        module = types.ModuleType('krb5')
        module.init_context = lambda: 'ctx'
        module.cc_resolve = lambda ctx, name: name.decode()
        module.cc_destroy = lambda ctx, cache: fake.destroyed.append(cache)
        return module

    def install(self, monkeypatch):
        monkeypatch.setitem(sys.modules, 'gssapi', self.module())
        monkeypatch.setitem(sys.modules, 'krb5', self.krb5())
        from services.msca import kerberos
        monkeypatch.setattr(kerberos, '_HELD', {})
        return self

    @property
    def principals(self):
        return [principal for principal, _store in self.acquired]


def sign_in(auth, host='ca.example'):
    """The Authorization header ``auth`` sends to ``host``: its credential is acquired then."""
    return auth._token(host)


def record_principals(monkeypatch):
    """The principal (and keytab) each certsrv client built signs in with, recorded as it is built."""
    from services.msca import connection
    seen = []

    def acquire(kept, principal, keytab, channel='certsrv'):
        seen.append(principal)

    class Auth:
        def __init__(self, credential, **kwargs):
            credential()

    monkeypatch.setattr(connection, 'initiator_credential', acquire)
    monkeypatch.setattr(connection, 'KerberosAuth', Auth)
    return seen
