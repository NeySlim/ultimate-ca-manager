export default {
  helpContent: {
    title: 'SSH-Zertifizierungsstellen',
    subtitle: 'SSH-CAs für Benutzer- und Host-Authentifizierung verwalten',
    overview: 'Erstellen und verwalten Sie SSH-Zertifizierungsstellen gemäß den OpenSSH-Standards. SSH-CAs machen die Verteilung einzelner öffentlicher Schlüssel überflüssig — stattdessen vertrauen Server und Benutzer der CA, und die CA signiert Zertifikate, die Zugang gewähren.',
    sections: [
      {
        title: 'CA-Typen',
        items: [
          { label: 'User CA', text: 'Signiert Benutzerzertifikate für die SSH-Anmeldung. Server vertrauen dieser CA und akzeptieren jedes von ihr signierte Zertifikat.' },
          { label: 'Host CA', text: 'Signiert Host-Zertifikate zum Nachweis der Serveridentität. Clients vertrauen dieser CA, um sicherzustellen, dass sie sich mit dem richtigen Server verbinden.' },
        ]
      },
      {
        title: 'Schlüsselalgorithmen',
        items: [
          { label: 'Ed25519', text: 'Modern, schnell, kleine Schlüssel (256 Bit). Empfohlen für neue Bereitstellungen.' },
          { label: 'ECDSA P-256 / P-384', text: 'Elliptische-Kurven-Schlüssel, weit verbreitet. Gutes Gleichgewicht zwischen Sicherheit und Kompatibilität.' },
          { label: 'RSA 2048 / 4096', text: 'Traditioneller Algorithmus. Verwenden Sie 4096 Bit für langlebige CAs. Breiteste Kompatibilität mit älteren Systemen.' },
        ]
      },
      {
        title: 'Serverkonfiguration',
        items: [
          { label: 'Setup-Skript', text: 'Laden Sie ein POSIX-Shell-Skript herunter, das sshd automatisch konfiguriert, dieser CA zu vertrauen. Unterstützt alle gängigen Linux-Distributionen.' },
          { label: 'Manuelle Einrichtung', text: 'Kopieren Sie den öffentlichen CA-Schlüssel und fügen Sie TrustedUserCAKeys (User CA) oder HostCertificate (Host CA) in sshd_config hinzu.' },
        ]
      },
      {
        title: 'Schlüsselwiderruf',
        items: [
          { label: 'KRL (Key Revocation List)', text: 'Kompaktes Binärformat zum Widerrufen einzelner Zertifikate. Wird über RevokedKeys in sshd_config konfiguriert.' },
          { label: 'KRL herunterladen', text: 'Laden Sie die aktuelle KRL-Datei aus dem CA-Detailbereich herunter.' },
        ]
      },
    ],
    tips: [
      'Verwenden Sie getrennte CAs für Benutzer- und Host-Zertifikate — mischen Sie diese niemals.',
      'Ed25519 wird wegen Geschwindigkeit und Sicherheit für neue Bereitstellungen empfohlen.',
      'Laden Sie das Setup-Skript für eine einfache Serverkonfiguration herunter — es übernimmt Sicherung und Validierung automatisch.',
    ],
    warnings: [
      'Das Löschen einer CA widerruft keine von ihr signierten Zertifikate — widerrufen Sie diese zuerst oder aktualisieren Sie das Server-Vertrauen.',
      'Wenn der private Schlüssel der CA kompromittiert wird, müssen alle von ihr signierten Zertifikate als nicht vertrauenswürdig betrachtet werden.',
    ],
  },
  helpGuides: {
    title: 'SSH-Zertifizierungsstellen',
    content: `
## Übersicht

SSH-Zertifizierungsstellen (CAs) bilden das Fundament der zertifikatsbasierten SSH-Authentifizierung. Anstatt einzelne öffentliche Schlüssel an jeden Server zu verteilen, erstellen Sie eine CA und konfigurieren Server so, dass sie ihr vertrauen. Jedes von der CA signierte Zertifikat wird dann automatisch akzeptiert.

UCM unterstützt das OpenSSH-Zertifikatsformat (RFC 4253 + OpenSSH-Erweiterungen), das nativ von OpenSSH 5.4+ verstanden wird — keine zusätzliche Software auf Servern oder Clients erforderlich.

## CA-Typen

### User CA
Eine User CA signiert Zertifikate, die **Benutzer gegenüber Servern** authentifizieren. Wenn ein Server einer User CA vertraut, darf sich jeder Benutzer anmelden, der ein gültiges, von dieser CA signiertes Zertifikat vorweist (vorbehaltlich der Principal-Übereinstimmung).

**Serverkonfiguration:**
\`\`\`
# /etc/ssh/sshd_config
TrustedUserCAKeys /etc/ssh/user_ca.pub
\`\`\`

### Host CA
Eine Host CA signiert Zertifikate, die **Server gegenüber Clients** authentifizieren. Wenn ein Client einer Host CA vertraut, kann er überprüfen, ob der Server, mit dem er sich verbindet, legitim ist — TOFU-Warnungen (Trust On First Use) werden damit eliminiert.

**Client-Konfiguration:**
\`\`\`
# ~/.ssh/known_hosts
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Eine CA erstellen

1. Klicken Sie auf **SSH-CA erstellen**
2. Geben Sie einen aussagekräftigen Namen ein (z. B. „Produktions-User-CA")
3. Wählen Sie den CA-Typ: **User** oder **Host**
4. Wählen Sie den Schlüsselalgorithmus:
   - **Ed25519** — Empfohlen. Schnell, kleine Schlüssel, moderne Sicherheit.
   - **ECDSA P-256/P-384** — Gute Kompatibilität und Sicherheit.
   - **RSA 2048/4096** — Breiteste Kompatibilität, größere Schlüssel.
5. Legen Sie optional die maximale Gültigkeit und Standarderweiterungen fest
6. Klicken Sie auf **Erstellen**

> 💡 Verwenden Sie getrennte CAs für Benutzer- und Host-Zertifikate. Verwenden Sie niemals eine CA für beide Zwecke.

## Servereinrichtung

### Automatisches Setup-Skript

UCM generiert ein POSIX-Shell-Skript, das Ihren Server automatisch konfiguriert:

1. Öffnen Sie den CA-Detailbereich
2. Klicken Sie auf **Setup-Skript herunterladen**
3. Übertragen Sie das Skript auf Ihren Server
4. Führen Sie es aus:

\`\`\`bash
chmod +x setup-ssh-ca.sh
sudo ./setup-ssh-ca.sh
\`\`\`

Das Skript:
- Erkennt Ihr Betriebssystem und Init-System
- Sichert sshd_config vor allen Änderungen
- Installiert den öffentlichen CA-Schlüssel
- Fügt TrustedUserCAKeys (User CA) oder HostCertificate (Host CA) hinzu
- Validiert die Konfiguration mit \`sshd -t\`
- Startet sshd nur bei erfolgreicher Validierung neu
- Unterstützt \`--dry-run\` zur Vorschau der Änderungen

### Manuelle Einrichtung

#### User CA
\`\`\`bash
# Öffentlichen CA-Schlüssel auf den Server kopieren
echo "ssh-ed25519 AAAA... user-ca" | sudo tee /etc/ssh/user_ca.pub

# Zu sshd_config hinzufügen
echo "TrustedUserCAKeys /etc/ssh/user_ca.pub" | sudo tee -a /etc/ssh/sshd_config

# sshd neu starten
sudo systemctl restart sshd
\`\`\`

#### Host CA
\`\`\`bash
# Den Host-Schlüssel des Servers signieren
# Dann zu sshd_config hinzufügen:
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

## Schlüsselwiderrufslisten (KRL)

SSH-CAs unterstützen Schlüsselwiderrufslisten zum Invalidieren kompromittierter Zertifikate:

1. Widerrufen Sie Zertifikate auf der Seite SSH-Zertifikate
2. Laden Sie die aktualisierte KRL aus dem CA-Detailbereich herunter
3. Verteilen Sie die KRL-Datei an die Server:

\`\`\`bash
# Zu sshd_config hinzufügen
RevokedKeys /etc/ssh/revoked_keys
\`\`\`

> ⚠ Server müssen für die Prüfung der KRL konfiguriert sein. Der Widerruf wird erst wirksam, wenn die KRL verteilt wurde.

## Bewährte Praktiken

| Praxis | Empfehlung |
|--------|------------|
| Getrennte CAs | Verwenden Sie separate CAs für Benutzer- und Host-Zertifikate |
| Schlüsselalgorithmus | Ed25519 für neue Bereitstellungen, RSA 4096 für ältere Kompatibilität |
| CA-Lebensdauer | CAs langlebig halten; stattdessen kurzlebige Zertifikate verwenden |
| Sicherung | Exportieren und sicher aufbewahren des privaten CA-Schlüssels |
| Principal-Zuordnung | Principals bestimmten Benutzernamen zuordnen, keine Platzhalter verwenden |
`
  }
}
