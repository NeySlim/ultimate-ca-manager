export default {
  helpContent: {
    title: 'Panoramica',
    subtitle: 'Cosa richiede un intervento e lo stato della PKI',
    overview: 'Sei schede indipendenti sui dati in tempo reale della tua PKI. Ogni scheda si carica per conto suo e mostra il proprio stato di caricamento, vuoto, errore o permesso mancante. Ogni contatore che ha un elenco apre l\'elenco dei certificati filtrato esattamente sui certificati che conta.',
    sections: [
      {
        title: 'Schede',
        items: [
          { label: 'Da gestire', text: 'I sei elementi più urgenti, quelli critici per primi, ciascuno con il link al proprio record; un livello compresso dà il totale per tipo, e i quattro tipi di rinnovo aprono l\'elenco dei certificati' },
          { label: 'Stato dell\'automazione', text: 'Per protocollo (ACME, SCEP, EST) i successi e i fallimenti giornalieri, e lo stato dello scheduler' },
          { label: 'Gerarchia', text: 'Le autorità ad albero sotto la loro CA padre, con lo stato di CRL e OCSP, un contrassegno offline o firmata in modo incrociato, e i certificati emessi da ciascuna in 7 giorni; ogni autorità apre la propria pagina' },
          { label: 'Orizzonte di scadenza', text: 'I contatori dei certificati in scadenza e scaduti, ciascuno con il proprio elenco, e i cinque certificati che scadono per primi' },
          { label: 'Conformità', text: 'Certificati attivi per algoritmo di chiave e debolezza (RSA sotto i 3072 bit, hash di firma debole, certificati server oltre 398 giorni, catena incompleta, nessuna chiave privata); ogni contatore apre l\'elenco corrispondente' },
          { label: 'Ultime operazioni', text: 'Le cinque operazioni più recenti; con il permesso di audit, un link apre l\'intero registro' },
        ]
      },
    ],
    tips: [
      'Scegli il preset Operatore, Responsabile o Tutte le schede nell\'intestazione per decidere quali schede mostrare',
      'Il layout è salvato con il tuo account e ti segue tra i browser',
      'Nell\'elenco dei certificati, i filtri provenienti dalla panoramica compaiono come chip; rimuovine uno con la sua x',
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
