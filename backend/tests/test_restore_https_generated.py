"""A restored HTTPS pair is what the node serves: a stored regenerated pair would replace it at start."""
from collections import defaultdict

from services import shared_files
from services.backup.restore_extended import RestoreExtendedMixin


class _Staged:
    def __init__(self):
        self.paths = []

    def stage(self, path, data, mode):
        self.paths.append(path)


def _store_generated(app):
    from models import db
    with app.app_context():
        shared_files.store_file(shared_files.HTTPS_GENERATED, b'{"crt": "c", "key": "k"}')
        db.session.commit()


def _generated_left(app):
    from models import SharedFile, db
    with app.app_context():
        db.session.rollback()
        found = db.session.get(SharedFile, shared_files.HTTPS_GENERATED) is not None
        shared_files.drop_file(shared_files.HTTPS_GENERATED)
        db.session.commit()
        return found


def test_restoring_an_https_pair_drops_the_stored_regenerated_pair(app):
    from models import db
    _store_generated(app)
    with app.app_context():
        RestoreExtendedMixin()._restore_https_files(
            {'https_server': {'cert_pem': 'C', 'key_pem': 'K'}}, defaultdict(int), _Staged())
        db.session.commit()
    assert _generated_left(app) is False


def test_an_archive_without_an_https_pair_keeps_it(app):
    from models import db
    _store_generated(app)
    with app.app_context():
        RestoreExtendedMixin()._restore_https_files({}, defaultdict(int), _Staged())
        db.session.commit()
    assert _generated_left(app) is True
