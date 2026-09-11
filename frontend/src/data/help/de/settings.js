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
          { label: "Wildcard TLS", text: "Konkreter Hostname (z. B. acme.ucm.example.com). Ein *.ucm.example.com-Zertifikat-SAN deckt TLS für Admin- und ACME-Vhosts ab — nicht *.ucm.example.com als Vhost eintragen" },
          { label: "Vor dem Speichern", text: "Sorgen Sie zuerst für funktionierendes DNS und TLS auf dem ACME-Vhost — Clients, die das Directory neu lesen, wechseln die URLs sofort, und Erneuerungen schlagen fehl, wenn der Vhost nicht erreichbar ist" },
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
        title: 'Automatische Updates (v2.215)',
        content: 'Einstellungen › Updates: eine tägliche Hintergrundprüfung auf neue Versionen und eine optionale unbeaufsichtigte Installation.',
        items: [
          { label: "Kanal", text: "Stabil folgt nur finalen Releases; Release-Kandidaten nimmt zusätzlich nur rcN-Versionen an — Alpha/Beta niemals" },
          { label: 'Benachrichtigung', text: 'Eine neu verfügbare Version löst das Webhook-/E-Mail-Ereignis system.update_available aus, einmal pro Version' },
          { label: 'Auto-Installation', text: 'Standardmäßig aus. Wenn aktiviert, lädt UCM das Update zur gewählten Stunde herunter, verifiziert und installiert es und startet dann neu — nur DEB/RPM-Installationen' },
          { label: 'Prüfsumme', text: 'Eine unbeaufsichtigte Installation erfordert die veröffentlichte SHA256 des Releases zur Verifizierung; eine manuelle Installation verifiziert ebenfalls, wann immer eine Prüfsumme veröffentlicht ist' },
          { label: 'Docker', text: 'Container können sich nicht selbst aktualisieren — Prüfung und Benachrichtigung funktionieren weiterhin; ziehen Sie das neue Image, um zu aktualisieren' },
          { label: 'Popup nach Update', text: 'Optional (v2.217): zeigt die Versionshinweise nach einer installierten Aktualisierung einmal pro Benutzer an. Standardmäßig aus' },
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
          { label: 'HTTPS', text: 'TLS-Zertifikat für die UCM-Weboberfläche. Das angewendete Zertifikat wird gespeichert und bei seiner Erneuerung automatisch erneut angewendet (v2.217); das gebundene Zertifikat wird mit einer Schaltfläche zum Aufheben der Bindung angezeigt, um Erneuerungen nicht mehr zu folgen (v2.218)' },
          { label: 'Updates', text: 'Nach neuen Versionen suchen, Änderungsprotokoll anzeigen, geplante tägliche Prüfung mit optionaler unbeaufsichtigter Installation (DEB/RPM)' },
          { label: 'Webhooks', text: 'HTTP-Webhooks für Zertifikatsereignisse (Ausstellung, Widerruf, Ablauf)' },
          { label: 'Bereitstellung', text: 'Deploy-Ziele: entfernte Hosts, auf die Zertifikate bei Ausstellung und Erneuerung per SSH/SFTP übertragen werden, mit einem festen Reload-Befehl (nur Admins, v2.215)' },
          { label: 'Active Directory', text: 'UCMs eigene AD/LDAP-Verbindung für zertifikatsbezogene Abfragen (Kerberos-Prinzipalauflösung, AD-abgeleitete Betreffe)' },
          { label: 'Windows-Autoregistrierung', text: 'MS-XCEP/MS-WSTEP native Windows-Registrierung: Richtlinienermittlung, Zertifikatsausstellung und Kerberos/SPNEGO-Bindung' },
        ]
      },
      {
        title: 'Deploy-Hooks (v2.215)',
        content: 'Einstellungen › Bereitstellung (nur Admins): entfernte Hosts, auf die UCM Zertifikate per SFTP überträgt und anschließend einen festen Reload-Befehl per SSH ausführt.',
        items: [
          { label: 'Ziel', text: 'Host, Port, SSH-Benutzer. UCM generiert einen ed25519-Schlüssel (den angezeigten öffentlichen Schlüssel auf dem Ziel installieren) oder akzeptiert einen importierten privaten Schlüssel — verschlüsselt gespeichert' },
          { label: 'Host-Key', text: 'Wird bei der ersten erfolgreichen Verbindung gepinnt (Trust-on-first-use); jede spätere Änderung lässt die Verbindung fehlschlagen (fail-closed). Bei Änderung des Hosts wird neu gepinnt' },
          { label: 'Reload-Befehl', text: 'Ein fester, vom Admin definierter Befehl, der nach einer erfolgreichen Übertragung ausgeführt wird (z. B. systemctl reload nginx) — exit 0 = Erfolg, kein Templating' },
          { label: 'Verknüpfungen', text: 'Zertifikate werden aus der Zertifikat-Detailansicht mit Zielen verknüpft, mit Zielpfaden pro Datei' },
          { label: 'Zustellung', text: 'Übertragungen laufen asynchron über eine dauerhafte Warteschlange mit Wiederholungen und Backoff; Status pro Zustellung, manuelles „Jetzt bereitstellen" und Wiederholen, vollständiger Audit-Trail' },
          { label: 'Minimale Rechte', text: 'Verwenden Sie auf jedem Ziel ein dediziertes SSH-Konto: Schreibzugriff auf die Zertifikatspfade und die Berechtigung, den Dienst neu zu laden — mehr nicht' },
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
      {
        title: 'Active-Directory-Connector',
        content: 'UCMs eigene LDAP-Verbindung zu Active Directory, unabhängig von einem unter SSO konfigurierten LDAP-Anbieter -- dieser dient der Anmeldung bei UCM, dieser hier den zertifikatsbezogenen AD-Abfragen.',
        items: [
          { label: 'Zweck', text: 'Löst ein Kerberos-Maschinen- oder Benutzerprinzipal zu seinem AD-Objekt auf, damit UCM einen Zertifikatsbetreff/SAN ableiten kann, genau wie eine echte Windows-CA' },
          { label: 'Felder', text: 'Server, Port, LDAPS mit optionaler CA-Verifizierung, Basis-DN, Bind-DN/Passwort' },
          { label: 'Verbindung testen', text: 'Verbindung und Anmeldedaten vor dem Speichern überprüfen' },
          { label: 'GPO-Registrierungs-URLs', text: 'Kerberos- und Benutzername/Passwort-URLs für die Zertifikatregistrierungsrichtlinie zur Registrierung in der Gruppenrichtlinie' },
        ]
      },
      {
        title: 'Windows-Autoregistrierung (XCEP/WSTEP)',
        content: 'Native Windows-Zertifikatregistrierung über MS-XCEP-Richtlinienermittlung und MS-WSTEP-Ausstellung -- unterstützt manuelle MMC/certreq-Registrierung und unbeaufsichtigte GPO-Autoregistrierung.',
        items: [
          { label: 'XCEP', text: 'Ermöglicht Windows-Clients, verfügbare Zertifikatvorlagen vor der Registrierung zu ermitteln' },
          { label: 'WSTEP', text: 'Verarbeitet Zertifikatsanforderung und -erneuerung, sobald die Richtlinie ermittelt wurde' },
          { label: 'Kerberos/SPNEGO', text: 'Bindet die Kerberos-authentifizierten Endpunkte für die stille GPO-Autoregistrierung (erfordert einen SPN und ein Keytab vom Domänencontroller)' },
          { label: 'Einrichtungs-Checkliste', text: 'Der Tab zeigt eine Live-Checkliste dessen, was konfiguriert ist bzw. noch fehlt, sowohl für die manuelle als auch die unbeaufsichtigte Registrierung' },
          { label: 'AD-abgeleitete Betreffe', text: 'Vorlagen können sich für die Ableitung ihres Betreffs/SAN aus Active Directory (über den AD-Connector) für die unbeaufsichtigte Registrierung entscheiden' },
        ]
      },
      {
        title: 'Auto-Erneuerung',
        items: [
          { label: 'Quellen', text: 'Der Planer erneuert Zertifikate, deren privaten Schlüssel der Server hält: standardmäßig die über das Formular oder eine signierte Anfrage ausgestellten („manuell") sowie SCEP-, ACME- und EST-Registrierungen mit servergeneriertem Schlüssel. Geräte, die ihren eigenen Schlüssel halten, erneuern über ihr Protokoll' },
          { label: 'Genehmigung ausstehend', text: 'Ein Zertifikat, dessen Erneuerung zur Genehmigung eingereiht ist, bleibt dieser Entscheidung überlassen, solange sie vor dem Ablauf des Zertifikats fallen kann' },
          { label: 'Inzwischen erneuert', text: 'Ein Zertifikat, das ein Operator während des Durchlaufs erneuert hat, wird nicht ein zweites Mal erneuert; ein während des Durchlaufs gelöschtes wird übersprungen' },
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
- **Öffentlicher ACME-Vhost** — Konkreter Hostname in den ACME-Directory-URLs (z. B. \`acme.ucm.example.com\` — nicht \`*.ucm.example.com\`). Ein Wildcard-**TLS-Zertifikat-SAN** \`*.ucm.example.com\` deckt sowohl \`admin.ucm.example.com\` als auch \`acme.ucm.example.com\` ab. Konfigurieren Sie DNS und TLS für den ACME-Vhost **vor** dem Speichern — Clients, die das Directory neu lesen, wechseln die URLs sofort.

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

### Verschlüsselung privater Schlüssel
Alle in der Datenbank gespeicherten privaten Schlüssel mit AES-256 verschlüsseln, geschützt durch eine Master-Key-Datei. Der Bereich zeigt den Verschlüsselungsstatus und die Zähler **verschlüsselt / unverschlüsselt**. Zwei Opt-in-Umgebungsvariablen machen fehlende Schlüssel beim Start fatal: \`UCM_REQUIRE_DB_ENCRYPTION_KEY\` (Verschlüsselung von Integrationsgeheimnissen) und \`UCM_REQUIRE_KEY_ENCRYPTION\` (Verschlüsselung privater Schlüssel).

> 💡 Sicherheitskritische Einstellungen (Sitzung, Sperrung, HSTS, öffentliche URL, Passwortrichtlinie) erfordern die Berechtigung **admin:settings** — die Felder sind für Operatoren gesperrt.

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

### Authentifizierung

Optionale ausgehende Authentifizierung (alle gelten zusätzlich zur optionalen HMAC-Signatur):

- **Keine** — Kein Auth-Header (öffentliche Webhooks)
- **Bearer** — Authorization: Bearer {token}
- **Basic** — Authorization: Basic base64(username:password)
- **API Key** — Benutzerdefinierter Header (z. B. X-Api-Key: {token})
- **Custom** — Authorization: {scheme} {token} (z. B. auth-key VALUE)

Tokens werden verschlüsselt gespeichert und nie in der UI zurückgegeben.

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

## Auto-Erneuerung

Die Einstellungen zur Auto-Erneuerung steuern den Erneuerungsplaner.

- **Quellen** — der Planer erneuert Zertifikate, deren privaten Schlüssel der Server hält: standardmäßig die über das Formular oder eine signierte Anfrage ausgestellten („manuell") sowie SCEP-, ACME- und EST-Registrierungen mit servergeneriertem Schlüssel. Geräte, die ihren eigenen Schlüssel halten, erneuern über ihr Protokoll
- **Genehmigung ausstehend** — ein Zertifikat, dessen Erneuerung zur Genehmigung eingereiht ist, bleibt dieser Entscheidung überlassen, solange sie vor dem Ablauf des Zertifikats fallen kann
- **Inzwischen erneuert** — ein Zertifikat, das ein Operator während des Durchlaufs erneuert hat, wird nicht ein zweites Mal erneuert; ein während des Durchlaufs gelöschtes wird übersprungen

## Geplante Backups

Einstellungen › Sicherung ermöglicht automatische Backups.

- Frequenz **täglich / wöchentlich / monatlich**
- **Aufbewahrung**: die N neuesten behalten, ältere bereinigen
- Backups mit dem Backup-Passwort **verschlüsselt**


## Active-Directory-Connector

UCMs eigene LDAP-Verbindung zu Active Directory, unabhängig von einem unter SSO konfigurierten LDAP-Anbieter. Jener dient der Anmeldung bei UCM; dieser hier wird für zertifikatsbezogene AD-Abfragen verwendet und funktioniert unabhängig davon, ob SSO überhaupt konfiguriert ist.

- **Zweck** — Löst ein Kerberos-Maschinen- oder Benutzerprinzipal zu seinem AD-Objekt auf, damit UCM einen Zertifikatsbetreff/SAN ableiten kann, genau wie eine echte Windows-CA
- **Server** — Hostname/IP und Port eines Domänencontrollers
- **LDAPS** — Umschalten, um LDAP über SSL/TLS zu verwenden; **SSL-Zertifikat prüfen** validiert das Zertifikat des DC (optional gegen ein benutzerdefiniertes CA-Bundle, wenn es nicht öffentlich vertrauenswürdig ist)
- **Basis-DN** und **Bind-DN / Passwort** — Für Abfragen verwendete Dienstkonto-Anmeldedaten
- **Verbindung testen** — Konnektivität und Anmeldedaten vor dem Speichern überprüfen

### GPO-Registrierungsrichtlinien-URLs

Registrieren Sie nach der Konfiguration eine der angezeigten URLs als Certificate Enrollment Policy-Server in der Gruppenrichtlinie (Richtlinien für öffentliche Schlüssel → Zertifikatdienste-Client – Zertifikatregistrierungsrichtlinie), zusammen mit Zertifikatdienste-Client – Automatische Registrierung:
- **Kerberos** — Keine Anmeldeaufforderung; erfordert einen domänenverbundenen Client und den GPO-Authentifizierungstyp Kerberos
- **Benutzername/Passwort** — Fragt nach Anmeldedaten; nur für die interaktive Registrierung „Neues Zertifikat anfordern“

## Windows-Autoregistrierung (XCEP/WSTEP)

Native Windows-Zertifikatregistrierung über **MS-XCEP** (Richtlinienermittlung) und **MS-WSTEP** (Zertifikatsausstellung und -erneuerung) -- dieselben Protokolle, die ein echtes ADCS für MMC „Neues Zertifikat anfordern“, \`certreq\` und unbeaufsichtigte GPO-Autoregistrierung verwendet.

### Einrichtungs-Checkliste

Der Tab verfolgt, was konfiguriert ist und was noch benötigt wird, sowohl für den manuellen als auch den unbeaufsichtigten Registrierungspfad -- eine Zertifizierungsstelle, Richtlinienermittlung (XCEP), Zertifikatsausstellung (WSTEP) und, für unbeaufsichtigte GPO-Autoregistrierung, ein Active-Directory-Connector, Kerberos/SPNEGO und mindestens eine Vorlage mit erlaubter Autoregistrierung.

### Richtlinienermittlung (XCEP)

- **Zertifizierungsstelle** — Die CA, deren Vorlagen angekündigt werden und die über diese Konfiguration Zertifikate ausstellt
- **Gültigkeit (Tage)** — Standardgültigkeit für über WSTEP ausgestellte Zertifikate

### Kerberos / SPNEGO

Bindet die Kerberos-authentifizierten XCEP/WSTEP-Endpunkte für die stille GPO-Autoregistrierung, sodass Maschinen und Benutzer über ihr Kerberos-Ticket statt per Anmeldeaufforderung authentifiziert werden:
- **Dienstprinzipalname (SPN)** — z. B. \`HTTP/ucm.beispiel.de@BEISPIEL.DE\`
- **Keytab** — Erstellt mit \`ktpass\` oder \`ktutil\` auf dem Domänencontroller für den obigen SPN

> ⚠ Wenn die serverseitige SPNEGO-Bibliothek nicht installiert ist, funktioniert die Kerberos-Authentifizierung nicht, selbst wenn sie hier aktiviert ist -- eine Warnung wird im Tab angezeigt.

### Registrierungsrichtlinien-URLs

- **Benutzername/Passwort** — Fragt nach Anmeldedaten; für die interaktive Registrierung „Neues Zertifikat anfordern“, ohne Active Directory zu benötigen
- **Kerberos** — Keine Anmeldeaufforderung; erfordert einen domänenverbundenen Client und eine GPO-Konfiguration

### Zertifikatserneuerungs-Bindung

Neben Benutzername/Passwort und Kerberos unterstützt WSTEP die **Erneuerung per Client-Zertifikat**, analog zu echten ADCS-CES-Endpunkten: Die Erneuerungsanfrage (RST) muss mit dem privaten Schlüssel eines Zertifikats XML-DSig-signiert sein, das **UCM selbst ausgestellt hat**. Das vorgelegte Zertifikat wird **Byte für Byte** mit dem gespeicherten Zertifikat der konfigurierten CA abgeglichen — Seriennummer oder Betreff allein genügen nie. So können Windows-Clients unbeaufsichtigt mit ihrem aktuellen Zertifikat erneuern, ohne Anmeldedaten oder Kerberos-Ticket.

### SID-Sicherheitserweiterung (KB5014754)

Bei **Kerberos-authentifizierter Ausstellung** bettet UCM die AD-SID des Anfragers in die Microsoft-SID-Sicherheitserweiterung (\`szOID_NTDS_CA_SECURITY_EXT\`) des ausgestellten Zertifikats ein. Domänencontroller nutzen sie für die **starke Zertifikatszuordnung** (KB5014754) — erforderlich, seit AD die starke Zuordnung für zertifikatsbasierte Authentifizierung erzwingt (Smartcard-Anmeldung, PKINIT).

### AD-abgeleitete Betreffe

Eine Zertifikatvorlage kann sich für **Betreff aus Active Directory erstellen** (Vorlagen → Registrierung) entscheiden: Für unbeaufsichtigte GPO-Autoregistrierung werden Betreff und SAN aus dem AD-Objekt des Anfragers über den AD-Connector abgeleitet, statt vom Client eine Angabe zu verlangen -- entspricht der Konfiguration einer echten ADCS-Vorlage für die Autoregistrierung. Unabhängig davon kündigt **Autoregistrierung zulassen** die Vorlage als \`autoEnroll=true\` in der Certificate Enrollment Policy an, sodass GPO-/Kerberos-authentifizierte Clients sie beim Anmelden automatisch anfordern.
`
  }
}
