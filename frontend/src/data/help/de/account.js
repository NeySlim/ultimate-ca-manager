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
          { label: '2FA (TOTP)', text: 'Aktivieren Sie zeitbasierte Einmalpasswörter über eine Authenticator-App' },
          { label: 'Sicherheitsschlüssel', text: 'Registrieren Sie WebAuthn/FIDO2-Schlüssel (YubiKey, Fingerabdruck, usw.)' },
          { label: 'mTLS', text: 'Verwalten Sie Client-Zertifikate für die gegenseitige TLS-Authentifizierung' },
        ]
      },
      {
        title: 'API-Schlüssel',
        items: [
          { label: 'Schlüssel erstellen', text: 'Generieren Sie einen neuen API-Schlüssel mit optionalem Ablaufdatum' },
          { label: 'Berechtigungen', text: 'API-Schlüssel erben die Berechtigungen Ihrer Rolle' },
          { label: 'Widerrufen', text: 'Einen API-Schlüssel sofort ungültig machen' },
        ]
      },
    ],
    tips: [
      'Aktivieren Sie mindestens einen zweiten Faktor (TOTP oder Sicherheitsschlüssel) für Admin-Konten',
      'API-Schlüssel können mit einem Ablaufdatum für kurzlebige Integrationen versehen werden',
      'Scannen Sie den QR-Code mit einer beliebigen TOTP-App: Google Authenticator, Authy, 1Password, usw.',
    ],
  },
  helpGuides: {
    title: 'Mein Konto',
    content: `
## Übersicht

Verwalten Sie Ihr persönliches Profil, Sicherheitseinstellungen und API-Schlüssel.

## Profil

- **Vollständiger Name** — Ihr Anzeigename in UCM
- **E-Mail** — Wird für Benachrichtigungen, Passwortwiederherstellung und ACME-Registrierung verwendet
- **Kontoinformationen** — Erstellungsdatum, letzter Anmeldezeitpunkt, Gesamtanzahl der Anmeldungen

## Sicherheit

### Passwortänderung
Ändern Sie Ihr aktuelles Passwort. Es muss der Systempasswortrichtlinie entsprechen (Mindestlänge, Komplexitätsanforderungen).

### Zwei-Faktor-Authentifizierung (TOTP)
Fügen Sie ein zeitbasiertes Einmalpasswort mit einer beliebigen Authenticator-App hinzu:

1. Klicken Sie auf **2FA aktivieren**
2. Scannen Sie den QR-Code mit Ihrer Authenticator-App (Google Authenticator, Authy, 1Password, usw.)
3. Geben Sie den 6-stelligen Code zur Bestätigung ein
4. Speichern Sie die **Wiederherstellungscodes** — sie werden nur einmal angezeigt

> ⚠ Wenn Sie den Zugang zu Ihrem Authenticator und den Wiederherstellungscodes verlieren, muss ein Administrator Ihre 2FA deaktivieren.

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
5. Kopieren Sie den Schlüssel sofort — er wird nur einmal angezeigt

### API-Schlüssel verwenden
Fügen Sie den Schlüssel im \`X-API-Key\`-Header ein:

\`\`\`
X-API-Key: <ihr-api-schlüssel>
\`\`\`

### Berechtigungen
API-Schlüssel erben die Berechtigungen Ihrer Benutzerrolle. Sie können nicht mehr Zugriff haben als Ihr Konto.

### Schlüssel widerrufen
Klicken Sie auf **Löschen**, um einen API-Schlüssel sofort ungültig zu machen. Aktive Sitzungen, die den Schlüssel verwenden, werden beendet.

> 💡 Verwenden Sie kurzlebige API-Schlüssel mit Ablaufdatum für CI/CD und Automatisierung.
`
  }
}
