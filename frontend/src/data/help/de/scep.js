export default {
  helpContent: {
    title: 'SCEP',
    subtitle: 'Simple Certificate Enrollment Protocol',
    overview: 'SCEP ermöglicht es Netzwerkgeräten (Router, Switches, Firewalls) und MDM-Lösungen, automatisch Zertifikate anzufordern und zu erhalten. Geräte authentifizieren sich über ein Challenge-Passwort.',
    sections: [
      {
        title: 'Tabs',
        items: [
          { label: 'Anfragen', text: 'Ausstehende, genehmigte und abgelehnte SCEP-Registrierungsanfragen' },
          { label: 'Konfiguration', text: 'SCEP-Servereinstellungen: CA-Auswahl, Auto-Genehmigung' },
          { label: 'Profile', text: 'Benannte Enrollment-Endpunkte, jeder mit eigener URL, CA, Vorlage und Challenge' },
          { label: 'Intune-App-Registrierungen', text: 'Entra-App-Registrierungen (Mandanten-ID, Client-ID, Client-Secret), die sich die Profile teilen, die Intune-Challenges validieren; ein leeres Secret beim Bearbeiten behält das bisherige, Verbindung testen fordert ein Token an und ermittelt den Dienst, ohne eine Challenge zu verbrauchen, und eine noch von einem Profil verwendete App kann nicht gelöscht werden' },
          { label: 'Herausforderungen', text: 'Die Challenge-Passwörter für die Geräteregistrierung anzeigen und neu erzeugen' },
          { label: 'Information', text: 'SCEP-Endpunkt-URLs und Integrationsanweisungen' },
        ]
      },
      {
        title: 'Konfiguration',
        items: [
          { label: 'Signierende CA', text: 'Auswählen, welche CA SCEP-registrierte Zertifikate signiert. Geräte verschlüsseln ihre Anfrage an diese CA, daher muss sie einen RSA-Schlüssel in Software besitzen: EC-, HSM-gestützte, schlüssellose, Offline- und widerrufene CAs werden nicht aufgelistet (v2.248)' },
          { label: 'Auto-Genehmigung', text: 'Anfragen mit gültigem Challenge-Passwort automatisch genehmigen, oder Erneuerungen, die von einem durch denselben Endpunkt ausgestellten Zertifikat signiert sind' },
          { label: 'Über Klartext-HTTP bereitstellen', text: 'Standardmäßig aus. Beantwortet SCEP zusätzlich auf dem HTTP-Protokollport (standardmäßig 8080) unter http://ihr-server:8080/scep/pkiclient.exe und den Profil-URLs, für Clients wie sscep, die HTTPS nicht verwenden können. RFC 8894 §7.10: SCEP-Nachrichten sind bereits geschützt, der CMS-Umschlag hält das Challenge-Passwort geheim' },
          { label: 'Challenge-Passwort', text: 'Gemeinsames Geheimnis, das Geräte zur Authentifizierung der Registrierung verwenden. Eine Erneuerung (RenewalReq), die von einem durch denselben Endpunkt (Profil oder global) ausgestellten Zertifikat signiert ist, wird durch dieses Zertifikat authentifiziert, daher wird ihre Challenge nicht geprüft und ein Wechsel des Geheimnisses hindert bereits registrierte Geräte nicht an der Erneuerung (RFC 8894 §2.4). Jedes andere Zertifikat benötigt weiterhin die Challenge des Endpunkts' },
          { label: 'Geräteschlüssel (v2.248)', text: 'Ein Gerät signiert seine Anfrage mit einem RSA-, ECDSA-, Ed25519- oder ML-DSA-Schlüssel; eine ML-DSA-Signatur folgt RFC 9882 (SHA-512-Digest). Ed448 wird abgelehnt, ML-DSA im FIPS-Modus ebenfalls' },
        ]
      },
      {
        title: 'Profile',
        items: [
          { label: 'URL-Segment', text: 'Jedes Profil wird unter /scep/<segment>/pkiclient.exe bereitgestellt, jede Geräteflotte oder jedes MDM-Profil auf die eigene URL zeigen lassen' },
          { label: 'Zertifikatsvorlage', text: 'Ist eine Vorlage gebunden, bestimmen deren KU/EKU und Gültigkeit jedes über das Profil ausgestellte Zertifikat' },
          { label: 'Signatur-Digest (v2.251)', text: 'Über ein Profil ausgestellte Zertifikate werden mit dem Digest ihres Templates signiert, angehoben auf den zum CA-Schlüssel passenden, als Präferenz, die die Richtlinien überschreiben können. Ohne Template gilt der Digest des CA-Schlüssels' },
          { label: 'Challenge pro Profil', text: 'Jedes Profil hat ein eigenes, verschlüsselt gespeichertes Challenge-Passwort mit demselben Ablauffenster wie die globale Challenge' },
          { label: 'Standard-Endpunkt', text: 'Der Endpunkt /scep/pkiclient.exe ohne Segment bedient weiterhin die globale Konfiguration' },
          { label: 'Microsoft Intune-Validierung', text: 'Ein Profil kann anstelle eines statischen Passworts gegen Intunes eigene gerätespezifische SCEP-Challenge validieren: im Profil eine App-Registrierung aus dem Tab Intune-App-Registrierungen auswählen (Berechtigungen SCEP challenge validation + Application.Read.All), Auto-Genehmigung bleibt Pflicht; beim Upgrade erhält jedes bestehende Profil eine nach ihm benannte App, dedupliziert nach Mandant und Client' },
          { label: 'Manuelle Genehmigung', text: 'Eine über ein Profil eingegangene Anfrage wird mit der Vorlage dieses Profils (Gültigkeit, Key Usages) genehmigt, genau wie die Auto-Genehmigung sie ausstellen würde' },
          { label: 'Zwecke, die kein Antragsteller erhalten darf', text: 'Eine an ein Profil gebundene Vorlage darf weder OCSP-Signierung, Zeitstempelung, „Any Purpose" noch Smartcard-Anmeldung tragen, und eine SCEP-Erneuerung übernimmt sie nie; Smartcard-Anmeldung ist erlaubt, wenn das Profil gegen Intune validiert, das für die Identität bürgt' },
        ]
      },
    ],
    tips: [
      'Verwenden Sie eindeutige Challenge-Passwörter pro CA für bessere Sicherheitsüberwachung',
      'Auto-Genehmigung ist praktisch, aber überprüfen Sie Anfragen in Hochsicherheitsumgebungen manuell',
      'SCEP-URL: https://ihr-server:8443/scep/pkiclient.exe für die konfigurierte CA, https://ihr-server:8443/scep/<profil>/pkiclient.exe für ein Profil',
      'Intune-Profile benötigen aktivierte Auto-Genehmigung: die Registrierung bei Intune ist ein synchroner Validierungs- und Ausstellungsvorgang ohne Genehmigungswarteschlange auf Intune-Seite',
    ],
    warnings: [
      'Das Challenge-Passwort gehört in den CSR, der im CMS-Umschlag, verschlüsselt an die CA, übertragen wird (RFC 8894 §2.4), daher legt Klartext-HTTP es nicht offen; ein Client, der es als signiertes Attribut außerhalb des Umschlags sendet, legt es offen, über HTTP und gegenüber allem, was die Anfrage protokolliert',
    ],
  },
  helpGuides: {
    title: 'SCEP-Server',
    content: `
## Übersicht

Das Simple Certificate Enrollment Protocol (SCEP) ermöglicht es Netzwerkgeräten. Routern, Switches, Firewalls, MDM-verwalteten Endpunkten: automatisch Zertifikate anzufordern und zu erhalten.

## Tabs

### Anfragen
Alle SCEP-Registrierungsanfragen anzeigen:
- **Ausstehend**: Warten auf manuelle Genehmigung (wenn Auto-Genehmigung deaktiviert ist)
- **Genehmigt**: Erfolgreich ausgestellt
- **Abgelehnt**: Von einem Administrator abgelehnt

### Konfiguration
Den SCEP-Server konfigurieren:
- **Aktivieren/Deaktivieren**: Den SCEP-Dienst umschalten
- **Signierende CA**: Auswählen, welche CA SCEP-registrierte Zertifikate signiert. Geräte verschlüsseln ihre Anfrage an diese CA, daher muss sie einen RSA-Schlüssel in Software besitzen: EC-, HSM-gestützte, schlüssellose, Offline- und widerrufene CAs werden nicht aufgelistet (v2.248)
- **Auto-Genehmigung**: Anfragen mit gültigem Challenge-Passwort automatisch genehmigen, oder Erneuerungen, die von einem durch denselben Endpunkt ausgestellten Zertifikat signiert sind
- **Über Klartext-HTTP bereitstellen**: standardmäßig aus. Beantwortet SCEP zusätzlich auf dem HTTP-Protokollport (standardmäßig 8080) für Clients, die HTTPS nicht verwenden können, etwa sscep. RFC 8894 §7.10: SCEP-Nachrichten sind bereits geschützt, TLS ist daher nicht erforderlich; der CMS-Umschlag hält das Challenge-Passwort geheim

### Profile
Benannte Enrollment-Endpunkte, jeder unter seiner eigenen URL bereitgestellt:

\`\`\`
https://ihr-server:8443/scep/<profil>/pkiclient.exe
\`\`\`

Jedes Profil ist gebunden an:
- **Seine eigene CA**: verschiedene Geräteflotten können sich gegen verschiedene CAs registrieren
- **Eine optionale Zertifikatsvorlage**: ist eine Vorlage gebunden, bestimmen deren Key Usage, Extended Key Usage und Gültigkeit jedes über das Profil ausgestellte Zertifikat
- **Zwecke, die kein Antragsteller erhalten darf**: eine an ein Profil gebundene Vorlage darf weder OCSP-Signierung, Zeitstempelung, „Any Purpose" noch Smartcard-Anmeldung tragen, und eine SCEP-Erneuerung übernimmt sie nie; Smartcard-Anmeldung ist erlaubt, wenn das Profil gegen Intune validiert, das für die Identität bürgt
- **Ein Challenge-Passwort pro Profil**: verschlüsselt gespeichert, mit demselben Ablauffenster wie die globale Challenge
- **Eine Genehmigungsrichtlinie**: Auto-Genehmigung oder manuelle Prüfung pro Profil

Lassen Sie jede Geräteflotte, jedes MDM-Profil oder jeden Mandanten auf die eigene Profil-URL zeigen. Der Endpunkt \`/scep/pkiclient.exe\` ohne Segment bedient weiterhin unverändert die globale Konfiguration.

### Challenge-Passwörter
Der Tab **Herausforderungen** zeigt die Challenge-Passwörter. Geräte müssen ein gültiges Challenge-Passwort in ihrer Registrierungsanfrage zur Authentifizierung angeben.

- **Passwort anzeigen**: Das aktuelle Challenge für eine CA anzeigen
- **Regenerieren**: Ein neues Challenge-Passwort erstellen (macht das alte für neue Registrierungen ungültig)

Eine Erneuerung (RenewalReq), die von einem durch denselben Endpunkt (Profil oder global) ausgestellten Zertifikat signiert ist, wird durch dieses Zertifikat authentifiziert: Ihr Challenge-Passwort wird nicht geprüft, sodass ein neu erzeugtes Geheimnis bereits registrierte Geräte nicht an der Erneuerung hindert (RFC 8894 §2.4). Ein anderswo ausgestelltes Zertifikat, durch ein anderes Profil, ACME, EST oder die Oberfläche, benötigt weiterhin die Challenge des Endpunkts. Ein EC-Gerät sendet weiterhin ein Passwort, das die Verschlüsselung seiner Antwort schlüsselt.

### Information
Zeigt die SCEP-Endpunkt-URL und Integrationsanweisungen an.

## SCEP-Registrierungsablauf

1. Gerät sendet eine **GetCACert**-Anfrage, um das CA-Zertifikat zu erhalten
2. Gerät generiert ein Schlüsselpaar und erstellt einen CSR
3. Gerät verpackt den CSR mit dem **Challenge-Passwort** und sendet eine **PKCSReq**
4. UCM validiert das Challenge-Passwort
5. Wenn Auto-Genehmigung aktiv ist, signiert UCM das Zertifikat und gibt es zurück
6. Wenn Auto-Genehmigung deaktiviert ist, prüft ein Admin die Anfrage und genehmigt/lehnt ab

### Geräteschlüssel
Das Gerät signiert seine PKCSReq mit seinem eigenen Schlüssel: RSA, ECDSA, Ed25519 oder ML-DSA. Eine ML-DSA-Signatur wird nach RFC 9882 geprüft (SHA-512-Digest, die eigene Algorithmenkennung des Schlüssels, keine Parameter). Ed448-Signaturen werden abgelehnt, ML-DSA-Signaturen im FIPS-Modus ebenfalls. Die Anfrage wird weiterhin an die signierende RSA-CA verschlüsselt.

## SCEP-URLs

\`\`\`
https://ihr-server:8443/scep/pkiclient.exe            (konfigurierte CA)
https://ihr-server:8443/scep/<profil>/pkiclient.exe  (Endpunkt pro Profil)
https://ihr-server:8443/cgi-bin/pkiclient.exe         (konfigurierte CA, Legacy-Pfad)
http://ihr-server:8080/scep/pkiclient.exe             (mit Über Klartext-HTTP bereitstellen)
\`\`\`

Geräte benötigen die URL für die Registrierung; \`/scep\` allein ist die Weboberfläche, kein SCEP-Endpunkt. Verwenden Sie eine Profil-URL, um die CA, Vorlage und das Challenge-Passwort dieses Profils anzusprechen.

### CA-Wechsel (GetNextCACert)
GetNextCACert liefert den Nachfolger der CA des Endpunkts, signiert von der aktuellen CA: eine andere CA mit derselben übergeordneten CA und demselben Subject-DN, nicht widerrufen, nicht offline, mit einem RSA-Schlüssel in Software und mit späterem Ablauf. Eine CA, die nur den Anzeigenamen teilt, wird nie ausgeliefert; ohne Nachfolger lautet die Antwort 404.

## Anfragen genehmigen/ablehnen

Für ausstehende Anfragen (Auto-Genehmigung deaktiviert):
1. Prüfen Sie die Anfragedetails (Betreff, Transaktions-ID, Status, CSR)
2. Klicken Sie auf **Genehmigen**, um das Zertifikat zu signieren und auszustellen
3. Oder klicken Sie auf **Ablehnen** mit einem Grund

Eine über ein Profil eingegangene Anfrage wird mit der Vorlage dieses Profils (Gültigkeit, Key Usages) ausgestellt, genau wie bei der Auto-Genehmigung.

> Das Challenge-Passwort gehört in den CSR, der im CMS-Umschlag, verschlüsselt an die CA, übertragen wird (RFC 8894 §2.4), daher legt Klartext-HTTP es nicht offen. Ein Client, der es als signiertes Attribut außerhalb des Umschlags sendet, legt es offen: Lassen Sie solche Clients bei HTTPS.

## Geräteintegration

### Cisco IOS
\`\`\`
crypto pki trustpoint UCM
  enrollment url https://ihr-server:8443/scep/pkiclient.exe
  password <challenge-passwort>
\`\`\`

### JAMF
Konfigurieren Sie das SCEP-Profil mit:
- Server-URL: \`https://ihr-server:8443/scep/pkiclient.exe\`, oder der \`/scep/<profil>/pkiclient.exe\` eines Profils
- Challenge: das Passwort von UCM

### Microsoft Intune
Intune unterstützt kein statisches Challenge-Passwort: es stellt eine eigene verschlüsselte, gerätespezifische Challenge aus, die nur die Intune-API validieren kann. Aktivieren Sie auf einem SCEP-**Profil** (nicht dem globalen Endpunkt) **Microsoft Intune SCEP-Challenge-Validierung** und geben Sie Mandanten-ID, Client-ID und Client-Secret einer Entra-App-Registrierung an:

1. Registrieren Sie in Microsoft Entra ID eine App und erteilen Sie ihr die Anwendungsberechtigungen **Intune API → SCEP challenge validation** (\`scep_challenge_provider\`) und **Microsoft Graph → Application.Read.All**, beide mit Administratorzustimmung
2. Legen Sie unter **Intune-App-Registrierungen** die App-Registrierung einmalig an (Name, Mandanten-ID, Client-ID, Client-Secret) und klicken Sie auf **Verbindung testen**, um zu bestätigen, dass UCM Intune erreichen kann; wählen Sie sie dann im Profil im Selektor **App-Registrierung** aus. Profile desselben Mandanten teilen sie sich, das Secret wird also an einer einzigen Stelle rotiert
3. Zeigen Sie in Intune die Server-URL des Geräte-SCEP-Profils auf den Endpunkt \`/scep/<segment>/pkiclient.exe\` dieses Profils

Intune-Profile müssen **Auto-Genehmigung** aktiviert haben: die Registrierung bei Intune ist ein synchroner Validierungs- und Ausstellungsvorgang, ohne Warteschlange auf Intune-Seite für eine manuelle Prüfung.
`
  }
}
