# Ultimate Certificate Manager

[English](README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [中文](README.zh.md)

![Version](https://img.shields.io/github/v/release/NeySlim/ultimate-ca-manager?label=version&color=brightgreen)
![License](https://img.shields.io/badge/license-AGPL--3.0--only-blue.svg)
![Docker Hub](https://img.shields.io/docker/v/neyslim/ultimate-ca-manager?label=docker%20hub&color=blue)
![GHCR](https://img.shields.io/badge/ghcr.io-available-blue)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20UCM-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/neyslim)

**Ultimate Certificate Manager (UCM)** ist eine webbasierte Plattform zur Verwaltung von Zertifizierungsstellen (CA) mit Unterstützung für PKI-Protokolle (ACME, SCEP, EST, OCSP, CRL/CDP), Microsoft-ADCS-Integration, Multi-Faktor-Authentifizierung und Verwaltung des gesamten Zertifikatslebenszyklus.

> **UCM ist ein junges, aktiv weiterentwickeltes Projekt.** Feedback, Fehlerberichte und Funktionswünsche sind sehr willkommen! [Eröffnen Sie gern ein Issue](https://github.com/NeySlim/ultimate-ca-manager/issues): Jede Meldung hilft, UCM zu verbessern.

> Neuigkeiten finden Sie in den [aktuellen Release Notes](https://github.com/NeySlim/ultimate-ca-manager/releases/latest) und im vollständigen [CHANGELOG](CHANGELOG.md).

![Dashboard](docs/screenshots/dashboard-dark.png)

---

## Funktionen

### PKI-Kern
- **CA-Verwaltung** -- Root- und Zwischen-CAs, Hierarchieansicht, Import/Export, **Widerruf von Zwischen-CAs** (CRL und OCSP der übergeordneten CA, Status „übergeordnet widerrufen“ darunter), **reine Zertifikats-CAs** (eine CA, die aus einer externen Anfrage signiert wurde und deren privater Schlüssel später importiert wird), **HSM-gestützte Signaturschlüssel** (der private Schlüssel verlässt das HSM nie), **konfigurierbares RFC-5280-Profil** (Signatur-Digest, Key Usage, EKU), eine CA kann **in den Ausstellungsformularen ausgeblendet** werden (eine Root, die nur Zwischen-CAs signiert), mit Voreinstellungen im Stil von Let's Encrypt und optionalem Signaturverfahren **RSA-PSS**, **Compliance-Profile** nach ANSSI, BSI und den EU-Vorgaben für kryptografische Verfahren (agreed mechanisms), **extern signierte CAs** (UCM erzeugt das Schlüsselpaar und eine CSR vom Typ CA, eine Offline-/externe Root signiert sie: Der private Schlüssel verlässt UCM nie, mit CSR-Erneuerung unter demselben Schlüssel), **cross-signierte CA-Zertifikate** (neben dem eigenen CA-Zertifikat anhängen oder cross-signieren, bei einem Root-Wechsel in der Standardkette ausliefern, die Kette pro Export oder Deployment wählen, sehen, was noch auf die alte Root verkettet), **Name Constraints nach RFC 5280** bei der Erstellung (erlaubte und ausgeschlossene Teilbäume für DNS, IP-Bereiche und E-Mail, auf jedem Ausstellungspfad durchgesetzt), Gültigkeit ab 1 Jahr oder beliebig vielen Tagen bis zu 50 Jahren sowie eine optionale Regel für **eindeutigen Subject** (ein Zertifikat, dessen Subject unter dieser CA bereits eine andere Entität trägt, wird auf jedem Ausstellungspfad abgelehnt, RFC 5280 §4.1.2.6)
- **Zertifikatslebenszyklus** -- Ausstellen, signieren, widerrufen (mit dem RFC-5280-Grund, aus jedem Widerrufsdialog und in großen Mengen), erneuern (**in-place**: stabile IDs über Erneuerungen hinweg, abgelöste Seriennummern bleiben bis zu ihrem ursprünglichen Ablauf in CRL/OCSP, eine gewählte Gültigkeit bleibt durch die Richtlinie begrenzt), umbenennen (veränderbarer Anzeigename, deckt Zertifikate ohne CN ab), exportieren (PEM, DER, PKCS#12 mit einem 3DES/SHA-1-Kompatibilitätsmodus für Android 15 und älter, macOS 14 und älter, ältere Windows- und Java-Versionen, JKS; die Kette lässt die selbstsignierte Root standardmäßig weg, mit der Option **Root-CA einschließen**, wo ein Paketierungs- oder Importziel sie benötigt), Massenoperationen, Filter nach Status / Aussteller / Quelle (ACME, SCEP, EST, AD CS, Import …), einschließlich der durch eine Erneuerung oder erneute Registrierung **archivierten** Einträge, die als Verlauf erhalten bleiben
- **Konformitätsprüfung (Linting)** -- Prüfungen pro Zertifikat gegen RFC 5280, die CA/Browser Forum Baseline Requirements und ETSI EN 319 412 mit pkilint (und zlint, sofern verfügbar), nur zur Information
- **CSR-Verwaltung** -- Certificate Signing Requests erstellen, importieren und signieren, mit **eigenen Extra-EKU-OIDs** (RFC 5280 §4.2.1.12), **typisierter SAN-Validierung** (DNS / IP / E-Mail / URI / UPN), den Kurven NIST P-256 / P-384 / P-521 und Brainpool P256r1 / P384r1 / P512r1 sowie einem **Rückweg über eine externe CA**: Ein andernorts für eine in UCM erzeugte CSR ausgestelltes Zertifikat vervollständigt diese CSR beim Import und behält ihren privaten Schlüssel; **beim Signieren ergänzte Namen** (die E-Mail-Adresse einer S/MIME-Anfrage von einer Smartcard, die nur einen CN enthält, unter denselben Name Constraints, Richtlinien und derselben Genehmigung) und **erneutes Signieren** aus dem Verlauf, für Geräte, die ihre Anfrage nicht zweimal erzeugen können
- **Zertifikatsvorlagen** -- Vordefinierte Profile für Server, Client, Code Signing, E-Mail und Windows-Smartcard-Anmeldung; Schlüsseltypen RSA-2048/3072/4096, EC P-256/P-384/P-521, Brainpool und **Post-Quanten-ML-DSA-44/65/87** (Ed25519/Ed448 für CAs), **eigene X.509-Erweiterungen per OID**, **qcStatements (ETSI EN 319 412-5) und Certificate-Policy-OIDs** sowie Subject-Vorgaben (einschließlich E-Mail), die im Ausstellungsformular vorausgefüllt werden; JSON-Export und -Import, die jede Einstellung erhalten, eine Vorlage oder mehrere pro Datei
- **Zertifikatserkennung (Discovery)** -- Netzwerk-Scans, Scan-Profile, geplante Scans, Zertifikatsimport
- **Vertrauensspeicher (Trust Store)** -- Vertrauenswürdige Root-CA-Zertifikate verwalten, mit Ablaufwarnungen und Massenentfernung
- **Kettenreparatur** -- Kettenvalidierung auf Basis von AKI/SKI mit automatischem Reparatur-Scheduler
- **SSH-Zertifikate** -- Verwaltung von SSH-Zertifizierungsstellen, Host-/Benutzerzertifikate signieren, CAs und Zertifikate importieren, curl-freundliche Einrichtungsskripte; Key-IDs von der CA vergeben (`principals@CA name`) oder dem Anfragenden überlassen

### Protokolle
- **ACME** -- RFC 8555, automatische Registrierung, automatische Erneuerung, Challenges DNS-01/HTTP-01/TLS-ALPN-01, Wildcard-Unterstützung, **IP-Identifikatoren (RFC 8738)**, **CAA-Prüfung mit Bindung an Konto/Methode (RFC 8657/8659)**, **External Account Binding (EAB, RFC 8555 §7.3.4)**, **Renewal Information (ARI, RFC 9773)**, **von UCM ausgelieferte HTTP-01-Challenge-Dateien** (`/.well-known/acme-challenge/` von Port 80 weiterleiten, vor dem Absenden geprüft, automatisch erneuert), **Wahl des DNS-01-Resolvers** (automatisch, nur System oder nur aufgeführte Resolver, für Netze ohne Zugriff auf öffentliche Resolver) für Split-Horizon, ACME auf internen/privaten IPs (einschließlich optionalem Loopback-Upstream für eine auf demselben Host laufende CA), **Multi-CA-Verwaltung** (CA-Auswahl pro Anfrage, bei der Bestellung festgelegt, sodass Erneuerungen dieselbe CA wiederverwenden: Let's Encrypt, Actalis, ZeroSSL, Google Trust Services, HARICA …), **externe CSR und Wiederverwendung des Schlüssels bei Erneuerung**, **Staging-Preflight als Trockenlauf**, **Multi-CA-Proxy** (bereits validierte Upstream-Domains werden direkt durchgereicht, Endpunkte pro CA unter `/acme/proxy/<slug>/directory`, einschließlich Upstream-Widerruf), **bevorzugte Zertifikatskette** (Alternativen nach RFC 8555 §7.4.2, pro CA-Konto), **Zertifikatsprofile** (draft-ietf-acme-profiles: benannte Ausstellungsrichtlinien, die im Directory angekündigt und pro Bestellung wählbar sind, jeweils optional an eine Zertifikatsvorlage gebunden, deren Key Usage und EKU dann das ausgestellte Zertifikat bestimmen, plus ein **Standardprofil** und ein Standard-Signatur-Digest für Bestellungen ohne Profilangabe), **Verwaltung lokaler Server-Bestellungen** (Bestellansicht mit Bereinigung und geplanter Löschung abgelaufener Bestellungen); der Proxy veröffentlicht außerdem die clientseitigen dns-01-TXT-Werte, sodass die Propagierungsprüfungen der Clients (lego, Traefik, Caddy) unverändert bestehen, verwendet die noch offene Bestellung eines Kontos bei Wiederholungen erneut, und ein optionaler **DNS-UPDATE-Listener (RFC 2136)** lässt Standard-rfc2136-Solver wie den von cert-manager DNS-01 über den Proxy beantworten, mit TSIG-Schlüsseln pro Konto
- **SCEP** -- RFC 8894, automatische Geräteregistrierung mit Genehmigungsworkflows, GetCert/GetCRL, signiertes GetNextCACert, optional auf dem einfachen HTTP-Port für Clients wie sscep (außerhalb des FIPS-Modus, der nur RSA-OAEP-Schlüsseltransport zulässt), durch das Gerätezertifikat authentifizierte Erneuerungen, AES-128-Verschlüsselung mit passwortbasiertem (PBKDF2) Fallback für Nicht-RSA-Clients; eine von Hand genehmigte Anfrage wird mit der Vorlage des Profils ausgestellt, über das sie kam, genau wie bei automatischer Genehmigung; benannte Profile validieren **Microsoft-Intune**-Challenges gegen die Intune-API des Mandanten, und Windows-Geräte (RSAES-OAEP-Schlüsseltransport) sowie Apple-Geräte registrieren sich darüber, siehe [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md)
- **EST** -- RFC 7030 Enrollment over Secure Transport, einschließlich serverseitiger Schlüsselerzeugung (CMS §4.4) und **CA-Labels** (§3.2.2: mehrere CAs über einen Endpunkt bedienen)
- **OCSP** -- RFC 6960, Zertifikatsstatus in Echtzeit, Anfragen für mehrere Zertifikate, Nonce-Unterstützung, Validierung delegierter Responder mit automatischer Erneuerung des Responder-Zertifikats, konfigurierbare Antwortgültigkeit
- **TSA (RFC 3161)** -- Zeitstempeldienst mit konfigurierbarer Policy-OID; signiert mit einem **dedizierten End-Entity-Signaturzertifikat** (RFC 3161, standardmäßig erforderlich und von strengen Prüfern wie `openssl ts -verify` und jarsigner verlangt), aus ausgestellten Zertifikaten gewählt oder mit einem Klick erzeugt (kritisch, exklusive timeStamping-EKU); Erneuerungen werden automatisch nachgeführt, die Ausstellerkette ist in den Token eingebettet, strikter Modus mit dediziertem Signierer, Zustand und Ablauf des Signierers werden im Dashboard angezeigt
- **CRL/CDP** -- Verteilung von Zertifikatssperrlisten mit Unterstützung für Delta-CRLs (RFC 5280 §5.2.4), Zeitplan pro CA (Gültigkeit unabhängig vom Veröffentlichungsrhythmus) und konfigurierbarem Signatur-Digest, optionale benannte URLs (CA-Namens-Slug in CDP/AIA-Pfaden, auch für bestehende CAs aktivierbar), **Upload extern signierter CRLs für Offline-CAs bzw. CAs ohne Schlüssel** (gegen das CA-Zertifikat validiert, mit monoton steigender CRL-Nummer, am bestehenden CDP-Endpunkt ausgeliefert und von OCSP herangezogen)
- **AIA CA Issuers** -- Download des CA-Zertifikats über Authority Information Access (RFC 5280 §4.2.2.1)

### Integrationen
- **Microsoft ADCS** -- Vollständiger Lebenszyklus über AD CS: CSR-Signierung, Vorlagenerkennung, EOBO (Enroll On Behalf Of), Erneuern/Widerrufen über den Konnektor und ein optionaler WinRM-Administrationskanal für den Abgleich von CRL-Widerrufen, den Import des CA-Bestands und das Genehmigen/Ablehnen ausstehender Anfragen mit einem CA-Zustandspanel
- **Windows-Autoenrollment & Active-Directory-Konnektor** -- MS-XCEP/WSTEP-Richtlinie und -Registrierung für domänenverbundene Computer und Benutzer mit der in der Anfrage genannten Vorlage; bei der Kerberos-Bindung beziehen Computer- und AD-abgeleitete Vorlagen das Subject aus Active Directory (der DNS-Hostname des Computers bzw. der DN und UPN des Benutzers), über mehrere Domänencontroller mit Failover und einer geplanten Zustandsprüfung pro DC, nie mit anonymem Bind; die Registrierung wird in **Profilen pro Realm** konfiguriert (`/api/v2/windows-profiles`), jedes mit eigener CA, eigenen Vorlagen, eigenem Kerberos-Keytab, eigener AD-Gruppe und eigenem Konnektor, und eine Kerberos-Anfrage wird vom aktivierten Profil des Realms ihres Principals bedient (die UsernamePassword-Bindung vom Standardprofil, sofern aktiviert, eine zertifikatsgebundene Erneuerung vom Profil, das auf dem vorgelegten Zertifikat vermerkt ist), über **mehrere Active-Directory-Konnektoren** (einer pro Forest oder Domäne)
- **Microsoft Intune** -- Validierung von SCEP-Challenges für von Intune verwaltete Geräte, Entra-App-Registrierungen einmal unter SCEP › Intune-App-Registrierungen definiert und pro Profil ausgewählt, mit einer Schritt-für-Schritt-Anleitung in `docs/integrations/intune-scep.md`
- **HSM** -- SoftHSM enthalten, PKCS#11, Azure Key Vault, Google Cloud KMS, OpenBao/Vault Transit; **HSM-gestützte CAs** mit nicht exportierbaren Signaturschlüsseln, RSA-PSS und Brainpool über PKCS#11 sowie einer deklarierten Gerätezertifizierung (Common Criteria, EUCC, FIPS 140-3), die vom EU-Compliance-Profil geprüft wird; ein Verbindungstest zeigt, was ein PKCS#11-Modul meldet (Bibliothek, Hersteller, Firmware)
- **Kubernetes / cert-manager** -- Referenzmanifeste für ClusterIssuer (HTTP-01 + DNS-01 mit EAB), Beispiel-Certificate, Secret-Vorlage unter `examples/kubernetes/cert-manager/`
- **DNS-Anbieter** -- Cloudflare, Route53, Azure DNS, Plesk und weitere für ACME-DNS-01-Challenges
- **Webhooks** -- Ereignisgesteuerte Benachrichtigungen zu Ereignissen im Zertifikatslebenszyklus (15+ Ereignistypen), **Zustellverlauf pro Endpunkt mit manueller Wiederholung**, dauerhafte asynchrone Zustellwarteschlange mit exponentiellem Backoff und ein Aufbewahrungsfenster für den Verlauf, damit er nicht unbegrenzt wächst

### Sicherheit & Zugriff
- **Authentifizierung** -- Passwort, WebAuthn/FIDO2 (auch als zweiter Faktor, neben oder anstelle von TOTP), TOTP-2FA, mTLS, API-Schlüssel (`X-API-Key` oder `Authorization: Bearer`)
- **SSO** -- LDAP (LDAPS oder StartTLS), OAuth2 (Azure/Google/GitHub), SAML-Single-Sign-On mit Single Logout, Rollenzuordnung zu integrierten und **eigenen Rollen** (SAML-Gruppen aus der Assertion gelesen, einschließlich Entra-ID- und AD-FS-Claims) und ein konfigurierbares NameID-Format; **Nachverfolgung von `auth_source` pro Benutzer** und optionale Rollensynchronisierung bei der Anmeldung
- **RBAC** -- 4 integrierte Rollen (Admin, Operator, Auditor, Viewer) plus eigene Rollen mit granularen Berechtigungen; **Gruppen vergeben zusätzliche Berechtigungen** zur Rolle eines Benutzers (nie Administrator)
- **Richtlinien & Genehmigungen** -- Richtlinien zur Zertifikatsausstellung mit Genehmigungsworkflows und durchgesetzten Regeln (erlaubte Schlüsseltypen und Signatur-Hashes, Obergrenze für DNS-SANs, Obergrenze für die Gültigkeit, begrenzt auf CA, Vorlage oder DNS-Muster), die **jeden Operatorpfad** binden (das Ausstellungsformular, das Signieren einer gespeicherten Anfrage einzeln oder in großen Mengen, und die Erneuerung) und für Schlüsseltypen und Hashes auch ACME, SCEP, EST, WSTEP und die CA-Erstellung; eine Richtlinie, die eine Genehmigung verlangt, hält **ACME-, EST-, SCEP- und WSTEP-Anfragen** in der Genehmigungswarteschlange zurück, und jedem Client wird das in der Sprache seines Protokolls mitgeteilt (ACME `processing`, EST 202 mit Retry-After, SCEP PENDING, WSTEP pending); eine Richtlinie kann auch **Widerrufe und Erneuerungen** unter Genehmigung stellen; eine Anfrage in der Warteschlange wird von selbst geschlossen, wenn ihr Ziel inzwischen signiert, erneuert, gelöscht oder widerrufen wurde
- **Schlüssel- und Hash-Vorgaben** -- Eine Anfrage ohne Schlüssel- oder Hash-Angabe folgt auf jedem Ausstellungspfad einer einzigen Vorgabe (RSA-2048 mit SHA-256, sofern ein Profil oder eine Richtlinie das nicht ablehnt, dann der erste zugelassene Typ), der Hash folgt dem Signaturschlüssel, und eine neue Zwischen-CA verwendet nie einen schwächeren Hash als ihre übergeordnete CA
- **Audit-Logs** -- Protokollierung von Aktionen mit Integritätsprüfung, Remote-Syslog-Weiterleitung und optionaler Aufbewahrungsdauer
- **Verschlüsselung privater Schlüssel** -- AES-128 (Fernet, HMAC-SHA256) im Ruhezustand unter einem Hauptschlüssel, der beim ersten Start erzeugt wird (in einem Container, wenn `/etc/ucm` ein Volume ist) oder als `KEY_ENCRYPTION_KEY` vorgegeben wird; er deckt CA- und Zertifikatsschlüssel, Schlüssel von SSH-CAs und Deployment-Zielen, ACME-Konto- und EAB-Schlüssel, SCEP-Challenges und LDAP-Bind-Passwörter ab, mit **Restliche Schlüssel verschlüsseln** für Geheimnisse, die vor der Aktivierung gespeichert wurden; bei aktivierter Verschlüsselung bleibt keine Klartext-Schlüsseldatei auf der Platte (vorhandene Kopien werden bei der Aktivierung und beim Start entfernt, öffentliche Zertifikatsdateien bleiben), und die Schlüsseldateien werden beim Deaktivieren neu angelegt
- **Hochverfügbarkeit** -- Zwei oder mehr Knoten auf einer PostgreSQL-Datenbank mit `UCM_HA=1` betreiben (Docker, Docker Compose, DEB/RPM oder `ha.enabled` des Helm-Charts): Ein gewählter Knoten führt die geplanten Aufgaben aus, Einstellungen, Verschlüsselung, Sicherungen und Rolling Updates erreichen jeden Knoten, und Sitzungen werden geteilt, sodass nur die Kerberos-Registrierungsendpunkte eine Affinität zur Quelladresse benötigen (siehe [docs/HA.md](docs/HA.md))
- **FIPS-Modus** -- Das Docker-Image `-fips` führt die Kryptografie von UCM im OpenSSL FIPS Provider 3.5.9 aus (CMVP-Zertifikat #5586), der ML-DSA, Ed25519 und Ed448 zulässt, sodass Post-Quanten- und EdDSA-Signaturen im FIPS-Modus mit dem Image verfügbar sind; die mit `UCM_FIPS_BUILD=1` gebauten DEB- und RPM-Pakete laufen auf dem FIPS-Modul von RHEL 9 (#5573) oder Ubuntu 24.04 Pro (#5115), die sie nicht bieten. Mit `UCM_FIPS=1` startet UCM nur auf einem aktiven, selbstgetesteten Modul, erzeugt Schlüssel darüber, erlaubt einen Algorithmus nur, wenn das geladene Modul ihn zulässt, und verweigert den Rest (MD5, 3DES, scrypt, Argon2id, Legacy-PKCS#12, NTLM); eine Bereitschaftsprüfung listet vorab auf, was eine Instanz verlieren würde. UCM selbst ist kein validiertes Modul, und Debian 13 sowie arm64 gehören nicht zu den getesteten Konfigurationen des Zertifikats #5586
- **Compliance-Profile** -- Richtlinien pro CA nach ANSSI PG-083, BSI TR-02102-1 und den von der ECCG vereinbarten kryptografischen Verfahren (Schlüsseltypen, Hashes, Signaturverfahren, Gültigkeitshorizonte, im HSM gehaltene CA-Schlüssel, EC-Zeitstempel-Signierer), mit Ablehnungen, wo der Text etwas vorschreibt, und Hinweisen, wo er etwas empfiehlt, und einem schreibgeschützten Preflight, bevor ein Profil an eine bestehende CA gebunden wird; UCM ist von keiner dieser Stellen zertifiziert oder qualifiziert
- **SBOM** -- Eine CycloneDX-SBOM für jede Paket- und Image-Plattform jedes Releases, gebunden an den Datei-Hash bzw. den Image-Digest, die auflistet, was ausgeliefert wird, mit Versionen und deklarierten Lizenzen, und was ein Paket bei der Installation auflöst ([docs/SBOM.md](docs/SBOM.md))
- **Härtung** -- Vom Betreiber konfigurierbares HSTS (Einstellungen → Sicherheit oder Umgebungsvariable), Absicherung der Client-Zertifikat-Header über vertrauenswürdige Proxys, API-Schlüssel-Berechtigungen auf die des Erstellers begrenzt; vertrauenswürdige Proxys lassen sich als CIDR-Netze angeben, und sobald die Proxy-Unterstützung aktiv ist, werden `X-Forwarded-*`-Header nur von ihnen akzeptiert, sodass ein Client, der das Backend direkt erreicht, seine Adresse nicht fälschen kann; die Weboberfläche und die Verwaltungs-API lassen sich auf **aufgeführte IP-Adressen und Netze beschränken**, während die PKI-Protokollendpunkte erreichbar bleiben

### Betrieb & Überwachung
- **Übersicht** -- Vier Kennzahlen, Einrichtungsschritte für den ersten Start und neun unabhängige Karten (Arbeitswarteschlange mit Aktionen zum Erneuern, Wiederholen und Veröffentlichen, Zustand der Automatisierung, Ausstellungen nach Quelle, Ablaufhorizont, Compliance, Widerrufsabdeckung, Hierarchie, letzte Vorgänge, Zertifizierungsstellen und HSM), ein-, ausgeblendet und umsortierbar mit pro Benutzer gespeicherten Layout-Voreinstellungen, die sich bei Datenänderungen von selbst neu laden
- **Berichte** -- Geplante PDF-Berichte, Management-Zusammenfassungen, widerrufene Zertifikate, eigene Vorlagen
- **Zertifikats-Toolbox** -- SSL-Prüfung, CSR-/Zertifikats-Decoder, Schlüsselabgleich, Formatkonverter
- **E-Mail-Benachrichtigungen** -- SMTP mit STARTTLS oder implizitem TLS (Port 465), **OAuth2 (XOAUTH2)** für Gmail, Outlook.com und Microsoft 365, anpassbare HTML-/Text-Vorlagen, Ablaufwarnungen für Zertifikate mit mehreren Tagesschwellen (eine E-Mail pro Schwelle und Gültigkeitszeitraum, eskalierend im Stil 30/14/7/1), optional ohne die Zertifikate, die ACME-Clients selbst erneuern
- **Deploy Hooks** -- Ausgestellte und erneuerte Zertifikate sowie neu erzeugte CRLs (DER oder ein PEM-Bundle mit den CRLs der übergeordneten CAs) per SSH/SFTP an entfernte Hosts übertragen, mit Zielpfaden und einem optionalen Reload-Befehl pro Bindung: schlüsselbasierte Authentifizierung (erzeugter ed25519- oder importierter Schlüssel, im Ruhezustand verschlüsselt), Host-Key-Pinning beim ersten Verbindungsaufbau, Zielpfade pro Bindung (Zertifikat / Schlüssel / vollständige Kette, die Kette ohne selbstsignierte Root, sofern die Bindung sie nicht anfordert, atomar geschrieben), dauerhafte Zustellwarteschlange mit Wiederholungen und Verlauf pro Zustellung, eine **Voreinstellung für denselben Host** für Dienste neben UCM sowie **HTTP-API-Ziele**, die ein Zertifikat in einer einzigen Anfrage an eine Firewall, einen Load Balancer oder eine Cloud-API übertragen, aufgebaut aus einer Body-Vorlage (URL, Methode, verschlüsselte Header, Variablen der Form `{{cert_pem|json}}`, privater Schlüssel nur mit ausdrücklichem Opt-in über verifiziertes HTTPS)
- **Sicherung & Wiederherstellung** -- Manuelle und geplante verschlüsselte Sicherungen mit Aufbewahrungsrichtlinien und einer optionalen Obergrenze für den Platz, den die gespeicherten Archive belegen; Archive sind Ströme unabhängig authentifizierter Blöcke, sodass ihr Erstellen und ihre Prüfung vor einer Wiederherstellung sie nicht vollständig im Speicher halten; Archive enthalten ACME-Client-Bestellungen und ausstehende Anfragen, werden im Merge- oder Replace-Modus wiederhergestellt, ordnen Zeilen installationsübergreifend über den Namen zu und spielen die Reparaturmigrationen erneut ab
- **Diagnose-Log-Paket** -- Download mit einem Klick (Einstellungen → Info → Diagnose) von Anwendungslogs, Fehlerlog, systemd-Journal und einer geheimnisfreien Systemdiagnose als ZIP, mit geschwärzten sensiblen Token
- **Systemlog-Viewer** -- Anwendungs-, Zugriffs-, Fehler- und systemd-Journal-Logs in der Oberfläche durchsuchen, gefiltert nach Level, Zeitfenster und Text, mit geschwärzten Geheimnissen
- **Prometheus-Metriken** -- optionaler, per Bearer-Token geschützter Endpunkt `/metrics` mit Zählern zu Zertifikaten, CAs, Scheduler, Webhooks und ACME
- **Scheduler** -- Admin-Ansicht der Hintergrundaufgaben (Ablaufprüfungen, CRL-Aktualisierung, Webhook-Zustellung, Sicherungen, automatische Erneuerung) mit Status und „Jetzt ausführen“, unter Gunicorn in einem eigenen Prozess ausgeführt
- **HTTPS für sich selbst** -- Ein beliebiges ausgestelltes Zertifikat auf die Weboberfläche anwenden; die Bindung folgt Erneuerungen automatisch (Dateien neu erzeugt, Dienst neu gestartet)
- **Sichere Netzwerk-Voreinstellungen** -- Dual-Stack-Listening (`HOST=::` bedient IPv6 und IPv4 über einen Socket) und Schutzmechanismen für die Admin-Base-URL (Erreichbarkeitsprüfung vor dem Anwenden, kanonische Weiterleitung tritt zurück, wenn der Host nicht mehr aufgelöst wird, Notfallschalter `UCM_DISABLE_CANONICAL_REDIRECT=1`)
- **Software-Updates** -- Update-Prüfung in der Anwendung mit Installation per Klick, geplante tägliche Prüfung auf einem Stable- oder Release-Candidate-Kanal und optionale unbeaufsichtigte Installation (DEB/RPM) mit verpflichtender SHA256-Verifizierung und wahrheitsgemäßen Ergebnisereignissen (als installiert gemeldet erst, wenn die tatsächliche Installation versionsgeprüft ist), plus ein optionales einmaliges Release-Notes-Fenster pro Benutzer nach einem Update
- **Globale Suche** -- Ressourcenübergreifende Suche und Befehlspalette (Strg+K)

### Plattform
- **Themes** -- Atelier und Aurore, jeweils dunkel oder hell oder dem System folgend; **pro Benutzer serverseitig gespeicherte Einstellungen** (Sprache, Theme, Modus)
- **i18n** -- 10 Sprachen (EN, FR, DE, ES, IT, PT, UK, RU, ZH, JA)
- **Gespeicherter UI-Zustand** -- Filterauswahlen bleiben auf den wichtigsten Listenseiten über Neuladen hinweg erhalten (Zertifikate, CAs, Vorlagen, Richtlinien, Audit-Logs, Vertrauensspeicher, Benutzer, SSH)
- **Datenbank** -- SQLite (Standard) oder **natives PostgreSQL-Backend** mit bidirektionaler Migrationsoberfläche
- **Responsive Oberfläche** -- React 18 + Radix UI, mobilfreundlich
- **Echtzeit** -- WebSocket-Live-Updates: Eine Änderung eines anderen Operators aktualisiert die Listen, die sie zeigen, und nach einem Ausfall lädt eine Wiederverbindung sie neu, statt veraltete Zeilen auf dem Bildschirm zu lassen
- **Multiplattform** -- Docker, Debian/Ubuntu (.deb), RHEL/Rocky/Fedora (.rpm); die Pakete richten die Log-Rotation für Zugriffs- und Fehlerlogs ein
- **Reverse-Proxy-tauglich** -- Öffentliche Ports unabhängig von den Listen-Ports (ein ausdrückliches `:80` oder `:443` in den Base-URLs wird wie eingegeben angekündigt), vertrauenswürdige Proxys per IP oder CIDR-Netz und `proxy.*`-Werte des Helm-Charts für einen Ingress vor UCM

---

## Schnellstart

### Docker

```bash
docker run -d --restart=unless-stopped \
  --name ucm \
  -p 8443:8443 \
  -p 8080:8080 \
  -v ucm-data:/opt/ucm/data \
  -v ucm-config:/etc/ucm \
  neyslim/ultimate-ca-manager:latest
```

Auch über die GitHub Container Registry verfügbar: `ghcr.io/neyslim/ultimate-ca-manager`. Die FIPS-Variante trägt das Tag `<version>-fips` (mit `UCM_FIPS=1` starten).

### Debian/Ubuntu

Laden Sie das `.deb`-Paket aus dem [aktuellen Release](https://github.com/NeySlim/ultimate-ca-manager/releases/latest) herunter:

```bash
sudo dpkg -i ucm_<version>_all.deb
sudo systemctl enable --now ucm
```

### RHEL/Rocky/Fedora

Laden Sie das `.rpm`-Paket aus dem [aktuellen Release](https://github.com/NeySlim/ultimate-ca-manager/releases/latest) herunter: `ucm-VERSION-1.fc43.noarch.rpm` für Fedora, `ucm-el9-VERSION-1.el9.noarch.rpm` für RHEL, Rocky Linux und AlmaLinux 9, `ucm-el10-VERSION-1.el10.noarch.rpm` für dieselben Distributionen in Version 10.

```bash
sudo dnf install ./ucm-VERSION-1.fc43.noarch.rpm
sudo systemctl enable --now ucm
```

**Zugriff:** `https://localhost:8443` oder `https://your-server-fqdn:8443`
**Erste Anmeldung:** `admin`, mit dem beim ersten Start erzeugten Passwort: `sudo cat /opt/ucm/data/initial-admin-password` (Docker: `docker exec <container> cat /opt/ucm/data/initial-admin-password`). Es muss bei der ersten Anmeldung geändert werden. Wie Sie ein eigenes vorgeben, steht unter [Erster Zugriff](docs/installation/README.md#first-access).

Alle Methoden, einschließlich Docker Compose und Installation aus dem Quellcode, beschreibt der [Installationsleitfaden](docs/installation/README.md).

---

## Dokumentation

| Ressource | Link |
|-----------|------|
| Wiki (vollständige Dokumentation) | [github.com/NeySlim/ultimate-ca-manager/wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki) |
| Installation | [docs/installation/](docs/installation/README.md) |
| Benutzerhandbuch | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| Administratorhandbuch | [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md) |
| Microsoft Intune SCEP | [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md) |
| ACME-Proxy-Clients | [docs/integrations/acme-proxy-clients.md](docs/integrations/acme-proxy-clients.md) |
| API-Referenz | [docs/API_REFERENCE.md](docs/API_REFERENCE.md) |
| Sicherheit | [docs/SECURITY.md](docs/SECURITY.md) |
| Upgrade-Leitfaden | [UPGRADE.md](UPGRADE.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |

---

## Technologie-Stack

| Komponente | Technologie |
|------------|-------------|
| Frontend | React 18, Vite, Radix UI, Recharts |
| Backend | Python 3.11+, Flask, SQLAlchemy |
| Datenbank | SQLite oder PostgreSQL |
| Server | Gunicorn + gevent WebSocket |
| Kryptografie | pyOpenSSL, cryptography |
| Authentifizierung | Session-Cookies, WebAuthn/FIDO2, TOTP, mTLS |

---

## Dateipfade

| Element | Pfad |
|---------|------|
| Anwendung | `/opt/ucm/` |
| Daten & DB | `/opt/ucm/data/` |
| Konfiguration (DEB/RPM) | `/etc/ucm/ucm.env` |
| Logs (DEB/RPM) | `/var/log/ucm/` |
| Dienst | `systemctl status ucm` |

Docker: Daten unter `/opt/ucm/data/` (als Volume einbinden), Konfiguration über Umgebungsvariablen, Logs nach stdout.

---

## Mitwirken

Pull Requests zielen auf `dev`, und beim ersten werden Sie gebeten, einmalig die
[CLA](CLA.md) zu unterzeichnen. Den Rest beschreibt [CONTRIBUTING.md](CONTRIBUTING.md): wie man
einen Fehler nützlich meldet, wie ein prüfbarer Pull Request aussieht und welche Regeln für
Tests, Übersetzungen und Migrationen gelten.

---

## Lizenz

UCM ist freie Software unter der [GNU AGPL v3.0 only](LICENSE). Der Betrieb, in beliebigem Umfang und auch kommerziell, kostet nichts; für alle, die es verändern und ihre Änderungen nicht veröffentlichen können, gibt es eine [kommerzielle Lizenz](COMMERCIAL-LICENSE.md).

Versionen vor 2.243 bleiben unter ihrer ursprünglichen Lizenz, BSD 3-Clause mit der Commons Clause.

---

## Support

- [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- [GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)

Wenn Sie UCM nützlich finden, unterstützen Sie gern seine Entwicklung:

<a href="https://ko-fi.com/neyslim"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support on Ko-fi" /></a>
