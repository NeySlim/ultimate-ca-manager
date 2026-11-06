"""A restore replaces the instance, which is what the documentation says.

Every restorer used to upsert what the archive held and leave the rest alone,
so restoring after a compromise kept the account, the API key or the client
certificate added after the snapshot. These tests pin what is removed, and
just as importantly what is not.
"""
import pytest

from models import db
from services.backup import manifest
from services.backup.restore.plan import RestorePlan
from services.backup.restore.replace import (
    deletion_order, replace_sections, rows_to_remove,
)

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()


class TestDeletionOrder:
    def test_a_section_goes_before_what_it_points_at(self):
        order = deletion_order(set(manifest.SECTIONS))
        position = {name: index for index, name in enumerate(order)}
        for name, section in manifest.SECTIONS.items():
            for column, target in section.references.items():
                if target == name:
                    continue    # a role built on another role: one section,
                    # and the rows inside it are removed in one statement
                if target in position and name in position:
                    assert position[name] < position[target], (
                        f"{name} would be removed after {target}, which it "
                        "points at")

    def test_a_section_goes_before_every_table_it_has_a_foreign_key_into(
            self, app):
        """The declarations are a smaller set than the foreign keys, on
        purpose: a column that reads the same on every installation is not a
        reference and is not declared as one. `acme_client_orders.account_id`
        is one of those and is also a real foreign key, so ordering by the
        declarations alone removed the ACME accounts before the orders that
        point at them: PostgreSQL refused the delete and took the whole
        replacing restore with it."""
        from services.backup.export_generic import load_model

        with app.app_context():
            order = deletion_order(set(manifest.SECTIONS))
            position = {name: index for index, name in enumerate(order)}
            section_of_table = {}
            for name, section in manifest.SECTIONS.items():
                section_of_table[load_model(section).__table__.name] = name

            late = []
            for name, section in manifest.SECTIONS.items():
                table = load_model(section).__table__
                for column in table.columns:
                    for foreign_key in column.foreign_keys:
                        target = section_of_table.get(
                            foreign_key.column.table.name)
                        if target is None or target == name:
                            continue
                        if position[name] > position[target]:
                            late.append(
                                f'{name}.{column.key} points at {target}, '
                                'which is removed first')
            assert not late, late

    def test_every_section_is_ordered_once(self):
        order = deletion_order(set(manifest.SECTIONS))
        assert sorted(order) == sorted(manifest.SECTIONS)


class TestWhatIsRemoved:
    def test_a_row_the_archive_does_not_carry_is_named(self, app):
        from models.group import Group
        with app.app_context():
            kept = Group(name='replace-kept-group')
            extra = Group(name='replace-extra-group')
            db.session.add_all([kept, extra])
            db.session.commit()
            try:
                archived = [{'name': 'replace-kept-group'}]
                plan = RestorePlan.build({'groups': archived})
                doomed = rows_to_remove('groups', archived, plan)
                assert extra.id in doomed
                assert kept.id not in doomed
            finally:
                Group.query.filter(Group.name.in_(
                    ['replace-kept-group', 'replace-extra-group'])).delete(
                    synchronize_session=False)
                db.session.commit()

    def test_a_section_the_archive_does_not_mention_is_untouched(self, app):
        """An archive taken without the optional histories must not wipe them."""
        from models.group import Group
        with app.app_context():
            group = Group(name='replace-untouched-group')
            db.session.add(group)
            db.session.commit()
            try:
                plan = RestorePlan.build({})
                removed = replace_sections({}, plan, {'groups'})
                assert removed == {}
                assert Group.query.filter_by(name='replace-untouched-group').first()
            finally:
                db.session.delete(group)
                db.session.commit()

    def test_rows_named_as_kept_survive(self, app):
        from models.group import Group
        with app.app_context():
            extra = Group(name='replace-protected-group')
            db.session.add(extra)
            db.session.commit()
            try:
                # Everything the target holds except the protected row, so the
                # only candidate for removal is the one named as kept.
                archived = [{'name': group.name} for group in Group.query.all()
                            if group.name != 'replace-protected-group']
                payload = {'groups': archived}
                plan = RestorePlan.build(payload)
                removed = replace_sections(payload, plan, {'groups'},
                                           keep={'groups': {extra.id}})
                assert removed.get('groups', 0) == 0
                assert Group.query.filter_by(name='replace-protected-group').first()
            finally:
                Group.query.filter_by(name='replace-protected-group').delete()
                db.session.commit()

    def test_a_singleton_section_is_never_pruned(self, app):
        with app.app_context():
            plan = RestorePlan.build({'smtp_config': []})
            assert rows_to_remove('smtp_config', [], plan) == []


