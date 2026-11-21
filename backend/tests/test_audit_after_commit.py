"""An audit entry is written last, once the change it describes is durable.

`AuditService.log_action` commits the session it is given, and rolls all of it
back when it cannot write its own entry. Called anywhere other than last, it
is therefore the call that decides whether the business change survives, and
the caller answers the client with a success for something that has just been
undone.

The order has to hold in both directions:

* A change already staged when the audit fires rides on the audit's commit.
  The entry is what makes it durable, and an entry that cannot be written
  takes it back down with it.
* A change staged *after* the audit is described by an entry that is already
  durable. The audit says the thing happened; the commit that was supposed to
  make it happen can still fail. `services/ca/ca_crud.py` read that way: the
  files were already deleted from disk, the entry said the authority was
  deleted, and only then did the row go.

Nineteen places had it one way or the other and were corrected one at a
time: five deployment routes, two CRL configuration routes, generating a CRL
and a delta CRL, installing an externally signed one, deleting a certificate,
deleting a certificate authority, two ACME authorization paths, a webhook
refusal and a Microsoft CA refusal that each recorded the very request they
were refusing, an SSO role synchronisation that wrote the change down before
making it, a bundle import whose audit committed the caller's whole bundle,
and the two deployment paths that recorded a push already made on a remote
host before the record of it was safe.

Correcting them one at a time does not stop the twentieth. This does, as far
as it reaches. It reads one function at a time, so a write staged inside a
helper that function calls is invisible to it: three of the nineteen hid
theirs that way (`acme_api.py`, `msca.py:sign_csr`, `hsm.py`) and would not
be caught coming back. A scan cannot see an audit reached through a variable
either, and it reads the thirteen largest functions in these zones by
statement order alone rather than by path. What it does cover is every shape
the nineteen took.

The alternative was to change `log_action` so that it stops committing its
caller's session. That changes the meaning of 324 call sites at once, several
of which have no other commit and rely on it. The property is cheaper to
state here: capture what the entry needs, commit, then record.
"""
import ast
import os
import re


SESSION_WRITES = {'add', 'delete', 'add_all', 'merge'}
# Every helper in `services/audit/helpers.py`, not the four that happened to
# appear in the campaign: all nine delegate to `log_action` and therefore all
# nine commit the session they are called with.
AUDIT_CALLS = {'log_action', 'log_acme', 'log_auth', 'log_ca', 'log_certificate',
               'log_csr', 'log_scep', 'log_system', 'log_user'}

# `obj.field = value` stages a change as surely as `db.session.add(obj)`, and
# it is how most of this codebase does it: seven of the sixteen sites the
# campaign corrected staged their change that way and were invisible to a
# scan that only looked for `add` and `delete`. These owners are not rows.
NOT_A_ROW = {
    'self', 'cls', 'g', 'request', 'response', 'app', 'current_app',
    'session', 'logger', 'os', 'sys', 'json', 'result', 'results',
    'args', 'kwargs', 'e', 'err', 'exc', 'service', 'client', 'provider_cls',
}
COMMITS = {'safe_commit', '_safe_commit', 'commit_or_rollback'}
# A rollback settles the session too. What follows it carries nothing, which
# is why a refusal that audits has to roll back first: `api/v2/webhooks.py`
# audited its refusal with the refused webhook's URL and signing secret still
# staged, and the audit's own commit persisted them.
SETTLES = {'rollback'}

# Enumerating every path through a function is exponential in the number of
# branches. Past this many, enumeration is abandoned for that function and it
# falls back on reading its statements in order. Truncating the enumeration
# instead, as this first did, stopped at the cut and never looked at the rest
# of the function at all, so an audit written past it was invisible. The cap
# is set where the cost stops buying much: at 20000 it takes about nine
# seconds and leaves eight audit-writing functions on the fallback, at 100000
# thirty seconds for seven.
PATH_CAP = 20000


class _TooManyPaths(Exception):
    """Raised when a function has more branches than PATH_CAP can enumerate."""

