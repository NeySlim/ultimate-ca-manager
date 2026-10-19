"""A notification has no subject template: every event builds its own
subject, and nothing ever wrote or read `subject_template`."""
from models.email_notification import NotificationConfig


def test_it_is_not_exposed(app):
    with app.app_context():
        assert 'subject_template' not in NotificationConfig(type='cert_expiring').to_dict()
