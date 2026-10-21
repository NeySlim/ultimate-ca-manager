"""List what a compliance profile would refuse on this instance, without changing anything.

Run from backend/: ``python -m scripts.compliance_preflight --profile bsi [--ca ID] [--json]``.
Exit code 0 when nothing blocks, 1 with blockers, 2 when a check could not run
or the profile or the CA is unknown.
"""
import argparse
import json
import sys

import compliance_profiles
from models import db
from scripts.fips_preflight import exit_code
from services import compliance_preflight, preflight_core


def read_only_app(config=None):
    """The database the service uses, opened read-only; no migration, no scheduler."""
    return preflight_core.read_only_app('ucm-compliance-preflight', config)


def render_text(report: dict) -> str:
    summary, profile = report['summary'], report['profile']
    scope = f", CA #{report['ca_id']}" if report['ca_id'] is not None else ''
    lines = [f"Profile {profile['name']} ({profile['reference']}{scope}): {summary['blocker']} blocker(s), "
             f"{summary['warning']} warning(s), {summary['info']} info"]
    for finding in report['findings']:
        lines += ['', f"[{finding['severity'].upper()}] {finding['id']} ({finding['count']})",
                  f"  {finding['title']}"]
        lines += [f"  - {example}" for example in finding['examples']]
        if finding['count'] > len(finding['examples']):
            lines.append(f"  - ... and {finding['count'] - len(finding['examples'])} more")
        lines.append(f"  Remedy: {finding['remedy']}")
    for error in report['errors']:
        lines += ['', f"[ERROR] {error['id']}: the check could not run ({error['error']})"]
    if not report['findings'] and not report['errors']:
        lines.append(f"Nothing found that the {profile['name']} profile would refuse or advise against.")
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--profile', required=True, choices=compliance_profiles.PROFILE_NAMES)
    parser.add_argument('--ca', type=int, help='check this CA alone')
    parser.add_argument('--json', action='store_true', help='print the report as JSON')
    args = parser.parse_args(argv)
    app = read_only_app()
    with app.app_context():
        try:
            report = compliance_preflight.run(args.profile, args.ca)
        except LookupError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        finally:
            db.session.rollback()
    print(json.dumps(report, indent=2) if args.json else render_text(report))
    return exit_code(report)


if __name__ == '__main__':
    sys.exit(main())