# Written down rather than silently tolerated. Each one would carry the reason
# it is the exception, and the reason is what stops it being copied. There are
# none: the two that were here did not survive being checked. `reset_db`
# turned out to be a route that never ran, and the ordering it was exempted
# for was fixed instead; `create_certificate` was a false positive of a rule
# that judged any later write as the entry running ahead of its change.
DELIBERATE = set()


# Filled by `_offenders` before it scans: the plain function names that
# reach an audit call themselves. Half the refusals in this codebase record
# themselves through a local wrapper -- `_audit` in the Microsoft CA routes,
# `_safe_audit_log` and `record_restore` around the backup ones, `_log_audit`
# in the importer, `_audit_acme` in the ACME server. A scan that only knew
# `X.log_action(...)` looked straight past all of them, which is how the
# refusal that persisted what it refused stayed invisible to its own guard.
# name -> whether the wrapper commits before it records. `_record_failure`
# in the deployment service writes the failure down and then records it, so a
# change staged before the call is settled by the time the entry is written;
# `_audit` in the Microsoft CA routes only records. Reading both as a bare
# audit reported the first for something it had just made safe.
AUDIT_WRAPPERS = {}

# Stage an entry into the caller's transaction and never commit: the entry rides the
# caller's commit, which is the order this rule asks for. Followed by name, a homonym
# deep inside one (a cipher's `.decrypt`) would otherwise make it read as a committing audit.
STAGES = {'stage_audit_entry'}


