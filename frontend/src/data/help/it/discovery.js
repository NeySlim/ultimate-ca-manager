export default {
  helpContent: {
    title: 'Rilevamento certificati',
    subtitle: 'Trova i certificati TLS sulla tua rete',
    overview: 'Scansiona la tua rete per trovare i certificati TLS distribuiti su server ed endpoint e confrontarli con l\'inventario della tua PKI gestita. Individua i certificati non tracciati, rileva i cambiamenti e sorveglia i certificati in scadenza fuori dal controllo di UCM.',
    sections: [
      {
        title: 'Schede',
        items: [
          { label: 'Rilevati', text: 'Tutti i certificati trovati dalle scansioni, con stato, scadenza e dettagli dell\'endpoint' },
          { label: 'Profili', text: 'Configurazioni di scansione salvate, target, porte, pianificazione, notifiche' },
          { label: 'Cronologia', text: 'Esecuzioni di scansione passate con durata, target scansionati e certificati trovati' },
        ]
      },
      {
        title: 'Scansione',
        items: [
          { label: 'Scansione rapida', text: 'Scansione ad-hoc senza salvare un profilo, inserisci target e porte, i risultati arrivano in tempo reale' },
          { label: 'Target', text: 'Inseriti come tag, uno per target: hostname, IP, sottorete CIDR (192.168.1.0/24) o host:porta (10.0.0.1:8443)' },
          { label: 'Porte', text: 'Porte TCP separate da virgole (es. 443, 8443, 636), oppure il preset delle porte comuni' },
          { label: 'Opzioni avanzate', text: 'Risoluzione DNS inversa (record PTR), timeout e concorrenza' },
          { label: 'Pianificazione', text: 'I profili si eseguono manualmente o automaticamente ogni 1h / 6h / 12h / 24h / 7g' },
          { label: 'Notifiche', text: 'Avvisi email per nuovi certificati, cambiamenti dei certificati o scadenze imminenti. Un certificato trovato tramite SNI su un target IP è contato come nuovo a ogni scansione' },
        ]
      },
      {
        title: 'Stati dei risultati',
        items: [
          { label: 'Gestito', text: 'L\'impronta SHA-256 del certificato corrisponde a un certificato nell\'inventario di UCM' },
          { label: 'Non gestito', text: 'Trovato sulla rete ma non nell\'inventario, un candidato da portare sotto gestione' },
          { label: 'Errore', text: 'L\'endpoint ha risposto ma l\'handshake TLS o il certificato è fallito (SNI rifiutato, certificato illeggibile). Una connessione rifiutata, un timeout, un errore DNS o di rete non lasciano alcuna riga. Riprova una riga, oppure Riprova tutti gli errori della pagina corrente' },
          { label: 'Cambiato', text: 'Un endpoint che presenta un certificato diverso dalla scansione precedente è contrassegnato con un timestamp di ultimo cambiamento' },
        ]
      },
    ],
    tips: [
      'Filtra i risultati con le etichette di stato: Tutti, Gestito, Non gestito, Errore',
      'L\'esportazione scarica tutti i certificati rilevati come CSV, qualunque sia il filtro',
      'Pianifica una scansione giornaliera delle tue sottoreti server con la notifica dei nuovi certificati abilitata',
    ],
    warnings: [
      'L\'esecuzione delle scansioni e la gestione dei profili richiedono permessi di amministratore; la sottorete di un profilo è limitata a 1024 indirizzi (/22), un CIDR inserito come target a 65.536 host',
    ],
  },
  helpGuides: {
    title: 'Rilevamento certificati',
    content: `
## Panoramica

Il Rilevamento certificati scansiona la tua rete per trovare i certificati TLS distribuiti su server ed endpoint e li confronta con l'inventario della tua PKI gestita. Usalo per individuare i certificati non tracciati, rilevare i cambiamenti e sorvegliare i certificati in scadenza fuori dal controllo di UCM.

## Schede

### Rilevati
Tutti i certificati trovati dalle scansioni, con stato, scadenza e dettagli dell'endpoint. Fai clic su una riga per aprire il pannello dettaglio con le informazioni del certificato, i Subject Alternative Names e la cronologia delle scansioni (visto la prima volta, visto l'ultima volta, ultimo cambiamento).

### Profili
Configurazioni di scansione salvate per scansioni ricorrenti: target, porte, pianificazione e notifiche.

### Cronologia
Esecuzioni di scansione passate con durata, target scansionati e certificati trovati.

## Scansione rapida

Esegui una scansione ad-hoc senza salvare un profilo:

1. Fai clic su **Scansione rapida**
2. Inserisci i **target**, ciascuno come tag: hostname, IP, sottorete CIDR (\`192.168.1.0/24\`) o \`host:porta\` (\`10.0.0.1:8443\`)
3. Inserisci le **porte**: porte TCP separate da virgole (es. \`443, 8443, 636\`), oppure scegli il preset delle porte comuni
4. Facoltativamente regola le **opzioni avanzate**: risoluzione DNS inversa (record PTR), timeout, concorrenza
5. Fai clic su **Avvia scansione**: l'avanzamento si aggiorna in tempo reale via WebSocket

## Profili di scansione

I profili salvano una configurazione di target per un uso ripetuto:

- **Target e porte**: stessi formati della Scansione rapida
- **Pianificazione**: manuale, oppure automatica ogni 1h / 6h / 12h / 24h / 7g
- **Notifiche**: avvisi email quando vengono rilevati nuovi certificati, quando un certificato cambia su un endpoint o quando i certificati rilevati stanno per scadere. Un certificato trovato tramite SNI su un target IP è contato come nuovo a ogni scansione

Esegui un profilo su richiesta con **Scansiona**, oppure lascia che lo scheduler lo esegua all'intervallo configurato.

## Stati dei risultati

- **Gestito**: L'impronta SHA-256 del certificato corrisponde a un certificato nell'inventario di UCM
- **Non gestito**: Trovato sulla rete ma non nell'inventario: un candidato da portare sotto gestione
- **Errore**: L'endpoint ha risposto ma l'handshake TLS o il certificato è fallito (SNI rifiutato, certificato illeggibile). Una connessione rifiutata, un timeout, un errore DNS o di rete non vengono registrati

### Rilevamento dei cambiamenti
Quando un endpoint presenta un certificato diverso dalla scansione precedente, il cambiamento viene registrato (impronta precedente conservata, timestamp **Ultimo cambiamento**) e può attivare una notifica.

## Filtri ed esportazione

- **Etichette di filtro per stato**: Tutti, Gestito, Non gestito, Errore
- **Filtro per profilo**: Limita i risultati a un solo profilo di scansione
- **Esporta**: Scarica tutti i certificati rilevati come CSV, qualunque sia il filtro
- **Riprova**: Riscansiona i singoli target in errore, oppure **Riprova tutti gli errori** mostrati nella pagina corrente
- **Risolvi DNS**: Risoluzione DNS inversa in blocco per gli IP rilevati

## Limiti e sicurezza

- La sottorete di un profilo è limitata a 1024 indirizzi (equivalente a un /22 IPv4), un CIDR inserito come target a 65.536 host; fino a 1000 target per scansione di profilo
- Gli intervalli privati RFC1918 e il loopback sono scansionabili: il modello di deployment on-prem di UCM; gli intervalli link-local, multicast e riservati sono bloccati
- Le scansioni avviate a mano e le modifiche ai profili sono registrate nel log di audit; le esecuzioni pianificate no

## Permessi

- **read:certificates**: Visualizzare i certificati rilevati, i profili e la cronologia
- **admin:system**: Creare/modificare i profili ed eseguire le scansioni
- **delete:certificates**: Eliminare i risultati rilevati

> 💡 Pianifica una scansione giornaliera delle tue sottoreti server e abilita la notifica dei nuovi certificati: intercetta i certificati distribuiti fuori dal tuo processo PKI.
`
  }
}
