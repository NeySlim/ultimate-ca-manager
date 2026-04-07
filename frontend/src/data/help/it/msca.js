export default {
  helpContent: {
    title: 'Integrazione Microsoft AD CS',
    subtitle: 'Firma certificati con Microsoft Certificate Authority',
    overview: 'Connetti UCM ai servizi certificati di Microsoft Active Directory (AD CS) per firmare i CSR utilizzando la tua infrastruttura PKI Windows. Supporta i metodi di autenticazione certificato (mTLS), Kerberos e Basic.',
    sections: [
      {
        title: 'Metodi di autenticazione',
        items: [
          { label: 'Certificato client (mTLS)', text: 'Il più sicuro. Genera un certificato client sulla tua MS CA, esporta come PFX, carica certificato e chiave PEM.' },
          { label: 'Basic Auth', text: 'Nome utente/password tramite HTTPS. Funziona senza join al dominio. Abilita basic auth in IIS certsrv.' },
          { label: 'Kerberos', text: 'Richiede il pacchetto requests-kerberos e una macchina unita al dominio o keytab configurato.' },
        ]
      },
      {
        title: 'Firma dei CSR',
        items: [
          { label: 'Selezione template', text: 'Scegli tra i template di certificato disponibili sulla MS CA' },
          { label: 'Approvazione automatica', text: 'I template con autoenroll restituiscono il certificato immediatamente' },
          { label: 'Approvazione del responsabile', text: 'Alcuni template richiedono l\'approvazione del responsabile — UCM traccia la richiesta in sospeso' },
          { label: 'Polling dello stato', text: 'Controlla lo stato della richiesta in sospeso dal pannello dei dettagli del CSR' },
        ]
      },
      {
        title: 'Iscrizione per conto di (EOBO)',
        items: [
          { label: 'Panoramica', text: 'Invia CSR per conto di un altro utente utilizzando certificati di agente di iscrizione' },
          { label: 'DN iscritto', text: 'Distinguished Name dell\'utente di destinazione (compilato automaticamente dal soggetto del CSR)' },
          { label: 'UPN iscritto', text: 'User Principal Name dell\'utente di destinazione (compilato automaticamente dall\'email SAN del CSR)' },
          { label: 'Requisiti', text: 'Il template CA deve consentire l\'iscrizione per conto di altri. L\'account di servizio UCM necessita di un certificato di agente di iscrizione.' },
        ]
      },
    ],
    tips: [
      'Testa prima la connessione per verificare l\'autenticazione e scoprire i template disponibili.',
      'Abilita EOBO selezionando la casella nel modale di firma — i campi si compilano automaticamente dai dati del CSR.',
      'L\'autenticazione con certificato client è raccomandata per la produzione — non richiede il join al dominio.',
    ],
    warnings: [
      'Kerberos richiede che la macchina sia unita al dominio o un keytab configurato — non disponibile in Docker.',
      'EOBO richiede un certificato di agente di iscrizione configurato sul server AD CS.',
    ],
  },
  helpGuides: {
    title: 'Integrazione Microsoft AD CS',
    content: `
## Panoramica

UCM si integra con i servizi certificati di Microsoft Active Directory (AD CS) per firmare i CSR utilizzando la tua infrastruttura PKI Windows esistente. Questo collega la tua CA interna con la gestione del ciclo di vita dei certificati di UCM.

## Configurazione di una connessione

1. Vai su **Impostazioni → Microsoft CA**
2. Clicca **Aggiungi connessione**
3. Inserisci il **nome della connessione** e l'**hostname del server CA**
4. Facoltativamente inserisci il **nome comune della CA** (rilevato automaticamente se vuoto)
5. Seleziona il **metodo di autenticazione**
6. Inserisci le credenziali per il metodo scelto
7. Clicca **Testa connessione** per verificare
8. Imposta un **template predefinito** e clicca **Salva**

## Metodi di autenticazione

| Metodo | Requisiti | Ideale per |
|--------|-----------|----------|
| **Certificato client (mTLS)** | Certificato/chiave client PEM dalla CA | Produzione — nessun join al dominio necessario |
| **Basic Auth** | Nome utente + password, HTTPS | Configurazioni semplici — abilita basic auth in IIS certsrv |
| **Kerberos** | Macchina unita al dominio + keytab | Ambienti Active Directory aziendali |

### Configurazione certificato client (raccomandato)

1. Sulla tua CA Windows, crea un certificato per l'account di servizio UCM
2. Esporta come PFX, poi converti in PEM:
   \`\`\`bash
   openssl pkcs12 -in client.pfx -out client-cert.pem -clcerts -nokeys
   openssl pkcs12 -in client.pfx -out client-key.pem -nocerts -nodes
   \`\`\`
3. Incolla il contenuto PEM del certificato e della chiave nel modulo di connessione UCM

## Firma dei CSR tramite Microsoft CA

1. Vai su **CSR → In attesa**
2. Seleziona un CSR e clicca **Firma**
3. Passa alla scheda **Microsoft CA**
4. Seleziona la connessione e il template del certificato
5. Clicca **Firma**

### Template con approvazione automatica
Il certificato viene restituito immediatamente e importato in UCM.

### Template con approvazione del responsabile
UCM salva la richiesta come **In sospeso** e traccia l'ID della richiesta MS CA. Una volta approvata sulla CA Windows, controlla lo stato dal pannello dei dettagli del CSR per importare il certificato.

## Iscrizione per conto di (EOBO)

L'EOBO consente a un agente di iscrizione di richiedere certificati per conto di altri utenti. Questo è comune negli ambienti aziendali dove un amministratore PKI gestisce i certificati per gli utenti finali.

### Prerequisiti

- L'account di servizio UCM necessita di un **certificato di agente di iscrizione** emesso dalla CA
- Il template del certificato deve avere il permesso **"Iscrizione per conto di altri utenti"** abilitato
- La scheda sicurezza del template deve concedere all'agente di iscrizione il diritto di iscrivere

### Utilizzo di EOBO in UCM

1. Nel modale di firma, seleziona la connessione Microsoft CA e il template
2. Seleziona la casella **Iscrizione per conto di (EOBO)**
3. I campi si compilano automaticamente dal CSR:
   - **DN iscritto** — dal soggetto del CSR (es. CN=John Doe,OU=Users,DC=corp,DC=local)
   - **UPN iscritto** — dall'email SAN del CSR (es. john.doe@corp.local)
4. Modifica i valori se necessario
5. Clicca **Firma**

UCM passa questi come attributi della richiesta ADCS:
- EnrolleeObjectName:<DN> — identifica l'utente di destinazione in AD
- EnrolleePrincipalName:<UPN> — il nome di accesso dell'utente

### EOBO vs iscrizione diretta

| Caratteristica | Iscrizione diretta | EOBO |
|---------|-------------------|------|
| Chi firma | L'utente stesso | Agente di iscrizione per conto di |
| Chiave privata | Macchina dell'utente | Può essere su UCM (modello CSR) |
| Permessi template | Iscrizione standard | Richiede diritti di agente di iscrizione |
| Caso d'uso | Self-service | Gestione PKI centralizzata |

## Risoluzione dei problemi

| Problema | Soluzione |
|-------|----------|
| Test connessione fallito | Verifica hostname, porta 443 e che certsrv sia accessibile |
| Nessun template trovato | Verifica che l'account UCM abbia i permessi di iscrizione sulla CA |
| EOBO negato | Verifica il certificato di agente di iscrizione e i permessi del template |
| Richiesta bloccata in sospeso | Approva sulla console della CA Windows, poi aggiorna lo stato in UCM |

> 💡 Usa il pulsante **Testa connessione** per verificare l'autenticazione e scoprire i template disponibili prima della firma.
`
  }
}
