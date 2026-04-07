export default {
  helpContent: {
    title: 'Trust Store',
    subtitle: 'Gestione dei certificati fidati',
    overview: 'Importa e gestisci i certificati CA root e intermedi fidati. Il trust store viene utilizzato per la validazione della catena e può essere sincronizzato con il trust store del sistema operativo.',
    sections: [
      {
        title: 'Tipi di certificato',
        definitions: [
          { term: 'Root CA', description: 'Ancora di fiducia autofirmata di primo livello' },
          { term: 'Intermedio', description: 'Certificato CA firmato da una root o da un altro intermedio' },
          { term: 'Client Auth', description: 'Certificato utilizzato per l\'autenticazione client (mTLS)' },
          { term: 'Code Signing', description: 'Certificato utilizzato per la verifica della firma del codice' },
          { term: 'Personalizzato', description: 'Certificato fidato categorizzato manualmente' },
        ]
      },
      {
        title: 'Azioni',
        items: [
          { label: 'Importa file', text: 'Carica file certificato PEM, DER o PKCS#7' },
          { label: 'Importa URL', text: 'Recupera un certificato da un URL remoto' },
          { label: 'Aggiungi PEM', text: 'Incolla direttamente il testo del certificato codificato in PEM' },
          { label: 'Sincronizza dal sistema', text: 'Importa le CA fidate del sistema operativo in UCM' },
          { label: 'Esporta', text: 'Scarica i certificati fidati individualmente' },
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

Il Trust Store gestisce i certificati CA fidati utilizzati per la validazione della catena. Importa CA root e intermedie da fonti esterne o sincronizza con il trust store del sistema operativo.

## Categorie di certificati

- **Root CA** — Ancore di fiducia autofirmate
- **Intermedio** — CA firmate da root o altri intermedi
- **Client Auth** — Certificati per l'autenticazione client mTLS
- **Code Signing** — Certificati per la verifica della firma del codice
- **Personalizzato** — Certificati categorizzati manualmente

## Importazione dei certificati

### Da file
Carica file certificato nei seguenti formati:
- **PEM** — Codifica Base64 (singolo o raggruppato)
- **DER** — Formato binario
- **PKCS#7 (P7B)** — Catena di certificati

### Da URL
Recupera un certificato da un endpoint HTTPS remoto. UCM scarica e importa la catena di certificati del server.

### Incolla PEM
Incolla il testo del certificato codificato in PEM direttamente nell'area di testo.

### Sincronizza dal sistema
Importa tutte le CA fidate dal trust store del sistema operativo. Questo popola UCM con le stesse CA root fidate dal sistema operativo (es. il bundle CA di Mozilla su Linux).

> 💡 La sincronizzazione dal sistema è un'importazione una tantum. Le modifiche al trust store del sistema operativo non vengono riflesse automaticamente.

## Gestione delle voci

- **Filtra per scopo** — Restringe l'elenco per categoria di certificato
- **Cerca** — Trova certificati per nome soggetto
- **Esporta** — Scarica singoli certificati in formato PEM
- **Elimina** — Rimuovi un certificato dal trust store

## Casi d'uso

### Validazione della catena
Durante la verifica di una catena di certificati, UCM controlla il trust store per le CA root riconosciute.

### mTLS
I certificati client presentati durante l'autenticazione mutual TLS vengono validati rispetto al trust store.

### ACME
Quando UCM agisce come client ACME (Let's Encrypt), il trust store viene utilizzato per verificare il certificato della CA ACME.
`
  }
}
