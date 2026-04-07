export default {
  helpContent: {
    title: 'Report',
    subtitle: 'Report di conformità e inventario PKI',
    overview: 'Genera, scarica e pianifica report per l\'audit di conformità. I report coprono l\'inventario dei certificati, i certificati in scadenza, la gerarchia CA, l\'attività di audit e lo stato di conformità delle politiche. Scarica un report esecutivo PDF per la revisione della dirigenza.',
    sections: [
      {
        title: 'Tipi di report',
        items: [
          { label: 'Inventario certificati', text: 'Elenco completo di tutti i certificati con stato' },
          { label: 'Certificati in scadenza', text: 'Certificati in scadenza entro una finestra temporale specificata' },
          { label: 'Gerarchia CA', text: 'Struttura delle Autorità di certificazione e statistiche' },
          { label: 'Riepilogo audit', text: 'Riepilogo eventi di sicurezza e attività utente' },
          { label: 'Stato conformità', text: 'Riepilogo conformità e violazioni delle politiche' },
        ]
      },
      {
        title: 'Report esecutivo PDF',
        items: [
          { label: 'Scarica PDF', text: 'Report PDF professionale con un clic per la dirigenza e gli auditor' },
          { label: 'Contenuti', text: 'Riepilogo esecutivo, valutazione dei rischi, inventario certificati, punteggi di conformità, infrastruttura CA, attività di audit e raccomandazioni' },
          { label: 'Grafici e visuali', text: 'Include indicatore di rischio, distribuzione degli stati, timeline delle scadenze e analisi della conformità' },
        ]
      },
      {
        title: 'Pianificazione',
        items: [
          { label: 'Report scadenze', text: 'Email giornaliera con i certificati in scadenza' },
          { label: 'Report conformità', text: 'Email settimanale con lo stato di conformità delle politiche' },
        ]
      },
    ],
    tips: [
      'Usa il report esecutivo PDF per le revisioni della dirigenza e gli audit di conformità.',
      'Scarica i report come CSV per l\'analisi nei fogli di calcolo o JSON per l\'automazione.',
      'Usa la funzione di invio di test per verificare la consegna email prima di abilitare le pianificazioni.',
    ],
  },
  helpGuides: {
    title: 'Report',
    content: `
## Panoramica

Genera, scarica e pianifica report di conformità PKI. I report forniscono visibilità sulla tua infrastruttura di certificati per audit, conformità e pianificazione operativa.

## Tipi di report

### Inventario certificati
Elenco completo di tutti i certificati gestiti da UCM. Include soggetto, emittente, numero di serie, date di validità, tipo di chiave e stato attuale. Usa per audit di conformità e documentazione dell'infrastruttura.

### Certificati in scadenza
Certificati in scadenza entro una finestra temporale specificata (predefinito: 30 giorni). Fondamentale per evitare interruzioni — rivedi questo report regolarmente o pianificalo per la consegna giornaliera.

### Gerarchia CA
Struttura delle Autorità di certificazione che mostra le relazioni padre-figlio, il conteggio dei certificati per CA e lo stato della CA. Utile per comprendere la topologia della tua PKI.

### Riepilogo audit
Riepilogo eventi di sicurezza e attività utente. Include tentativi di accesso, operazioni sui certificati, violazioni delle politiche e modifiche alla configurazione. Essenziale per gli audit di sicurezza.

### Stato conformità
Riepilogo conformità e violazioni delle politiche. Mostra quali certificati sono conformi alle tue politiche e quali le violano. Necessario per la conformità normativa.

## Report esecutivo PDF

Clicca **Scarica PDF** in alto a destra per generare un report esecutivo professionale adatto per revisioni della dirigenza, presentazioni al consiglio e audit di conformità.

### Contenuti
Il report PDF include 9 sezioni:
1. **Pagina di copertina** — Metriche chiave, indicatore di rischio e risultati principali in sintesi
2. **Indice** — Navigazione rapida
3. **Riepilogo esecutivo** — Stato generale della PKI, distribuzione dei certificati e livello di rischio
4. **Valutazione dei rischi** — Risultati critici, certificati in scadenza, algoritmi deboli
5. **Inventario certificati** — Analisi per stato, tipo di chiave e CA emittente
6. **Analisi della conformità** — Distribuzione dei punteggi, analisi per grado, punteggi per categoria
7. **Ciclo di vita dei certificati** — Timeline delle scadenze e tasso di automazione
8. **Infrastruttura CA** — Dettagli CA root e intermedie, gerarchia
9. **Raccomandazioni** — Azioni concrete basate sullo stato attuale della PKI

### Grafici e visuali
Il report include elementi visivi: barra indicatore di rischio, distribuzione degli stati, analisi per grado di conformità e timeline delle scadenze — progettati per stakeholder non tecnici.

> 💡 Il report PDF viene generato da dati in tempo reale. Scaricalo prima delle riunioni per lo snapshot più aggiornato.

## Generazione dei report

1. Trova il report che desideri nell'elenco
2. Clicca **▶ Genera** per creare un'anteprima
3. L'anteprima appare sotto come tabella formattata
4. Clicca **Chiudi** per chiudere l'anteprima

## Download dei report

Ogni riga del report ha pulsanti di download:
- **CSV** — Formato foglio di calcolo per Excel, Google Sheets o LibreOffice
- **JSON** — Dati strutturati per automazione e integrazione

> 💡 I report CSV sono più facili per gli stakeholder non tecnici. JSON è migliore per script e integrazioni API.

## Pianificazione dei report

### Report scadenze (giornaliero)
Invia automaticamente un report sulle scadenze dei certificati ogni giorno ai destinatari configurati. Abilitalo per individuare i certificati in scadenza prima che causino interruzioni.

### Report conformità (settimanale)
Invia un riepilogo della conformità alle politiche ogni settimana. Utile per il monitoraggio continuo della conformità senza sforzo manuale.

### Configurazione
1. Clicca **Pianifica report** in alto a destra
2. Abilita i report che vuoi pianificare
3. Aggiungi gli indirizzi email dei destinatari (premi Invio o clicca Aggiungi)
4. Clicca Salva

### Invio di test
Prima di abilitare le pianificazioni, usa il pulsante ✈️ su qualsiasi riga del report per inviare un report di test a un indirizzo email specifico. Questo verifica che SMTP sia configurato correttamente e che il formato del report soddisfi le tue esigenze.

> ⚠ I report pianificati richiedono che SMTP sia configurato in **Impostazioni → Email**. L'invio di test fallirà se SMTP non è configurato.

## Permessi

- **read:reports** — Genera e scarica report
- **read:audit + export:audit** — Scarica il report esecutivo PDF
- **write:settings** — Configura le pianificazioni dei report

> 💡 Pianifica prima il report scadenze — è il più operativamente prezioso e aiuta a prevenire le interruzioni legate ai certificati.
`
  }
}
