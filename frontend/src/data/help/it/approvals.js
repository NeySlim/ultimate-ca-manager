export default {
  helpContent: {
    title: 'Richieste di approvazione',
    subtitle: 'Gestione del flusso di approvazione certificati',
    overview: 'Rivedi e gestisci le richieste di approvazione dei certificati. Quando una politica richiede l\'approvazione, l\'emissione del certificato viene sospesa finché il numero richiesto di approvatori non ha esaminato e approvato la richiesta.',
    sections: [
      {
        title: 'Ciclo di vita della richiesta',
        items: [
          { label: 'In attesa', text: 'In attesa di revisione — il certificato non può ancora essere emesso' },
          { label: 'Approvata', text: 'Tutte le approvazioni richieste sono state ricevute — il certificato può essere emesso' },
          { label: 'Rifiutata', text: 'Qualsiasi rifiuto blocca immediatamente la richiesta' },
          { label: 'Scaduta', text: 'Nessuna decisione entro sette giorni; chiusa come scaduta e mai conteggiata tra quelle in attesa' },
        ]
      },
      {
        title: 'Da dove arrivano le richieste',
        items: [
          { label: 'Modulo di emissione', text: 'Una richiesta di certificato corrispondente a una politica che richiede l\'approvazione' },
          { label: 'Firma CSR e firma massiva', text: 'La firma di una richiesta memorizzata, singola o da Operazioni, viene messa in coda allo stesso modo; l\'approvazione esegue la firma' },
          { label: 'Rinnovo', text: 'Anche il rinnovo di un certificato, singolo o massivo, viene messo in coda; un rinnovo che non potrebbe essere soddisfatto (revocato, chiave non detenuta dal server) viene rifiutato subito' },
          { label: 'Amministratori', text: 'Saltano la coda su ogni percorso, come nel modulo di emissione' },
        ]
      },
      {
        title: 'Richieste chiuse al posto tuo',
        items: [
          { label: 'Firmata o rinnovata direttamente', text: 'Una richiesta in coda il cui oggetto è stato nel frattempo firmato o rinnovato da un amministratore viene chiusa come approvata da quell\'azione e collegata al certificato' },
          { label: 'Eliminato o revocato', text: 'Una richiesta il cui oggetto è stato eliminato o revocato viene chiusa come rifiutata; una sospensione del certificato lascia la richiesta di rinnovo in attesa della rimozione della sospensione' },
          { label: 'Già soddisfatta', text: 'Approvare una richiesta già soddisfatta la chiude sul certificato esistente; approvare una di più richieste per lo stesso oggetto chiude le altre come approvate da te' },
          { label: 'Oggetto scomparso', text: 'Approvare una richiesta la cui richiesta memorizzata, certificato o CA non esiste più la chiude come rifiutata' },
          { label: 'Termine ultimo', text: 'Una richiesta attende sette giorni; oltre quel termine viene chiusa come scaduta, mai conteggiata tra quelle in attesa, e lo scheduler dei rinnovi riprende per il suo certificato' },
        ]
      },
    ],
    tips: [
      'Un singolo rifiuto blocca immediatamente l\'approvazione — questo è intenzionale per la sicurezza.',
      'Mentre un rinnovo attende l\'approvazione, lo scheduler lascia il certificato a quella decisione, purché possa arrivare prima della scadenza del certificato.',
      'I commenti di approvazione vengono registrati nella traccia di audit per la conformità.',
    ],
  },
  helpGuides: {
    title: 'Richieste di approvazione',
    content: `
## Panoramica

La pagina Approvazioni mostra tutte le richieste di certificato che richiedono l'approvazione manuale prima dell'emissione. I flussi di approvazione sono configurati nelle **Politiche** — quando una politica ha "Richiedi approvazione" abilitato, qualsiasi richiesta di certificato corrispondente crea una richiesta di approvazione qui.

## Ciclo di vita della richiesta

### In attesa
La richiesta è in attesa di revisione. Il certificato non può essere emesso finché il numero richiesto di approvatori non ha dato l'approvazione. Le richieste in attesa appaiono per prime per impostazione predefinita.

### Approvata
Tutte le approvazioni richieste sono state ricevute. Il certificato verrà emesso automaticamente una volta approvato.

### Rifiutata
Un singolo rifiuto blocca immediatamente la richiesta. Il certificato non verrà emesso. Un commento di rifiuto è obbligatorio per spiegare il motivo.

### Scaduta
La richiesta non è stata decisa entro sette giorni. Le richieste scadute devono essere ripresentate.

## Da dove arrivano le richieste
Oltre al modulo di emissione, una politica che richiede l'approvazione mette in coda anche:
- **Firma CSR** e **firma massiva** da Operazioni: l'approvazione esegue la firma
- **Rinnova** e **rinnovo massivo**: l'approvazione esegue il rinnovo; un rinnovo che non potrebbe essere soddisfatto (certificato revocato, chiave non detenuta dal server) viene rifiutato subito invece di essere messo in coda

Gli amministratori saltano la coda su ogni percorso.

## Richieste chiuse al posto tuo
- Una richiesta in coda il cui oggetto è stato nel frattempo **firmato o rinnovato direttamente** da un amministratore viene chiusa come approvata da quell'azione e collegata al certificato
- Una richiesta il cui oggetto è stato **eliminato o revocato** viene chiusa come rifiutata; una sospensione del certificato lascia la richiesta di rinnovo in attesa della rimozione della sospensione
- Approvare una richiesta **già soddisfatta** la chiude sul certificato esistente; approvare una di più richieste per lo stesso oggetto chiude le altre come approvate da te
- Approvare una richiesta la cui richiesta memorizzata, certificato o CA **non esiste più** la chiude come rifiutata

I webhook vengono informati di queste chiusure come per un rifiuto.

## Termine ultimo
Una richiesta attende **sette giorni** una decisione. Oltre quel termine viene chiusa come scaduta, non viene mai conteggiata tra quelle in attesa e lo scheduler dei rinnovi riprende per il suo certificato. Mentre un rinnovo attende l'approvazione, lo scheduler lascia il certificato a quella decisione, purché possa arrivare prima della scadenza del certificato.

## Approvazione di una richiesta

1. Clicca su una richiesta in attesa per visualizzarne i dettagli
2. Rivedi i dettagli del certificato, il richiedente e la politica associata
3. Clicca **Approva** e facoltativamente aggiungi un commento
4. L'approvazione viene registrata con il tuo nome utente e il timestamp

## Rifiuto di una richiesta

1. Clicca su una richiesta in attesa per visualizzarne i dettagli
2. Clicca **Rifiuta**
3. Inserisci un **motivo del rifiuto** (obbligatorio) — viene registrato per la conformità audit
4. La richiesta viene immediatamente bloccata

> ⚠ Un singolo rifiuto blocca l'intera richiesta. Questo è intenzionale — se un revisore identifica un problema, l'emissione non deve procedere.

## Cronologia delle approvazioni

Ogni richiesta mantiene una cronologia completa delle approvazioni che mostra:
- Chi ha approvato o rifiutato (nome utente)
- Quando l'azione è stata eseguita (timestamp)
- Commento fornito (se presente)

Questa cronologia è immutabile e fa parte della traccia di audit.

## Filtri

Usa la barra dei filtri per stato in alto per mostrare:
- **In attesa** — Richieste in attesa della tua revisione
- **Approvate** — Richieste approvate di recente
- **Rifiutate** — Richieste rifiutate con motivazioni
- **Totale** — Tutte le richieste indipendentemente dallo stato

## Permessi

- **read:approvals** — Visualizza le richieste di approvazione
- **write:approvals** — Approva o rifiuta le richieste

> 💡 Configura le notifiche email nelle politiche in modo che gli approvatori vengano avvisati quando arrivano nuove richieste.
`
  }
}
