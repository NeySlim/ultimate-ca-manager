export default {
  helpContent: {
    title: 'Sicherheitseinstellungen',
    subtitle: 'Authentifizierung und Zugriffsrichtlinien',
    overview: 'Konfigurieren Sie Passwortrichtlinien, Sitzungsverwaltung, Ratenbegrenzung und Netzwerksicherheit. Diese Einstellungen gelten systemweit und betreffen alle Benutzerkonten.',
    sections: [
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
    ],
    tips: [
      'Aktivieren Sie die Ratenbegrenzung zum Schutz vor automatisierten Angriffswerkzeugen',
      'Verwenden Sie IP-Einschränkungen, um den Admin-Zugriff auf vertrauenswürdige Netzwerke zu beschränken',
    ],
    warnings: [
      'Zu strenge Passwortrichtlinien können Benutzer frustrieren',
      'Stellen Sie immer sicher, dass mindestens ein Admin auf das System zugreifen kann, bevor Sie IP-Einschränkungen aktivieren',
    ],
  },
  helpGuides: {
    title: 'Sicherheitseinstellungen',
    content: `
## Übersicht

Systemweite Sicherheitskonfiguration, die alle Benutzerkonten und Zugriffsmuster betrifft.

## Passwortrichtlinie

### Komplexitätsanforderungen
- **Mindestlänge** — 8 bis 32 Zeichen
- **Großbuchstaben erforderlich** — Mindestens ein Großbuchstabe
- **Kleinbuchstaben erforderlich** — Mindestens ein Kleinbuchstabe
- **Zahlen erforderlich** — Mindestens eine Ziffer
- **Sonderzeichen erforderlich** — Mindestens ein Symbol

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
Verlangt von allen Benutzern, 2FA zu aktivieren. Benutzer, die 2FA nicht eingerichtet haben, werden bei der nächsten Anmeldung dazu aufgefordert.

### Unterstützte Methoden
- **TOTP** — Zeitbasierte Einmalpasswörter (Authenticator-Apps)
- **WebAuthn** — Hardware-Sicherheitsschlüssel und Biometrie

> 💡 Erzwingen Sie 2FA mindestens für Admin-Konten. Erwägen Sie die Durchsetzung für alle Benutzer in sicherheitskritischen Umgebungen.
`
  }
}
