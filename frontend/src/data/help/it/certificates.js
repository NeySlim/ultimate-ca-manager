export default {
  helpContent: {
    title: 'Certificati',
    subtitle: 'Emetti, gestisci e monitora i certificati',
    overview: 'Gestione centralizzata di tutti i certificati X.509. Emetti nuovi certificati dalle tue CA, importa quelli esistenti, monitora le date di scadenza e gestisci rinnovi e revoche.',
    sections: [
      {
        title: "Analisi di conformità",
        content: "L'azione « Analizza » nel dettaglio di un certificato lo passa attraverso linter di standard e mostra i risultati. Solo informativo — non blocca mai l'emissione.",
        items: [
          { label: "Profili", text: "RFC 5280 (sempre rilevante) e CA/Browser Forum Baseline Requirements (certificati TLS server)" },
          { label: "Gravità", text: "I risultati sono classificati: fatal, error, warning, notice, info" },
          { label: "Motore", text: "Basato su pkilint (e zlint se il suo binario è presente) — dipendenza opzionale del server" },
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
          { label: 'Rinnova', text: 'In loco dalla v2.214: stessi id/refid, nuovo numero di serie e nuova validità — il numero di serie sostituito resta nella CRL fino alla vecchia scadenza. Un certificato revocato non può essere rinnovato' },
          { label: 'Rinomina', text: 'Imposta un nome visualizzato indipendente dal CN (predefinito: il CN o il primo nome DNS SAN per i certificati senza CN)' },
          { label: 'Revoca', text: 'Segna come revocato con un motivo — apparirà nella CRL' },
          { label: 'Rimuovi sospensione', text: 'Riattiva un certificato revocato con motivo "Sospensione certificato" — ripristina lo stato valido' },
          { label: 'Revoca e sostituisci', text: 'Revoca e riemetti immediatamente un sostituto' },
          { label: 'Esporta', text: 'Scarica in formato PEM, DER, PKCS#12 o JKS' },
          { label: 'Modalità compatibilità PKCS#12 (v2.222)', text: 'Le finestre di esportazione offrono un profilo 3DES/SHA-1 per gli importatori che rifiutano l\'archivio AES-256 predefinito come password errata: Android 15 e precedenti, macOS 14 e precedenti, Windows Server 2016 e precedenti, Java datato. Disattivato per impostazione predefinita, protegge meno il file' },
          { label: 'Confronta', text: 'Confronto affiancato di due certificati' },
        ]
      },
      {
        title: 'EKU extra personalizzati (RFC 5280 §4.2.1.12)',
        content: 'Il modulo di emissione e la modale di firma CSR espongono un selettore multiplo "EKU extra" che aggiunge OID Extended Key Usage oltre ai default del tipo di certificato:',
        items: [
          { label: 'Catalogo', text: '18 EKU noti (Microsoft RDP 1.3.6.1.4.1.311.54.1.2, smartcard logon, document signing, IPsec, Kerberos PKINIT, ecc.)' },
          { label: 'OID libero', text: 'Qualsiasi OID puntato ben formato conforme a ^[0-2](?:\\.(?:0|[1-9]\\d*)){1,15}$' },
          { label: 'Limite', text: 'Fino a 16 OID totali per certificato' },
          { label: 'Fusione, mai sostituzione', text: 'Gli EKU di default del tipo (es. serverAuth) restano bloccati — gli extra si aggiungono sopra' },
          { label: 'Rifiutato', text: 'anyExtendedKeyUsage (2.5.29.37.0) è esplicitamente vietato' },
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
        content: 'Invia questo certificato a host remoti via SSH/SFTP — solo admin, le destinazioni si gestiscono in Impostazioni › Distribuzione.',
        items: [
          { label: 'Associa destinazione', text: 'Dalla vista di dettaglio del certificato: scegli una destinazione di distribuzione e imposta i percorsi di destinazione assoluti per certificato, chiave privata e/o catena completa (almeno uno)' },
          { label: 'Stesso host', text: 'Per distribuire sullo stesso host UCM, usa una destinazione SFTP su 127.0.0.1 con un account SSH dedicato; il servizio isolato non può scrivere fuori dalla directory dei dati' },
          { label: 'Automatico', text: 'All\'emissione e al rinnovo, i file associati vengono inviati di nuovo e viene eseguito il comando di ricarica della destinazione — le consegne sono messe in coda con tentativi' },
          { label: 'File', text: 'Scritti in modo atomico esattamente nei percorsi configurati (la directory padre deve esistere): chiave 0600, certificato/catena 0644' },
          { label: 'Distribuisci ora', text: 'Invio manuale dalla vista di dettaglio, con lo stato di consegna e l\'ultimo errore mostrati per destinazione' },
        ]
      },

    ],
    tips: [
      'Aggiungi la stella ⭐ ai certificati importanti per inserirli nella lista dei preferiti',
      'Usa i filtri per trovare rapidamente i certificati per stato, CA o testo di ricerca — la selezione viene conservata al ricaricamento della pagina',
      'Il rinnovo conserva lo stesso record (id, refid, data di creazione) — le chiavi detenute da UCM vengono rigenerate, i certificati registrati via protocollo (SCEP/EST/ACME) mantengono la loro chiave lato client',
      'Serve un EKU non standard (Microsoft RDP, smartcard logon, document signing)? Aggiungilo via "EKU extra" invece di modificare i template',
    ],
    warnings: [
      'La revoca è generalmente permanente — tranne per "Sospensione certificato" che può essere rimossa',
      'Un certificato valido e non revocato non può essere eliminato (409) — revocalo prima affinché la revoca raggiunga CRL/OCSP; le revoche sopravvivono all\'eliminazione',
    ],
  },
  helpGuides: {
    title: 'Certificati',
    content: `
## Panoramica

Gestione centralizzata di tutti i certificati X.509. Emetti nuovi certificati, importa quelli esistenti, monitora le date di scadenza, gestisci rinnovi e revoche.

## Stato del certificato

- **Valido** — Entro il periodo di validità e non revocato
- **In scadenza** — Scadrà entro 30 giorni (configurabile)
- **Scaduto** — Oltre la data "Non dopo"
- **Revocato** — Esplicitamente revocato, pubblicato nella CRL
- **Orfano** — La CA emittente non esiste più in UCM
- **Archiviato** — Sostituito da un rinnovo o da una re-iscrizione che ha conservato il vecchio record per la cronologia (SCEP, EST, WSTEP, ACME, responder OCSP)

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
- **PEM** — Certificati singoli o in bundle
- **DER** — Formato binario
- **PKCS#12 (P12/PFX)** — Certificato + chiave + catena (password richiesta)
- **PKCS#7 (P7B)** — Catena di certificati senza chiavi

## Rinnovo di un certificato

Dalla v2.214, il rinnovo aggiorna il certificato **in loco**:
- Stesso record: **id, refid e data di creazione non cambiano mai** — le integrazioni mantengono i loro riferimenti
- Stessi Soggetto e SAN; nuovo numero di serie e nuovo periodo di validità
- I certificati la cui chiave è detenuta da UCM vengono **rigenerati con una nuova chiave**; i certificati registrati via protocollo (SCEP/EST/ACME) vengono rifirmati con la loro chiave pubblica esistente
- Il **numero di serie sostituito resta pubblicato nella CRL** (motivo \`superseded\`) e risponde \`revoked\` via OCSP fino alla scadenza originale del vecchio certificato
- \`renewed_at\` / \`renewed_times\` tracciano la cronologia dei rinnovi
- Un certificato revocato non può essere rinnovato (409) — emettine invece uno nuovo

**Eliminazione**: un certificato valido e non revocato non può essere eliminato (409) — revocalo prima affinché le relying party vedano il cambiamento. Le revoche sono persistite indipendentemente dal record del certificato e sopravvivono all'eliminazione.

## Revoca di un certificato

1. Seleziona il certificato → **Revoca**
2. Scegli un motivo di revoca (Compromissione chiave, Compromissione CA, Cambio affiliazione, Sostituzione, Cessazione dell'attività, Sospensione certificato, ecc.)
3. Conferma la revoca

I certificati revocati vengono pubblicati nella CRL alla prossima rigenerazione.

> ⚠ La revoca è generalmente permanente — tranne per **Sospensione certificato** che può essere rimossa.

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
- **PEM** — Solo certificato
- **PEM + Catena** — Certificato con catena completa dell'emittente
- **DER** — Formato binario
- **PKCS#12** — Certificato + chiave + catena, protetto da password

## Preferiti

Aggiungi la stella ⭐ ai certificati importanti per aggiungerli ai segnalibri. I preferiti appaiono per primi nelle viste filtrate e sono accessibili dal filtro preferiti.

## Confronto certificati

Seleziona due certificati e clicca **Confronta** per vedere un confronto affiancato di Soggetto, SAN, Key Usage, validità ed estensioni.

## Filtri e ricerca

- **Filtro per stato** — Valido, In scadenza, Scaduto, Revocato, Orfano, Archiviato
- **Filtro per CA** — Mostra i certificati di una CA specifica
- **Filtro per origine** — Filtra in base a come il certificato è entrato in UCM (emesso, importato, ACME, SCEP, ecc.)
- **Filtro per template** — Trova i certificati **modificati dal template**: emessi da un template ma con tipo di chiave, validità o digest esplicitamente sovrascritti al momento della richiesta. I campi divergenti sono elencati nel dettaglio del certificato; il record è congelato all'emissione
- **Ricerca testuale** — Cerca per CN, numero di serie o SAN
- **Ordinamento** — Per nome, data di scadenza, data di creazione, stato
## Analisi di conformità

L'azione **Analizza** (dettaglio del certificato) verifica la conformità agli standard X.509. Solo informativo.

- **RFC 5280** — profilo X.509 IETF, sempre rilevante
- **CA/Browser Forum** — Baseline Requirements per certificati TLS pubblici (rumore atteso su PKI interna)
- Gravità: fatal / error / warning / notice / info
- Motore: pkilint (+ zlint se presente) — dipendenza server opzionale, degradazione graziosa se assente

`
  }
}
