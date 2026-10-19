"""`app.initialized` and `https.enabled` are no longer seeded: nothing read
either, and the second claimed an HTTPS enforcement it did not control."""
from database_health import ensure_system_config_defaults
from models import SystemConfig, db


def test_startup_seeds_neither(app):
    with app.app_context():
        SystemConfig.query.filter(SystemConfig.key.in_(['app.initialized', 'https.enabled'])).delete(
            synchronize_session=False)
        db.session.commit()
        ensure_system_config_defaults(app)
        keys = {k for (k,) in db.session.query(SystemConfig.key)}
        assert 'app.version' in keys
        assert not keys & {'app.initialized', 'https.enabled'}
