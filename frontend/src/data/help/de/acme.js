export default {
  helpContent: {
    title: 'ACME',
    subtitle: 'Automatisierte Zertifikatsverwaltung',
    overview: 'UCM unterstützt zwei ACME-Modi: ACME-Client für öffentliche Zertifikate von jeder RFC 8555-konformen CA (Let\'s Encrypt, ZeroSSL, Buypass, HARICA, usw.) und lokaler ACME-Server für interne PKI-Automatisierung mit Multi-CA-Domänenzuordnung.',
    sections: [
      {
        title: "Renewal Information (ARI, RFC 9773)",
        content: "Der lokale ACME-Server stellt eine renewalInfo-Ressource bereit, damit Clients den idealen Zeitpunkt zur Erneuerung jedes Zertifikats erfahren.",
        items: [
          { label: "Vorgeschlagenes Fenster", text: "Liefert ein Start/Ende-Fenster zentriert vor dem Ablauf, um Erneuerungen zeitlich zu verteilen" },
          { label: "Widerruf", text: "Ein widerrufenes Zertifikat liefert ein Fenster in der Vergangenheit → konforme Clients erneuern sofort" },
          { label: "Ohne Authentifizierung", text: "renewalInfo ist ein einfacher GET — weder Konto noch JWS erforderlich (RFC 9773)" },
        ]
      },
      {
        title: 'ACME-Client',
        items: [
          { label: 'Client', text: 'Zertifikate von jeder ACME-CA anfordern — Let\'s Encrypt, ZeroSSL, Buypass, HARICA oder benutzerdefiniert' },
          { label: 'Benutzerdefinierter Server', text: 'Eine benutzerdefinierte ACME-Directory-URL festlegen, um eine beliebige RFC 8555-konforme CA zu verwenden' },
          { label: 'EAB', text: 'External Account Binding-Unterstützung für CAs, die eine Vorregistrierung erfordern (ZeroSSL, HARICA, usw.)' },
          { label: 'Schlüsseltypen', text: 'RSA-2048, RSA-4096, ECDSA P-256, ECDSA P-384 für Zertifikatsschlüssel' },
          { label: 'Kontoschlüssel', text: 'ES256 (P-256), ES384 (P-384) oder RS256-Algorithmen für ACME-Kontoschlüssel' },
          { label: 'DNS-Anbieter', text: 'DNS-01-Challenge-Anbieter konfigurieren (Cloudflare, Route53, usw.)' },
          { label: 'Domänen', text: 'Domänen DNS-Anbietern für automatische Validierung zuordnen' },
        ]
      },
      {
        title: 'Lokaler ACME-Server',
        items: [
          { label: 'Konfiguration', text: 'Den integrierten ACME-Server aktivieren/deaktivieren, Standard-CA auswählen' },
          { label: 'Lokale Domänen', text: 'Interne Domänen bestimmten CAs für Multi-CA-Ausstellung zuordnen' },
          { label: 'Konten', text: 'Registrierte ACME-Client-Konten anzeigen und verwalten' },
          { label: 'Verlauf', text: 'Alle ACME-Zertifikatsausstellungsaufträge verfolgen' },
        ]
      },
      {
        title: 'ACME-Proxy',
        items: [
          { label: 'Upstream-CA', text: 'Wählen Sie eine Voreinstellung (Let\'s Encrypt Produktion/Staging) oder geben Sie eine benutzerdefinierte URL für jede RFC 8555 CA ein' },
          { label: 'Kontostatus', text: 'Zeigt an, ob UCM bei der Upstream-CA registriert ist. Konten werden automatisch bei der ersten Proxy-Anfrage registriert' },
          { label: 'Verbindungstest', text: 'Überprüfen Sie die Konnektivität zur Upstream-CA und prüfen Sie, ob EAB-Zugangsdaten erforderlich sind' },
          { label: 'Konto zurücksetzen', text: 'Löschen Sie gespeicherte Upstream-Zugangsdaten, um eine Neuregistrierung zu erzwingen (nach CA-Wechsel verwenden)' },
          { label: 'EAB-Zugangsdaten', text: 'External Account Binding-Zugangsdaten für CAs, die sie erfordern (z.B. ZeroSSL, Google Trust)' },
          { label: 'DNS-Herausforderungen', text: 'UCM bearbeitet DNS-01-Herausforderungen im Auftrag der Clients mit konfigurierten DNS-Anbietern' },
        ]
      },
      {
        title: 'EAB-Credentials (serverseitig)',
        content: 'Wenn UCM als ACME-Server fungiert, erlaubt External Account Binding (RFC 8555 §7.3.4) das Erfordern vorab ausgegebener Credentials, bevor Clients Konten registrieren können:',
        items: [
          { label: 'Ausstellen', text: 'Neues kid + HMAC-Schlüsselpaar unter ACME → EAB Credentials erzeugen' },
          { label: 'Verteilen', text: 'kid + HMAC an den Client weitergeben (cert-manager, certbot, acme.sh)' },
          { label: 'Binden', text: 'Der Client signiert ein JWS über den MAC-Schlüssel bei newAccount, um sein ACME-Konto zu binden' },
          { label: 'Rotieren / Widerrufen', text: 'kid jederzeit widerrufen — bestehende Konten funktionieren weiter, neue Bindungen werden abgelehnt' },
          { label: 'Audit', text: 'Ausstellung, Rotation und Widerruf werden unter dem ausführenden Operator auditiert' },
        ]
      },
      {
        title: 'Benutzerdefinierte DNS-Resolver (DNS-01)',
        items: [
          { label: 'Pro Konto override', text: 'System-Resolver bei der Validierung von _acme-challenge TXT-Records überschreiben' },
          { label: 'Split-Horizon', text: 'Nützlich, wenn Ihr autoritativer Server intern ist, die öffentliche Sicht aber anderswo gecacht wird' },
          { label: 'Veraltete Records', text: 'Vermeidet Public-Resolver-Caching während schneller Auto-Renewals' },
        ]
      },
      {
        title: 'ACME über interne / private IPs',
        content: 'HTTP-01 und TLS-ALPN-01-Validierung funktioniert standardmäßig für RFC1918, Loopback, .lan / .local / .corp-Ziele — UCMs primäres Deployment-Modell.',
        items: [
          { label: 'Toggle', text: 'Settings → SystemConfig → acme.allow_private_ips (Standard: true)' },
          { label: 'Immer blockiert', text: 'Cloud-Metadata-IPs (169.254.169.254, fd00:ec2::254 usw.) werden bedingungslos blockiert' },
        ]
      },
      {
        title: 'Multi-CA-Auflösung',
        content: 'Wenn ein ACME-Client ein Zertifikat anfordert, löst UCM die signierende CA in dieser Reihenfolge auf:',
        items: [
          '1. Lokale Domänenzuordnung — exakter Domänenabgleich, dann übergeordnete Domäne',
          '2. DNS-Domänenzuordnung — prüft die für den DNS-Anbieter konfigurierte ausstellende CA',
          '3. Globaler Standard — die in der ACME-Serverkonfiguration festgelegte CA',
          '4. Erste verfügbare CA mit einem privaten Schlüssel',
        ]
      },
      {
        title: 'Zertifikate für IP-Adressen (RFC 8738)',
        content: 'Der lokale ACME-Server kann Zertifikate für IPv4- und IPv6-Adressen ausstellen, nicht nur für DNS-Namen. Verwenden Sie den Identifier-Typ „ip“ in der Bestellung.',
        items: [
          { label: 'Identifier', text: 'Bestellung mit { "type": "ip", "value": "192.0.2.10" } (IPv4) oder einem IPv6-Literal wie 2001:db8::1' },
          { label: 'Challenges', text: 'Nur HTTP-01 und TLS-ALPN-01 werden angeboten — DNS-01 ist für IP-Identifier gemäß RFC 8738 verboten' },
          { label: 'TLS-ALPN-01 SNI', text: 'Die Validierung verwendet die Reverse-DNS-Form (in-addr.arpa / ip6.arpa) als SNI-Hostname' },
          { label: 'Ausgestellter SAN', text: 'Das Zertifikat enthält einen iPAddress-SAN; gemischte DNS- + IP-Bestellungen werden unterstützt' },
          { label: 'Interne IPs', text: 'RFC1918- und Loopback-Adressen werden sofort validiert — UCMs primäres Bereitstellungsmodell' },
        ]
      }
    ],
    tips: [
      'ACME-Directory-URL: https://ihr-server:port/acme/directory',
      'Verwenden Sie eine benutzerdefinierte Directory-URL, um sich mit ZeroSSL, Buypass, HARICA oder einer anderen RFC 8555-CA zu verbinden',
      'EAB-Anmeldeinformationen (Key ID + HMAC Key) werden von Ihrer CA bei der Registrierung bereitgestellt',
      'ECDSA P-256-Schlüssel bieten gleichwertige Sicherheit wie RSA-2048 bei deutlich geringerer Größe',
      'Verwenden Sie lokale Domänen, um verschiedenen internen Domänen unterschiedliche CAs zuzuweisen',
      'Jede CA mit einem privaten Schlüssel kann als ausstellende CA ausgewählt werden',
      'Wildcard-Domänen (*.example.com) erfordern DNS-01-Validierung',
      'Wenn UCM der ACME-Server ist, eigene EAB-Credentials unter ACME → EAB Credentials ausstellen',
      'Für Kubernetes/cert-manager: Referenzmanifeste unter examples/kubernetes/cert-manager/',
    ],
    warnings: [
      'Domänenvalidierung ist erforderlich — Ihr Server muss erreichbar sein oder DNS konfiguriert sein',
      'Das Ändern des Kontoschlüsseltyps erfordert eine erneute Registrierung Ihres ACME-Kontos',
    ],
  },
  helpGuides: {
    title: 'ACME',
    content: `
## Übersicht

UCM unterstützt ACME (Automated Certificate Management Environment) in zwei Modi:

- **ACME-Client** — Zertifikate von jeder RFC 8555-konformen CA erhalten (Let's Encrypt, ZeroSSL, Buypass, HARICA oder benutzerdefiniert)
- **Lokaler ACME-Server** — Integrierter ACME-Server für interne PKI-Automatisierung mit Multi-CA-Unterstützung

## ACME-Client

### Client-Einstellungen
Verwalten Sie Ihre ACME-Client-Konfiguration:
- **Umgebung** — Staging (Test) oder Produktion (Live-Zertifikate)
- **Kontakt-E-Mail** — Erforderlich für die Kontoregistrierung
- **Auto-Erneuerung** — Zertifikate automatisch vor Ablauf erneuern
- **Zertifikatsschlüsseltyp** — RSA-2048, RSA-4096, ECDSA P-256 oder ECDSA P-384
- **Kontoschlüssel-Algorithmus** — ES256, ES384 oder RS256 für die ACME-Kontosignierung

### Benutzerdefinierter ACME-Server
Verwenden Sie jede RFC 8555-konforme CA, nicht nur Let's Encrypt:

| CA-Anbieter | Directory-URL |
|---|---|
| **Let's Encrypt** | *(Standard, leer lassen)* |
| **ZeroSSL** | \`https://acme.zerossl.com/v2/DV90\` |
| **Buypass** | \`https://api.buypass.com/acme/directory\` |
| **HARICA** | \`https://acme-v02.harica.gr/acme/<token>/directory\` |
| **Google Trust** | \`https://dv.acme-v02.api.pki.goog/directory\` |

Legen Sie die Directory-URL Ihrer CA unter **Einstellungen** → **Benutzerdefinierter ACME-Server** fest.

### External Account Binding (EAB)
Einige CAs erfordern EAB-Anmeldeinformationen, um Ihr ACME-Konto mit einem bestehenden Konto bei der CA zu verknüpfen:

1. Registrieren Sie sich im Portal Ihrer CA, um **EAB Key ID** und **HMAC Key** zu erhalten
2. Geben Sie beide Werte unter **Einstellungen** → **Benutzerdefinierter ACME-Server** ein
3. Der HMAC-Schlüssel ist base64url-kodiert (von der CA bereitgestellt)

> 💡 EAB wird von ZeroSSL, HARICA, Google Trust Services und den meisten Enterprise-CAs benötigt.

### ECDSA vs RSA-Schlüssel

| Schlüsseltyp | Größe | Sicherheit | Leistung |
|---|---|---|---|
| **RSA-2048** | 2048 Bit | Standard | Basis |
| **RSA-4096** | 4096 Bit | Höher | Langsamer |
| **ECDSA P-256** | 256 Bit | ≈ RSA-3072 | Deutlich schneller |
| **ECDSA P-384** | 384 Bit | ≈ RSA-7680 | Schneller |

ECDSA-Schlüssel werden für moderne Implementierungen empfohlen — kleiner, schneller und gleich sicher.

### DNS-Anbieter
Konfigurieren Sie DNS-01-Challenge-Anbieter für die Domänenvalidierung. Unterstützte Anbieter umfassen:
- Cloudflare
- AWS Route 53
- Google Cloud DNS
- DigitalOcean
- OVH
- Und weitere

Jeder Anbieter erfordert spezifische API-Anmeldeinformationen für den DNS-Dienst.

### Domänen
Ordnen Sie Ihre Domänen DNS-Anbietern zu. Beim Anfordern eines Zertifikats für eine Domäne verwendet UCM den zugeordneten Anbieter, um DNS-01-Challenge-Einträge zu erstellen.

1. Klicken Sie auf **Domäne hinzufügen**
2. Geben Sie den Domänennamen ein (z.B. \`example.com\` oder \`*.example.com\`)
3. Wählen Sie den DNS-Anbieter
4. Klicken Sie auf **Speichern**

> 💡 Wildcard-Zertifikate (\`*.example.com\`) erfordern DNS-01-Validierung.


## ACME-Proxy-Modus

Der ACME-Proxy ermöglicht es internen Clients, Zertifikate von einer öffentlichen CA (Let's Encrypt, ZeroSSL usw.) über UCM anzufordern, ohne direkten Internetzugang. UCM fungiert als Vermittler, verwaltet DNS-01-Herausforderungen und leitet Anfragen an die Upstream-CA weiter.

### Wann den Proxy-Modus verwenden
- Interne Server ohne direkten Internetzugang
- Zentralisierte DNS-01-Challenge-Behandlung über in UCM konfigurierte DNS-Anbieter
- Audit und Nachverfolgung aller öffentlichen Zertifikatsausstellungen

### Konfiguration
1. Gehen Sie zu **ACME** → Registerkarte **Let's Encrypt**
2. Scrollen Sie zum Abschnitt **ACME Proxy**
3. Aktivieren Sie den **ACME Proxy**-Schalter
4. Wählen Sie ein **Upstream-CA-Konto** unter **Externe CA-Konten** (Let's Encrypt, Actalis, ZeroSSL, benutzerdefinierte URL, EAB)
5. Klicken Sie auf **Verbindungstest**, um die Konnektivität zur Upstream-CA zu überprüfen
6. Registrieren Sie das Upstream-Konto bei Bedarf (E-Mail + **Konto registrieren**)
7. UCM registriert automatisch ein Konto bei der ersten Proxy-Anfrage, falls noch nicht geschehen

### Dedizierte Proxy-Pfade (Multi-CA)
Jedes externe CA-Konto kann einen eigenen ACME-Proxy-Endpunkt bereitstellen:

1. Öffnen Sie **Externe CA-Konten** (gleiche Registerkarte Let's Encrypt)
2. Bearbeiten oder erstellen Sie ein CA-Konto
3. Aktivieren Sie **Über ACME-Proxy bereitstellen**
4. Setzen Sie einen eindeutigen **Proxy-Pfad (Slug)** — z. B. \`actalis-production\`, \`letsencrypt-staging\`
5. Speichern — die URL erscheint im Proxy-Abschnitt und auf der Kontokarte

Clients verwenden:
\`\`\`
https://ihr-ucm-server:8443/acme/proxy/<slug>/directory
\`\`\`

Der Legacy-Standardpfad bleibt für das in den Proxy-Einstellungen gewählte Konto verfügbar:
\`\`\`
https://ihr-ucm-server:8443/acme/proxy/directory
\`\`\`

Reservierte Slugs (nicht erlaubt): \`directory\`, \`new-order\`, \`challenge\`, \`acct\`, usw.

### Kontoverwaltung
- Das **Kontostatus-Badge** zeigt an, ob UCM bei der Upstream-CA registriert ist
- Ein Wechsel der Upstream-CA löscht automatisch veraltete Zugangsdaten und erzwingt eine Neuregistrierung
- Verwenden Sie die Schaltfläche **Konto zurücksetzen**, um Zugangsdaten bei Bedarf manuell zu löschen
- **Verbindungstest** prüft, ob das Upstream-Verzeichnis erreichbar ist und ob EAB erforderlich ist

### Proxy verwenden
Richten Sie Ihre internen ACME-Clients auf das Proxy-Verzeichnis der Ziel-CA.

**Slug-URL** (empfohlen bei mehreren CAs):
\`\`\`
https://ihr-ucm-server:8443/acme/proxy/<slug>/directory
\`\`\`

**Standard-URL** (Konto aus den Proxy-Einstellungen):
\`\`\`
https://ihr-ucm-server:8443/acme/proxy/directory
\`\`\`

Beispiel mit certbot (\`<slug>\` ersetzen):
\`\`\`
certbot certonly \\
  --server https://ihr-ucm-server:8443/acme/proxy/<slug>/directory \\
  --preferred-challenges dns-01 \\
  --authenticator manual \\
  --manual-auth-hook /bin/true \\
  --manual-cleanup-hook /bin/true \\
  --non-interactive --agree-tos -m you@example.com \\
  -d subdomain.example.com
\`\`\`

> 💡 Die Proxy-EAB-Zugangsdaten sind von den Client-EAB getrennt — sie authentifizieren UCM gegenüber der Upstream-CA, nicht Ihre Clients gegenüber UCM.

> ⚠ Voraussetzung: Die Domain muss in ACME Domains mit DNS-Provider konfiguriert sein. Der Proxy unterstützt nur dns-01.

> ⚠ Vermeiden Sie gleichzeitige Anfragen für denselben FQDN (Certbot + UCM-UI).

> ℹ️ Bei selbstsigniertem UCM-HTTPS-Zertifikat (Lab) \`--no-verify-ssl\` zu Certbot hinzufügen.

## Lokaler ACME-Server

### Konfiguration
- **Aktivieren/Deaktivieren** — Den integrierten ACME-Server umschalten
- **Standard-CA** — Auswählen, welche CA Zertifikate standardmäßig signiert
- **Nutzungsbedingungen** — Optionale ToS-URL für Clients

### ACME-Directory-URL
\`\`\`
https://ihr-server:8443/acme/directory
\`\`\`

Clients wie certbot, acme.sh oder Caddy verwenden diese URL, um die ACME-Endpunkte zu ermitteln.

### Lokale Domänen (Multi-CA)
Ordnen Sie interne Domänen bestimmten CAs zu. So können verschiedene Domänen von verschiedenen CAs signiert werden.

1. Klicken Sie auf **Domäne hinzufügen**
2. Geben Sie die Domäne ein (z.B. \`internal.corp\` oder \`*.dev.local\`)
3. Wählen Sie die **ausstellende CA**
4. Aktivieren/deaktivieren Sie **Auto-Genehmigung**
5. Klicken Sie auf **Speichern**

### CA-Auflösungsreihenfolge
Wenn ein ACME-Client ein Zertifikat anfordert, bestimmt UCM die signierende CA in dieser Reihenfolge:
1. **Lokale Domänenzuordnung** — Exakter Abgleich, dann übergeordneter Domänenabgleich
2. **DNS-Domänenzuordnung** — Die für den DNS-Anbieter konfigurierte CA
3. **Globaler Standard** — Die in der ACME-Serverkonfiguration festgelegte CA
4. **Erste verfügbare** — Jede CA mit einem privaten Schlüssel

### Konten
Registrierte ACME-Client-Konten anzeigen:
- Konto-ID und Kontakt-E-Mail
- Registrierungsdatum
- Anzahl der Bestellungen

### Verlauf
Alle Zertifikatsausstellungsaufträge durchsuchen:
- Auftragsstatus (ausstehend, gültig, ungültig, bereit)
- Angeforderte Domänennamen
- Verwendete signierende CA
- Ausstellungszeitpunkt

## certbot verwenden

\`\`\`
# Konto registrieren (Let's Encrypt — Standard)
certbot register --agree-tos --email admin@example.com

# Mit benutzerdefinierter ACME-CA + EAB registrieren
certbot register \\
  --server 'https://acme.zerossl.com/v2/DV90' \\
  --eab-kid 'ihre-key-id' \\
  --eab-hmac-key 'ihr-hmac-schlüssel' \\
  --agree-tos --email admin@example.com

# Zertifikat mit ECDSA-Schlüssel anfordern
certbot certonly --server https://ihr-server:8443/acme/directory \\
  --standalone -d meinserver.internal.corp \\
  --key-type ecdsa --elliptic-curve secp256r1

# Erneuern
certbot renew --server https://ihr-server:8443/acme/directory
\`\`\`

## acme.sh verwenden

\`\`\`
# Standard (Let's Encrypt)
acme.sh --issue -d example.com --standalone

# Benutzerdefinierte ACME-CA mit EAB und ECDSA
acme.sh --issue \\
  --server 'https://acme-v02.harica.gr/acme/TOKEN/directory' \\
  --eab-kid 'ihre-key-id' \\
  --eab-hmac-key 'ihr-hmac-schlüssel' \\
  --keylength ec-256 \\
  -d example.com --standalone
\`\`\`

> ⚠ Für internen ACME-Betrieb müssen Clients der UCM-CA vertrauen. Installieren Sie das Root-CA-Zertifikat im Vertrauensspeicher des Clients.
## Zertifikate für IP-Adressen (RFC 8738)

Der lokale ACME-Server kann Zertifikate für **IP-Adressen** (IPv4 und IPv6) ausstellen, nicht nur für DNS-Namen. Nützlich für interne Dienste, Appliances und direkt per IP adressierte Hosts.

### Ein IP-Zertifikat bestellen
Verwenden Sie den Identifier-Typ \`ip\` in der ACME-Bestellung:
\`\`\`json
{
  "identifiers": [
    { "type": "ip", "value": "192.0.2.10" },
    { "type": "ip", "value": "2001:db8::1" }
  ]
}
\`\`\`
Gemischte DNS- + IP-Bestellungen werden ebenfalls unterstützt.

### Validierung
- **HTTP-01** und **TLS-ALPN-01** sind die einzigen Challenges für IP-Identifier. **DNS-01 ist** für IPs durch RFC 8738 **verboten**.
- **HTTP-01** verbindet sich direkt mit der IP (IPv6-Literale werden in Klammern gesetzt, z. B. \`http://[2001:db8::1]/...\`).
- **TLS-ALPN-01** verwendet die Reverse-DNS-Form der IP (\`in-addr.arpa\` / \`ip6.arpa\`) als SNI-Hostname.

### Ausgestelltes Zertifikat
Das signierte Zertifikat enthält für jede validierte IP einen **iPAddress**-SubjectAltName-Eintrag.

> 💡 Interne Adressen (RFC1918, Loopback) werden sofort validiert — UCMs primäres Bereitstellungsmodell. Cloud-Metadaten-IPs bleiben blockiert.

## Renewal Information (ARI, RFC 9773)

Der lokale ACME-Server kündigt \`renewalInfo\` in seinem Directory an und liefert ein **vorgeschlagenes Erneuerungsfenster** pro Zertifikat.

- Fenster zentriert vor Ablauf → zeitlich verteilte Erneuerungen
- Widerrufenes Zertifikat → Fenster in der Vergangenheit (jetzt erneuern)
- Nicht authentifizierter GET auf \`/acme/renewalInfo/<certID>\`

`
  }
}
