export default {
  helpContent: {
    title: 'Overview',
    subtitle: 'What needs action, and the state of the PKI',
    overview: 'Six independent cards over the live data of your PKI. Each card loads on its own and shows its own loading, empty, error or missing-permission state. Every counter that has a list opens the certificate list filtered to exactly the certificates it counts.',
    sections: [
      {
        title: 'Cards',
        items: [
          { label: 'To handle', text: 'The six most urgent items, critical first, each linking to its record; a folded tier gives the total per kind, and the four renewal kinds open the certificate list' },
          { label: 'Automation health', text: 'Per protocol (ACME, SCEP, EST) the daily successes and failures, and the scheduler state' },
          { label: 'Hierarchy', text: 'The authorities as a tree under their parent, with CRL and OCSP state, an offline or cross-signed mark, and the certificates each issued over 7 days; each authority opens its page' },
          { label: 'Expiry horizon', text: 'The expiring and expired counters, each opening its list, and the five certificates that expire next' },
          { label: 'Compliance', text: 'Live certificates by key algorithm and weakness (RSA below 3072 bits, weak signature hash, server certificates over 398 days, incomplete chain, no private key); each counter opens the matching list' },
          { label: 'Latest operations', text: 'The five most recent operations; with the audit permission, a link opens the whole trail' },
        ]
      },
    ],
    tips: [
      'Pick the Operator, Manager or All cards preset in the header to choose which cards are shown',
      'The layout is saved with your account and follows you across browsers',
      'On the certificate list, filters coming from the overview appear as chips; remove one with its x',
    ],
  },
  helpGuides: {
    title: 'Dashboard',
    content: `
## Panoramica

La Dashboard è il tuo hub di monitoraggio centrale. Mostra metriche in tempo reale, grafici e avvisi sull'intera infrastruttura PKI attraverso widget personalizzabili.

## Widget

### Scheda statistiche
Mostra questi contatori:
- **Certificati**: tutti i certificati, scaduti e revocati inclusi
- **CA**: Autorità di certificazione Root e Intermedie
- **CSR**: Richieste di firma certificato in attesa di firma
- **ACME**: account ACME registrati
- **Certificati SSH**: mostrato quando esiste una CA SSH

### Attività certificati
Un grafico ad area dei certificati emessi, revocati e scaduti per giorno nel periodo scelto. Passa il mouse sui punti dati per vedere i conteggi esatti.

### Distribuzione stati
Grafico a torta che mostra la ripartizione degli stati dei certificati:
- **Valido**: Entro il periodo di validità e non revocato
- **In scadenza**: Scade entro 30 giorni
- **Scaduto**: Oltre la data "Non dopo"
- **Revocato**: Esplicitamente revocato

### Prossima scadenza
Elenca i sei certificati validi che scadono per primi, qualunque sia la data. Clicca su un certificato per visualizzarne i dettagli.

### Stato del sistema
Mostra lo stato dei servizi UCM:
- Server ACME (abilitato/disabilitato)
- Server SCEP
- Protocollo EST (abilitato/disabilitato, CA assegnata)
- Rigenerazione automatica CRL con conteggio CDP
- Risponditore OCSP
- TSA, SMTP e webhook
- Stato del rinnovo automatico

Il pannello Salute del sistema mostra anche la connessione WebSocket, il database, l'API e l'ora dell'ultimo aggiornamento.

### Attività recente
Un feed in tempo reale delle ultime operazioni: emissione certificati, revoche, importazioni, accessi utente. Si aggiorna in tempo reale tramite WebSocket.

### Autorità di certificazione
Visualizzazione rapida delle ultime CA, ciascuna contrassegnata Root o Sub.

### Scadenza trust store
Certificati attendibili che scadono per primi.

### Account ACME
Elenca gli account client ACME registrati e il conteggio dei loro ordini.

## Personalizzazione

### Riorganizzazione dei widget
Clicca **Modifica layout** nell'intestazione della pagina, poi trascina qualsiasi widget dalla sua intestazione per riposizionarlo. Il layout utilizza una griglia responsiva che si adatta alle dimensioni dello schermo.

### Mostrare/nascondere widget
Clicca **Personalizza** (icona cursori) nell'intestazione della pagina, poi l'occhio accanto a un widget per attivarne/disattivarne la visibilità. I widget nascosti vengono ricordati tra le sessioni.

### Persistenza del layout
Il layout è salvato nel browser, non nel tuo account: ogni account che accede dallo stesso profilo del browser lo condivide, e un altro browser parte dal layout predefinito.

## Aggiornamenti in tempo reale
La dashboard riceve aggiornamenti in tempo reale tramite WebSocket. Non è necessario aggiornare manualmente: nuovi certificati, cambi di stato e voci di attività appaiono automaticamente.

> 💡 Il punto verde nella barra laterale indica una connessione WebSocket attiva e scompare quando cade. I dati verranno aggiornati alla riconnessione.
`
  }
}