PASSWORD = 'Correct-Horse-Battery-9'


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    return {name: name in names for name in manifest.SECTIONS}


class TestARestoreIsAReplacement:
    """What the wiki always promised, and the restore never did."""

    def test_a_row_added_after_the_snapshot_is_removed(self, app):
        from models.group import Group
        with app.app_context():
            before = Group(name='replace-in-archive')
            db.session.add(before)
            db.session.commit()

            blob = _service().create_backup(PASSWORD, include=_only('groups'))

            # Added after the snapshot: exactly what a restore after a
            # compromise is meant to take away.
            after = Group(name='replace-added-after-snapshot')
            db.session.add(after)
            db.session.commit()

            try:
                _service().restore_backup(blob, PASSWORD)
                db.session.expire_all()
                assert Group.query.filter_by(name='replace-in-archive').first()
                assert Group.query.filter_by(
                    name='replace-added-after-snapshot').first() is None
            finally:
                Group.query.filter(Group.name.in_(
                    ['replace-in-archive', 'replace-added-after-snapshot'])).delete(
                    synchronize_session=False)
                db.session.commit()

    def test_merge_mode_keeps_it(self, app):
        from models.group import Group
        with app.app_context():
            db.session.add(Group(name='merge-in-archive'))
            db.session.commit()
            blob = _service().create_backup(PASSWORD, include=_only('groups'))
            db.session.add(Group(name='merge-added-after-snapshot'))
            db.session.commit()

            try:
                _service().restore_backup(blob, PASSWORD, mode='merge')
                db.session.expire_all()
                assert Group.query.filter_by(
                    name='merge-added-after-snapshot').first() is not None
            finally:
                Group.query.filter(Group.name.in_(
                    ['merge-in-archive', 'merge-added-after-snapshot'])).delete(
                    synchronize_session=False)
                db.session.commit()

    def test_a_section_the_archive_left_out_is_untouched(self, app, create_user):
        """An archive of the groups alone must not remove the users."""
        from models import User
        create_user(username='replace_untouched_user', role='operator')
        with app.app_context():
            blob = _service().create_backup(PASSWORD, include=_only('groups'))
            _service().restore_backup(blob, PASSWORD)
            db.session.expire_all()
            assert User.query.filter_by(username='replace_untouched_user').first()

    def test_an_unknown_mode_is_refused_before_anything_happens(self, app):
        from services.backup.errors import BackupSchemaError
        with app.app_context():
            blob = _service().create_backup(PASSWORD, include=_only('groups'))
            with pytest.raises(BackupSchemaError, match='Unknown restore mode'):
                _service().restore_backup(blob, PASSWORD, mode='overwrite')


class TestTwoNamesThatAreNotTheSameValue:
    """An identity column that is not a date is not read back as one.

    Every identity value used to be handed to `datetime.fromisoformat`, which
    accepts far more than a timestamp: a template called `20260914` and one
    called `2026-09-14` came out as the same key, the index kept one of them,
    and an archived row was applied over the other. The same holds for a
    serial number, which this product stores as a historical mix of decimal
    and hexadecimal text.
    """

    NAMES = ('20260914', '2026-09-14')

    def test_the_index_tells_them_apart(self, app):
        from models.certificate_template import CertificateTemplate

        with app.app_context():
            CertificateTemplate.query.filter(
                CertificateTemplate.name.in_(self.NAMES)).delete(
                    synchronize_session=False)
            db.session.commit()
            for name in self.NAMES:
                db.session.add(CertificateTemplate(
                    name=name, template_type='server',
                    extensions_template='{}'))
            db.session.commit()

            try:
                plan = RestorePlan.build(
                    {'certificate_templates': [{'name': name}
                                               for name in self.NAMES]})
                found = {name: plan.existing_id('certificate_templates',
                                                {'name': name})
                         for name in self.NAMES}
                assert found[self.NAMES[0]] != found[self.NAMES[1]], (
                    f'both names resolve to the same row ({found}): a restore '
                    'would write one template over the other')
                for name, target_id in found.items():
                    assert CertificateTemplate.query.get(target_id).name == name
            finally:
                CertificateTemplate.query.filter(
                    CertificateTemplate.name.in_(self.NAMES)).delete(
                        synchronize_session=False)
                db.session.commit()

    def test_a_timestamp_is_still_read_back(self, app):
        """The reason the parsing is there at all: the archive spells a
        moment with a `T` and the database hands back a `datetime`."""
        from datetime import datetime

        from services.backup.restore.plan import _normalise

        moment = datetime(2026, 9, 14, 1, 2, 3)
        assert _normalise('2026-09-14T01:02:03', True) == _normalise(moment)
        assert _normalise('2026-09-14 01:02:03', True) == _normalise(moment)
