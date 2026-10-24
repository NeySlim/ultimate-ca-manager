Thanks for the detailed answer. The documentation PR (option D) is ready on our side. Before we finish the listener, two of your requirements collide with how real clients behave, so we would like your OK on how we handle them. Both come from reading the client source code (we cite the files below) and will be confirmed in our end-to-end tests.

**1. Signed SOA queries.** You wrote that the listener should answer unsigned SOA queries and refuse every other query. BIND `nsupdate` (used by acme.sh `dns_nsupdate` when `NSUPDATE_ZONE` is not set, and by Posh-ACME's RFC2136 plugin) **signs** its SOA discovery query with the TSIG key whenever a `server` is given (`bin/nsupdate/nsupdate.c`, `sendrequest()`: `default_servers ? NULL : tsigkey`). It treats an unsigned reply to a signed query as fatal. RFC 8945 §5.3 also requires a signed response to a signed request. Our proposal: answer SOA discovery both unsigned and signed. A signed query is verified like an UPDATE (RFC 8945 §5.2 order) and gets a signed answer. The answer is the same as for an unsigned query, so this adds no new information.

**2. "No response larger than the request".** An SOA answer is always larger than the query. lego and cert-manager retry over TCP when they see TC=1, and certbot queries over TCP first. But `nsupdate` queries over UDP and ignores TC (no truncation handling in `nsupdate.c` or `lib/dns/request.c`). Our proposal:
- UDP requests **without a valid TSIG** (the only ones a spoofed source address can produce): the response is never larger than the request. A larger answer is replaced by a minimal TC=1 response, as RFC 1035 §4.2.1 and RFC 6891 §7 describe.
- UDP requests **with a TSIG that verified** (MAC checked, time window capped at 300 s, replays answered from a cache without side effects): the normal RFC limit, max(512, EDNS payload size). For a signed SOA query the response is about 1.25× the request.
- TCP: no limit (no amplification over TCP).

Two smaller points, in case you want to object:
- **Unsigned UPDATE** gets REFUSED right after parsing, before the zone check. Otherwise NOTAUTH vs REFUSED would let anyone without a key find out which domains are in ACME → Domains. RFC 3007 §2 requires TSIG in secure updates, and RFC 2136 §3.3.1 leaves the permission check to the implementation.
- **SOA content** is fixed: owner = the ACME Domains entry that covers the name, MNAME = that domain, RNAME = `hostmaster.<domain>`, SERIAL = 1, TTL 0. No UCM hostname, no timestamp.

If either point 1 or 2 is not acceptable, the alternative for nsupdate users is to document `NSUPDATE_ZONE` (acme.sh) and `-DDNSZone` (Posh-ACME), which skip SOA discovery, and keep your rules as written.
