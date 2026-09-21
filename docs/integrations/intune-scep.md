# Microsoft Intune SCEP Enrollment

Microsoft Intune does not support a static SCEP challenge password. Instead it
issues a **per-device, per-request encrypted and signed challenge blob** that
only Intune's own API can validate. UCM therefore cannot compare the challenge
locally — it must call Intune to validate every request live.

This guide covers configuring that live validation: the Entra app registration
UCM authenticates with, the SCEP profile fields that enable it, exposing the
SCEP endpoint to devices, and the Intune-side profile.

---

## Prerequisites

- [ ] UCM with version at least v2.209 with SCEP enabled
- [ ] An issuing CA configured in UCM (this guide creates the SCEP profile)
- [ ] Microsoft Intune tenant with Intune licensing and MDM setup already working
- [ ] Entra ID permissions to create an app registration and grant admin consent
- [ ] UCM's SCEP endpoint reachable from managed devices over HTTPS —
      if UCM is internal-only, [Entra Application Proxy](#option-a--microsoft-entra-application-proxy)
      in Step 4 publishes it without exposing the host directly
- [ ] **Auto-approve enabled on the SCEP profile** — required, see note below

> **Auto-approve is mandatory.** UCM rejects any profile with
> `intune_enabled` set but `auto_approve` off:
>
> ```
> Intune SCEP challenge validation requires auto-approve — Intune expects a
> synchronous validate-then-issue response, not a manual approval queue
> ```
>
> A manual approval queue breaks Intune's synchronous flow; the device times
> out waiting for a certificate.

---

## Step 1 — Start the SCEP profile in UCM

**Protocols → SCEP → Profiles → New profile**

![UCM SCEP Profiles tab](img/intune-scep-profiles-empty.png)

Fill in the profile fields:

| Field | Value |
|-------|-------|
| **Name** | e.g. `UCM Intune - Device - Client Authentication` |
| **URL segment** | e.g. `ucm-intune-device-clientauth` — lowercase letters, digits and hyphens only. This becomes the profile's enrollment path: `/scep/ucm-intune-device-clientauth/pkiclient.exe` |
| **Description** | Optional |
| **Certificate Authority** | Your issuing CA, e.g. `Issuing CA 2036` |
| **Certificate template** | e.g. `Client Certificate` — when set, the template's key usage, extended key usage and validity govern every certificate issued through this profile |
| **Enabled** | On |

![New SCEP profile dialog](img/intune-scep-new-profile.png)

Now turn on **Microsoft Intune SCEP challenge validation**. Three things change
in the form:

- The **Challenge Password** field disappears — Intune issues its own
  per-device challenge, so the static challenge and Intune validation are
  mutually exclusive.
- **Auto-approve requests** is forced on and becomes read-only, with the note:
  *"Intune requires auto-approve — its enrollment flow is a synchronous
  validate-then-issue round trip, not a manual approval queue."*
- An **App registration** selector appears, with a **Test connection** button
  and a **Manage app registrations** link. The Entra app is defined once, under
  **Protocols → SCEP → Intune app registrations**, and every profile that validates with the
  same tenant picks it from this list.

![Intune validation enabled on the profile](img/intune-scep-profile-intune.png)

Save the profile later: Step 2 produces the three values the app registration
needs, and Step 3 creates it.

---

## Step 2 — Create the Entra app registration

Open [entra.microsoft.com](https://entra.microsoft.com) → **App registrations**
→ **New registration**.

| Setting | Value |
|---------|-------|
| **Name** | `UCM SCEP Validation` |
| **Supported account types** | Single tenant — *Accounts in this organizational directory only* |
| **Redirect URI** | Not required — UCM uses the client-credentials flow, with no signed-in user |

![Register an application](img/intune-scep-entra-register.png)

### Record the tenant and client IDs

On the app's **Overview** blade, note both values — you'll paste them into UCM
in Step 3.

| Value | Example format |
|-------|----------------|
| Directory (tenant) ID | `aaaabbbb-0000-cccc-1111-dddd2222eeee` |
| Application (client) ID | `00001111-aaaa-2222-bbbb-3333cccc4444` |

Both are GUIDs. The values above are examples — substitute your own.

![App registration Overview](img/intune-scep-entra-overview.png)

### Create a client secret

**Certificates & secrets → Client secrets → New client secret**

| Field | Value |
|-------|-------|
| **Description** | e.g. `UCM_Secret_2026` |
| **Expires** | Entra recommends 180 days (6 months) — choose whatever suits your rotation policy |

> **Copy the secret Value immediately.** Entra displays it only once, at
> creation. If you navigate away without copying it, delete the secret and
> create another.

Note the expiry you chose — SCEP enrollment stops working the day the secret
expires, so it needs rotating on that schedule.

![Add a client secret](img/intune-scep-entra-secret.png)

### Add API permissions

**API permissions → Add a permission.** A new registration starts with only
Microsoft Graph → `User.Read` (delegated), which is not sufficient.

Add two **application** permissions — not delegated, since UCM runs as a daemon
with no signed-in user.

#### 1. Microsoft Graph → `Application.Read.All`

Lets UCM locate your tenant's Intune validation service.

Select **Microsoft Graph**:

![Select Microsoft Graph](img/intune-scep-entra-graph.png)

Choose **Application permissions**:

![Graph application permissions](img/intune-scep-entra-graph-apppermissions.png)

Search for and tick **Application.Read.All**, then **Add permissions**:

![Application.Read.All selected](img/intune-scep-entra-graph-readall.png)

#### 2. Intune → `scep_challenge_provider`

Click **Add a permission** again. This time choose the **Intune** API
(*"Programmatic access to Intune data"*) — not Microsoft Graph:

![Select the Intune API](img/intune-scep-entra-intuneapi.png)

Choose **Application permissions**:

![Intune application permissions](img/intune-scep-entra-intune-apppermissions.png)

Tick **scep_challenge_provider** (*"SCEP challenge validation"*), then
**Add permissions**:

![scep_challenge_provider selected](img/intune-scep-entra-intune-scepprovider.png)

### Grant admin consent

Both new permissions show **⚠ Not granted** until consented.

![Permissions pending consent](img/intune-scep-entra-pending.png)

Click **Grant admin consent for &lt;your organization&gt;** and confirm. Both
rows turn to a green **Granted** status.

> Enrollment fails at the service-discovery step if consent is skipped — the
> permissions being *listed* is not the same as being *granted*.

---

## Step 3 — Register the app in UCM, pick it in the profile, test

**Protocols → SCEP → Intune app registrations → New app registration**. Give it a name
(e.g. `Corp tenant`) and fill in the three values from Step 2:

| Field | Enter |
|-------|-------|
| **Tenant ID** | The Directory (tenant) ID from Step 2. The field hints the tenant domain form (`contoso.onmicrosoft.com`), but the GUID works too |
| **Client ID** | The Application (client) ID from Step 2 |
| **Client secret** | The secret **Value** copied in Step 2 |

![Intune credential fields](img/intune-scep-fields.png)

Once filled in, the profile looks like this:

![Completed Intune profile](img/intune-scep-profile-complete.png)

All three are required. The secret is masked; once saved it displays as
`••••••••` and is never sent back to the browser. Leave it blank when editing an
existing registration to keep the stored secret unchanged. One registration
serves every profile of the tenant: rotate the secret once, in one place.

### Test the connection

Click **Test connection**. The button stays disabled until Tenant ID and Client
ID are both filled.

- **Success:** *"Connected to Intune successfully"*
- **Failure:** *"Intune connection test failed"*, with the underlying error

You can test **before saving** — the form's current values are used. When
editing a saved registration with the secret field left blank, the stored
secret is used instead.

> The test only verifies that UCM can authenticate and reach your tenant's
> Intune validation service. No device or certificate request is involved and no
> real Intune challenge is consumed, so it is safe to run repeatedly.

The outcome is recorded on the registration as the last-test timestamp and
result, shown in the Intune app registrations list.

A green toast confirms UCM acquired a token and reached your tenant's Intune
validation service:

![Connected to Intune successfully](img/intune-scep-test-toast.png)

Click **Create**. Back in the profile dialog, choose the registration in the
**App registration** selector (the **Test connection** button there tests the
selected registration) and click **Create**. The profile now shows an
**Intune** badge in the profiles list, and the registration shows which
profiles use it.

> Upgrading from an earlier version: profiles that carried their own tenant,
> client ID and secret get a registration automatically, named after the
> profile and shared by the profiles that used the same tenant, client ID and
> secret. A profile on a different secret (a rotation in progress) keeps a
> registration of its own, so it goes on enrolling; the log says so, and you
> merge the two by hand once every profile is on the new secret.

![Profiles list showing the Intune badge](img/intune-scep-profiles-list.png)

The row shows the enrollment path, the CA and template, and both an
**Auto-approve requests** and an **Intune** badge.

> **Secret storage:** the client secret is encrypted at rest.

### Copy the SCEP URL

Use the copy button on the profile row to get the enrollment URL — you'll need
it for the Intune profile in Step 5. It is built from the URL segment you chose:

```
https://<ucm-host>/scep/<url-segment>/pkiclient.exe
```

For the example profile above, with URL segment `ucm-intune-device-clientauth`:

```
https://ucm.domain.com/scep/ucm-intune-device-clientauth/pkiclient.exe
```

Each profile has its own segment, so a second profile (user certificates, say)
gets a different URL against the same UCM host.

---

## Step 4 — Expose the SCEP endpoint

Managed devices must reach UCM's SCEP endpoint over HTTPS.

- **SCEP URL:** `https://ucm.domain.com/scep/<url-segment>/pkiclient.exe`

Choose one exposure method:

### Option A — Microsoft Entra Application Proxy

> **Scope:** this section covers **configuring** the App Proxy application
> only. Installing and registering the connector is out of scope — it assumes
> a connector is already installed and healthy in the group you select below.

Confirm the connector group has at least one **Active** connector before
starting:

![Private Network connectors](img/intune-scep-appproxy-connectors.png)

**Entra admin center → Enterprise applications → New application →
Add your own on-premises application**

#### Application settings

| Setting | Value |
|---------|-------|
| Name | `UCM-Proxy` |
| Internal Url | `https://ucm.domain.com:8443/` — where UCM actually listens |
| External Url | `https://UCMProxy-<tenant>.msappproxy.net/` — the hostname devices will reach |
| Pre Authentication | **Passthrough** — see note below |
| Connector Group | `Default - Europe` — the group serving the UCM network |
| SSL Certificate | Not required when using the default `msappproxy.net` domain |

![App Proxy application configuration](img/intune-scep-appproxy-config.png)

Nothing on the **Advanced** tab needs changing — the defaults are fine for
SCEP.

> **Pre-authentication must be Passthrough.** A SCEP client is not a browser
> and cannot complete an interactive Entra sign-in. With Pre Authentication set
> to "Microsoft Entra ID", the proxy answers the device's SCEP request with a
> sign-in page the client cannot satisfy, and enrollment fails. Passthrough
> forwards the request to UCM unauthenticated at the proxy layer — the SCEP
> challenge itself remains the authentication mechanism, validated live against
> Intune.
>
> Entra notes that from **30 June 2026**, admin consent must be explicitly
> granted for newly created application proxy enterprise applications.

#### Verify

The proxied SCEP endpoint should answer a `GetCACaps` request from outside the
corporate network:

```bash
curl "https://UCMProxy-<tenant>.msappproxy.net/scep/ucm-intune-device-clientauth/pkiclient.exe?operation=GetCACaps"
```

A working endpoint returns UCM's plain-text capability list:

```
POSTPKIOperation
SHA-256
SHA-384
SHA-512
AES
Renewal
GetNextCACert
SCEPStandard
```

`POSTPKIOperation` and `Renewal` are the two that matter for Intune: the first
lets clients POST the PKCS#7 request rather than URL-encode it, the second
allows certificate renewal. `SCEPStandard` advertises RFC 8894 conformance.

Getting this response through the proxy confirms the whole path — DNS, TLS,
Passthrough pre-authentication, and the connector reaching UCM.

### Option B — Reverse proxy (NGINX)

If you are not using App Proxy, publish the SCEP endpoint with NGINX in
**TLS passthrough** mode: NGINX forwards the encrypted stream untouched and
never holds a key or sees plaintext. UCM terminates TLS itself, with its own
certificate, exactly as it does for a direct connection.

This is a `stream` block, not an `http` one. It belongs at the top level of
`nginx.conf`, as a sibling of `http { }` — a file in `sites-enabled/` will not
work, because those are included *inside* `http { }`. The `stream` server also
takes port 443 exclusively, so this host cannot serve ordinary HTTPS sites from
its `http { }` block on the same port; give those a different address or port.

```nginx
# /etc/nginx/nginx.conf — top level, alongside http { }
stream {
    upstream ucm {
        server ucm.domain.com:8443;
    }

    # NGINX reads only the SNI server name from the TLS handshake.
    # It never decrypts the connection.
    map $ssl_preread_server_name $ucm_backend {
        ucm-scep.domain.com  ucm;
        default              "";   # refuse anything else
    }

    server {
        listen      443;
        listen [::]:443;

        ssl_preread on;
        proxy_pass  $ucm_backend;

        proxy_connect_timeout 5s;
        proxy_timeout         60s;
    }
}
```

This needs the `stream` and `stream_ssl_preread` modules. The official NGINX
packages include both, but distribution builds vary — confirm before relying on
it:

```bash
nginx -V 2>&1 | tr ' ' '\n' | grep -E 'stream|ssl_preread'
```

Verify the published endpoint the same way as in Option A, substituting your own
hostname.

#### What passthrough changes

Because NGINX never decrypts the connection, three things follow. None of them
prevent Intune enrollment, but all three are worth knowing before you choose
this over Option A.

| Consequence | Detail |
|-------------|--------|
| UCM's own certificate is what devices see | It must carry the external hostname (`ucm-scep.domain.com`) in its SAN and be trusted by the device. Issue it from the same CA whose root you deploy in Step 5 and the trusted certificate profile covers it. |
| The whole UCM instance is published, not just `/scep/` | Path filtering needs the HTTP layer, which passthrough does not expose. The admin UI and API answer on that hostname too. Restrict by network or firewall, or terminate TLS instead if you need path filtering. |
| Client IPs in UCM's logs become the proxy's address | No `X-Forwarded-For` is possible without the HTTP layer. SCEP request logs and the Requests page will show the NGINX host rather than the enrolling device. |

> **Passthrough is stricter than App Proxy, not equivalent to it.** Entra
> Application Proxy terminates TLS at Microsoft's edge and the connector opens a
> second TLS connection to your Internal Url, so devices see a Microsoft
> certificate and your own certificate is only presented to the connector. The
> `stream` configuration above is true end-to-end passthrough: one TLS session,
> device to UCM.

---

## Step 5 — Configure the Intune SCEP profile

### Prerequisite: deploy the CA chain first

A device can only trust a certificate UCM issues if it already trusts the chain
above it. With a two-tier PKI — a root CA and an issuing CA beneath it — both
have to reach the device, as trusted certificate profiles assigned to the *same
group* that will receive the SCEP profile.

A trusted certificate profile carries exactly one certificate, and the
**Destination Store** field appears for **Windows platforms only** — on
iOS/iPadOS the certificate goes to the system keychain with no store to choose.
So the number of profiles differs by platform.

#### Windows 10 and later — two profiles

| # | Certificate | Destination store | Why |
|---|-------------|-------------------|-----|
| 1 | **Root CA** | Computer certificate store — **Root** | The trust anchor. Nothing beneath it validates without it. |
| 2 | **Issuing CA** | Computer certificate store — **Intermediate** | Completes the chain locally, so validation does not depend on receiving the intermediate from elsewhere. |

#### iOS/iPadOS — two profiles

| # | Certificate | Why |
|---|-------------|-----|
| 1 | **Root CA** | The trust anchor. |
| 2 | **Issuing CA** | Completes the chain on the device. |

There is no Destination Store choice on iOS/iPadOS — the certificate goes to the
system keychain.

![Example of configured profiles (iOS)](img/intune-scep-profile-trustedCA-iOS.png)

> **Deploy the issuing CA too, not just the root.** UCM does return the issuing
> CA to the enrolling device in its `GetCACert` response, so enrollment itself
> generally succeeds without this. The intermediate profile is what makes the
> chain resolvable for *everything else* on the device afterwards — a Wi-Fi or
> VPN supplicant, a browser, a relying service validating the certificate the
> device just enrolled. Deploying it removes a whole class of "the certificate
> is there but nothing accepts it" failures.

#### Export and create

Export each certificate from UCM separately — **Certificate Authorities** →
select the CA → **Export**, format **DER** (Microsoft asks for a DER-encoded
`.cer`), with **Include CA chain** and **Include private key** both **off**. A
trusted certificate profile takes one certificate, not a bundle, and never a
private key.

Then create the profiles under **Devices → Configuration → Create → Trusted
certificate**, assigning each to the *same group* that will receive the SCEP
profile.

> Trusted certificate profiles created for **Windows 10 and later** are listed
> in the admin center under the platform **Windows 8.1 and later**. This is a
> known display quirk, documented by Microsoft; the profiles work on Windows 10
> and 11.

- [ ] Root CA exported from UCM
- [ ] Issuing CA exported from UCM
- [ ] *(Windows)* Root CA profile — Root store
- [ ] *(Windows)* Issuing CA profile — Intermediate store
- [ ] *(iOS/iPadOS)* Root CA profile
- [ ] *(iOS/iPadOS)* Issuing CA profile
- [ ] All assigned to the same group as the SCEP profile below
- [ ] All deploy *before* the SCEP profile

### Create the profile

**Microsoft Intune admin center → Devices → Manage devices → Configuration →
Create**

| Field | Value |
|-------|-------|
| **Platform** | **Windows 10 and later**, or **iOS/iPadOS** — one profile per platform |
| **Profile** | **SCEP certificate** (or **Templates → SCEP certificate**) |

Then in **Basics**, give the profile a name and an optional description.

> **One profile per platform.** An Intune SCEP profile targets a single
> platform, so a mixed fleet needs one profile per platform. They can all point
> at the same UCM SCEP profile URL — UCM does not distinguish clients by
> platform. The settings below are given per platform because the available
> fields differ.

### Configuration settings

The values below are a worked example for the device client-authentication
profile this guide has been building (`ucm-intune-device-clientauth`). Adjust
them to your own template — the next section explains what has to line up.

#### Common to both platforms

| Setting | Value |
|---------|-------|
| **Certificate type** | **Device** — the rest of this table is a device profile. A **User** profile uses user tokens instead (`CN={{UserPrincipalName}}`, a UPN SAN); a device certificate can only carry device attributes in its subject and SAN. |
| **Subject name format** | `CN={{DeviceId}}` or `CN={{AAD_Device_ID}}` |
| **Subject alternative name** | **URI** = `IntuneDeviceId://{{DeviceId}}` — see the note below |
| **Certificate validity period** | `1 year`, the same as the bound template. This value never reaches UCM: the certificate is issued for the template's validity (365 days for the bundled Client Certificate template), capped at the issuing CA's own expiry, so keep the two equal. Intune supports up to 24 months. |
| **Key usage** | **Digital signature** *and* **Key encipherment** |
| **Key size (bits)** | `2048` |
| **Hash algorithm** | **SHA-2** — UCM advertises SHA-256, SHA-384 and SHA-512 |
| **Root Certificate** | The trusted certificate profile from the previous step — on Windows, the **issuing CA** one. See the note below. |
| **Extended key usage** | **Client Authentication** (`1.3.6.1.5.5.7.3.2`) |
| **Renewal threshold (%)** | `20` — renewal starts when 20% of the lifetime remains |
| **SCEP Server URLs** | The externally reachable URL from Step 4, **not** the internal one. The value differs by platform — see the note below. |

Four of those rows are worth a second look:

> **Use the external URL, and mind the trailing path.** Microsoft's
> documentation shows an NDES URL here; with UCM you point at the profile's own
> enrollment endpoint instead. It must be the address devices can reach from the
> internet, and HTTPS is required for all Android enrollment scenarios.
>
> The Windows SCEP client appends `/pkiclient.exe` to whatever it is given, so
> the two platforms take different values for the same endpoint:
>
> | Platform | SCEP Server URL |
> |---|---|
> | iOS/iPadOS | `https://UCMProxy-<tenant>.msappproxy.net/scep/ucm-intune-device-clientauth/pkiclient.exe` |
> | Windows | `https://UCMProxy-<tenant>.msappproxy.net/scep/ucm-intune-device-clientauth` |
>
> Leaving `/pkiclient.exe` on the Windows profile produces a request for
> `.../pkiclient.exe/pkiclient.exe`, which UCM has no route for.
>
> **The URI SAN carries the Intune device identity.** `IntuneDeviceId://{{DeviceId}}`
> is Microsoft's recommended form for NAC solutions, which read it to identify
> the enrolled device. UCM copies the CSR's SubjectAltName through verbatim, so
> the URI arrives in the issued certificate unchanged and is listed on the
> certificate's record.
>
> **Key usage matches UCM's bundled template.** The stock **Client Certificate**
> template asserts `digitalSignature` + `keyEncipherment` with `clientAuth` EKU
> over 365 days, so the values above line up with it as they stand. If you bind
> a template of your own, assert both bits there too — a template governs the
> issued key usage, so one asserting only `digitalSignature` silently drops
> `keyEncipherment` from the certificate even though Intune accepted the
> request. Note also that UCM derives key usage from the enrollee's key
> algorithm: an ECDSA or Ed25519 key never asserts `keyEncipherment`, since it
> cannot honour it. The RSA-2048 key above is unaffected.
>
> **Root Certificate is not necessarily the root.** On Windows, point this at
> the trusted certificate profile holding the **issuing CA** (e.g. `Issuing CA
> 2036`) — the CA that actually signs the device's certificate — not the
> top-level root. The field takes a single profile; the others stay deployed,
> they are simply not the one referenced here.

#### Windows 10 and later

> **Windows needs UCM v2.232 or later.** Earlier releases refused the Windows
> client's RSAES-OAEP key transport at the `PKIOperation` step
> ([#228](https://github.com/NeySlim/ultimate-ca-manager/issues/228)); iOS/iPadOS
> was never affected.

One setting exists only on the Windows profile:

| Setting | Value |
|---------|-------|
| **Key storage provider (KSP)** | **Enroll to Trusted Platform Module (TPM) KSP, otherwise fail** — requires a usable TPM and refuses to fall back to a software key |

> **That KSP value is deliberate and strict.** It guarantees the private key is
> hardware-bound and non-exportable, but enrollment *fails* on any device
> without a working TPM rather than quietly issuing a software-backed key.
> Choose *"…if present, otherwise Software KSP"* instead only if your fleet
> includes devices that cannot meet that bar.

#### iOS/iPadOS

The iOS/iPadOS profile has **no Key storage provider field** — key protection is
handled by the device's own keychain and Secure Enclave policy rather than by a
profile setting. Every other value is the same as the common table above.

Finish through **Assignments** (target the same group as the trusted certificate
profiles) and **Review + create**.

### Match the settings to UCM's template

Two independent checks sit on either side of the enrollment, and it helps to
keep them apart:

1. **Intune validates the CSR against its own profile.** The device builds the
   CSR from the Intune settings, so this normally agrees by construction. It
   fails when something rewrites the request — see *Known issue: escaped special
   characters* below — and surfaces as `SubjectNameMismatch`,
   `SubjectAltNameMismatch`, `KeyUsageMismatch`, `KeyLengthMismatch` or
   `EnhancedKeyUsageMismatch` in the Troubleshooting table.
2. **UCM's bound template governs what is actually issued.** It is not part of
   Intune's check. A template narrower than the Intune profile does not fail
   anything — it quietly issues a certificate with less than the device asked
   for.

The second is the one that bites silently, so it is worth confirming the
template matches. UCM's bundled **Client Certificate** template, the one this
guide binds in Step 1, is already aligned with the settings above:

| Template setting | Value | Intune counterpart |
|------------------|-------|--------------------|
| Key usage | `digitalSignature`, `keyEncipherment` | **Key usage** |
| Extended key usage | `clientAuth` | **Extended key usage** |
| Validity | 365 days | **Certificate validity period** |

If you bind a template of your own, line these up rather than adjusting the
Intune profile to match a narrower template.

### Known issue: escaped special characters

If a subject name contains `+`, `,`, `;` or `=` as an escaped character
(preceded by a backslash), the resulting CSR carries an incorrect subject name,
Intune's challenge validation fails, and no certificate is issued. Quote the
whole CN value instead, or remove the character:

```
CN="Test User (TestCompany, LLC)",OU=UserAccounts,DC=corp,DC=contoso,DC=com
```

---

## Troubleshooting

### Connection test fails

| Symptom | Likely cause |
|---------|--------------|
| `Tenant ID, client ID and client secret are all required` | A field was left blank and no saved secret exists |
| Token acquisition failure | Wrong tenant/client ID, or expired/mistyped client secret |
| Service discovery failure | Admin consent not granted, or missing API permissions |

### Profile save rejected

These are server-side validation errors, surfaced as an error message when you
save the profile form.

| Error | Fix |
|-------|-----|
| `Intune SCEP challenge validation requires a tenant ID and client ID` | Fill both fields |
| `Intune SCEP challenge validation requires a client secret` | Enter a secret — required unless one is already stored |
| `Intune SCEP challenge validation requires auto-approve` | Should not occur via the web interface, which forces auto-approve on. Seen when a profile is modified outside the UI. |

### Validation error codes

UCM surfaces Intune's own error codes verbatim (mirroring Microsoft's
`ErrorCode` enum). Any code other than `Success` means **do not trust the
request** — no certificate is issued.

| Code | Meaning |
|------|---------|
| `ChallengePasswordMissing` | CSR carried no challenge — device didn't get one from Intune |
| `ChallengeDecryptionError` | Challenge could not be decrypted |
| `ChallengeDeserializationError` | Challenge blob malformed |
| `ChallengeDecodingError` | Challenge could not be decoded |
| `ChallengeInvalidTimestamp` | Challenge timestamp invalid |
| `ChallengeExpired` | Challenge past its validity window — device retried too late |
| `CertificateRequestDecodingFailed` | CSR could not be parsed |
| `SubjectNameMissing` / `SubjectNameMismatch` | CSR subject absent or disagrees with the Intune profile |
| `SubjectAltNameMissing` / `SubjectAltNameMismatch` | SAN absent or disagrees with the Intune profile |
| `KeyUsageMismatch` | Key usage differs from the Intune profile |
| `KeyLengthMismatch` | Key size differs from the Intune profile |
| `EnhancedKeyUsageMissing` / `EnhancedKeyUsageMismatch` | EKU absent or disagrees |
| `AadKeyIdentifierListMissing` | Expected Entra key identifier list absent |
| `RegisteredKeyMismatch` | Key does not match the device's registered key |
| `SigningCertThumbprintMismatch` | Signing certificate thumbprint mismatch |
| `ScepProfileNoLongerTargetedToTheClient` | Profile no longer assigned to the device |
| `SignatureValidationFailed` | Request signature invalid |
| `BadCertificateRequestIdInChallenge` | Challenge references an unknown request |
| `BadDeviceIdInChallenge` | Challenge references an unknown device |
| `BadUserIdInChallenge` | Challenge references an unknown user |
| `Unknown` | Unrecognized code, or a transport failure reaching Intune |

> Transport failures (network error, malformed response) are treated the same
> as a validation rejection: the certificate is not issued.

### Enrollment fails on the device

- [ ] Confirm the connection test passes
- [ ] Confirm the SCEP URL is reachable from the device network
- [ ] Confirm the trusted certificate profiles (root *and* issuing CA) deploy before the SCEP profile
- [ ] Confirm the profile is still assigned to the device
- [ ] Check UCM logs for the returned Intune error code

#### Where to look on the UCM side

Every inbound SCEP request is logged with its operation, and every rejection is
logged with the reason that produced it. This is UCM's **application** log — the
web server's access log carries status codes only and will show a rejected
enrollment as an unremarkable `200`.

Where that application log lands depends on how UCM was installed.

**DEB / RPM (systemd)** — the unit sets `StandardOutput=journal` with
`SyslogIdentifier=ucm`, so the journal is the reliable place to look:

```bash
sudo journalctl -u ucm --since "10 min ago" | grep SCEP
```

Widen it to catch the Intune validation errors too, which do not all contain the
string `SCEP`:

```bash
sudo journalctl -u ucm --since "1 hour ago" \
  | grep -E "SCEP (request|error response)|Intune SCEP|scep"
```

Follow it live while a device enrolls — usually the fastest way to see what a
failing enrollment actually did:

```bash
sudo journalctl -u ucm -f | grep --line-buffered -iE "scep|intune"
```

Depending on the install, the same lines may also be written to
`/var/log/ucm/ucm.log`. If the journal is empty, check there:

```bash
grep -E "SCEP (request|error response)|Intune SCEP" /var/log/ucm/ucm.log | tail -50
```

**Docker** — the application log goes to stdout:

```bash
docker logs --since 10m <container> 2>&1 | grep -iE "scep|intune"
```

For reference, the files a native install may write:

| Log | Path | Contents |
|-----|------|----------|
| Application log | `/var/log/ucm/ucm.log` | Every SCEP request, and the reason for every rejection |
| Access log | `/var/log/ucm/access.log` | HTTP requests only — status codes, no SCEP detail |
| Gunicorn error log | `/var/log/ucm/error.log` | Worker startup and unhandled tracebacks |

> **A SCEP failure is not an HTTP failure.** Per RFC 8894 §3.3.2, protocol
> errors are returned *inside* a signed PKI message with HTTP 200 — an HTTP
> status is only used for transport problems. A device that reports an
> enrollment failure against a string of `200`s in the access log is normal;
> the reason is only in the application log.

Requests rejected during validation — a failed challenge, a message that does
not decrypt, a CSR whose signature does not verify — are refused before a
request record is created, so they appear in the application log but **not** in
the SCEP Requests page. An empty Requests page therefore does not mean the
device never reached UCM.

#### Where to look on the device

##### Windows 10 and later

- **Event Viewer** → *Applications and Services Logs* → *Microsoft* → *Windows*
  → **DeviceManagement-Enterprise-Diagnostics-Provider** → *Admin*. SCEP
  enrollment results are logged here, including the failure HRESULT.
- Collect a full MDM diagnostic bundle:

  ```powershell
  mdmdiagnosticstool.exe -area DeviceEnrollment;DeviceProvisioning -cab C:\Temp\mdm.cab
  ```

- Check whether the certificate actually landed:

  ```powershell
  certutil -store My           # device certificates
  certutil -store -user My     # user certificates
  ```

##### iOS/iPadOS

- On the device: **Settings** → **General** → **VPN & Device Management** →
  select the management profile to see whether the certificate payload
  installed.
- For detail, capture a **sysdiagnose** (hold both volume buttons and the side
  button briefly) and review the `profiled` and `mdmd` subsystems, or connect
  the device and watch those subsystems live in **Console.app** on a Mac.

##### Both platforms

The Intune admin center reports the profile's own view of the outcome under
**Devices → Configuration → *your profile* → Device status**, which is the
quickest way to confirm the device attempted enrollment at all.

---

## Related Documentation

- [Advanced Features](../ADVANCED-FEATURES.md)
- [Admin Guide](../ADMIN_GUIDE.md)
- [API Reference](../API_REFERENCE.md)
- [Security](../SECURITY.md)
- [Installation Guide](../installation/README.md)

Microsoft documentation:

- [Use SCEP certificate profiles with Microsoft Intune](https://learn.microsoft.com/en-us/intune/device-configuration/certificates/scep-profiles) — the Intune-side profile settings in Step 5
- [Create trusted certificate profiles](https://learn.microsoft.com/en-us/intune/device-configuration/certificates/trusted-root-profiles) — deploying UCM's root CA to devices

## Standards Compliance

| Standard | Relevance |
|----------|-----------|
| [RFC 8894](https://www.rfc-editor.org/rfc/rfc8894) | Simple Certificate Enrolment Protocol (SCEP) |
| [RFC 5280](https://www.rfc-editor.org/rfc/rfc5280) | X.509 certificate and CRL profile |
| [RFC 2986](https://www.rfc-editor.org/rfc/rfc2986) | PKCS #10 certification request syntax |
| [Intune SCEP API reference](https://learn.microsoft.com/en-us/intune/fundamentals/certificates/ref-scep-api) | Microsoft's SCEP validation API |
| [OAuth 2.0 client credentials (RFC 6749 §4.4)](https://www.rfc-editor.org/rfc/rfc6749#section-4.4) | Entra app authentication |
