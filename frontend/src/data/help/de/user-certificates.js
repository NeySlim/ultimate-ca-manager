export default {
  helpContent: {
    title: 'Benutzerzertifikate',
    subtitle: 'mTLS-Client-Zertifikate verwalten',
    overview: 'Dedizierte Verwaltung für mTLS-Client-Zertifikate, die über die Konto-Seite registriert wurden. Zeigen, exportieren, widerrufen und löschen Sie Zertifikate, die Benutzern für die mutuelle TLS-Authentifizierung ausgestellt wurden.',
    sections: [
      {
        title: 'Zertifikatsstatus',
        definitions: [
          { term: 'Gültig', description: 'Innerhalb des Gültigkeitszeitraums und nicht widerrufen' },
          { term: 'Ablaufend', description: 'Läuft innerhalb von 30 Tagen ab' },
          { term: 'Abgelaufen', description: 'Nach dem „Nicht nach"-Datum' },
          { term: 'Widerrufen', description: 'Explizit von einem Operator oder Admin widerrufen' },
        ]
      },
      {
        title: 'Aktionen',
        items: [
          { label: 'Exportieren', text: 'Als PEM (mit Schlüssel und Kette) oder PKCS#12 (passwortgeschützt) herunterladen' },
          { label: 'Widerrufen', text: 'Mit einem Grund widerrufen, das Zertifikat erscheint in der CRL' },
          { label: 'Löschen', text: 'Das Zertifikat und seine Benutzerzuordnung aus UCM entfernen' },
        ]
      },
      {
        title: 'Berechtigungen',
        items: [
          { label: 'Viewer', text: 'Sehen nur ihre eigenen Zertifikate' },
          { label: 'Operatoren', text: 'Können alle Benutzerzertifikate anzeigen, exportieren, widerrufen und löschen; der Export des privaten Schlüssels eines fremden Zertifikats erfordert read:private_keys, das der Rolle fehlt' },
          { label: 'Admins', text: 'Vollzugriff, private Schlüssel eingeschlossen' },
          { label: 'Auditoren', text: 'Können Zertifikate anzeigen und exportieren, ohne ihren privaten Schlüssel' },
        ]
      },
    ],
    tips: [
      'Registrieren Sie neue mTLS-Zertifikate unter Konto → mTLS-Tab',
      'Zertifikate werden von UCM wie jedes andere Zertifikat gespeichert und verwaltet',
      'Verwenden Sie die Statistikleiste, um schnell nach Status zu filtern',
      'Klicken Sie auf eine Zeile, um die vollständigen Zertifikatsdetails im Inspektor anzuzeigen',
    ],
    warnings: [
      'Der Widerruf eines Benutzerzertifikats verhindert sofort die mTLS-Anmeldung mit diesem Zertifikat',
      'Das Löschen entfernt das Zertifikat dauerhaft: es kann nicht wiederhergestellt werden',
    ],
  },
  helpGuides: {
    title: 'Benutzerzertifikate',
    content: `
## Übersicht

Die Seite Benutzerzertifikate verwaltet mTLS-Client-Zertifikate, die über den Tab **Konto → mTLS** registriert wurden. Anders als reguläre Zertifikate sind diese speziell an Benutzerkonten für die mutuelle TLS-Authentifizierung gebunden.

Die Zertifikate hier werden vollständig von UCM verwaltet: sie werden mit privaten Schlüsseln in der Datenbank gespeichert und können jederzeit exportiert, widerrufen oder gelöscht werden.

## Ein Zertifikat registrieren

1. Gehen Sie zum Tab **Konto → mTLS**
2. Klicken Sie auf **Zertifikat registrieren**
3. Das System generiert ein Schlüsselpaar und stellt ein von Ihrer mTLS-CA signiertes Client-Zertifikat aus
4. Das Zertifikat erscheint auf dieser Seite und kann für die mTLS-Anmeldung verwendet werden

## Zertifikatsstatus

- **Gültig**: Innerhalb des Gültigkeitszeitraums und nicht widerrufen
- **Ablaufend**: Läuft innerhalb von 30 Tagen ab
- **Abgelaufen**: Nach dem „Nicht nach"-Datum
- **Widerrufen**: Explizit widerrufen, in der CRL veröffentlicht

## Ein Zertifikat exportieren

1. Wählen Sie ein Zertifikat → **Exportieren**
2. Wählen Sie das Format:
   - **PEM**: Zertifikat + privater Schlüssel + CA-Kette im Textformat
   - **PKCS#12**: Binärbündel, passwortgeschützt (mind. 8 Zeichen)
3. Klicken Sie auf **Herunterladen**

Die exportierte Datei kann in Browser, Betriebssysteme oder API-Clients für die mTLS-Authentifizierung importiert werden.

> ⚠ Das PKCS#12-Passwort muss mindestens 8 Zeichen lang sein.

## Ein Zertifikat widerrufen

1. Wählen Sie ein Zertifikat → **Widerrufen**
2. Wählen Sie einen Widerrufsgrund:
   - Schlüsselkompromittierung
   - Zugehörigkeit geändert
   - Ersetzt
   - Betriebseinstellung
   - Nicht spezifiziert
3. Bestätigen Sie den Widerruf

> ⚠ Der Widerruf eines Zertifikats verhindert sofort die mTLS-Anmeldung mit diesem Zertifikat. Der Widerruf ist dauerhaft.

## Ein Zertifikat löschen

Das Löschen entfernt sowohl das Zertifikat als auch die Benutzer-Zertifikat-Zuordnung. Nur Admins und Operatoren können löschen.

> ⚠ Das Löschen ist dauerhaft und kann nicht rückgängig gemacht werden.

## Berechtigungen

| Rolle | Anzeigen | Exportieren | Widerrufen | Löschen |
|-------|----------|-------------|------------|---------|
| Admin | Alle | Alle | Alle | Alle |
| Operator | Alle | Alle (der private Schlüssel eines anderen Benutzers erfordert read:private_keys) | Alle | Alle |
| Auditor | Alle | Nur Zertifikat, ohne privaten Schlüssel | ✗ | ✗ |
| Viewer | Nur eigene | Nur eigene | ✗ | ✗ |

### Erforderliche Berechtigungen

- **read:user_certificates**: Zertifikatsliste und Details anzeigen
- **write:user_certificates**: Zertifikate widerrufen
- **delete:user_certificates**: Zertifikate löschen

> 💡 Registrieren Sie neue mTLS-Zertifikate über die Konto-Seite. Diese Seite dient der Verwaltung bestehender Zertifikate.
`
  }
}
