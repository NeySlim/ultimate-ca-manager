export default {
  helpContent: {
    title: 'CRL e OCSP',
    subtitle: 'Servizi di revoca dei certificati',
    overview: 'Gestisci le Liste di revoca dei certificati (CRL) e i servizi del protocollo OCSP (Online Certificate Status Protocol). Questi servizi consentono ai client di verificare se un certificato è stato revocato.',
    sections: [
      {
        title: 'Gestione CRL',
        items: [
          { label: 'Rigenerazione automatica', text: 'Attiva/disattiva la rigenerazione automatica delle CRL per ogni CA' },
          { label: 'Rigenerazione manuale', text: 'Forza la rigenerazione immediata della CRL' },
          { label: 'Scarica CRL', text: 'Scarica il file CRL in formato DER o PEM' },
          { label: 'Distribuzione CRL', text: 'Associa una destinazione SSH/SFTP per inviare automaticamente ogni CRL rigenerata. Ogni associazione definisce il formato PEM o DER, il percorso di destinazione, le CRL padre opzionali e il proprio comando di ricarica' },
          { label: 'URL CDP', text: 'URL del CRL Distribution Point da incorporare nei certificati' },
          { label: 'Validità', text: 'Validità della CRL per CA da 1 giorno fino a 5 anni (90d/180d/1y/3y/5y per le CA offline che non possono rifirmare secondo pianificazione). Oltre un anno appare un avviso, le relying party possono conservare dati di revoca obsoleti per l\'intera finestra' },
          { label: 'CRL esterna', text: 'Le CA senza chiave/offline non possono autofirmare una CRL, carica dal pannello di dettaglio della CA una CRL generata accanto alla chiave offline; viene validata (firma, emittente, monotonicità) e servita allo stesso URL CDP (v2.215)' },
        ]
      },
      {
        title: 'Servizio OCSP',
        items: [
          { label: 'Stato', text: 'Indica se il risponditore OCSP è attivo per ogni CA' },
          { label: 'URL AIA', text: 'URL Authority Information Access, endpoint del risponditore OCSP e download del certificato CA Issuers incorporati nei certificati emessi' },
          { label: 'Cache', text: 'Cache delle risposte con pulizia automatica giornaliera delle voci scadute' },
          { label: 'Query totali', text: 'Numero di richieste OCSP elaborate' },
          { label: 'Risponditore delegato', text: 'Firma le risposte con un certificato OCSPSigning dedicato invece della chiave della CA, assegnane uno per CA dal pannello di dettaglio' },
          { label: 'Rinnovo automatico del risponditore', text: 'Un task giornaliero riemette il certificato del risponditore delegato prima della scadenza (stessa coppia di chiavi, rinnovato alla pari) e lo ricollega, abilitato per impostazione predefinita' },
        ]
      },
    ],
    tips: [
      'Abilita la rigenerazione automatica per mantenere le CRL aggiornate dopo le revoche dei certificati',
      'Copia gli URL CDP, OCSP e AIA CA Issuers per incorporarli nei tuoi profili certificato',
      'OCSP fornisce il controllo della revoca in tempo reale ed è preferito rispetto alla CRL',
    ],
  },
  helpGuides: {
    title: 'CRL e OCSP',
    content: `
## Panoramica

Le Liste di revoca dei certificati (CRL) e il protocollo OCSP (Online Certificate Status Protocol) consentono ai client di verificare se un certificato è stato revocato. UCM supporta entrambi i meccanismi.

## Gestione CRL

### Cos'è una CRL?
Una CRL è un elenco firmato di numeri di serie di certificati revocati, pubblicato da una CA. I client scaricano la CRL e verificano se il numero di serie di un certificato vi compare.

### CRL per CA
Ogni CA ha la propria CRL. L'elenco CRL mostra tutte le tue CA con:
- **Conteggio revocati**: Numero di certificati nella CRL
- **Ultima rigenerazione**: Quando la CRL è stata ricostruita l'ultima volta
- **Rigenerazione automatica**: Se gli aggiornamenti automatici della CRL sono abilitati

### Rigenerazione di una CRL
Clicca **Rigenera** per ricostruire immediatamente la CRL di una CA. Utile dopo la revoca di certificati.

### Rigenerazione automatica
Abilita la rigenerazione automatica per ricostruire automaticamente la CRL ogni volta che un certificato viene revocato. Attivabile per ogni CA.

### Validità della CRL
La pianificazione CRL (per CA) definisce per quanto tempo ogni CRL pubblicata rimane valida. Le opzioni vanno da **1 giorno a 5 anni**: 1d, 2d, 3d, 7d, 14d, 30d, 90d, 180d, 1y, 3y, 5y.

- Le **CA online** dovrebbero mantenere una validità breve (giorni) così le relying party recepiscono rapidamente le revoche
- Le **CA offline** (tipicamente una root che non può rifirmare le CRL secondo pianificazione) sono il caso d'uso previsto per le opzioni lunghe: da 90d fino a 5y
- Oltre un anno viene mostrato un avviso: le relying party possono conservare dati di revoca obsoleti per l'intera finestra di validità

### CRL Distribution Point (CDP)
L'URL CDP viene incorporato nei certificati in modo che i client sappiano dove scaricare la CRL. Copia l'URL dai dettagli della CRL.

\`\`\`
http://your-server:8080/cdp/{ca_refid}.crl
\`\`\`

> 💡 **Abilitazione automatica**: quando crei una nuova CA, il CDP viene abilitato automaticamente se è configurato un URL Base protocollo o un server di protocollo HTTP. L'URL CDP viene generato automaticamente, nessun passaggio manuale necessario.

> ⚠️ **Importante**: gli URL vengono generati automaticamente utilizzando la porta del protocollo HTTP e l'FQDN del server. Se accedi a UCM tramite \`localhost\`, l'URL non può essere generato. Configura prima il tuo **FQDN** o l'**URL Base protocollo** in Impostazioni → Generale.

### Download delle CRL
Scarica le CRL in formato DER o PEM per la distribuzione ai client o l'integrazione con altri sistemi.

## Risponditore OCSP

### Cos'è OCSP?
OCSP fornisce il controllo dello stato dei certificati in tempo reale. Invece di scaricare un'intera CRL, i client inviano una query per un certificato specifico e ottengono una risposta immediata.

### Stato OCSP
La sezione OCSP mostra:
- **Stato del risponditore**: Attivo o inattivo per ogni CA
- **Query totali**: Numero di richieste OCSP elaborate
- **Cache**: Cache delle risposte con pulizia automatica giornaliera delle voci scadute

### Cache OCSP

UCM memorizza nella cache le risposte OCSP per le prestazioni. La cache è:
- **Pulita automaticamente**: Le risposte scadute vengono eliminate quotidianamente dallo scheduler
- **Invalidata alla revoca**: Quando un certificato viene revocato, la sua risposta OCSP in cache viene immediatamente cancellata
- **Invalidata alla rimozione della sospensione**: Quando una Sospensione certificato viene rimossa, la cache OCSP viene aggiornata

### Risponditore OCSP delegato

Per impostazione predefinita, le risposte OCSP sono firmate con la chiave della CA stessa. Un **risponditore delegato** usa invece un certificato dedicato con l'EKU **OCSPSigning**: assegnane uno per CA dal pannello di dettaglio della CA (sono idonei solo i certificati con EKU OCSPSigning e chiave privata).

**Rinnovo automatico**: un task giornaliero riemette il certificato del risponditore prima della scadenza, stessa coppia di chiavi ed estensioni, rinnovato alla pari, e ricollega la configurazione del risponditore della CA al nuovo certificato. I certificati di firma OCSP a vita breve (es. un template di 90 giorni) ruotano senza intervento manuale. Abilitato per impostazione predefinita; può essere disabilitato e la finestra di rinnovo regolata in Impostazioni › Sicurezza.

### URL AIA
L'estensione Authority Information Access (AIA) viene incorporata nei certificati per indicare ai client dove trovare:

**Risponditore OCSP**: controllo della revoca in tempo reale:
\`\`\`
http://your-server:8080/ocsp
\`\`\`

**CA Issuers** (RFC 5280 §4.2.2.1): scarica il certificato della CA emittente per la costruzione della catena:
\`\`\`
http://your-server:8080/ca/{ca_refid}.cer   (formato DER)
http://your-server:8080/ca/{ca_refid}.pem   (formato PEM)
\`\`\`

Abilita CA Issuers per ogni CA nella sezione **AIA CA Issuers** del pannello dei dettagli. L'URL viene generato automaticamente utilizzando il server del protocollo HTTP e l'FQDN configurato.

> ⚠️ **Prerequisito**: gli URL del protocollo (CDP, OCSP, AIA) richiedono un **FQDN** valido o un **URL Base protocollo** configurato in Impostazioni → Generale. Se accedi a UCM tramite \`localhost\`, l'abilitazione di queste funzionalità fallirà, imposta prima l'FQDN.

### OCSP vs CRL

| Caratteristica | CRL | OCSP |
|---------|-----|------|
| Frequenza aggiornamento | Periodica | Tempo reale |
| Larghezza di banda | Elenco completo ogni volta | Singola query |
| Privacy | Nessun tracciamento | Il server vede le query |
| Supporto offline | Sì (in cache) | Richiede connettività |

> 💡 Best practice: abilita sia CRL che OCSP per la massima compatibilità.
`
  }
}
