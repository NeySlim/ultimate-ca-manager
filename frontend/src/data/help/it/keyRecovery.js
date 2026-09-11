export default {
  helpContent: {
    title: 'Recupero delle chiavi',
    subtitle: 'Recuperare le chiavi private archiviate sotto doppio controllo',
    overview: 'Il recupero delle chiavi restituisce la chiave privata archiviata di un certificato emesso in precedenza tramite un flusso di lavoro soggetto ad approvazione e completamente tracciato. Esiste per le chiavi che non sono state esportate al momento dell\'emissione (il preset non lo consentiva, oppure l\'esportazione è stata saltata) e che servono in un secondo momento — con una traccia di approvazione associata al recupero.',
    sections: [
      {
        title: 'Flusso di lavoro',
        items: [
          { label: 'Richiesta', text: 'Un utente richiede il recupero della chiave archiviata di un certificato specifico, indicando un motivo' },
          { label: 'Approvazione (quattro occhi)', text: 'Un secondo operatore autorizzato esamina e approva — il richiedente non può approvare la propria richiesta' },
          { label: 'Download', text: 'Una volta approvata, la chiave viene rilasciata come pacchetto PKCS#12 protetto da password' },
        ]
      },
      {
        title: 'Requisiti',
        items: [
          { label: 'Chiave archiviata', text: 'La chiave privata del certificato deve essere memorizzata nel database — il recupero non può ricostruire una chiave che non è mai stata archiviata' },
          { label: 'Doppio controllo', text: 'Richiesta e approvazione sono azioni separate eseguite da persone diverse; ogni passaggio viene registrato nel registro di audit' },
        ]
      },
    ],
    tips: [
      'Il recupero delle chiavi è pensato per le chiavi che non sono state esportate al momento dell\'emissione del certificato; non sostituisce la limitazione dell\'esportazione delle chiavi in fase di emissione.',
      'Ogni richiesta, approvazione e download viene registrato nel registro di audit ai fini di conformità.',
    ],
    warnings: [
      'Un certificato la cui chiave privata non è mai stata archiviata non può essere recuperato — non c\'è nulla da rilasciare.',
    ],
  },
  helpGuides: {
    title: 'Recupero delle chiavi',
    content: `
## Panoramica

Il recupero delle chiavi restituisce la **chiave privata archiviata** di un certificato emesso in precedenza tramite un flusso di lavoro soggetto ad approvazione e completamente tracciato. È pensato per le chiavi che **non sono state esportate al momento dell'emissione** — il preset non consentiva l'esportazione, oppure è stata semplicemente saltata — e che servono in un secondo momento, con una traccia di approvazione associata al recupero.

Il recupero funziona solo se la chiave privata è stata archiviata (memorizzata nel database) al momento dell'emissione. Non può ricostruire una chiave che non è mai stata conservata.

## Flusso di lavoro

### 1. Richiesta
Un utente apre una richiesta di recupero per un certificato specifico e indica un motivo. La richiesta viene registrata ed entra nello stato in attesa.

### 2. Approvazione (quattro occhi)
Un secondo operatore autorizzato esamina la richiesta e la approva. Il richiedente **non può approvare la propria richiesta** — richiesta e approvazione sono azioni separate eseguite da persone diverse (doppio controllo).

### 3. Download
Una volta approvata, la chiave archiviata viene rilasciata come pacchetto **PKCS#12 protetto da password**. Il download viene registrato nel registro di audit.

## Requisiti

- **Chiave archiviata** — la chiave privata del certificato deve essere presente nel database. I certificati la cui chiave non è mai stata archiviata non possono essere recuperati.
- **Doppio controllo** — la richiesta e l'approvazione sono passaggi distinti eseguiti da utenti diversi.

## Permessi

- **read:key_recovery** — Richiedere un recupero e consultare le richieste
- **admin** — Approvare o rifiutare una richiesta di recupero in attesa
- **read:private_keys** — Permesso riservato agli admin, richiesto per l'esportazione *diretta* della chiave privata dalla pagina Certificati (bypassando questo flusso)

## Cos'è (e cosa non è)

Il recupero delle chiavi aggiunge una **traccia di approvazione** al recupero di una chiave archiviata dopo l'emissione. Non sostituisce la limitazione dell'esportazione delle chiavi private nei preset — se un ruolo può già esportare le chiavi direttamente, si tratta di un percorso di accesso separato da controllare a sé stante.

> 💡 Ogni richiesta, approvazione e download viene registrato nel registro di audit ai fini di conformità.
`
  }
}
