"""Issue #459: a CA's display name and description travel in the backup archive and come back on
another installation, line breaks and tabs included."""
import uuid

from models import CA, db
from tests.test_backup_cross_installation import PASSWORD, Keys, _installation, _only, _service
from tests.test_restore_replace_dependents import _authority_row

NAME = 'Partner Root (renamed)'
DESCRIPTION = 'Signed by the partner\n\tRenewal: ask the PKI team'


def test_the_name_and_the_description_are_archived_and_restored(app, tmp_path):
    include = _only('certificate_authorities')
    refid = f'described-ca-{uuid.uuid4().hex[:6]}'
    with _installation(app, f"sqlite:///{tmp_path / 'source.db'}", Keys(tmp_path, 'source')), \
            app.app_context():
        ca, _key, _cert = _authority_row(refid)
        ca.descr, ca.description = NAME, DESCRIPTION
        db.session.commit()
        svc = _service()
        blob = svc.create_backup(PASSWORD, include=include)
        _key, archived = svc._decrypt_framed(blob, PASSWORD)
    assert [(row['descr'], row['description']) for row in archived['certificate_authorities']] == [(NAME, DESCRIPTION)]
    with _installation(app, f"sqlite:///{tmp_path / 'target.db'}", Keys(tmp_path, 'target')), \
            app.app_context():
        _service().restore_backup(blob, PASSWORD, mode='merge')
        restored = CA.query.filter_by(refid=refid).one()
        assert (restored.descr, restored.description) == (NAME, DESCRIPTION)
