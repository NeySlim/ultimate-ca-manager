export default {
  helpContent: {
    title: 'Rollenbasierte Zugriffskontrolle',
    subtitle: 'Feingliedrige Berechtigungsverwaltung',
    overview: 'Definieren Sie benutzerdefinierte Rollen mit granularen Berechtigungen. Systemrollen (Admin, Operator, Auditor, Viewer) sind integriert. Benutzerdefinierte Rollen ermöglichen die präzise Steuerung, welche Vorgänge jeder Benutzer durchführen kann.',
    sections: [
      {
        title: 'Systemrollen',
        definitions: [
          { term: 'Admin', description: 'Vollständiger Zugriff auf alle Funktionen und Einstellungen' },
          { term: 'Operator', description: 'Kann Zertifikate und CAs verwalten, aber keine Systemeinstellungen' },
          { term: 'Auditor', description: 'Nur-Lese-Zugriff auf alle Betriebsdaten für Compliance und Audit' },
          { term: 'Viewer', description: 'Grundlegender Nur-Lese-Zugriff auf Zertifikate, CAs und Templates' },
        ]
      },
      {
        title: 'Benutzerdefinierte Rollen',
        items: [
          { label: 'Rolle erstellen', text: 'Eine neue Rolle mit Name und Beschreibung definieren' },
          { label: 'Berechtigungsmatrix', text: 'Berechtigungen nach Kategorie aktivieren/deaktivieren (CAs, Zertifikate, Benutzer, usw.)' },
          { label: 'Abdeckung', text: 'Visuelle Prozentzahl der insgesamt gewährten Berechtigungen für die Rolle' },
          { label: 'Benutzeranzahl', text: 'Sehen, wie viele Benutzer jeder Rolle zugewiesen sind' },
        ]
      },
    ],
    tips: [
      'Befolgen Sie das Prinzip der geringsten Rechte — gewähren Sie nur notwendige Berechtigungen',
      'Systemrollen können nicht geändert oder gelöscht werden',
      'Schalten Sie ganze Kategorien ein/aus für schnelle Rolleneinrichtung',
    ],
  },
  helpGuides: {
    title: 'Rollenbasierte Zugriffskontrolle',
    content: `
## Übersicht

RBAC bietet feingliedrige Berechtigungsverwaltung. Definieren Sie benutzerdefinierte Rollen mit spezifischen Berechtigungen und weisen Sie diese Benutzern oder Gruppen zu.

## Systemrollen

Vier integrierte Rollen, die nicht geändert oder gelöscht werden können:

- **Admin** — Vollständiger Zugriff auf alles
- **Operator** — Zertifikate, CAs, CSRs, Templates verwalten. Kein Zugriff auf Systemeinstellungen, Benutzer oder RBAC
- **Auditor** — Nur-Lese-Zugriff auf alle Betriebsdaten (Zertifikate, CAs, ACME, SCEP, HSM, Audit-Protokolle, Richtlinien, Gruppen), aber nicht auf Einstellungen oder Benutzerverwaltung
- **Viewer** — Grundlegender Nur-Lese-Zugriff auf Zertifikate, CAs, CSRs, Templates und Vertrauensspeicher

## Benutzerdefinierte Rollen

### Benutzerdefinierte Rolle erstellen
1. Klicken Sie auf **Rolle erstellen**
2. Geben Sie einen **Namen** und optionale Beschreibung ein
3. Konfigurieren Sie Berechtigungen mit der **Berechtigungsmatrix**
4. Klicken Sie auf **Erstellen**

### Berechtigungsmatrix
Berechtigungen sind nach Kategorie organisiert:
- **CAs** — Erstellen, Lesen, Aktualisieren, Löschen, Importieren, Exportieren
- **Zertifikate** — Ausstellen, Lesen, Widerrufen, Erneuern, Exportieren, Löschen
- **CSRs** — Erstellen, Lesen, Signieren, Löschen
- **Templates** — Erstellen, Lesen, Aktualisieren, Löschen
- **Benutzer** — Erstellen, Lesen, Aktualisieren, Löschen
- **Gruppen** — Erstellen, Lesen, Aktualisieren, Löschen
- **Einstellungen** — Lesen, Aktualisieren
- **Audit** — Lesen, Exportieren, Bereinigen
- **ACME** — Konfigurieren, Konten verwalten
- **SCEP** — Konfigurieren, Anfragen genehmigen
- **Vertrauensspeicher** — Vertrauenswürdige Zertifikate verwalten
- **HSM** — Anbieter und Schlüssel verwalten
- **Sicherung** — Erstellen, Wiederherstellen

### Kategorie-Schalter
Klicken Sie auf eine Kategorieüberschrift, um alle Berechtigungen in dieser Kategorie gleichzeitig zu aktivieren/deaktivieren.

### Abdeckungsindikator
Ein Prozent-Badge zeigt, wie viel des gesamten Berechtigungssatzes die Rolle abdeckt. 100% = Admin-Äquivalent.

## Rollen zuweisen

Rollen werden zugewiesen:
- **Direkt** — Auf der Benutzerseite einen Benutzer bearbeiten und eine Rolle auswählen
- **Über Gruppen** — Einer Gruppe eine Rolle zuweisen; alle Mitglieder erben sie

## Effektive Berechtigungen

Die effektiven Berechtigungen eines Benutzers ergeben sich aus der Vereinigung von:
1. Den Berechtigungen der direkt zugewiesenen Rolle
2. Allen Rollen aus Gruppen, denen der Benutzer angehört

Die permissivste Regel gewinnt (additives Modell, keine Verweigerungsregeln).

> ⚠ Systemrollen können nicht bearbeitet oder gelöscht werden. Erstellen Sie benutzerdefinierte Rollen für spezifische Anforderungen.
`
  }
}