def _kind(call):
    """Classify a call as staging a change, committing, or auditing."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in AUDIT_CALLS:
        return 'audit'
    if isinstance(func, ast.Name) and func.id in AUDIT_WRAPPERS:
        return 'commit+audit' if AUDIT_WRAPPERS[func.id] else 'audit'
    if isinstance(func, ast.Attribute) and func.attr in AUDIT_WRAPPERS:
        return 'commit+audit' if AUDIT_WRAPPERS[func.attr] else 'audit'
    if isinstance(func, ast.Name) and func.id in COMMITS:
        return 'commit'
    if isinstance(func, ast.Attribute) and func.attr == 'commit':
        return 'commit'
    if isinstance(func, ast.Attribute) and func.attr in SETTLES:
        owner = func.value
        if isinstance(owner, ast.Attribute) and owner.attr == 'session':
            return 'commit'
        if isinstance(owner, ast.Name) and owner.id == 'session':
            return 'commit'
    if isinstance(func, ast.Attribute) and func.attr in SESSION_WRITES:
        # `db.session.add(...)`, not some set's `.add(...)`. The owner has to
        # be a session: a plain Python set named `renewed_ca_ids` cost this
        # scan a false positive once, and the false positive was believed.
        owner = func.value
        if isinstance(owner, ast.Attribute) and owner.attr == 'session':
            return 'write'
        if isinstance(owner, ast.Name) and owner.id == 'session':
            return 'write'
    return None


def _stages_a_change(node):
    """Whether this statement mutates a column on a row already in session."""
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AugAssign):
        targets = [node.target]
    else:
        return False
    for target in targets:
        if not isinstance(target, ast.Attribute):
            continue
        if target.attr.startswith('_'):
            # A mapped column is never private. `service._finalizing_order_id`
            # is bookkeeping on a Python object, and reading it as a staged
            # change reported the ACME finalize route for a `finally` clause.
            continue
        owner = target.value
        if isinstance(owner, ast.Name) and owner.id not in NOT_A_ROW:
            return True
    return False


# `_events` is pure over an immutable tree, and `_paths` asks it for the same
# subtrees over and over as it walks every control-flow path: 1.5 million
# calls for 3744 functions in one run, each re-walking its subtree. Keyed by
# node identity and emptied whenever the wrapper set is recomputed, since
# `_kind` reads it.
_EVENTS_CACHE = {}


def _events(node):
    cached = _EVENTS_CACHE.get(node)
    if cached is not None:
        return cached
    out = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            kind = _kind(child)
            if kind == 'commit+audit':
                out.append((child.lineno, 'commit'))
                out.append((child.lineno, 'audit'))
            elif kind:
                out.append((child.lineno, kind))
        elif _stages_a_change(child):
            out.append((child.lineno, 'write'))
    # By line only, and stably. Sorting the pairs compared the kind as a
    # string when two events shared a line, so `audit` came before `commit`
    # by alphabet: a wrapper that commits and then records read as recording
    # first, and two statements separated by a semicolon swapped as well.
    result = sorted(out, key=lambda event: event[0])
    _EVENTS_CACHE[node] = result
    return result


def _paths(body, decided=None):
    """One (events, decisions) pair per control-flow path through `body`.

    Branch-blind scanning reads a refusal audited in one arm and a commit
    reached only in the other as a single sequence. Three quarters of what it
    reported were pairs that no single request can reach.

    Decisions are carried along each path so a condition cannot be answered
    both ways on the same one. Without that, `if commit:` written twice in a
    function produces a path that skips the commit and takes the audit, which
    no call can do; `services/cert/mixins/csr.py` was reported for exactly
    that.
    """
    decided = dict(decided or {})
    results = [([], decided)]

    def stop_at(stmt):
        return [(ev + [(getattr(stmt, 'lineno', 0), 'stop')], d)
                for ev, d in results]

    for stmt in body:
        if isinstance(stmt, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
            return stop_at(stmt)

        if isinstance(stmt, ast.If):
            key = ast.dump(stmt.test)
            # The condition runs before either arm, and it is not decoration:
            # `if not commit_or_rollback(...)` is where this codebase commits.
            # Reading only the arms made that commit invisible and reported
            # `renew_certificate_in_place`, which commits exactly there.
            asked = _events(stmt.test)
            merged = []
            for events, taken in results:
                if events and events[-1][1] == 'stop':
                    merged.append((events, taken))
                    continue
                if taken.get(key) is not False:
                    for arm, after in _paths(stmt.body, {**taken, key: True}):
                        merged.append((events + asked + arm, after))
                if taken.get(key) is not True:
                    otherwise = ({**taken, key: False})
                    arms = (_paths(stmt.orelse, otherwise) if stmt.orelse
                            else [([], otherwise)])
                    for arm, after in arms:
                        merged.append((events + asked + arm, after))
                if len(merged) > PATH_CAP:
                    raise _TooManyPaths()
            results = merged
            continue

        if isinstance(stmt, (ast.For, ast.While, ast.AsyncFor)):
            # Zero trips or one. A second trip repeats the first one's events
            # and reveals no ordering the first does not. The `else` clause
            # runs when the loop was not broken out of, so it follows the
            # body rather than replacing it.
            # What is iterated over, or tested, runs whether or not the body
            # does.
            asked = _events(stmt.iter if isinstance(stmt, (ast.For, ast.AsyncFor))
                            else stmt.test)
            tail = _paths(stmt.orelse, {}) if stmt.orelse else [([], {})]
            branches = [([], {})] + _paths(stmt.body, {})
            branches = [(asked + b + t, {})
                        for b, _bd in branches for t, _td in tail]
        elif isinstance(stmt, ast.Try):
            # `else` runs after the body, and a handler runs after some
            # prefix of it. Modelling the handler as replacing the body
            # entirely was the hole: a change staged in the body and audited
            # in the handler appeared on no path at all, which is exactly the
            # shape of the Microsoft CA refusal that persisted what it was
            # refusing, and of every refusal written that way.
            arms = []
            for body_events, _d in _paths(stmt.body, {}):
                if stmt.orelse:
                    for tail, _t in _paths(stmt.orelse, {}):
                        arms.append(body_events + tail)
                else:
                    arms.append(body_events)
            for handler in stmt.handlers:
                for handler_events, _d in _paths(handler.body, {}):
                    for body_events, _d2 in _paths(stmt.body, {}):
                        for prefix in _states_before_raising(body_events):
                            arms.append(prefix + handler_events)
            if stmt.finalbody:
                tails = [t for t, _d in _paths(stmt.finalbody, {})]
                arms = [a + t for a in arms for t in tails][:PATH_CAP]
            branches = [(a, {}) for a in arms]
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            branches = _paths(stmt.body, {})
        else:
            branches = [(_events(stmt), {})]

        merged = []
        for events, taken in results:
            if events and events[-1][1] == 'stop':
                merged.append((events, taken))
                continue
            for arm, _after in branches:
                merged.append((events + arm, taken))
                if len(merged) > PATH_CAP:
                    raise _TooManyPaths()
        results = merged

    return results


def _states_before_raising(events):
    """One prefix of `events` per distinct state an exception can interrupt.

    A handler runs after some prefix of the body, and which prefix matters
    only through two facts: whether a change is staged, and whether anything
    has been committed yet. Keeping one prefix per pair holds the model exact
    without enumerating every statement boundary.
    """
    seen = {}
    pending = False
    committed = False
    for index in range(len(events) + 1):
        seen.setdefault((pending, committed), events[:index])
        if index == len(events):
            break
        kind = events[index][1]
        if kind == 'write':
            pending = True
        elif kind == 'commit':
            pending = False
            committed = True
        elif kind == 'stop':
            break
    return list(seen.values())


def _in_order(path):
    """The line of the first audit reached out of order on this path.

    Two ways to be out of order, and the second needs a condition the first
    does not. An entry written while a change is staged carries that change
    on its own commit. An entry written before anything at all has been
    committed describes work that has not happened yet, and the commit meant
    to do it can still fail.

    Once something has been committed, a later write is separate work with
    its own commit, not the subject of the entry. `request_certificate`
    commits the order, records it, and only then may set it to processing and
    commit again; reading that as an entry running ahead of its change was
    wrong, and it is the same shape that made `create_certificate` look like
    an offender worth exempting.
    """
    pending = False
    committed_something = False
    for index, (line, kind) in enumerate(path):
        if kind == 'stop':
            break
        if kind == 'write':
            pending = True
        elif kind == 'commit':
            pending = False
            committed_something = True
        elif kind == 'audit':
            if pending:
                return line          # the entry carries the change
            if not committed_something:
                staged = False
                for _later_line, later_kind in path[index + 1:]:
                    if later_kind == 'stop':
                        break
                    if later_kind == 'write':
                        staged = True
                    elif later_kind == 'commit' and staged:
                        return line  # the entry ran ahead of the change
    return None


def _handler_audits_over_pending_work(node):
    """A handler that records an entry while the body still holds a change.

    Cheap because it looks at one `try` at a time: the body of a single one
    has few enough branches to enumerate whatever the size of the function
    around it.
    """
    for stmt in ast.walk(node):
        if not isinstance(stmt, ast.Try):
            continue
        try:
            body_paths = [events for events, _d in _paths(stmt.body)]
        except _TooManyPaths:
            body_paths = [_events_of_block(stmt.body)]
        except RecursionError:
            body_paths = [_events_of_block(stmt.body)]
        # Any point in the body where a change is staged and not yet
        # committed is a point an exception can interrupt.
        reaches_pending = False
        for events in body_paths:
            staged = False
            for _line, kind in events:
                if kind == 'write':
                    staged = True
                elif kind == 'commit':
                    staged = False
                if staged:
                    reaches_pending = True
                    break
            if reaches_pending:
                break
        if not reaches_pending:
            continue
        for handler in stmt.handlers:
            settled = False
            for line, kind in _events_of_block(handler.body):
                if kind == 'commit':
                    settled = True
                elif kind == 'audit' and not settled:
                    return line
    return None


def _events_of_block(body):
    out = []
    for stmt in body:
        out.extend(_events(stmt))
    return sorted(out, key=lambda event: event[0])


def _audit_out_of_order(fn):
    """The line of the first audit this function reaches out of order.

    A function with more branches than `PATH_CAP` can enumerate falls back on
    reading its statements in order, which is weaker: it cannot tell an arm
    from the arm beside it, so it only reports the half of the rule that is
    safe to judge that way, a change already staged when the entry is
    written. Forty functions in the scanned zones are past the cap, and
    silently not analysing them was worse than analysing them roughly.
    """
    try:
        paths = [events for events, _decided in _paths(fn.body)]
    except _TooManyPaths:
        flat = _events(fn)
        pending = False
        for line, kind in flat:
            if kind == 'write':
                pending = True
            elif kind == 'commit':
                pending = False
            elif kind == 'audit':
                if pending:
                    return line
                pending = False
        # Reading the statements in order settles a change at the first
        # commit it meets, which hides the one shape this whole rule exists
        # for: a refusal audited in a handler, reached from the middle of a
        # body whose commit is further down and never ran. Every `try` in the
        # function is therefore looked at on its own, where the enumeration
        # is small enough to be exact.
        return _handler_audits_over_pending_work(fn)

    for path in paths:
        out_of_order = _in_order(path)
        if out_of_order is not None:
            return out_of_order
    return None


# Everywhere an audit entry is written from. `middleware`, `security` and
# `websocket` were outside the first scan and hold three of them.
ZONES = ('api', 'services', 'auth', 'utils', 'middleware', 'security',
         'websocket', 'models')


def _find_audit_wrappers(trees):
    """Function names that reach an audit call, directly or through another.

    Iterated to a fixed point so a wrapper around a wrapper counts too.
    """
    bodies = {}
    for tree in trees:
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                bodies.setdefault(fn.name, []).append(fn)

    # What each name calls, collected once. The fixed point below then reads
    # these sets instead of walking every function again on every pass, which
    # is what made this the slowest test in the suite: same answer, one walk.
    attribute_calls = {}
    plain_calls = {}
    for name, definitions in bodies.items():
        attrs, plains = set(), set()
        for fn in definitions:
            for call in ast.walk(fn):
                if not isinstance(call, ast.Call):
                    continue
                func = call.func
                if isinstance(func, ast.Attribute):
                    attrs.add(func.attr)
                elif isinstance(func, ast.Name):
                    plains.add(func.id)
        attribute_calls[name] = attrs
        plain_calls[name] = plains

    wrappers = set()
    changed = True
    while changed:
        changed = False
        for name in bodies:
            if name in wrappers or name in STAGES:
                continue
            attrs = attribute_calls[name]
            if (attrs & AUDIT_CALLS or attrs & wrappers
                    or plain_calls[name] & wrappers):
                wrappers.add(name)
                changed = True
    # A route named after what it does is not a wrapper for it. Only names
    # that read as "record this" are followed; anything else would make every
    # function that happens to audit into an audit itself, and the rule would
    # fire on its own callers.
    # Named like something that records an entry, not merely containing the
    # word. `create_txt_record` publishes a DNS record and matched on
    # "record", so every provider call that publishes one read as an audit.
    named = {name for name in wrappers
             if 'audit' in name.lower()
             or re.match(r'_?(log|record)(_|$)', name.lower())}

    # And whether each one settles the session before it records.
    settles_first = {}
    for name in named:
        settles = False
        for fn in bodies.get(name, []):
            seen_commit = False
            events = [(c.lineno, _kind_without_wrappers(c))
                      for c in ast.walk(fn) if isinstance(c, ast.Call)
                      and _kind_without_wrappers(c)]
            for line, kind in sorted(events, key=lambda event: event[0]):
                if kind == 'commit':
                    seen_commit = True
                elif kind == 'audit' and seen_commit:
                    settles = True
                    break
        settles_first[name] = settles
    return settles_first


def _kind_without_wrappers(call):
    """`_kind` before the wrapper table exists, used to build it."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in AUDIT_CALLS:
        return 'audit'
    if isinstance(func, ast.Name) and func.id in COMMITS:
        return 'commit'
    if isinstance(func, ast.Attribute) and func.attr == 'commit':
        return 'commit'
    return None


