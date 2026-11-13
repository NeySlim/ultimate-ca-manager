# Security Policy

## Supported versions

Only the latest stable release receives security fixes. 2.254 is the last version of the 2.x line, which now receives security fixes only, numbered 2.254.1, 2.254.2 and so on: upgrade to the latest of them to stay covered. Release candidates and the `dev` branch are for testing and are not supported.

## Reporting a vulnerability

Please do not open a public issue, discussion or pull request for a vulnerability.

Report it privately through [GitHub Security Advisories](https://github.com/NeySlim/ultimate-ca-manager/security/advisories/new). Include:

- the affected version and deployment (DEB, RPM, Docker, Helm);
- the steps to reproduce, or a proof of concept;
- the impact as you see it.

## What to expect

- A first answer within 7 days, saying whether the report is confirmed.
- The fix lands on `dev` and ships in the next stable release.
- The advisory is published once that release is out, crediting you unless you prefer otherwise.
- Please keep the details private until the advisory is published, or for 90 days after your report, whichever comes first.

## Scope

UCM is meant to run on premises, and reaching LAN addresses (webhooks, SSO, ACME validation) is by design. Blocking cloud metadata and loopback is in scope; reaching an RFC 1918 address an administrator configured is not.

Security features and hardening notes are documented in [docs/SECURITY.md](docs/SECURITY.md).
