export default {
  helpContent: {
    title: 'Dashboard',
    subtitle: 'Panoramica del sistema e monitoraggio',
    overview: 'Panoramica in tempo reale della tua infrastruttura PKI. I widget mostrano lo stato dei certificati, gli avvisi di scadenza, lo stato del sistema e le attività recenti. Il layout è completamente personalizzabile con il trascinamento.',
    sections: [
      {
        title: 'Widget',
        items: [
          { label: 'Statistiche', text: 'Totale CA, certificati attivi, CSR in attesa e conteggio delle scadenze imminenti' },
          { label: 'Tendenza certificati', text: 'Grafico storico delle emissioni nel tempo' },
          { label: 'Distribuzione stati', text: 'Grafico a torta: validi / in scadenza / scaduti / revocati' },
          { label: 'Prossima scadenza', text: 'Certificati in scadenza entro 30 giorni' },
          { label: 'Stato del sistema', text: 'Stato dei servizi: ACME, SCEP, EST, OCSP, CRL/CDP, rinnovo automatico' },
          { label: 'Attività recente', text: 'Ultime operazioni eseguite nel sistema' },
          { label: 'Certificati recenti', text: 'Certificati emessi o importati di recente' },
          { label: 'Autorità di certificazione', text: 'Elenco CA con informazioni sulla catena' },
          { label: 'Account ACME', text: 'Account client ACME registrati' },
        ]
      },
    ],
    tips: [
      'Trascina i widget per riorganizzare il layout della dashboard',
      'Clicca l\'icona dell\'occhio nell\'intestazione per mostrare/nascondere widget specifici',
      'La dashboard si aggiorna in tempo reale tramite WebSocket — non è necessario aggiornare manualmente',
      'Il layout viene salvato per utente e persiste tra le sessioni',
    ],
  },
  helpGuides: {
    title: 'Dashboard',
    content: `
## Panoramica

La Dashboard è il tuo hub di monitoraggio centrale. Mostra metriche in tempo reale, grafici e avvisi sull'intera infrastruttura PKI attraverso widget personalizzabili.

## Widget

### Scheda statistiche
Mostra quattro contatori principali:
- **Totale CA** — Autorità di certificazione Root e Intermedie
- **Certificati attivi** — Certificati validi e non revocati
- **CSR in attesa** — Richieste di firma certificato in attesa di approvazione
- **In scadenza** — Certificati in scadenza entro 30 giorni

### Tendenza certificati
Un grafico a linee che mostra le emissioni di certificati nel tempo. Passa il mouse sui punti dati per vedere i conteggi esatti.

### Distribuzione stati
Grafico a torta che mostra la ripartizione degli stati dei certificati:
- **Valido** — Entro il periodo di validità e non revocato
- **In scadenza** — Scade entro 30 giorni
- **Scaduto** — Oltre la data "Non dopo"
- **Revocato** — Esplicitamente revocato

### Prossima scadenza
Elenca i certificati con scadenza più imminente. Clicca su un certificato per visualizzarne i dettagli. Configura la soglia in **Impostazioni → Generale**.

### Stato del sistema
Mostra lo stato dei servizi UCM:
- Server ACME (abilitato/disabilitato)
- Server SCEP
- Protocollo EST (abilitato/disabilitato, CA assegnata)
- Rigenerazione automatica CRL con conteggio CDP
- Risponditore OCSP
- Stato del rinnovo automatico
- Tempo di attività del servizio

### Attività recente
Un feed in tempo reale delle ultime operazioni: emissione certificati, revoche, importazioni, accessi utente. Si aggiorna in tempo reale tramite WebSocket.

### Autorità di certificazione
Visualizzazione rapida di tutte le CA con il loro tipo (Root/Intermedia) e il conteggio dei certificati.

### Account ACME
Elenca gli account client ACME registrati e il conteggio dei loro ordini.

## Personalizzazione

### Riorganizzazione dei widget
Trascina qualsiasi widget dalla sua intestazione per riposizionarlo. Il layout utilizza una griglia responsiva che si adatta alle dimensioni dello schermo.

### Mostrare/nascondere widget
Clicca l'**icona dell'occhio** nell'intestazione della pagina per attivare/disattivare la visibilità dei singoli widget. I widget nascosti vengono ricordati tra le sessioni.

### Persistenza del layout
La configurazione del layout viene salvata per utente nel browser. Persiste tra le sessioni e i dispositivi che condividono lo stesso profilo del browser.

## Aggiornamenti in tempo reale
La dashboard riceve aggiornamenti in tempo reale tramite WebSocket. Non è necessario aggiornare manualmente — nuovi certificati, cambi di stato e voci di attività appaiono automaticamente.

> 💡 Se il WebSocket è disconnesso, appare un indicatore giallo nella barra laterale. I dati verranno aggiornati alla riconnessione.
`
  }
}
