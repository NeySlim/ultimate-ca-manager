export default {
  helpContent: {
    title: 'SCEP',
    subtitle: 'Simple Certificate Enrollment Protocol',
    overview: 'SCEP consente ai dispositivi di rete (router, switch, firewall) e alle soluzioni MDM di richiedere e ottenere automaticamente certificati. I dispositivi si autenticano utilizzando una challenge password.',
    sections: [
      {
        title: 'Schede',
        items: [
          { label: 'Richieste', text: 'Richieste di iscrizione SCEP in attesa, approvate e rifiutate' },
          { label: 'Configurazione', text: 'Impostazioni del server SCEP: selezione CA, approvazione automatica' },
          { label: 'Challenges', text: 'Visualizza e rigenera le challenge password per l\'iscrizione dei dispositivi' },
          { label: 'Informazioni', text: 'URL degli endpoint SCEP e istruzioni di integrazione' },
          { label: 'Profili', text: 'Endpoint di enrollment denominati, ciascuno con URL, CA, modello e challenge propri' },
          { label: 'Registrazioni dell\'app Intune', text: 'Registrazioni app Entra (tenant ID, client ID, client secret) condivise dai profili che validano le challenge di Intune; un secret vuoto in modifica conserva quello attuale, Verifica connessione richiede un token e individua il servizio senza consumare alcuna challenge, e un\'app ancora usata da un profilo non può essere eliminata' },
        ]
      },
      {
        title: 'Configurazione',
        items: [
          { label: 'CA firmataria', text: 'Seleziona quale CA firma i certificati iscritti tramite SCEP. I dispositivi cifrano la richiesta verso questa CA, che deve quindi avere una chiave RSA in software: le CA EC, basate su HSM, senza chiave, offline e revocate non sono elencate (v2.248)' },
          { label: 'Approvazione automatica', text: 'Approva automaticamente le richieste con challenge password valide, o i rinnovi firmati da un certificato emesso dallo stesso endpoint' },
          { label: 'Servire su HTTP semplice', text: "Disattivato per impostazione predefinita. Risponde a SCEP anche sulla porta del protocollo HTTP (8080 per impostazione predefinita), a http://your-server:8080/scep/pkiclient.exe e agli URL dei profili, per client come sscep che non possono usare HTTPS. RFC 8894 §7.10: i messaggi SCEP sono già protetti, la busta CMS mantiene privata la challenge password" },
          { label: 'Challenge Password', text: "Segreto condiviso che i dispositivi usano per autenticare l'iscrizione. Un rinnovo (RenewalReq) firmato da un certificato emesso dallo stesso endpoint (profilo o globale) è autenticato da quel certificato, quindi la sua challenge non viene controllata e ruotare il segreto non impedisce ai dispositivi iscritti di rinnovare (RFC 8894 §2.4). Qualsiasi altro certificato richiede ancora la challenge dell'endpoint" },
          { label: 'Chiavi del dispositivo (v2.248)', text: 'Un dispositivo firma la richiesta con una chiave RSA, ECDSA, Ed25519 o ML-DSA; una firma ML-DSA segue la RFC 9882 (digest SHA-512). Ed448 è rifiutato, e anche ML-DSA in modalità FIPS' },
        ]
      },
      {
        title: 'Profili',
        items: [
          { label: 'Segmento URL', text: 'Ogni profilo è servito su /scep/<segment>/pkiclient.exe, punta ogni flotta di dispositivi o profilo MDM al proprio URL' },
          { label: 'Modello di certificato', text: 'Quando un modello è associato, i suoi KU/EKU e la validità governano ogni certificato emesso tramite il profilo' },
          { label: 'Digest della firma (v2.251)', text: 'I certificati emessi tramite un profilo sono firmati con il digest del suo modello, portato a quello corrispondente alla chiave della CA, come preferenza che le policy possono sovrascrivere. Senza modello si applica il digest della chiave della CA' },
          { label: 'Challenge per profilo', text: 'Ogni profilo ha la propria password di challenge, memorizzata cifrata, con la stessa finestra di scadenza della challenge globale' },
          { label: 'Endpoint predefinito', text: 'L\'endpoint /scep/pkiclient.exe senza segmento continua a servire la configurazione globale' },
          { label: 'Validazione Microsoft Intune', text: 'Un profilo può validarsi contro la challenge SCEP propria di Intune per dispositivo invece di una password statica: scegli una registrazione app dalla scheda Registrazioni dell\'app Intune (permessi SCEP challenge validation + Application.Read.All), l\'approvazione automatica resta obbligatoria; all\'aggiornamento ogni profilo esistente ottiene un\'app con il suo nome, deduplicata per tenant e client' },
          { label: 'Approvazione manuale', text: 'Una richiesta arrivata tramite un profilo viene approvata con il modello di quel profilo (validità, key usage), esattamente come la emetterebbe l\'approvazione automatica' },
          { label: 'Scopi preclusi a chi si iscrive', text: 'Un modello associato a un profilo non può includere firma OCSP, marca temporale, "qualsiasi scopo" (any purpose) o Smartcard Logon, e un rinnovo SCEP non li riporta mai; Smartcard Logon è consentito quando il profilo si valida contro Intune, che garantisce l\'identità' },
        ]
      },
    ],
    tips: [
      'Usa challenge password uniche per CA per un miglior auditing di sicurezza',
      'L\'approvazione automatica è comoda ma rivedi le richieste manualmente in ambienti ad alta sicurezza',
      'URL SCEP: https://your-server:8443/scep/pkiclient.exe per la CA configurata, https://your-server:8443/scep/<profile>/pkiclient.exe per un profilo',
      'I profili Intune richiedono l\'approvazione automatica attiva: l\'iscrizione Intune è un round trip sincrono di convalida e poi emissione, senza coda di approvazione lato Intune',
    ],
    warnings: [
      "La challenge password è nella CSR, che viaggia dentro la busta CMS cifrata verso la CA (RFC 8894 §2.4), quindi l'HTTP semplice non la espone; un client che la invia come attributo firmato fuori dalla busta la espone, su HTTP e a qualsiasi cosa registri la richiesta",
    ],
  },
  helpGuides: {
    title: 'Server SCEP',
    content: `
## Panoramica

Il Simple Certificate Enrollment Protocol (SCEP) consente ai dispositivi di rete: router, switch, firewall, endpoint gestiti da MDM, di richiedere e ottenere automaticamente certificati.

## Schede

### Richieste
Visualizza tutte le richieste di iscrizione SCEP:
- **In attesa**: In attesa di approvazione manuale (se l'approvazione automatica è disattivata)
- **Approvate**: Emesse con successo
- **Rifiutate**: Negate da un amministratore

### Configurazione
Configura il server SCEP:
- **Abilita/Disabilita**: Attiva/disattiva il servizio SCEP
- **CA firmataria**: Seleziona quale CA firma i certificati iscritti tramite SCEP. I dispositivi cifrano la richiesta verso questa CA, che deve quindi avere una chiave RSA in software: le CA EC, basate su HSM, senza chiave, offline e revocate non sono elencate (v2.248)
- **Approvazione automatica**: Approva automaticamente le richieste con challenge password valide, o i rinnovi firmati da un certificato emesso dallo stesso endpoint
- **Servire su HTTP semplice**: disattivato per impostazione predefinita. Risponde a SCEP anche sulla porta del protocollo HTTP (8080 per impostazione predefinita) per i client che non possono usare HTTPS, come sscep. RFC 8894 §7.10: i messaggi SCEP sono già protetti, quindi TLS non è richiesto; la busta CMS mantiene privata la challenge password

### Profili
Endpoint di enrollment denominati, ciascuno servito su un URL proprio:

\`\`\`
https://your-server:8443/scep/<profile>/pkiclient.exe
\`\`\`

Ogni profilo è associato a:
- **La propria CA**: flotte di dispositivi diverse possono iscriversi presso CA diverse
- **Un modello di certificato opzionale**: quando associato, key usage, extended key usage e validità del modello governano ogni certificato emesso tramite il profilo
- **Scopi preclusi a chi si iscrive**: un modello associato a un profilo non può includere firma OCSP, marca temporale, "qualsiasi scopo" (any purpose) o Smartcard Logon, e un rinnovo SCEP non li riporta mai; Smartcard Logon è consentito quando il profilo si valida contro Intune, che garantisce l'identità
- **Una challenge password per profilo**: memorizzata cifrata, con la stessa finestra di scadenza della challenge globale
- **Una politica di approvazione**: approvazione automatica o revisione manuale per profilo

Punta ogni flotta di dispositivi, profilo MDM o tenant al proprio URL di profilo. L'endpoint senza segmento \`/scep/pkiclient.exe\` continua a servire la configurazione globale senza modifiche.

### Challenge Password
La scheda **Challenges** mostra le challenge password. I dispositivi devono includere una challenge password valida nella loro richiesta di iscrizione per autenticarsi.

- **Visualizza password**: Mostra la challenge attuale per una CA
- **Rigenera**: Crea una nuova challenge password (invalida quella precedente per le nuove iscrizioni)

Un rinnovo (RenewalReq) firmato da un certificato emesso dallo stesso endpoint (profilo o globale) è autenticato da quel certificato: la sua challenge password non viene controllata, quindi un segreto rigenerato non impedisce ai dispositivi iscritti di rinnovare (RFC 8894 §2.4). Un certificato emesso altrove, da un altro profilo, da ACME, EST o dall'interfaccia, richiede ancora la challenge dell'endpoint. Un dispositivo EC invia comunque una password, che cifra la sua risposta.

### Informazioni
Mostra l'URL dell'endpoint SCEP e le istruzioni di integrazione.

## Flusso di iscrizione SCEP

1. Il dispositivo invia una richiesta **GetCACert** per ottenere il certificato CA
2. Il dispositivo genera una coppia di chiavi e crea un CSR
3. Il dispositivo incapsula il CSR con la **challenge password** e invia un **PKCSReq**
4. UCM valida la challenge password
5. Se l'approvazione automatica è attiva, UCM firma e restituisce il certificato
6. Se l'approvazione automatica è disattivata, un amministratore rivede e approva/rifiuta

### Chiavi del dispositivo
Il dispositivo firma il proprio PKCSReq con la propria chiave: RSA, ECDSA, Ed25519 o ML-DSA. Una firma ML-DSA viene verificata secondo la RFC 9882 (digest SHA-512, identificatore di algoritmo della chiave stessa, nessun parametro). Le firme Ed448 sono rifiutate, e anche quelle ML-DSA in modalità FIPS. La richiesta resta cifrata verso la CA firmataria RSA.

## URL SCEP

\`\`\`
https://your-server:8443/scep/pkiclient.exe            (configured CA)
https://your-server:8443/scep/<profile>/pkiclient.exe  (per-profile endpoint)
https://your-server:8443/cgi-bin/pkiclient.exe         (configured CA, legacy path)
http://your-server:8080/scep/pkiclient.exe             (with Serve on plain HTTP)
\`\`\`

I dispositivi necessitano dell'URL per iscriversi; \`/scep\` da solo è l'interfaccia web, non un endpoint SCEP. Usa un URL di profilo per indirizzare la CA, il modello e la challenge password di quel profilo.

### Cambio di CA (GetNextCACert)
GetNextCACert serve il successore della CA dell'endpoint, firmato dalla CA corrente: un'altra CA con lo stesso padre e lo stesso DN del soggetto, non revocata, non offline, con una chiave RSA in software, e che scade più tardi. Una CA che condivide solo il nome visualizzato non viene mai servita; senza un successore la risposta è 404.

## Approvazione/Rifiuto delle richieste

Per le richieste in attesa (approvazione automatica disattivata):
1. Rivedi i dettagli della richiesta (soggetto, ID transazione, stato, CSR)
2. Clicca **Approva** per firmare ed emettere il certificato
3. Oppure clicca **Rifiuta** con una motivazione

Una richiesta arrivata tramite un profilo viene emessa con il modello di quel profilo (validità, key usage), esattamente come farebbe l'approvazione automatica.

> ⚠ Le challenge password vengono trasmesse nella richiesta SCEP. Usa sempre HTTPS per l'endpoint SCEP.

## Integrazione dispositivi

### Cisco IOS
\`\`\`
crypto pki trustpoint UCM
  enrollment url https://your-server:8443/scep
  password <challenge-password>
\`\`\`

### JAMF
Configura il profilo SCEP con:
- URL server: \`https://your-server:8443/scep\`
- Challenge: la password da UCM

### Microsoft Intune
Intune non supporta una challenge password statica: emette una propria challenge cifrata per dispositivo che solo l'API di Intune può validare. Su un **profilo** SCEP (non l'endpoint globale), abilita **Convalida challenge SCEP di Microsoft Intune** e fornisci tenant ID, client ID e client secret di una registrazione app Entra:

1. In Microsoft Entra ID, registra un'app e concedile i permessi applicazione **Intune API → SCEP challenge validation** (\`scep_challenge_provider\`) e **Microsoft Graph → Application.Read.All**, entrambi con consenso amministratore
2. In **Registrazioni dell'app Intune**, aggiungi la registrazione app una sola volta (nome, tenant ID, client ID, client secret) e clicca **Verifica connessione** per confermare che UCM possa raggiungere Intune; poi selezionala nel selettore **Registrazione app** del profilo. I profili dello stesso tenant la condividono, quindi il secret si ruota in un solo punto
3. In Intune, punta l'URL server del profilo SCEP del dispositivo all'endpoint \`/scep/<segment>/pkiclient.exe\` di questo profilo

I profili con Intune abilitato devono avere l'**approvazione automatica** attiva: l'iscrizione Intune è un round trip sincrono di convalida e poi emissione, senza coda lato Intune per una revisione manuale.
`
  }
}
