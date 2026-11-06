export default {
  helpContent: {
    title: 'Certificati',
    subtitle: 'Emetti, gestisci e monitora i certificati',
    overview: 'Gestione centralizzata di tutti i certificati X.509. Emetti nuovi certificati dalle tue CA, importa quelli esistenti, monitora le date di scadenza e gestisci rinnovi e revoche.',
    sections: [
      {
        title: "Analisi di conformità",
        content: "L'azione « Analizza » nel dettaglio di un certificato lo passa attraverso linter di standard e mostra i risultati. Solo informativo, non blocca mai l'emissione.",
        items: [
          { label: "Profili", text: "RFC 5280 (sempre rilevante), CA/Browser Forum Baseline Requirements (certificati TLS server) ed ETSI EN 319 412 (certificati qualificati e correlati a eIDAS, inclusi i qcStatements)" },
          { label: "Gravità", text: "I risultati sono classificati: fatal, error, warning, notice, info" },
          { label: "Motore", text: "Basato su pkilint (e zlint se il suo binario è presente): dipendenza opzionale del server" },
          { label: "PKI interna", text: "Le regole CA/Browser Forum riguardano i certificati pubblici; aspettati risultati non applicabili su una PKI interna" },
        ]
      },
      {
        title: 'Stato del certificato',
        definitions: [
          { term: 'Valido', description: 'Entro il periodo di validità e non revocato' },
          { term: 'In scadenza', description: 'Scadrà entro 30 giorni' },
          { term: 'Scaduto', description: 'Oltre la data "Non dopo"' },
          { term: 'Revocato', description: 'Esplicitamente revocato (pubblicato nella CRL)' },
          { term: 'Orfano', description: 'La CA emittente non esiste più nel sistema' },
          { term: 'Archiviato', description: 'Sostituito da un rinnovo o da una re-iscrizione che ha conservato il vecchio record per la cronologia (SCEP, EST, WSTEP, ACME, responder OCSP); elencato con il filtro di stato "Archiviato"' },
        ]
      },
      {
        title: 'Azioni',
        items: [
          { label: 'Emetti', text: 'Crea un nuovo certificato firmato da una delle tue CA' },
          { label: 'Importa', text: 'Importa un certificato esistente (PEM, DER o PKCS#12)' },
          { label: 'Rinnova', text: 'In loco dalla v2.214: stessi id/refid, nuovo numero di serie e nuova validità, il numero di serie sostituito resta nella CRL fino alla vecchia scadenza. Un certificato revocato non può essere rinnovato. Chiede la validità del nuovo certificato in giorni, precompilata con la durata attuale; le policy e la scadenza della CA la limitano comunque' },
          { label: 'Rinomina', text: 'Imposta un nome visualizzato indipendente dal CN (predefinito: il CN o il primo nome DNS SAN per i certificati senza CN)' },
          { label: 'Revoca', text: 'Segna come revocato con un motivo, apparirà nella CRL' },
          { label: 'Rimuovi sospensione', text: 'Riattiva un certificato revocato con motivo "Sospensione certificato", ripristina lo stato valido' },
          { label: 'Revoca e sostituisci', text: 'Revoca e riemetti immediatamente un sostituto' },
          { label: 'Esporta', text: 'Scarica in formato PEM, DER, PKCS#12 o JKS' },
          { label: 'Modalità compatibilità PKCS#12 (v2.222)', text: 'Le finestre di esportazione offrono un profilo 3DES/SHA-1 per gli importatori che rifiutano l\'archivio AES-256 predefinito come password errata: Android 15 e precedenti, macOS 14 e precedenti, Windows Server 2016 e precedenti, Java datato. Disattivato per impostazione predefinita, protegge meno il file' },
          { label: 'Confronta', text: 'Confronto affiancato di due certificati' },
          { label: 'Altre estensioni (v2.251)', text: 'I dettagli di certificati e CA elencano sotto Altre estensioni quelle per cui UCM non ha una sezione, con OID, nome se noto, criticità e valore grezzo. Il modulo di emissione può aggiungere estensioni personalizzate a quelle del modello' },
          { label: 'Chiavi compromesse (v2.251)', text: 'Una chiave revocata come keyCompromise resta nota dopo l\'eliminazione del suo certificato, qualunque CA l\'abbia emesso, Let\'s Encrypt compresa: una richiesta, un rinnovo o una finalizzazione con quella chiave viene rifiutata' },
          { label: 'Certificati del client ACME (v2.251)', text: 'Anche un certificato ottenuto dal client ACME viene rinnovato sul posto, mantenendo id e refid. Le copie che i rinnovi precedenti avevano importato come nuove righe restano nell\'inventario finché non vengono archiviate o eliminate' },
        ]
      },
      {
        title: 'EKU extra personalizzati (RFC 5280 §4.2.1.12)',
        content: 'Il modulo di emissione e la modale di firma CSR espongono un selettore multiplo "EKU extra" che aggiunge OID Extended Key Usage oltre ai default del tipo di certificato:',
        items: [
          { label: 'Catalogo', text: '18 EKU noti (Microsoft RDP 1.3.6.1.4.1.311.54.1.2, smartcard logon, document signing, IPsec, Kerberos PKINIT, ecc.)' },
          { label: 'OID libero', text: 'Qualsiasi OID puntato ben formato conforme a ^[0-2](?:\\.(?:0|[1-9]\\d*)){1,15}$' },
          { label: 'Limite', text: 'Fino a 16 OID totali per certificato' },
          { label: 'Fusione, mai sostituzione', text: 'Gli EKU di default del tipo (es. serverAuth) restano bloccati, gli extra si aggiungono sopra' },
          { label: 'Rifiutato', text: 'anyExtendedKeyUsage (2.5.29.37.0) è esplicitamente vietato' },
        ]
      },
      {
        title: 'Coppie di certificati ibridi (RFC 9763)',
        content: 'Un certificato classico (A) e uno ML-DSA (B) per lo stesso soggetto, collegati: B contiene l\'estensione relatedCertificate che indica A tramite il suo hash. I client che conoscono ML-DSA verificano entrambi; gli altri continuano a usare A.',
        items: [
          { label: 'Emissione', text: 'Seleziona "Emetti una coppia ibrida (RFC 9763)" nel modulo di emissione del certificato e scegli la chiave classica e il livello ML-DSA; entrambi provengono dalla stessa CA, con lo stesso soggetto, gli stessi nomi e la stessa validità, e B non dichiara alcun key usage o EKU assente in A. Proposto solo se le policy della CA consentono entrambi, mai in modalità FIPS. Con i profili ANSSI, BSI ed EU ACM, ML-DSA-65 e ML-DSA-87 sono proposti solo nella coppia. Una policy che richiede approvazione rifiuta per ora la coppia' },
          { label: 'Collegamento tramite richiesta', text: 'Un CSR con una relatedCertRequest firmata dalla chiave di A (Firma CSR, ACME, EST, WSTEP) emette un B collegato ad A. A deve essere conservato qui, valido, non revocato e un certificato end-entity; un B più recente che indica lo stesso A subentra nella coppia' },
          { label: 'Collegato', text: 'Ogni membro mostra un badge Collegato nell\'elenco e nei dettagli, con un link che apre l\'altro membro' },
          { label: 'Revoca', text: 'Revocare un membro, singolarmente o in blocco, revoca anche l\'altro a meno che tu non deselezioni "Revoca anche il certificato collegato", ad esempio per mantenere A quando è compromessa solo la chiave ML-DSA; con una policy che richiede approvazione, i due vanno insieme. Un avviso indica l\'altro membro quando non è stato possibile revocarlo. La revoca ACME revoca solo il certificato presentato' },
          { label: 'Rinnovo', text: 'Rinnovare uno dei due membri rinnova entrambi, manualmente, in blocco o automaticamente, e il nuovo B indica il nuovo A. Un membro rinnovato da solo, mentre l\'altro è revocato, esce dalla coppia' },
          { label: 'Esportazione', text: 'Il formato Bundle ibrido scarica un file ZIP con entrambi i certificati, e con entrambe le chiavi quando includi la chiave e puoi esportare le chiavi' },
        ]
      },
      {
        title: 'File certificato su disco (v2.140)',
        items: [
          { label: 'Auto-materializzati', text: 'I file .crt / .key vengono scritti sotto data/certs/ per ogni percorso di creazione (UI, firma CSR, ACME, SCEP, import)' },
          { label: 'Anche le CA', text: 'I file .crt / .key delle CA vengono scritti sotto data/cas/ con lo stesso meccanismo' },
          { label: 'Rete di sicurezza', text: 'Una scansione di rigenerazione all\'avvio ricostruisce qualsiasi file mancante dal database' },
          { label: 'Non bloccante', text: 'Gli errori di scrittura vengono loggati ma non interrompono mai la transazione DB' },
        ]
      },
      {
        title: 'Distribuzione (v2.215)',
        content: 'Invia questo certificato a host remoti via SSH/SFTP, solo admin, le destinazioni si gestiscono in Impostazioni › Distribuzione.',
        items: [
          { label: 'Associa destinazione', text: 'Dalla vista di dettaglio del certificato: scegli una destinazione di distribuzione e imposta i percorsi di destinazione assoluti per certificato, chiave privata e/o catena completa (almeno uno). La catena completa omette la CA root a meno che Includi CA radice sia selezionato' },
          { label: 'Stesso host', text: 'Per distribuire sullo stesso host UCM, usa una destinazione SFTP su 127.0.0.1 con un account SSH dedicato; il servizio isolato non può scrivere fuori dalla directory dei dati' },
          { label: 'Automatico', text: 'All\'emissione e al rinnovo, i file associati vengono inviati di nuovo e viene eseguito il comando di ricarica opzionale di quella distribuzione; le consegne sono messe in coda con tentativi' },
          { label: 'File', text: 'Scritti in modo atomico esattamente nei percorsi configurati (la directory padre deve esistere): chiave 0600, certificato/catena 0644' },
          { label: 'Distribuisci ora', text: 'Invio manuale dalla vista di dettaglio, con lo stato di consegna e l\'ultimo errore mostrati per destinazione' },
        ]
      },

    ],
    tips: [
      'Aggiungi la stella ⭐ ai certificati importanti per inserirli nella lista dei preferiti',
      'Usa i filtri per trovare rapidamente i certificati per stato, CA o testo di ricerca: la selezione viene conservata al ricaricamento della pagina',
      'Il rinnovo conserva lo stesso record (id, refid, data di creazione): le chiavi detenute da UCM vengono rigenerate, i certificati registrati via protocollo (SCEP/EST/ACME) mantengono la loro chiave lato client',
      'Serve un EKU non standard (Microsoft RDP, smartcard logon, document signing)? Aggiungilo via "EKU extra" invece di modificare i template',
      'Quando una policy o la scadenza della CA emittente accorcia la validità richiesta, il risultato lo indica: "Issued for N day(s) instead of the M requested", con il motivo',
      'Una firma RSA-PSS viene mostrata con il suo hash e la lunghezza del salt, ad es. RSASSA-PSS SHA-256 (salt 32)',
    ],
    warnings: [
      'La revoca è generalmente permanente: tranne per "Sospensione certificato" che può essere rimossa',
      'Un certificato valido e non revocato non può essere eliminato direttamente: Elimina ne spiega il motivo e propone "Revoca, poi elimina", così la revoca raggiunge CRL/OCSP; le revoche sopravvivono all\'eliminazione',
      'UCM firma solo con SHA-256, SHA-384 o SHA-512: SHA-224 e i nomi di hash sconosciuti vengono rifiutati invece di essere sostituiti da SHA-256',
    ],
  },
  helpGuides: {
    title: 'Certificati',
    content: `
## Panoramica

Gestione centralizzata di tutti i certificati X.509. Emetti nuovi certificati, importa quelli esistenti, monitora le date di scadenza, gestisci rinnovi e revoche.

## Stato del certificato

- **Valido**: Entro il periodo di validità e non revocato
- **In scadenza**: Scadrà entro 30 giorni (configurabile)
- **Scaduto**: Oltre la data "Non dopo"
- **Revocato**: Esplicitamente revocato, pubblicato nella CRL
- **Orfano**: La CA emittente non esiste più in UCM
- **Archiviato**: Sostituito da un rinnovo o da una re-iscrizione che ha conservato il vecchio record per la cronologia (SCEP, EST, WSTEP, ACME, responder OCSP)

## Emissione di un certificato

1. Clicca **Emetti certificato**
2. Seleziona la **CA firmataria** (deve avere una chiave privata)
3. Compila il Soggetto (CN è obbligatorio, altri campi opzionali)
4. Aggiungi Subject Alternative Names (SAN): nomi DNS, IP, email
5. Scegli il tipo e la dimensione della chiave
6. Imposta il periodo di validità
7. Facoltativamente applica un **Template** per precompilare le impostazioni
8. Clicca **Emetti**

### Utilizzo dei template
I template precompilano Key Usage, Extended Key Usage, valori predefiniti del soggetto e validità. Seleziona un template prima di compilare il modulo per risparmiare tempo.

## Importazione di certificati

Formati supportati:
- **PEM**: Certificati singoli o in bundle
- **DER**: Formato binario
- **PKCS#12 (P12/PFX)**: Certificato + chiave + catena (password richiesta)
- **PKCS#7 (P7B)**: Catena di certificati senza chiavi

## Rinnovo di un certificato

Dalla v2.214, il rinnovo aggiorna il certificato **in loco**:
- Stesso record: **id, refid e data di creazione non cambiano mai**: le integrazioni mantengono i loro riferimenti
- Stessi Soggetto e SAN; nuovo numero di serie e nuovo periodo di validità
- I certificati la cui chiave è detenuta da UCM vengono **rigenerati con una nuova chiave**; i certificati registrati via protocollo (SCEP/EST/ACME) vengono rifirmati con la loro chiave pubblica esistente
- Il **numero di serie sostituito resta pubblicato nella CRL** (motivo \`superseded\`) e risponde \`revoked\` via OCSP fino alla scadenza originale del vecchio certificato
- \`renewed_at\` / \`renewed_times\` tracciano la cronologia dei rinnovi
- Un certificato revocato non può essere rinnovato (409): emettine invece uno nuovo
- **Rinnova** chiede la validità del nuovo certificato in giorni, precompilata con la durata attuale; le policy di emissione e la scadenza della CA la limitano comunque

**Eliminazione**: un certificato valido e non revocato non può essere eliminato direttamente: **Elimina** ne spiega il motivo e propone **Revoca, poi elimina**, così le relying party vedono il cambiamento. Le revoche sono persistite indipendentemente dal record del certificato e sopravvivono all'eliminazione.

## Revoca di un certificato

1. Seleziona il certificato → **Revoca**
2. Scegli un motivo di revoca (Compromissione chiave, Compromissione CA, Cambio affiliazione, Sostituzione, Cessazione dell'attività, Sospensione certificato, ecc.)
3. Conferma la revoca

I certificati revocati vengono pubblicati nella CRL alla prossima rigenerazione.

> ⚠ La revoca è generalmente permanente: tranne per **Sospensione certificato** che può essere rimossa.

### Rimozione sospensione

Se un certificato è stato revocato con il motivo **Sospensione certificato**, può essere ripristinato allo stato valido:

1. Apri i dettagli del certificato revocato
2. Il pulsante **Rimuovi sospensione** appare nella barra delle azioni (solo per revoche con Sospensione certificato)
3. Clicca **Rimuovi sospensione** per ripristinare il certificato
4. Il certificato torna allo stato valido, la CRL viene rigenerata e la cache OCSP viene aggiornata

> 💡 La Sospensione certificato è utile per sospensioni temporanee (es. dispositivo smarrito, indagine in corso).

### Revoca e sostituzione
Combina la revoca con la riemissione immediata. Il nuovo certificato eredita lo stesso Soggetto e SAN.

## Esportazione dei certificati

Formati di esportazione:
- **PEM**: Solo certificato
- **PEM + Catena**: Certificato con le sue CA emittenti (**Includi catena CA**); la CA root viene aggiunta solo se **Includi CA radice** è selezionato
- **DER**: Formato binario
- **PKCS#12**: Certificato + chiave + catena, protetto da password

## Coppie di certificati ibridi (RFC 9763)

Una coppia ibrida collega un certificato classico (**A**, RSA o EC) e uno post-quantistico (**B**, ML-DSA) per lo stesso soggetto. B contiene l'estensione non critica **relatedCertificate**, che indica A tramite il suo hash, così una parte fidata può richiederli entrambi.

- **Emissione**: seleziona **Emetti una coppia ibrida (RFC 9763)** nel modulo di emissione del certificato (oppure invia \`hybrid\` in \`POST /api/v2/certificates\`) per emettere entrambi dalla stessa CA, con lo stesso soggetto, gli stessi nomi e la stessa validità. B copia le estensioni di A con un proprio key identifier e key usage, e non dichiara alcun key usage o EKU assente in A. Con i profili di conformità ANSSI, BSI ed EU ACM, ML-DSA-65 e ML-DSA-87 sono accettati solo come B: mai da soli, e ML-DSA-44 per niente
- **Collegamento tramite richiesta**: un CSR con una **relatedCertRequest** firmata dalla chiave di A emette un B collegato ad A, tramite Firma CSR, ACME, EST o WSTEP. A deve essere conservato da UCM, valido, non revocato, un certificato end-entity emesso da una CA di questa istanza la cui catena è valida ora, e la richiesta deve avere al massimo 7 giorni. Un certificato più recente che indica lo stesso A subentra nella coppia, e il precedente la lascia. Un certificato fornito inline nella posizione della richiesta deve essere A; le altre posizioni non vengono scaricate
- **Revoca** di uno dei due membri, singolarmente o in blocco, revoca anche l'altro, a meno che **Revoca anche il certificato collegato** non sia deselezionato. Con una policy che richiede approvazione, la coppia va insieme, e due policy di approvazione diverse sui due membri lasciano la revoca a un amministratore. Se l'altro membro non può essere revocato, la risposta lo segnala (\`related_not_revoked\`) e va revocato separatamente. ACME revokeCert revoca solo il certificato presentato (RFC 8555)
- **Rinnovo** di uno dei due membri, manuale, in blocco o automatico, rinnova entrambi, e il nuovo B indica il nuovo A. Un membro rinnovato da solo, mentre l'altro è revocato, esce dalla coppia, come l'altro membro quando uno dei due viene eliminato
- **Esportazione**: il formato **hybrid-bundle** è un file ZIP con entrambi i certificati, e con entrambe le chiavi private quando la chiave è inclusa; viene rifiutato quando nessuno dei due certificati indica più l'altro

> ⚠ Una policy che richiede approvazione rifiuta per ora di emettere una coppia ibrida: emettila con una policy senza approvazione.

## Preferiti

Aggiungi la stella ⭐ ai certificati importanti per aggiungerli ai segnalibri. I preferiti appaiono per primi nelle viste filtrate e sono accessibili dal filtro preferiti.

## Confronto certificati

Seleziona due certificati e clicca **Confronta** per vedere un confronto affiancato di Soggetto, SAN, Key Usage, validità ed estensioni.

## Filtri e ricerca

- **Filtro per stato**: Valido, In scadenza, Scaduto, Revocato, Orfano, Archiviato
- **Filtro per CA**: Mostra i certificati di una CA specifica
- **Filtro per origine**: Filtra in base a come il certificato è entrato in UCM (emesso, importato, ACME, SCEP, ecc.)
- **Filtro per template**: Trova i certificati **modificati dal template**: emessi da un template ma con tipo di chiave, validità o digest esplicitamente sovrascritti al momento della richiesta. I campi divergenti sono elencati nel dettaglio del certificato; il record è congelato all'emissione
- **Ricerca testuale**: Cerca per CN, numero di serie o SAN
- **Ordinamento**: Per nome, data di scadenza, data di creazione, stato
## Analisi di conformità

L'azione **Analizza** (dettaglio del certificato) verifica la conformità agli standard X.509. Solo informativo.

- **RFC 5280**: profilo X.509 IETF, sempre rilevante
- **CA/Browser Forum**: Baseline Requirements per certificati TLS pubblici (rumore atteso su PKI interna)
- Gravità: fatal / error / warning / notice / info
- Motore: pkilint (+ zlint se presente): dipendenza server opzionale, degradazione graziosa se assente

`
  }
}
