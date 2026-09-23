export default {
  helpContent: {
    title: 'Modelli di certificato',
    subtitle: 'Profili certificato riutilizzabili',
    overview: 'Definisci profili certificato riutilizzabili con campi soggetto, key usage, extended key usage, periodi di validità e altre estensioni preconfigurati. Applica i modelli durante l\'emissione o la firma dei certificati.',
    sections: [
      {
        title: 'Origine',
        definitions: [
          { term: 'Sistema', description: 'Predefiniti all\'installazione. Duplicane uno per ottenere una copia modificabile: il modello stesso non può essere modificato né eliminato' },
          { term: 'Personalizzato', description: 'Creati o importati qui, gli unici che possono essere modificati o eliminati' },
        ]
      },
      {
        title: 'Funzionalità',
        items: [
          { label: 'Tipo', text: 'Web Server, Email, VPN Server o Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon o Personalizzato. Imposta i valori predefiniti di Key Usage, EKU e SAN' },
          { label: 'Valori predefiniti soggetto', text: 'Precompila Organizzazione, OU, Paese, Stato, Città' },
          { label: 'Key Usage', text: 'Digital Signature, Key Encipherment, ecc.' },
          { label: 'Extended Key Usage', text: 'Server Auth, Client Auth, Code Signing, Email Protection' },
          { label: 'Validità', text: 'Periodo di validità predefinito in giorni' },
          { label: 'Duplica', text: 'Clona un modello esistente e modificalo' },
          { label: 'Mostra sistema', text: 'Nascondi i modelli integrati per lavorare solo con i tuoi. Memorizzato per browser' },
          { label: 'Importa/Esporta', text: 'Condividi modelli come file JSON tra istanze UCM' },
        ]
      },
      {
        title: 'Autoenrollment Windows',
        items: [
          { label: 'Consenti autoenrollment', text: 'Pubblicizza il modello come autoEnroll=true nella Certificate Enrollment Policy, così i client GPO/Kerberos lo richiedono automaticamente al logon. Disattivato per impostazione predefinita, l\'enrollment manuale resta possibile senza questo flag' },
          { label: 'Costruisci soggetto da Active Directory', text: 'Deriva soggetto e SAN dall\'oggetto AD del richiedente (tramite l\'AD Connector) invece di richiedere che sia il client a fornirli, per l\'autoenrollment GPO non presidiato' },
          { label: 'Limita l\'enrollment a un gruppo AD', text: 'Solo i membri del gruppo AD configurato (inclusa l\'appartenenza annidata) possono fare enrollment tramite l\'endpoint Kerberos. Vuoto = qualsiasi principal autenticato. Non applicato sull\'endpoint Username/Password' },
          { label: 'Campi soggetto bloccati', text: 'Forza i valori C/ST/L/O/OU su ogni certificato emesso via WSTEP, sovrascrivendo il CSR o la derivazione AD per quei campi. CN e SAN non sono mai interessati, lascia un campo vuoto per mantenerlo dinamico' },
        ]
      },
    ],
    tips: [
      'Crea modelli separati per server TLS, client e firma del codice',
      'Usa l\'azione Duplica per creare rapidamente varianti di un modello, anche di uno di sistema',
      'I modelli con flag di autoenrollment mostrano i badge AD / Auto / ACL / Pinned nell\'elenco',
    ],
  },
  helpGuides: {
    title: 'Modelli di certificato',
    content: `
## Panoramica

I modelli definiscono profili certificato riutilizzabili. Invece di configurare manualmente Key Usage, Extended Key Usage, validità e campi soggetto ogni volta, applica un modello per precompilare tutto.

## Sistema e Personalizzato

Ogni modello appartiene a una delle due categorie, indicata nella colonna **Origine**.

### Sistema
I modelli predefiniti all'installazione: Web Server (TLS/SSL), Email Certificate (S/MIME), VPN Server, VPN Client, Code Signing, OCSP Signing, Client Authentication e Smartcard Logon. Modifica ed Elimina sono rifiutati per questi modelli, sia nell'interfaccia sia dall'API. **Duplica** fornisce una copia modificabile su cui lavorare.

### Personalizzato
Tutto ciò che viene creato o importato qui. Questi modelli possono essere modificati ed eliminati liberamente.

Disattiva **Mostra sistema** nella barra degli strumenti per nascondere i modelli integrati e lavorare solo con i tuoi. La scelta viene memorizzata, a meno che tu non abbia ancora modelli personalizzati: in tal caso quelli integrati restano visibili.

Le autorità di certificazione non si creano dai modelli: creale nella pagina **Autorità di certificazione**.

## Creazione di un modello

1. Clicca **Crea modello**
2. Inserisci un **nome** e una descrizione opzionale
3. Seleziona il **tipo** di modello: Web Server, Email, VPN Server, VPN Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon o Personalizzato. Imposta i valori predefiniti di Key Usage, Extended Key Usage e SAN, che puoi poi modificare
4. Configura i **valori predefiniti del soggetto** (O, OU, C, ST, L)
5. Seleziona i flag **Key Usage**
6. Seleziona i valori **Extended Key Usage**
7. Imposta il **periodo di validità predefinito** in giorni
8. Clicca **Crea**

## Utilizzo dei modelli

Quando emetti un certificato o firmi un CSR, seleziona un modello dal menu a tendina. Il modello precompila:
- Campi soggetto (puoi sovrascriverli)
- Key Usage e Extended Key Usage
- Periodo di validità

## Flag di autoenrollment Windows

I modelli includono tre flag opt-in usati dai protocolli di autoenrollment Windows (XCEP/WSTEP, configurati in **Impostazioni → Autoenrollment Windows**):

- **Consenti autoenrollment**: Pubblicizza il modello come \`autoEnroll=true\` nella Certificate Enrollment Policy, così i client autenticati GPO/Kerberos lo richiedono automaticamente al logon senza alcuna azione dell'utente. Disattivato per impostazione predefinita: come nel vero ADCS, un modello può comunque essere richiesto manualmente (MMC «Richiedi nuovo certificato», \`certreq\`) senza questo flag, perché Enroll e Autoenroll sono permessi separati.
- **Costruisci soggetto da Active Directory**: Per l'autoenrollment GPO non presidiato: deriva soggetto e SAN del certificato dall'oggetto AD del richiedente (tramite l'AD Connector) invece di richiedere che sia il client a fornirli.
- **Limita l'enrollment a un gruppo AD**: Solo i principal appartenenti al gruppo Active Directory configurato (inclusa l'appartenenza annidata) possono fare enrollment con questo modello tramite l'endpoint autenticato Kerberos. Inserisci un nome di gruppo o un DN completo; lascia vuoto per consentire qualsiasi principal autenticato, come nel comportamento predefinito del vero ADCS. Non applicato sull'endpoint Username/Password, che non ha un'identità per richiesta da verificare.

I modelli con questi flag mostrano i badge **AD**, **Auto** e **ACL** nell'elenco dei modelli.

## Campi soggetto bloccati

Un modello può **bloccare** i campi organizzativi del soggetto: **C, ST, L, O, OU**: per i certificati emessi via WSTEP. Un valore bloccato viene forzato su ogni certificato emesso, sovrascrivendo qualunque valore fornito dal CSR del client o dalla derivazione Active Directory per quel campo.

- **Common Name e Subject Alternative Name non sono mai interessati**: restano dinamici per ogni richiedente
- Lascia un campo vuoto per mantenerlo dinamico
- I modelli con campi bloccati mostrano un badge **Pinned** e i valori bloccati appaiono nel pannello di dettaglio del modello

Usalo per garantire un'identità organizzativa uniforme (es. \`O\` e \`C\` fissi) su un intero parco in autoenrollment, indipendentemente da ciò che ogni client Windows invia.

## Duplicazione dei modelli

Clicca **Duplica** per creare una copia di un modello esistente. Modifica la copia senza influire sull'originale.

## Importa ed Esporta

### Esporta
Esporta i modelli come JSON per condividerli tra istanze UCM.

### Importa
Importa da:
- **File JSON**: Carica un file JSON del modello
- **Incolla JSON**: Incolla il JSON direttamente nell'area di testo

## Esempi comuni di modelli

### Server TLS
- Key Usage: Digital Signature, Key Encipherment
- Extended Key Usage: Server Authentication
- Validità: 365 giorni

### Autenticazione Client
- Key Usage: Digital Signature
- Extended Key Usage: Client Authentication
- Validità: 365 giorni

### Firma del codice
- Key Usage: Digital Signature
- Extended Key Usage: Code Signing
- Validità: 365 giorni
`
  }
}
