"""Delete the rows a deploy/import test created: ids newer than the start of the test."""


def _purge(table, column, values, depth=0):
    """Delete the rows of *table* whose *column* is in *values*, after the rows that
    reference them through a foreign key (PostgreSQL enforces every one)."""
    from models import db
    if not values or depth > 8:
        return
    for child in db.metadata.sorted_tables:
        for fk in child.foreign_keys:
            if fk.column.table is not table or child is table:
                continue
            keys = [k for (k,) in db.session.execute(
                db.select(table.c[fk.column.name]).where(table.c[column].in_(values)))]
            _purge(child, fk.parent.name, [k for k in keys if k is not None], depth + 1)
    db.session.execute(db.delete(table).where(table.c[column].in_(values)))


def delete_leftovers(app):
    from models import (db, CA, Certificate, DeployTarget, DeployBinding,
                        DeployDelivery, MicrosoftCA, MSCARequest)
    order = [DeployDelivery, DeployBinding, DeployTarget, MSCARequest, MicrosoftCA, Certificate, CA]
    with app.app_context():
        before = [(m, db.session.query(db.func.max(m.id)).scalar() or 0) for m in order]
    yield
    with app.app_context():
        db.session.rollback()
        for model, top in before:
            ids = [i for (i,) in db.session.query(model.id).filter(model.id > top)]
            _purge(model.__table__, 'id', ids)
        db.session.commit()
