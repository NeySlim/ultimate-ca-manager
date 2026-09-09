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
          { label: 'Revoca', text: 'Revoca una CA intermedia dalla sua CA padre: pubblicata nella CRL e nell\'OCSP del padre, e la CA non può più firmare (permanente)' },
          { label: 'Ripara catena', text: 'Correggi automaticamente le relazioni padre-figlio interrotte' },
        ]
      },
      {
        title: 'CA firmate esternamente (modalità CSR, v2.214)',
        content: 'Il tipo di creazione «Firmata da CA esterna (CSR)» copre il pattern della root offline: la coppia di chiavi risiede in UCM, il certificato viene firmato altrove. La chiave privata non lascia mai UCM.',
        items: [
          { label: 'Crea', text: 'UCM genera la coppia di chiavi (locale o HSM) e una CSR di tipo CA — la CSR viene scaricata automaticamente' },
          { label: 'In attesa del certificato', text: 'La CA in attesa non può firmare, essere esportata, fare da padre o andare offline finché il suo certificato non è installato' },
          { label: 'Carica certificato', text: 'Incolla o carica il certificato firmato esternamente (PEM/DER). La sua chiave pubblica deve corrispondere alla chiave privata memorizzata; i vincoli CA vengono applicati' },
          { label: 'Catena', text: 'Collegata automaticamente quando l\'emittente è noto a UCM — importa la root esterna (solo certificato) per una catena completa' },
          { label: 'Rinnova via CSR', text: 'Riemette una CSR dalla stessa chiave (SKI stabile); firmala esternamente e carica il nuovo certificato' },
          { label: 'Dopo il rinnovo', text: 'Il certificato sostituito resta valido fino al suo notAfter — UCM ne mostra il numero di serie dopo il caricamento; revocalo presso la root esterna se non deve più essere considerato attendibile' },
        ]
      },
      {
        title: 'CA supportate da HSM',
        items: [
          { label: 'Archiviazione chiave', text: 'Alla creazione della CA scegli Locale (cifrato in DB) o HSM' },
          { label: 'Genera nuova chiave', text: 'Crea una nuova chiave di firma sul provider HSM selezionato' },
          { label: 'Usa chiave esistente', text: 'Collega la CA a una chiave di firma inutilizzata già presente sull\'HSM' },
          { label: 'Nessuna esportazione chiave privata', text: 'Le chiavi supportate da HSM non lasciano mai l\'HSM — le esportazioni PKCS#12, JKS e solo-chiave sono disabilitate' },
          { label: 'Prerequisito', text: 'Prima configura e collega un provider HSM in Gestione HSM' },
        ]
      },
      {
        title: 'Modalità offline',
        items: [
          { label: 'Scopo', text: "Proteggere la chiave privata di una CA (tipicamente una root) dall'uso a runtime mantenendo disponibili certificato, catena, CRL e OCSP" },
          { label: 'Protetta da password', text: "La chiave è cifrata con una password fornita dall'utente (PKCS#8) e rimane nel database. Ripristino inserendo la password." },
          { label: 'Esportata su file', text: 'La chiave è esportata come PEM cifrato scaricabile una volta e rimossa dal database. Ripristino caricando nuovamente il file con la password.' },
          { label: 'Politica password', text: 'La password segue le regole di complessità UCM (lunghezza e classi di caratteri). Se persa, la chiave è irrecuperabile.' },
          { label: 'Effetto sulla firma', text: "La firma di CSR, l'emissione di certificati e il rinnovo della CA sono bloccati offline. CRL e OCSP continuano a funzionare dalle firme in cache." },
          { label: 'Sub-CA', text: 'Sia le CA root che intermedie possono essere portate offline indipendentemente' },
        ]
      },
      {
        title: 'CRL esterne per CA senza chiave (v2.215)',
        content: 'Una CA la cui chiave non è utilizzabile da UCM (CA offline, importazione solo certificato) non può firmare la propria CRL — carica invece una CRL generata accanto alla chiave offline.',
        items: [
          { label: 'Dove', text: 'Pannello di dettaglio della CA › Lista di revoca (CRL): mostra il numero della CRL servita, il conteggio delle voci, this/next update e un avviso una volta superato il nextUpdate' },
          { label: 'Caricamento', text: 'Solo CRL complete (non delta), in formato PEM o DER. La firma deve essere verificabile con il certificato della CA e l\'emittente deve corrispondere al suo soggetto' },
          { label: 'Monotonicità', text: 'Un caricamento più vecchio della CRL attualmente servita (numero CRL o thisUpdate) viene rifiutato — emettila con un numero CRL più alto' },
          { label: 'Pubblicazione', text: 'La CRL caricata viene servita al percorso CDP esistente della CA e OCSP risponde «revocato» per i numeri di serie che elenca' },
          { label: 'Flusso di lavoro', text: 'Revoca presso la root offline, genera la CRL della root nell\'ambiente air-gap, caricala qui — la chiave della root non va mai online' },
        ]
      },
    ],
    tips: [
      'Le CA con l\'icona della chiave (🔑) hanno una chiave privata e possono firmare certificati',
      'Porta la CA root offline non appena le tue intermedie sono operative',
      'Usa «Esportata su file» per il massimo isolamento air-gap; «Protetta da password» per un ripristino rapido in loco',
      'L\'esportazione PKCS#12 include la catena completa ed è ideale per il backup',
    ],
    warnings: [
      'L\'eliminazione di una CA NON revoca i certificati che ha emesso — revocali prima',
      'Le chiavi private sono memorizzate crittografate; la perdita del database significa la perdita delle chiavi',
      'Le password della modalità offline NON sono recuperabili — conservale nel tuo password manager / vault prima di confermare',
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

### Crea una CA firmata esternamente (modalità CSR, v2.214)
Per il pattern della root offline — la chiave della CA emittente risiede in UCM, il suo certificato viene firmato altrove:
1. Clicca **Crea** → tipo **Firmata da CA esterna (CSR)**
2. Compila il Soggetto e le impostazioni della chiave (locale o HSM) — la validità è decisa dal firmatario esterno
3. Invia: UCM genera la coppia di chiavi e una CSR di tipo CA (scaricata automaticamente)
4. Fai firmare la CSR dalla tua CA root esterna/offline
5. Torna sulla CA (badge **In attesa del certificato**), clicca **Carica certificato** e fornisci il certificato firmato (PEM o DER)

UCM attiva la CA solo se la chiave pubblica del certificato corrisponde alla chiave privata memorizzata e i vincoli CA sono rispettati. La catena si collega automaticamente quando l'emittente è noto a UCM — importa la root esterna (solo certificato) per una catena completa. Fino all'attivazione, la CA in attesa non può firmare, essere esportata, fare da CA padre o andare offline.

Per rinnovare, usa **Rinnova via CSR**: una nuova CSR viene emessa **dalla stessa chiave** (lo SKI resta stabile), firmata esternamente e caricata tramite lo stesso flusso.

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

## Revoca di una CA intermedia

Una CA intermedia la cui chiave è compromessa o che viene dismessa si revoca presso la sua CA padre, come un certificato:

1. Seleziona la CA intermedia e clicca **Revoca CA**
2. Scegli il motivo RFC 5280 (compromissione della chiave, compromissione della CA, cessazione dell'attività, ...)
3. Conferma: la revoca è permanente

Cosa succede dopo:
- Il numero di serie della CA viene pubblicato nella **CRL della CA padre** (rigenerata immediatamente) e il **responder OCSP** del padre risponde \`revoked\` con il motivo
- La CA revocata **non può più firmare** nulla: certificati, CSR, rinnovi, sub-CA, e nemmeno le CA sotto di essa
- I certificati che ha emesso non sono più considerati attendibili dai client che validano la catena; la sua CRL e il suo OCSP continuano a essere serviti finché la CA non viene eliminata
- L'eliminazione della CA revocata mantiene la sua voce nella CRL del padre fino alla scadenza originale del certificato

> ⚠ Una CA root non può essere revocata da UCM (autofirmata: le relying party la rimuovono dai loro trust store), e un'intermedia firmata da una root esterna si revoca presso quella root. La sua CRL può poi essere servita da UCM (vedi Modalità offline).

## Eliminazione di una CA

> ⚠ L'eliminazione di una CA la rimuove da UCM ma NON revoca i certificati che ha emesso. Revoca prima i certificati se necessario.

L'eliminazione è bloccata se la CA ha CA figlie. Elimina o riassegna le figlie prima.

## CA supportate da HSM

UCM può memorizzare la chiave di firma di una CA su un modulo di sicurezza hardware (HSM) esterno anziché nel database cifrato locale. È l'opzione consigliata per le CA radice e intermedie in produzione.

### Quando usarlo
- Requisiti di conformità (FIPS 140-2/3, eIDAS, Common Criteria)
- Difesa in profondità: le chiavi non possono essere esfiltrate anche se l'host UCM è compromesso
- Custodia centralizzata delle chiavi tra più strumenti PKI

### Prerequisiti
1. Apri **Gestione HSM** e configura un provider (PKCS#11 / OpenBao / ecc.)
2. Verifica che il provider sia **Attivo** e **Connesso**

### Passo per passo
1. Apri **Crea CA**
2. Compila Subject e validità come al solito
3. In **Archiviazione chiave**, passa da *Locale* a **HSM**
4. Scegli il provider HSM
5. Scegli una modalità chiave:
   - **Genera nuova chiave** — fornisci un'etichetta (lettere/cifre/_/-) e scegli l'algoritmo (RSA-2048/3072/4096 o EC-P256/P384/P521)
   - **Usa chiave esistente** — scegli una chiave di firma inutilizzata già presente sull'HSM
6. Invia. UCM crea il certificato CA e lo collega alla chiave HSM.

### Limitazioni
- Le chiavi private supportate da HSM **non possono essere esportate**. Le opzioni di esportazione PKCS#12, JKS e solo-chiave sono nascoste per le CA HSM. Può essere esportato solo il certificato (PEM/DER/P7B).
- **Non esiste migrazione in loco** tra Locale e HSM. Per «spostare» una CA locale esistente su un HSM, crea una nuova CA sull'HSM e riemetti i certificati.
- Le chiavi esistenti offerte in *Usa chiave esistente* sono filtrate a chiavi asimmetriche di firma non ancora collegate ad altre CA.

## Modalità offline

Togli la chiave di firma di una CA dall'uso a runtime senza eliminare la CA. Certificato, catena, CRL e OCSP continuano a funzionare — solo le operazioni di firma (firma CSR, emissione certificato, rinnovo CA) sono bloccate.

Questo è il modo standard per proteggere una CA root tra cerimonie rare, mantenendo online la sua trust anchor e l'infrastruttura di revoca.

### Due modalità

**Protetta da password** — la chiave privata rimane nel database UCM, wrappata (PKCS#8) con una password che scegli tu. Per riportare la CA online, clicca su **Ripristina** e reinserisci la password. Veloce e comodo; la sicurezza dipende dalla forza della password e dal fatto che UCM non sia compromesso.

**Esportata su file** — la chiave privata viene esportata come file PEM cifrato con password scaricato una volta. La chiave viene poi **rimossa dal database**. Per riportare la CA online, clicca su **Ripristina**, carica il file e inserisci la password. È l'opzione più forte (vero air-gap) ma sei pienamente responsabile del file: se lo perdi, la chiave è irrecuperabile.

### Regole password
La password segue la politica di complessità standard UCM: lunghezza minima, mix di classi di caratteri, niente sequenze banali. Le stesse regole delle password utente.

### Passo per passo — Porta offline
1. Apri il pannello di dettaglio della CA
2. Clicca su **Porta offline**
3. Leggi la spiegazione, clicca su **Continua**
4. Scegli una modalità (*Protetta da password* o *Esportata su file*)
5. Inserisci la password due volte
6. Conferma. Per *Esportata su file*, la chiave cifrata viene scaricata immediatamente — conservala in sicurezza.

### Passo per passo — Ripristina
1. Apri il pannello di dettaglio della CA offline
2. Clicca su **Ripristina**
3. Inserisci la password
4. Per *Esportata su file*: seleziona anche il file di chiave scaricato in precedenza
5. Conferma. Le operazioni di firma riprendono immediatamente.

### Effetto sulle operazioni
| Operazione | Online | Offline |
|---|---|---|
| Emetti certificato | Consentito | **Bloccato** |
| Firma CSR | Consentito | **Bloccato** |
| Rinnova CA | Consentito | **Bloccato** |
| Rinnova certificato emesso | Consentito | **Bloccato** |
| Servire CRL / OCSP | Consentito | Consentito (firma in cache) |
| Esportare certificato / catena | Consentito | Consentito |
| Elimina CA | Consentito | Consentito |

> ⚠ Le password della modalità offline **non sono recuperabili**. Conservale nel tuo password manager / vault prima di confermare. Password persa = CA inutilizzabile = riemissione completa della gerarchia subordinata.
`
  }
}