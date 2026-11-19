"""The rows a restore announces are the rows it counts while writing, section for section.

A section counted on one side only left the progress short of its total until the commit
(announced, never counted) or at its total minus one before the end (counted, not announced).
SQLite and PostgreSQL, a merge and a replacement.
"""
import os

import pytest

from models import db
from services.backup.restore import transaction
from tests.test_restore_sso_one_per_type import target  # noqa: F401  (SQLite and PostgreSQL)

# One row or more in each section whose restorer reads rows on its own path: the SMTP server,
# the notification rules, the ACME accounts and EAB credentials (one each that is left out),
# the CRL numbers; the groups go through the generic restorer
PAYLOAD = {
    'smtp_config': [{'smtp_host': 'smtp.progress.test', 'smtp_port': 25, 'enabled': False}],
    'notification_config': [{'type': 'progress_total_a', 'enabled': True},
                            {'type': 'progress_total_b', 'enabled': False}],
    'groups': [{'name': f'progress-total-{i}'} for i in range(3)],
    'acme_accounts': [{'account_id': 'progress-total-account'}],
    'acme_eab_credentials': [{'kid': 'progress-total-kid'}],
    'crl_number_counters': [{'issuer_key': 'progress-total-issuer', 'last_number': 7}],
}


def _rows(payload):
    return {name: [dict(row) for row in rows] for name, rows in payload.items()}


@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_the_rows_announced_are_the_rows_counted(target, mode):
    from services.backup_service import BackupService
    announced, counted = [], [0]

    def row(applied=0, total=None):
        if total is not None:
            announced.append(total)
        counted[0] += applied

    with transaction.progressing(lambda step: None, row):
        BackupService()._restore_payload(_rows(PAYLOAD), os.urandom(32), mode)
    db.session.rollback()
    carried = sum(len(rows) for rows in PAYLOAD.values())
    assert announced == [carried], announced
    assert counted[0] == carried, (counted[0], carried)
