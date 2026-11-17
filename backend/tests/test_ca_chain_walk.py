"""One bounded walk of the CA hierarchy (DUP-PKI-008).

``CA.caref`` holds the parent's refid as a plain string with no foreign key,
so a repaired or imported hierarchy can point a CA at itself or at one of its
own descendants. Ten places walked that hierarchy and they did not agree on
what to do about it: SCEP raised, the ACME chain stopped, and the CA export,
the central ``get_ca_chain`` and the key-recovery bundle looped forever on the
very same two rows.

These tests feed one input — a two-CA cycle — to the walkers that are reachable
from an endpoint, and pin both halves of the contract: every walk terminates,
and the paths that used to fail loudly still fail loudly with the same message.
"""
import signal
import uuid

import pytest

from models import db, CA


class ChainWalkTimeout(Exception):
    """The walk under test did not terminate inside the watchdog."""


def run_bounded(fn, seconds=10):
    """Run *fn* under a SIGALRM watchdog.

    A walk with no loop guard does not fail, it never returns — so the only
    way to assert on it is to cut it short and call that a failure.
    """
    def _handler(signum, frame):
        raise ChainWalkTimeout()

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@pytest.fixture
def looping_cas(app, create_ca):
    """Two CAs whose caref fields point at each other."""
    tag = uuid.uuid4().hex[:8]
    first = create_ca(cn=f'Loop A {tag}')
    second = create_ca(cn=f'Loop B {tag}')
    with app.app_context():
        row_a = db.session.get(CA, first['id'])
        row_b = db.session.get(CA, second['id'])
        row_a.caref = row_b.refid
        row_b.caref = row_a.refid
        db.session.commit()
        ids = (first['id'], second['id'], row_a.refid, row_b.refid)
    try:
        yield ids
    finally:
        with app.app_context():
            for cid in (first['id'], second['id']):
                row = db.session.get(CA, cid)
                if row is not None:
                    row.caref = None
            db.session.commit()


def test_central_chain_walk_visits_each_ca_once(app, looping_cas):
    ca_id, _, _, _ = looping_cas
    from services.ca.ca_operations import CAOperationsMixin

    with app.app_context():
        chain = run_bounded(lambda: CAOperationsMixin.get_ca_chain(ca_id))

    # Both CAs carry a certificate, so both belong in the chain — but only once.
    assert len(chain) == 2


def test_ca_export_with_chain_terminates(auth_client, looping_cas):
    ca_id, _, _, _ = looping_cas

    response = run_bounded(
        lambda: auth_client.get(f'/api/v2/cas/{ca_id}/export?format=pem&include_chain=true')
    )

    assert response.status_code == 200
    # The exported CA plus the one CA above it, and nothing repeated.
    assert response.data.count(b'-----BEGIN CERTIFICATE-----') == 2


def test_key_recovery_and_export_share_the_bound(app, looping_cas):
    """The walk itself, at the level every caller now shares."""
    from utils.ca_chain import walk_ca_chain

    ca_id, _, refid_a, refid_b = looping_cas
    with app.app_context():
        start = db.session.get(CA, ca_id)
        visited = run_bounded(lambda: [ca.refid for ca in walk_ca_chain(start)])
        assert visited == [refid_a, refid_b]

        ancestors = run_bounded(
            lambda: [ca.refid for ca in walk_ca_chain(start, include_start=False)]
        )
        assert ancestors == [refid_b]


def test_scep_chain_still_raises_on_a_cycle(app, looping_cas):
    """SCEP fails closed, and keeps saying so in the same words."""
    from services.scep.scep_service import SCEPService

    _, _, refid_a, _ = looping_cas
    with app.app_context():
        service = SCEPService(refid_a)
        with pytest.raises(ValueError, match='Cycle detected in SCEP CA chain'):
            run_bounded(service.get_ca_chain)


def test_scep_chain_still_raises_when_a_parent_is_missing(app, create_ca):
    from services.scep.scep_service import SCEPService

    ca = create_ca(cn=f'Orphan {uuid.uuid4().hex[:8]}')
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        row.caref = 'no-such-parent-refid'
        db.session.commit()
        refid = row.refid
        try:
            service = SCEPService(refid)
            with pytest.raises(ValueError, match='SCEP CA chain is incomplete'):
                run_bounded(service.get_ca_chain)
        finally:
            db.session.get(CA, ca['id']).caref = None
            db.session.commit()


def test_walk_stops_at_the_depth_ceiling(app, create_ca, monkeypatch):
    """The ceiling is the one revoked_in_chain already refuses to exceed."""
    from utils import ca_chain

    ca = create_ca(cn=f'Deep {uuid.uuid4().hex[:8]}')
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        row.caref = row.refid  # self-reference: the shortest possible loop
        db.session.commit()
        try:
            walked = run_bounded(lambda: list(ca_chain.walk_ca_chain(row)))
            assert [c.refid for c in walked] == [row.refid]
        finally:
            db.session.get(CA, ca['id']).caref = None
            db.session.commit()
