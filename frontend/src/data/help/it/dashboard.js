export default {
  helpContent: {
    title: 'Dashboard',
    subtitle: 'Panoramica del sistema e monitoraggio',
    overview: 'Panoramica in tempo reale della tua infrastruttura PKI. I widget mostrano lo stato dei certificati, gli avvisi di scadenza, lo stato del sistema e le attività recenti. Il layout è completamente personalizzabile con il trascinamento.',
    sections: [
      {
        title: 'Widget',
        items: [
          { label: 'Statistiche', text: 'Totale certificati (scaduti e revocati inclusi), CA, CSR in attesa e account ACME, più i certificati SSH quando esiste una CA SSH' },
          { label: 'Attività certificati', text: 'Certificati emessi, revocati e scaduti per giorno nel periodo scelto' },
          { label: 'Distribuzione stati', text: 'Grafico a torta: validi / in scadenza / scaduti / revocati' },
          { label: 'Prossima scadenza', text: 'I sei certificati validi che scadono per primi, qualunque sia la data; il firmatario TSA dedicato configurato è contrassegnato con un chip "TSA signer" (v2.218)' },
          { label: 'Stato del sistema', text: 'Stato dei servizi: ACME, SCEP, EST, OCSP, CRL/CDP, TSA (v2.218), rinnovo automatico, SMTP e webhook. I badge mostrano uno stato di avviso ambra distinto (firmatario TSA prossimo alla scadenza, SMTP configurato ma disabilitato) e il relativo messaggio di stato al passaggio del mouse' },
          { label: 'Attività recente', text: 'Ultime operazioni eseguite nel sistema' },
          { label: 'Certificati recenti', text: 'Certificati emessi o importati di recente' },
          { label: 'Autorità di certificazione', text: 'Ultime CA, ciascuna contrassegnata Root o Sub' },
          { label: 'Account ACME', text: 'Account client ACME registrati' },
          { label: 'Scadenza trust store', text: 'Certificati attendibili che scadono per primi' },
        ]
      },
    ],
    tips: [
      'Clicca Modifica layout nell\'intestazione, poi trascina i widget per riorganizzarli',
      'Clicca il pulsante Personalizza (icona cursori) nell\'intestazione, poi l\'occhio accanto a un widget per mostrarlo o nasconderlo',
      'La dashboard si aggiorna in tempo reale tramite WebSocket: non è necessario aggiornare manualmente',
      'Il layout è salvato in questo browser, per ogni account che accede da esso',
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
