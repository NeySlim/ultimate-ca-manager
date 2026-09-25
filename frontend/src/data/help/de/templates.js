export default {
  helpContent: {
    title: 'Zertifikatstemplates',
    subtitle: 'Wiederverwendbare Zertifikatsprofile',
    overview: 'Definieren Sie wiederverwendbare Zertifikatsprofile mit vorkonfigurierten Betreffsfeldern, Key Usage, Extended Key Usage, Gültigkeitszeiträumen und anderen Erweiterungen. Wenden Sie Templates bei der Ausstellung oder Signierung von Zertifikaten an.',
    sections: [
      {
        title: 'Herkunft',
        definitions: [
          { term: 'System', description: 'Bei der Installation mitgeliefert. Duplizieren Sie eines für eine bearbeitbare Kopie: es selbst kann weder bearbeitet noch gelöscht werden' },
          { term: 'Benutzerdefiniert', description: 'Hier erstellt oder importiert, und die einzige Art, die bearbeitet oder gelöscht werden kann' },
        ]
      },
      {
        title: 'Funktionen',
        items: [
          { label: 'Typ', text: 'Web Server, Email, VPN Server oder Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon oder Custom. Legt die Standardwerte für Key Usage, EKU und SAN fest' },
          { label: 'Betreffsstandards', text: 'Organisation, OU, Land, Bundesland, Stadt und E-Mail vorausfüllen. Bei „E-Mail"- und „Server + Client (Kombiniert)"-Zertifikaten wird die E-Mail zusätzlich zum SAN' },
          { label: 'Key Usage', text: 'Digital Signature, Key Encipherment, usw.' },
          { label: 'Extended Key Usage', text: 'Server Auth, Client Auth, Code Signing, Email Protection' },
          { label: 'Gültigkeit', text: 'Standard-Gültigkeitsdauer in Tagen' },
          { label: 'Duplizieren', text: 'Ein vorhandenes Template klonen und modifizieren' },
          { label: 'System anzeigen', text: 'Die mitgelieferten Templates ausblenden, um nur mit Ihren eigenen zu arbeiten. Wird pro Browser gespeichert' },
          { label: 'Import/Export', text: 'Templates als JSON-Dateien zwischen UCM-Instanzen teilen, ein Template oder mehrere in einer Datei' },
        ]
      },
      {
        title: 'Windows-Autoregistrierung',
        items: [
          { label: 'Autoregistrierung erlauben', text: 'Das Template als autoEnroll=true in der Certificate Enrollment Policy ausweisen, damit GPO/Kerberos-Clients es bei der Anmeldung automatisch anfordern. Standardmäßig aus, manuelle Registrierung bleibt auch ohne dieses Flag möglich' },
          { label: 'Betreff aus Active Directory ableiten', text: 'Betreff und SAN aus dem AD-Objekt des Anfragenden ableiten (über den AD-Connector), statt sie vom Client zu verlangen, für unbeaufsichtigte GPO-Autoregistrierung' },
          { label: 'Registrierung auf AD-Gruppe beschränken', text: 'Nur Mitglieder der konfigurierten AD-Gruppe (einschließlich verschachtelter Mitgliedschaften) dürfen über den Kerberos-Endpunkt registrieren. Leer = jeder authentifizierte Principal. Auf dem Benutzername/Passwort-Endpunkt nicht durchgesetzt' },
          { label: 'Gepinnte Betreffsfelder', text: 'C/ST/L/O/OU-Werte auf jedem über WSTEP ausgestellten Zertifikat erzwingen, sie überschreiben CSR oder AD-Ableitung für diese Felder. CN und SAN sind nie betroffen, lassen Sie ein Feld leer, um es dynamisch zu halten' },
        ]
      },
    ],
    tips: [
      'Erstellen Sie separate Templates für TLS-Server, Clients und Code-Signierung',
      'Verwenden Sie die Duplizieren-Aktion, um schnell Varianten eines Templates zu erstellen, auch von einem System-Template',
      'Templates mit Autoregistrierungs-Flags zeigen AD- / Auto- / ACL- / Pinned-Badges in der Liste',
    ],
  },
  helpGuides: {
    title: 'Zertifikatstemplates',
    content: `
## Übersicht

Templates definieren wiederverwendbare Zertifikatsprofile. Anstatt Key Usage, Extended Key Usage, Gültigkeit und Betreffsfelder jedes Mal manuell zu konfigurieren, wenden Sie ein Template an, um alles vorzufüllen.

## System und Benutzerdefiniert

Jedes Template gehört zu einer der beiden Arten, angezeigt in der Spalte **Herkunft**.

### System
Die bei der Installation mitgelieferten Templates: Web Server (TLS/SSL), Email Certificate (S/MIME), VPN Server, VPN Client, Code Signing, OCSP Signing, Client Authentication und Smartcard Logon. Bearbeiten und Löschen werden für sie abgelehnt, in der Oberfläche wie über die API. **Duplizieren** liefert Ihnen eine bearbeitbare Kopie als Ausgangsbasis.

### Benutzerdefiniert
Alles, was hier erstellt oder importiert wurde. Diese Templates können frei bearbeitet und gelöscht werden.

Schalten Sie **System anzeigen** in der Werkzeugleiste aus, um die mitgelieferten Templates auszublenden und nur mit Ihren eigenen zu arbeiten. Die Wahl wird gespeichert, es sei denn, Sie haben noch keine benutzerdefinierten Templates; in diesem Fall bleiben die mitgelieferten sichtbar.

Zertifizierungsstellen werden nicht aus Templates erstellt: legen Sie sie auf der Seite **Zertifizierungsstellen** an.

## Template erstellen

1. Klicken Sie auf **Template erstellen**
2. Geben Sie einen **Namen** und eine optionale Beschreibung ein
3. Wählen Sie den Template-**Typ**: Web Server, Email, VPN Server, VPN Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon oder Custom. Er legt die Standardwerte für Key Usage, Extended Key Usage und SAN fest, die Sie anschließend ändern können
4. Konfigurieren Sie **Betreffsstandards** (O, OU, C, ST, L, CN, E-Mail). Bei „E-Mail"- und „Server + Client (Kombiniert)"-Zertifikaten wird die E-Mail zusätzlich zu einem E-Mail-SAN
5. Wählen Sie **Key Usage**-Flags
6. Wählen Sie **Extended Key Usage**-Werte
7. Legen Sie die **Standard-Gültigkeitsdauer** in Tagen fest
8. Klicken Sie auf **Erstellen**

## Templates verwenden

Wählen Sie beim Ausstellen eines Zertifikats oder Signieren eines CSR ein Template aus der Dropdown-Liste. Das Template füllt vor:
- Betreffsfelder (die Sie überschreiben können)
- Key Usage und Extended Key Usage
- Gültigkeitsdauer

## Windows-Autoregistrierungs-Flags

Templates tragen drei Opt-in-Flags für die Windows-Autoregistrierungsprotokolle (XCEP/WSTEP, konfiguriert unter **Einstellungen → Windows-Autoregistrierung**):

- **Autoregistrierung erlauben**: Das Template als \`autoEnroll=true\` in der Certificate Enrollment Policy ausweisen, damit GPO/Kerberos-authentifizierte Clients es bei der Anmeldung automatisch und ohne Benutzeraktion anfordern. Standardmäßig aus: wie bei echtem ADCS kann ein Template auch ohne dieses Flag manuell registriert werden (MMC „Neues Zertifikat anfordern", \`certreq\`), da Enroll und Autoenroll getrennte Berechtigungen sind.
- **Betreff aus Active Directory ableiten**: Für unbeaufsichtigte GPO-Autoregistrierung: Betreff und SAN des Zertifikats aus dem AD-Objekt des Anfragenden ableiten (über den AD-Connector), statt sie vom Client zu verlangen.
- **Registrierung auf AD-Gruppe beschränken**: Nur Principals, die der konfigurierten Active-Directory-Gruppe angehören (einschließlich verschachtelter Mitgliedschaften), dürfen dieses Template über den Kerberos-authentifizierten Endpunkt registrieren. Geben Sie einen Gruppennamen oder vollständigen DN ein; leer lassen, um jeden authentifizierten Principal zuzulassen: entsprechend dem ADCS-Standardverhalten. Auf dem Benutzername/Passwort-Endpunkt nicht durchgesetzt, da dort keine Identität pro Anfrage geprüft werden kann.

Templates mit diesen Flags zeigen **AD**-, **Auto**- und **ACL**-Badges in der Template-Liste.

## Gepinnte Betreffsfelder

Ein Template kann die organisatorischen Betreffsfelder: **C, ST, L, O, OU**: für über WSTEP ausgestellte Zertifikate **pinnen**. Ein gepinnter Wert wird auf jedes ausgestellte Zertifikat erzwungen und überschreibt, was der CSR des Clients oder die Active-Directory-Ableitung für dieses Feld liefert.

- **Common Name und Subject Alternative Name sind nie betroffen**: sie bleiben pro Anfragendem dynamisch
- Lassen Sie ein Feld leer, um es dynamisch zu halten
- Templates mit gepinnten Feldern zeigen ein **Pinned**-Badge, und die gepinnten Werte erscheinen im Template-Detailbereich

Nutzen Sie dies, um eine einheitliche organisatorische Identität (z.B. ein festes \`O\` und \`C\`) über eine autoregistrierte Flotte hinweg zu garantieren, unabhängig davon, was jeder Windows-Client übermittelt.

## Templates duplizieren

Klicken Sie auf **Duplizieren**, um eine Kopie eines vorhandenen Templates zu erstellen. Modifizieren Sie die Kopie, ohne das Original zu beeinflussen.

## Import & Export

### Export
Exportieren Sie Templates als JSON zum Teilen zwischen UCM-Instanzen.

### Import
Importieren Sie aus:
- **JSON-Datei**: Template-JSON-Datei hochladen, ein Template oder mehrere in einer Datei
- **JSON einfügen**: JSON direkt in den Textbereich einfügen

Ein Template, dessen Name bereits existiert, wird übersprungen, und der Import gibt an, welche das waren.

## Gängige Template-Beispiele

### TLS-Server
- Key Usage: Digital Signature, Key Encipherment
- Extended Key Usage: Server Authentication
- Gültigkeit: 365 Tage

### Client-Authentifizierung
- Key Usage: Digital Signature
- Extended Key Usage: Client Authentication
- Gültigkeit: 365 Tage

### Code-Signierung
- Key Usage: Digital Signature
- Extended Key Usage: Code Signing
- Gültigkeit: 365 Tage
`
  }
}
