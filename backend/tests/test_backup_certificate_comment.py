"""Issue #454: a certificate's comment travels in the backup archive and comes back on another
installation, line breaks and tabs included."""
import uuid

from models import Certificate, db
from tests.test_backup_cross_installation import PASSWORD, Keys, _installation, _only, _service
from tests.test_restore_replace_dependents import _authority_row, _certificate_row

COMMENT = 'Owner: PKI team\n\tTicket INC-454, 100%_kept'


def test_the_comment_is_archived_and_restored(app, tmp_path):
    include = _only('certificate_authorities', 'certificates')
    refid = f'comment-leaf-{uuid.uuid4().hex[:6]}'
    with _installation(app, f"sqlite:///{tmp_path / 'source.db'}", Keys(tmp_path, 'source')), \
            app.app_context():
        leaf = _certificate_row(refid, _authority_row(f'comment-ca-{uuid.uuid4().hex[:6]}'))
        leaf.comment = COMMENT
        db.session.commit()
        svc = _service()
        blob = svc.create_backup(PASSWORD, include=include)
        _key, archived = svc._decrypt_framed(blob, PASSWORD)
    assert [row['comment'] for row in archived['certificates']] == [COMMENT]
    with _installation(app, f"sqlite:///{tmp_path / 'target.db'}", Keys(tmp_path, 'target')), \
            app.app_context():
        _service().restore_backup(blob, PASSWORD, mode='merge')
        assert Certificate.query.filter_by(refid=refid).one().comment == COMMENT
