export default {
  helpContent: {
    title: 'Certificati SSH',
    subtitle: 'Emetti e gestisci certificati OpenSSH',
    overview: 'Emetti certificati SSH firmati dalle tue CA SSH. I certificati sostituiscono la gestione manuale di authorized_keys fornendo accesso limitato nel tempo, vincolato ai principals, con scadenza automatica. Sono supportati sia i certificati utente che quelli host.',
    sections: [
      {
        title: 'Modalità di emissione',
        items: [
          { label: 'Modalità firma', text: 'Incolla una chiave pubblica SSH esistente per firmarla. La chiave privata resta sulla macchina dell\'utente — UCM non la vede mai.' },
          { label: 'Modalità generazione', text: 'UCM genera una nuova coppia di chiavi e firma il certificato. Scarica la chiave privata immediatamente — non potrà essere recuperata in seguito.' },
        ]
      },
      {
        title: 'Campi del certificato',
        items: [
          { label: 'Key ID', text: 'Identificativo univoco del certificato. Appare nei log SSH per finalità di audit.' },
          { label: 'Principals', text: 'Nomi utente (certificato utente) o nomi host (certificato host) per i quali il certificato è valido. Separati da virgola.' },
          { label: 'Validità', text: 'Durata del certificato. Scegli un valore preimpostato (1h, 8h, 24h, 7g, 30g, 90g, 365g) oppure imposta una durata personalizzata in secondi.' },
          { label: 'Extensions', text: 'Estensioni SSH come permit-pty, permit-agent-forwarding. Applicabili solo ai certificati utente.' },
          { label: 'Critical Options', text: 'Restrizioni come force-command o source-address per limitare l\'uso del certificato.' },
        ]
      },
      {
        title: 'Tipi di certificati',
        items: [
          { label: 'Certificato utente', text: 'Autentica un utente presso un server. Il server deve fidarsi della CA firmataria tramite TrustedUserCAKeys.' },
          { label: 'Certificato host', text: 'Autentica un server presso i client. I client si fidano della CA tramite @cert-authority in known_hosts.' },
        ]
      },
      {
        title: 'Gestione',
        items: [
          { label: 'Revoca', text: 'Aggiunge un certificato alla lista di revoca delle chiavi (KRL) della CA. I server devono essere configurati per verificare la KRL.' },
          { label: 'Scarica', text: 'Scarica il certificato, la chiave pubblica o la chiave privata (solo modalità generazione).' },
        ]
      },
    ],
    tips: [
      'Usa certificati a breve scadenza (8h–24h) per l\'accesso utente, così da minimizzare l\'impatto di una chiave compromessa.',
      'La modalità firma è preferibile — la chiave privata dell\'utente non lascia mai la sua macchina.',
      'I Key ID devono essere descrittivi (es.: «jdoe-prod-2025») per facilitare l\'analisi dei log.',
      'Per i certificati host, il principal deve corrispondere al nome host usato dai client per la connessione.',
    ],
    warnings: [
      'In modalità generazione, scarica la chiave privata immediatamente — non viene conservata e non può essere recuperata.',
      'La revoca di un certificato funziona solo se i server sono configurati per verificare il file KRL della CA.',
    ],
  },
  helpGuides: {
    title: 'Certificati SSH',
    content: `
## Panoramica

I certificati SSH sono chiavi pubbliche SSH firmate con metadati: identità, periodo di validità, principals consentiti ed estensioni. Sostituiscono l'approccio tradizionale di \`authorized_keys\` con un controllo degli accessi centralizzato, limitato nel tempo e verificabile.

UCM emette certificati in formato OpenSSH compatibili con OpenSSH 5.4+ su qualsiasi piattaforma.

## Modalità di emissione

### Modalità firma (consigliata)
L'utente genera la propria coppia di chiavi e fornisce solo la **chiave pubblica** a UCM. La chiave privata non lascia mai la macchina dell'utente.

**Procedura per l'utente:**
\`\`\`bash
# 1. Generare una coppia di chiavi (macchina dell'utente)
ssh-keygen -t ed25519 -f ~/.ssh/id_work -C "jdoe@example.com"

# 2. Copiare il contenuto della chiave pubblica
cat ~/.ssh/id_work.pub

# 3. Incollare nel modulo di firma di UCM
# 4. Scaricare il certificato firmato
# 5. Salvare come ~/.ssh/id_work-cert.pub

# 6. Connettersi
ssh -i ~/.ssh/id_work user@server
\`\`\`

### Modalità generazione
UCM genera sia la coppia di chiavi che il certificato. Usare questa modalità quando è necessario distribuire le credenziali in modo centralizzato.

> ⚠ **Scarica la chiave privata immediatamente** — non viene conservata in UCM e non può essere recuperata.

**Procedura:**
1. Seleziona una CA e compila i dettagli del certificato
2. Scegli la modalità «Generazione»
3. Fai clic su **Emetti**
4. Scarica i tre file:
   - Chiave privata (\`keyid\`) — **Conservala al sicuro!**
   - Certificato (\`keyid-cert.pub\`)
   - Chiave pubblica (\`keyid.pub\`)

## Campi del certificato

### Key ID
Un identificativo univoco incorporato nel certificato. Appare nei log del server SSH quando il certificato viene utilizzato, rendendolo indispensabile per l'audit.

**Buoni esempi di Key ID:** \`jdoe-prod-2025\`, \`webserver-01\`, \`deploy-ci-pipeline\`

### Principals
I principals definiscono **chi** (certificati utente) o **cosa** (certificati host) il certificato autorizza:

- **Certificati utente**: elenco dei nomi utente con cui il titolare può accedere (es.: \`deploy\`, \`admin\`)
- **Certificati host**: elenco dei nomi host o IP con cui il server è conosciuto (es.: \`web01.example.com\`, \`10.0.1.5\`)

> 💡 Se non vengono specificati principals, il certificato è valido per qualsiasi principal — il che è generalmente troppo permissivo.

### Validità

Scegli un valore preimpostato o imposta una durata personalizzata:

| Preimpostazione | Caso d'uso |
|-----------------|------------|
| 1 ora | Pipeline CI/CD, attività una tantum |
| 8 ore | Accesso per giornata lavorativa standard |
| 24 ore | Accesso esteso |
| 7 giorni | Accesso basato su sprint |
| 30 giorni | Rotazione mensile |
| 365 giorni | Account di servizio a lunga durata |

I certificati a breve scadenza (8h–24h) sono consigliati per gli utenti. Validità più lunghe sono accettabili per gli account di servizio automatizzati.

### Extensions (solo certificati utente)

| Extension | Descrizione |
|-----------|-------------|
| permit-pty | Consente sessioni di terminale interattivo |
| permit-agent-forwarding | Consente l'inoltro dell'agente SSH |
| permit-X11-forwarding | Consente l'inoltro del display X11 |
| permit-port-forwarding | Consente l'inoltro di porte TCP |
| permit-user-rc | Consente l'esecuzione di ~/.ssh/rc al login |

### Critical Options

| Opzione | Descrizione |
|---------|-------------|
| force-command | Limita il certificato a un singolo comando |
| source-address | Limita a indirizzi IP o CIDR di origine specifici |

**Esempio:** Un certificato con \`force-command=ls\` e \`source-address=10.0.0.0/8\` può eseguire solo \`ls\` e solo dalla rete 10.x.x.x.

## Utilizzo dei certificati

### Certificato utente
\`\`\`bash
# Posiziona il certificato accanto alla chiave privata
# Se la chiave è ~/.ssh/id_work, il certificato deve essere ~/.ssh/id_work-cert.pub
cp downloaded-cert.pub ~/.ssh/id_work-cert.pub

# SSH utilizza automaticamente il certificato
ssh user@server
\`\`\`

### Certificato host
\`\`\`bash
# Sul server: posiziona il certificato host
sudo cp host-cert.pub /etc/ssh/ssh_host_ed25519_key-cert.pub

# Aggiungi a sshd_config
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

Sui client, aggiungi la Host CA a known_hosts:
\`\`\`
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Revoca

1. Seleziona un certificato nella tabella
2. Fai clic su **Revoca** nel pannello dettaglio
3. Il certificato viene aggiunto alla lista di revoca delle chiavi (KRL) della CA
4. Scarica e distribuisci la KRL aggiornata ai server (dalla pagina CA SSH)

> ⚠ La revoca ha effetto solo quando i server verificano la KRL tramite \`RevokedKeys\` in sshd_config.

## Risoluzione dei problemi

| Problema | Soluzione |
|----------|----------|
| Permission denied (publickey) | Verifica che la CA sia considerata affidabile sul server (TrustedUserCAKeys) |
| Certificato non utilizzato | Assicurati che il file del certificato si chiami \`<chiave>-cert.pub\` accanto alla chiave privata |
| Mancata corrispondenza del principal | Il nome utente SSH deve essere elencato nei principals del certificato |
| Certificato scaduto | Emetti un nuovo certificato con una validità adeguata |
| Verifica dell'host fallita | Aggiungi la Host CA a known_hosts con @cert-authority |
`
  }
}
