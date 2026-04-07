export default {
  helpContent: {
    title: 'Benutzer & Gruppen',
    subtitle: 'Identitäts- und Zugriffsverwaltung',
    overview: 'Verwalten Sie Benutzerkonten und Gruppenmitgliedschaften. Weisen Sie Rollen zu, um den Zugriff auf UCM-Funktionen zu steuern. Gruppen ermöglichen die Massenverwaltung von Berechtigungen für Teams.',
    sections: [
      {
        title: 'Benutzer',
        items: [
          { label: 'Benutzer erstellen', text: 'Einen neuen Benutzer mit Benutzername, E-Mail und Erstpasswort hinzufügen' },
          { label: 'Rollen', text: 'System- oder benutzerdefinierte Rollen zur Steuerung der Berechtigungen zuweisen' },
          { label: 'Status', text: 'Benutzerkonten aktivieren oder deaktivieren' },
          { label: 'Passwort zurücksetzen', text: 'Passwort eines Benutzers zurücksetzen (Admin-Aktion)' },
          { label: 'API-Schlüssel', text: 'Pro-Benutzer-API-Schlüssel für programmatischen Zugriff verwalten' },
        ]
      },
      {
        title: 'Gruppen',
        items: [
          { label: 'Gruppe erstellen', text: 'Eine Gruppe definieren und Mitglieder zuweisen' },
          { label: 'Rollenvererbung', text: 'Gruppen können Rollen erben — alle Mitglieder erhalten Gruppenberechtigungen' },
          { label: 'Mitgliederverwaltung', text: 'Benutzer zu Gruppen hinzufügen oder daraus entfernen' },
        ]
      },
    ],
    tips: [
      'Verwenden Sie Gruppen zur Berechtigungsverwaltung für Teams anstelle einzelner Benutzer',
      'Deaktivierte Benutzer können sich nicht anmelden, aber ihre Daten bleiben erhalten',
    ],
    warnings: [
      'Das Löschen eines Benutzers ist dauerhaft — erwägen Sie stattdessen die Deaktivierung',
    ],
  },
  helpGuides: {
    title: 'Benutzer & Gruppen',
    content: `
## Übersicht

Verwalten Sie Benutzerkonten, Gruppen und Rollenzuweisungen. Benutzer authentifizieren sich bei UCM über Passwort, SSO, WebAuthn oder mTLS. Gruppen ermöglichen die Massenverwaltung von Berechtigungen.

## Benutzer-Tab

### Benutzer erstellen
1. Klicken Sie auf **Benutzer erstellen**
2. Geben Sie einen **Benutzernamen** ein (eindeutig, kann später nicht geändert werden)
3. Geben Sie eine **E-Mail** ein (wird für Benachrichtigungen und Wiederherstellung verwendet)
4. Legen Sie ein **Erstpasswort** fest
5. Wählen Sie eine **Rolle** (Admin, Operator, Auditor, Viewer oder benutzerdefiniert)
6. Klicken Sie auf **Erstellen**

### Benutzerstatus
- **Aktiv** — Kann sich anmelden und Aktionen durchführen
- **Deaktiviert** — Kann sich nicht anmelden, Daten bleiben erhalten

Schalten Sie den Status eines Benutzers um, ohne sein Konto zu löschen.

### Passwort zurücksetzen
Administratoren können das Passwort jedes Benutzers zurücksetzen. Der Benutzer wird bei der nächsten Anmeldung zur Änderung aufgefordert.

### API-Schlüssel
Jeder Benutzer kann mehrere API-Schlüssel für programmatischen Zugriff haben. API-Schlüssel erben die Berechtigungen der Benutzerrolle. Weitere Informationen zur Verwaltung eigener Schlüssel finden Sie auf der Kontoseite.

## Gruppen-Tab

### Gruppe erstellen
1. Klicken Sie auf **Gruppe erstellen**
2. Geben Sie einen **Namen** und eine optionale Beschreibung ein
3. Weisen Sie eine **Rolle** zu (Gruppenmitglieder erben diese Rolle)
4. Klicken Sie auf **Erstellen**

### Mitglieder verwalten
- Klicken Sie auf eine Gruppe, um ihre Mitglieder zu sehen
- Verwenden Sie das **Transfer-Panel**, um Benutzer hinzuzufügen/zu entfernen
- Benutzer können mehreren Gruppen angehören

### Rollenvererbung
Die effektiven Berechtigungen eines Benutzers sind die **Vereinigung** von:
- Ihrer direkt zugewiesenen Rolle
- Allen Rollen aus Gruppen, denen sie angehören

## Rollen

### Systemrollen
- **Admin** — Vollständiger Zugriff auf alle Funktionen
- **Operator** — Kann Zertifikate, CAs, CSRs verwalten, aber keine Systemeinstellungen
- **Auditor** — Nur-Lese-Zugriff auf alle Betriebsdaten für Compliance und Audit
- **Viewer** — Nur-Lese-Zugriff auf Zertifikate, CAs und Templates

### Benutzerdefinierte Rollen
Erstellen Sie Rollen mit granularen Berechtigungen auf der **RBAC**-Seite.

> 💡 Verwenden Sie Gruppen zur Verwaltung von Team-Berechtigungen anstelle der Zuweisung von Rollen an einzelne Benutzer.
`
  }
}
