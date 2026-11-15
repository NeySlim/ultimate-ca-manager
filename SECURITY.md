# Security Policy

## Supported versions

The current release line receives bug fixes, security fixes and new features: a fix ships in the next build of that line (for example 3.1 after 3.0), so upgrade to its latest stable release to stay covered.

The last release of the previous line, 2.254, receives security fixes only, published as maintenance releases 2.254.1, 2.254.2 and so on; it gets no other bug fix and no new feature. Earlier 2.x releases are not supported: upgrade to the latest 2.254.N.

Release candidates and the `dev` branch are for testing and are not supported.

## Reporting a vulnerability

Please do not open a public issue, discussion or pull request for a vulnerability.

Report it privately through [GitHub Security Advisories](https://github.com/NeySlim/ultimate-ca-manager/security/advisories/new). Include:

- the affected version and deployment (DEB, RPM, Docker, Helm);
- the steps to reproduce, or a proof of concept;
- the impact as you see it.

## What to expect

- A first answer within 7 days, saying whether the report is confirmed.
- The fix ships in the next stable release of the current line and, when 2.254 is affected, in the next 2.254.N.
- The advisory is published once that release is out, crediting you unless you prefer otherwise.
- Please keep the details private until the advisory is published, or for 90 days after your report, whichever comes first.

## Scope

UCM is meant to run on premises, and reaching LAN addresses (webhooks, SSO, ACME validation) is by design. Blocking cloud metadata and loopback is in scope; reaching an RFC 1918 address an administrator configured is not.

Security features and hardening notes are documented in [docs/SECURITY.md](docs/SECURITY.md).
