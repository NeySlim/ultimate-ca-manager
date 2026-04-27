# UCM × cert-manager — reference manifests

End-to-end integration of [cert-manager](https://cert-manager.io/) with
UCM's ACME server (RFC 8555). Issue, auto-renew, and rotate TLS certs
for any Kubernetes workload using your private UCM-managed CA.

## What's in this directory

| File | Purpose |
|---|---|
| `clusterissuer-ucm.yaml` | ClusterIssuer for HTTP-01 (no EAB) |
| `clusterissuer-ucm-dns01.yaml` | ClusterIssuer for DNS-01 + EAB (wildcards, internal-only workloads) |
| `eab-secret.yaml` | Holds the HMAC for External Account Binding |
| `certificate-example.yaml` | Sample `Certificate` (single-host + wildcard) |

## Prerequisites

- Kubernetes cluster with cert-manager ≥ 1.13 installed
  (`helm install cert-manager jetstack/cert-manager -n cert-manager --set crds.enabled=true`)
- UCM reachable from your cluster pods on its HTTPS port
  (`https://<ucm-host>:8443/acme/directory`)
- For DNS-01: an authoritative DNS server accepting RFC 2136 dynamic
  updates with TSIG (BIND9, Knot, PowerDNS, etc.)

## Quick start — HTTP-01 (no EAB)

```bash
# 1. Edit clusterissuer-ucm.yaml — set `server:` to your UCM host
#    and `class:` to your Ingress class (nginx, traefik, ...).
kubectl apply -f clusterissuer-ucm.yaml
kubectl wait --for=condition=Ready clusterissuer/ucm-acme-http01 --timeout=60s

# 2. Issue a cert.
kubectl apply -f certificate-example.yaml
kubectl wait --for=condition=Ready certificate/app-tls --timeout=300s

# 3. Use it.
kubectl get secret app-tls -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -text -noout
```

cert-manager will auto-renew via the same ACME account (no EAB needed
on renewal — UCM only requires EAB for **account creation**).

## Quick start — DNS-01 + EAB (wildcards / internal-only workloads)

### Step 1 — Enable EAB in UCM
1. Log in to UCM as **admin**.
2. **Settings → ACME** → enable **External Account Required**.
3. **ACME → EAB Credentials → Create**. UCM returns once:
   ```
   kid:  XPD3ZsFCbGrWWib9pWYIMw
   hmac: sVbRLYu-AHNZz52yq69Leld02zVMU68GIIkLjHbVzlM
   ```
   Copy both — the HMAC is shown ONLY at creation time. UCM stores a
   hash; if you lose it, revoke and create a new one.

### Step 2 — Create the EAB Secret
```bash
# Edit eab-secret.yaml: paste the HMAC into stringData.hmac
kubectl apply -f eab-secret.yaml
```

### Step 3 — Create the TSIG Secret
```bash
kubectl create secret generic tsig-secret \
  --namespace cert-manager \
  --from-literal=tsig-secret-key='<base64-tsig-secret-from-your-DNS-server>'
```

### Step 4 — Create the ClusterIssuer
```bash
# Edit clusterissuer-ucm-dns01.yaml:
#   - server: → your UCM URL
#   - externalAccountBinding.keyID: → the kid from step 1
#   - rfc2136.nameserver: → your DNS server IP:port
#   - rfc2136.tsigKeyName: → the TSIG key name (with trailing dot)
kubectl apply -f clusterissuer-ucm-dns01.yaml
kubectl wait --for=condition=Ready clusterissuer/ucm-acme-dns01 --timeout=60s
```

### Step 5 — Issue a wildcard
```bash
# Uncomment the "B" section in certificate-example.yaml, edit dnsNames.
kubectl apply -f certificate-example.yaml
kubectl wait --for=condition=Ready certificate/wildcard-example --timeout=300s
```

## Trusting UCM's TLS cert

The examples set `skipTLSVerify: true` for convenience. In production,
distribute UCM's CA cert to cert-manager instead:

```bash
# 1. Export UCM's TLS chain (run on the UCM host, as admin)
openssl s_client -connect <ucm-host>:8443 -showcerts < /dev/null \
  | sed -n '/BEGIN CERT/,/END CERT/p' > ucm-ca.crt

# 2. Mount it into cert-manager via a ConfigMap and the
#    cert-manager-webhook + cert-manager-cainjector deployments
#    (see https://cert-manager.io/docs/configuration/acme/#using-a-private-acme-server).

# 3. Set skipTLSVerify: false in the ClusterIssuer.
```

## Troubleshooting

```bash
# ClusterIssuer not Ready
kubectl describe clusterissuer ucm-acme-dns01

# Cert stuck pending
kubectl describe certificate <name> -n <ns>
kubectl describe order   -n <ns>
kubectl describe challenge -n <ns>
kubectl logs -n cert-manager deploy/cert-manager --tail=200 | grep -i <name>

# Common errors
#   externalAccountRequired       → UCM has EAB ON but issuer has none
#   unauthorized (EAB)            → wrong kid/hmac, or HMAC was reused
#   EAB credential not usable     → EAB is "used" or "revoked" — create a new one
#   x509 unknown authority        → set skipTLSVerify: true OR distribute UCM's CA
#   TSIG: bad key                 → TSIG name/algorithm/secret mismatch with DNS server
#   DNS-01 self-check failed      → recursive resolver doesn't see the TXT record
#                                    (use --dns01-recursive-nameservers-only on cert-manager)
```

## Notes about UCM's ACME server

- **Internal domains supported**: UCM is on-prem PKI. Domains like
  `*.lan`, `*.local`, RFC1918 IPs are first-class — no extra config.
- **EAB is one-shot**: a credential goes `active → used` after first
  successful registration. Renewals reuse the existing account, no
  EAB required. To rotate the account, create a new EAB and delete
  cert-manager's account-key Secret.
- **Account key change** (RFC 8555 §7.3.5) is supported and audited.
- **Audit**: account creation, order creation, finalize, certificate
  revoke, challenge final state, and key change are written to UCM's
  audit log (Operations → Audit Logs).
- **Renewal**: cert-manager renews based on `renewBefore` (default
  2/3 of cert lifetime). UCM has no rate limit on renewals.
