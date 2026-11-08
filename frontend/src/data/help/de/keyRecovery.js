export default {
  helpContent: {
    title: 'Schlüsselwiederherstellung',
    subtitle: 'Archivierte private Schlüssel nach dem Vier-Augen-Prinzip wiederherstellen',
    overview: 'Die Schlüsselwiederherstellung ruft den archivierten privaten Schlüssel eines zuvor ausgestellten Zertifikats über einen genehmigungspflichtigen, vollständig auditierten Workflow ab. Sie existiert für Schlüssel, die bei der Ausstellung nicht exportiert wurden (die Voreinstellung erlaubte es nicht, oder der Export wurde übersprungen) und später benötigt werden, mit einer Genehmigungsspur, die mit dem Abruf verknüpft ist.',
    sections: [
      {
        title: 'Ablauf',
        items: [
          { label: 'Anfrage', text: 'Ein Benutzer beantragt die Wiederherstellung des archivierten Schlüssels eines bestimmten Zertifikats und gibt einen Grund an' },
          { label: 'Genehmigung (Vier-Augen-Prinzip)', text: 'Ein Administrator prüft und genehmigt; bei aktiver doppelter Kontrolle (Standard) kann der Antragsteller seine eigene Anfrage nicht genehmigen' },
          { label: 'Download', text: 'Nach der Genehmigung wird der Schlüssel als passwortgeschütztes PKCS#12-Paket freigegeben' },
          { label: 'Zertifikat ersetzt (v2.251)', text: 'Genehmigung und Wiederherstellung antworten mit 410, sofern das Zertifikat der Anfrage nicht mehr dasjenige ist, auf dem sie geöffnet wurde. Eine ersetzende Wiederherstellung bricht die offenen Anfragen zu den Zertifikaten ab, die sie entfernt' },
        ]
      },
      {
        title: 'Voraussetzungen',
        items: [
          { label: 'Archivierter Schlüssel', text: 'Der private Schlüssel des Zertifikats muss in der Datenbank gespeichert sein, die Wiederherstellung kann keinen Schlüssel rekonstruieren, der nie archiviert wurde' },
          { label: 'Vier-Augen-Prinzip', text: 'Standardmäßig an: Anfrage und Genehmigung sind getrennte Aktionen verschiedener Personen. Anfragen, Genehmigungen und Downloads werden im Audit-Protokoll festgehalten; eine abgelehnte Genehmigung oder ein abgelehnter Download nicht' },
        ]
      },
    ],
    tips: [
      'Die Schlüsselwiederherstellung ist für Schlüssel gedacht, die bei der Ausstellung des Zertifikats nicht exportiert wurden; sie ist kein Ersatz für die Einschränkung des Schlüsselexports zum Zeitpunkt der Ausstellung.',
      'Jede Anfrage, Genehmigung und jeder Download wird im Audit-Protokoll aufgezeichnet; Ablehnungen nicht.',
    ],
    warnings: [
      'Ein Zertifikat, dessen privater Schlüssel nie archiviert wurde, kann nicht wiederhergestellt werden: es gibt nichts freizugeben.',
    ],
  },
  helpGuides: {
    title: 'Schlüsselwiederherstellung',
    content: `
## Übersicht

Die Schlüsselwiederherstellung ruft den **archivierten privaten Schlüssel** eines zuvor ausgestellten Zertifikats über einen genehmigungspflichtigen, vollständig auditierten Workflow ab. Sie ist für Schlüssel gedacht, die **bei der Ausstellung nicht exportiert wurden**: die Voreinstellung erlaubte den Export nicht, oder er wurde einfach übersprungen, und später benötigt werden, mit einer Genehmigungsspur, die mit dem Abruf verknüpft ist.

Die Wiederherstellung funktioniert nur, wenn der private Schlüssel bei der Ausstellung archiviert (in der Datenbank gespeichert) wurde. Sie kann keinen Schlüssel rekonstruieren, der nie aufbewahrt wurde.

## Ablauf

### 1. Anfrage
Ein Benutzer eröffnet eine Wiederherstellungsanfrage für ein bestimmtes Zertifikat und gibt einen Grund an. Die Anfrage wird aufgezeichnet und geht in den Status „ausstehend" über.

### 2. Genehmigung (Vier-Augen-Prinzip)
Ein Administrator prüft die Anfrage und genehmigt sie. Bei aktiver doppelter Kontrolle (Standard) **kann der Antragsteller seine eigene Anfrage nicht genehmigen**: Anfrage und Genehmigung sind getrennte Aktionen verschiedener Personen.

### 3. Download
Nach der Genehmigung wird der archivierte Schlüssel als **passwortgeschütztes PKCS#12-Paket** freigegeben. Der Download wird im Audit-Protokoll festgehalten.

## Voraussetzungen

- **Archivierter Schlüssel**: der private Schlüssel des Zertifikats muss in der Datenbank vorhanden sein. Zertifikate, deren Schlüssel nie archiviert wurde, können nicht wiederhergestellt werden.
- **Vier-Augen-Prinzip**: standardmäßig an, Anfrage und Genehmigung sind getrennte Schritte, die von verschiedenen Benutzern ausgeführt werden. Ein Administrator kann es ausschalten und dann seine eigene Anfrage genehmigen.

## Berechtigungen

- **read:key_recovery**: Anfragen einsehen
- **write:key_recovery**: Eine Wiederherstellung beantragen
- **admin**: Eine ausstehende Wiederherstellungsanfrage genehmigen oder ablehnen
- **read:private_keys**: Erforderlich für den *direkten* Export privater Schlüssel von der Zertifikatsseite (unter Umgehung dieses Workflows). Von den eingebauten Rollen besitzt nur Admin ihn; eine benutzerdefinierte Rolle kann ihn gewähren

## Was es ist (und was nicht)

Die Schlüsselwiederherstellung fügt dem Abruf eines archivierten Schlüssels nach der Ausstellung eine **Genehmigungsspur** hinzu. Der direkte Export privater Schlüssel ist an den Scope **read:private_keys** gebunden: Rollen ohne ihn (auch die eingebaute Rolle Operator) müssen über die Schlüsselwiederherstellung gehen. Ein Administrator oder eine benutzerdefinierte Rolle mit diesem Scope exportiert den Schlüssel direkt, ohne Genehmigung, sodass die Vier-Augen-Genehmigung nur die Rollen ohne ihn bindet.

> 💡 Jede Anfrage, Genehmigung und jeder Download wird zu Compliance-Zwecken im Audit-Protokoll festgehalten.
`
  }
}
