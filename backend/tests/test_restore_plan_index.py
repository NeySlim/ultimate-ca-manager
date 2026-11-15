"""The restore plan indexes the rows here by identity without loading them.

`_index_of` maps each section's identity to its ids here, for every section an
archive carries or points at. It loaded each row whole to read two columns:
the whole certificates table, PEMs and keys included, several times a restore.
"""
from sqlalchemy import event

from models import Certificate, db
from services.backup.manifest import SECTIONS
from services.backup.restore import plan as plan_module

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()


def test_certificates_are_indexed_without_loading_a_row(app, create_ca, create_cert):
    ca = create_ca(cn='Plan Index CA')
    issued = [create_cert(cn=f'plan-index-{n}.example.com', ca_id=ca['id']) for n in range(3)]
    loaded = []

    def count(target, context):
        loaded.append(target)

    with app.app_context():
        expected = {row.refid: row.id for row in db.session.query(Certificate.refid, Certificate.id)}
        db.session.expunge_all()
        event.listen(Certificate, 'load', count)
        try:
            index, shared, incomplete = plan_module._index_of('certificates', SECTIONS['certificates'])
        finally:
            event.remove(Certificate, 'load', count)

    assert loaded == []
    for cert in issued:
        assert index[(cert['refid'],)] == expected[cert['refid']]
    assert shared == {} and incomplete == []
