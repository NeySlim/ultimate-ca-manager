"""The initial admin path of init_database creates the admin and leaves a stored app.version."""
from tests.fresh_app import fresh_app


def test_no_user_left_creates_the_admin_and_keeps_the_stored_version():
    from app import init_database
    from models import SystemConfig, User, db
    with fresh_app() as application, application.app_context():
        SystemConfig.query.filter_by(key='app.version').delete()
        db.session.add(SystemConfig(key='app.version', value='999.0', description='v'))
        User.query.delete()
        db.session.commit()

        init_database(application)

        admin = User.query.filter_by(username=application.config['INITIAL_ADMIN_USERNAME']).one_or_none()
        assert admin is not None and admin.role == 'admin'
        assert [row.value for row in SystemConfig.query.filter_by(key='app.version')] == ['999.0']
