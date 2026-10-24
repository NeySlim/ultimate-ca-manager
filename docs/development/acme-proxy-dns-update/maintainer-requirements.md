# Maintainer requirements, NeySlim/ultimate-ca-manager#416 (comment by NeySlim, 2026-10-24)

Source: extracted from the public issue page. Short verbatim quotes are marked with quotes; the rest is a close paraphrase.

- Option A accepted. Two PRs: documentation first (option D), then the listener. Option B (acme-dns compatible API) may come later as a complement, not instead of A.
- Separate UDP/TCP listener is acceptable. TSIG keys belong to a proxy account (slug), optionally linked to an EAB credential (then the key only accepts values for orders of the ACME account bound to that credential). No single global key.
- "The listener should answer unsigned SOA queries for names covered by a pending proxy order" "...and refuse every other query."
- Persist the token (or client TXT value) when the client fetches the authorization, not when the background job runs. Match on sha256(token "." client_thumbprint), including sibling orders sharing one upstream authorization (#307).
- Deletes: class NONE (one record) and class ANY (whole RRset). "Always answer NOERROR, even when the order is gone (RFC 2136 §3.4.2.3)."
- "A non-empty prerequisite section gets REFUSED."
- TSIG errors per RFC 8945 §5.2: BADKEY and BADSIG unsigned with empty MAC; BADTIME signed with server time. Use dnspython for parsing and TSIG; do not hand-roll HMAC.
- hmac-sha256 default, "nothing weaker than SHA-256", no hmac-md5; FIPS mode must refuse what the existing RFC 2136 DNS provider refuses.
- Audit log: accepted updates and signed refusals (BADKEY, BADSIG, value mismatch). Unsigned or malformed packets: application log only (avoid audit flooding).
- Exposure: "No response larger than the request", no recursion, documentation note that the listener is for the internal network.
- "The DEB and RPM services and the Docker image run as an unprivileged user without CAP_NET_BIND_SERVICE": unprivileged default port; docs explain mapping to 53. Startup follows the HTTP protocol server pattern (env var first, then setting); 0 disables; off by default.
- Packaging: Docker EXPOSE, entrypoint port check, Helm Service port UDP+TCP with unprivileged target port. DEB/RPM unit files unchanged.
- TSIG keys encrypted at rest, shown once (like EAB). New table with migration for SQLite and PostgreSQL. UI with contextual help in the same PR; strings in all 9 locales.
- Minimum tests: unknown key, bad signature, bad time, unsigned update, name without pending order, value mismatch, delete of a record that no longer exists, SOA discovery.
- Some third-party client behaviour in the issue came from reading code, not testing; confirm per client (SOA discovery for acme.sh dns_nsupdate, Posh-ACME, certbot-dns-rfc2136).
