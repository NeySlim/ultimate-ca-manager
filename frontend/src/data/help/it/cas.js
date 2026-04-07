export default {
  helpContent: {
    title: 'Autorità di certificazione',
    subtitle: 'Gestisci la tua gerarchia PKI',
    overview: 'Crea e gestisci Autorità di certificazione Root e Intermedie. Costruisci una catena di fiducia completa per la tua organizzazione. Le CA con chiave privata possono firmare i certificati direttamente.',
    sections: [
      {
        title: 'Viste',
        items: [
          { label: 'Vista ad albero', text: 'Visualizzazione gerarchica delle relazioni padre-figlio tra CA' },
          { label: 'Vista elenco', text: 'Vista tabellare piatta con ordinamento e filtri' },
          { label: 'Vista organizzazione', text: 'Raggruppata per organizzazione per configurazioni multi-tenant' },
        ]
      },
      {
        title: 'Azioni',
        items: [
          { label: 'Crea CA Root', text: 'Autorità di livello superiore autofirmata' },
          { label: 'Crea Intermedia', text: 'CA firmata da una CA padre nella catena' },
          { label: 'Importa CA', text: 'Importa un certificato CA esistente (con o senza chiave privata)' },
          { label: 'Esporta', text: 'PEM, DER o PKCS#12 (P12/PFX) con protezione password' },
          { label: 'Rinnova CA', text: 'Riemetti il certificato CA con un nuovo periodo di validità' },
          { label: 'Ripara catena', text: 'Correggi automaticamente le relazioni padre-figlio interrotte' },
        ]
      },
    ],
    tips: [
      'Le CA con l\'icona della chiave (🔑) hanno una chiave privata e possono firmare certificati',
      'Usa CA intermedie per la firma quotidiana, mantieni la CA root offline quando possibile',
      'L\'esportazione PKCS#12 include la catena completa ed è ideale per il backup',
    ],
    warnings: [
      'L\'eliminazione di una CA NON revoca i certificati che ha emesso — revocali prima',
      'Le chiavi private sono memorizzate crittografate; la perdita del database significa la perdita delle chiavi',
    ],
  },
  helpGuides: {
    title: 'Autorità di certificazione',
    content: `
## Panoramica

Le Autorità di certificazione (CA) costituiscono le fondamenta della tua PKI. UCM supporta gerarchie CA multilivello con CA Root, CA Intermedie e Sub-CA.

## Tipi di CA

### CA Root
Un certificato autofirmato che funge da ancora di fiducia. Le CA Root dovrebbero idealmente essere mantenute offline negli ambienti di produzione. In UCM, una CA Root non ha genitore.

### CA Intermedia
Firmata da una CA Root o da un'altra CA Intermedia. Utilizzata per la firma quotidiana dei certificati. Le CA Intermedie limitano il raggio d'azione in caso di compromissione.

### Sub-CA
Qualsiasi CA firmata da una CA Intermedia, creando livelli gerarchici più profondi.

## Viste

### Vista ad albero
Mostra la gerarchia completa delle CA come albero espandibile/comprimibile. Le relazioni padre-figlio sono visualizzate con indentazione e linee di collegamento.

### Vista elenco
Tabella piatta con colonne ordinabili: Nome, Tipo, Stato, Certificati emessi, Data di scadenza.

### Vista organizzazione
Raggruppa le CA per il campo Organizzazione (O). Utile per configurazioni multi-tenant dove diversi dipartimenti gestiscono alberi CA separati.

## Creazione di una CA

### Crea CA Root
1. Clicca **Crea** → **CA Root**
2. Compila i campi del Soggetto (CN, O, OU, C, ST, L)
3. Seleziona l'algoritmo della chiave (RSA 2048/4096, ECDSA P-256/P-384)
4. Imposta il periodo di validità (tipicamente 10-20 anni per le CA Root)
5. Facoltativamente seleziona un template di certificato
6. Clicca **Crea**

### Crea CA Intermedia
1. Clicca **Crea** → **CA Intermedia**
2. Seleziona la **CA padre** (deve avere una chiave privata)
3. Compila i campi del Soggetto
4. Imposta il periodo di validità (tipicamente 5-10 anni)
5. Clicca **Crea**

> ⚠ La validità della CA Intermedia non può superare quella della sua CA padre.

## Importazione di una CA

Importa certificati CA esistenti tramite:
- **File PEM** — Certificato in formato PEM
- **File DER** — Formato binario DER
- **PKCS#12** — Bundle certificato + chiave privata (richiede password)

Quando si importa senza chiave privata, la CA può verificare i certificati ma non può firmarne di nuovi.

## Esportazione di una CA

Formati di esportazione:
- **PEM** — Certificato codificato in Base64
- **DER** — Formato binario
- **PKCS#12 (P12/PFX)** — Certificato + chiave privata + catena, protetto da password

> 💡 L'esportazione PKCS#12 include la catena completa dei certificati ed è ideale per il backup.

## Chiavi private

Le CA con l'**icona della chiave** (🔑) hanno una chiave privata memorizzata in UCM e possono firmare certificati. Le CA senza chiave sono solo per la fiducia — validano le catene ma non possono emettere certificati.

### Archiviazione delle chiavi
Le chiavi private sono crittografate a riposo nel database UCM. Per una sicurezza superiore, considera l'utilizzo di un provider HSM (vedi pagina HSM).

## Ripara catena

Se le relazioni padre-figlio sono interrotte (es. dopo un'importazione), usa **Ripara catena** per ricostruire automaticamente la gerarchia basandosi sulla corrispondenza Emittente/Soggetto.

## Rinnovo di una CA

Il rinnovo riemette il certificato CA con:
- Stesso soggetto e chiave
- Nuovo periodo di validità
- Nuovo numero di serie

I certificati esistenti firmati dalla CA rimangono validi.

## Eliminazione di una CA

> ⚠ L'eliminazione di una CA la rimuove da UCM ma NON revoca i certificati che ha emesso. Revoca prima i certificati se necessario.

L'eliminazione è bloccata se la CA ha CA figlie. Elimina o riassegna le figlie prima.
`
  }
}
