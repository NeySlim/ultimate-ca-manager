export default {
  helpContent: {
    title: 'ACME',
    subtitle: 'Automatisierte Zertifikatsverwaltung',
    overview: 'UCM unterstützt zwei ACME-Modi: ACME-Client für öffentliche Zertifikate von jeder RFC 8555-konformen CA (Let\'s Encrypt, ZeroSSL, Buypass, HARICA, usw.) und lokaler ACME-Server für interne PKI-Automatisierung mit Multi-CA-Domänenzuordnung.',
    sections: [
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
        title: 'Multi-CA-Auflösung',
        content: 'Wenn ein ACME-Client ein Zertifikat anfordert, löst UCM die signierende CA in dieser Reihenfolge auf:',
        items: [
          '1. Lokale Domänenzuordnung — exakter Domänenabgleich, dann übergeordnete Domäne',
          '2. DNS-Domänenzuordnung — prüft die für den DNS-Anbieter konfigurierte ausstellende CA',
          '3. Globaler Standard — die in der ACME-Serverkonfiguration festgelegte CA',
          '4. Erste verfügbare CA mit einem privaten Schlüssel',
        ]
      },
    ],
    tips: [
      'ACME-Directory-URL: https://ihr-server:port/acme/directory',
      'Verwenden Sie eine benutzerdefinierte Directory-URL, um sich mit ZeroSSL, Buypass, HARICA oder einer anderen RFC 8555-CA zu verbinden',
      'EAB-Anmeldeinformationen (Key ID + HMAC Key) werden von Ihrer CA bei der Registrierung bereitgestellt',
      'ECDSA P-256-Schlüssel bieten gleichwertige Sicherheit wie RSA-2048 bei deutlich geringerer Größe',
      'Verwenden Sie lokale Domänen, um verschiedenen internen Domänen unterschiedliche CAs zuzuweisen',
      'Jede CA mit einem privaten Schlüssel kann als ausstellende CA ausgewählt werden',
      'Wildcard-Domänen (*.example.com) erfordern DNS-01-Validierung',
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
`
  }
}
