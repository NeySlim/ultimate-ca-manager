export default {
  helpContent: {
    title: 'Importa ed esporta',
    subtitle: 'Migrazione dati e backup',
    overview: 'Importa certificati da fonti esterne ed esporta i tuoi dati PKI. L\'importazione intelligente rileva automaticamente i tipi di file. L\'integrazione OPNsense consente la sincronizzazione diretta con il tuo firewall.',
    sections: [
      {
        title: 'Importa',
        items: [
          { label: 'Importazione intelligente', text: 'Carica qualsiasi file certificato — UCM rileva automaticamente il formato (PEM, DER, P12, P7B)' },
          { label: 'Sincronizzazione OPNsense', text: 'Connettiti al firewall OPNsense e importa i suoi certificati e CA' },
        ]
      },
      {
        title: 'Esporta',
        items: [
          { label: 'Esporta certificati', text: 'Download massivo di certificati come bundle PEM o PKCS#7' },
          { label: 'Esporta CA', text: 'Download massivo di certificati CA e catene' },
        ]
      },
      {
        title: 'Integrazione OPNsense',
        items: [
          { label: 'Connessione', text: 'Fornisci URL OPNsense, chiave API e segreto API' },
          { label: 'Testa connessione', text: 'Verifica la connettività prima dell\'importazione' },
          { label: 'Seleziona elementi', text: 'Scegli quali certificati e CA importare' },
        ]
      },
    ],
    tips: [
      'L\'importazione intelligente gestisce bundle PEM con più certificati in un singolo file',
      'Testa la connessione OPNsense prima di eseguire un\'importazione completa',
      'I file PKCS#12 richiedono la password corretta per importare le chiavi private',
    ],
  },
  helpGuides: {
    title: 'Importa ed esporta',
    content: `
## Panoramica

Importa certificati da fonti esterne ed esporta i tuoi dati PKI per backup o migrazione.

## Importazione intelligente

La procedura guidata di importazione intelligente rileva automaticamente i tipi di file e li elabora:

### Formati supportati
- **PEM** — Certificati singoli o in bundle, CA e chiavi
- **DER** — Certificato o chiave in formato binario
- **PKCS#12 (P12/PFX)** — Certificato + chiave + catena (richiede password)
- **PKCS#7 (P7B)** — Catena di certificati senza chiavi

### Come funziona
1. Clicca **Importa** o trascina i file nella zona di rilascio
2. UCM analizza ogni file e ne identifica il contenuto
3. Rivedi gli elementi rilevati (CA, certificati, chiavi)
4. Clicca **Importa** per aggiungerli a UCM

> 💡 L'importazione intelligente gestisce bundle PEM con più certificati in un singolo file. Distingue automaticamente le CA dai certificati di entità finale.

## Integrazione OPNsense

Sincronizza certificati e CA da un firewall OPNsense:

### Configurazione
1. In OPNsense, crea una chiave API (Sistema → Accesso → Utenti → Chiavi API)
2. In UCM, inserisci l'URL OPNsense, la chiave API e il segreto API
3. Clicca **Testa connessione** per verificare

### Importazione
1. Clicca **Connetti** per recuperare i certificati e le CA disponibili
2. Seleziona gli elementi che vuoi importare
3. Clicca **Importa selezionati**

UCM importa i certificati con le loro chiavi private (se disponibili) e preserva la gerarchia CA.

## Esportazione certificati

Esportazione massiva di tutti i certificati:
- **PEM** — File PEM individuali
- **Bundle P7B** — Tutti i certificati in un singolo file PKCS#7
- **ZIP** — Tutti i certificati come file PEM individuali in un archivio ZIP

## Esportazione CA

Esportazione massiva di tutte le Autorità di certificazione:
- **PEM** — Catena di certificati in formato PEM
- **Catena completa** — Root → Intermedia → Sub-CA

## Migrazione tra istanze UCM

Per migrare da un'istanza UCM a un'altra:
1. Crea un **backup** sull'istanza di origine (Impostazioni → Backup)
2. Installa UCM sulla destinazione
3. **Ripristina** il backup sulla destinazione

Questo preserva tutti i dati: certificati, CA, chiavi, utenti, impostazioni e log di audit.
`
  }
}
