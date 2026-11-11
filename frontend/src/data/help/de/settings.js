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
          { label: "Admin", text: "admin.ucm.example.com, GUI und API (mTLS nach Richtlinie)" },
          { label: "ACME", text: "acme.ucm.example.com, /acme/* und /acme/proxy/* (ohne Client-mTLS)" },
          { label: "Wildcard TLS", text: "Konkreter Hostname (z. B. acme.ucm.example.com). Ein *.ucm.example.com-Zertifikat-SAN deckt TLS für Admin- und ACME-Vhosts ab, nicht *.ucm.example.com als Vhost eintragen" },
          { label: "Vor dem Speichern", text: "Sorgen Sie zuerst für funktionierendes DNS und TLS auf dem ACME-Vhost, Clients, die das Directory neu lesen, wechseln die URLs sofort, und Erneuerungen schlagen fehl, wenn der Vhost nicht erreichbar ist" },
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
        content: "Einstellungen › Planer listet die Hintergrundaufgaben mit Status und letzter Ausführung auf.",
        items: [
          { label: "Aufgaben", text: "Ablaufprüfungen, CRL-Aktualisierung, Webhook-Zustellung, geplante Backups, Auto-Erneuerung usw." },
          { label: "Jetzt ausführen", text: "Jede Aufgabe bei Bedarf auslösen" },
          { label: "Sichtbarkeit", text: "Letzte Ausführung, letzte Dauer und Fehleranzahl je Aufgabe" },
          { label: "Planer-Prozess (v2.251)", text: "Die Aufgaben laufen in einem eigenen Planer-Prozess, der mit dem Dienst startet und nach einem Absturz oder einem Reload innerhalb weniger Sekunden neu startet. Eine lange Aufgabe verzögert so weder Anfragen noch Worker. Er benötigt etwa 150 MB Speicher" },
          { label: "Veralteter Status (v2.251)", text: "Hat der Planer-Prozess eine Zeit lang nichts gemeldet, warnt der Tab, dass der angezeigte Status veraltet sein kann" },
          { label: "Lange Aufgaben (v2.251)", text: "Jetzt ausführen wartet bis zu 30 Sekunden auf das Ergebnis. Eine Aufgabe, die dann noch läuft, wird als gestartet und weiterhin laufend gemeldet, ihr Ergebnis erscheint bei einer späteren Aktualisierung" },
        ]
      },
      {
        title: "Geplante Backups",
        content: "Automatische, verschlüsselte Datenbank-Backups in konfigurierbarer Frequenz mit Aufbewahrung.",
        items: [
          { label: "Frequenz", text: "Täglich / wöchentlich / monatlich" },
          { label: "Aufbewahrung", text: "Backups, die älter sind als die eingestellte Anzahl Tage (standardmäßig 30), werden bereinigt" },
          { label: "Verschlüsselung", text: "Backups werden mit dem konfigurierten Backup-Passwort verschlüsselt" },
          { label: "Schlüsselableitung", text: "Automatisch (Argon2id, sofern verfügbar, PBKDF2 im FIPS-Modus), PBKDF2-HMAC-SHA256 oder Argon2id. Mit Argon2id geschriebene Archive lassen sich auf einer Instanz im FIPS-Modus nicht wiederherstellen" },
        ]
      },
      {
        title: 'Wiederherstellung (v2.251)',
        items: [
          { label: 'Ersetzen oder zusammenführen', text: 'Wiederherstellen aus Backup ersetzt die Daten hier durch die des Archivs und entfernt, was das Archiv nicht enthält; der Audit-Eintrag listet das Entfernte auf. Die API akzeptiert auch mode=merge, das das Archiv zu den Daten hier hinzufügt' },
          { label: 'Gemeinsame Sperre', text: 'Backups und Wiederherstellungen teilen eine Sperre: Eine Wiederherstellung wird abgelehnt (409), solange ein Backup läuft, und ein manuelles Backup wartet auf eine laufende Wiederherstellung' },
          { label: 'Upload-Limit', text: "Ein seit 3.0 erstelltes Archiv wird in Teilen wiederhergestellt und hat keine Größenbeschränkung, es sei denn, BACKUP_MAX_ARCHIVE_MB legt eine fest. Ein älteres Archiv wird bis BACKUP_MAX_UPLOAD_MB akzeptiert (standardmäßig 512 MB). Beide Werte werden in der Serverumgebung gesetzt, und eine Ablehnung nennt den betreffenden Parameter. Ein Reverse-Proxy vor UCM behält sein eigenes Limit für die Body-Größe" },
          { label: 'Inhalt eines Archivs', text: 'Archive enthalten ACME-Client-Orders, Genehmigungsanfragen und Schlüsselwiederherstellungsanfragen. Beim Wiederherstellen eines Archivs, das vor dieser Version geschrieben wurde, bleiben diese Zeilen hier unverändert' },
          { label: 'Gleiche Namen', text: 'Ein DNS-Anbieter, ACME-CA-Konto oder Webhook, dessen Namen hier eine andere Zeile trägt, wird als „Name (2)“ wiederhergestellt, und das von der API zurückgegebene Ergebnis listet ihn auf' },
          { label: 'Einstellungen, die eine Zeile benennen', text: 'Die SCEP- und ACME-Ausstellungs-CAs, OCSP-Responder und ähnliche Einstellungen folgen den archivierten Zeilen. Aus einem älteren Archiv auf einer anderen Installation wiederhergestellt, werden sie geleert und müssen neu gewählt werden' },
        ]
      },
      {
        title: 'Automatische Updates (v2.215)',
        content: 'Einstellungen › Updates: eine tägliche Hintergrundprüfung auf neue Versionen und eine optionale unbeaufsichtigte Installation.',
        items: [
          { label: "Kanal", text: "Stabil folgt nur finalen Releases; Release-Kandidaten nimmt zusätzlich nur rcN-Versionen an, Alpha/Beta niemals" },
          { label: 'Benachrichtigung', text: 'Eine neu verfügbare Version löst das Webhook-/E-Mail-Ereignis system.update_available aus, einmal pro Version' },
          { label: 'Auto-Installation', text: 'Standardmäßig aus. Wenn aktiviert, lädt UCM das Update zur gewählten Stunde herunter, verifiziert und installiert es und startet dann neu, nur DEB/RPM-Installationen' },
          { label: 'Prüfsumme', text: 'Eine unbeaufsichtigte Installation erfordert die veröffentlichte SHA256 des Releases zur Verifizierung; eine manuelle Installation verifiziert ebenfalls, wann immer eine Prüfsumme veröffentlicht ist' },
          { label: 'Docker', text: 'Container können sich nicht selbst aktualisieren, Prüfung und Benachrichtigung funktionieren weiterhin; ziehen Sie das neue Image, um zu aktualisieren' },
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
          { label: 'Allgemein', text: 'Syslog-Hostname (als HOSTNAME in weitergeleiteten Syslog-Nachrichten gesendet), Basis-URLs und systemweite Standardwerte' },
          { label: 'Darstellung', text: 'Theme-Auswahl (hell/dunkel/System), Akzentfarbe, Desktop-Modus' },
          { label: 'E-Mail (SMTP)', text: 'SMTP-Server, Anmeldedaten, E-Mail-Template-Editor und Ablauf-Warnbenachrichtigungen' },
          { label: 'Sicherheit', text: 'Passwortrichtlinie, Sitzungsdauer, Admin-Zugriffs-Allowlist, mTLS, Verschlüsselung privater Schlüssel; Inaktivitäts-Timeout und Kontosperre befinden sich unter Allgemein' },
          { label: 'SSO', text: 'SAML 2.0, OAuth2/OIDC und LDAP Single-Sign-On-Integration' },
          { label: 'Sicherung', text: 'Manuelle und geplante Datenbanksicherungen' },
          { label: 'Audit', text: 'Protokollaufbewahrung, Syslog-Weiterleitung, Integritätsüberprüfung' },
          { label: 'Datenbank', text: 'Aktives Backend (SQLite oder PostgreSQL), Größe, Tabellenanzahl, testen/wechseln/migrieren zwischen Backends' },
          { label: 'PostgreSQL-Schema (v2.251)', text: 'Eine PostgreSQL-URL, deren search_path ein anderes Schema als public nennt, wird unterstützt: Die Integritätsprüfung zählt die Tabellen dieses Schemas, und eine Migration dorthin gleicht seine Sequenzen an' },
          { label: 'HTTPS', text: 'TLS-Zertifikat für die UCM-Weboberfläche. Das angewendete Zertifikat wird gespeichert und bei seiner Erneuerung automatisch erneut angewendet (v2.217); das gebundene Zertifikat wird mit einer Schaltfläche zum Aufheben der Bindung angezeigt, um Erneuerungen nicht mehr zu folgen (v2.218)' },
          { label: 'Updates', text: 'Nach neuen Versionen suchen, Änderungsprotokoll anzeigen, geplante tägliche Prüfung mit optionaler unbeaufsichtigter Installation (DEB/RPM)' },
          { label: 'Webhooks', text: 'HTTP-Webhooks für Zertifikatsereignisse (Ausstellung, Widerruf, Ablauf)' },
          { label: 'Eindeutige Webhook-Namen (v2.251)', text: 'Ein bereits verwendeter Webhook-Name wird abgelehnt (409), beim Anlegen und beim Umbenennen. Das Upgrade hat frühere Duplikate in „Name (2)“, „Name (3)“ umbenannt, die ältesten zuerst' },
          { label: 'Bereitstellung', text: 'Deploy-Ziele stellen wiederverwendbare SSH-/SFTP-Verbindungen oder eine HTTP-API-Anfrage (v2.252) bereit; Zertifikats- und CRL-Bereitstellungen legen eigene Pfade und optionale Reload-Befehle fest (nur Admins, v2.215)' },
          { label: 'Active Directory', text: 'UCMs eigene AD/LDAP-Verbindung für zertifikatsbezogene Abfragen (Kerberos-Prinzipalauflösung, AD-abgeleitete Betreffe)' },
          { label: 'Windows-Autoregistrierung', text: 'MS-XCEP/MS-WSTEP native Windows-Registrierung: Richtlinienermittlung, Zertifikatsausstellung und Kerberos/SPNEGO-Bindung' },
          { label: 'Info', text: 'Systeminformationen, Links & Ressourcen und UCM unterstützen verweisen auf Ko-fi (Administratoren sehen zudem einmal pro UCM-Version eine ausblendbare Ko-fi-Karte). Mit admin:system listet FIPS-Bereitschaft prüfen auf, was der FIPS-Modus auf dieser Instanz ablehnen würde, mit je einer Abhilfe, und ändert nichts' },
          { label: 'Compliance-Profile', text: 'Unter Info, mit admin:system: Profil prüfen listet auf, was ANSSI, BSI oder EU ACM (Regeln, die sich an einem Referenztext orientieren) auf dieser Instanz ablehnen oder davon abraten würden, und ändert nichts. Mit admin:settings legt Standardprofil für neue CAs fest, welches Profil eine CA erhält, wenn keines gewählt wird; bestehende CAs bleiben unverändert' },
        ]
      },
      {
        title: 'Deploy-Hooks (v2.215)',
        content: 'Einstellungen › Bereitstellung (nur Admins): wiederverwendbare SSH-/SFTP-Verbindungen oder HTTP-API-Anfragen für Zertifikats- und CRL-Bereitstellungen. Pfade und optionale Reload-Befehle werden an jeder SSH-Bereitstellung konfiguriert.',
        items: [
          { label: 'Ziel', text: 'Host, Port, SSH-Benutzer. UCM generiert einen ed25519-Schlüssel (den angezeigten öffentlichen Schlüssel auf dem Ziel installieren) oder akzeptiert einen importierten privaten Schlüssel, verschlüsselt gespeichert' },
          { label: 'HTTP-API-Ziel (v2.252)', text: 'URL, Methode (POST, PUT, PATCH), Anfrage-Header, verschlüsselt gespeichert und nie wieder angezeigt, und eine Body-Vorlage mit {{cert_pem}}, {{fullchain_pem}}, {{cn}}, {{serial}}... plus den Filtern |json, |jsonstr, |b64 und |urlencode. Ein JSON-Body wird beim Speichern geprüft. Der private Schlüssel ({{key_pem}}) wird nur mit ausdrücklichem Opt-in des Ziels und einer https-URL gesendet; das TLS-Zertifikat wird immer geprüft, bei selbstsignierter Appliance gegen einen eingefügten Vertrauensanker. Weiterleitungen werden abgelehnt, Cloud-Metadaten- und Loopback-Adressen blockiert. Nur Zertifikate: CRLs bleiben auf SSH-Zielen' },
          { label: 'Host-Key', text: 'Wird bei der ersten erfolgreichen Verbindung gepinnt (Trust-on-first-use); jede spätere Änderung lässt die Verbindung fehlschlagen (fail-closed). Bei Änderung des Hosts wird neu gepinnt' },
          { label: 'Reload-Befehl', text: 'Ein optionaler Befehl, der pro Zertifikats- oder CRL-Verknüpfung konfiguriert und nach einer erfolgreichen Übertragung ausgeführt wird (z. B. systemctl reload nginx): exit 0 = Erfolg, kein Templating' },
          { label: 'Verknüpfungen', text: 'Zertifikate werden aus der Zertifikat-Detailansicht verknüpft, CRLs unter CRL & OCSP. Jede Verknüpfung besitzt eigene Pfade, Dateioptionen und ihren Reload-Befehl' },
          { label: 'Zustellung', text: 'Übertragungen laufen asynchron über eine dauerhafte Warteschlange mit Wiederholungen und Backoff; Status pro Zustellung, manuelles „Jetzt bereitstellen" und Wiederholen, vollständiger Audit-Trail' },
          { label: 'Minimale Rechte', text: 'Verwenden Sie auf jedem Ziel ein dediziertes SSH-Konto: Schreibzugriff auf die Zertifikatspfade und die Berechtigung, den Dienst neu zu laden, mehr nicht' },
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
          { label: 'Felder', text: 'Domänencontroller (einer pro Zeile, jeweils mit eigenem Hostnamen, der Reihe nach mit Failover versucht), Port, LDAPS mit optionaler CA-Verifizierung, Basis-DN, Bind-DN und Passwort (beide erforderlich, solange der Connector aktiviert ist)' },
          { label: 'Verbindung testen', text: 'Verbindung und Anmeldedaten vor dem Speichern überprüfen' },
          { label: 'GPO-Registrierungs-URLs', text: 'Kerberos- und Benutzername/Passwort-URLs für die Zertifikatregistrierungsrichtlinie zur Registrierung in der Gruppenrichtlinie' },
          { label: 'Zustandsprüfung', text: 'Jeder Domänencontroller wird im Intervall der Zustandsprüfung mit einem echten Bind geprüft; ein nicht erreichbarer wird bei der Registrierung übersprungen, bis er sich erholt. Das Ergebnis erscheint in der Einstellungszeile und bei jedem DC' },
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
          { label: 'ML-DSA-Vorlagen (v2.248)', text: 'Werden über ihre Schlüsselalgorithmus-OID mit dem Microsoft Software Key Storage Provider angekündigt, sind noch nicht mit einem echten Windows-Client getestet und im FIPS-Modus ausgeblendet. Die zertifikatsbasierte Erneuerung kann kein ML-DSA-Zertifikat verwenden (XML-DSig kennt keine ML-DSA-Signatur): ein neues Zertifikat registrieren' },
          { label: 'ECDSA-Vorlagen (v2.251)', text: 'Werden in Richtlinienschema 3 mit ihrer Kurve (ECDSA_P256, ECDSA_P384, ECDSA_P521) als Signaturschlüssel und Anfrage-Hash angekündigt, dem stärkeren aus Vorlagen-Digest und dem zur Kurve passenden. RSA-Vorlagen außerhalb des FIPS-Modus bleiben bei Schema 2' },
          { label: 'Vorlage und Schlüssel (v2.251)', text: 'Der Anfrageschlüssel muss zur Vorlage passen, unter der ausgestellt wird: dieselbe Kurve oder derselbe ML-DSA-Satz, oder ein mindestens ebenso langer RSA-Schlüssel. Eine P-384-Anfrage wird also nicht mehr unter einer P-256-Vorlage mit gleichem EKU ausgestellt. Der Anfrage-Umschlag, den Windows mit einem ECDSA-Schlüssel signiert, wird akzeptiert' },
          { label: 'Erneuerung von Windows (v2.248)', text: 'certreq ... Renew authentifiziert sich mit dem zu erneuernden Zertifikat als TLS-Client-Zertifikat: mTLS muss aktiviert und die WSTEP-CA oder eine ihrer übergeordneten CAs vertrauenswürdig sein. Eine Erneuerung behält Vorlage und EKUs des erneuerten Zertifikats' },
          { label: 'Kerberos in Docker (v2.251)', text: 'Die Docker-Images enthalten das Kerberos-Backend von pyspnego, sodass die Kerberos-Bindung in einem Container wie bei den DEB- und RPM-Installationen funktioniert' },
        ]
      },
      {
        title: 'Auto-Erneuerung',
        items: [
          { label: 'Quellen', text: 'Der Planer erneuert Zertifikate, deren privaten Schlüssel der Server hält: standardmäßig die über das Formular oder eine signierte Anfrage ausgestellten („manuell") sowie SCEP-, ACME- und EST-Registrierungen mit servergeneriertem Schlüssel. Geräte, die ihren eigenen Schlüssel halten, erneuern über ihr Protokoll' },
          { label: 'Genehmigung ausstehend', text: 'Ein Zertifikat, dessen Erneuerung zur Genehmigung eingereiht ist, bleibt dieser Entscheidung überlassen, solange sie vor dem Ablauf des Zertifikats fallen kann' },
          { label: 'Inzwischen erneuert', text: 'Ein Zertifikat, das ein Operator während des Durchlaufs erneuert hat, wird nicht ein zweites Mal erneuert; ein während des Durchlaufs gelöschtes wird übersprungen' },
          { label: 'Kurzlebige Zertifikate', text: 'Die Erneuerung beginnt nie vor dem letzten Drittel der Laufzeit eines Zertifikats: ein 27-Tage-Zertifikat wird 9 Tage vor Ablauf erneuert, nicht schon ab der Ausstellung' },
          { label: 'Jetzt ausführen', text: 'Startet sofort einen Erneuerungsdurchlauf und meldet die ablaufenden Zertifikate, die er unberührt ließ, nach Grund gezählt: noch nicht im letzten Drittel der Laufzeit, privater Schlüssel nicht beim Server, Quelle nicht ausgewählt' },
          { label: 'Signatur-Digest (v2.251)', text: 'Eine Erneuerung behält den Digest des ursprünglichen Zertifikats, solange er mindestens dem zum CA-Schlüssel passenden entspricht und die Richtlinien ihn erlauben, sonst folgt sie der Ausstellungsregel: Unter einer P-384- oder P-521-CA wird ein SHA-256-Original mit SHA-384 oder SHA-512 erneuert' },
        ]
      },

    ],
    tips: [
      'Prüfen Sie über die Statusleiste unten, ob der Dienst antwortet',
      'Testen Sie SMTP-Einstellungen, bevor Sie sich auf E-Mail-Benachrichtigungen verlassen',
      'Passen Sie das E-Mail-Template mit Ihrem Branding über den integrierten HTML/Text-Editor an',
      'Planen Sie automatische Sicherungen für Produktionsumgebungen',
      'Der Wechsel SQLite ↔ PostgreSQL ist bidirektional: die UI führt Sicherheitsprüfungen (Treiber geladen, Ziel erreichbar, Ziel leer) vor der Migration durch',
    ],
    warnings: [
      'Das Ändern des HTTPS-Zertifikats erfordert einen Dienstneustart',
      'Das Ändern von Sicherheitseinstellungen kann Benutzer aussperren: überprüfen Sie den Zugriff vor dem Speichern',
    ],
  },
  helpGuides: {
    title: 'Einstellungen',
    content: `
## Übersicht

Systemweite Konfiguration in Tabs organisiert. Änderungen werden sofort wirksam, sofern nicht anders angegeben.

## Allgemein

- **Syslog-Hostname**: Wird als HOSTNAME in weitergeleiteten Syslog-Nachrichten gesendet; leer gilt der Hostname der Maschine
- **Basis-URL**: Kanonische HTTPS-URL der Admin-Oberfläche und der API; andere Hostnamen und IPs leiten dorthin um
- **Protokoll-Basis-URL**: In CDP- und OCSP-Adressen geschriebene Basis-URL; http:// vermeidet TLS-Verifizierungsschleifen, leer gilt die Basis-URL
- **HTTP-Protokoll-Port**: Einfacher HTTP-Port, der CDP und OCSP ausliefert; 0 deaktiviert ihn, eine Änderung erfordert einen Neustart
- **Öffentlicher ACME-Vhost**: Konkreter Hostname in den ACME-Directory-URLs (z. B. \`acme.ucm.example.com\`: nicht \`*.ucm.example.com\`). Ein Wildcard-**TLS-Zertifikat-SAN** \`*.ucm.example.com\` deckt sowohl \`admin.ucm.example.com\` als auch \`acme.ucm.example.com\` ab. Konfigurieren Sie DNS und TLS für den ACME-Vhost **vor** dem Speichern: Clients, die das Directory neu lesen, wechseln die URLs sofort.

## Darstellung

- **Theme**: Hell, Dunkel oder System (folgt OS-Präferenz)
- **Akzentfarbe**: Primärfarbe für Schaltflächen, Links und Hervorhebungen
- **Desktop-Modus erzwingen**: Responsives mobiles Layout deaktivieren

## E-Mail (SMTP)

SMTP für E-Mail-Benachrichtigungen konfigurieren (Ablaufwarnungen, Benutzereinladungen):
- **SMTP-Host** und **Port**
- **Benutzername** und **Passwort**
- **Verschlüsselung**: Keine, STARTTLS oder SSL/TLS
- **Absenderadresse**: E-Mail-Adresse des Absenders
- **Inhaltstyp**: HTML, Klartext oder Beides
- **Warnungsempfänger**: Mehrere Empfänger über die Tag-Eingabe hinzufügen

Klicken Sie auf **Testen**, um eine Test-E-Mail zu senden und die Konfiguration zu überprüfen.

### E-Mail-Template-Editor

Klicken Sie auf **Template bearbeiten**, um den Split-Pane-Template-Editor in einem schwebenden Fenster zu öffnen:
- **HTML-Tab**: HTML-E-Mail-Template bearbeiten mit Live-Vorschau rechts
- **Klartext-Tab**: Klartextversion für E-Mail-Clients bearbeiten, die kein HTML unterstützen
- Verfügbare Variablen: \`{{title}}\`, \`{{content}}\`, \`{{datetime}}\`, \`{{instance_url}}\`, \`{{logo}}\`, \`{{title_color}}\`
- Klicken Sie auf **Auf Standard zurücksetzen**, um das integrierte UCM-Template wiederherzustellen
- Das Fenster ist in der Größe veränderbar und verschiebbar für komfortables Bearbeiten

### Ablaufwarnungen

Wenn SMTP konfiguriert ist, aktivieren Sie automatische Zertifikatsablaufwarnungen:
- Warnungen ein-/ausschalten
- Warnschwellenwerte auswählen (90T, 60T, 30T, 14T, 7T, 3T, 1T)
- **Jetzt prüfen** ausführen, um einen sofortigen Scan auszulösen
- **Über ACME ausgestellte Zertifikate auslassen**: lässt die vom ACME-Server von UCM ausgestellten Zertifikate aus, die ihre Clients erneuern; standardmäßig aus

## Sicherheit

### Passwortrichtlinie
- Mindestlänge (6-32 Zeichen)
- Großbuchstaben, Zahlen, Sonderzeichen erfordern

### Sitzungsverwaltung
- Sitzungsdauer (Stunden, unabhängig von der Aktivität); das Inaktivitäts-Timeout befindet sich unter Allgemein

### Kontosperre
- Maximale Anmeldeversuche und Sperrdauer, unter Allgemein: Sie sperren das Konto, nicht die IP-Adresse

### Admin-Zugriffs-Allowlist
Beschränkt die Weboberfläche und die Management-API auf aufgelistete IP-Adressen und CIDR-Netzwerke; PKI-Protokolle bleiben von überall erreichbar. Siehe die Anleitung zu den Sicherheitseinstellungen.

### 2FA-Durchsetzung
Alle Benutzer zur Aktivierung der Zwei-Faktor-Authentifizierung verpflichten.

### Verschlüsselung privater Schlüssel
Alle in der Datenbank gespeicherten privaten Schlüssel mit AES-128 (Fernet, mit HMAC-SHA256) verschlüsseln, geschützt durch eine Master-Key-Datei. Der Bereich zeigt den Verschlüsselungsstatus und die Zähler **verschlüsselt / unverschlüsselt**. Zwei Opt-in-Umgebungsvariablen machen fehlende Schlüssel beim Start fatal: \`UCM_REQUIRE_DB_ENCRYPTION_KEY\` (Verschlüsselung von Integrationsgeheimnissen) und \`UCM_REQUIRE_KEY_ENCRYPTION\` (Verschlüsselung privater Schlüssel).
Eine neue Installation erzeugt den Master-Key beim ersten Start (in einem Container nur, wenn \`/etc/ucm\` ein eigenes Volume ist); der Bereich Sicherheit der Einstellungen zeigt den Verschlüsselungsstatus, und die Übersicht zeigt ein Banner, solange kein Schlüssel geladen ist.

> 💡 Sicherheitskritische Einstellungen (Sitzung, Sperrung, HSTS, öffentliche URL, Passwortrichtlinie) erfordern die Berechtigung **admin:settings**: die Felder sind für Operatoren gesperrt.

> ⚠ Eine Liste, die Ihre eigene Adresse nicht enthält, wird abgelehnt. Wenn Sie trotzdem den Zugriff verlieren, setzen Sie \`UCM_ADMIN_ALLOWLIST_DISABLE=1\` und starten Sie UCM neu.

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
Klicken Sie auf **Sicherung erstellen**, um einen Datenbank-Snapshot zu erstellen. Sicherungen enthalten die Zertifikate, CAs, Schlüssel und Einstellungen; das Audit-Protokoll und andere Verlaufstabellen sind nicht enthalten.

### Geplante Sicherung
Automatische Sicherungen konfigurieren:
- Häufigkeit (täglich, wöchentlich, monatlich)
- Aufbewahrung in Tagen: ältere Sicherungen werden bereinigt (standardmäßig 30)
- **Schlüsselableitung**: Automatisch (Argon2id, sofern verfügbar, PBKDF2 im FIPS-Modus), PBKDF2-HMAC-SHA256 oder Argon2id. Mit Argon2id geschriebene Archive lassen sich auf einer Instanz im FIPS-Modus nicht wiederherstellen

### Wiederherstellen
Laden Sie eine Sicherungsdatei hoch, um UCM auf einen früheren Zustand zurückzusetzen.

- Backups und Wiederherstellungen teilen eine Sperre: Eine Wiederherstellung wird abgelehnt (409), solange ein Backup läuft, und ein manuelles Backup wartet auf eine laufende Wiederherstellung
- Ein seit 3.0 erstelltes Archiv wird in Teilen wiederhergestellt, ohne Größenbeschränkung, es sei denn, \`BACKUP_MAX_ARCHIVE_MB\` legt eine fest; ein älteres Archiv wird bis \`BACKUP_MAX_UPLOAD_MB\` akzeptiert (standardmäßig 512 MB). Beide Werte werden in der Serverumgebung gesetzt, und eine Ablehnung nennt den betreffenden Parameter; ein Reverse-Proxy vor UCM behält sein eigenes Limit für die Body-Größe
- Archive enthalten ACME-Client-Orders, Genehmigungsanfragen und Schlüsselwiederherstellungsanfragen (v2.251)
- Ein DNS-Anbieter, ACME-CA-Konto oder Webhook, dessen Namen hier eine andere Zeile trägt, wird als \`name (2)\` wiederhergestellt
- Die API akzeptiert auch \`mode=merge\`, das das Archiv zu den Daten hier hinzufügt, statt sie zu ersetzen

> ⚠ Die Wiederherstellung einer Sicherung ersetzt ALLE aktuellen Daten.

## Audit

- **Protokollaufbewahrung**: Alte Protokolle nach N Tagen automatisch bereinigen
- **Syslog-Weiterleitung**: Ereignisse an einen Remote-Syslog-Server senden (UDP/TCP/TLS)
- **Integritätsüberprüfung**: Die Hash-Kette prüfen, die jeden Audit-Eintrag verbindet; die Kette ist immer aktiv, es gibt nichts zu aktivieren

## Datenbank

UCM unterstützt zwei Datenbank-Backends:

- **SQLite** (Standard): dateibasiert, ohne Konfiguration, ideal für Einzelknoten
- **PostgreSQL 13+**: empfohlen für Hochverfügbarkeit, Multi-Instanz oder wenn Sie bereits einen verwalteten PG-Cluster betreiben

Das aktive Backend wird über die Umgebungsvariable \`DATABASE_URL\` ausgewählt. Wenn nicht gesetzt, verwendet UCM SQLite unter \`DATA_DIR/ucm.db\`.

### Statusbereich
- Aktives Backend (sqlite / postgresql) und seine Engine-Version
- Datenbankgröße und Tabellenanzahl

### Verbindung testen
Validieren Sie eine \`DATABASE_URL\` (z. B. \`postgresql://user:pass@host:5432/ucm\`) vor dem Wechsel. Der Test öffnet eine echte Verbindung und meldet jeden Fehler. PostgreSQL-Server älter als Version 13 werden abgelehnt, UCM erfordert PostgreSQL 13 oder neuer.

### Backend wechseln
Speichert \`DATABASE_URL\` in \`/etc/ucm/ucm.env\` (DEB/RPM) und startet UCM neu. Nur die Tabellen für Konten, Rollen, SSO und MFA werden ins neue Backend kopiert, sodass Sie sich weiterhin anmelden können; verwenden Sie zuerst **Migrieren**, wenn Sie Ihre übrigen Daten behalten möchten.

### Daten migrieren
Kopiert alle Zeilen vom aktuellen zum Ziel-Backend. Funktioniert in beide Richtungen (SQLite ↔ PostgreSQL):

1. Die Quelldatenbank wird unter \`/opt/ucm/data/backups/db_migration/\` gesichert
2. Das Schema wird auf dem Ziel über SQLAlchemy erstellt
3. FK-Prüfungen werden während des Bulk-Loads deaktiviert
4. Spalten werden nach Namen zugeordnet; nur die bekannten Legacy-Spalten entfallen, und jede andere Spalte, die dem Ziel fehlt, lässt die Migration ablehnen
5. PostgreSQL-Sequenzen werden nach dem Laden zurückgesetzt
6. Der Dienst startet automatisch neu (DEB/RPM): auf Docker setzen Sie \`DATABASE_URL\` in Ihrer Compose-Datei und starten den Container manuell neu

**Sicherheitsprüfungen (schneller Abbruch, Quelle unangetastet):**
- Das Ziel muss leer sein. Wenn eine seiner Tabellen bereits Zeilen enthält, wird die Migration mit HTTP 409 abgelehnt und ein Bereinigungshinweis ausgegeben:
  - PostgreSQL: \`psql ... -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'\`
  - PostgreSQL in einem anderen Schema als \`public\` (ein \`search_path\` in der URL): Der Hinweis nennt dieses Schema, dessen Sequenzen die Migration angleicht (v2.251)
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
- **Auto-Update**: Auf unterstützten Installationen (DEB/RPM) klicken Sie auf **Update installieren**, um die neueste Version automatisch herunterzuladen und zu installieren
- **Update-Kanal**: stabil, Vorabversion (Release-Kandidaten) oder dev

## Webhooks

HTTP-Webhooks konfigurieren, um externe Systeme bei Ereignissen zu benachrichtigen:

### Unterstützte Ereignisse
- Zertifikat ausgestellt, widerrufen, erneuert, bald ablaufend, abgelaufen, importiert, gelöscht
- CA erstellt, aktualisiert, gelöscht
- CSR eingereicht, genehmigt, abgelehnt
- Template erstellt, aktualisiert
- ACME-Preflight, Erneuerung fehlgeschlagen, Widerruf fehlgeschlagen
- Update verfügbar, gestartet, installiert, fehlgeschlagen

Zertifikatsimporte und Template-Änderungen über die Weboberfläche lösen ihr Ereignis nicht aus.

### Authentifizierung

Optionale ausgehende Authentifizierung (alle gelten zusätzlich zur optionalen HMAC-Signatur):

- **Keine**: Kein Auth-Header (öffentliche Webhooks)
- **Bearer**: Authorization: Bearer {token}
- **Basic**: Authorization: Basic base64(username:password)
- **API Key**: Benutzerdefinierter Header (z. B. X-Api-Key: {token})
- **Custom**: Authorization: {scheme} {token} (z. B. auth-key VALUE)

Tokens werden verschlüsselt gespeichert und nie in der UI zurückgegeben.

### Webhook erstellen
1. Klicken Sie auf **Webhook hinzufügen**
2. Geben Sie die **URL** ein (HTTPS empfohlen; http:// wird akzeptiert)
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

Einstellungen › Planer zeigt die Hintergrundaufgaben.

- Aufgabenliste mit **Status**, **letzter Ausführung**, **Dauer** und **Fehlern**
- **Jetzt ausführen** für jede Aufgabe: Es wartet bis zu 30 Sekunden, und eine Aufgabe, die dann noch läuft, wird als gestartet gemeldet, ihr Ergebnis erscheint bei einer späteren Aktualisierung
- Umfasst Ablauf, CRL, Webhook-Zustellung, Backups, Auto-Erneuerung…
- **Planer-Prozess** (v2.251): Die Aufgaben laufen in einem eigenen Prozess, der mit dem Dienst startet und nach einem Absturz oder einem Reload innerhalb weniger Sekunden neu startet. Eine lange Aufgabe verzögert so weder Anfragen noch Worker. Eine Warnung erscheint, wenn er eine Zeit lang nichts gemeldet hat

## Auto-Erneuerung

Die Einstellungen zur Auto-Erneuerung steuern den Erneuerungsplaner.

- **Quellen**: der Planer erneuert Zertifikate, deren privaten Schlüssel der Server hält: standardmäßig die über das Formular oder eine signierte Anfrage ausgestellten („manuell") sowie SCEP-, ACME- und EST-Registrierungen mit servergeneriertem Schlüssel. Geräte, die ihren eigenen Schlüssel halten, erneuern über ihr Protokoll
- **Genehmigung ausstehend**: ein Zertifikat, dessen Erneuerung zur Genehmigung eingereiht ist, bleibt dieser Entscheidung überlassen, solange sie vor dem Ablauf des Zertifikats fallen kann
- **Inzwischen erneuert**: ein Zertifikat, das ein Operator während des Durchlaufs erneuert hat, wird nicht ein zweites Mal erneuert; ein während des Durchlaufs gelöschtes wird übersprungen
- **Kurzlebige Zertifikate**: die Erneuerung beginnt nie vor dem letzten Drittel der Laufzeit eines Zertifikats: ein 27-Tage-Zertifikat wird 9 Tage vor Ablauf erneuert, nicht schon ab der Ausstellung
- **Jetzt ausführen**: startet sofort einen Erneuerungsdurchlauf und meldet die ablaufenden Zertifikate, die er unberührt ließ, nach Grund gezählt: noch nicht im letzten Drittel der Laufzeit, privater Schlüssel nicht beim Server, Quelle nicht ausgewählt

## Geplante Backups

Einstellungen › Sicherung ermöglicht automatische Backups.

- Frequenz **täglich / wöchentlich / monatlich**
- **Aufbewahrung**: Backups, die älter sind als die eingestellte Anzahl Tage, werden bereinigt
- Backups mit dem Backup-Passwort **verschlüsselt**


## Active-Directory-Connector

UCMs eigene LDAP-Verbindung zu Active Directory, unabhängig von einem unter SSO konfigurierten LDAP-Anbieter. Jener dient der Anmeldung bei UCM; dieser hier wird für zertifikatsbezogene AD-Abfragen verwendet und funktioniert unabhängig davon, ob SSO überhaupt konfiguriert ist.

- **Zweck**: Löst ein Kerberos-Maschinen- oder Benutzerprinzipal zu seinem AD-Objekt auf, damit UCM einen Zertifikatsbetreff/SAN ableiten kann, genau wie eine echte Windows-CA
- **Domänencontroller**: Einer pro Zeile, jeweils mit eigenem Hostnamen, der Reihe nach versucht: Abfragen wechseln zum nächsten, wenn ein DC ausfällt. Ein reiner Domänenname scheitert an der Zertifikatsprüfung, da ein Domänencontroller-Zertifikat nur den eigenen Host nennt
- **LDAPS**: Umschalten, um LDAP über SSL/TLS zu verwenden; **SSL-Zertifikat prüfen** validiert das Zertifikat des DC (optional gegen ein benutzerdefiniertes CA-Bundle, wenn es nicht öffentlich vertrauenswürdig ist)
- **Basis-DN** und **Bind-DN / Passwort**: Für Abfragen verwendete Dienstkonto-Anmeldedaten; Bind-DN und Passwort sind beide erforderlich, solange der Connector aktiviert ist
- **Verbindung testen**: Konnektivität und Anmeldedaten vor dem Speichern überprüfen
- **Intervall der Zustandsprüfung**: Jeder Domänencontroller wird in diesem Intervall mit einem echten Bind geprüft; ein nicht erreichbarer wird bei der Registrierung übersprungen, bis er sich erholt. Das Ergebnis erscheint in der Einstellungszeile und bei jedem DC

### GPO-Registrierungsrichtlinien-URLs

Registrieren Sie nach der Konfiguration eine der angezeigten URLs als Certificate Enrollment Policy-Server in der Gruppenrichtlinie (Richtlinien für öffentliche Schlüssel → Zertifikatdienste-Client – Zertifikatregistrierungsrichtlinie), zusammen mit Zertifikatdienste-Client – Automatische Registrierung:
- **Kerberos**: Keine Anmeldeaufforderung; erfordert einen domänenverbundenen Client und den GPO-Authentifizierungstyp Kerberos
- **Benutzername/Passwort**: Fragt nach Anmeldedaten; nur für die interaktive Registrierung „Neues Zertifikat anfordern“

## Windows-Autoregistrierung (XCEP/WSTEP)

Native Windows-Zertifikatregistrierung über **MS-XCEP** (Richtlinienermittlung) und **MS-WSTEP** (Zertifikatsausstellung und -erneuerung) -- dieselben Protokolle, die ein echtes ADCS für MMC „Neues Zertifikat anfordern“, \`certreq\` und unbeaufsichtigte GPO-Autoregistrierung verwendet.

### Einrichtungs-Checkliste

Der Tab verfolgt, was konfiguriert ist und was noch benötigt wird, sowohl für den manuellen als auch den unbeaufsichtigten Registrierungspfad -- eine Zertifizierungsstelle, Richtlinienermittlung (XCEP), Zertifikatsausstellung (WSTEP) und, für unbeaufsichtigte GPO-Autoregistrierung, ein Active-Directory-Connector, Kerberos/SPNEGO und mindestens eine Vorlage mit erlaubter Autoregistrierung.

### Richtlinienermittlung (XCEP)

- **Zertifizierungsstelle**: Die CA, deren Vorlagen angekündigt werden und die über diese Konfiguration Zertifikate ausstellt
- **Gültigkeit (Tage)**: Gültigkeit der über WSTEP ausgestellten Zertifikate, wenn die Anfrage zu keiner Vorlage passt; sonst gilt die Gültigkeit der passenden Vorlage

Eine Vorlage mit dem Schlüsseltyp **ML-DSA** wird über ihre Schlüsselalgorithmus-OID angekündigt, mit dem Microsoft Software Key Storage Provider und einer reinen Signatur-Schlüsselspezifikation. Sie ist im FIPS-Modus ausgeblendet, und die Registrierung durch einen echten Windows-Client wurde noch nicht getestet.

Eine **ECDSA**-Vorlage wird in Richtlinienschema 3 mit ihrer Kurve (\`ECDSA_P256\`, \`ECDSA_P384\`, \`ECDSA_P521\`) als Signaturschlüssel und Anfrage-Hash angekündigt, dem stärkeren aus Vorlagen-Digest und dem zur Kurve passenden. RSA-Vorlagen außerhalb des FIPS-Modus bleiben bei Schema 2. Der Anfrageschlüssel muss zur Vorlage passen, unter der ausgestellt wird: dieselbe Kurve oder derselbe ML-DSA-Satz, oder ein mindestens ebenso langer RSA-Schlüssel (v2.251).

### Kerberos / SPNEGO

Bindet die Kerberos-authentifizierten XCEP/WSTEP-Endpunkte für die stille GPO-Autoregistrierung, sodass Maschinen und Benutzer über ihr Kerberos-Ticket statt per Anmeldeaufforderung authentifiziert werden:
- **Dienstprinzipalname (SPN)**: z. B. \`HTTP/ucm.beispiel.de@BEISPIEL.DE\`
- **Keytab**: Erstellt mit \`ktpass\` oder \`ktutil\` auf dem Domänencontroller für den obigen SPN

> ⚠ Wenn die serverseitige SPNEGO-Bibliothek nicht installiert ist, funktioniert die Kerberos-Authentifizierung nicht, selbst wenn sie hier aktiviert ist -- eine Warnung wird im Tab angezeigt.

Die Docker-Images enthalten dieses Backend seit v2.251.

### Registrierungsrichtlinien-URLs

- **Benutzername/Passwort**: Fragt nach Anmeldedaten; für die interaktive Registrierung „Neues Zertifikat anfordern“, ohne Active Directory zu benötigen
- **Kerberos**: Keine Anmeldeaufforderung; erfordert einen domänenverbundenen Client und eine GPO-Konfiguration

### Zertifikatserneuerungs-Bindung

Neben Benutzername/Passwort und Kerberos unterstützt WSTEP die **Erneuerung per Client-Zertifikat**, analog zu echten ADCS-CES-Endpunkten: Die Erneuerungsanfrage (RST) muss mit dem privaten Schlüssel eines Zertifikats XML-DSig-signiert sein, das **UCM selbst ausgestellt hat**. Das vorgelegte Zertifikat wird **Byte für Byte** mit dem gespeicherten Zertifikat der konfigurierten CA abgeglichen, Seriennummer oder Betreff allein genügen nie. So können Windows-Clients unbeaufsichtigt mit ihrem aktuellen Zertifikat erneuern, ohne Anmeldedaten oder Kerberos-Ticket.

XML-DSig kennt keine ML-DSA-Signaturmethode, daher kann ein **ML-DSA**-Zertifikat auf diesem Weg nicht erneuern: UCM nennt den Schlüssel in der Ablehnung, und der Client registriert stattdessen ein neues Zertifikat.

Windows kann auch mit \`certreq ... Renew\` erneuern, authentifiziert durch das zu erneuernde Zertifikat als TLS-Client-Zertifikat: mTLS aktivieren, mit der WSTEP-CA oder einer ihrer übergeordneten CAs als vertrauenswürdig. Eine Erneuerung behält Vorlage und EKUs des erneuerten Zertifikats (v2.248).

### SID-Sicherheitserweiterung (KB5014754)

Bei **Kerberos-authentifizierter Ausstellung** bettet UCM die AD-SID des Anfragers in die Microsoft-SID-Sicherheitserweiterung (\`szOID_NTDS_CA_SECURITY_EXT\`) des ausgestellten Zertifikats ein. Domänencontroller nutzen sie für die **starke Zertifikatszuordnung** (KB5014754): erforderlich, seit AD die starke Zuordnung für zertifikatsbasierte Authentifizierung erzwingt (Smartcard-Anmeldung, PKINIT).

### AD-abgeleitete Betreffe

Eine Zertifikatvorlage kann sich für **Betreff aus Active Directory erstellen** (Vorlagen → Registrierung) entscheiden: Für unbeaufsichtigte GPO-Autoregistrierung werden Betreff und SAN aus dem AD-Objekt des Anfragers über den AD-Connector abgeleitet, statt vom Client eine Angabe zu verlangen -- entspricht der Konfiguration einer echten ADCS-Vorlage für die Autoregistrierung. Unabhängig davon kündigt **Autoregistrierung zulassen** die Vorlage als \`autoEnroll=true\` in der Certificate Enrollment Policy an, sodass GPO-/Kerberos-authentifizierte Clients sie beim Anmelden automatisch anfordern.

## Info

- **Systeminformationen**, **Links & Ressourcen** und **UCM unterstützen** verweisen auf Ko-fi. Administratoren sehen zudem einmal pro UCM-Version eine ausblendbare Ko-fi-Karte
- **FIPS-Bereitschaft prüfen** (admin:system): listet auf, was der FIPS-Modus auf dieser Instanz ablehnen würde (scrypt-Passwort-Hashes, Ed25519-Autoritäten, Argon2id-Backups, PostgreSQL ohne TLS ...), mit je einer Abhilfe. Es wird nichts geändert
`
  }
}
