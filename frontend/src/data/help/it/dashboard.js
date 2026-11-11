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
    title: 'Panoramica',
    content: `
## Panoramica

La Panoramica è la pagina iniziale: sei schede indipendenti sui dati in tempo reale della tua PKI. Ogni scheda si carica per conto suo e mostra il proprio stato di caricamento, vuoto, errore o permesso mancante.

## Schede

### Da gestire
I sei elementi più urgenti, quelli critici per primi, ciascuno con il link al proprio record. Un livello compresso dà il totale per tipo; i quattro tipi di rinnovo aprono l'elenco dei certificati.

### Stato dell'automazione
Per protocollo (ACME, SCEP, EST), i successi e i fallimenti giornalieri e l'ultima operazione, più lo stato dello scheduler.

### Gerarchia
Le autorità ad albero sotto la loro CA padre, con lo stato di CRL e OCSP, un contrassegno offline o firmata in modo incrociato, e i certificati emessi da ciascuna in 7 giorni. Ogni autorità apre la propria pagina.

### Orizzonte di scadenza
I contatori dei certificati in scadenza e scaduti, ciascuno con il proprio elenco, e i cinque certificati che scadono per primi.

### Conformità
Certificati attivi per algoritmo di chiave e debolezza: RSA sotto i 3072 bit, hash di firma debole, certificati server oltre 398 giorni, catena incompleta, nessuna chiave privata. Ogni contatore apre l'elenco corrispondente.

### Ultime operazioni
Le cinque operazioni più recenti. Senza **read:audit** vedi solo i tuoi eventi; con il permesso, un link apre l'intero registro nella pagina Registri di audit.

## Aprire un elenco filtrato
Ogni contatore che ha un elenco apre la pagina Certificati filtrata esattamente sui certificati che conta. Il filtro compare come chip sopra la tabella; rimuovilo con la sua x.

## Scegliere le schede
Scegli il preset **Operatore**, **Responsabile** o **Tutte le schede** nell'intestazione della pagina per decidere quali schede mostrare. Il layout è salvato con il tuo account e ti segue tra i browser.

## Aggiornamento
Le schede si caricano all'apertura della pagina; una scheda in errore offre **Riprova**. L'icona di connessione nella barra superiore mostra lo stato del collegamento in tempo reale, e la barra di stato in basso mostra la versione e se il servizio risponde.
`
  }
}
