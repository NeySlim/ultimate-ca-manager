# ACME proxy: DNS UPDATE (RFC 2136) clients

The ACME proxy of UCM has an optional DNS UPDATE listener. DNS-01 clients that speak RFC 2136 can use it instead of a DNS provider API. This page gives the settings for each client. For the listener itself (enabling, ports, keys, answers and error codes), read [ADMIN_GUIDE.md](../ADMIN_GUIDE.md#acme-proxy-dns-update-listener-rfc-2136).

> **Internal network only.** Do not expose the listener to the internet.

## How it works

1. The client asks the proxy for a certificate and fetches the DNS-01 challenge.
2. The client sends a TSIG-signed DNS UPDATE for `_acme-challenge.<name>` to UCM, with its TXT value.
3. UCM accepts the update only if the value is the one expected for a pending proxy order of the key's scope.
4. The listener writes **nothing** to DNS. UCM publishes the challenge record through its DNS provider (ACME > Domains). The update tells UCM that the client holds the right value.

The domain must be in **ACME > Domains**.

## Common settings

| Item | Value |
|------|-------|
| ACME directory (all clients) | `https://ucm.example.com:8443/acme/proxy/<slug>/directory` (`<slug>` is the slug of the proxy account) |
| DNS server | `ucm.example.com`, or the Service name in Kubernetes. Port 53 when you mapped it, otherwise the listener port (for example 8053) |
| Key name | The name that UCM shows for the key, for example `myproxy-1a2b3c4d.` (keep the trailing dot where a client needs it) |
| Secret | The base64 secret that UCM shows once when it creates the key |
| Algorithm | **`hmac-sha256`** (`hmac-sha384` and `hmac-sha512` also work in most clients) |
| Clock | Within 300 seconds of the UCM clock |

The examples use these placeholder values:

```
key name:   myproxy-1a2b3c4d.
secret:     REPLACE_WITH_BASE64_SECRET
server:     ucm.example.com  (192.0.2.10)
```

**Do not use the default algorithm of a client.** The defaults are `hmac-md5` (cert-manager, certbot, nsupdate, win-acme) and `hmac-sha1` (lego). UCM answers `BADKEY` to both. Every example below sets `hmac-sha256`.

**Keep the secret safe.** Store it in the secret store of the client. Do not leave it in shell history or in a file that others can read.

## cert-manager

cert-manager has the `rfc2136` solver. Use the manifest [`examples/kubernetes/cert-manager/clusterissuer-ucm-proxy-rfc2136.yaml`](../../examples/kubernetes/cert-manager/clusterissuer-ucm-proxy-rfc2136.yaml).

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ucm-proxy-tsig
  namespace: cert-manager
stringData:
  tsig-secret-key: REPLACE_WITH_BASE64_SECRET
---
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: ucm-proxy-rfc2136
spec:
  acme:
    server: https://ucm.example.com:8443/acme/proxy/<slug>/directory
    email: pki-admin@example.com
    privateKeySecretRef:
      name: ucm-proxy-rfc2136-account-key
    solvers:
      - dns01:
          rfc2136:
            nameserver: ucm-dns-update.ucm.svc:53
            tsigKeyName: myproxy-1a2b3c4d.
            tsigAlgorithm: HMACSHA256
            tsigSecretSecretRef:
              name: ucm-proxy-tsig
              key: tsig-secret-key
            protocol: UDP        # or TCP
```

Facts about cert-manager v1.21:

- `tsigAlgorithm` accepts `HMACMD5` (the default), `HMACSHA1`, `HMACSHA256` and `HMACSHA512`, not `HMACSHA384`. **Set `HMACSHA256` or `HMACSHA512`.**
- `nameserver` is `host[:port]`. A host name is valid. The default port is 53.
- `protocol` is `UDP` (default) or `TCP`.
- cert-manager does not ask UCM for the zone. It finds the zone apex through its **recursive resolvers** (`--dns01-recursive-nameservers`), and sends the UPDATE for that zone to the `nameserver`. The resolvers must see the public zone of the domain. If the cluster cannot reach public DNS, give cert-manager a resolver that can, with `--dns01-recursive-nameservers` (and `--dns01-recursive-nameservers-only` to use only those).
- cert-manager sends an update with a TTL of 60. Several names in one certificate give several updates at the same time.
- For the Helm Service name, see the [chart README](../../charts/ucm/README.md#dns-update-listener). The name is `<fullname>-dns-update`. `<fullname>` is the release name when it contains `ucm`, otherwise `<release>-ucm`. With the release `ucm` in the namespace `ucm`, the nameserver is `ucm-dns-update.ucm.svc:53`.

## acme.sh (`dns_nsupdate`)

acme.sh calls the BIND `nsupdate` tool. Install `nsupdate` (package `bind9-dnsutils`, `bind-utils`) first.

Key file in BIND format (`/etc/acme.sh/ucm.key`, mode `0600`):

```
key "myproxy-1a2b3c4d." {
    algorithm hmac-sha256;
    secret "REPLACE_WITH_BASE64_SECRET";
};
```

```bash
export NSUPDATE_SERVER="ucm.example.com"
export NSUPDATE_SERVER_PORT="53"          # or 8053
export NSUPDATE_KEY="/etc/acme.sh/ucm.key"
# Optional: skip the SOA query, name the zone yourself.
# export NSUPDATE_ZONE="example.com"
# Optional: extra nsupdate options, for example -v to use TCP.
# export NSUPDATE_OPT="-v"

acme.sh --issue --dns dns_nsupdate -d www.example.com \
  --server https://ucm.example.com:8443/acme/proxy/<slug>/directory \
  --dnssleep 60
```

Facts:

- `NSUPDATE_SERVER`, `NSUPDATE_SERVER_PORT`, `NSUPDATE_KEY`, `NSUPDATE_ZONE` and `NSUPDATE_OPT` are the variables of the plugin. It adds the TXT with TTL 60 and removes it with `update delete <name> txt`, which is a delete of the whole TXT set. UCM answers `NOERROR` to that.
- Without `NSUPDATE_ZONE`, `nsupdate` first asks for the SOA of the record name. It **signs** this query when it has a key, and it needs a **signed answer**. UCM signs it. You need no extra setting.
- `nsupdate` sends over UDP and does not handle truncated (TC) answers. UCM keeps the signed SOA answer small for this reason.
- acme.sh checks the TXT record in public DNS before it asks the CA. When the host cannot reach public DNS, or the record needs time, set `--dnssleep <seconds>` to wait instead of checking.
- The key file algorithm must be `hmac-sha256` (or 384 or 512). Without an `algorithm` setting, `nsupdate` uses `hmac-md5`.

## certbot (`certbot-dns-rfc2136`)

Credentials file `/etc/letsencrypt/ucm-rfc2136.ini` (mode `0600`):

```ini
dns_rfc2136_server = 192.0.2.10
dns_rfc2136_port = 53
dns_rfc2136_name = myproxy-1a2b3c4d.
dns_rfc2136_secret = REPLACE_WITH_BASE64_SECRET
dns_rfc2136_algorithm = HMAC-SHA256
# Optional. Sign the SOA query too. UCM answers both ways.
# dns_rfc2136_sign_query = true
```

```bash
certbot certonly \
  --server https://ucm.example.com:8443/acme/proxy/<slug>/directory \
  --dns-rfc2136 \
  --dns-rfc2136-credentials /etc/letsencrypt/ucm-rfc2136.ini \
  --dns-rfc2136-propagation-seconds 60 \
  -d www.example.com
```

Facts (certbot-dns-rfc2136 5.8.0):

- `dns_rfc2136_server` must be an **IP address**. A host name is refused.
- The default algorithm is `HMAC-MD5`. Set `dns_rfc2136_algorithm` (accepted: `HMAC-SHA256`, `HMAC-SHA384`, `HMAC-SHA512`, and the weaker ones that UCM refuses).
- The port is `dns_rfc2136_port`, default 53.
- certbot asks for the SOA first over TCP, then over UDP. It needs a NOERROR answer with the SOA in the answer section, the owner equal to the queried name, and the AA flag. UCM answers like this for the zone apex that is in ACME Domains. certbot goes up from `_acme-challenge.<name>` until it finds it.
- `dns_rfc2136_sign_query` is optional. By default certbot does not sign the SOA query. UCM answers unsigned SOA queries for pending orders.
- certbot sends the UPDATE over TCP only. Map port 53 for TCP as well as UDP.
- certbot adds the TXT with TTL 120 and deletes one record (class NONE).

## lego

```bash
export DNSUPDATE_NAMESERVER="ucm.example.com:53"
export DNSUPDATE_TSIG_KEY="myproxy-1a2b3c4d."
export DNSUPDATE_TSIG_SECRET="REPLACE_WITH_BASE64_SECRET"
export DNSUPDATE_TSIG_ALGORITHM="hmac-sha256."

lego --server https://ucm.example.com:8443/acme/proxy/<slug>/directory \
  --email pki-admin@example.com --accept-tos \
  --dns dnsupdate -d www.example.com run
```

Or a BIND key file (`DNSUPDATE_TSIG_FILE=/etc/lego/ucm.key`, the same format as for acme.sh) instead of key, secret and algorithm.

Facts (lego v4.35.2):

- The provider is `rfc2136`, with the alias `dnsupdate`. The variables are `DNSUPDATE_NAMESERVER`, `DNSUPDATE_TSIG_KEY`, `DNSUPDATE_TSIG_SECRET`, `DNSUPDATE_TSIG_ALGORITHM`, `DNSUPDATE_TSIG_FILE`, `DNSUPDATE_ZONES`, `DNSUPDATE_PROPAGATION_TIMEOUT`, `DNSUPDATE_TTL`, `DNSUPDATE_DNS_TIMEOUT`.
- **The default algorithm is `hmac-sha1`.** UCM refuses it. Set `DNSUPDATE_TSIG_ALGORITHM=hmac-sha256.`
- Without `DNSUPDATE_ZONES`, lego asks the name server (UCM) for the SOA without a signature, over UDP, and repeats over TCP when the answer is truncated. UCM answers.
- When the host cannot reach public DNS, set `DNSUPDATE_ZONES=example.com` (lego then skips the SOA lookup) and replace the propagation check with a fixed wait: `--dns.propagation-wait 90s`. `--dns.propagation-disable-ans` only drops the check against the authoritative servers.
- lego sends one message that first deletes the TXT set of the name (class ANY) and then adds the record, TTL 120. It removes with a delete of one record (class NONE). UCM accepts both forms.
- `DNSUPDATE_NAMESERVER` without a port uses port 53.

## win-acme

```
wacs.exe --baseuri https://ucm.example.com:8443/acme/proxy/<slug>/directory ^
  --accepttos --emailaddress pki-admin@example.com ^
  --validationmode dns-01 --validation rfc2136 ^
  --serverhost ucm.example.com ^
  --tsigkeyname myproxy-1a2b3c4d. ^
  --tsigkeysecret REPLACE_WITH_BASE64_SECRET ^
  --tsigkeyalgorithm sha256
```

Add your usual `--source` options for the host names. (Source options are not part of this plugin and were not checked here.)

Facts (win-acme with ARSoft.Tools.Net 3.6.0):

- The plugin options are `--serverhost`, `--serverport`, `--tsigkeyname`, `--tsigkeysecret` (base64) and `--tsigkeyalgorithm`. The algorithm names are the ARSoft names (`sha256`, `sha384`, `sha512`, ignoring case). An unknown name becomes `md5`. If you set none, it is `md5`.
- **UCM must be reachable on port 53.** `--serverport` is passed to the DNS library as the query timeout (in milliseconds), not as a port. The library always uses port 53. Map port 53 to the listener (`-p 53:8053/udp -p 53:8053/tcp` in Docker, the Helm Service port 53, or a firewall redirect).
- **Do not use `sha384`.** The library computes `hmac-sha384` with SHA-256, so every signature is wrong (`BADSIG`). Use `sha256`.
- win-acme does not ask for the SOA. It sends test updates for the registrable domain and then for each longer name until the server answers `NOERROR`. UCM answers `NOTAUTH` for a zone that is not in ACME Domains (or a parent of one). Put the domain in ACME Domains.
- It sends over UDP first, then TCP, with TTL 60. It deletes one record (class NONE).
- `--eab-key-identifier`, `--eab-key` and `--eab-algorithm` set External Account Binding.

## Posh-ACME (plugin `RFC2136`)

```powershell
$key = Read-Host 'TSIG secret' -AsSecureString
$pArgs = @{
    DDNSNameserver = 'ucm.example.com'
    DDNSPort       = 53
    DDNSKeyName    = 'myproxy-1a2b3c4d.'
    DDNSKeyType    = 'hmac-sha256'
    DDNSKeyValue   = $key
}

New-PACertificate www.example.com -AcceptTOS -Contact pki-admin@example.com `
    -DirectoryUrl 'https://ucm.example.com:8443/acme/proxy/<slug>/directory' `
    -DnsPlugin RFC2136 -PluginArgs $pArgs -DnsSleep 60
```

Facts (Posh-ACME RFC2136 plugin):

- The plugin parameters are `DDNSNameserver`, `DDNSPort` (default 53), `DDNSKeyName`, `DDNSKeyType`, `DDNSKeyValue` (secure string), `DDNSKeyValueInsecure` (deprecated), `DDNSExePath` and `DDNSZone`. `DDNSKeyType` accepts `hmac-md5` to `hmac-sha512`. Use `hmac-sha256`.
- **Set `DDNSNameserver`.** Without it, `nsupdate` finds the server through the SOA record (MNAME) of the zone and sends the update to port 53 there, not to UCM.
- The plugin runs `nsupdate`. It must be in the path (or set `DDNSExePath`).
- `nsupdate` signs the SOA query and needs a signed answer. UCM signs it. With `DDNSZone` (for example `example.com`), `nsupdate` skips the SOA query.
- The plugin adds the TXT with TTL 60 and deletes one record (class NONE).
- `-DnsSleep` (default 120 seconds) is the wait after the update and before the CA validates.

## Quick checks

With the BIND tools you can test a key without a client:

```bash
nsupdate -k /etc/acme.sh/ucm.key <<'EOF'
server ucm.example.com 53
zone example.com.
update add _acme-challenge.www.example.com. 60 TXT "value-of-a-pending-order"
send
EOF
```

`zone` makes `nsupdate` skip the SOA query. `REFUSED` here is normal for a value that no pending order expects. `BADKEY`, `BADSIG` and `BADTIME` mean a key, secret or clock problem. See the table in the Admin Guide.

## Source references

Option names above come from these sources: BIND 9.18 `nsupdate`, acme.sh `dnsapi/dns_nsupdate.sh`, certbot-dns-rfc2136 5.8.0, lego v4.35.2 (`providers/dns/rfc2136`, `cmd/flags.go`), cert-manager v1.21.3 (`ACMEIssuerDNS01ProviderRFC2136`, `pkg/issuer/acme/dns/rfc2136`), Posh-ACME `Plugins/RFC2136.ps1`, win-acme `plugin.validation.dns.rfc2136` with ARSoft.Tools.Net 3.6.0.
