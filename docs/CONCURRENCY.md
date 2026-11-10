# Concurrency model

Several web workers, and with HA several nodes, share one database. The scheduler
runs its tasks on one leader only. This page lists the invariants that hold when two
workers act at once, and what enforces each one. Real concurrency is tested on
PostgreSQL (`UCM_TEST_PG_URL`); SQLite serializes writers on its own.

| Invariant | Protection | Where |
|---|---|---|
| No two certificate rows carry the same serial string under one CA (RFC 5280 §4.1.2.2) | Random 159-bit serial; unique partial index `uix_certificates_ca_serial` on `certificates (caref, serial_number)`, which compares the stored string (not normalised: decimal on some paths, hexadecimal on others); `create_certificate`, `sign_csr` and `sign_csr_from_crypto` sign once more on a collision, undoing only their own savepoint | `models/certificate.py`, migration 142, `utils/ca_serial_counter.py` |
| `certificate_authorities.serial` counts the issuances of the five shared paths: `create_certificate`, `sign_csr`, `sign_csr_from_crypto`, intermediate CA creation (parent's count) and `increment_serial` | One `UPDATE … SET serial = serial + 1` (with `RETURNING` where the dialect has it), never a Python read-modify-write. Paths that sign on their own do not count: the certificate creation route, an approved request's issuance, SCEP, in-place renewal, the post-quantum related certificate, the EST server-side key delegate, the OCSP responder and TSA signer certificates, and the HTTPS server certificate | `utils/ca_serial_counter.py` `next_ca_serial` |
| One CRL number per issuer, never reused (RFC 5280 §5.2.3) | Counter row `SELECT … FOR UPDATE`; unique index `uix_crl_ca_number` | `services/crl/numbering.py`, migration 134 |
| Audit chain never forks | `pg_advisory_xact_lock` around the append | `services/audit/chain.py` |
| A certificate is renewed in place once | Row re-read `FOR UPDATE` and the expected serial checked (409); serial swapped only if unchanged | `services/cert/renewal.py` `_reread`, `_take_serial` |
| A renewed row is superseded once | Compare-and-set on the superseded row | `services/ca/ca_signing.py` `_claim_superseded` |
| A CSR is signed once | `UPDATE … WHERE crt IS NULL` | `services/cert/mixins/csr.py` |
| Webhook and deploy deliveries run once | Conditional `UPDATE` taking a lease | `services/webhook_service.py`, `services/deploy/service.py` |
| ACME client order renewed or finalized once | Lease on the order row | `services/acme/order_lease.py` |
| ACME server order finalized once | `ready → processing` conditional `UPDATE` | `services/acme/mixins/order.py` |
| ACME proxy order row merges every writer | Row `FOR UPDATE` on PostgreSQL; a striped process lock on SQLite | `services/acme/acme_proxy_service.py` `_update_order_row` |
| ACME proxy challenge resolves on any node | Challenge → (order, identifier, authorization) stored in `acme_proxy_challenge_links` | `services/acme/acme_proxy_service.py` |
| Approval requests decided once | `FOR UPDATE` / `SKIP LOCKED` | `services/approval_gate.py` |
| SSH CA serials unique | Counter row `FOR UPDATE` | `services/ssh_ca_service.py` |
| A due discovery profile starts one scan | `next_scan_at` moved only while still due and the schedule enabled (rowcount 1) | `services/discovery_scheduler_task.py` |
| A delegated OCSP responder is renewed once | Binding rebound only if it still names the old certificate | `services/ocsp_responder_renewal.py` |

Scheduled tasks without a claim of their own rely on the leader election: the backup
`last_run`, the Microsoft CA CRL and inventory syncs. The automatic renewal task also
relies on the per-certificate `FOR UPDATE` above. The ACME order recovery is a
conditional `UPDATE`.

When the migration 142 finds certificate rows sharing a serial string under one CA, it
lists them, keeps them, and leaves the index pending under the `SystemConfig` key
`serial_unique_index_pending`, which every start logs and `/health` reports as
`serial_unique_index_pending` (the number of pairs). While it is pending, a backend
migration refuses the source, and a restore of a backup taken from it is refused on an
installation that has the index, naming the rows; the pending installation itself still
restores its own backups. The flag never travels in a backup.
Once they are resolved, deleting the `142_serial_per_ca_and_proxy_links` row from
`_migrations` makes the next start run the migration again and create the index.