def _offenders():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    found = []
    parsed = []
    for zone in ZONES:
        for base, _dirs, names in os.walk(os.path.join(here, zone)):
            if '__pycache__' in base:
                continue
            for name in names:
                if not name.endswith('.py'):
                    continue
                path = os.path.join(base, name)
                try:
                    tree = ast.parse(open(path).read())
                except SyntaxError:
                    continue
                parsed.append((path, tree))

    AUDIT_WRAPPERS.clear()
    AUDIT_WRAPPERS.update(_find_audit_wrappers([t for _p, t in parsed]))
    _EVENTS_CACHE.clear()   # `_kind` reads AUDIT_WRAPPERS, just rebuilt

    for path, tree in parsed:
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            hit = _audit_out_of_order(fn)
            if hit:
                rel = os.path.relpath(path, here)
                if f'{rel}:{fn.name}' not in DELIBERATE:
                    found.append(f'{rel}:{hit} {fn.name}')
    return sorted(found)


CANARY = """
from models import db
from services.audit_service import AuditService


def revoke_thing_out_of_order(cert, reason):
    cert.revoked = True
    AuditService.log_certificate('revoke', cert.id, {'reason': reason})
    db.session.commit()


def revoke_thing_in_order(cert, reason):
    cert.revoked = True
    db.session.commit()
    AuditService.log_certificate('revoke', cert.id, {'reason': reason})
"""


