"""Delete the rows a deploy/import test created: ids newer than the start of the test."""


def delete_leftovers(app):
    from models import (db, CA, Certificate, DeployTarget, DeployBinding,
                        DeployDelivery, MicrosoftCA, MSCARequest)
    # Children first: deliveries and requests point at bindings, targets, CAs and certificates
    order = [DeployDelivery, DeployBinding, DeployTarget, MSCARequest, MicrosoftCA, Certificate, CA]
    with app.app_context():
        before = [(m, db.session.query(db.func.max(m.id)).scalar() or 0) for m in order]
    yield
    with app.app_context():
        for model, top in before:
            model.query.filter(model.id > top).delete(synchronize_session=False)
        db.session.commit()
