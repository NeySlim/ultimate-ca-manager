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
          { label: 'Erster Start', text: 'Ohne Hauptschlüssel erzeugt UCM beim Start /etc/ucm/master.key (0600) und verschlüsselt die bereits gespeicherten Schlüssel. Ein Container tut dies nur, wenn /etc/ucm ein benanntes Volume oder ein Host-Verzeichnis ist. Übersprungen mit gesetztem KEY_ENCRYPTION_KEY, mit bereits verschlüsselten Schlüsseln oder einer verschlüsselten Audit-Kette in der Datenbank, nachdem die Verschlüsselung hier deaktiviert wurde, oder mit UCM_AUTO_MASTER_KEY=false. Bei jedem Start verschlüsselt ein geladener Schlüssel auch die noch unverschlüsselt gespeicherten Werte, und ein Schlüssel, der sie nicht entschlüsselt, versetzt UCM in den abgesicherten Modus. Sichern Sie die Schlüsseldatei' },
          { label: 'Schlüsseldateien auf dem Datenträger', text: 'Zeigt die verbleibenden Klartext-Schlüsselkopien; verwenden Sie Deploy-Hooks, wenn ein anderer Dienst eine Schlüsseldatei benötigt' },
          { label: 'UCM_REQUIRE_DB_ENCRYPTION_KEY', text: 'Opt-in-Umgebungsvariable: Start ohne expliziten Datenbank-Verschlüsselungsschlüssel verweigern' },
          { label: 'UCM_REQUIRE_KEY_ENCRYPTION', text: 'Opt-in-Umgebungsvariable: Start verweigern, solange die Verschlüsselung privater Schlüssel nicht aktiviert ist' },
          { label: 'Verbleibende Schlüssel verschlüsseln', text: 'Wird angezeigt, solange die Verschlüsselung aktiviert ist und einige Schlüssel oder Geheimnisse noch unverschlüsselt gespeichert sind: verschlüsselt sie und lässt bereits verschlüsselte unverändert' },
        ]
      },
      {
        title: 'Passwortrichtlinie',
        items: [
          { label: 'Mindestlänge', text: 'Mindestanzahl erforderlicher Zeichen, 6 bis 32' },
          { label: 'Komplexität', text: 'Großbuchstaben, Zahlen und Sonderzeichen erfordern, jeweils einzeln schaltbar' },
        ]
      },
      {
        title: 'Sitzung & Zugriff',
        items: [
          { label: 'Sitzungszeitlimit', text: 'Automatische Abmeldung nach Inaktivitätszeitraum (Einstellungen › Allgemein)' },
          { label: 'Sitzungsdauer', text: 'Maximale Sitzungslänge in Stunden, unabhängig von der Aktivität' },
          { label: 'Kontosperre', text: 'Max. Anmeldeversuche und Sperrdauer (Einstellungen › Allgemein) sperren ein Konto nach wiederholten Fehlschlägen. Anfragelimits pro IP werden über die Umgebungsvariablen RATE_LIMIT_* gesetzt, nicht auf dieser Seite' },
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
          { label: 'Vertrauenswürdige CA', text: 'Die CA, deren Client-Zertifikate bei der Anmeldung akzeptiert werden, und der Standardaussteller, wenn ein Benutzer eines erzeugt. Jede CA mit nicht widerrufenem Zertifikat kann gewählt werden, auch schlüssellose oder Offline-CAs: Eine solche CA stellt nichts aus, ihre Benutzer laden daher anderswo ausgestellte Zertifikate hoch (v2.248)' },
          { label: 'Client-Zertifikat erfordern', text: 'mTLS optional für die Web-UI verpflichtend machen, das Ändern der mTLS-Einstellungen erfordert einen Dienstneustart' },
          { label: 'Gleiche Seriennummer, andere CA (v2.251)', text: 'Eine Registrierung wird über Aussteller und Seriennummer identifiziert, sodass ein Client-Zertifikat registriert, importiert oder zugewiesen werden kann, wenn das registrierte Zertifikat einer anderen CA dieselbe Seriennummer hat' },
          { label: 'Reverse-Proxy-Header (v2.252)', text: 'Hinter einem Proxy, der das Client-Zertifikat als Header weiterleitet, senden Sie den Aussteller-DN (X-SSL-Client-I-DN) mit der Seriennummer, als Hexadezimalwert gelesen, oder das Zertifikat selbst (X-SSL-Client-Cert). Eine Seriennummer ohne ihren Aussteller öffnet keine Registrierung, die einen erfasst hat, und ein vorgelegtes Zertifikat lässt sich ohne ihn nicht registrieren' },
          { label: 'Widerrufener Aussteller', text: 'Ein Client-Zertifikat, das unter einer widerrufenen CA ausgestellt wurde, auf jeder Ebene seiner Kette, eröffnet keine Sitzung und kann weder registriert noch importiert werden (v2.252)' },
          { label: 'Erzeugte Schlüssel (v2.251)', text: 'Ein von UCM erzeugtes mTLS-Benutzerzertifikat erhält einen Schlüssel in der Stärke der ausstellenden CA, RSA oder eine NIST-Kurve, die Browser akzeptieren, auf den nächstliegenden von den Richtlinien erlaubten Typ verschoben, statt immer RSA-2048' },
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
- **Verbleibende Schlüssel verschlüsseln**: Wird angezeigt, solange die Verschlüsselung aktiviert ist und einige Schlüssel oder Geheimnisse noch unverschlüsselt gespeichert sind; verschlüsselt sie und lässt bereits verschlüsselte unverändert

### Durchsetzung beim Start

Ohne konfigurierten Verschlüsselungsschlüssel protokolliert UCM beim Start eine Warnung, läuft aber weiter. Zwei **Opt-in-Umgebungsvariablen** machen daraus einen harten Fehler:

- \`UCM_REQUIRE_DB_ENCRYPTION_KEY\`: Start ohne expliziten Datenbank-Verschlüsselungsschlüssel verweigern (andernfalls greifen Integrationsgeheimnisse auf einen aus der Maschinen-ID abgeleiteten Schlüssel zurück)
- \`UCM_REQUIRE_KEY_ENCRYPTION\`: Start verweigern, solange die Verschlüsselung privater Schlüssel nicht aktiviert ist

Beide akzeptieren \`1\`/\`true\`/\`yes\`/\`on\`. Ein ungültiger Schlüssel wird als fataler Fehler behandelt, statt stillschweigend auf Klartext zurückzufallen.

## Passwortrichtlinie

### Komplexitätsanforderungen
- **Mindestlänge**: 6 bis 32 Zeichen (standardmäßig 8)
- **Großbuchstaben erforderlich**: Mindestens ein Großbuchstabe
- **Zahlen erforderlich**: Mindestens eine Ziffer
- **Sonderzeichen erforderlich**: Mindestens ein Symbol

UCM hat weder Passwortablauf noch Passwortverlauf als Einstellung.

## Sitzungsverwaltung

### Sitzungszeitlimit
Unter **Einstellungen › Allgemein**: Meldet Benutzer nach N Minuten Inaktivität automatisch ab. Gilt nur für Web-UI-Sitzungen, nicht für API-Schlüssel.

### Sitzungsdauer
Maximale Sitzungslänge in Stunden, unabhängig von der Aktivität. Die Zahl gleichzeitiger Sitzungen pro Benutzer ist nicht begrenzt.

## Anmeldeschutz

### Max. Anmeldeversuche
Unter **Einstellungen › Allgemein**: die Zahl fehlgeschlagener Anmeldungen, nach der das **Konto** gesperrt wird.

### Sperrdauer
Wie lange das Konto gesperrt bleibt, in Minuten.
Ein gesperrtes Konto beantwortet eine Passwort- oder LDAP-Anmeldung bis zum Ende der Sperre mit demselben „Invalid credentials“ wie ein unbekannter Name, sodass die Antwort nicht verrät, dass das Konto existiert; die Sperre wird im Audit-Protokoll erfasst.

### Anfrage-Ratenlimits
Anfragen werden zusätzlich pro Client-IP-Adresse durch die Umgebungsvariablen \`RATE_LIMIT_*\` begrenzt (Buckets für Authentifizierung, aufwendige Anfragen, Standard und Protokolle; Clients aus privaten Netzen ausgenommen mit \`RATE_LIMIT_TRUST_LAN\`). Die Anmelderouten haben ein eigenes Limit, 5 Versuche pro Minute, das die 429-Antwort mit \`Retry-After\` nennt.

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

- **Vertrauenswürdige CA**: Die CA, deren Client-Zertifikate bei der Anmeldung akzeptiert werden, und der Standardaussteller, wenn ein Benutzer eines erzeugt. Jede CA mit nicht widerrufenem Zertifikat kann gewählt werden, auch schlüssellose oder Offline-CAs: Eine solche CA stellt nichts aus, ihre Benutzer laden daher anderswo ausgestellte Zertifikate hoch (v2.248)
- **Client-Zertifikat erfordern**: mTLS optional für die Web-UI verpflichtend machen
- Das Ändern der mTLS-Einstellungen erfordert einen Dienstneustart

## Erforderliche Berechtigungen

Sicherheitskritische Einstellungen. Sitzung, Sperrung, HSTS, öffentliche URL und Passwortrichtlinie: erfordern die Berechtigung **admin:settings**. Für Operatoren (nur write:settings) werden diese Felder gesperrt angezeigt; der Rest der Karte lässt sich weiterhin normal speichern.
`
  }
}
