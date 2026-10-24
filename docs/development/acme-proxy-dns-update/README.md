# ACME proxy DNS UPDATE listener: design notes

This directory has the design notes of the DNS UPDATE listener (RFC 2136 with TSIG, RFC 8945) for the ACME proxy. The issue is NeySlim/ultimate-ca-manager#416. You do not need these files to build or run UCM.

| File | Content |
|---|---|
| [`plan.md`](plan.md) | Design plan: RFC invariants with positive and negative tests, decisions, security reviews, and the results of the code reviews (section 12). |
| [`agent-workflow.md`](agent-workflow.md) | How the work was split between AI agents and the main session: rules, roles, and the structure of the prompts. |
| [`prompts-pr2.md`](prompts-pr2.md) | The full prompts of the implementation parts, verbatim. |
| [`maintainer-requirements.md`](maintainer-requirements.md) | The requirements of the maintainer for the listener. |
| [`maintainer-comment-416.md`](maintainer-comment-416.md) | The comment drafted for issue #416. |
| [`spike/tsig_spike.py`](spike/tsig_spike.py) | The prototype that checked the TSIG behavior of dnspython. |

The code and its user documentation are in the listener pull request (`docs/ADMIN_GUIDE.md`, `docs/integrations/acme-proxy-dns-update.md`, `docs/testing/ACME-PROXY-DNS-UPDATE.md`).
