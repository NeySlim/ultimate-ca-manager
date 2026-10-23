# Contributing to UCM

Bug reports, feature requests and pull requests are all welcome. UCM is a young
project and most of what is in it came from someone saying it was missing.

## Before you write code

For anything beyond a small fix, [open an issue](https://github.com/NeySlim/ultimate-ca-manager/issues)
first. It costs you nothing and it avoids the case where a good pull request has to
be turned down because it conflicts with work already underway.

For a bug, what helps most: the version (`cat /opt/ucm/VERSION` or the About page),
the database backend (SQLite or PostgreSQL), how it was installed (Docker, deb,
rpm, Helm), and what you expected instead. Logs from `/var/log/ucm/ucm.log` are
usually where the answer is.

## Contributor licence agreement

Your first pull request has to carry your signature of the [CLA](CLA.md). It is one
line added to `signatures/cla-v1.1.md`, in that same pull request:

```
| your-github-username | YYYY-MM-DD | I have read and agree to the UCM CLA v1.1 |
```

A check on the pull request tells you if an author is missing, co-authors included.
A commit whose email GitHub links to no account counts as yours: tick the
attestation line the pull request template carries.
You are asked once, and the signature covers everything you have contributed, before
and after.

In return, section 8 of the agreement grants you a commercial licence of your own:
you may host, operate, support or integrate UCM for others, for a fee, without
publishing your modifications and without owing the project anything. It is personal
to you and does not cover selling UCM itself.

You keep the copyright on your work. The agreement grants a licence and, crucially,
the right to sublicense: UCM goes out under the free licence in [LICENSE](LICENSE)
and, separately, under a commercial licence for the organisations that cannot meet
its terms. That second licence is what funds the development, and it can only cover
code the project is allowed to sublicense.

If you would rather not sign, say so in the issue: a maintainer can usually
reimplement the change, and the report itself is still worth having.

## Working on the code

```bash
git checkout -b feature/my-change      # branch from dev, not from main
```

Development happens on `dev`. `main` carries stable releases and `test` carries
release candidates, so pull requests target **`dev`**.

Run the tests before you open the pull request:

```bash
pip install -r backend/requirements-dev.txt     # once: runtime and test dependencies
cd backend  && python3 -m pytest tests/ -q      # backend
cd frontend && npm test                          # frontend
```

Both suites have to be green. If you touched only one side, running that side is
enough while you iterate, but the full run is what the CI does.

A change that fixes a bug should come with a test that fails without the fix. It is
the only way to know the fix does anything, and it keeps the bug from coming back.

## What a good pull request looks like

- **One subject per pull request.** A refactor bundled with a fix is hard to review
  and impossible to revert cleanly.
- **A CHANGELOG entry** under `## [Unreleased]`, one or two sentences: what was
  broken, what is no longer broken. Not the investigation.
- **Translations.** UCM ships in 9 languages. A new user-facing string goes into all
  of `frontend/src/i18n/locales/*.json`, and `node scripts/check-i18n-sync.js` tells
  you if one is missing.
- **Migrations** work on SQLite *and* PostgreSQL. See the existing files in
  `backend/migrations/` for the pattern.
- **Commit subjects** as `type(scope): summary`, in the imperative, under 72
  characters.

## Security

Please do not open a public issue for a vulnerability. See [SECURITY.md](SECURITY.md)
for how to report one privately.

## Licence

Contributions are accepted under the terms of the [CLA](CLA.md) and distributed
under the licence in [LICENSE](LICENSE), and under the commercial licence for those
who hold one. Questions: <licensing@ucm.tools>
