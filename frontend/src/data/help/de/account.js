export default {
  helpContent: {
    title: 'Mein Konto',
    subtitle: 'Persönliche Einstellungen und Sicherheit',
    overview: 'Verwalten Sie Ihr Profil, Sicherheitseinstellungen und API-Schlüssel. Aktivieren Sie die Zwei-Faktor-Authentifizierung und registrieren Sie Sicherheitsschlüssel für erweiterten Kontoschutz.',
    sections: [
      {
        title: 'Profil',
        items: [
          { label: 'Vollständiger Name', text: 'Ihr Anzeigename, der in der gesamten Anwendung angezeigt wird' },
          { label: 'E-Mail', text: 'Wird für Benachrichtigungen und Kontowiederherstellung verwendet' },
          { label: 'Kontoinformationen', text: 'Erstellungsdatum, letzte Anmeldung, Gesamtanzahl der Anmeldungen' },
        ]
      },
      {
        title: 'Sicherheit',
        items: [
          { label: 'Passwort', text: 'Ändern Sie Ihr aktuelles Passwort' },
          { label: '2FA (TOTP)', text: 'Aktivieren Sie zeitbasierte Einmalpasswörter über eine Authenticator-App. Erneutes Aktivieren, solange sie aktiv ist, wird abgelehnt: deaktivieren Sie sie zuerst' },
          { label: 'Sicherheitsschlüssel', text: 'Registrieren Sie WebAuthn/FIDO2-Schlüssel (YubiKey, Fingerabdruck, usw.)' },
          { label: 'mTLS', text: 'Verwalten Sie Client-Zertifikate für die gegenseitige TLS-Authentifizierung' },
        ]
      },
      {
        title: 'API-Schlüssel',
        items: [
          { label: 'Schlüssel erstellen', text: 'Generieren Sie einen neuen API-Schlüssel mit optionalem Ablaufdatum' },
          { label: 'Berechtigungen', text: 'Ein Schlüssel trägt den bei der Erstellung gewählten Geltungsbereich, nie mehr als Ihre eigenen Berechtigungen. Ein Schlüssel kann nur einen Schlüssel erstellen oder neu erzeugen, dessen Berechtigungen er selbst besitzt' },
          { label: 'Widerrufen', text: 'Einen API-Schlüssel sofort ungültig machen' },
          { label: 'Deaktivierte Benutzer', text: 'API-Schlüssel eines deaktivierten Benutzers werden abgelehnt, selbst wenn der Schlüssel selbst noch gültig ist' },
          { label: 'Nur interaktive Sitzung', text: 'API-Schlüssel, auch mit Vollzugriff, können weder Ihr Profil, Passwort, 2FA, Sicherheitsschlüssel, mTLS-Zertifikate oder Sitzungen ändern noch über die Benutzerverwaltungsaktionen auf Ihr eigenes Konto zugreifen: melden Sie sich interaktiv an' },
        ]
      },
      {
        title: 'Einstellungen (serverseitig synchronisiert)',
        content: 'Sprache, Theme-Familie und Theme-Modus werden in der Datenbank gespeichert und folgen Ihnen über Browser und Geräte hinweg:',
        items: [
          { label: 'Gespeichert', text: 'In users.preferences (JSON). Neue Endpunkte GET/PUT /api/v2/account/preferences' },
          { label: 'Automatisch angewendet', text: '/api/v2/auth/verify gibt Ihre Einstellungen zurück, sie werden bei jedem Page-Load angewendet' },
          { label: 'Frischer Browser', text: 'Login von einem neuen Gerät oder nach dem Löschen der Site-Daten → gewählte Sprache und Theme werden wiederhergestellt' },
        ]
      },

    ],
    tips: [
      'Aktivieren Sie mindestens einen zweiten Faktor (TOTP oder Sicherheitsschlüssel) für Admin-Konten',
      'API-Schlüssel können mit einem Ablaufdatum für kurzlebige Integrationen versehen werden',
      'API-Keys können auch ohne Ablaufdatum für langlaufende Automatisierung erstellt werden',
      'Scannen Sie den QR-Code mit einer beliebigen TOTP-App: Google Authenticator, Authy, 1Password, usw.',
      'Filterauswahl auf jeder Listenseite (Zertifikate, CAs, Audit usw.) wird automatisch über Reloads hinweg gespeichert',
    ],
  },
  helpGuides: {
    title: 'Mein Konto',
    content: `
## Übersicht

Verwalten Sie Ihr persönliches Profil, Sicherheitseinstellungen und API-Schlüssel.

## Profil

- **Vollständiger Name**: Ihr Anzeigename in UCM
- **E-Mail**: Wird für Benachrichtigungen, Passwortwiederherstellung und ACME-Registrierung verwendet
- **Kontoinformationen**: Erstellungsdatum, letzter Anmeldezeitpunkt, Gesamtanzahl der Anmeldungen

## Sicherheit

### Passwortänderung
Ändern Sie Ihr aktuelles Passwort. Es muss der Systempasswortrichtlinie entsprechen (Mindestlänge, Komplexitätsanforderungen).

### Zwei-Faktor-Authentifizierung (TOTP)
Fügen Sie ein zeitbasiertes Einmalpasswort mit einer beliebigen Authenticator-App hinzu:

1. Klicken Sie auf **2FA aktivieren**
2. Scannen Sie den QR-Code mit Ihrer Authenticator-App (Google Authenticator, Authy, 1Password, usw.)
3. Geben Sie den 6-stelligen Code zur Bestätigung ein
4. Speichern Sie die **Wiederherstellungscodes**: sie werden nur einmal angezeigt

> ⚠ Wenn Sie den Zugang zu Ihrem Authenticator und den Wiederherstellungscodes verlieren, muss ein Administrator Ihre 2FA deaktivieren.

Um 2FA auf einen neuen Authenticator zu übertragen, deaktivieren Sie sie zuerst: Erneutes Aktivieren, solange sie aktiv ist, wird abgelehnt.

### Sicherheitsschlüssel (WebAuthn/FIDO2)
Registrieren Sie Hardware-Sicherheitsschlüssel oder biometrische Authentifikatoren:
- YubiKey
- Fingerabdruckleser
- Windows Hello
- Touch ID

1. Klicken Sie auf **Sicherheitsschlüssel registrieren**
2. Geben Sie einen Namen für den Schlüssel ein
3. Folgen Sie der Browseraufforderung zur Authentifizierung
4. Der Schlüssel erscheint in Ihrer Liste der registrierten Anmeldeinformationen

Ist 2FA aktiviert oder erzwungen, kann ein registrierter Schlüssel auch den zweiten Schritt einer Passwortanmeldung bestätigen: wählen Sie **Sicherheitsschlüssel verwenden**.

Ohne Authentifizierungs-App aktivieren Sie im Abschnitt Zwei-Faktor-Authentifizierung **Sicherheitsschlüssel als zweiter Faktor**: Jede Anmeldung mit Passwort verlangt dann einen Ihrer Schlüssel, und der letzte Schlüssel kann nicht entfernt werden, solange die Option aktiv ist.

### mTLS-Zertifikate
Verwalten Sie Client-Zertifikate für die gegenseitige TLS-Authentifizierung:
- Laden Sie ein Client-Zertifikat hoch
- Laden Sie Ihre registrierten Zertifikate herunter
- Löschen Sie alte Zertifikate

## API-Schlüssel

### API-Schlüssel erstellen
1. Klicken Sie auf **API-Schlüssel erstellen**
2. Geben Sie einen **Namen** ein (beschreibend, z.B. „CI/CD-Pipeline")
3. Setzen Sie optional ein **Ablaufdatum**
4. Klicken Sie auf **Erstellen**
5. Kopieren Sie den Schlüssel sofort: er wird nur einmal angezeigt

### API-Schlüssel verwenden
Fügen Sie den Schlüssel im \`X-API-Key\`-Header ein:

\`\`\`
X-API-Key: <ihr-api-schlüssel>
\`\`\`

Oder senden Sie ihn als Bearer-Token: \`Authorization: Bearer <ihr-api-schlüssel>\`.

### Berechtigungen
Jeder Schlüssel trägt den bei der Erstellung gewählten Geltungsbereich (**Vollzugriff**, **Nur Lesen**, **Lesen & Schreiben**, **Nur Zertifikate**) und nie mehr Zugriff als Ihr Konto. Ein Schlüssel kann nur einen Schlüssel erstellen oder neu erzeugen, dessen Berechtigungen er selbst besitzt.

API-Schlüssel, auch mit Vollzugriff, können weder Ihr Profil, Passwort, 2FA, Sicherheitsschlüssel, mTLS-Zertifikate oder Sitzungen ändern noch über die Benutzerverwaltungsaktionen auf Ihr eigenes Konto zugreifen: dafür ist eine interaktive Sitzung nötig.

### Schlüssel widerrufen
Klicken Sie auf **Löschen**, um einen API-Schlüssel sofort ungültig zu machen. Aktive Sitzungen, die den Schlüssel verwenden, werden beendet.

> 💡 Verwenden Sie kurzlebige API-Schlüssel mit Ablaufdatum für CI/CD und Automatisierung.
`
  }
}
