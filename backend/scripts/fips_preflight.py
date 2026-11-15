"""List what FIPS mode would refuse on this instance, without changing anything.

Run from backend/: ``python -m scripts.fips_preflight [--json]``. Exit code 0
when nothing blocks, 1 with blockers, 2 when a check could not run or UCM_FIPS
is set without the FIPS provider.
"""
import argparse
import json
import os
import pwd
import sys
from pathlib import Path

import fips_mode
from migration_runner import encoding_refusal, pending_migrations
from models import db
from services import fips_preflight, preflight_core


def read_only_app(config=None):
    """The database the service uses, opened read-only; no migration, no scheduler."""
    if fips_mode.requested():
        # As enforce_at_startup does; an explicit value stays, for the report to name it
        os.environ.setdefault('PGGSSENCMODE', 'disable')
    return preflight_core.read_only_app('ucm-fips-preflight', config)


def _command() -> str:
    """This run again, as the account that runs it now, from the backend directory."""
    backend = Path(__file__).resolve().parents[1]
    return (f'cd {backend} && sudo -u {pwd.getpwuid(os.geteuid()).pw_name} '
            f'{sys.executable} -m scripts.fips_preflight')


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
        if error['id'] == 'fips.provider':
            lines.append(f"[ERROR] {error['id']}: {error['error']}")
        else:
            lines.append(f"[ERROR] {error['id']}: the check could not run ({error['error']})")
    if report.get('deferred'):
        lines.append('')
        lines.append(f"[INFO] {report['deferred']['count']} checks need the upgraded database: "
                     f"run {report['deferred']['command']} after the first start")
    if not report['findings'] and not report['errors'] and not report.get('deferred'):
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
        # On a bare connection: the first SQLAlchemy one fails on such a database, unnamed
        refusal = encoding_refusal(db.engine)
        if refusal:
            print(f'[ERROR] database: {refusal}')
            return 2
        try:
            # Before the upgrade the next start applies, the model and the tables differ: the
            # checks that read the database wait for it, the others run
            deferred = [d for d in fips_preflight.DETECTORS if d.reads_database] \
                if pending_migrations(db.engine) else []
            report = fips_preflight.run([d for d in fips_preflight.DETECTORS if d not in deferred])
        finally:
            db.session.rollback()
    if deferred:
        report['deferred'] = {'count': len(deferred), 'command': _command()}
    if fips_mode.requested() and not fips_mode.provider_active():
        # A docker exec does not inherit the entrypoint's OPENSSL_CONF: the header would say FIPS is off.
        remedy = ('set OPENSSL_CONF=/run/ucm/openssl-fips.cnf' if os.getenv('UCM_DOCKER') == '1' else
                  'put the host in FIPS mode and install the package with UCM_FIPS_BUILD=1 in /etc/ucm/ucm.env')
        report['errors'].insert(0, {'id': 'fips.provider', 'error': (
            f'UCM_FIPS is set but this process runs without the FIPS provider: {remedy}')})
        report['ready'] = False
    print(json.dumps(report, indent=2) if args.json else render_text(report))
    return exit_code(report)


if __name__ == '__main__':
    sys.exit(main())
