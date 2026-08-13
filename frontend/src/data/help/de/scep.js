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
          { label: 'Konfiguration', text: 'SCEP-Servereinstellungen: CA-Auswahl, CA-Kennung, Auto-Genehmigung' },
          { label: 'Profile', text: 'Benannte Enrollment-Endpunkte, jeder mit eigener URL, CA, Vorlage und Challenge' },
          { label: 'Challenge-Passwörter', text: 'Pro-CA-Challenge-Passwörter für die Geräteregistrierung verwalten' },
          { label: 'Information', text: 'SCEP-Endpunkt-URLs und Integrationsanweisungen' },
        ]
      },
      {
        title: 'Konfiguration',
        items: [
          { label: 'Signierende CA', text: 'Auswählen, welche CA SCEP-registrierte Zertifikate signiert' },
          { label: 'Auto-Genehmigung', text: 'Anfragen mit gültigem Challenge-Passwort automatisch genehmigen' },
          { label: 'Challenge-Passwort', text: 'Gemeinsames Geheimnis, das Geräte zur Authentifizierung der Registrierung verwenden' },
        ]
      },
      {
        title: 'Profile',
        items: [
          { label: 'URL-Segment', text: 'Jedes Profil wird unter /scep/<segment>/pkiclient.exe bereitgestellt — jede Geräteflotte oder jedes MDM-Profil auf die eigene URL zeigen lassen' },
          { label: 'Zertifikatsvorlage', text: 'Ist eine Vorlage gebunden, bestimmen deren KU/EKU und Gültigkeit jedes über das Profil ausgestellte Zertifikat' },
          { label: 'Challenge pro Profil', text: 'Jedes Profil hat ein eigenes, verschlüsselt gespeichertes Challenge-Passwort mit demselben Ablauffenster wie die globale Challenge' },
          { label: 'Standard-Endpunkt', text: 'Der Endpunkt /scep/pkiclient.exe ohne Segment bedient weiterhin die globale Konfiguration' },
          { label: 'Microsoft Intune-Validierung', text: 'Ein Profil kann anstelle eines statischen Passworts gegen Intunes eigene gerätespezifische SCEP-Challenge validieren — erfordert eine Entra-App-Registrierung (Berechtigungen SCEP challenge validation + Application.Read.All) und aktivierte Auto-Genehmigung' },
        ]
      },
    ],
    tips: [
      'Verwenden Sie eindeutige Challenge-Passwörter pro CA für bessere Sicherheitsüberwachung',
      'Auto-Genehmigung ist praktisch, aber überprüfen Sie Anfragen in Hochsicherheitsumgebungen manuell',
      'SCEP-URL-Format: https://ihr-server:port/scep',
      'Intune-Profile benötigen aktivierte Auto-Genehmigung — die Registrierung bei Intune ist ein synchroner Validierungs- und Ausstellungsvorgang ohne Genehmigungswarteschlange auf Intune-Seite',
    ],
    warnings: [
      'Challenge-Passwörter werden in der SCEP-Anfrage übertragen — verwenden Sie HTTPS für Transportsicherheit',
    ],
  },
  helpGuides: {
    title: 'SCEP-Server',
    content: `
## Übersicht

Das Simple Certificate Enrollment Protocol (SCEP) ermöglicht es Netzwerkgeräten — Routern, Switches, Firewalls, MDM-verwalteten Endpunkten — automatisch Zertifikate anzufordern und zu erhalten.

## Tabs

### Anfragen
Alle SCEP-Registrierungsanfragen anzeigen:
- **Ausstehend** — Warten auf manuelle Genehmigung (wenn Auto-Genehmigung deaktiviert ist)
- **Genehmigt** — Erfolgreich ausgestellt
- **Abgelehnt** — Von einem Administrator abgelehnt

### Konfiguration
Den SCEP-Server konfigurieren:
- **Aktivieren/Deaktivieren** — Den SCEP-Dienst umschalten
- **Signierende CA** — Auswählen, welche CA SCEP-registrierte Zertifikate signiert
- **CA-Kennung** — Die Kennung, die Geräte verwenden, um die richtige CA zu finden
- **Auto-Genehmigung** — Anfragen mit gültigem Challenge-Passwort automatisch genehmigen

### Profile
Benannte Enrollment-Endpunkte, jeder unter seiner eigenen URL bereitgestellt:

\`\`\`
https://ihr-server:8443/scep/<profil>/pkiclient.exe
\`\`\`

Jedes Profil ist gebunden an:
- **Seine eigene CA** — verschiedene Geräteflotten können sich gegen verschiedene CAs registrieren
- **Eine optionale Zertifikatsvorlage** — ist eine Vorlage gebunden, bestimmen deren Key Usage, Extended Key Usage und Gültigkeit jedes über das Profil ausgestellte Zertifikat
- **Ein Challenge-Passwort pro Profil** — verschlüsselt gespeichert, mit demselben Ablauffenster wie die globale Challenge
- **Eine Genehmigungsrichtlinie** — Auto-Genehmigung oder manuelle Prüfung pro Profil

Lassen Sie jede Geräteflotte, jedes MDM-Profil oder jeden Mandanten auf die eigene Profil-URL zeigen. Der Endpunkt \`/scep/pkiclient.exe\` ohne Segment bedient weiterhin unverändert die globale Konfiguration.

### Challenge-Passwörter
Pro-CA-Challenge-Passwörter verwalten. Geräte müssen ein gültiges Challenge-Passwort in ihrer Registrierungsanfrage zur Authentifizierung angeben.

- **Passwort anzeigen** — Das aktuelle Challenge für eine CA anzeigen
- **Regenerieren** — Ein neues Challenge-Passwort erstellen (macht das alte ungültig)

### Information
Zeigt die SCEP-Endpunkt-URL und Integrationsanweisungen an.

## SCEP-Registrierungsablauf

1. Gerät sendet eine **GetCACert**-Anfrage, um das CA-Zertifikat zu erhalten
2. Gerät generiert ein Schlüsselpaar und erstellt einen CSR
3. Gerät verpackt den CSR mit dem **Challenge-Passwort** und sendet eine **PKCSReq**
4. UCM validiert das Challenge-Passwort
5. Wenn Auto-Genehmigung aktiv ist, signiert UCM das Zertifikat und gibt es zurück
6. Wenn Auto-Genehmigung deaktiviert ist, prüft ein Admin die Anfrage und genehmigt/lehnt ab

## SCEP-URLs

\`\`\`
https://ihr-server:8443/scep                          (globaler Endpunkt)
https://ihr-server:8443/scep/<profil>/pkiclient.exe   (Endpunkt pro Profil)
\`\`\`

Geräte benötigen die URL plus die CA-Kennung für die Registrierung. Verwenden Sie eine Profil-URL, um die CA, Vorlage und das Challenge-Passwort dieses Profils anzusprechen.

## Anfragen genehmigen/ablehnen

Für ausstehende Anfragen (Auto-Genehmigung deaktiviert):
1. Prüfen Sie die Anfragedetails (Betreff, Schlüsseltyp, Challenge)
2. Klicken Sie auf **Genehmigen**, um das Zertifikat zu signieren und auszustellen
3. Oder klicken Sie auf **Ablehnen** mit einem Grund

> ⚠ Challenge-Passwörter werden in der SCEP-Anfrage übertragen. Verwenden Sie immer HTTPS für den SCEP-Endpunkt.

## Geräteintegration

### Cisco IOS
\`\`\`
crypto pki trustpoint UCM
  enrollment url https://ihr-server:8443/scep
  password <challenge-passwort>
\`\`\`

### JAMF
Konfigurieren Sie das SCEP-Profil mit:
- Server-URL: \`https://ihr-server:8443/scep\`
- Challenge: das Passwort von UCM

### Microsoft Intune
Intune unterstützt kein statisches Challenge-Passwort — es stellt eine eigene verschlüsselte, gerätespezifische Challenge aus, die nur die Intune-API validieren kann. Aktivieren Sie auf einem SCEP-**Profil** (nicht dem globalen Endpunkt) **Microsoft Intune SCEP-Challenge-Validierung** und geben Sie Mandanten-ID, Client-ID und Client-Secret einer Entra-App-Registrierung an:

1. Registrieren Sie in Microsoft Entra ID eine App und erteilen Sie ihr die Anwendungsberechtigungen **Intune API → SCEP challenge validation** (\`scep_challenge_provider\`) und **Microsoft Graph → Application.Read.All**, beide mit Administratorzustimmung
2. Geben Sie Mandanten-ID, Client-ID und Client-Secret im Profil ein und klicken Sie auf **Verbindung testen**, um vor dem Speichern zu bestätigen, dass UCM Intune erreichen kann
3. Zeigen Sie in Intune die Server-URL des Geräte-SCEP-Profils auf den Endpunkt \`/scep/<segment>/pkiclient.exe\` dieses Profils

Intune-Profile müssen **Auto-Genehmigung** aktiviert haben — die Registrierung bei Intune ist ein synchroner Validierungs- und Ausstellungsvorgang, ohne Warteschlange auf Intune-Seite für eine manuelle Prüfung.
`
  }
}
