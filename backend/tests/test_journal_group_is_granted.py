"""The service reads the journal it is told to collect, by a grant in the unit.

Both units log to the journal, and the diagnostic bundle collects it with
`journalctl -u ucm`. Reading a system unit's journal requires systemd-journal
membership, and the service user was only ever added to the SoftHSM group, so
`collect_journal` returned nothing and the bundle shipped without the journal
its own description advertises.

The grant is declared in the unit rather than made with a `usermod` at install
time. A group added to the account is held by everything that account ever
runs and survives until someone remembers to take it away; `SupplementaryGroups`
is scoped to this service, visible where the rest of its hardening is, and
revoked by commenting out one line.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

UNITS = ('packaging/systemd/ucm.service',)
RECIPES = ('packaging/debian/postinst', 'packaging/rpm/ucm.spec')


@pytest.mark.parametrize('unit', UNITS)
def test_each_unit_grants_journal_membership(unit):
    body = (ROOT / unit).read_text(encoding='utf-8')
    assert re.search(r'^SupplementaryGroups=systemd-journal\s*$', body, re.M), \
        f'{unit} does not grant the service systemd-journal'


@pytest.mark.parametrize('unit', UNITS)
def test_the_grant_is_a_service_setting(unit):
    """In [Install] or [Unit] it would be silently ignored."""
    body = (ROOT / unit).read_text(encoding='utf-8')
    service = body.split('[Service]', 1)[1].split('\n[', 1)[0]
    assert 'SupplementaryGroups=systemd-journal' in service, f'{unit}'


@pytest.mark.parametrize('recipe', RECIPES)
def test_no_recipe_grants_the_group_to_the_account(recipe):
    """A usermod outlives the service, the unit file and the uninstall."""
    body = (ROOT / recipe).read_text(encoding='utf-8')
    assert not re.search(r'usermod\s+-aG\s+\S*systemd-journal', body), \
        f'{recipe} adds the service account to systemd-journal for good'


@pytest.mark.parametrize('unit', UNITS)
def test_the_units_still_log_to_the_journal(unit):
    """The grant is pointless if the units stop writing there."""
    body = (ROOT / unit).read_text(encoding='utf-8')
    assert re.search(r'^StandardOutput=journal\s*$', body, re.M), f'{unit}'
    assert re.search(r'^StandardError=journal\s*$', body, re.M), f'{unit}'
