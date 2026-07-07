export default {
  helpContent: {
    title: 'Einstellungen',
    subtitle: 'Systemkonfiguration',
    overview: 'Konfigurieren Sie alle Aspekte des UCM-Systems. Einstellungen sind nach Kategorien organisiert: Allgemein, Darstellung, E-Mail, Sicherheit, SSO, Sicherung, Audit, Datenbank, HTTPS, Updates und Webhooks.',
    sections: [
      {
        title: "Prometheus-Metriken",
        content: "Opt-in-Endpunkt /metrics, der Zähler (Zertifikate, CAs, Planer, Webhooks, ACME) im Prometheus-Format bereitstellt.",
        items: [
          { label: "Aktivieren", text: "Setzen Sie ein Metriken-Token unter Einstellungen › Allgemein; ohne Token liefert der Endpunkt 404 (deaktiviert)" },
          { label: "Authentifizierung", text: "Scrapen mit Authorization: Bearer <Token>" },
          { label: "Zähler", text: "ucm_certificates, ucm_certificate_authorities, ucm_scheduler_task_*, ucm_webhook_deliveries, ucm_acme_*" },
        ]
      },
      {
        title: "Öffentlicher ACME-Vhost",
        content: "Einstellungen › Allgemein: öffentlicher Hostname und Port für ACME-Directory-URLs hinter einem Reverse Proxy.",
        items: [
          { label: "Admin", text: "admin.ucm.example.com — GUI und API (mTLS nach Richtlinie)" },
          { label: "ACME", text: "acme.ucm.example.com — /acme/* und /acme/proxy/* (ohne Client-mTLS)" },
          { label: "Wildcard", text: "Ein Zertifikat *.ucm.example.com deckt admin.ucm.example.com und acme.ucm.example.com ab, nicht den Apex ucm.example.com" },
          { label: "TLS-Zertifikat-ID", text: "Metadaten für das auf dem ACME-Vhost bereitgestellte Zertifikat (z. B. Wildcard)" },
        ]
      },
      {
        title: "Webhook-Zustellungsverlauf",
        content: "Jeder Webhook-Endpunkt führt ein Zustellungsprotokoll mit Status, Versuchen und manuellem Wiederholen.",
        items: [
          { label: "Status", text: "pending / delivered / failed, mit letztem HTTP-Code und Fehler" },
          { label: "Wiederholen", text: "Ein fehlgeschlagenes oder bereits zugestelltes Ereignis manuell erneut einreihen" },
          { label: "Asynchron", text: "Zustellungen laufen aus einer dauerhaften Warteschlange mit exponentiellem Backoff (bis zu 5 Versuche)" },
        ]
      },
      {
        title: "Planer-Ansicht",
        content: "Einstellungen › System listet die Hintergrundaufgaben mit Status und letzter Ausführung auf.",
        items: [
          { label: "Aufgaben", text: "Ablaufprüfungen, CRL-Aktualisierung, Webhook-Zustellung, geplante Backups, Auto-Erneuerung usw." },
          { label: "Jetzt ausführen", text: "Jede Aufgabe bei Bedarf auslösen" },
          { label: "Sichtbarkeit", text: "Letzte Ausführung, letzte Dauer und Fehleranzahl je Aufgabe" },
        ]
      },
      {
        title: "Geplante Backups",
        content: "Automatische, verschlüsselte Datenbank-Backups in konfigurierbarer Frequenz mit Aufbewahrung.",
        items: [
          { label: "Frequenz", text: "Täglich / wöchentlich / monatlich" },
          { label: "Aufbewahrung", text: "Die N neuesten Backups behalten; ältere werden bereinigt" },
          { label: "Verschlüsselung", text: "Backups werden mit dem konfigurierten Backup-Passwort verschlüsselt" },
        ]
      },
      {
        title: "HSTS (Strict Transport Security)",
        content: "Operator-konfigurierbare HSTS-Richtlinie, sodass Instanzen mit selbstsignierten Zertifikaten während der Ersteinrichtung sich vollständig abmelden können.",
        items: [
          { label: "Standard", text: "HSTS an, includeSubDomains, max-age 1 Jahr (abwärtskompatibel)" },
          { label: "Deaktivieren", text: "Für Instanzen mit selbstsignierten Zertifikaten während der Ersteinrichtung deaktivieren (verhindert Browser-Sperre)" },
          { label: "Env-Override", text: "UCM_HSTS_ENABLED, UCM_HSTS_INCLUDE_SUBDOMAINS, UCM_HSTS_MAX_AGE in /etc/ucm/ucm.env haben Vorrang vor der DB" },
          { label: "Subdomains", text: "includeSubDomains entfernen, wenn Subdomains separate Dienste mit eigenen Zertifikaten hosten" },
        ]
      },
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
      {
        title: 'SMTP OAuth2 (XOAUTH2)',
        content: 'Moderne OAuth2-Authentifizierung für ausgehende Mail, ersetzt die alten App-Passwort-Flows, die Microsoft und Google einstellen:',
        items: [
          { label: 'Gmail', text: 'Google-Cloud-OAuth2-Client mit dem Scope https://mail.google.com/ konfigurieren' },
          { label: 'Microsoft 365 / Outlook.com', text: 'Azure-AD-App mit delegierter SMTP.Send-Berechtigung registrieren' },
          { label: 'Refresh-Tokens', text: 'UCM speichert das Refresh-Token und erneuert Access-Tokens vor jedem Versand automatisch' },
          { label: 'Fallback', text: 'Passwort-Authentifizierung wird weiterhin unterstützt, wenn OAuth2 nicht konfiguriert ist' },
        ]
      },

    ],
    tips: [
      'Verwenden Sie das Systemstatus-Widget oben, um den Dienstzustand schnell zu überprüfen',
      'Testen Sie SMTP-Einstellungen, bevor Sie sich auf E-Mail-Benachrichtigungen verlassen',
      'Passen Sie das E-Mail-Template mit Ihrem Branding über den integrierten HTML/Text-Editor an',
      'Planen Sie automatische Sicherungen für Produktionsumgebungen',
      'Der Wechsel SQLite ↔ PostgreSQL ist bidirektional — die UI führt Sicherheitsprüfungen (Treiber geladen, Ziel erreichbar, Ziel leer) vor der Migration durch',
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
Validieren Sie eine \`DATABASE_URL\` (z. B. \`postgresql://user:pass@host:5432/ucm\`) vor dem Wechsel. Der Test öffnet eine echte Verbindung und meldet jeden Fehler. PostgreSQL-Server älter als Version 13 werden abgelehnt — UCM erfordert PostgreSQL 13 oder neuer.

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

**Sicherheitsprüfungen (schneller Abbruch, Quelle unangetastet):**
- Das Ziel muss leer sein. Wenn \`users\`, \`cas\` oder \`certificates\` bereits Zeilen enthalten, wird die Migration mit HTTP 409 abgelehnt und ein Bereinigungshinweis ausgegeben:
  - PostgreSQL: \`psql ... -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'\`
  - SQLite: löschen Sie die Ziel-\`.db\`-Datei
- Wenn die Migration auf halbem Weg fehlschlägt, bleibt die Quelle unangetastet und die Fehlermeldung verweist auf die Quellsicherung. Setzen Sie das Ziel zurück, bevor Sie es erneut versuchen.

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
## Prometheus-Metriken

Opt-in-Endpunkt **\`/metrics\`** mit Token-Schutz.

- Aktivieren durch Setzen eines Metriken-Tokens (Einstellungen › Allgemein); ohne Token → 404
- Scrapen mit Header \`Authorization: Bearer <Token>\`
- Stellt \`ucm_certificates\`, \`ucm_certificate_authorities\`, \`ucm_scheduler_task_*\`, \`ucm_webhook_deliveries\`, \`ucm_acme_*\` bereit

## Webhook-Zustellungsverlauf

Öffnen Sie den Verlauf (Uhr-Symbol) an einem Webhook, um seine Zustellungen zu sehen.

- Status **pending / delivered / failed** mit letztem HTTP-Code und Fehler
- Eine Zustellung manuell **wiederholen**
- Dauerhafte Warteschlange mit exponentiellem Backoff (bis zu 5 Versuche)

## Planer-Ansicht

Einstellungen › System zeigt die Hintergrundaufgaben.

- Aufgabenliste mit **Status**, **letzter Ausführung**, **Dauer** und **Fehlern**
- **Jetzt ausführen** für jede Aufgabe
- Umfasst Ablauf, CRL, Webhook-Zustellung, Backups, Auto-Erneuerung…

## Geplante Backups

Einstellungen › Sicherung ermöglicht automatische Backups.

- Frequenz **täglich / wöchentlich / monatlich**
- **Aufbewahrung**: die N neuesten behalten, ältere bereinigen
- Backups mit dem Backup-Passwort **verschlüsselt**

`
  }
}
