export default {
  helpContent: {
    title: 'Trust Store',
    subtitle: 'Gestione dei certificati fidati',
    overview: 'Conserva i certificati CA root e intermedi fidati. La vista catena di un certificato e le sue esportazioni completano la catena con un certificato del trust store il cui soggetto corrisponde al nome dell\'emittente. Il trust store può essere popolato dal trust store del sistema operativo o dalle CA gestite da UCM.',
    sections: [
      {
        title: 'Tipi di certificato',
        definitions: [
          { term: 'Root CA', description: 'Ancora di fiducia autofirmata di primo livello' },
          { term: 'Intermedio', description: 'Certificato CA firmato da una root o da un altro intermedio' },
          { term: 'Sistema', description: 'Importato dal trust store del sistema operativo' },
          { term: 'Code Signing', description: 'Certificato utilizzato per la verifica della firma del codice' },
          { term: 'Email', description: 'Certificato utilizzato per S/MIME' },
          { term: 'Personalizzato', description: 'Certificato fidato categorizzato manualmente' },
        ]
      },
      {
        title: 'Azioni',
        items: [
          { label: 'Aggiungi', text: 'Aggiungi i certificati delle CA gestite da UCM. Un certificato esterno si aggiunge tramite l\'API (POST /api/v2/truststore con PEM, oppure /api/v2/truststore/import con un file PEM o DER)' },
          { label: 'Sincronizza dal sistema', text: 'Importa le CA fidate del sistema operativo in UCM, fino al numero scelto (500 per impostazione predefinita, 1000 al massimo)' },
          { label: 'Esporta', text: 'Scarica i certificati fidati individualmente' },
          { label: 'Elimina selezionati', text: 'Seleziona più certificati e rimuovili insieme, ad esempio le CA di sistema filtrate come scadute; vengono rimosse solo le righe mostrate dai filtri attuali' },
        ]
      },
    ],
    tips: [
      'Usa "Sincronizza dal sistema" per popolare rapidamente il trust store con le CA a livello del sistema operativo',
      'Filtra per scopo per concentrarti su categorie specifiche di certificati',
    ],
  },
  helpGuides: {
    title: 'Trust Store',
    content: `
## Panoramica

Il Trust Store conserva i certificati CA fidati. Popolalo dalle CA gestite da UCM o dal trust store del sistema operativo.

## Categorie di certificati

- **Root CA**: Ancore di fiducia autofirmate
- **Intermedio**: CA firmate da root o altri intermedi
- **Sistema**: Importati dal trust store del sistema operativo
- **Code Signing**: Certificati per la verifica della firma del codice
- **Email**: Certificati per S/MIME
- **Personalizzato**: Certificati categorizzati manualmente

## Aggiunta dei certificati

### Dalle CA gestite
**Aggiungi** elenca le CA gestite da UCM: seleziona quelle da fidare.

### Certificati esterni
La pagina non ha un modulo di caricamento per un certificato esterno a UCM. Aggiungilo tramite l'API: \`POST /api/v2/truststore\` con il suo PEM, oppure \`POST /api/v2/truststore/import\` con un file PEM o DER.

### Sincronizza dal sistema
Importa le CA fidate del trust store del sistema operativo (es. il bundle CA di Mozilla su Linux), fino al numero scelto: 500 per impostazione predefinita, 1000 al massimo.

> 💡 La sincronizzazione dal sistema è un'importazione una tantum. Le modifiche al trust store del sistema operativo non vengono riflesse automaticamente.

## Gestione delle voci

- **Filtra per scopo**: Restringe l'elenco per categoria di certificato
- **Cerca**: Trova certificati per nome soggetto
- **Esporta**: Scarica singoli certificati in formato PEM
- **Elimina**: Rimuovi un certificato dal trust store
- **Elimina selezionati**: Seleziona più certificati e rimuovili insieme, ad esempio le CA di sistema filtrate come scadute; vengono rimosse solo le righe mostrate dai filtri attuali

## Casi d'uso

### Catene
La vista catena di un certificato, e le sue esportazioni con la catena, prendono un certificato del trust store il cui soggetto corrisponde al nome dell'emittente per completare la catena. Nessuna firma viene verificata rispetto al trust store.

Il trust store non ha alcun ruolo nell'autenticazione client mTLS (che usa la CA fidata scelta in Impostazioni › Sicurezza) né nella connessione del client ACME alla sua CA.
`
  }
}
