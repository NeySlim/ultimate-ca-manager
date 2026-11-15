"""Re-encrypt the integration secrets under UCM_DB_ENCRYPTION_KEY.

Run from backend/, on the instance whose secrets they are, with the new key in the
environment: ``UCM_DB_ENCRYPTION_KEY=<key> python -m scripts.rewrap_db_key [--dry-run]``.
The secrets are read with this host's machine-derived key (the key used while
UCM_DB_ENCRYPTION_KEY was unset), or with the key in the variable named by --from-env.
Safe to run again: a secret already under the new key is skipped. A secret no key opens
stops the run before anything is written. Exit code 0 done, 1 refused, 2 not run.
"""
import argparse
import os
import sys

from cryptography.fernet import Fernet


def _app():
    from flask import Flask
    from config.settings import get_config
    from models import db
    app = Flask('ucm-rewrap-db-key')
    app.config.from_object(get_config())
    db.init_app(app)
    return app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--from-env', metavar='VAR',
                        help='read the secrets with the key in this variable instead of the machine-derived key')
    parser.add_argument('--dry-run', action='store_true', help='count what would be re-encrypted, write nothing')
    args = parser.parse_args(argv)

    target = os.environ.get('UCM_DB_ENCRYPTION_KEY', '')
    try:
        Fernet(target.encode())
    except Exception:
        print('UCM_DB_ENCRYPTION_KEY must hold the new key (a Fernet key) in this environment', file=sys.stderr)
        return 2
    if args.from_env:
        source = os.environ.get(args.from_env, '').encode()
        what = args.from_env
    else:
        from utils.encryption import machine_derived_key
        source, what = machine_derived_key(create=False), 'the machine-derived key'
    try:
        Fernet(source)
    except Exception:
        print(f'No usable source key ({what})', file=sys.stderr)
        return 2

    from models import db
    from services.db_key_rewrap import RewrapRefused, rewrap
    with _app().app_context():
        try:
            result = rewrap([source], target.encode(), dry_run=args.dry_run)
        except RewrapRefused as e:
            print(f'Refused: {len(e.labels)} secret(s) open under neither {what} nor '
                  f'UCM_DB_ENCRYPTION_KEY, nothing was written:', file=sys.stderr)
            for label in e.labels:
                print(f'  - {label}', file=sys.stderr)
            print('Enter them again in UCM, or clear them, then run this again.', file=sys.stderr)
            return 1
        finally:
            db.session.remove()
    if args.dry_run:
        print(f"{result['to_rewrite']} secret(s) to re-encrypt, {result['already']} already under the key")
    else:
        print(f"{result['rewritten']} secret(s) re-encrypted, {result['already']} already under the key")
    return 0


if __name__ == '__main__':
    sys.exit(main())
