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
          { label: 'Configurazione', text: 'Impostazioni del server SCEP: selezione CA, identificativo CA, approvazione automatica' },
          { label: 'Challenge Password', text: 'Gestisci le challenge password per CA per l\'iscrizione dei dispositivi' },
          { label: 'Informazioni', text: 'URL degli endpoint SCEP e istruzioni di integrazione' },
          { label: 'Profili', text: 'Endpoint di enrollment denominati, ciascuno con URL, CA, modello e challenge propri' },
        ]
      },
      {
        title: 'Configurazione',
        items: [
          { label: 'CA firmataria', text: 'Seleziona quale CA firma i certificati iscritti tramite SCEP' },
          { label: 'Approvazione automatica', text: 'Approva automaticamente le richieste con challenge password valide' },
          { label: 'Challenge Password', text: 'Segreto condiviso che i dispositivi usano per autenticare l\'iscrizione' },
        ]
      },
      {
        title: 'Profili',
        items: [
          { label: 'Segmento URL', text: 'Ogni profilo è servito su /scep/<segment>/pkiclient.exe — punta ogni flotta di dispositivi o profilo MDM al proprio URL' },
          { label: 'Modello di certificato', text: 'Quando un modello è associato, i suoi KU/EKU e la validità governano ogni certificato emesso tramite il profilo' },
          { label: 'Challenge per profilo', text: 'Ogni profilo ha la propria password di challenge, memorizzata cifrata, con la stessa finestra di scadenza della challenge globale' },
          { label: 'Endpoint predefinito', text: 'L\'endpoint /scep/pkiclient.exe senza segmento continua a servire la configurazione globale' },
          { label: 'Validazione Microsoft Intune', text: 'Un profilo può validarsi contro la challenge SCEP propria di Intune per dispositivo invece di una password statica — richiede una registrazione app Entra (permessi SCEP challenge validation + Application.Read.All) e l\'approvazione automatica attiva' },
        ]
      },
    ],
    tips: [
      'Usa challenge password uniche per CA per un miglior auditing di sicurezza',
      'L\'approvazione automatica è comoda ma rivedi le richieste manualmente in ambienti ad alta sicurezza',
      'Formato URL SCEP: https://your-server:port/scep',
      'I profili Intune richiedono l\'approvazione automatica attiva — l\'iscrizione Intune è un round trip sincrono di convalida e poi emissione, senza coda di approvazione lato Intune',
    ],
    warnings: [
      'Le challenge password vengono trasmesse nella richiesta SCEP — usa HTTPS per la sicurezza del trasporto',
    ],
  },
  helpGuides: {
    title: 'Server SCEP',
    content: `
## Panoramica

Il Simple Certificate Enrollment Protocol (SCEP) consente ai dispositivi di rete — router, switch, firewall, endpoint gestiti da MDM — di richiedere e ottenere automaticamente certificati.

## Schede

### Richieste
Visualizza tutte le richieste di iscrizione SCEP:
- **In attesa** — In attesa di approvazione manuale (se l'approvazione automatica è disattivata)
- **Approvate** — Emesse con successo
- **Rifiutate** — Negate da un amministratore

### Configurazione
Configura il server SCEP:
- **Abilita/Disabilita** — Attiva/disattiva il servizio SCEP
- **CA firmataria** — Seleziona quale CA firma i certificati iscritti tramite SCEP
- **Identificativo CA** — L'identificativo che i dispositivi usano per localizzare la CA corretta
- **Approvazione automatica** — Approva automaticamente le richieste con challenge password valide

### Profili
Endpoint di enrollment denominati, ciascuno servito su un URL proprio:

\`\`\`
https://your-server:8443/scep/<profile>/pkiclient.exe
\`\`\`

Ogni profilo è associato a:
- **La propria CA** — flotte di dispositivi diverse possono iscriversi presso CA diverse
- **Un modello di certificato opzionale** — quando associato, key usage, extended key usage e validità del modello governano ogni certificato emesso tramite il profilo
- **Una challenge password per profilo** — memorizzata cifrata, con la stessa finestra di scadenza della challenge globale
- **Una politica di approvazione** — approvazione automatica o revisione manuale per profilo

Punta ogni flotta di dispositivi, profilo MDM o tenant al proprio URL di profilo. L'endpoint senza segmento \`/scep/pkiclient.exe\` continua a servire la configurazione globale senza modifiche.

### Challenge Password
Gestisci le challenge password per CA. I dispositivi devono includere una challenge password valida nella loro richiesta di iscrizione per autenticarsi.

- **Visualizza password** — Mostra la challenge attuale per una CA
- **Rigenera** — Crea una nuova challenge password (invalida quella precedente)

### Informazioni
Mostra l'URL dell'endpoint SCEP e le istruzioni di integrazione.

## Flusso di iscrizione SCEP

1. Il dispositivo invia una richiesta **GetCACert** per ottenere il certificato CA
2. Il dispositivo genera una coppia di chiavi e crea un CSR
3. Il dispositivo incapsula il CSR con la **challenge password** e invia un **PKCSReq**
4. UCM valida la challenge password
5. Se l'approvazione automatica è attiva, UCM firma e restituisce il certificato
6. Se l'approvazione automatica è disattivata, un amministratore rivede e approva/rifiuta

## URL SCEP

\`\`\`
https://your-server:8443/scep                          (global endpoint)
https://your-server:8443/scep/<profile>/pkiclient.exe  (per-profile endpoint)
\`\`\`

I dispositivi necessitano dell'URL più l'identificativo CA per iscriversi. Usa un URL di profilo per indirizzare la CA, il modello e la challenge password di quel profilo.

## Approvazione/Rifiuto delle richieste

Per le richieste in attesa (approvazione automatica disattivata):
1. Rivedi i dettagli della richiesta (soggetto, tipo di chiave, challenge)
2. Clicca **Approva** per firmare ed emettere il certificato
3. Oppure clicca **Rifiuta** con una motivazione

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
Intune non supporta una challenge password statica — emette una propria challenge cifrata per dispositivo che solo l'API di Intune può validare. Su un **profilo** SCEP (non l'endpoint globale), abilita **Convalida challenge SCEP di Microsoft Intune** e fornisci tenant ID, client ID e client secret di una registrazione app Entra:

1. In Microsoft Entra ID, registra un'app e concedile i permessi applicazione **Intune API → SCEP challenge validation** (\`scep_challenge_provider\`) e **Microsoft Graph → Application.Read.All**, entrambi con consenso amministratore
2. Inserisci tenant ID, client ID e client secret nel profilo, poi clicca **Verifica connessione** per confermare che UCM possa raggiungere Intune prima di salvare
3. In Intune, punta l'URL server del profilo SCEP del dispositivo all'endpoint \`/scep/<segment>/pkiclient.exe\` di questo profilo

I profili con Intune abilitato devono avere l'**approvazione automatica** attiva — l'iscrizione Intune è un round trip sincrono di convalida e poi emissione, senza coda lato Intune per una revisione manuale.
`
  }
}
