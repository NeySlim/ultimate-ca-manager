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
          { label: 'Certificati', text: 'Revoca, rinnova, elimina o esporta, filtra per stato e CA emittente' },
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
      'Revoca, rinnovo, firma ed eliminazione chiedono conferma prima di essere eseguiti; un\'esportazione parte subito',
    ],
    warnings: [
      'L\'eliminazione massiva è irreversibile: crea sempre un backup prima',
      'La revoca massiva pubblicherà CRL aggiornate per tutte le CA interessate',
    ],
  },
  helpGuides: {
    title: 'Operazioni',
    content: `
## Panoramica

Operazioni massive e gestione dei dati. Esegui azioni batch su più risorse contemporaneamente.

## Scheda Importazione

Come la pagina Importa ed esporta: procedura guidata di importazione intelligente e integrazione OPNsense (connetti, sfoglia e importa da OPNsense).

## Scheda Esportazione

Esportazione massiva di certificati e CA.

## Azioni massive

Esegui operazioni batch su più risorse contemporaneamente.

### Come funziona
1. Seleziona il **tipo di risorsa** (Certificati, CA, CSR, Template, Utenti)
2. Spunta gli elementi nella tabella (la vista Cestino facoltativa li sposta invece tra due pannelli)
3. Scegli l'**azione** da eseguire
4. Conferma ed esegui

### Azioni disponibili per risorsa

#### Certificati
- **Revoca massiva**: Revoca più certificati contemporaneamente
- **Rinnovo massivo**: Rinnova più certificati
- **Esportazione massiva**: Scarica i certificati selezionati come bundle
- **Eliminazione massiva**: Rimuovi permanentemente i certificati selezionati

#### CA
- **Esportazione massiva**: Scarica le CA selezionate
- **Eliminazione massiva**: Rimuovi le CA selezionate (non devono avere figlie)

#### CSR
- **Firma massiva**: Firma più CSR con una CA selezionata
- **Eliminazione massiva**: Rimuovi i CSR selezionati

#### Template
- **Eliminazione massiva**: Rimuovi i template selezionati

#### Utenti
- **Eliminazione massiva**: Rimuovi permanentemente gli utenti selezionati

> ⚠ Le operazioni massive sono irreversibili. Crea sempre un backup prima di eseguire eliminazioni o revoche massive.

> 💡 Usa la ricerca e i filtri sopra la tabella per trovare rapidamente elementi specifici.
`
  }
}
