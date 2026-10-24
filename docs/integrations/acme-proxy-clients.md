# Using the ACME proxy from hosts without DNS API access

The UCM ACME proxy (`/acme/proxy/<slug>/directory` and `/acme/proxy/directory`)
lets internal ACME clients get certificates from an external CA such as
Let's Encrypt or ZeroSSL. UCM creates the `_acme-challenge` TXT record itself,
through the DNS provider set in **ACME → Domains**. The client needs no DNS
credentials.

Every ACME client still insists on running a DNS-01 "solver" step. This guide
shows how to make that step do nothing, for each common client, and how to deal
with the DNS checks that clients run on their own.

---

## When to use this

Use this setup when:

- the ACME clients run on internal hosts that have no internet access, and
- those hosts have no DNS API credentials, and you do not want to give them any.

UCM is then the only component that talks to the external CA and to the DNS API.

Prerequisites:

- The domain (or a parent domain) is in **ACME → Domains** with a DNS provider.
- The upstream CA account is exposed through the proxy (**ACME → Let's Encrypt →
  External CA Accounts → Expose via ACME proxy**). See
  [ADMIN_GUIDE.md](../ADMIN_GUIDE.md) for the proxy settings.
- The proxy supports `dns-01` only. HTTP-01 and TLS-ALPN-01 are not available.

In all examples, `ucm.example.com` is the UCM host and `<slug>` is the proxy
path of the CA account. The default URL
`https://ucm.example.com:8443/acme/proxy/directory` works the same way.

The clients must trust the TLS certificate of UCM. Install the CA that issued
it on the host, or use the client's own CA bundle option.

---

## Why a "no-op" DNS step is enough

RFC 8555 §8.4 says that for DNS-01 the client "provisions a TXT record with the
digest value under that name". The RFC defines no mechanism for this
provisioning. How the record gets created is outside the protocol.

RFC 8555 §7.5.1 says: "The client indicates to the server that it is ready for
the challenge validation by sending an empty JSON body ("{}") carried in a POST
request to the challenge URL (not the authorization URL)."

So a client may run any step it likes, including one that does nothing, and
then send that POST. The proxy accepts it.

UCM does the DNS work itself. When the client fetches the authorization, UCM
starts to publish two TXT values under `_acme-challenge.<domain>`:

- the value that the upstream CA expects, so the upstream CA can validate, and
- the value computed with the client's own account key, so the checks that the
  client runs for itself can pass.

When the record is visible, UCM submits the challenge to the external CA. The
POST from the client only says that the client is ready: the proxy answers with
the status `processing`, and the client polls until the challenge is `valid`.

---

## Per-client configuration

### certbot

```bash
certbot certonly \
  --server https://ucm.example.com:8443/acme/proxy/<slug>/directory \
  --authenticator manual \
  --preferred-challenges dns-01 \
  --manual-auth-hook /bin/true \
  --manual-cleanup-hook /bin/true \
  --non-interactive --agree-tos -m admin@example.com \
  -d app.example.com
```

The `manual` authenticator runs the two hooks and does not check DNS. With
`/bin/true` as hook, nothing happens in the solver step.

### acme.sh

acme.sh has no built-in no-op DNS mode, so add a small DNS API file. Create
`~/.acme.sh/dnsapi/dns_ucmproxy.sh`:

```sh
#!/usr/bin/env sh
# No-op DNS API for the UCM ACME proxy. UCM creates the TXT record itself.

# Usage: dns_ucmproxy_add _acme-challenge.www.example.com "txt-value"
dns_ucmproxy_add() {
  return 0
}

# Usage: dns_ucmproxy_rm _acme-challenge.www.example.com "txt-value"
dns_ucmproxy_rm() {
  return 0
}
```

Then issue the certificate:

```bash
acme.sh --issue \
  --server https://ucm.example.com:8443/acme/proxy/<slug>/directory \
  --dns dns_ucmproxy \
  --dnssleep 30 \
  -d app.example.com
```

For `--dns <name>`, acme.sh loads `dnsapi/<name>.sh` and calls `<name>_add` and
`<name>_rm` with the TXT name and value as arguments. A non-zero return code is
an error, so both functions return 0.

