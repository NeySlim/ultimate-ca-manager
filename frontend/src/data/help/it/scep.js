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
    ],
    tips: [
      'Usa challenge password uniche per CA per un miglior auditing di sicurezza',
      'L\'approvazione automatica è comoda ma rivedi le richieste manualmente in ambienti ad alta sicurezza',
      'Formato URL SCEP: https://your-server:port/scep',
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
https://your-server:8443/scep
\`\`\`

I dispositivi necessitano di questo URL più l'identificativo CA per iscriversi.

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

### Microsoft Intune / JAMF
Configura il profilo SCEP con:
- URL server: \`https://your-server:8443/scep\`
- Challenge: la password da UCM
`
  }
}
