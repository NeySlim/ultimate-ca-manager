"""SCEP is configured in the database only: the SCEP_* environment variables,
offered in ucm.env, were loaded into the config and never used."""
from config.settings import Config


def test_config_carries_no_scep_environment_variables():
    assert not [a for a in dir(Config) if a.startswith('SCEP_') and a != 'SCEP_DIR']
