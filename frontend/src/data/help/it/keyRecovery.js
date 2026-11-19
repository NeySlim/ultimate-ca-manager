export default {
  helpContent: {
    title: 'Recupero delle chiavi',
    subtitle: 'Recuperare le chiavi private archiviate sotto doppio controllo',
    overview: 'Il recupero delle chiavi restituisce la chiave privata archiviata di un certificato emesso in precedenza tramite un flusso di lavoro soggetto ad approvazione e completamente tracciato. Esiste per le chiavi che non sono state esportate al momento dell\'emissione (il preset non lo consentiva, oppure l\'esportazione è stata saltata) e che servono in un secondo momento, con una traccia di approvazione associata al recupero.',
    sections: [
      {
        title: 'Flusso di lavoro',
        items: [
          { label: 'Richiesta', text: 'Un utente richiede il recupero della chiave archiviata di un certificato specifico, indicando un motivo' },
          { label: 'Approvazione (quattro occhi)', text: 'Un amministratore esamina e approva; con il doppio controllo attivo (predefinito), il richiedente non può approvare la propria richiesta' },
          { label: 'Download', text: 'Una volta approvata, la chiave viene rilasciata come pacchetto PKCS#12 protetto da password' },
          { label: 'Certificato sostituito (v2.251)', text: 'Approvazione e recupero rispondono 410 a meno che il certificato della richiesta sia ancora quello su cui è stata aperta. Un ripristino con sostituzione annulla le richieste aperte sui certificati che rimuove' },
        ]
      },
      {
        title: 'Requisiti',
        items: [
          { label: 'Chiave archiviata', text: 'La chiave privata del certificato deve essere memorizzata nel database, il recupero non può ricostruire una chiave che non è mai stata archiviata' },
          { label: 'Doppio controllo', text: 'Attivo per impostazione predefinita: richiesta e approvazione sono azioni separate eseguite da persone diverse. Richieste, approvazioni e download sono scritti nel registro di audit; un\'approvazione o un download rifiutati no' },
        ]
      },
    ],
    tips: [
      'Il recupero delle chiavi è pensato per le chiavi che non sono state esportate al momento dell\'emissione del certificato; non sostituisce la limitazione dell\'esportazione delle chiavi in fase di emissione.',
      'Ogni richiesta, approvazione e download viene registrato nel registro di audit; i rifiuti no.',
    ],
    warnings: [
      'Un certificato la cui chiave privata non è mai stata archiviata non può essere recuperato: non c\'è nulla da rilasciare.',
    ],
  },
  helpGuides: {
    title: 'Recupero delle chiavi',
    content: `
## Panoramica

Il recupero delle chiavi restituisce la **chiave privata archiviata** di un certificato emesso in precedenza tramite un flusso di lavoro soggetto ad approvazione e completamente tracciato. È pensato per le chiavi che **non sono state esportate al momento dell'emissione**: il preset non consentiva l'esportazione, oppure è stata semplicemente saltata, e che servono in un secondo momento, con una traccia di approvazione associata al recupero.

Il recupero funziona solo se la chiave privata è stata archiviata (memorizzata nel database) al momento dell'emissione. Non può ricostruire una chiave che non è mai stata conservata.

## Flusso di lavoro

### 1. Richiesta
Un utente apre una richiesta di recupero per un certificato specifico e indica un motivo. La richiesta viene registrata ed entra nello stato in attesa.

### 2. Approvazione (quattro occhi)
Un amministratore esamina la richiesta e la approva. Con il doppio controllo attivo (predefinito), il richiedente **non può approvare la propria richiesta**: richiesta e approvazione sono azioni separate eseguite da persone diverse.

### 3. Download
Una volta approvata, la chiave archiviata viene rilasciata come pacchetto **PKCS#12 protetto da password**. Il download viene registrato nel registro di audit.

## Requisiti

- **Chiave archiviata**: la chiave privata del certificato deve essere presente nel database. I certificati la cui chiave non è mai stata archiviata non possono essere recuperati.
- **Doppio controllo**: attivo per impostazione predefinita, la richiesta e l'approvazione sono passaggi distinti eseguiti da utenti diversi. Un amministratore può disattivarlo, e allora può approvare la propria richiesta.

## Permessi

- **read:key_recovery**: Consultare le richieste
- **write:key_recovery**: Richiedere un recupero
- **admin**: Approvare o rifiutare una richiesta di recupero in attesa
- **read:private_keys**: Richiesto per l'esportazione *diretta* della chiave privata dalla pagina Certificati (bypassando questo flusso). Tra i ruoli integrati solo Admin lo possiede; un ruolo personalizzato può concederlo

## Cos'è (e cosa non è)

Il recupero delle chiavi aggiunge una **traccia di approvazione** al recupero di una chiave archiviata dopo l'emissione. L'esportazione diretta della chiave privata è protetta dal permesso **read:private_keys**: i ruoli che non lo hanno (compreso il ruolo Operator integrato) devono passare dal recupero delle chiavi. Un amministratore, o un ruolo personalizzato con quel permesso, esporta la chiave direttamente, senza approvazione, quindi l'approvazione a quattro occhi vincola solo i ruoli che non lo hanno.

> 💡 Ogni richiesta, approvazione e download viene registrato nel registro di audit ai fini di conformità.
`
  }
}
