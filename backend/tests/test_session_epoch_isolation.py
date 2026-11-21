"""No file leaves the session epoch it found: the sequential suite shares one database,
and a later file's sessions would otherwise read as begun before a restore."""
from auth.session_epoch import EPOCH_KEY
from models import SystemConfig


def test_no_earlier_file_left_the_epoch_changed(app):
    with app.app_context():
        assert SystemConfig.query.filter_by(key=EPOCH_KEY).first() is None
