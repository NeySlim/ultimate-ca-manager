# ACME client bench against Pebble

A reproducible bench for UCM's **ACME client** (UCM obtaining certificates from an external CA)
against [Pebble](https://github.com/letsencrypt/pebble), Let's Encrypt's ACME test server, with
real DNS-01 validation through `pebble-challtestsrv`. Everything runs in throwaway containers on one
Docker host and is removed afterwards.

Files:

| File | Role |
|---|---|
| `acme-pebble-bench.sh` | build the UCM image, start and remove the containers |
| `acme_pebble_bench.py` | scenarios, run on the Docker host (Python 3 stdlib, `docker` and `openssl` CLIs) |
| `acme_pebble_hook.py` | DNS-01 hook for UCM's *Custom Command* DNS provider: publishes the TXT in challtestsrv |

## Topology

```
 bench network (BENCH_SUBNET, default 10.231.77.0/24)
 ┌───────────────────────┐   DNS-01 lookups    ┌─────────────────────────┐
 │ pebble-challtestsrv .2│◄────────────────────│ Pebble .3  (alias pebble)│
 │  DNS :8053, mgmt :8055│                     │  ACME :14000, mgmt :15000│
 └──────────▲────────────┘                     └────────────▲────────────┘
            │ set-txt / clear-txt (hook)                    │ ACME over HTTPS
            │ TXT self-check (custom resolver)              │ (REQUESTS_CA_BUNDLE = Pebble minica)
 ┌──────────┴───────────────────────────────────────────────┴────────────┐
 │ UCM .4  (image built from the tree under test, API on :8443)          │
 └───────────────────────────────────────────────────────────────────────┘
```

- Pebble serves its directory with a certificate from its own test CA (`pebble.minica.pem`, SAN
  `pebble`). UCM's ACME client uses `requests` with verification on, so the UCM container gets
  `REQUESTS_CA_BUNDLE` pointing at that CA. No UCM setting is changed for TLS.
- DNS-01 is real: UCM's Custom Command provider runs `acme_pebble_hook.py`, which publishes the TXT
  in challtestsrv; Pebble queries challtestsrv (`-dnsserver`); UCM's own TXT self-check uses the
  *custom* resolver mode pointed at challtestsrv.
- Pebble sends `Retry-After: PEBBLE_RETRY_AFTER_ORDER` (default 40 s) on a processing order. The
  finalize-crash scenario needs that window; the polling scenario measures it.
- `PEBBLE_AUTHZREUSE=0` so every order really validates, `PEBBLE_WFE_NONCEREJECT=0` for determinism,
  `PEBBLE_VA_NOSLEEP=1`.
- Limits: Pebble 256 MiB / 1 CPU, challtestsrv 128 MiB / 0.5 CPU, UCM 1 GiB / 2 CPUs.

## Procedure

On the machine holding the source tree, with `DOCKER_SSH` the Docker host and `REF` the commit
under test:

```bash
REF=dev
BENCH=/tmp/ucm-pebble-bench
ssh "$DOCKER_SSH" "rm -rf $BENCH && mkdir -p $BENCH/ctx $BENCH/bench"
git archive "$REF" | ssh "$DOCKER_SSH" "tar -x -C $BENCH/ctx"
scp docs/testing/acme-pebble-bench.sh docs/testing/acme_pebble_bench.py \
    docs/testing/acme_pebble_hook.py "$DOCKER_SSH:$BENCH/bench/"
```

On the Docker host:

```bash
cd /tmp/ucm-pebble-bench
export UCM_IMAGE=ucm-pebble-ucm:bench BENCH_WORKDIR=/tmp/ucm-pebble-bench/work
free -h                                       # the stack needs about 1.5 GiB
bash bench/acme-pebble-bench.sh build ctx     # about 2 min from a cold cache
bash bench/acme-pebble-bench.sh up            # about 15 s
python3 bench/acme_pebble_bench.py --report report.json   # about 20 min, exit 0 when all pass
bash bench/acme-pebble-bench.sh down
docker rmi "$UCM_IMAGE" && rm -rf /tmp/ucm-pebble-bench
```

`build` adds a placeholder `frontend/dist/index.html` when the tree has no built frontend: the
bench only uses the API. To replay one scenario, `down` then `up` (Pebble keeps its state in
memory, the scenarios expect a fresh UCM) and pass `--only s1,s5`.

Variables: `BENCH_PREFIX` (container prefix, default `ucm-pebble`), `BENCH_SUBNET`,
`BENCH_WORKDIR`, `UCM_IMAGE`, `PEBBLE_IMAGE` and `CHALLTEST_IMAGE` (pinned by digest),
`PEBBLE_RETRY_AFTER_ORDER`, `PEBBLE_AUTHZREUSE`, `PEBBLE_WFE_NONCEREJECT`, `BENCH_DOMAIN`
(default `bench.example.com`), `UCM_USER`, `UCM_PASSWORD`, `UCM_BENCH_PASSWORD` (the first login
replaces the initial password with this one).

## Setup done by the driver

- Initial password changed, then ACME client settings: contact e-mail, DNS self-check timeout 10 s
  and delay 0, resolver mode *custom* on challtestsrv.
- DNS providers (Custom Command): `challtest` (correct TXT), `challtest-wrong` (wrong TXT),
  `challtest-flip` (correct, switched to wrong by scenario 4).
- Two CA accounts on Pebble, registered through the API: `pebble-main` (order poll timeout 120 s,
  interval 3 s) and `pebble-slow` (timeout 30 s, below Pebble's Retry-After).

## Scenarios

| Key | Scenario | Pass condition |
|---|---|---|
| s1 | Issuance through `POST /acme/client/request` (auto-poll) | order `issued`, one certificate, serial known to Pebble, stored key matches |
| s3 | `Retry-After` on finalize | next order poll after Retry-After (main), at the poll timeout (slow), both issued |
| s7 | First name longer than 64 characters | order issued; the CSR UCM builds has an empty subject and a critical SAN |
| s2 | Scheduled renewal (`acme_auto_renewal`) of a due order | Pebble ARI override makes s1 due; the same certificate row gets a new serial Pebble knows and the stored key matches, one order, nothing on a second run |
| s6 | ARI (reported with s2) | Pebble answers 200 to UCM's CertID; the renewal's `replaces` is accepted |
| s8 | Deployment binding on a renewed certificate | a `DeployBinding` on the certificate: after the renewal the row keeps its id, the binding still names it and `deploy_deliveries` holds a `certificate.renewed` delivery for it |
| s4a | Invalid order on issuance | wrong TXT: order `invalid` with Pebble's detail, no certificate, no other order |
| s4b | Invalid order on renewal | a due order whose DNS-01 now fails, renewed twice: failure counted, no order left behind |
| s5 | Crash between `finalize` and download | UCM killed during the Retry-After sleep after the finalize POST; on restart the order holds its pending key and a manual finalize answers 409 (the dead process's lease) |
| s5b | Same crash during a scheduled renewal | on restart the renewal's order holds the key, the scheduler's first pass skips the leased order, the certificate row is unchanged |
| s5r | Resume of s5 | once the lease runs out, a status check imports the certificate Pebble issued before the kill, with its key; Pebble issued nothing else |
| s5br | Resume of s5b | once the lease runs out, the next renewal imports that certificate into the same row without a new order (no `alreadyReplaced`) |

Scenarios run in the order `s1 s3 s7 s2 s8 s4 s5 s5b s5r s5br`: `s3` and `s2` reuse the order made by `s1`,
`s4` deletes its due order so that `s5b` finds a single due order. A lease left by a killed process
lasts 10 minutes, so `s5r` and `s5br` wait for it: the whole run takes about 20 minutes.

Pebble's management API is used for evidence only: `/cert-status-by-serial/<hex>` and
`/set-renewal-info/` (an ARI window in the past, so a renewal is due without waiting).
