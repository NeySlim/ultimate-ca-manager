"""List what FIPS mode would refuse on this instance, without changing anything.

Run from backend/: ``python -m scripts.fips_preflight [--json]``. Exit code 0
when nothing blocks, 1 with blockers, 2 when a check could not run.
"""
import argparse
import json
import sys

from flask import Flask
from sqlalchemy import event

import fips_mode
from config.settings import get_config
from models import db
from services import fips_preflight


def read_only_app(config=None) -> Flask:
    """The database the service uses, opened read-only; no migration, no scheduler."""
    app = Flask('ucm-fips-preflight')
    app.config.from_object(config or get_config())
    uri = app.config['SQLALCHEMY_DATABASE_URI']
    if uri.startswith('sqlite:///') and ':memory:' not in uri:
        app.config['SQLALCHEMY_DATABASE_URI'] = (
            f"sqlite:///file:{uri[len('sqlite:///'):]}?mode=ro&uri=true")
    db.init_app(app)
    with app.app_context():
        if db.engine.dialect.name == 'postgresql':
            @event.listens_for(db.engine, 'connect')
            def _read_only(dbapi_connection, _record):
                with dbapi_connection.cursor() as cursor:
                    cursor.execute('SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY')
                dbapi_connection.commit()  # a rolled-back SET would be undone
    return app


def render_text(report: dict) -> str:
    lines = []
    summary = report['summary']
    state = 'FIPS mode is active' if report['fips_active'] else 'FIPS mode is not active'
    lines.append(f"FIPS readiness ({state}): {summary['blocker']} blocker(s), "
                 f"{summary['warning']} warning(s), {summary['info']} info")
    for finding in report['findings']:
        lines.append('')
        lines.append(f"[{finding['severity'].upper()}] {finding['id']} ({finding['count']})")
        lines.append(f"  {finding['title']}")
        for example in finding['examples']:
            lines.append(f"  - {example}")
        if finding['count'] > len(finding['examples']):
            lines.append(f"  - ... and {finding['count'] - len(finding['examples'])} more")
        lines.append(f"  Remedy: {finding['remedy']}")
    for error in report['errors']:
        lines.append('')
        lines.append(f"[ERROR] {error['id']}: the check could not run ({error['error']})")
    if not report['findings'] and not report['errors']:
        lines.append('Nothing found that FIPS mode would refuse.')
    return '\n'.join(lines)


def exit_code(report: dict) -> int:
    if report['errors']:
        return 2
    return 1 if report['summary']['blocker'] else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--json', action='store_true', help='print the report as JSON')
    args = parser.parse_args(argv)
    app = read_only_app()
    with app.app_context():
        try:
            report = fips_preflight.run()
        finally:
            db.session.rollback()
    if fips_mode.requested() and not fips_mode.provider_active():
        # A docker exec does not inherit the entrypoint's OPENSSL_CONF: the report would be wrong.
        report['errors'].insert(0, {'id': 'fips.provider', 'error': (
            'UCM_FIPS is set but this process runs without the FIPS provider: '
            'set OPENSSL_CONF=/run/ucm/openssl-fips.cnf')})
        report['ready'] = False
    print(json.dumps(report, indent=2) if args.json else render_text(report))
    return exit_code(report)


if __name__ == '__main__':
    sys.exit(main())