`--dnssleep <seconds>` is important. Without it, acme.sh checks the TXT record
through public DNS-over-HTTPS resolvers (Cloudflare, Google, AliDNS, DNSPod).
A host without internet cannot reach them. With `--dnssleep`, acme.sh does not
check anything and only waits for the given time.

### lego

Use the `exec` DNS provider with `/bin/true` as the program, and tell lego not
to check the TXT record:

```bash
EXEC_PATH=/bin/true \
lego --server https://ucm.example.com:8443/acme/proxy/<slug>/directory \
  --email admin@example.com \
  --accept-tos \
  --dns exec \
  --dns.propagation-wait 30s \
  --domains app.example.com \
  run
```

- The `exec` provider runs the program in `EXEC_PATH` with the arguments
  `present` or `cleanup`, the record name and the record value. `/bin/true`
  ignores them and exits with 0.
- `--dns.propagation-wait <duration>` "disables all the propagation checks of
  the TXT record and uses a wait duration instead".
- `--dns.propagation-disable-ans` is a weaker option. It skips only the check on
  the authoritative name servers.
- `--dns.resolvers host:port` sets the resolvers that lego uses to find the zone
  apex. See [DNS resolver limits](#dns-resolver-limits).
- With several domains, the `exec` provider handles them one after the other
  and waits 60 seconds between them by default. Set `EXEC_SEQUENCE_INTERVAL`
  (seconds) to a lower value to shorten this.

Traefik also uses lego. This guide does not cover Traefik, because its
configuration is not part of the lego source that was checked.

### cert-manager

cert-manager has no script solver and no no-op solver. Use its built-in
`acmeDNS` solver with a small stub that answers every update call with
HTTP 200. The solver sends `POST <host>/update` and accepts any 2xx answer. It
does not read the response body.

Parts:

1. A small nginx Deployment and Service in the `cert-manager` namespace. It
   answers `POST /update` with HTTP 200 and `{"txt":"noop"}`, `/health` with 200,
   and everything else with 404.
2. A Secret that holds the acme-dns account file. It is a JSON object with one
   entry per domain name. cert-manager looks up the entry by the domain name of
   the challenge (for `*.example.com` this is `example.com`). It sends the
   `subdomain`, `username` and `password` of the entry to the stub. The stub
   ignores them, so any values work. The Secret must be in the cert-manager
   cluster resource namespace (default `cert-manager`) for a ClusterIssuer.
3. A ClusterIssuer with the `acmeDNS` solver. Its `host` is the URL of the stub
   Service, with scheme.

All manifests are in
[`examples/kubernetes/cert-manager/clusterissuer-ucm-proxy-acmedns-stub.yaml`](../../examples/kubernetes/cert-manager/clusterissuer-ucm-proxy-acmedns-stub.yaml).
The key part is the issuer:

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: ucm-acme-proxy
spec:
  acme:
    server: https://ucm.example.com:8443/acme/proxy/<slug>/directory
    email: admin@example.com
    privateKeySecretRef:
      name: ucm-acme-proxy-account-key
    solvers:
      - dns01:
          acmeDNS:
            host: http://ucm-acmedns-stub.cert-manager.svc:8080
            accountSecretRef:
              name: ucm-acmedns-stub-accounts
              key: acmedns.json
```

Edit the domain names in the Secret, then apply the file:

```bash
kubectl apply -f examples/kubernetes/cert-manager/clusterissuer-ucm-proxy-acmedns-stub.yaml
kubectl wait --for=condition=Ready clusterissuer/ucm-acme-proxy --timeout=60s
```

After the solver step, cert-manager checks that the TXT record is visible and
then waits 60 seconds. For the check, see
[DNS resolver limits](#dns-resolver-limits). This step is the most common
problem with cert-manager.

### win-acme (Windows)

Use the `script` validation plugin with create and delete scripts that do
nothing. Create `C:\acme\noop.cmd`:

```bat
@echo off
exit /b 0
```

Run win-acme with:

```bat
wacs.exe --baseuri https://ucm.example.com:8443/acme/proxy/<slug>/directory ^
  --accepttos --emailaddress admin@example.com ^
  --validationmode dns-01 ^
  --validation script ^
  --dnscreatescript C:\acme\noop.cmd ^
  --dnsdeletescript C:\acme\noop.cmd
```

`--validationmode dns-01` is required: the default validation mode is HTTP-01.
Add your usual `--source` arguments to select the host names. If one script
handles both actions, use `--dnsscript <path>` instead of the two other
arguments. win-acme calls the scripts with `create <Identifier> <RecordName>
<Token>` and `delete <Identifier> <RecordName> <Token>` by default.

Before win-acme starts the validation, it queries the name servers of the zone
and waits for the TXT record. A host that cannot reach them can switch this off
in `settings.json`:

```json
{
  "Validation": {
    "PreValidateDns": false
  }
}
```

If you keep the check, win-acme retries `PreValidateDnsRetryCount` times (default 5)
with `PreValidateDnsRetryInterval` seconds between them (default 30). It then
logs that the validation is going to fail and continues anyway. The
`Validation.DnsServers` setting lists the servers that win-acme uses to find the
zone.

### Posh-ACME (Windows / PowerShell)

Posh-ACME can load custom DNS plugins. Set the `POSHACME_PLUGINS` environment
variable to a folder before you import the module. The folder holds `.ps1`
plugin files with unique names. The file name without `.ps1` is the plugin name.
A DNS plugin must define `Get-CurrentPluginType`, `Add-DnsTxt`, `Remove-DnsTxt`
and `Save-DnsTxt`.

Create `C:\poshacme-plugins\UcmProxy.ps1`:

```powershell
function Get-CurrentPluginType { 'dns-01' }

function Add-DnsTxt {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory,Position=0)]
        [string]$RecordName,
        [Parameter(Mandatory,Position=1)]
        [string]$TxtValue,
        [Parameter(ValueFromRemainingArguments)]
        $ExtraParams
    )
    # No-op: UCM creates the TXT record.
}

