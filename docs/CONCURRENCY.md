# Concurrency model

Several web workers, and with HA several nodes, share one database. The scheduler
runs its tasks on one leader only. This page lists the invariants that hold when two
workers act at once, and what enforces each one. Real concurrency is tested on
PostgreSQL (`UCM_TEST_PG_URL`); SQLite serializes writers on its own.

| Invariant | Protection | Where |
|---|---|---|
| No two certificate rows carry the same serial string under one CA (RFC 5280 §4.1.2.2) | Random 159-bit serial; unique partial index `uix_certificates_ca_serial` on `certificates (caref, serial_number)`, which compares the stored string (always decimal: every path stores the decimal form); `create_certificate`, `sign_csr` and `sign_csr_from_crypto` sign once more on a collision, undoing only their own savepoint | `models/certificate.py`, migration 300 (step 142), `utils/ca_serial_counter.py` |
| `certificate_authorities.serial` counts every certificate a CA signs: `create_certificate`, `sign_csr`, `sign_csr_from_crypto`, the certificate creation route (each member of a post-quantum pair), an approved request's issuance, SCEP, in-place renewal, intermediate CA creation and cross-signing (issuer's count), the EST key generator, TSA signer and renewed OCSP responder certificates, and `increment_serial` | One `UPDATE … SET serial = serial + 1` (with `RETURNING` where the dialect has it) in the transaction that stores the certificate, never a Python read-modify-write, taken after every existing certificate row the transaction locks or updates (both members of a renewed pair, a superseded or archived OCSP responder or EST key generator row, the rows a renewal unlinks, the certificate A an RFC 9763 B links back to), and in id order when a pair counts under two CAs, so no two transactions lock these rows in opposite orders; rows the transaction inserts may be written after the count. A pre-certificate (RFC 6962) counts with its certificate; self-signed certificates (root CA, HTTPS server, ACME TLS-ALPN challenge) and SSH certificates (own counter) do not count | `utils/ca_serial_counter.py` `next_ca_serial` |
| One CRL number per issuer, never reused (RFC 5280 §5.2.3) | Counter row `SELECT … FOR UPDATE`; unique index `uix_crl_ca_number` | `services/crl/numbering.py`, `models/crl.py` |
| Audit chain never forks | `pg_advisory_xact_lock` around the append | `services/audit/chain.py` |
| A certificate is renewed in place once | Row re-read `FOR UPDATE`, the expected serial and archived state checked (409): a row archived meanwhile is never revived; serial swapped only if unchanged | `services/cert/renewal.py` `_reread`, `_take_serial` |
| A renewed row is superseded once | Compare-and-set on the superseded row and the serial of the certificate the client presented: a row renewed in place meanwhile is refused (`AlreadySuperseded`), as are the OCSP responder task's and the EST key generator's archive of it | `services/ca/ca_signing.py` `_claim_superseded`, `services/ocsp_responder_renewal.py` `_archive`, `services/est_key_generator.py` `_archive` |
| A CSR is signed once | `UPDATE … WHERE crt IS NULL` | `services/cert/mixins/csr.py` |
| Webhook and deploy deliveries run once | Conditional `UPDATE` taking a lease | `services/webhook_service.py`, `services/deploy/service.py` |
| ACME client order renewed or finalized once | Lease on the order row | `services/acme/order_lease.py` |
| ACME server order finalized once | `ready → processing` conditional `UPDATE` | `services/acme/mixins/order.py` |
| ACME proxy order row merges every writer | Row `FOR UPDATE` on PostgreSQL; a striped process lock on SQLite | `services/acme/acme_proxy_service.py` `_update_order_row` |
| ACME proxy challenge resolves on any node | Challenge → (order, identifier, authorization) stored in `acme_proxy_challenge_links` | `services/acme/acme_proxy_service.py` |
| Approval requests decided once | `FOR UPDATE` / `SKIP LOCKED` | `services/approval_gate.py` |
| SSH CA serials unique | Counter row `FOR UPDATE` | `services/ssh_ca_service.py` |
| A Microsoft CA certificate never replaces one from another source on a CSR row | Row rewritten only while it holds no certificate or one a Microsoft CA issued (rowcount 1); otherwise the request is closed as `superseded` and the certificate enters through the inventory as a separate row | `api/v2/msca.py` `_import_signed_cert`, `services/msca/ca_control.py` `complete_request` |
| A due discovery profile starts one scan | `next_scan_at` moved only while still due and the schedule enabled (rowcount 1) | `services/discovery_scheduler_task.py` |
| A delegated OCSP responder is renewed once | Binding rebound only if it still names the old certificate | `services/ocsp_responder_renewal.py` |
| An HA backup archive is listed only once whole | Row and chunks in one transaction, read back before the commit | `services/backup/shared_store.py` `store_archive` |
| HA backup retention and deletions run one at a time across nodes | Transaction advisory lock keyed by schema | `services/backup/shared_store.py` `_take_lock` |
| One active background job per slot (`backup`, `audit_verify`; a `restore` holds them all), on the whole installation, HA included | Partial unique index `uq_background_jobs_active_slot` on the slot of pending and running jobs; the cross-slot check runs after the insert, under `pg_advisory_xact_lock` on PostgreSQL and the SQLite write lock; every state change is a conditional `UPDATE` on the previous state | `services/jobs/store.py` `create_job`, `claim_job`, `conclude_job` |
| A restore is cancelled or commits, never both; each step after its commit runs once | The `committed` phase is written in the restore's own transaction, only while no cancellation is flagged; the cancellation flag is written only before that phase; each later step moves the phase from the previous one (rowcount 1), the session epoch in the same transaction as its step | `services/jobs/restore.py` `_Run.mark`, `_Ledger.advance`, `claim_sessions`; `services/jobs/store.py` `cancel_or_flag` |

Scheduled backups reserve their run in the database (`services/backup/schedule.py`
`_claim_run`: a compare-and-set of `backup.last_run`), so of two nodes finding a run due,
one writes. Scheduled tasks without a claim of their own rely on the leader election: the
Microsoft CA CRL and inventory syncs. The automatic renewal task also
relies on the per-certificate `FOR UPDATE` above. The ACME order recovery is a
conditional `UPDATE`.

When the upgrade from 2.254 (migration 300) finds certificate rows sharing a serial under one CA, it
lists them, keeps them, and leaves the index pending under the `SystemConfig` key
`serial_unique_index_pending`, which every start logs and `/health` reports as
`serial_unique_index_pending` (the number of pairs). While it is pending, a backend
migration refuses the source, and a restore of a backup taken from it is refused on an
installation that has the index, naming the rows; the pending installation itself still
restores its own backups. The flag never travels in a backup.
While the key is set, every start runs the upgrade step 144 again, and only it, which clears
the key in the same transaction as the conversion: once the rows are resolved, a restart creates the
index and stores every serial in decimal, and a start cut short leaves the key for the next.
`migration_runner.py status` and `dry-run` say so rather than report the database up to date.
On PostgreSQL, creating the index locks `certificates` against writes until its transaction commits: during the upgrade from 2.254, from step 142 to the end of migration 300, a time that grows with the number of certificates (steps 144 and 157 read every one); during a replay, only when it creates the index, from that creation to the commit that follows. A replay that finds the index takes no such lock.