class TestTheScanStillFinds:
    """The rule above asserts an empty list, which is also what a broken
    scanner returns. `DELIBERATE` is empty, so nothing else exercises the
    detection: these two do, on a known offender and its corrected twin.
    """

    def _function(self, name):
        tree = ast.parse(CANARY)
        return next(fn for fn in ast.walk(tree)
                    if isinstance(fn, ast.FunctionDef) and fn.name == name)

    def test_an_audit_before_the_commit_is_reported(self):
        assert _audit_out_of_order(self._function(
            'revoke_thing_out_of_order')) is not None

    def test_the_same_function_written_in_order_is_not(self):
        assert _audit_out_of_order(self._function(
            'revoke_thing_in_order')) is None


STAGING = """
def stage_audit_entry(**fields):
    return _staged_copy(fields)


def _staged_copy(entry):
    return cipher.decrypt(entry)


def decrypt(data):
    return AuditService.log_action('decrypted')


def _audit_decrypted(data):
    return cipher.decrypt(data)
"""


class TestStagingIsNotAnAudit:
    def test_a_staging_helper_never_becomes_a_wrapper(self):
        wrappers = _find_audit_wrappers([ast.parse(STAGING)])
        assert 'stage_audit_entry' not in wrappers
        # Any other name is still followed through the same homonym
        assert '_audit_decrypted' in wrappers


class TestAuditLast:
    def test_no_audit_is_written_out_of_order(self):
        offenders = _offenders()
        assert offenders == [], (
            'at these places an audit entry and the change it describes are '
            'not committed in that order, so the entry decides whether the '
            f'change survives or describes one that may not: {offenders}. '
            'Capture what the entry needs, commit, then record.')

    def test_every_exception_is_still_earning_its_place(self):
        """An exemption nobody re-checks is a hole nobody sees.

        Two things have to hold: the function still exists, and removing the
        exemption still produces an offender. An exemption that no longer
        changes the answer is one the code has outgrown, and leaving it there
        blesses whatever is written in that function next.
        """
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for entry in sorted(DELIBERATE):
            path, name = entry.rsplit(':', 1)
            full = os.path.join(here, path)
            assert os.path.exists(full), f'{path} is gone'
            tree = ast.parse(open(full).read())
            functions = {fn.name: fn for fn in ast.walk(tree)
                         if isinstance(fn, (ast.FunctionDef,
                                            ast.AsyncFunctionDef))}
            assert name in functions, f'{entry} no longer names a function'
            assert _audit_out_of_order(functions[name]) is not None, (
                f'{entry} is exempted from a rule it no longer breaks; '
                'remove it rather than leave it standing')
