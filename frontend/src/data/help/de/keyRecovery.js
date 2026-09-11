export default {
  helpContent: {
    title: 'Schlüsselwiederherstellung',
    subtitle: 'Archivierte private Schlüssel nach dem Vier-Augen-Prinzip wiederherstellen',
    overview: 'Die Schlüsselwiederherstellung ruft den archivierten privaten Schlüssel eines zuvor ausgestellten Zertifikats über einen genehmigungspflichtigen, vollständig auditierten Workflow ab. Sie existiert für Schlüssel, die bei der Ausstellung nicht exportiert wurden (die Voreinstellung erlaubte es nicht, oder der Export wurde übersprungen) und später benötigt werden — mit einer Genehmigungsspur, die mit dem Abruf verknüpft ist.',
    sections: [
      {
        title: 'Ablauf',
        items: [
          { label: 'Anfrage', text: 'Ein Benutzer beantragt die Wiederherstellung des archivierten Schlüssels eines bestimmten Zertifikats und gibt einen Grund an' },
          { label: 'Genehmigung (Vier-Augen-Prinzip)', text: 'Ein zweiter autorisierter Operator prüft und genehmigt — der Antragsteller kann seine eigene Anfrage nicht genehmigen' },
          { label: 'Download', text: 'Nach der Genehmigung wird der Schlüssel als passwortgeschütztes PKCS#12-Paket freigegeben' },
        ]
      },
      {
        title: 'Voraussetzungen',
        items: [
          { label: 'Archivierter Schlüssel', text: 'Der private Schlüssel des Zertifikats muss in der Datenbank gespeichert sein — die Wiederherstellung kann keinen Schlüssel rekonstruieren, der nie archiviert wurde' },
          { label: 'Vier-Augen-Prinzip', text: 'Anfrage und Genehmigung sind getrennte Aktionen verschiedener Personen; jeder Schritt wird im Audit-Protokoll festgehalten' },
        ]
      },
    ],
    tips: [
      'Die Schlüsselwiederherstellung ist für Schlüssel gedacht, die bei der Ausstellung des Zertifikats nicht exportiert wurden; sie ist kein Ersatz für die Einschränkung des Schlüsselexports zum Zeitpunkt der Ausstellung.',
      'Jede Anfrage, Genehmigung und jeder Download wird zu Compliance-Zwecken im Audit-Protokoll aufgezeichnet.',
    ],
    warnings: [
      'Ein Zertifikat, dessen privater Schlüssel nie archiviert wurde, kann nicht wiederhergestellt werden — es gibt nichts freizugeben.',
    ],
  },
  helpGuides: {
    title: 'Schlüsselwiederherstellung',
    content: `
## Übersicht

Die Schlüsselwiederherstellung ruft den **archivierten privaten Schlüssel** eines zuvor ausgestellten Zertifikats über einen genehmigungspflichtigen, vollständig auditierten Workflow ab. Sie ist für Schlüssel gedacht, die **bei der Ausstellung nicht exportiert wurden** — die Voreinstellung erlaubte den Export nicht, oder er wurde einfach übersprungen — und später benötigt werden, mit einer Genehmigungsspur, die mit dem Abruf verknüpft ist.

Die Wiederherstellung funktioniert nur, wenn der private Schlüssel bei der Ausstellung archiviert (in der Datenbank gespeichert) wurde. Sie kann keinen Schlüssel rekonstruieren, der nie aufbewahrt wurde.

## Ablauf

### 1. Anfrage
Ein Benutzer eröffnet eine Wiederherstellungsanfrage für ein bestimmtes Zertifikat und gibt einen Grund an. Die Anfrage wird aufgezeichnet und geht in den Status „ausstehend" über.

### 2. Genehmigung (Vier-Augen-Prinzip)
Ein zweiter autorisierter Operator prüft die Anfrage und genehmigt sie. Der Antragsteller **kann seine eigene Anfrage nicht genehmigen** — Anfrage und Genehmigung sind getrennte Aktionen verschiedener Personen (Vier-Augen-Prinzip).

### 3. Download
Nach der Genehmigung wird der archivierte Schlüssel als **passwortgeschütztes PKCS#12-Paket** freigegeben. Der Download wird im Audit-Protokoll festgehalten.

## Voraussetzungen

- **Archivierter Schlüssel** — der private Schlüssel des Zertifikats muss in der Datenbank vorhanden sein. Zertifikate, deren Schlüssel nie archiviert wurde, können nicht wiederhergestellt werden.
- **Vier-Augen-Prinzip** — Anfrage und Genehmigung sind getrennte Schritte, die von verschiedenen Benutzern ausgeführt werden.

## Berechtigungen

- **read:key_recovery** — Eine Wiederherstellung beantragen und Anfragen einsehen
- **admin** — Eine ausstehende Wiederherstellungsanfrage genehmigen oder ablehnen
- **read:private_keys** — Nur Admins vorbehaltener Scope, der für den *direkten* Export privater Schlüssel von der Zertifikatsseite (unter Umgehung dieses Workflows) erforderlich ist

## Was es ist (und was nicht)

Die Schlüsselwiederherstellung fügt dem Abruf eines archivierten Schlüssels nach der Ausstellung eine **Genehmigungsspur** hinzu. Sie ist kein Ersatz für die Einschränkung des Exports privater Schlüssel in Voreinstellungen — wenn eine Rolle Schlüssel bereits direkt exportieren kann, ist das ein eigener Zugriffspfad, der separat kontrolliert werden muss.

> 💡 Jede Anfrage, Genehmigung und jeder Download wird zu Compliance-Zwecken im Audit-Protokoll festgehalten.
`
  }
}
