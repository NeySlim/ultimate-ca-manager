export default {
  helpContent: {
    title: 'Integrazione Microsoft AD CS',
    subtitle: 'Firma certificati con Microsoft Certificate Authority',
    overview: 'Connetti UCM ai servizi certificati di Microsoft Active Directory (AD CS) per firmare i CSR con la tua infrastruttura PKI Windows e gestire l\'intero ciclo di vita dei certificati. Supporta autenticazione con certificato (mTLS), Kerberos e Basic, più un canale di amministrazione WinRM opzionale per revoca, CRL, inventario e gestione delle richieste in sospeso.',
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
          { label: 'Approvazione del responsabile', text: 'Alcuni template richiedono l\'approvazione del responsabile, UCM traccia la richiesta in sospeso' },
          { label: 'Richieste in sospeso', text: 'Una richiesta che la CA trattiene per il suo responsabile resta In sospeso in UCM, e la pagina non offre alcun controllo dello stato: una volta emessa sulla CA, importa il certificato, oppure lascia che la Sincronizzazione inventario sul canale di amministrazione WinRM importi i certificati che UCM non conosce ancora' },
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
      {
        title: 'Ciclo di vita: rinnovo e revoca',
        items: [
          { label: 'Rinnova', text: 'Il rinnovo di un certificato emesso da AD CS reinvia il suo CSR originale alla stessa connessione e allo stesso template, firma la CA emittente, non UCM.' },
          { label: 'Revoca', text: 'La revoca di un certificato emesso da AD CS è locale a UCM, a meno che il canale di amministrazione WinRM sia configurato, in tal caso viene propagata alla CA Windows.' },
          { label: 'Rinnovo in sospeso', text: 'Se la CA trattiene il rinnovo per l\'approvazione del responsabile, UCM lo traccia come qualsiasi altra richiesta in sospeso.' },
        ]
      },
      {
        title: 'Canale di amministrazione WinRM (opzionale)',
        items: [
          { label: 'Scopo', text: 'Esegue operazioni di gestione sulla CA Windows (revoca, annullamento revoca, pubblicazione CRL, inventario, approvazione/rifiuto) tramite PowerShell remoting + certutil, operazioni che l\'iscrizione web di AD CS non può fare.' },
          { label: 'Trasporto', text: 'NTLM o Kerberos su HTTP/HTTPS. Consigliato Kerberos + HTTPS; Kerberos riutilizza il keytab della connessione.' },
          { label: 'Credenziali', text: 'Riutilizza per impostazione predefinita quelle della connessione. Le connessioni mTLS devono impostare un account WinRM dedicato (ufficiale «Rilascia e gestisci certificati» con privilegi minimi).' },
          { label: 'Requisito', text: 'WinRM abilitato sulla CA e il pacchetto opzionale pywinrm installato. Le operazioni di gestione richiedono admin:system; la propagazione alla CA di una revoca o del rilascio di una sospensione segue il permesso write:certificates del certificato.' },
        ]
      },
      {
        title: 'Sincronizzazione revoche via CRL',
        items: [
          { label: 'Sincronizzazione unidirezionale', text: 'Recupera periodicamente la CRL della CA e contrassegna come revocati in UCM i certificati revocati sulla CA. Non annulla mai una revoca.' },
          { label: 'Origine della CRL', text: 'Un URL di CRL esplicito, oppure rilevato automaticamente dal punto di distribuzione CRL dei certificati emessi.' },
          { label: 'Verificata', text: 'La firma della CRL viene controllata rispetto al certificato della CA prima di applicare qualsiasi cosa.' },
        ]
      },
      {
        title: 'Inventario CA e pannello di controllo',
        items: [
          { label: 'Sincronizzazione inventario', text: 'Importa i certificati emessi direttamente sulla CA che UCM non conosce ancora (incrementale per id richiesta); la riconciliazione è disponibile tramite l\'API.' },
          { label: 'Richieste in sospeso', text: 'Elenca, approva (reinvio + importazione automatica) o rifiuta le richieste in attesa di approvazione del responsabile della CA.' },
          { label: 'Salute della CA', text: 'Stato del servizio CA, scadenza del certificato CA, prossimo aggiornamento della CRL e numero di richieste in sospeso a colpo d\'occhio.' },
        ]
      },
    ],
    tips: [
      'Testa prima la connessione per verificare l\'autenticazione e scoprire i template disponibili.',
      'Abilita EOBO selezionando la casella nel modale di firma: i campi si compilano automaticamente dai dati del CSR.',
      'L\'autenticazione con certificato client è raccomandata per la produzione: non richiede il join al dominio.',
      'Abilita il canale di amministrazione WinRM per propagare le revoche alla CA e gestire le richieste in sospeso da UCM.',
    ],
    warnings: [
      'Kerberos richiede che la macchina sia unita al dominio o un keytab configurato: non disponibile in Docker.',
      'EOBO richiede un certificato di agente di iscrizione configurato sul server AD CS.',
      'Senza il canale di amministrazione WinRM, la revoca di un certificato AD CS lo contrassegna come revocato solo in UCM: la CA Windows non viene notificata.',
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
4. Facoltativamente inserisci il **nome comune della CA** (se vuoto si usa l'hostname del server)
5. Seleziona il **metodo di autenticazione**
6. Inserisci le credenziali per il metodo scelto
7. Clicca **Testa connessione** per verificare
8. Imposta un **template predefinito** e clicca **Salva**

## Metodi di autenticazione

| Metodo | Requisiti | Ideale per |
|--------|-----------|----------|
| **Certificato client (mTLS)** | Certificato/chiave client PEM dalla CA | Produzione: nessun join al dominio necessario |
| **Basic Auth** | Nome utente + password, HTTPS | Configurazioni semplici: abilita basic auth in IIS certsrv |
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
UCM salva la richiesta come **In sospeso** e traccia l'ID della richiesta MS CA. La pagina non offre un controllo dello stato per essa: una volta emessa sulla CA Windows, importa il certificato, oppure lascia che la **Sincronizzazione inventario** sul canale di amministrazione WinRM importi i certificati che UCM non conosce ancora.

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
   - **DN iscritto**: dal soggetto del CSR (es. CN=John Doe,OU=Users,DC=corp,DC=local)
   - **UPN iscritto**: dall'email SAN del CSR (es. john.doe@corp.local)
4. Modifica i valori se necessario
5. Clicca **Firma**

UCM passa questi come attributi della richiesta ADCS:
- EnrolleeObjectName:<DN>: identifica l'utente di destinazione in AD
- EnrolleePrincipalName:<UPN>: il nome di accesso dell'utente

### EOBO vs iscrizione diretta

| Caratteristica | Iscrizione diretta | EOBO |
|---------|-------------------|------|
| Chi firma | L'utente stesso | Agente di iscrizione per conto di |
| Chiave privata | Macchina dell'utente | Può essere su UCM (modello CSR) |
| Permessi template | Iscrizione standard | Richiede diritti di agente di iscrizione |
| Caso d'uso | Self-service | Gestione PKI centralizzata |

## Ciclo di vita dei certificati

### Rinnovare un certificato AD CS
Il rinnovo **non** rifirma localmente (la chiave emittente risiede sulla CA Windows). UCM reinvia il CSR originale del certificato: stessa chiave, soggetto e SAN, alla connessione e al template che lo hanno emesso, e aggiorna il certificato in loco. Se la CA trattiene il rinnovo per l'approvazione del responsabile, viene tracciato come richiesta in sospeso.

### Revocare un certificato AD CS
L'iscrizione web di AD CS non ha un endpoint di revoca. La revoca di un certificato emesso da AD CS:
- **Senza il canale di amministrazione WinRM**: lo contrassegna come revocato solo in UCM; la CA Windows non viene notificata. Revocalo anche sulla CA.
- **Con il canale di amministrazione WinRM**: UCM propaga la revoca alla CA Windows (certutil -revoke + pubblicazione della CRL). La rimozione di un certificateHold propaga anche l'annullamento della revoca.

## Canale di amministrazione WinRM (opzionale)

Il canale di amministrazione consente a UCM di eseguire sulla CA Windows operazioni di gestione che l'iscrizione web non può fare: revoca/annullamento revoca, pubblicazione CRL, inventario e approvazione/rifiuto delle richieste in sospeso. Usa PowerShell remoting + certutil.

### Requisiti
- **WinRM abilitato** sulla CA (Enable-PSRemoting; consigliato listener HTTPS sulla 5986)
- Il pacchetto opzionale **pywinrm** installato in UCM (pip install pywinrm)
- Un account autorizzato a **gestire i certificati** sulla CA («Issue and Manage Certificates»)

### Configurazione
1. Modifica la connessione e abilita il **canale di amministrazione WinRM**
2. Imposta l'host (per impostazione predefinita il server della connessione), la porta e il trasporto
3. **Trasporto**: Kerberos (consigliato, riutilizza il keytab della connessione) o NTLM, su HTTP o HTTPS
4. **Credenziali**: lascia vuoto per riutilizzare quelle della connessione (Basic/Kerberos). Le connessioni mTLS non hanno credenziali WinRM riutilizzabili, imposta un account dedicato
5. Clicca **Testa canale di amministrazione**

| Modalità di autenticazione di iscrizione | Riutilizza le credenziali per WinRM? |
|-------------------------------------------|---------------------------------------|
| Kerberos (keytab) | Sì: stesso principal/keytab |
| Basic (utente/password) | Sì: password verso NTLM/Kerberos |
| Certificato (mTLS) | No: imposta un account WinRM dedicato |

## Sincronizzazione revoche via CRL

Abilita **Sincronizza le revoche dalla CRL della CA** sulla connessione affinché UCM recuperi periodicamente la CRL della CA e contrassegni come revocati in UCM i certificati revocati sulla CA. È strettamente unidirezionale (dalla CA a UCM) e non annulla mai la revoca di un certificato revocato in UCM. L'URL della CRL proviene dalla connessione o viene rilevato automaticamente dal punto di distribuzione CRL dei certificati emessi, e la sua firma viene verificata rispetto al certificato della CA prima di applicare qualsiasi cosa. Viene eseguita ogni ora, più un'azione **Sincronizza CRL ora**.

## Sincronizzazione inventario CA

Abilita **Importa i certificati emessi direttamente sulla CA** per portare nello store di UCM i certificati emessi al di fuori di UCM (strumenti nativi, autoenrollment, o precedenti a UCM), in modo che UCM tracci l'intero ciclo di vita. Legge il database della CA con certutil -view, importa i certificati che UCM non ha ancora (deduplicati per numero di serie) ed è incrementale per id richiesta (con opzione di riscansione completa). Una vista di **riconciliazione** elenca i certificati presenti sulla CA ma non in UCM, e viceversa. Viene eseguita ogni 6 ore, più un'azione **Importa dalla CA ora**. Richiede il canale di amministrazione WinRM.

## Pannello di controllo CA

Il pannello di controllo (aperto dalla connessione, richiede il canale di amministrazione) gestisce le richieste in attesa di approvazione del responsabile della CA e mostra la salute della CA:
- **Richieste in sospeso**: elenca, **Approva** (certutil -resubmit; il certificato emesso viene importato automaticamente) o **Rifiuta** (certutil -deny)
- **Salute**: stato del servizio CA, scadenza del certificato CA, prossimo aggiornamento della CRL e numero di richieste in sospeso

## Risoluzione dei problemi

| Problema | Soluzione |
|-------|----------|
| Test connessione fallito | Verifica hostname, porta 443 e che certsrv sia accessibile |
| Nessun template trovato | Verifica che l'account UCM abbia i permessi di iscrizione sulla CA |
| EOBO negato | Verifica il certificato di agente di iscrizione e i permessi del template |
| Richiesta bloccata in sospeso | Approvala dal pannello di controllo CA, oppure sulla console della CA Windows e poi aggiorna lo stato in UCM |
| Test del canale di amministrazione fallito | Verifica che WinRM sia abilitato sulla CA, la porta/il trasporto e che pywinrm sia installato |
| Revoca assente sulla CA | Abilita il canale di amministrazione WinRM: senza di esso, la revoca è locale a UCM |
| Sospeso non rilevato (CA non in inglese) | Corretto nella v2.192. UCM ora riconosce le pagine di attesa AD CS localizzate |

> 💡 Usa il pulsante **Testa connessione** per verificare l'autenticazione e scoprire i template disponibili prima della firma. Abilita il **canale di amministrazione WinRM** per gestire revoca, CRL, inventario e richieste in sospeso direttamente da UCM.
`
  }
}
