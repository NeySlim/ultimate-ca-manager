"""Three places SQLite and PostgreSQL would have answered differently.

The suite runs on SQLite, so these pin the shapes that make the two agree
rather than the PostgreSQL error messages:

* a negative ``LIMIT`` — SQLite reads it as "no limit" and returns the whole
  table, PostgreSQL refuses it with ``LIMIT must not be negative``. Six
  endpoints capped the top of their limit and left the bottom open, so
  ``?limit=-1`` was a full dump on one backend and a 500 on the other.
* a ``String`` column compared to a Python int — SQLite matches on type
  affinity, PostgreSQL raises ``operator does not exist: character varying =
  integer``. ``{"ca_refid": 5}`` reached five protocol-config routes uncast.
* an ``ORDER BY`` with ties and no tie-break — the row order is the plan's
  choice, so paging hands out different pages on the two backends.
"""
import uuid

import pytest
from sqlalchemy import Column, Integer, String, create_engine, select
from sqlalchemy.orm import Session, declarative_base

from utils.pagination import parse_request_limit

_Base = declarative_base()


class _Row(_Base):
    __tablename__ = 'dual_backend_probe'
    id = Column(Integer, primary_key=True)
    name = Column(String(36))


def test_sqlite_really_does_treat_a_negative_limit_as_no_limit():
    """The premise, checked rather than assumed."""
    engine = create_engine('sqlite://')
    _Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([_Row(id=i, name=str(i)) for i in range(1, 6)])
        session.commit()
        assert len(session.scalars(select(_Row).limit(2)).all()) == 2
        assert len(session.scalars(select(_Row).limit(-1)).all()) == 5


def test_sqlite_really_does_match_a_string_column_against_an_int():
    engine = create_engine('sqlite://')
    _Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(_Row(id=5, name='5'))
        session.commit()
        assert len(session.scalars(select(_Row).filter_by(name=5)).all()) == 1


@pytest.mark.parametrize('value,expected', [
    (None, 10),
    ('', 10),
    ('abc', 10),
    (-1, 1),
    ('-1', 1),
    (0, 1),
    (1, 1),
    (7, 7),
    (999, 50),
    ('999', 50),
])
def test_a_limit_is_bounded_at_both_ends(app, value, expected):
    # Two lots corrected this family independently; `parse_request_limit` is
    # the one that survived, because it reads the request like its neighbour
    # `parse_request_pagination` does.
    with app.test_request_context(f'/?limit={value}'):
        assert parse_request_limit(10, 50) == expected


@pytest.mark.parametrize('path', [
    '/api/v2/search?q=probe&limit=-1',
    '/api/v2/dashboard/recent-cas?limit=-1',
    '/api/v2/dashboard/expiring-certs?limit=-1',
    '/api/v2/dashboard/activity?limit=-1',
    '/api/v2/audit/export?limit=-1&format=json',
    '/api/v2/deploy/deliveries?limit=-1',
])
def test_no_endpoint_passes_a_negative_limit_to_the_database(auth_client, path):
    """On PostgreSQL each of these was a 500; on SQLite, a full table."""
    assert auth_client.get(path).status_code == 200


def test_a_negative_limit_no_longer_defeats_the_cap(auth_client, create_cert):
    tag = uuid.uuid4().hex[:8]
    for i in range(3):
        create_cert(cn=f'limitprobe{tag}-{i}.example.com')

    capped = auth_client.get(f'/api/v2/search?q=limitprobe{tag}&limit=1')
    negative = auth_client.get(f'/api/v2/search?q=limitprobe{tag}&limit=-1')

    assert capped.status_code == negative.status_code == 200
    assert len(capped.get_json()['data']['certificates']) == 1
    # -1 is floored to 1, not read as "everything".
    assert len(negative.get_json()['data']['certificates']) == 1


@pytest.mark.parametrize('path', [
    '/api/v2/est/config',
])
def test_an_integer_ca_refid_is_a_clean_refusal(auth_client, path):
    """Not a 500 from the driver: the value is text before it reaches SQL."""
    response = auth_client.patch(path, json={'ca_refid': 5})
    assert response.status_code in (400, 404)
    assert response.status_code != 500


def test_no_route_hands_a_refid_column_an_unconverted_request_value():
    """The behavioural test above cannot tell this apart on SQLite — it matches
    nothing either way. PostgreSQL is where it turns into a 500, so the shape
    is what gets pinned: the value is text before it reaches the column."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for module in ('api/v2/est.py', 'api/v2/windows_profiles.py',
                   'api/v2/tsa.py', 'api/v2/scep.py'):
        for lineno, line in enumerate(
            (root / module).read_text(encoding='utf-8').splitlines(), 1
        ):
            if re.search(r"filter_by\(\s*refid\s*=\s*data\[", line) and 'str(' not in line:
                offenders.append(f'{module}:{lineno}: {line.strip()[:80]}')
    assert offenders == [], (
        'CA.refid is String(36); PostgreSQL refuses "character varying = integer": '
        + '; '.join(offenders)
    )


def test_certificate_paging_settles_its_ties(auth_client, create_cert, create_ca):
    """`revoked` has two values for the whole table, so every row of a normal
    install is tied. The order must be total, not left to the plan: paging a
    tied column has to partition the rows, and reversing the sort has to
    reverse them.

    On SQLite an unsettled ORDER BY happens to come back in rowid order, which
    is why this asserts the descending direction — that is where a missing
    tie-break shows up on this backend as well as on PostgreSQL.
    """
    tag = uuid.uuid4().hex[:8]
    ca = create_ca(cn=f'Tie CA {tag}')
    for i in range(5):
        create_cert(cn=f'tie{tag}-{i}.example.com', ca_id=ca['id'])

    def _ids(order, page):
        response = auth_client.get(
            f'/api/v2/certificates?search=tie{tag}&sort_by=revoked'
            f'&sort_order={order}&page={page}&per_page=2')
        assert response.status_code == 200
        return [row['id'] for row in response.get_json()['data']]

    ascending = _ids('asc', 1) + _ids('asc', 2) + _ids('asc', 3)
    descending = _ids('desc', 1) + _ids('desc', 2) + _ids('desc', 3)

    assert len(ascending) == len(set(ascending)), 'a row was served on two pages'
    assert ascending == sorted(ascending)
    assert descending == sorted(descending, reverse=True)
    assert descending == list(reversed(ascending))
