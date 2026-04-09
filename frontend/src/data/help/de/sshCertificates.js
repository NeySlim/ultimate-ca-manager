export default {
  helpContent: {
    title: 'SSH-Zertifikate',
    subtitle: 'OpenSSH-Zertifikate ausstellen und verwalten',
    overview: 'Stellen Sie SSH-Zertifikate aus, die von Ihren SSH-CAs signiert werden. Zertifikate ersetzen die manuelle authorized_keys-Verwaltung durch zeitlich begrenzten, principal-bezogenen Zugang mit automatischem Ablauf. Sowohl Benutzer- als auch Host-Zertifikate werden unterstützt.',
    sections: [
      {
        title: 'Ausstellungsmodi',
        items: [
          { label: 'Signaturmodus', text: 'Fügen Sie einen vorhandenen öffentlichen SSH-Schlüssel zum Signieren ein. Der private Schlüssel verbleibt auf dem Gerät des Benutzers — UCM sieht ihn nie.' },
          { label: 'Generierungsmodus', text: 'UCM generiert ein neues Schlüsselpaar und signiert das Zertifikat. Laden Sie den privaten Schlüssel sofort herunter — er kann später nicht abgerufen werden.' },
        ]
      },
      {
        title: 'Zertifikatsfelder',
        items: [
          { label: 'Key ID', text: 'Eindeutiger Bezeichner des Zertifikats. Erscheint in den SSH-Protokollen zur Auditierung.' },
          { label: 'Principals', text: 'Benutzernamen (Benutzerzertifikat) oder Hostnamen (Host-Zertifikat), für die dieses Zertifikat gültig ist. Kommagetrennt.' },
          { label: 'Gültigkeit', text: 'Lebensdauer des Zertifikats. Wählen Sie eine Vorgabe (1h, 8h, 24h, 7d, 30d, 90d, 365d) oder legen Sie benutzerdefinierte Sekunden fest.' },
          { label: 'Extensions', text: 'SSH-Erweiterungen wie permit-pty, permit-agent-forwarding. Nur für Benutzerzertifikate anwendbar.' },
          { label: 'Critical Options', text: 'Einschränkungen wie force-command oder source-address zur Begrenzung der Zertifikatsverwendung.' },
        ]
      },
      {
        title: 'Zertifikatstypen',
        items: [
          { label: 'Benutzerzertifikat', text: 'Authentifiziert einen Benutzer gegenüber einem Server. Der Server muss der signierenden CA über TrustedUserCAKeys vertrauen.' },
          { label: 'Host-Zertifikat', text: 'Authentifiziert einen Server gegenüber Clients. Clients vertrauen der CA über @cert-authority in known_hosts.' },
        ]
      },
      {
        title: 'Verwaltung',
        items: [
          { label: 'Widerrufen', text: 'Fügt ein Zertifikat der Schlüsselwiderrufsliste (KRL) der CA hinzu. Server müssen für die Prüfung der KRL konfiguriert sein.' },
          { label: 'Herunterladen', text: 'Laden Sie das Zertifikat, den öffentlichen Schlüssel oder den privaten Schlüssel (nur Generierungsmodus) herunter.' },
        ]
      },
    ],
    tips: [
      'Verwenden Sie kurzlebige Zertifikate (8h–24h) für Benutzerzugang, um die Auswirkungen einer Schlüsselkompromittierung zu minimieren.',
      'Der Signaturmodus ist vorzuziehen — der private Schlüssel des Benutzers verlässt nie dessen Gerät.',
      'Key IDs sollten aussagekräftig sein (z. B. „jdoe-prod-2025") für einfache Protokollauswertung.',
      'Bei Host-Zertifikaten muss der Principal mit dem Hostnamen übereinstimmen, den Clients zur Verbindung verwenden.',
    ],
    warnings: [
      'Im Generierungsmodus laden Sie den privaten Schlüssel sofort herunter — er wird nicht gespeichert und kann nicht wiederhergestellt werden.',
      'Der Widerruf eines Zertifikats funktioniert nur, wenn Server für die Prüfung der KRL-Datei der CA konfiguriert sind.',
    ],
  },
  helpGuides: {
    title: 'SSH-Zertifikate',
    content: `
## Übersicht

SSH-Zertifikate sind signierte öffentliche SSH-Schlüssel mit Metadaten: Identität, Gültigkeitsdauer, erlaubte Principals und Erweiterungen. Sie ersetzen den traditionellen \`authorized_keys\`-Ansatz durch zentralisierte, zeitlich begrenzte und auditierbare Zugriffskontrolle.

UCM stellt Zertifikate im OpenSSH-Format aus, die mit OpenSSH 5.4+ auf jeder Plattform kompatibel sind.

## Ausstellungsmodi

### Signaturmodus (empfohlen)
Der Benutzer generiert sein eigenes Schlüsselpaar und stellt UCM nur den **öffentlichen Schlüssel** bereit. Der private Schlüssel verlässt nie das Gerät des Benutzers.

**Benutzer-Workflow:**
\`\`\`bash
# 1. Schlüsselpaar generieren (Gerät des Benutzers)
ssh-keygen -t ed25519 -f ~/.ssh/id_work -C "jdoe@example.com"

# 2. Inhalt des öffentlichen Schlüssels kopieren
cat ~/.ssh/id_work.pub

# 3. In das Signaturformular von UCM einfügen
# 4. Das signierte Zertifikat herunterladen
# 5. Als ~/.ssh/id_work-cert.pub speichern

# 6. Verbinden
ssh -i ~/.ssh/id_work user@server
\`\`\`

### Generierungsmodus
UCM generiert sowohl das Schlüsselpaar als auch das Zertifikat. Verwenden Sie diesen Modus, wenn Sie Anmeldedaten zentral bereitstellen müssen.

> ⚠ **Laden Sie den privaten Schlüssel sofort herunter** — er wird nicht in UCM gespeichert und kann nicht wiederhergestellt werden.

**Vorgehensweise:**
1. Wählen Sie eine CA und füllen Sie die Zertifikatsdetails aus
2. Wählen Sie den Modus „Generieren"
3. Klicken Sie auf **Ausstellen**
4. Laden Sie alle drei Dateien herunter:
   - Privater Schlüssel (\`keyid\`) — **Sicher aufbewahren!**
   - Zertifikat (\`keyid-cert.pub\`)
   - Öffentlicher Schlüssel (\`keyid.pub\`)

## Zertifikatsfelder

### Key ID
Ein eindeutiger Bezeichner, der in das Zertifikat eingebettet ist. Er erscheint in den Protokollen des SSH-Servers bei Verwendung des Zertifikats und ist daher unverzichtbar für die Auditierung.

**Gute Key IDs:** \`jdoe-prod-2025\`, \`webserver-01\`, \`deploy-ci-pipeline\`

### Principals
Principals definieren, **wer** (Benutzerzertifikate) oder **was** (Host-Zertifikate) durch das Zertifikat autorisiert wird:

- **Benutzerzertifikate**: Liste der Benutzernamen, unter denen sich der Inhaber anmelden darf (z. B. \`deploy\`, \`admin\`)
- **Host-Zertifikate**: Liste der Hostnamen/IPs, unter denen der Server bekannt ist (z. B. \`web01.example.com\`, \`10.0.1.5\`)

> 💡 Werden keine Principals angegeben, gilt das Zertifikat für jeden Principal — was in der Regel zu freizügig ist.

### Gültigkeit

Wählen Sie eine Vorgabe oder legen Sie eine benutzerdefinierte Dauer fest:

| Vorgabe | Anwendungsfall |
|---------|----------------|
| 1 Stunde | CI/CD-Pipelines, einmalige Aufgaben |
| 8 Stunden | Standard-Arbeitstag |
| 24 Stunden | Erweiterter Zugang |
| 7 Tage | Sprint-basierter Zugang |
| 30 Tage | Monatliche Rotation |
| 365 Tage | Langlebige Dienstkonten |

Kurzlebige Zertifikate (8h–24h) werden für menschliche Benutzer empfohlen. Längere Gültigkeit ist für automatisierte Dienstkonten akzeptabel.

### Extensions (nur Benutzerzertifikate)

| Extension | Beschreibung |
|-----------|--------------|
| permit-pty | Interaktive Terminalsitzungen erlauben |
| permit-agent-forwarding | SSH-Agent-Weiterleitung erlauben |
| permit-X11-forwarding | X11-Display-Weiterleitung erlauben |
| permit-port-forwarding | TCP-Port-Weiterleitung erlauben |
| permit-user-rc | Ausführung von ~/.ssh/rc bei der Anmeldung erlauben |

### Critical Options

| Option | Beschreibung |
|--------|--------------|
| force-command | Beschränkt das Zertifikat auf einen einzelnen Befehl |
| source-address | Beschränkt auf bestimmte Quell-IP-Adressen/CIDRs |

**Beispiel:** Ein Zertifikat mit \`force-command=ls\` und \`source-address=10.0.0.0/8\` kann nur \`ls\` ausführen und nur aus dem 10.x.x.x-Netzwerk.

## Zertifikate verwenden

### Benutzerzertifikat
\`\`\`bash
# Zertifikat neben dem privaten Schlüssel ablegen
# Wenn der Schlüssel ~/.ssh/id_work ist, muss das Zertifikat ~/.ssh/id_work-cert.pub sein
cp downloaded-cert.pub ~/.ssh/id_work-cert.pub

# SSH verwendet das Zertifikat automatisch
ssh user@server
\`\`\`

### Host-Zertifikat
\`\`\`bash
# Auf dem Server: Host-Zertifikat ablegen
sudo cp host-cert.pub /etc/ssh/ssh_host_ed25519_key-cert.pub

# Zu sshd_config hinzufügen
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

Auf den Clients die Host CA zu known_hosts hinzufügen:
\`\`\`
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Widerruf

1. Wählen Sie ein Zertifikat in der Tabelle
2. Klicken Sie auf **Widerrufen** im Detailbereich
3. Das Zertifikat wird der Schlüsselwiderrufsliste (KRL) der CA hinzugefügt
4. Laden Sie die aktualisierte KRL herunter und verteilen Sie sie an die Server (von der Seite SSH-CAs)

> ⚠ Der Widerruf wird erst wirksam, wenn Server die KRL über \`RevokedKeys\` in sshd_config prüfen.

## Fehlerbehebung

| Problem | Lösung |
|---------|--------|
| Permission denied (publickey) | Überprüfen Sie, ob die CA auf dem Server vertrauenswürdig ist (TrustedUserCAKeys) |
| Zertifikat wird nicht verwendet | Stellen Sie sicher, dass die Zertifikatsdatei \`<Schlüssel>-cert.pub\` neben dem privaten Schlüssel heißt |
| Principal-Nichtübereinstimmung | Der SSH-Benutzername muss in den Principals des Zertifikats aufgeführt sein |
| Zertifikat abgelaufen | Stellen Sie ein neues Zertifikat mit angemessener Gültigkeit aus |
| Host-Verifizierung fehlgeschlagen | Fügen Sie die Host CA mit @cert-authority zu known_hosts hinzu |
`
  }
}
