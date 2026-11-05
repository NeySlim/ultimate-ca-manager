#!/usr/bin/env python3
"""DNS-01 hook for UCM's Custom Command provider: publishes the TXT in pebble-challtestsrv.

UCM passes ACTION, RECORD_NAME and RECORD_VALUE in the environment. CHALLTEST_URL is
the challtestsrv management URL. With --wrong, a value Pebble will refuse is published.
"""
import json
import os
import sys
import urllib.request


def main():
    base = os.environ.get('CHALLTEST_URL', 'http://challtestsrv:8055').rstrip('/')
    action = os.environ.get('ACTION', '')
    host = os.environ['RECORD_NAME'].rstrip('.') + '.'
    if action == 'create':
        value = os.environ['RECORD_VALUE']
        if '--wrong' in sys.argv[1:]:
            value = 'not-the-key-authorization-digest'
        path, body = '/set-txt', {'host': host, 'value': value}
    elif action == 'delete':
        path, body = '/clear-txt', {'host': host}
    else:
        print(f'unknown ACTION {action!r}', file=sys.stderr)
        return 2
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method='POST')
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f'{action} {host} -> HTTP {resp.status}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
