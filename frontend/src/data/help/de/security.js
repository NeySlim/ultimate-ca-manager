export default {
  helpContent: {
    title: 'Sicherheitseinstellungen',
    subtitle: 'Authentifizierung und Zugriffsrichtlinien',
    overview: 'Konfigurieren Sie Passwortrichtlinien, Sitzungsverwaltung, Ratenbegrenzung und Netzwerksicherheit. Diese Einstellungen gelten systemweit und betreffen alle Benutzerkonten.',
    sections: [
      {
        title: 'Verschlüsselung privater Schlüssel',
        items: [
          { label: 'Status & Zähler', text: 'Zeigt, ob die Verschlüsselung aktiviert ist und wie viele gespeicherte private Schlüssel verschlüsselt bzw. unverschlüsselt sind' },
          { label: 'Aktivieren / Deaktivieren', text: 'Alle privaten Schlüssel mit AES-256 verschlüsseln. Beim Aktivieren werden Klartext-Schlüsselkopien entfernt, beim Deaktivieren neu erstellt' },
          { label: 'Schlüsseldateien auf dem Datenträger', text: 'Zeigt die verbleibenden Klartext-Schlüsselkopien; verwenden Sie Deploy-Hooks, wenn ein anderer Dienst eine Schlüsseldatei benötigt' },
          { label: 'UCM_REQUIRE_DB_ENCRYPTION_KEY', text: 'Opt-in-Umgebungsvariable: Start ohne expliziten Datenbank-Verschlüsselungsschlüssel verweigern' },
          { label: 'UCM_REQUIRE_KEY_ENCRYPTION', text: 'Opt-in-Umgebungsvariable: Start verweigern, solange die Verschlüsselung privater Schlüssel nicht aktiviert ist' },
        ]
      },
      {
        title: 'Passwortrichtlinie',
        items: [
          { label: 'Mindestlänge', text: 'Mindestanzahl erforderlicher Zeichen' },
          { label: 'Komplexität', text: 'Großbuchstaben, Kleinbuchstaben, Zahlen, Sonderzeichen erfordern' },
          { label: 'Ablauf', text: 'Passwortänderung nach einer bestimmten Anzahl von Tagen erzwingen' },
          { label: 'Verlauf', text: 'Wiederverwendung früherer Passwörter verhindern' },
        ]
      },
      {
        title: 'Sitzung & Zugriff',
        items: [
          { label: 'Sitzungszeitlimit', text: 'Automatische Abmeldung nach Inaktivitätszeitraum' },
          { label: 'Ratenbegrenzung', text: 'Anmeldeversuche begrenzen, um Brute-Force-Angriffe zu verhindern' },
          { label: 'Admin-Zugriffs-Allowlist', text: 'Die Weboberfläche und die Management-API auf aufgelistete IP-Adressen und Netzwerke beschränken' },
          { label: '2FA-Durchsetzung', text: 'Zwei-Faktor-Authentifizierung für alle Benutzer erfordern' },
        ]
      },
      {
        title: 'Admin-Zugriffs-Allowlist',
        items: [
          { label: 'Netzwerke', text: 'Eine IPv4- oder IPv6-Adresse bzw. ein CIDR-Netzwerk pro Zeile, höchstens 100. Leer bedeutet keine Einschränkung. IPv4 und IPv6 werden getrennt aufgelistet: 0.0.0.0/0 lässt keinen IPv6-Client zu, ebenso wenig ::/0 einen IPv4-Client' },
          { label: 'Was blockiert wird', text: 'Von anderen Adressen antworten die Weboberfläche, die Anmeldung, die /api/v2-API (einschließlich API-Schlüssel) und der WebSocket-Kanal mit 403' },
          { label: 'Immer erreichbar', text: 'ACME, SCEP, EST, OCSP, CRL/AIA, TSA, XCEP/WSTEP, das SSH-Setup-Skript und die Health-Endpunkte' },
          { label: 'Ihre Adresse', text: 'Der Bereich zeigt die Adresse, unter der der Server Sie sieht; eine Liste, die sie nicht enthält, wird abgelehnt' },
          { label: 'UCM_ADMIN_ALLOWED_NETWORKS', text: 'Umgebungsvariable (kommagetrennt), die Vorrang vor der Einstellung hat und sie schreibgeschützt macht' },
          { label: 'UCM_ADMIN_ALLOWLIST_DISABLE', text: 'Auf 1 setzen und neu starten, um die Prüfung nach einer Aussperrung zu deaktivieren' },
        ]
      },
      {
        title: 'mTLS-Authentifizierung',
        items: [
          { label: 'Vertrauenswürdige CA', text: 'Die CA auswählen, die mTLS-Client-Anmeldezertifikate ausstellt und validiert' },
          { label: 'Client-Zertifikat erfordern', text: 'mTLS optional für die Web-UI verpflichtend machen, das Ändern der mTLS-Einstellungen erfordert einen Dienstneustart' },
        ]
      },
    ],
    tips: [
      'Aktivieren Sie die Ratenbegrenzung zum Schutz vor automatisierten Angriffswerkzeugen',
      'Verwenden Sie die Admin-Zugriffs-Allowlist, um die Weboberfläche auf Ihr Management-VLAN, Ihren Bastion-Host oder Ihr VPN zu beschränken',
    ],
    warnings: [
      'Zu strenge Passwortrichtlinien können Benutzer frustrieren',
      'Hinter einem Reverse-Proxy müssen Sie UCM_BEHIND_PROXY und UCM_TRUSTED_PROXIES setzen, bevor Sie die Admin-Zugriffs-Allowlist verwenden, sonst scheint jede Anfrage vom Proxy zu kommen',
      'Sicherheitskritische Einstellungen (Sitzung, Sperrung, HSTS, öffentliche URL, Passwortrichtlinie) erfordern admin:settings, die Felder sind für Operatoren gesperrt',
    ],
  },
  helpGuides: {
    title: 'Sicherheitseinstellungen',
    content: `
## Übersicht

Systemweite Sicherheitskonfiguration, die alle Benutzerkonten und Zugriffsmuster betrifft.

## Verschlüsselung privater Schlüssel

Alle in der Datenbank gespeicherten privaten Schlüssel von CAs und Zertifikaten mit AES-256 verschlüsseln, geschützt durch eine außerhalb der Datenbank aufbewahrte Master-Key-Datei.

- **Status und Zähler**: Der Bereich zeigt, ob die Verschlüsselung aktiviert ist und wie viele Schlüssel derzeit **verschlüsselt** bzw. **unverschlüsselt** sind
- **Verschlüsselung aktivieren**: Erzeugt die Master-Key-Datei und verschlüsselt alle gespeicherten privaten Schlüssel. Sichern Sie die Schlüsseldatei sofort: Ohne sie sind verschlüsselte Schlüssel unwiederbringlich verloren
- **Verschlüsselung deaktivieren**: Entschlüsselt alle privaten Schlüssel zurück in die Klartextspeicherung (Bestätigung erforderlich)

### Durchsetzung beim Start

Ohne konfigurierten Verschlüsselungsschlüssel protokolliert UCM beim Start eine Warnung, läuft aber weiter. Zwei **Opt-in-Umgebungsvariablen** machen daraus einen harten Fehler:

- \`UCM_REQUIRE_DB_ENCRYPTION_KEY\`: Start ohne expliziten Datenbank-Verschlüsselungsschlüssel verweigern (andernfalls greifen Integrationsgeheimnisse auf einen aus der Maschinen-ID abgeleiteten Schlüssel zurück)
- \`UCM_REQUIRE_KEY_ENCRYPTION\`: Start verweigern, solange die Verschlüsselung privater Schlüssel nicht aktiviert ist

Beide akzeptieren \`1\`/\`true\`/\`yes\`/\`on\`. Ein ungültiger Schlüssel wird als fataler Fehler behandelt, statt stillschweigend auf Klartext zurückzufallen.

## Passwortrichtlinie

### Komplexitätsanforderungen
- **Mindestlänge**: 8 bis 32 Zeichen
- **Großbuchstaben erforderlich**: Mindestens ein Großbuchstabe
- **Kleinbuchstaben erforderlich**: Mindestens ein Kleinbuchstabe
- **Zahlen erforderlich**: Mindestens eine Ziffer
- **Sonderzeichen erforderlich**: Mindestens ein Symbol

### Passwortablauf
Erzwingt, dass Benutzer ihr Passwort nach einer bestimmten Anzahl von Tagen ändern. Auf 0 setzen, um zu deaktivieren.

### Passwortverlauf
Verhindert die Wiederverwendung der letzten N Passwörter. Benutzer können kein Passwort festlegen, das einem ihrer vorherigen N Passwörter entspricht.

## Sitzungsverwaltung

### Sitzungszeitlimit
Meldet Benutzer nach N Minuten Inaktivität automatisch ab. Gilt nur für Web-UI-Sitzungen, nicht für API-Schlüssel.

### Gleichzeitige Sitzungen
Begrenzt die Anzahl gleichzeitiger Sitzungen pro Benutzer. Zusätzliche Anmeldungen beenden die älteste Sitzung.

## Ratenbegrenzung

### Anmeldeversuche
Begrenzt fehlgeschlagene Anmeldeversuche pro IP-Adresse innerhalb eines Zeitfensters. Nach Überschreitung des Limits wird die IP vorübergehend gesperrt.

### Sperrdauer
Wie lange eine IP nach Überschreitung des Anmeldeversuchslimits gesperrt wird.

## Admin-Zugriffs-Allowlist

Beschränkt die Weboberfläche und die Management-API auf eine Liste von IP-Adressen und CIDR-Netzwerken, IPv4 oder IPv6, eine pro Zeile (höchstens 100). Eine leere Liste schränkt nichts ein. IPv4 und IPv6 werden getrennt aufgelistet: \`0.0.0.0/0\` lässt keinen IPv6-Client zu, und \`::/0\` lässt keinen IPv4-Client zu.

- **Von anderen Adressen blockiert**: Die Weboberfläche samt Ressourcen, die Anmeldung, jeder \`/api/v2\`-Aufruf (einschließlich API-Schlüssel) und der WebSocket-Kanal antworten mit **403**
- **Immer erreichbar**: ACME und der ACME-Proxy, SCEP, EST, OCSP, CRL und AIA, TSA, XCEP/WSTEP, das SSH-Setup-Skript sowie die Health- und Metrik-Endpunkte, damit Geräte und Überwachung weiter funktionieren
- **Ihre Adresse**: Der Bereich zeigt die Adresse, unter der der Server Sie sieht. Eine Liste, die sie nicht enthält, wird abgelehnt, sodass Sie sich beim Speichern nicht aussperren können
- **Audit**: Jede Änderung der Liste wird im Audit-Log protokolliert

### Umgebungsvariablen
- \`UCM_ADMIN_ALLOWED_NETWORKS\`: kommagetrennte Liste, die Vorrang vor der Einstellung hat und das Feld schreibgeschützt macht
- \`UCM_ADMIN_ALLOWLIST_DISABLE=1\`: deaktiviert die Prüfung nach einem Neustart; damit stellen Sie den Zugriff nach einer Aussperrung wieder her und entfernen die Variable danach

### Reverse-Proxy, Docker und Kubernetes
Hinter einem Reverse-Proxy setzen Sie \`UCM_BEHIND_PROXY=1\` und tragen den Proxy in \`UCM_TRUSTED_PROXIES\` ein, sonst scheint jede Anfrage vom Proxy zu kommen. Mit Docker im Bridge-Modus und ohne Proxy kann die gesehene Adresse die nach dem NAT von Docker sein: Prüfen Sie die angezeigte Adresse vor dem Speichern.

> ⚠ Dieser Filter arbeitet auf Anwendungsebene. Halten Sie zusätzlich eine Firewall vor dem HTTPS-Port vor.

## Zwei-Faktor-Authentifizierung

### Durchsetzung
Verlangt von allen Benutzern, 2FA zu aktivieren. Benutzer, die 2FA nicht eingerichtet haben, werden bei der nächsten Anmeldung dazu aufgefordert. Eine TOTP-App oder ein registrierter Sicherheitsschlüssel erfüllt sie, bei der Einrichtung wie bei der Anmeldung. Solange sie erzwungen wird, lässt sich TOTP nur deaktivieren, wenn ein Sicherheitsschlüssel bleibt, und der letzte Schlüssel nur entfernen, wenn TOTP bleibt. Ein Benutzer, dessen Schlüssel zum zweiten Faktor geworden ist, behält ihn, wenn die Erzwingung aufgehoben wird.

### Unterstützte Methoden
- **TOTP**: Zeitbasierte Einmalpasswörter (Authenticator-Apps)
- **WebAuthn**: Hardware-Sicherheitsschlüssel und Biometrie

> 💡 Erzwingen Sie 2FA mindestens für Admin-Konten. Erwägen Sie die Durchsetzung für alle Benutzer in sicherheitskritischen Umgebungen.

## mTLS-Authentifizierung

Benutzer können sich mit einem Client-Zertifikat statt mit einem Passwort anmelden:

- **Vertrauenswürdige CA**: Die CA auswählen, die mTLS-Client-Zertifikate ausstellt und validiert
- **Client-Zertifikat erfordern**: mTLS optional für die Web-UI verpflichtend machen
- Das Ändern der mTLS-Einstellungen erfordert einen Dienstneustart

## Erforderliche Berechtigungen

Sicherheitskritische Einstellungen. Sitzung, Sperrung, HSTS, öffentliche URL und Passwortrichtlinie: erfordern die Berechtigung **admin:settings**. Für Operatoren (nur write:settings) werden diese Felder gesperrt angezeigt; der Rest der Karte lässt sich weiterhin normal speichern.
`
  }
}