function Remove-DnsTxt {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory,Position=0)]
        [string]$RecordName,
        [Parameter(Mandatory,Position=1)]
        [string]$TxtValue,
        [Parameter(ValueFromRemainingArguments)]
        $ExtraParams
    )
    # No-op.
}

function Save-DnsTxt {
    [CmdletBinding()]
    param(
        [Parameter(ValueFromRemainingArguments)]
        $ExtraParams
    )
    # No-op.
}
```

Use it:

```powershell
$env:POSHACME_PLUGINS = 'C:\poshacme-plugins'
Import-Module Posh-ACME
Set-PAServer https://ucm.example.com:8443/acme/proxy/<slug>/directory
New-PACertificate app.example.com -AcceptTOS -Contact admin@example.com `
  -Plugin UcmProxy -DnsSleep 30
```

Posh-ACME does not query DNS itself. With `-DnsSleep <seconds>` (default 120)
it waits that time after the plugin runs. Add `-SkipCertificateCheck` to
`Set-PAServer` if UCM uses a certificate that the host does not trust.

---

## DNS resolver limits

Most clients check that the TXT record is visible before they tell the server to
validate. They use their own resolvers for this check. A host without internet
access never sees the public `_acme-challenge` record. The same applies to
split-horizon DNS, where the internal copy of the zone does not contain the
public `_acme-challenge` record.

Options for each client:

| Client | What to do |
|--------|------------|
| cert-manager | Set `--dns01-recursive-nameservers=<resolver that sees the public zone>` and `--dns01-recursive-nameservers-only` on the controller. See below. |
| acme.sh | `--dnssleep <seconds>`. acme.sh only waits and does not check. |
| lego | `--dns.propagation-wait <duration>` skips the checks and waits. `--dns.resolvers <host:port>` changes the resolvers used for zone and CNAME lookups. |
| certbot | Nothing. The manual hooks do no check. |
| win-acme | Set `Validation.PreValidateDns` to `false` in `settings.json`. |
| Posh-ACME | Nothing. It only waits for `-DnsSleep` seconds. |

### cert-manager flags

The controller flags are:

