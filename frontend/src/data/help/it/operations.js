export default {
  helpContent: {
    title: 'Operazioni',
    subtitle: 'Importazione, esportazione e azioni massive',
    overview: 'Centro operativo centralizzato. Importa certificati da file o OPNsense, esporta bundle in formati PEM/P7B ed esegui azioni massive su tutti i tipi di risorse con ricerca e filtri inline.',
    sections: [
      {
        title: 'Schede laterali',
        items: [
          { label: 'Importa', text: 'Importazione intelligente con rilevamento automatico del formato, più sincronizzazione OPNsense per recuperare certificati dai firewall' },
          { label: 'Esporta', text: 'Scarica bundle di certificati per tipo di risorsa in formato PEM o P7B tramite schede azione' },
          { label: 'Azioni massive', text: 'Seleziona un tipo di risorsa ed esegui operazioni batch su più elementi' },
        ]
      },
      {
        title: 'Azioni massive',
        items: [
          { label: 'Certificati', text: 'Revoca, rinnova, elimina o esporta — filtra per stato e CA emittente' },
          { label: 'CA', text: 'Elimina o esporta autorità di certificazione' },
          { label: 'CSR', text: 'Firma con una CA o elimina le richieste in attesa' },
          { label: 'Template', text: 'Elimina template di certificato' },
          { label: 'Utenti', text: 'Elimina account utente' },
        ]
      },
    ],
    tips: [
      'Usa i chip delle risorse per passare rapidamente tra i tipi di risorsa',
      'La ricerca e i filtri inline (Stato, CA) ti permettono di restringere gli elementi senza lasciare la barra degli strumenti',
      'Alterna tra le modalità vista Tabella e Cestino (pannello di trasferimento) sul desktop',
      'Visualizza l\'anteprima delle modifiche prima di confermare le operazioni massive',
    ],
    warnings: [
      'L\'eliminazione massiva è irreversibile — crea sempre un backup prima',
      'La revoca massiva pubblicherà CRL aggiornate per tutte le CA interessate',
    ],
  },
  helpGuides: {
    title: 'Operazioni',
    content: `
## Panoramica

Operazioni massive e gestione dei dati. Esegui azioni batch su più risorse contemporaneamente.

## Scheda Importazione/Esportazione

Come la pagina Importa ed esporta — procedura guidata di importazione intelligente e funzionalità di esportazione massiva.

## Scheda OPNsense

Come l'integrazione OPNsense di Importa ed esporta — connetti, sfoglia e importa da OPNsense.

## Azioni massive

Esegui operazioni batch su più risorse contemporaneamente.

### Come funziona
1. Seleziona il **tipo di risorsa** (Certificati, CA, CSR, Template, Utenti)
2. Sfoglia gli elementi disponibili nel **pannello sinistro**
3. Sposta gli elementi nel **pannello destro** (selezionati) usando le frecce di trasferimento
4. Scegli l'**azione** da eseguire
5. Conferma ed esegui

### Azioni disponibili per risorsa

#### Certificati
- **Revoca massiva** — Revoca più certificati contemporaneamente
- **Rinnovo massivo** — Rinnova più certificati
- **Esportazione massiva** — Scarica i certificati selezionati come bundle
- **Eliminazione massiva** — Rimuovi permanentemente i certificati selezionati

#### CA
- **Esportazione massiva** — Scarica le CA selezionate
- **Eliminazione massiva** — Rimuovi le CA selezionate (non devono avere figlie)

#### CSR
- **Firma massiva** — Firma più CSR con una CA selezionata
- **Eliminazione massiva** — Rimuovi i CSR selezionati

#### Template
- **Esportazione massiva** — Esporta come JSON
- **Eliminazione massiva** — Rimuovi i template selezionati

#### Utenti
- **Disabilitazione massiva** — Disattiva gli account utente selezionati
- **Eliminazione massiva** — Rimuovi permanentemente gli utenti selezionati

> ⚠ Le operazioni massive sono irreversibili. Crea sempre un backup prima di eseguire eliminazioni o revoche massive.

> 💡 Usa la ricerca e il filtro nel pannello sinistro per trovare rapidamente elementi specifici.
`
  }
}
