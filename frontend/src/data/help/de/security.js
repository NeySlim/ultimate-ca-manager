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
          { label: 'IP-Einschränkungen', text: 'Zugriff von bestimmten IP-Bereichen erlauben oder verweigern' },
          { label: '2FA-Durchsetzung', text: 'Zwei-Faktor-Authentifizierung für alle Benutzer erfordern' },
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
      'Verwenden Sie IP-Einschränkungen, um den Admin-Zugriff auf vertrauenswürdige Netzwerke zu beschränken',
    ],
    warnings: [
      'Zu strenge Passwortrichtlinien können Benutzer frustrieren',
      'Stellen Sie immer sicher, dass mindestens ein Admin auf das System zugreifen kann, bevor Sie IP-Einschränkungen aktivieren',
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

## IP-Einschränkungen

### Erlaubnisliste
Nur Verbindungen von angegebenen IPs oder CIDR-Bereichen erlauben. Alle anderen IPs werden blockiert.

### Sperrliste
Bestimmte IPs oder CIDR-Bereiche blockieren. Alle anderen IPs sind erlaubt.

> ⚠ Seien Sie äußerst vorsichtig mit IP-Einschränkungen. Fehlkonfigurationen können alle Benutzer, einschließlich Administratoren, aussperren. Testen Sie immer zuerst mit einer einzelnen IP.

## Zwei-Faktor-Authentifizierung

### Durchsetzung
Verlangt von allen Benutzern, 2FA zu aktivieren. Benutzer, die 2FA nicht eingerichtet haben, werden bei der nächsten Anmeldung dazu aufgefordert. Ein Benutzer mit registriertem Sicherheitsschlüssel bestätigt damit, statt TOTP einzurichten.

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
