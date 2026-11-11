export default {
  helpContent: {
    title: 'ACME',
    subtitle: 'Automatisierte Zertifikatsverwaltung',
    overview: 'UCM unterstützt zwei ACME-Modi: ACME-Client für öffentliche Zertifikate von jeder RFC 8555-konformen CA (Let\'s Encrypt, ZeroSSL, HARICA, usw.) und lokaler ACME-Server für interne PKI-Automatisierung mit Multi-CA-Domänenzuordnung.',
    sections: [
      {
        title: "Renewal Information (ARI, RFC 9773)",
        content: "Der lokale ACME-Server stellt eine renewalInfo-Ressource bereit, damit Clients den idealen Zeitpunkt zur Erneuerung jedes Zertifikats erfahren.",
        items: [
          { label: "Vorgeschlagenes Fenster", text: "Liefert ein Start/Ende-Fenster zentriert vor dem Ablauf, um Erneuerungen zeitlich zu verteilen" },
          { label: "Widerruf", text: "Ein widerrufenes Zertifikat liefert ein Fenster in der Vergangenheit → konforme Clients erneuern sofort" },
          { label: "Ohne Authentifizierung", text: "renewalInfo ist ein einfacher GET, weder Konto noch JWS erforderlich (RFC 9773)" },
          { label: "ACME-Proxy (v2.252)", text: "Für ein über den Proxy ausgestelltes Zertifikat wird das Fenster der Upstream-CA mit ihrem Retry-After weitergereicht und bis zu einer Stunde vorgehalten. Das Fenster wird lokal berechnet, wenn die CA kein renewalInfo ankündigt oder keine brauchbare Antwort gibt oder wenn das Zertifikat in UCM widerrufen ist" },
        ]
      },
      {
        title: 'ACME-Client',
        items: [
          { label: 'Client', text: 'Zertifikate von jeder ACME-CA anfordern, Let\'s Encrypt, ZeroSSL, HARICA oder benutzerdefiniert' },
          { label: 'Order-Tab (v2.219)', text: 'Die Client-Orders haben einen eigenen Seitenleisten-Tab "Let\'s Encrypt orders" mit Zähler sichtbar/gesamt und Statusfilter, analog zur Ansicht Local orders' },
          { label: 'Externe CA-Konten', text: 'Ein oder mehrere Konten pro CA, mehrere Konten können dieselbe Verzeichnis-URL teilen (z. B. zwei Let\'s-Encrypt-Konten zur administrativen Trennung); eine leere Verzeichnis-URL steht für Let\'s Encrypt Production' },
          { label: 'Benutzerdefinierter Server', text: 'Eine benutzerdefinierte ACME-Directory-URL festlegen, um eine beliebige RFC 8555-konforme CA zu verwenden' },
          { label: 'EAB', text: 'External Account Binding-Unterstützung für CAs, die eine Vorregistrierung erfordern (ZeroSSL, HARICA, usw.)' },
          { label: 'Schlüsseltypen', text: 'RSA-2048, RSA-4096, ECDSA P-256, ECDSA P-384, Brainpool P-256 oder P-384, ML-DSA-44, ML-DSA-65 oder ML-DSA-87 für Zertifikatsschlüssel; ML-DSA wird im FIPS-Modus oder in einem Build ohne ML-DSA nicht angeboten. Ein konfigurierter Standard, den diese Instanz nicht erzeugen kann, lässt die Order fehlschlagen, statt auf RSA-2048 zurückzufallen (v2.248)' },
          { label: 'Wiederverwendeter Schlüssel im FIPS-Modus', text: 'Die Wiederverwendung des Schlüssels eines Quellzertifikats wird abgelehnt, wenn der FIPS-Modus diesen Schlüssel nicht zulässt, ML-DSA eingeschlossen (v2.248)' },
          { label: 'Kontoschlüssel', text: 'ES256 (P-256), ES384 (P-384) oder RS256-Algorithmen für ACME-Kontoschlüssel' },
          { label: 'DNS-Anbieter', text: 'DNS-01-Challenge-Anbieter konfigurieren (Cloudflare, Route53, Tencent DNSPod, Plesk, usw.). Plesk läuft über seine XML-API; Verify TLS Certificate kann für ein selbstsigniertes Panel deaktiviert und eine DNS-Propagationsverzögerung hinzugefügt werden' },
          { label: 'Custom Command', text: 'DNS-Anbietertyp, der vom Admin konfigurierte lokale Befehle zum Erstellen/Löschen von TXT-Einträgen ausführt, Eintragsdetails werden über die Umgebungsvariablen DOMAIN, RECORD_NAME, RECORD_VALUE, TTL, ACTION übergeben. Absoluter Binärpfad erforderlich, keine Shell, konfigurierbares Timeout' },
          { label: 'Domänen', text: 'Domänen DNS-Anbietern für automatische Validierung zuordnen' },
          { label: 'HTTP-01', text: 'UCM stellt die Challenge-Datei seiner offenen Orders unter /.well-known/acme-challenge/ auf dem HTTP-Protokollport bereit (standardmäßig 8080): leiten Sie diesen Pfad von Port 80 der Domäne an UCM weiter. Verifizieren prüft zuerst die Datei, und HTTP-01-Orders werden automatisch erneuert' },
          { label: 'Erneuerung am Ort (v2.251)', text: 'Eine Erneuerung behält ID und refid des Zertifikats, sodass HTTPS-Bindung, Deploy-Bindungen und Webhooks ihm folgen. Zertifikate, die frühere Erneuerungen als neue Zeilen importiert haben, bleiben im Bestand: archivieren oder löschen Sie sie von Hand' },
          { label: 'Unterbrochene Orders (v2.251)', text: 'Eine durch einen Neustart in Bearbeitung gebliebene Order geht innerhalb von etwa 15 Minuten mit einer Meldung zurück auf ausstehend, bereit für Challenge verifizieren. Ein Zertifikat, das die CA vor einem Neustart oder einem fehlgeschlagenen Import ausgestellt hat, wird von Status prüfen, der Finalisierung oder der nächsten Erneuerung abgerufen' },
          { label: 'Veraltete ausstehende Orders (v2.251)', text: 'Die Erneuerungsaufgabe entfernt Orders, die länger als 7 Tage ausstehend sind und deren Order bei der CA abgelaufen ist oder deren Ablauf unbekannt ist, samt ihren TXT-Einträgen und protokolliert jede Entfernung im Audit. Die TXT-Einträge einer Order, deren Validierung fehlgeschlagen ist, werden entfernt, sobald sie ungültig ist' },
          { label: 'Order-Liste (v2.251)', text: 'Der Tab Let\'s Encrypt orders lädt jede Order, bis zu 5000, vier Seiten gleichzeitig, und wiederholt eine mit 429 abgelehnte Seite nach ihrem Retry-After. Fehlt eine Seite weiterhin, bleiben die erhaltenen Orders stehen, mit einem Hinweis, dass die Liste unvollständig ist' },
          { label: 'Fehlgeschlagene Erneuerungen (v2.251)', text: 'Eine Order zeigt ihre Anzahl fehlgeschlagener Erneuerungen mit dem letzten Fehler und dessen Datum. Nach 5 fehlgeschlagenen geplanten Erneuerungen wird sie einmal täglich wiederholt, und jeder Fehler, auch manuelle, löst das Ereignis acme_order.renewal_failed aus' },
          { label: 'Automatische Erneuerung je Order (v2.251)', text: 'Eine ausgewählte Order zeigt einen Schalter Automatische Erneuerung, der ihre Erneuerung stoppt oder fortsetzt. Das Löschen eines Zertifikats nach dem Widerruf schaltet die Erneuerung seiner Order mit einer Meldung ab' },
          { label: 'Eine Erneuerung gleichzeitig (v2.251)', text: 'Eine Erneuerung oder Finalisierung sperrt ihre Order: Eine zweite, die inzwischen gestartet wird, erhält 409, und der Planer überspringt die Order' },
          { label: 'Fehlendes Konto oder fehlender Anbieter (v2.251)', text: 'Eine Order, deren CA-Konto gelöscht wurde, deren DNS-Anbieter deaktiviert ist oder die den Schlüssel eines gelöschten Zertifikats wiederverwendet, stoppt vor der CA mit einer Meldung, was zu tun ist. Das Löschen oder Deaktivieren eines CA-Kontos wird abgelehnt (409), solange ausgestellte Orders darüber erneuern' },
          { label: 'Kompromittierte Schlüssel (v2.251)', text: 'Ein als kompromittiert widerrufener Schlüssel wird, gleich welche CA sein Zertifikat ausgestellt hat, bei der Anfrage und vor dem Öffnen einer Order durch eine Erneuerung abgelehnt (409), auch nachdem das Zertifikat gelöscht wurde. Eine Erneuerung, die einen solchen Schlüssel wiederverwenden soll, erzeugt einen neuen' },
          { label: 'Widerruf bei Erneuerung (v2.251)', text: 'Ist Altes Zertifikat nach Erneuerung widerrufen aktiviert (Lokales ACME › Erneuerungsrichtlinie), erhält die CA den lokalen Grund, wenn er keyCompromise, affiliationChanged, superseded oder cessationOfOperation ist, sonst keinen. Ein fehlgeschlagener Widerruf wird von der Erneuerungsaufgabe bis zum Ablauf des Zertifikats wiederholt und löst acme_order.revocation_failed aus' },
          { label: 'Erneuerungsschwelle (v2.249)', text: 'Tage vor Ablauf gilt, wenn die CA kein Erneuerungsfenster vorschlägt (ARI). Ein Zertifikat, dessen Laufzeit kürzer ist als das 1,5-Fache dieser Schwelle, erneuert stattdessen im letzten Drittel' },
          { label: 'Lange Namen (v2.249)', text: 'Ein erster Name über 64 Zeichen steht allein im Subject Alternative Name, als kritisch markiert, statt die Finalisierung scheitern zu lassen' },
          { label: 'Domain und Wildcard (v2.252)', text: 'Eine Order für eine Domain und ihre Wildcard erhält einen TXT-Wert je Autorisierung unter dem gemeinsamen Namen, und die DNS-Anbieter fügen jeden Wert neben den anderen hinzu. DuckDNS, Hurricane Electric und FreeDNS halten einen Wert pro Name daher wird eine solche Order abgelehnt, bevor die CA gefragt wird, ebenso eine DuckDNS-Order mit zwei Hosts unter einer Subdomain: Fordern Sie sie in getrennten Orders nacheinander an' },
          { label: 'TXT-Bereinigung (v2.252)', text: 'Die Bereinigung entfernt nur den TXT-Wert ihrer Order, sodass eine andere Order oder die Wildcard und die Apex-Domain mit demselben Namen ihre Werte behalten. DuckDNS, Hurricane Electric und FreeDNS halten einen Wert pro Name: Sie leeren ihn nur, wenn keine andere laufende Order den Namen verwendet' },
          { label: 'Eindeutige Namen (v2.251)', text: 'Ein bereits verwendeter Name eines DNS-Anbieters oder externen CA-Kontos wird abgelehnt (409), beim Anlegen und beim Umbenennen. Das Upgrade hat frühere Duplikate in „Name (2)“, „Name (3)“ umbenannt, die ältesten zuerst' },
          { label: 'Vercel-Team (v2.251)', text: 'Der Vercel-Anbieter akzeptiert eine optionale Team-ID für Domains eines Teams' },
          { label: 'RFC-2136-Anbieter (v2.252)', text: 'Der DNS-Server kann ein Hostname sein. Eine ausgefüllte Zone wird für die Namen darin verwendet; für andere Namen oder wenn sie leer ist, wird die Zone aus dem SOA gelesen, das der konfigurierte Server zurückgibt, dann vom System-Resolver' },
          { label: 'ARI-Erneuerungszeitpunkt (v2.252)', text: 'Schlägt die CA ein Erneuerungsfenster vor, wird jedes Zertifikat beim letzten 6-Stunden-Durchlauf vor einem einmal im Fenster zufällig gezogenen Zeitpunkt erneuert. Das Fenster wird nach dem Retry-After der CA erneut geprüft, begrenzt auf eine Minute bis einen Tag, und nie mehr, wenn das Zertifikat abgelaufen ist (RFC 9773)' },
          { label: 'CA-Fehler (v2.252)', text: 'Eine Fehlerseite der CA, die kein ACME-Problem ist (ein HTML-503), wird mit ihrem HTTP-Status und Retry-After gemeldet' },
          { label: 'RcodeZero-Token (v2.251)', text: 'RcodeZero benötigt ein API-Token mit Lese- und Schreibzugriff auf die Zone, nicht eines, das auf die ACME-Berechtigung beschränkt ist' },
          { label: 'Checkdomain (v2.251)', text: 'Checkdomain entfernt einen Wert, indem es die Einträge der Zone ohne ihn neu schreibt, wie seine API es dokumentiert, nach dem Lesen jeder Seite. SOA, Apex-NS und die erzeugten www-Kopien werden von diesem Neuschreiben ausgenommen' },
        ]
      },
      {
        title: 'Lokaler ACME-Server',
        items: [
          { label: 'Konfiguration', text: 'Den integrierten ACME-Server aktivieren/deaktivieren, Standard-CA auswählen' },
          { label: 'Lokale Domänen', text: 'Interne Domänen bestimmten CAs für Multi-CA-Ausstellung zuordnen' },
          { label: 'Konten', text: 'Registrierte ACME-Client-Konten anzeigen und verwalten' },
          { label: 'Konto-E-Mail (v2.218)', text: 'Die Kontakt-E-Mail eines lokalen Kontos kann über seine Detailansicht bearbeitet werden. Gemäß RFC 8555 gehört der Kontakt dem ACME-Client, sodass dessen nächste Kontoaktualisierung den Wert überschreiben kann' },
          { label: 'Verlauf', text: 'Alle ACME-Zertifikatsausstellungsaufträge verfolgen' },
                  { label: 'Lokale Orders (v2.217)', text: 'Der Tab Local orders listet die Orders des eingebauten Servers mit Statusfilter, Einzellöschung und Bereinigung; abgelaufene, nicht ausgestellte Orders werden alle 6 Stunden automatisch bereinigt, und ein Standard-Signatur-Digest gilt für Orders ohne Profil. Seit v2.218 entfernt die Bereinigung auch übrig gebliebene ausstehende Geschwister-Challenges bereits validierter Autorisierungen' },
                  { label: 'Profile und Vorlagen (v2.221)', text: 'Zertifikatsprofile (draft-ietf-acme-profiles) werden im Directory veröffentlicht und vom Client pro Order gewählt. Jedes Profil legt Gültigkeit und Digest fest und kann eine Zertifikatsvorlage binden, deren KU/EKU dann das ausgestellte Zertifikat bestimmen' },
                  { label: 'Standardprofil', text: 'Die meisten Clients fordern kein Profil an. Das unter den Profilen gewählte Standardprofil gilt für ihre Bestellungen; ohne Standardprofil erhalten sie 90 Tage und den Standard-Digest' },
                  { label: 'Widerruf (v2.248)', text: 'Das Zertifikat, das ein Client zum Widerrufen sendet, muss Byte für Byte mit dem gespeicherten übereinstimmen. Nur ein RSA- oder EC-P-256-, P-384- oder P-521-Zertifikatsschlüssel kann die Anfrage selbst signieren: ein ML-DSA-, EdDSA- oder Brainpool-Zertifikat mit dem Konto widerrufen, das es bestellt hat' },
                  { label: 'Widerruf durch Autorisierungen (v2.252)', text: 'Ein Konto mit gültigen, nicht abgelaufenen Autorisierungen für jeden Namen und jede IP-Adresse eines von diesem ACME-Server ausgestellten Zertifikats darf es widerrufen, auch wenn ein anderes Konto es bestellt hat (RFC 8555 §7.6). Durch Auto-Genehmigung erteilte Autorisierungen zählen nicht' },
                  { label: 'Angeforderte Daten (v2.252)', text: 'Eine Order kann notBefore und notAfter anfordern (cert-manager duration, lego --not-after): Das Zertifikat trägt genau diese Daten. Ein Fenster, das länger als die Gültigkeit des Profils ist, außerhalb der der ausstellenden CA liegt, von einer Richtlinie verboten oder bereits vergangen ist, wird abgelehnt, statt mit anderen Daten ausgestellt zu werden' },
                  { label: 'Ablauf (v2.252)', text: 'Eine Order nach ihrem Ablauf, oder deren gültige Autorisierung abgelaufen ist, kann nicht mehr finalisiert werden: Sie wird ungültig, und der Client legt eine neue Order an. Eine abgelaufene gültige Autorisierung liest sich als expired' },
                  { label: 'Challenges (v2.252)', text: 'Das Lesen einer Challenge mit leerer Payload startet ihre Validierung nie: Dafür sendet der Client {}. Ein tls-alpn-01-Zertifikat muss genau den validierten Namen oder die validierte IP-Adresse als Subject Alternative Name tragen' },
                  { label: 'CAA-Identitäten (v2.252)', text: 'Das Directory nennt die konfigurierten CAA-Kennungen als caaIdentities, sonst den öffentlichen ACME-Host, dieselbe Liste, gegen die finalize die CAA-Records prüft' },
        ]
      },
      {
        title: 'ACME-Proxy',
        items: [
          { label: 'Upstream-CA-Konto', text: 'Wählen Sie eines der Externen CA-Konten: Seine Verzeichnis-URL (Let\'s Encrypt, ZeroSSL, jede RFC 8555 CA) und die EAB-Zugangsdaten werden an diesem Konto festgelegt' },
          { label: 'Kontostatus', text: 'Zeigt an, ob UCM bei der Upstream-CA registriert ist. Konten werden automatisch bei der ersten Proxy-Anfrage registriert' },
          { label: 'Verbindungstest', text: 'Überprüfen Sie die Konnektivität zur Upstream-CA und prüfen Sie, ob EAB-Zugangsdaten erforderlich sind' },
          { label: 'Konto zurücksetzen', text: 'Die Upstream-Registrierung des gewählten CA-Kontos löschen, um eine Neuregistrierung zu erzwingen' },
          { label: 'EAB-Zugangsdaten', text: 'External Account Binding-Zugangsdaten für CAs, die sie erfordern (z.B. ZeroSSL, Google Trust), erfasst am CA-Konto unter Externe CA-Konten' },
          { label: 'DNS-Herausforderungen', text: 'UCM bearbeitet DNS-01-Herausforderungen im Auftrag der Clients mit konfigurierten DNS-Anbietern' },
          { label: 'Ersetzte Zertifikate bereinigen', text: 'Opt-in-Schalter: Beim Abschluss einer Proxy-Order werden Zertifikate gelöscht, die zuvor von Proxy-Orders für exakt denselben Domänensatz importiert wurden. Widerrufene Zertifikate bleiben immer erhalten; Nicht-Proxy-Zertifikate werden nie angetastet. Standardmäßig aus' },
                  { label: 'Client-Prechecks (v2.217)', text: 'Der Proxy veröffentlicht auch die mit dem Kontoschlüssel jedes Clients berechneten dns-01-TXT-Werte: die Propagation-Prechecks von lego/Traefik/Caddy bestehen, ohne deaktiviert zu werden, außer bei DuckDNS, Hurricane Electric und FreeDNS, die nur einen Wert halten: Deaktivieren Sie dort den Client-Precheck; ein wiederholtes new-order liefert die noch ausstehende Order des Kontos zurück' },
          { label: 'Client-Kompatibilität (v2.246)', text: 'Ist EAB erforderlich, liefern eine onlyReturnExisting-Abfrage und ein new-account mit einem registrierten Schlüssel das bestehende Konto zurück (cert-manager). Die Konto-URL beantwortet Lesezugriffe, Kontakt-Updates und Deaktivierung, die Deaktivierung von Autorisierungen wird akzeptiert (lego), und Challenge-Antworten tragen Link rel="up"' },
          { label: 'Upstream-Fehler (v2.252)', text: 'Ein Fehler der Upstream-CA erreicht den Client mit seinem Typ (rateLimited, badCSR, rejectedIdentifier, alreadyRevoked...), Status, Subproblems und Retry-After. Fehler zum eigenen Upstream-Konto des Proxys bleiben serverInternal' },
          { label: 'Profile und Gültigkeit (v2.252)', text: 'Das Directory listet die Profile der Upstream-CA. Ein vom Client angefordertes Profil, notBefore und notAfter werden an den Upstream weitergegeben, ein wiederholtes new-order verwendet eine ausstehende Order nur wieder, wenn es sie trägt, und ein Profil, das die Upstream-CA nicht anbietet, wird mit invalidProfile abgelehnt' },
          { label: 'Abgelehnter TXT-Record (v2.252)', text: 'Lehnt der DNS-Anbieter den TXT-Record ab, wird die Challenge nicht an den Upstream übermittelt: Die Order, ihre Autorisierungen und Challenges werden ungültig, keine ihrer anderen Challenges wird übermittelt, und die Meldung des Anbieters wird protokolliert und an der Order gespeichert. TXT-Records einer ungültigen oder deaktivierten Order werden entfernt' },
          { label: 'Fehlgeschlagene Challenge-Übermittlung (v2.252)', text: 'Lehnt die Upstream-CA die Challenge-Antwort ab (ein mehr als dreimal abgelehnter Nonce, ein Rate Limit) oder antwortet sie mit 5xx oder gar nicht und die Autorisierung zeigt die Challenge nicht als übernommen, wird die Order mit dem Upstream-Fehler ungültig und bleibt es, auch wenn die CA sie später validiert. Ihre TXT-Records werden entfernt (zwei Minuten später, solange die CA noch einen lesen könnte, oder im 15-Minuten-Durchlauf der Order-Pflege, wenn ein Neustart diese Verzögerung unterbrochen hat); die nächste Order des Clients für dieselben Namen wird erneut validiert oder ist sofort bereit, wenn die CA sie bereits validiert hat' },
          { label: 'CSR-Prüfungen (v2.252)', text: 'Bei der Finalisierung muss der CSR genau die Bezeichner der Order nennen, in CN oder SAN (RFC 8555 §7.4): Andernfalls wird er mit badCSR abgelehnt, bevor etwas die Upstream-CA erreicht' },
          { label: 'Deaktivierte Autorisierung (v2.252)', text: 'Eine Order, deren Autorisierung der Client deaktiviert hat, bleibt ungültig und erhält kein Zertifikat, selbst wenn die Order eines anderen Kontos zur selben Upstream-Order ausgestellt wird (RFC 8555 §7.5.2)' },
          { label: 'Unbekannte URLs (v2.252)', text: 'Eine URL oder Methode, die keine Route unter /acme oder /acme/proxy bedient, erhält ein malformed-Problemdokument mit Verweis auf das Directory, als 405 mit Allow, wenn eine andere Methode bedient wird, etwa ein GET auf eine reine POST-Ressource (RFC 8555 §6.3)' },
          { label: 'Challenge-Lesezugriffe (v2.252)', text: 'Der Proxy liest eine Challenge über ihre Autorisierung, nie mit einem POST-as-GET auf die Challenge, der die Validierung bei manchen CAs startet, bevor der TXT-Record existiert. Key Rollover bietet das Directory des Proxys nicht an' },
        ]
      },
      {
        title: 'DNS UPDATE (RFC 2136) für den ACME-Proxy',
        items: [
          { label: 'Funktion', text: 'Clients verwenden ihren Standard-rfc2136-Solver (certbot, lego, cert-manager, acme.sh, win-acme, Posh-ACME) und richten ihn auf UCM. UCM erstellt den TXT-Eintrag weiterhin über seinen eigenen DNS-Anbieter' },
          { label: 'Schlüssel', text: 'Erstellen Sie Schlüssel für jedes Proxy-Konto unter Externe CA-Konten. Ein Schlüssel kann mit EAB-Zugangsdaten verknüpft werden: Er gilt dann nur für Orders des ACME-Kontos, das mit diesen Zugangsdaten registriert wurde. UCM zeigt das Geheimnis nur einmal an' },
          { label: 'Akzeptierte Änderungen', text: 'UCM akzeptiert nur einen TXT-Eintrag unter _acme-challenge mit dem Wert, den es für die Order erwartet. Andere Änderungen lehnt es ab. Ein Löschen beantwortet es immer mit NOERROR' },
          { label: 'Port und Netzwerk', text: 'Legen Sie den Listener-Port im Abschnitt ACME-Proxy fest (0 deaktiviert ihn, 1024 bis 65535, Neustart erforderlich). Nur im internen Netzwerk verwenden. Für Port 53 leiten Sie ihn in Docker oder Kubernetes oder per Firewall-Weiterleitung um' },
          { label: 'Algorithmen', text: 'hmac-sha256, hmac-sha384 und hmac-sha512. UCM lehnt md5 und sha1 ab, die Standardwerte vieler Clients: Setzen Sie den Algorithmus in jedem Client. cert-manager unterstützt sha384 nicht, und win-acme berechnet es falsch' },
          { label: 'Zonenerkennung (SOA)', text: 'Clients fragen den SOA-Eintrag ab, um die Zone zu finden, und UCM beantwortet ihn. win-acme sendet stattdessen Test-Updates und verwendet immer Port 53' },
          { label: 'DNS-Prüfungen der Clients', text: 'Manche Clients prüfen den TXT-Eintrag im öffentlichen DNS, bevor sie fortfahren (lego, cert-manager, acme.sh). Sie brauchen einen Resolver, der die öffentliche Zone sieht, oder eine Wartezeit: --dns.propagation-wait (lego), --dnssleep (acme.sh), --dns01-recursive-nameservers (cert-manager)' },
        ]
      },
      {
        title: 'EAB-Credentials (serverseitig)',
        content: 'Wenn UCM als ACME-Server fungiert, erlaubt External Account Binding (RFC 8555 §7.3.4) das Erfordern vorab ausgegebener Credentials, bevor Clients Konten registrieren können:',
        items: [
          { label: 'Ausstellen', text: 'Neues kid + HMAC-Schlüsselpaar unter ACME → EAB Credentials erzeugen' },
          { label: 'Verteilen', text: 'kid + HMAC an den Client weitergeben (cert-manager, certbot, acme.sh)' },
          { label: 'Binden', text: 'Der Client signiert ein JWS über den MAC-Schlüssel bei newAccount, um sein ACME-Konto zu binden' },
          { label: 'Widerrufen', text: 'kid jederzeit widerrufen, bestehende Konten funktionieren weiter, neue Bindungen werden abgelehnt. Zum Rotieren erstellen Sie eine neue kid und widerrufen die alte' },
          { label: 'Audit', text: 'Ausstellung, Rotation und Widerruf werden unter dem ausführenden Operator auditiert' },
          { label: 'Domäneneinschränkungen', text: 'Ein Credential auf die anforderbaren Domänen begrenzen: * (alle), *.example.com (alle Subdomains) oder eine explizite Liste, eine leere Liste blockiert die Ausstellung vollständig. Durchgesetzt bei new-order/new-authz, auf Server und Proxy; nur sinnvoll, wenn EAB erforderlich ist' },
        ]
      },
      {
        title: 'Benutzerdefinierte DNS-Resolver (DNS-01)',
        items: [
          { label: 'Modus', text: 'ACME → Let\'s Encrypt → DNS-01-Resolver: Automatisch (aufgelistete, autoritative, öffentliche, dann System-Resolver), Nur System-Resolver oder Nur aufgelistete Resolver. Die eingeschränkten Modi fragen nie öffentliche Resolver ab, für Netzwerke, die sie blockieren' },
          { label: 'Split-Horizon', text: 'Nützlich, wenn Ihr autoritativer Server intern ist, die öffentliche Sicht aber anderswo gecacht wird' },
          { label: 'Veraltete Records', text: 'Vermeidet Public-Resolver-Caching während schneller Auto-Renewals' },
          { label: 'host:port-Einträge', text: 'Kommagetrennte IPs mit optionalem Port (127.0.0.1:5353, [2001:db8::53]:5300), jeder Resolver behält seinen eigenen Port: z. B. ein nur auf Loopback lauschender BIND oder dnsmasq auf einem alternativen Port' },
        ]
      },
      {
        title: 'ACME über interne / private IPs',
        content: 'HTTP-01 und TLS-ALPN-01-Validierung funktioniert standardmäßig für RFC1918, Loopback, .lan / .local / .corp-Ziele, UCMs primäres Deployment-Modell.',
        items: [
          { label: 'Toggle', text: 'ACME → ACME-Server → Private und interne Adressen erlauben (Standard: an)' },
          { label: 'Toggle', text: 'Let\'s-Encrypt-Tab → Loopback-ACME-CA zulassen, für eine kolokierte CA auf 127.0.0.1 (Standard: aus)' },
          { label: 'Immer blockiert', text: 'Cloud-Metadata-IPs (169.254.169.254, fd00:ec2::254 usw.) werden bedingungslos blockiert' },
        ]
      },
      {
        title: 'Multi-CA-Auflösung',
        content: 'Wenn ein ACME-Client ein Zertifikat anfordert, löst UCM die signierende CA in dieser Reihenfolge auf:',
        items: [
          '1. Lokale Domänenzuordnung: exakter Domänenabgleich, dann übergeordnete Domäne',
          '2. DNS-Domänenzuordnung: prüft die für den DNS-Anbieter konfigurierte ausstellende CA',
          '3. Globaler Standard: die in der ACME-Serverkonfiguration festgelegte CA',
          '4. Erste verfügbare CA mit einem privaten Schlüssel',
        ]
      },
      {
        title: 'Zertifikate für IP-Adressen (RFC 8738)',
        content: 'Der lokale ACME-Server kann Zertifikate für IPv4- und IPv6-Adressen ausstellen, nicht nur für DNS-Namen. Verwenden Sie den Identifier-Typ „ip“ in der Bestellung.',
        items: [
          { label: 'Identifier', text: 'Bestellung mit { "type": "ip", "value": "192.0.2.10" } (IPv4) oder einem IPv6-Literal wie 2001:db8::1' },
          { label: 'Challenges', text: 'Nur HTTP-01 und TLS-ALPN-01 werden angeboten, DNS-01 ist für IP-Identifier gemäß RFC 8738 verboten' },
          { label: 'TLS-ALPN-01 SNI', text: 'Die Validierung verwendet die Reverse-DNS-Form (in-addr.arpa / ip6.arpa) als SNI-Hostname' },
          { label: 'Ausgestellter SAN', text: 'Das Zertifikat enthält einen iPAddress-SAN; gemischte DNS- + IP-Bestellungen werden unterstützt' },
          { label: 'Interne IPs', text: 'RFC1918- und Loopback-Adressen werden sofort validiert, UCMs primäres Bereitstellungsmodell' },
        ]
      },
      {
        title: 'Persistente DNS-Validierung (dns-persist-01)',
        content: 'Der lokale ACME-Server kann Domains über einen persistenten TXT-Eintrag validieren, der an das ACME-Konto gebunden ist (draft-ietf-acme-dns-persist): Erneuerung ohne DNS-Schreibzugriffe. Opt-in, standardmäßig deaktiviert.',
        items: [
          { label: 'Eintrag', text: 'Erstellen Sie _validation-persist.<domain> TXT "<issuer-domain>; accounturi=<Konto-URL>", das Challenge-Objekt nennt beide erwarteten Werte' },
          { label: 'Aktivierung', text: 'ACME → Lokales ACME → Persistente DNS-Validierung (dns-persist-01)' },
          { label: 'Wildcard / Subdomains', text: 'Mit policy=wildcard werden auch Wildcard-Zertifikate und Subdomains des validierten Namens autorisiert' },
          { label: 'persistUntil', text: 'Optionales persistUntil=<Unix-Timestamp> stoppt neue Validierungen nach diesem Zeitpunkt' },
          { label: 'Sicherheit', text: 'Der Eintrag verleiht dem Kontoschlüssel Ausstellungsrechte, solange er existiert, TXT-Eintrag löschen, um sie zu entziehen' },
        ]
      }
    ],
    tips: [
      'ACME-Directory-URL: https://ihr-server:port/acme/directory',
      'Verwenden Sie eine benutzerdefinierte Directory-URL, um sich mit ZeroSSL, HARICA oder einer anderen RFC 8555-CA zu verbinden',
      'EAB-Anmeldeinformationen (Key ID + HMAC Key) werden von Ihrer CA bei der Registrierung bereitgestellt',
      'Wenn UCM der ACME-Server ist, eigene EAB-Credentials unter ACME → EAB Credentials ausstellen',
      'Für Kubernetes/cert-manager: Referenzmanifeste unter examples/kubernetes/cert-manager/',
      'ECDSA P-256-Schlüssel bieten gleichwertige Sicherheit wie RSA-2048 bei deutlich geringerer Größe',
      'Verwenden Sie lokale Domänen, um verschiedenen internen Domänen unterschiedliche CAs zuzuweisen',
      'Jede CA mit einem privaten Schlüssel kann als ausstellende CA ausgewählt werden',
      'Wildcard-Domänen (*.example.com) erfordern DNS-01-Validierung',
      'Jedes CA-Konto behält seine eigene Upstream-Registrierung: Wechselt der Proxy zu einem anderen Konto, wird dessen Registrierung verwendet',
      'Proxy-URL mit certbot verwenden: certbot certonly --server https://ihr-server:port/acme/proxy/directory',
    ],
    warnings: [
      'Domänenvalidierung ist erforderlich. Ihr Server muss erreichbar sein oder DNS konfiguriert sein',
      'Das Ändern des Kontoschlüsseltyps erfordert eine erneute Registrierung Ihres ACME-Kontos',
    ],
  },
  helpGuides: {
    title: 'ACME',
    content: `
## Übersicht

UCM unterstützt ACME (Automated Certificate Management Environment) in zwei Modi:

- **ACME-Client**: Zertifikate von jeder RFC 8555-konformen CA erhalten (Let's Encrypt, ZeroSSL, HARICA oder benutzerdefiniert)
- **Lokaler ACME-Server**: Integrierter ACME-Server für interne PKI-Automatisierung mit Multi-CA-Unterstützung

## ACME-Client

### Client-Einstellungen
Verwalten Sie Ihre ACME-Client-Konfiguration:
- **Umgebung**: Staging (Test) oder Produktion (Live-Zertifikate)
- **Kontakt-E-Mail**: Erforderlich für die Kontoregistrierung
- **Auto-Erneuerung**: Zertifikate automatisch vor Ablauf erneuern
- **Zertifikatsschlüsseltyp**: RSA-2048, RSA-4096, ECDSA P-256, ECDSA P-384, Brainpool P-256 oder P-384, ML-DSA-44, ML-DSA-65 oder ML-DSA-87. ML-DSA wird im FIPS-Modus oder in einem Build ohne ML-DSA nicht angeboten. Ein konfigurierter Typ, den diese Instanz nicht erzeugen kann, lässt die Order fehlschlagen, statt auf RSA-2048 zurückzufallen
- **Kontoschlüssel-Algorithmus**: ES256, ES384 oder RS256 für die ACME-Kontosignierung
- **Erneuerung am Ort** (v2.251): Eine Erneuerung behält ID und refid des Zertifikats, sodass seine HTTPS-Bindung, Deploy-Bindungen und Webhooks ihm folgen
- **Fehlgeschlagene Erneuerungen** (v2.251): Die Order-Liste zeigt die Fehleranzahl und den letzten Fehler; nach 5 fehlgeschlagenen geplanten Erneuerungen wird eine Order einmal täglich wiederholt. Der Schalter **Automatische Erneuerung** einer ausgewählten Order stoppt oder setzt ihre Erneuerung fort
- **Order-Liste** (v2.251): Jede Order wird geladen, vier Seiten gleichzeitig; eine Seite, die nach ihren Wiederholungen noch fehlt, löst einen Hinweis aus, dass die Liste unvollständig ist
- **Kompromittierte Schlüssel** (v2.251): Ein als kompromittiert widerrufener Schlüssel wird bei der Anfrage und vor jeder Erneuerung, die eine Order öffnet, abgelehnt (409)

### Benutzerdefinierter ACME-Server
Verwenden Sie jede RFC 8555-konforme CA, nicht nur Let's Encrypt:

| CA-Anbieter | Directory-URL |
|---|---|
| **Let's Encrypt** | *(Standard, leer lassen)* |
| **ZeroSSL** | \`https://acme.zerossl.com/v2/DV90\` |
| **HARICA** | \`https://acme-v02.harica.gr/acme/<token>/directory\` |
| **Google Trust** | \`https://dv.acme-v02.api.pki.goog/directory\` |

Legen Sie die Directory-URL Ihrer CA als **ACME-Verzeichnis-URL** seines Kontos unter **Externe CA-Konten** fest.

### Externe CA-Konten
Verwalten Sie alle externen Konten, mit denen sich UCM registriert:

- **Mehrere Konten pro CA erlaubt**: mehrere Konten können dieselbe Verzeichnis-URL teilen (z. B. zwei Let's-Encrypt-Konten mit unterschiedlichen Kontakt-E-Mails zur administrativen Trennung, nützlich mit dns-persist-01). Die Kontenzeile, nicht die URL, ist die Identität.
- **Leere Verzeichnis-URL**: steht standardmäßig für Let's Encrypt Production.
- **Standardkonto**: wird verwendet, wenn eine Anfrage kein Konto auswählt; URL-basierte Auflösungen liefern das Standardkonto.
- **Import**: beim Anlegen den privaten Schlüssel eines bestehenden Kontos importieren: die Hüllen PKCS#8, SEC1/X9.62 (\`BEGIN EC PRIVATE KEY\`) und PKCS#1 (\`BEGIN RSA PRIVATE KEY\`) werden akzeptiert; der Algorithmus wird automatisch abgeleitet.
- **Dedizierter Proxy-Endpunkt**: jedes Konto kann \`/acme/proxy/<slug>/directory\` mit eigenem Slug bereitstellen.

### External Account Binding (EAB)
Einige CAs erfordern EAB-Anmeldeinformationen, um Ihr ACME-Konto mit einem bestehenden Konto bei der CA zu verknüpfen:

1. Registrieren Sie sich im Portal Ihrer CA, um **EAB Key ID** und **HMAC Key** zu erhalten
2. Geben Sie beide Werte (**EAB-Schlüssel-ID**, **EAB-HMAC-Schlüssel**) am CA-Konto unter **Externe CA-Konten** ein
3. Der HMAC-Schlüssel ist base64url-kodiert (von der CA bereitgestellt)

> 💡 EAB wird von ZeroSSL, HARICA, Google Trust Services und den meisten Enterprise-CAs benötigt.

### ECDSA vs RSA-Schlüssel

| Schlüsseltyp | Größe | Sicherheit | Leistung |
|---|---|---|---|
| **RSA-2048** | 2048 Bit | Standard | Basis |
| **RSA-4096** | 4096 Bit | Höher | Langsamer |
| **ECDSA P-256** | 256 Bit | ≈ RSA-3072 | Deutlich schneller |
| **ECDSA P-384** | 384 Bit | ≈ RSA-7680 | Schneller |

ECDSA-Schlüssel werden für moderne Implementierungen empfohlen: kleiner, schneller und gleich sicher.

### Schlüsselquelle
Wählen Sie bei einer Zertifikatsanforderung, woher der private Schlüssel stammt:

- **Neuen Schlüssel erzeugen** *(Standard)*: UCM erstellt für jede Order ein neues Schlüsselpaar
- **Schlüssel bei Erneuerung wiederverwenden**: derselbe private Schlüssel über Erneuerungen hinweg (nötig für DANE/TLSA und Key Pinning); die Erstausstellung erzeugt den Schlüssel, Erneuerungen laden ihn erneut
- **Externen CSR bereitstellen**: fügen Sie einen extern erzeugten PEM-CSR ein; UCM reicht ihn beim Finalize ein, der private Schlüssel gelangt nie in UCM. Die CSR-Domänen müssen exakt den Order-Identifiern entsprechen

Im FIPS-Modus wird die Wiederverwendung des Schlüssels eines Quellzertifikats abgelehnt, wenn FIPS diesen Schlüssel nicht zulässt (ML-DSA eingeschlossen).

### Preflight (Testlauf)
**Preflight ausführen** im Anforderungsformular validiert die gesamte Anfrage gegen das **Staging**-Verzeichnis von Let's Encrypt, ohne Produktions-Ratenlimits zu verbrauchen:

- Prüft Domänensyntax, Kontakt-E-Mail, ACME-Konto / EAB und CA-Erreichbarkeit
- Der Modus **Vollständig** erstellt eine Staging-Order und zeigt die exakt zu veröffentlichenden \`_acme-challenge\`-TXT-Einträge an
- **Nur validieren** prüft Konfiguration und Konnektivität ohne Order
- Optional wird die DNS-TXT-Propagation nach dem Eintragen geprüft

> 💡 Eigene CAs haben keinen Staging-Endpunkt: der Preflight prüft dann nur Konfiguration und Konnektivität.

### DNS-Anbieter
Konfigurieren Sie DNS-01-Challenge-Anbieter für die Domänenvalidierung. Unterstützte Anbieter umfassen:
- Cloudflare
- AWS Route 53
- Azure DNS
- Google Cloud DNS
- DigitalOcean
- OVH
- Tencent Cloud DNSPod
- Plesk (XML-API): **Verify TLS Certificate** kann für ein selbstsigniertes Panel deaktiviert und eine DNS-Propagationsverzögerung hinzugefügt werden
- Und weitere

Jeder Anbieter erfordert spezifische API-Anmeldeinformationen für den DNS-Dienst.

Die Bereinigung entfernt nur den TXT-Wert ihrer Order, sodass eine andere Order oder die Wildcard und die Apex-Domain mit demselben Namen ihre Werte behalten; DuckDNS, Hurricane Electric und FreeDNS halten einen Wert pro Name, daher leeren sie ihn nur, wenn keine andere laufende Order ihn verwendet, und lehnen eine Order für eine Domain und ihre Wildcard ab (v2.252). Vercel akzeptiert eine optionale **Team-ID** für Domains eines Teams, und RcodeZero benötigt ein Token mit Lese- und Schreibzugriff auf die Zone. Ein bereits verwendeter Anbietername wird abgelehnt (v2.251).

#### Custom-Command-Anbieter
Für DNS-Dienste ohne nativen Treiber führt der **Custom Command**-Anbieter vom Admin konfigurierte lokale Befehle zum Erstellen/Löschen von TXT-Einträgen aus. Die Eintragsdetails werden als Umgebungsvariablen übergeben:

- \`DOMAIN\`: zu validierende Basisdomäne
- \`RECORD_NAME\`: vollständiger TXT-Eintragsname (\`_acme-challenge.example.com\`)
- \`RECORD_VALUE\`: TXT-Inhalt (Challenge-Digest)
- \`TTL\`: Eintrags-TTL in Sekunden
- \`ACTION\`: \`create\` oder \`delete\`

Der Befehl erfordert einen **absoluten Binärpfad**, läuft ohne Shell (keine Pipes oder Expansion) und wird nach einem konfigurierbaren Timeout beendet (5–300 s, Standard 60). Verwenden Sie ein kleines Wrapper-Skript, um externes DNS-Tooling anzubinden.

### Benutzerdefinierte DNS-Resolver
**DNS-01-Resolver** legt fest, wo UCM die \`_acme-challenge\`-TXT-Einträge abfragt: **Automatisch** (aufgelistete Resolver, dann die autoritativen Server der Zone, dann öffentliche Resolver, dann der System-Resolver), **Nur System-Resolver** oder **Nur aufgelistete Resolver**. Die eingeschränkten Modi fragen nie öffentliche Resolver ab, für Netzwerke, die sie blockieren. Einträge sind kommagetrennte IPs mit optionalem Port, z. B. \`127.0.0.1:5353\` oder \`[2001:db8::53]:5300\`.

### HTTP-01-Challenges
UCM stellt die Challenge-Datei seiner offenen Orders unter \`/.well-known/acme-challenge/<token>\` auf dem HTTP-Protokollport bereit (standardmäßig 8080). Die CA ruft sie auf Port 80 der Domäne ab, leiten Sie daher diesen Pfad von Ihrem Reverse-Proxy an UCM weiter oder binden Sie UCM an Port 80. **Challenge verifizieren** ruft zuerst die Datei ab und übermittelt nicht, wenn sie nicht ausgeliefert wird; **Verifizierung erzwingen** übermittelt trotzdem. HTTP-01-Orders werden automatisch erneuert.

### Domänen
Ordnen Sie Ihre Domänen DNS-Anbietern zu. Beim Anfordern eines Zertifikats für eine Domäne verwendet UCM den zugeordneten Anbieter, um DNS-01-Challenge-Einträge zu erstellen.

1. Klicken Sie auf **Domäne hinzufügen**
2. Geben Sie den Domänennamen ein (z.B. \`example.com\` oder \`*.example.com\`)
3. Wählen Sie den DNS-Anbieter
4. Klicken Sie auf **Speichern**

> 💡 Wildcard-Zertifikate (\`*.example.com\`) erfordern DNS-01-Validierung.


## ACME-Proxy-Modus

Der ACME-Proxy ermöglicht es internen Clients, Zertifikate von einer öffentlichen CA (Let's Encrypt, ZeroSSL usw.) über UCM anzufordern, ohne direkten Internetzugang. UCM fungiert als Vermittler, verwaltet DNS-01-Herausforderungen und leitet Anfragen an die Upstream-CA weiter.

### Wann den Proxy-Modus verwenden
- Interne Server ohne direkten Internetzugang
- Zentralisierte DNS-01-Challenge-Behandlung über in UCM konfigurierte DNS-Anbieter
- Audit und Nachverfolgung aller öffentlichen Zertifikatsausstellungen

### Konfiguration
1. Gehen Sie zu **ACME** → Registerkarte **Let's Encrypt**
2. Scrollen Sie zum Abschnitt **ACME Proxy**
3. Wählen Sie ein **Upstream-CA-Konto** unter **Externe CA-Konten** (Let's Encrypt, Actalis, ZeroSSL, benutzerdefinierte URL, EAB)
4. Klicken Sie auf **Verbindungstest**, um die Konnektivität zur Upstream-CA zu überprüfen
5. Registrieren Sie das Upstream-Konto bei Bedarf (E-Mail + **Konto registrieren**)
6. UCM registriert automatisch ein Konto bei der ersten Proxy-Anfrage, falls noch nicht geschehen

### Dedizierte Proxy-Pfade (Multi-CA)
Jedes externe CA-Konto kann einen eigenen ACME-Proxy-Endpunkt bereitstellen:

1. Öffnen Sie **Externe CA-Konten** (gleiche Registerkarte Let's Encrypt)
2. Bearbeiten oder erstellen Sie ein CA-Konto
3. Aktivieren Sie **Über ACME-Proxy bereitstellen**
4. Setzen Sie einen eindeutigen **Proxy-Pfad (Slug)**: z. B. \`actalis-production\`, \`letsencrypt-staging\`
5. Speichern: die URL erscheint im Proxy-Abschnitt und auf der Kontokarte

Clients verwenden:
\`\`\`
https://ihr-ucm-server:8443/acme/proxy/<slug>/directory
\`\`\`

Der Legacy-Standardpfad bleibt für das in den Proxy-Einstellungen gewählte Konto verfügbar:
\`\`\`
https://ihr-ucm-server:8443/acme/proxy/directory
\`\`\`

Reservierte Slugs (nicht erlaubt): \`directory\`, \`new-order\`, \`challenge\`, \`acct\`, usw.

### Kontoverwaltung
- Das **Kontostatus-Badge** zeigt an, ob UCM bei der Upstream-CA registriert ist
- Jedes CA-Konto behält seine eigene Upstream-Registrierung: Beim Wechsel des Upstream-Kontos wird dessen Registrierung verwendet, bei Bedarf bei der ersten Proxy-Anfrage registriert
- Verwenden Sie die Schaltfläche **Konto zurücksetzen**, um Zugangsdaten bei Bedarf manuell zu löschen
- **Verbindungstest** prüft, ob das Upstream-Verzeichnis erreichbar ist und ob EAB erforderlich ist

### Ersetzte Zertifikate bereinigen
Jede Proxy-Erneuerung importiert ein neues Zertifikat in den Bestand, sodass sich ersetzte Zertifikate mit der Zeit ansammeln. Der Schalter **Ersetzte Zertifikate bereinigen** (Proxy-Einstellungen) räumt automatisch auf: Beim Abschluss einer Proxy-Order werden Zertifikate gelöscht, die zuvor von Proxy-Orders für **exakt denselben Domänensatz** importiert wurden.

- **Widerrufene Zertifikate bleiben immer erhalten**: der Widerrufseintrag bleibt intakt
- Nicht über den Proxy ausgestellte Zertifikate werden nie angetastet
- Standardmäßig deaktiviert

### Proxy verwenden
Richten Sie Ihre internen ACME-Clients auf das Proxy-Verzeichnis der Ziel-CA.

**Slug-URL** (empfohlen bei mehreren CAs):
\`\`\`
https://ihr-ucm-server:8443/acme/proxy/<slug>/directory
\`\`\`

**Standard-URL** (Konto aus den Proxy-Einstellungen):
\`\`\`
https://ihr-ucm-server:8443/acme/proxy/directory
\`\`\`

Beispiel mit certbot (\`<slug>\` ersetzen):
\`\`\`
certbot certonly \\
  --server https://ihr-ucm-server:8443/acme/proxy/<slug>/directory \\
  --preferred-challenges dns-01 \\
  --authenticator manual \\
  --manual-auth-hook /bin/true \\
  --manual-cleanup-hook /bin/true \\
  --non-interactive --agree-tos -m you@example.com \\
  -d subdomain.example.com
\`\`\`

> 💡 Die EAB-Zugangsdaten des Upstream-CA-Kontos sind von den Client-EAB getrennt: sie authentifizieren UCM gegenüber der Upstream-CA, nicht Ihre Clients gegenüber UCM. Legen Sie sie an diesem Konto unter **Externe CA-Konten** fest.

> ⚠ Voraussetzung: Die Domain (oder eine übergeordnete Domain, die Subdomains abdeckt) muss in ACME Domains mit DNS-Provider konfiguriert sein. Der Proxy unterstützt nur dns-01.

> ⚠ Vermeiden Sie gleichzeitige Anfragen für denselben FQDN (Certbot + UCM-UI): Der zweite TXT-Record kann den ersten überschreiben.

Fehler der Upstream-CA erreichen den Client mit ihrem ACME-Typ, Status und Retry-After (ein Rate Limit ist ein 429 \`rateLimited\`, kein Proxy-Fehler). Ein Profil, \`notBefore\` und \`notAfter\` werden an den Upstream weitergegeben; ein Profil, das die Upstream-CA nicht auflistet, wird mit \`invalidProfile\` abgelehnt. Lehnt der DNS-Anbieter den TXT-Record ab, wird die Challenge nicht an den Upstream übermittelt und die Order wird ungültig, mit der Meldung des Anbieters in den Logs. Lehnt die Upstream-CA die Challenge-Antwort ab oder antwortet sie mit 5xx oder gar nicht und die Autorisierung zeigt die Challenge nicht als übernommen, wird die Order mit dem Upstream-Fehler endgültig ungültig und ihre TXT-Records werden entfernt, sodass die nächste Order des Clients erneut validiert wird. Ein CSR, der nicht genau die Bezeichner der Order nennt, wird mit \`badCSR\` abgelehnt, bevor er die Upstream-CA erreicht (v2.252).

> ℹ️ Bei selbstsigniertem UCM-HTTPS-Zertifikat (Lab) \`--no-verify-ssl\` zu Certbot hinzufügen.

### DNS UPDATE (RFC 2136)
Clients, die nur einen Standard-rfc2136-Solver verwenden können, können den ACME-Proxy ebenfalls nutzen. Sie senden das DNS-Update an UCM, und UCM erstellt den TXT-Eintrag mit seinem eigenen DNS-Anbieter.

#### Einrichtung
1. Aktivieren Sie **Über ACME-Proxy bereitstellen** am CA-Konto und legen Sie einen Proxy-Pfad fest (siehe oben)
2. Legen Sie im Abschnitt **ACME-Proxy** den **Port des DNS-UPDATE-Listeners** fest (0 deaktiviert ihn, 1024 bis 65535). Starten Sie UCM neu, um ihn zu übernehmen
3. Machen Sie den Port nur aus dem internen Netzwerk erreichbar. Für Port 53 leiten Sie ihn in Docker oder Kubernetes oder per Firewall-Weiterleitung auf den Listener um
4. Klicken Sie auf der Karte des CA-Kontos auf **DNS-UPDATE-Schlüssel (RFC 2136)**, dann auf **Neuer Schlüssel**
5. Wählen Sie einen Algorithmus (hmac-sha256 ist der Standard) und bei Bedarf EAB-Zugangsdaten
6. Kopieren Sie das Geheimnis und das Konfigurationsbeispiel für Ihren Client. UCM zeigt das Geheimnis nur einmal an

#### Was UCM akzeptiert
- Nur TXT-Einträge unter \`_acme-challenge\` mit dem Wert, den UCM für die Order erwartet
- UCM beantwortet ein Löschen immer mit NOERROR
- Ein Schlüssel gilt für das Proxy-Konto, zu dem er gehört. Mit EAB-Verknüpfung gilt er nur für Orders des ACME-Kontos, das mit diesen Zugangsdaten registriert wurde
- Widerrufen Sie einen Schlüssel, um ihn sofort zu stoppen. Löschen Sie einen widerrufenen Schlüssel, um ihn zu entfernen

#### Hinweise zu Clients
- **Algorithmus**: UCM lehnt die Standardwerte vieler Clients ab (HMAC-MD5, hmac-sha1). Setzen Sie hmac-sha256 (oder sha512) in jedem Client
- **certbot**: \`dns_rfc2136_server\` muss eine IP-Adresse sein. Setzen Sie \`dns_rfc2136_algorithm = HMAC-SHA256\`
- **lego**: Setzen Sie \`DNSUPDATE_TSIG_ALGORITHM\`. Der Standard ist hmac-sha1. Verwenden Sie \`--dns.propagation-wait\`, wenn lego die öffentliche Zone nicht sieht
- **cert-manager**: unterstützt nur HMACSHA256 und HMACSHA512, nicht sha384. Er findet die Zone über seine rekursiven Resolver: Setzen Sie \`--dns01-recursive-nameservers\` auf einen Resolver, der die öffentliche Zone sieht
- **acme.sh**: Verwenden Sie \`dns_nsupdate\` mit \`NSUPDATE_KEY\`, der auf die BIND-Schlüsseldatei zeigt. Verwenden Sie \`--dnssleep\`, wenn die Prüfungen über öffentliches DNS fehlschlagen
- **win-acme**: sendet das Update immer an Port 53 (\`--serverport\` wird als Timeout verwendet). Leiten Sie daher Port 53 auf den UCM-Listener um. Es berechnet hmac-sha384 falsch: Verwenden Sie sha256
- **Posh-ACME**: \`DDNSNameserver\` ist erforderlich. Ohne ihn sendet nsupdate das Update an den MNAME der Zone auf Port 53

Beispiel (acme.sh):
\`\`\`
export NSUPDATE_SERVER="ucm.example.com"
export NSUPDATE_SERVER_PORT="8053"
export NSUPDATE_KEY="/etc/ucm-tsig.key"
acme.sh --issue --dns dns_nsupdate --server https://ucm.example.com/acme/proxy/<slug>/directory -d www.example.com --dnssleep 30
\`\`\`

> ⚠ Verwenden Sie den Listener nur im internen Netzwerk. Veröffentlichen Sie ihn nicht im Internet.

## Lokaler ACME-Server

### Konfiguration
- **Aktivieren/Deaktivieren**: Den integrierten ACME-Server umschalten
- **Standard-CA**: Auswählen, welche CA Zertifikate standardmäßig signiert
- **Nutzungsbedingungen**: Optionaler Titel und Markdown-Text, von UCM bereitgestellt und im Directory verlinkt

### ACME-Directory-URL
\`\`\`
https://ihr-server:8443/acme/directory
\`\`\`

Clients wie certbot, acme.sh oder Caddy verwenden diese URL, um die ACME-Endpunkte zu ermitteln.

### Lokale Domänen (Multi-CA)
Ordnen Sie interne Domänen bestimmten CAs zu. So können verschiedene Domänen von verschiedenen CAs signiert werden.

1. Klicken Sie auf **Domäne hinzufügen**
2. Geben Sie die Domäne ein (z.B. \`internal.corp\` oder \`*.dev.local\`)
3. Wählen Sie die **ausstellende CA**
4. Aktivieren/deaktivieren Sie **Auto-Genehmigung**
5. Klicken Sie auf **Speichern**

### CA-Auflösungsreihenfolge
Wenn ein ACME-Client ein Zertifikat anfordert, bestimmt UCM die signierende CA in dieser Reihenfolge:
1. **Lokale Domänenzuordnung**: Exakter Abgleich, dann übergeordneter Domänenabgleich
2. **DNS-Domänenzuordnung**: Die für den DNS-Anbieter konfigurierte CA
3. **Globaler Standard**: Die in der ACME-Serverkonfiguration festgelegte CA
4. **Erste verfügbare**: Jede CA mit einem privaten Schlüssel

### EAB Credentials (serverseitig)
Wenn UCM der ACME-Server (oder Proxy) ist, können Sie **External Account Binding** verlangen: Clients müssen ein vorab ausgestelltes kid + HMAC-Schlüsselpaar vorlegen, um ein Konto zu registrieren. Stellen Sie Credentials unter **ACME → EAB Credentials** aus und widerrufen Sie sie dort.

Jedes Credential kann auf die **Domänen beschränkt werden, für die es Zertifikate anfordern darf**:
- \`*\`: jede Domäne (Standard für neue und bestehende Credentials)
- \`*.example.com\`: die Domäne und alle ihre Subdomains
- Eine explizite Domänenliste
- Eine **leere Liste blockiert die Ausstellung vollständig** für dieses Credential

Die Einschränkungen werden bei new-order und new-authz durchgesetzt, sowohl auf dem integrierten ACME-Server als auch auf dem Proxy. Sie sind nur sinnvoll, wenn **EAB erforderlich** ist: andernfalls können sich Clients einfach ohne Credential registrieren.

### Konten
Registrierte ACME-Client-Konten anzeigen:
- Konto-ID und Kontakt-E-Mail
- Registrierungsdatum
- Anzahl der Bestellungen

### Verlauf
Die über ACME ausgestellten Zertifikate durchsuchen:
- Common Name
- Status
- Aussteller
- Ablaufdatum
- Quelle

### Angeforderte Daten
Eine Order kann \`notBefore\` und \`notAfter\` tragen (cert-manager mit \`duration\`, lego \`--not-after\`). Das Zertifikat wird mit genau diesen Daten ausgestellt, oder die Anfrage wird als \`malformed\` abgelehnt: ein Fenster, das länger als die Gültigkeit des Profils ist (15 Minuten Uhrenabweichung ausgenommen), außerhalb der Gültigkeit der ausstellenden CA liegt oder bereits vergangen ist. Ein Fenster, das eine Richtlinie verbietet, länger als ihre maximale Gültigkeit oder über einem Schlüsseltyp-Horizont, wird bei finalize als \`badCSR\` abgelehnt. Ohne sie gilt die Gültigkeit des Profils.

### Widerruf
Ein Client widerruft mit seinem Konto-Schlüssel oder mit dem eigenen Schlüssel des Zertifikats, und das gesendete Zertifikat muss Byte für Byte mit dem gespeicherten übereinstimmen: eine Seriennummer allein genügt nie. Ein Konto, das gültige, nicht abgelaufene Autorisierungen für jeden Namen und jede IP-Adresse eines von diesem ACME-Server ausgestellten Zertifikats hält, darf es ebenfalls widerrufen, gleichgültig wer es bestellt hat; per Auto-Genehmigung erteilte Autorisierungen zählen nicht. Nur ein RSA- oder EC-P-256-, P-384- oder P-521-Schlüssel kann eine ACME-Anfrage signieren, daher wird ein ML-DSA-, EdDSA- oder Brainpool-Zertifikat mit dem Konto widerrufen, das es bestellt hat; UCM nennt das in der Ablehnung.

## Zertifikate für IP-Adressen (RFC 8738)

Der lokale ACME-Server kann Zertifikate für **IP-Adressen** (IPv4 und IPv6) ausstellen, nicht nur für DNS-Namen. Nützlich für interne Dienste, Appliances und direkt per IP adressierte Hosts.

### Ein IP-Zertifikat bestellen
Verwenden Sie den Identifier-Typ \`ip\` in der ACME-Bestellung:
\`\`\`json
{
  "identifiers": [
    { "type": "ip", "value": "192.0.2.10" },
    { "type": "ip", "value": "2001:db8::1" }
  ]
}
\`\`\`
Gemischte DNS- + IP-Bestellungen werden ebenfalls unterstützt.

### Validierung
- **HTTP-01** und **TLS-ALPN-01** sind die einzigen Challenges für IP-Identifier. **DNS-01 ist** für IPs durch RFC 8738 **verboten**.
- **HTTP-01** verbindet sich direkt mit der IP (IPv6-Literale werden in Klammern gesetzt, z. B. \`http://[2001:db8::1]/...\`).
- **TLS-ALPN-01** verwendet die Reverse-DNS-Form der IP (\`in-addr.arpa\` / \`ip6.arpa\`) als SNI-Hostname.

### Ausgestelltes Zertifikat
Das signierte Zertifikat enthält für jede validierte IP einen **iPAddress**-SubjectAltName-Eintrag.

> 💡 Interne Adressen (RFC1918, Loopback) werden sofort validiert. UCMs primäres Bereitstellungsmodell. Cloud-Metadaten-IPs bleiben blockiert.

## Persistente DNS-Validierung (dns-persist-01)

Der lokale ACME-Server unterstützt **dns-persist-01** (draft-ietf-acme-dns-persist): Validierung über einen **persistenten** TXT-Eintrag, der an das ACME-Konto gebunden ist, Erneuerungen erfordern keine DNS-Schreibzugriffe.

### Einrichtung
1. Aktivieren Sie es unter **ACME → Lokales ACME → Persistente DNS-Validierung** (standardmäßig deaktiviert).
2. Erstellen Sie den Eintrag einmalig:
\`\`\`
_validation-persist.app.example.com. IN TXT "ca.example.com; accounturi=https://ca.example.com/acme/acct/<id>"
\`\`\`
Das Challenge-Objekt nennt die erwarteten Werte \`accounturi\` und \`issuer-domain-names\`.

### Optionen
- \`policy=wildcard\`: autorisiert auch Wildcard-Zertifikate und Subdomains des validierten Namens (ein Eintrag auf einer übergeordneten Domain deckt deren Kinder ab)
- \`persistUntil=<Unix-Timestamp>\`: stoppt neue Validierungen nach diesem Zeitpunkt

> ⚠️ Der Eintrag verleiht dem ACME-Kontoschlüssel Ausstellungsrechte, solange er existiert: löschen Sie den TXT-Eintrag, um sie zu entziehen.

## certbot verwenden

\`\`\`
# Konto registrieren (Let's Encrypt. Standard)
certbot register --agree-tos --email admin@example.com

# Mit benutzerdefinierter ACME-CA + EAB registrieren
certbot register \\
  --server 'https://acme.zerossl.com/v2/DV90' \\
  --eab-kid 'ihre-key-id' \\
  --eab-hmac-key 'ihr-hmac-schlüssel' \\
  --agree-tos --email admin@example.com

# Zertifikat mit ECDSA-Schlüssel anfordern
certbot certonly --server https://ihr-server:8443/acme/directory \\
  --standalone -d meinserver.internal.corp \\
  --key-type ecdsa --elliptic-curve secp256r1

# Erneuern
certbot renew --server https://ihr-server:8443/acme/directory
\`\`\`

## acme.sh verwenden

\`\`\`
# Standard (Let's Encrypt)
acme.sh --issue -d example.com --standalone

# Benutzerdefinierte ACME-CA mit EAB und ECDSA
acme.sh --issue \\
  --server 'https://acme-v02.harica.gr/acme/TOKEN/directory' \\
  --eab-kid 'ihre-key-id' \\
  --eab-hmac-key 'ihr-hmac-schlüssel' \\
  --keylength ec-256 \\
  -d example.com --standalone
\`\`\`

> ⚠ Für internen ACME-Betrieb müssen Clients der UCM-CA vertrauen. Installieren Sie das Root-CA-Zertifikat im Vertrauensspeicher des Clients.

## Renewal Information (ARI, RFC 9773)

Der lokale ACME-Server kündigt \`renewalInfo\` in seinem Directory an und liefert ein **vorgeschlagenes Erneuerungsfenster** pro Zertifikat.

- Fenster zentriert vor Ablauf → zeitlich verteilte Erneuerungen
- Widerrufenes Zertifikat → Fenster in der Vergangenheit (jetzt erneuern)
- Nicht authentifizierter GET auf \`/acme/renewalInfo/<certID>\`
- ACME-Proxy: Für ein über den Proxy ausgestelltes Zertifikat wird das Fenster der Upstream-CA mit ihrem Retry-After weitergereicht; lokal berechnet, wenn die CA keines hat oder nicht antwortet

`
  }
}
