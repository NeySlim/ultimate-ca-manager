export default {
  helpContent: {
    title: 'Einstellungen',
    subtitle: 'Systemkonfiguration',
    overview: 'Konfigurieren Sie alle Aspekte des UCM-Systems. Einstellungen sind nach Kategorien organisiert: Allgemein, Darstellung, E-Mail, Sicherheit, SSO, Sicherung, Audit, Datenbank, HTTPS, Updates und Webhooks.',
    sections: [
      {
        title: 'Kategorien',
        items: [
          { label: 'Allgemein', text: 'Instanzname, Hostname und systemweite Standardwerte' },
          { label: 'Darstellung', text: 'Theme-Auswahl (hell/dunkel/System), Akzentfarbe, Desktop-Modus' },
          { label: 'E-Mail (SMTP)', text: 'SMTP-Server, Anmeldedaten, E-Mail-Template-Editor und Ablauf-Warnbenachrichtigungen' },
          { label: 'Sicherheit', text: 'Passwortrichtlinien, Sitzungszeitlimit, Ratenbegrenzung, IP-Einschränkungen' },
          { label: 'SSO', text: 'SAML 2.0, OAuth2/OIDC und LDAP Single-Sign-On-Integration' },
          { label: 'Sicherung', text: 'Manuelle und geplante Datenbanksicherungen' },
          { label: 'Audit', text: 'Protokollaufbewahrung, Syslog-Weiterleitung, Integritätsüberprüfung' },
          { label: 'Datenbank', text: 'Aktives Backend (SQLite oder PostgreSQL), Größe, Tabellenanzahl, testen/wechseln/migrieren zwischen Backends' },
          { label: 'HTTPS', text: 'TLS-Zertifikat für die UCM-Weboberfläche' },
          { label: 'Updates', text: 'Nach neuen Versionen suchen, Änderungsprotokoll anzeigen, Auto-Update (DEB/RPM)' },
          { label: 'Webhooks', text: 'HTTP-Webhooks für Zertifikatsereignisse (Ausstellung, Widerruf, Ablauf)' },
        ]
      },
    ],
    tips: [
      'Verwenden Sie das Systemstatus-Widget oben, um den Dienstzustand schnell zu überprüfen',
      'Testen Sie SMTP-Einstellungen, bevor Sie sich auf E-Mail-Benachrichtigungen verlassen',
      'Passen Sie das E-Mail-Template mit Ihrem Branding über den integrierten HTML/Text-Editor an',
      'Planen Sie automatische Sicherungen für Produktionsumgebungen',
    ],
    warnings: [
      'Das Ändern des HTTPS-Zertifikats erfordert einen Dienstneustart',
      'Das Ändern von Sicherheitseinstellungen kann Benutzer aussperren — überprüfen Sie den Zugriff vor dem Speichern',
    ],
  },
  helpGuides: {
    title: 'Einstellungen',
    content: `
## Übersicht

Systemweite Konfiguration in Tabs organisiert. Änderungen werden sofort wirksam, sofern nicht anders angegeben.

## Allgemein

- **Instanzname** — Wird im Browser-Titel und in E-Mails angezeigt
- **Hostname** — Der vollqualifizierte Domänenname des Servers
- **Standardgültigkeit** — Standard-Zertifikatsgültigkeitsdauer in Tagen
- **Ablaufwarnung-Schwellenwert** — Tage vor Ablauf zur Auslösung von Warnungen

## Darstellung

- **Theme** — Hell, Dunkel oder System (folgt OS-Präferenz)
- **Akzentfarbe** — Primärfarbe für Schaltflächen, Links und Hervorhebungen
- **Desktop-Modus erzwingen** — Responsives mobiles Layout deaktivieren
- **Seitenleisten-Verhalten** — Standardmäßig eingeklappt oder ausgeklappt

## E-Mail (SMTP)

SMTP für E-Mail-Benachrichtigungen konfigurieren (Ablaufwarnungen, Benutzereinladungen):
- **SMTP-Host** und **Port**
- **Benutzername** und **Passwort**
- **Verschlüsselung** — Keine, STARTTLS oder SSL/TLS
- **Absenderadresse** — E-Mail-Adresse des Absenders
- **Inhaltstyp** — HTML, Klartext oder Beides
- **Warnungsempfänger** — Mehrere Empfänger über die Tag-Eingabe hinzufügen

Klicken Sie auf **Testen**, um eine Test-E-Mail zu senden und die Konfiguration zu überprüfen.

### E-Mail-Template-Editor

Klicken Sie auf **Template bearbeiten**, um den Split-Pane-Template-Editor in einem schwebenden Fenster zu öffnen:
- **HTML-Tab** — HTML-E-Mail-Template bearbeiten mit Live-Vorschau rechts
- **Klartext-Tab** — Klartextversion für E-Mail-Clients bearbeiten, die kein HTML unterstützen
- Verfügbare Variablen: \`{{title}}\`, \`{{content}}\`, \`{{datetime}}\`, \`{{instance_url}}\`, \`{{logo}}\`, \`{{title_color}}\`
- Klicken Sie auf **Auf Standard zurücksetzen**, um das integrierte UCM-Template wiederherzustellen
- Das Fenster ist in der Größe veränderbar und verschiebbar für komfortables Bearbeiten

### Ablaufwarnungen

Wenn SMTP konfiguriert ist, aktivieren Sie automatische Zertifikatsablaufwarnungen:
- Warnungen ein-/ausschalten
- Warnschwellenwerte auswählen (90T, 60T, 30T, 14T, 7T, 3T, 1T)
- **Jetzt prüfen** ausführen, um einen sofortigen Scan auszulösen

## Sicherheit

### Passwortrichtlinie
- Mindestlänge (8-32 Zeichen)
- Großbuchstaben, Kleinbuchstaben, Zahlen, Sonderzeichen erfordern
- Passwortablauf (Tage)
- Passwortverlauf (Wiederverwendung verhindern)

### Sitzungsverwaltung
- Sitzungszeitlimit (Minuten der Inaktivität)
- Maximale gleichzeitige Sitzungen pro Benutzer

### Ratenbegrenzung
- Anmeldeversuchslimit pro IP
- Sperrdauer nach Überschreitung des Limits

### IP-Einschränkungen
Zugriff von bestimmten IP-Adressen oder CIDR-Bereichen erlauben oder verweigern.

### 2FA-Durchsetzung
Alle Benutzer zur Aktivierung der Zwei-Faktor-Authentifizierung verpflichten.

> ⚠ Testen Sie IP-Einschränkungen sorgfältig vor der Anwendung. Falsche Regeln können alle Benutzer aussperren.

## SSO (Single Sign-On)

### SAML 2.0
- Geben Sie Ihrem IDP die **SP-Metadaten-URL**: \`/api/v2/sso/saml/metadata\`
- Oder konfigurieren Sie manuell: IDP-Metadaten-XML hochladen/verlinken, Entity ID und ACS-URL konfigurieren
- IDP-Attribute UCM-Benutzerfeldern zuordnen (Benutzername, E-Mail, Rolle)

### OAuth2 / OIDC
- Autorisierungs-URL und Token-URL
- Client-ID und Client-Geheimnis
- Benutzerinfo-URL (für Attributabruf)
- Scopes (openid, profile, email)
- Benutzer bei erster SSO-Anmeldung automatisch erstellen

### LDAP
- Server-Hostname, Port (389/636), SSL-Umschalter
- Bind-DN und Passwort (Dienstkonto)
- Basis-DN und Benutzerfilter
- Attributzuordnung (Benutzername, E-Mail, vollständiger Name)

> 💡 Behalten Sie immer ein lokales Admin-Konto als Fallback, falls SSO ausfällt.

## Sicherung

### Manuelle Sicherung
Klicken Sie auf **Sicherung erstellen**, um einen Datenbank-Snapshot zu erstellen. Sicherungen enthalten alle Zertifikate, CAs, Schlüssel, Einstellungen und Audit-Protokolle.

### Geplante Sicherung
Automatische Sicherungen konfigurieren:
- Häufigkeit (täglich, wöchentlich, monatlich)
- Aufbewahrungsanzahl (Anzahl der zu behaltenden Sicherungen)

### Wiederherstellen
Laden Sie eine Sicherungsdatei hoch, um UCM auf einen früheren Zustand zurückzusetzen.

> ⚠ Die Wiederherstellung einer Sicherung ersetzt ALLE aktuellen Daten.

## Audit

- **Protokollaufbewahrung** — Alte Protokolle nach N Tagen automatisch bereinigen
- **Syslog-Weiterleitung** — Ereignisse an einen Remote-Syslog-Server senden (UDP/TCP/TLS)
- **Integritätsüberprüfung** — Hash-Verkettung zur Manipulationserkennung aktivieren

## Datenbank

UCM unterstützt zwei Datenbank-Backends:

- **SQLite** (Standard) — dateibasiert, ohne Konfiguration, ideal für Einzelknoten
- **PostgreSQL 13+** — empfohlen für Hochverfügbarkeit, Multi-Instanz oder wenn Sie bereits einen verwalteten PG-Cluster betreiben

Das aktive Backend wird über die Umgebungsvariable \`DATABASE_URL\` ausgewählt. Wenn nicht gesetzt, verwendet UCM SQLite unter \`UCM_DATA_DIR/ucm.db\`.

### Statusbereich
- Aktives Backend (sqlite / postgresql) und Treiber
- Datenbankgröße und Tabellenanzahl
- Migrationsversion

### Verbindung testen
Validieren Sie eine \`DATABASE_URL\` (z. B. \`postgresql+psycopg2://user:pass@host:5432/ucm\`) vor dem Wechsel. Der Test öffnet eine echte Verbindung und meldet jeden Fehler.

### Backend wechseln
Speichert \`DATABASE_URL\` in \`/etc/ucm/ucm.env\` (DEB/RPM) und startet UCM neu. **Keine Daten werden kopiert** — verwenden Sie zuerst **Migrieren**, wenn Sie Ihre bestehenden Daten behalten möchten.

### Daten migrieren
Kopiert alle Zeilen vom aktuellen zum Ziel-Backend. Funktioniert in beide Richtungen (SQLite ↔ PostgreSQL):

1. Die Quelldatenbank wird unter \`/opt/ucm/data/backups/db_migration/\` gesichert
2. Das Schema wird auf dem Ziel über SQLAlchemy erstellt
3. FK-Prüfungen werden während des Bulk-Loads deaktiviert
4. Quell-/Ziel-Spalten werden geschnitten (Legacy-Spalten werden mit einer Warnung übersprungen)
5. PostgreSQL-Sequenzen werden nach dem Laden zurückgesetzt
6. Der Dienst startet automatisch neu (DEB/RPM) — auf Docker setzen Sie \`DATABASE_URL\` in Ihrer Compose-Datei und starten den Container manuell neu

> ⚠ Erstellen Sie immer eine vollständige UCM-Sicherung (Einstellungen → Sicherung), bevor Sie zwischen Backends migrieren.

## HTTPS

TLS-Zertifikat für die UCM-Weboberfläche verwalten:
- Aktuelle Zertifikatsdetails anzeigen
- Neues Zertifikat importieren (PEM oder PKCS#12)
- Selbstsigniertes Zertifikat generieren

> ⚠ Das Ändern des HTTPS-Zertifikats erfordert einen Dienstneustart.

## Updates

- Nach neuen UCM-Versionen von GitHub-Releases suchen
- Änderungsprotokoll für verfügbare Updates anzeigen
- Aktuelle Version und Build-Informationen
- **Auto-Update**: Auf unterstützten Installationen (DEB/RPM) klicken Sie auf **Jetzt aktualisieren**, um die neueste Version automatisch herunterzuladen und zu installieren
- **Vorabversionen einbeziehen**: Umschalten, um auch nach Release-Kandidaten (RC) zu suchen

## Webhooks

HTTP-Webhooks konfigurieren, um externe Systeme bei Ereignissen zu benachrichtigen:

### Unterstützte Ereignisse
- Zertifikat ausgestellt, widerrufen, abgelaufen, erneuert
- CA erstellt, gelöscht
- Benutzer angemeldet, abgemeldet
- Sicherung erstellt

### Webhook erstellen
1. Klicken Sie auf **Webhook hinzufügen**
2. Geben Sie die **URL** ein (muss HTTPS sein)
3. Wählen Sie die zu abonnierenden **Ereignisse**
4. Setzen Sie optional ein **Geheimnis** für HMAC-Signaturverifizierung
5. Klicken Sie auf **Erstellen**

### Testen
Klicken Sie auf **Testen**, um ein Beispielereignis an die Webhook-URL zu senden und die Erreichbarkeit zu überprüfen.
`
  }
}