- `--dns01-recursive-nameservers=<list>`: comma-separated `<ip>:<port>` entries
  (or `https://` DNS-over-HTTPS URLs) that cert-manager uses for the DNS-01
  self check. The default is the resolvers in `/etc/resolv.conf`, or `8.8.8.8`
  and `8.8.4.4` if there are none.
- `--dns01-recursive-nameservers-only`: query only these resolvers.

Without `-only`, cert-manager does two things. It uses the recursive resolvers
to find the zone and its authoritative name servers. Then it queries every
authoritative name server of the zone on port 53 for the TXT record. This fails
when the cluster cannot reach those servers. After the check passes, it waits
60 seconds.

With `-only`, cert-manager asks only the listed resolvers. Note that cert-manager
also finds the zone apex through these resolvers (it looks for the SOA record),
so they must resolve the public SOA of the zone. Caching in the resolver can make
the check take longer.

With the Helm chart, use these values:

```yaml
dns01RecursiveNameservers: "10.0.0.53:53"
dns01RecursiveNameserversOnly: true
```

### Network-side fix: conditional forwarder

If you can change the DNS servers, you can fix the problem for all clients at
once. Add a conditional forwarder on the internal resolver for the
`_acme-challenge.<domain>` names (or for the whole public zone). It forwards to
a resolver that sees the public zone, for example the DNS provider's
authoritative servers or a public resolver. The clients then keep their
default settings.

### UCM's own check

UCM also checks that the TXT record is visible before it asks the external CA
to validate. This check has its own setting: **ACME → Let's Encrypt → DNS-01
resolvers**. See the section "ACME DNS-01 resolvers" in
[ADMIN_GUIDE.md](../ADMIN_GUIDE.md#acme-dns-01-resolvers). It does not change
the checks that the clients run.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Client times out while it waits for DNS | The client checks the TXT record with resolvers that cannot see the public zone (no internet, or split-horizon DNS). | Skip or move the check: see [DNS resolver limits](#dns-resolver-limits). Use `--dnssleep` (acme.sh), `--dns.propagation-wait` (lego), `PreValidateDns` (win-acme), or the cert-manager resolver flags. Or add a conditional forwarder. |
| The proxy returns `No DNS provider configured for domain` | The domain, or a parent domain, is not in **ACME → Domains**, or it has no DNS provider. | Add the domain in **ACME → Domains** and select a DNS provider. Request a name under that domain. |
| cert-manager challenge stays in `Waiting for DNS-01 challenge propagation` with `DNS record for "<domain>" not yet propagated` | The cert-manager resolvers do not see the TXT record, or the cluster cannot reach the authoritative name servers on port 53. | Set `--dns01-recursive-nameservers` to a resolver that sees the public zone and add `--dns01-recursive-nameservers-only`. Or add a conditional forwarder. Check the cert-manager controller log. |
| cert-manager challenge error `account credentials not found for domain <domain>` | The acme-dns account Secret has no entry for the domain name of the challenge. | Add an entry for that name to the Secret. For `*.example.com`, use `example.com`. |
| cert-manager error `error getting acmedns accounts secret` | The Secret or the key is missing in the cert-manager cluster resource namespace. | Create the Secret in the `cert-manager` namespace and set `key` to the right file name (`acmedns.json` in the example). |
| acme.sh error `Cannot find DNS API hook for: dns_ucmproxy` | The DNS API file is not in the acme.sh home folder. | Save it as `~/.acme.sh/dnsapi/dns_ucmproxy.sh`. |
| acme.sh error `No DOH` | acme.sh cannot reach any public DNS-over-HTTPS resolver. | Add `--dnssleep <seconds>`. |
| Posh-ACME warns that the plugin is missing a function | The plugin file lacks one of the four required functions. | Define `Get-CurrentPluginType`, `Add-DnsTxt`, `Remove-DnsTxt` and `Save-DnsTxt`. Set `POSHACME_PLUGINS` before `Import-Module`. |

---

## Notes

- Avoid concurrent requests for the same name. A second TXT record can replace
  the first one.
- The EAB credentials of the upstream CA account are set in UCM. They
  authenticate UCM with the upstream CA. They are not the credentials of your
  clients.
