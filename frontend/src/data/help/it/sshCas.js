export default {
  helpContent: {
    title: 'Autorità di certificazione SSH',
    subtitle: 'Gestisci le CA SSH per l\'autenticazione di utenti e host',
    overview: 'Crea e gestisci autorità di certificazione SSH conformi agli standard OpenSSH. Le CA SSH eliminano la necessità di distribuire singole chiavi pubbliche, i server e gli utenti si fidano della CA, e la CA firma certificati che concedono l\'accesso.',
    sections: [
      {
        title: 'Tipi di CA',
        items: [
          { label: 'User CA', text: 'Firma certificati utente per il login SSH. I server si fidano di questa CA e accettano qualsiasi certificato da essa firmato.' },
          { label: 'Host CA', text: 'Firma certificati host per dimostrare l\'identità del server. I client si fidano di questa CA per verificare di connettersi al server corretto.' },
        ]
      },
      {
        title: 'Algoritmi di chiave',
        items: [
          { label: 'Ed25519', text: 'Moderno, veloce, chiavi piccole (256 bit). Consigliato per le nuove installazioni.' },
          { label: 'ECDSA P-256 / P-384 / P-521', text: 'Chiavi a curva ellittica, ampiamente supportate. Buon equilibrio tra sicurezza e compatibilità.' },
          { label: 'RSA 4096', text: 'Algoritmo tradizionale, sempre a 4096 bit. Massima compatibilità con i sistemi più datati.' },
        ]
      },
      {
        title: 'Configurazione del server',
        items: [
          { label: 'Script di configurazione Linux/macOS', text: 'Scarica uno script shell POSIX (.sh) che configura automaticamente sshd per fidarsi di questa CA. Installazione rapida: curl -fsSL <url> | bash' },
          { label: 'Script di configurazione Windows', text: 'Scarica uno script PowerShell (.ps1) che configura Windows OpenSSH Server (scrive la chiave pubblica della CA in %ProgramData%\\ssh, blinda le ACL, aggiunge TrustedUserCAKeys / HostCertificate a sshd_config, valida con sshd -T, riavvia sshd). Installazione rapida: iwr <url> | iex' },
          { label: 'Blocco diagnostico', text: 'In caso di errore di Add-WindowsCapability (WSUS / dominio), lo script stampa un blocco etichettato che spiega lo stato della policy e tre percorsi di risoluzione, non modifica mai da sé la policy WSUS / WU' },
          { label: 'Dry-run', text: 'Entrambi gli script supportano un flag -DryRun / --dry-run per visualizzare in anteprima le modifiche senza applicarle' },
          { label: 'Configurazione manuale', text: 'Copia la chiave pubblica della CA e aggiungi TrustedUserCAKeys (User CA) o HostCertificate (Host CA) in sshd_config' },
        ]
      },
      {
        title: 'Revoca delle chiavi',
        items: [
          { label: 'KRL (Key Revocation List)', text: 'Formato binario compatto per revocare singoli certificati. Si configura tramite RevokedKeys in sshd_config.' },
          { label: 'Scarica KRL', text: 'Scarica il file KRL attuale dal pannello dettaglio della CA.' },
        ]
      },
      {
        title: 'Formati TTL',
        items: [
          { label: 'Durate con suffisso', text: 'Il TTL predefinito e il TTL massimo accettano 24h, 7d, 365d, suffissi s, m, h, d, w, y' },
          { label: 'Numeri semplici', text: 'Un numero senza suffisso è interpretato come secondi (es. 3600 = 1 ora)' },
          { label: 'Validazione', text: 'I valori malformati vengono rifiutati con un errore che indica i formati accettati' },
        ]
      },
    ],
    tips: [
      'Usa CA separate per i certificati utente e host: non mescolarle mai.',
      'Ed25519 è consigliato per le nuove installazioni grazie alla velocità e alla sicurezza.',
      'Scarica lo script di configurazione per una facile impostazione del server: gestisce automaticamente backup e validazione.',
    ],
    warnings: [
      'Eliminare una CA non revoca i certificati che ha firmato: revocali prima o aggiorna la fiducia dei server.',
      'Se la chiave privata della CA viene compromessa, tutti i certificati da essa firmati devono essere considerati non affidabili.',
    ],
  },
  helpGuides: {
    title: 'Autorità di certificazione SSH',
    content: `
## Panoramica

Le autorità di certificazione SSH (CA) sono il fondamento dell'autenticazione basata su certificati SSH. Anziché distribuire singole chiavi pubbliche a ogni server, si crea una CA e si configurano i server per fidarsi di essa. Qualsiasi certificato firmato dalla CA viene quindi accettato automaticamente.

UCM supporta il formato di certificato OpenSSH (RFC 4253 + estensioni OpenSSH), riconosciuto nativamente da OpenSSH 5.4+: nessun software aggiuntivo necessario su server o client.

## Tipi di CA

### User CA
Una User CA firma certificati che autenticano gli **utenti presso i server**. Quando un server si fida di una User CA, qualsiasi utente che presenti un certificato valido firmato da tale CA è autorizzato ad accedere (in base alla corrispondenza dei principals).

**Configurazione del server:**
\`\`\`
# /etc/ssh/sshd_config
TrustedUserCAKeys /etc/ssh/user_ca.pub
\`\`\`

### Host CA
Una Host CA firma certificati che autenticano i **server presso i client**. Quando un client si fida di una Host CA, può verificare che il server a cui si connette sia legittimo: eliminando gli avvisi TOFU (Trust On First Use).

**Configurazione del client:**
\`\`\`
# ~/.ssh/known_hosts
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Creare una CA

1. Fai clic su **Crea CA SSH**
2. Inserisci un nome descrittivo (es.: «CA utente Produzione»)
3. Seleziona il tipo di CA: **User** o **Host**
4. Scegli l'algoritmo di chiave:
   - **Ed25519**: Consigliato. Veloce, chiavi piccole, sicurezza moderna.
   - **ECDSA P-256/P-384/P-521**: Buona compatibilità e sicurezza.
   - **RSA 4096**: Massima compatibilità, chiavi più grandi.
5. Imposta opzionalmente la validità massima e le estensioni predefinite
6. Fai clic su **Crea**

### Formati TTL

I campi **TTL predefinito** e **TTL massimo** accettano durate leggibili:

- Valori con suffisso: \`24h\`, \`7d\`, \`365d\` (suffissi accettati: \`s\`, \`m\`, \`h\`, \`d\`, \`w\`, \`y\`)
- Numeri semplici: interpretati come **secondi** (es. \`3600\` = 1 ora)

I valori malformati vengono rifiutati con un errore che indica i formati accettati.

> 💡 Usa CA separate per i certificati utente e host. Non usare mai una stessa CA per entrambi gli scopi.

## Configurazione del server

### Script di configurazione automatica

UCM genera uno script shell POSIX che configura automaticamente il tuo server:

1. Apri il pannello dettaglio della CA
2. Fai clic su **Scarica script di configurazione**
3. Trasferisci lo script sul tuo server
4. Eseguilo:

\`\`\`bash
chmod +x setup-ssh-ca.sh
sudo ./setup-ssh-ca.sh
\`\`\`

Lo script:
- Rileva il sistema operativo e il sistema di init
- Esegue il backup di sshd_config prima di qualsiasi modifica
- Installa la chiave pubblica della CA
- Aggiunge TrustedUserCAKeys (User CA) o HostCertificate (Host CA)
- Valida la configurazione con \`sshd -t\`
- Riavvia sshd solo se la validazione ha esito positivo
- Supporta \`--dry-run\` per un'anteprima delle modifiche

### Configurazione manuale

#### User CA
\`\`\`bash
# Copia la chiave pubblica della CA sul server
echo "ssh-ed25519 AAAA... user-ca" | sudo tee /etc/ssh/user_ca.pub

# Aggiungi a sshd_config
echo "TrustedUserCAKeys /etc/ssh/user_ca.pub" | sudo tee -a /etc/ssh/sshd_config

# Riavvia sshd
sudo systemctl restart sshd
\`\`\`

#### Host CA
\`\`\`bash
# Firma la chiave host del server
# Poi aggiungi a sshd_config:
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

## Liste di revoca delle chiavi (KRL)

Le CA SSH supportano le liste di revoca delle chiavi per invalidare i certificati compromessi:

1. Revoca i certificati dalla pagina Certificati SSH
2. Scarica la KRL aggiornata dal pannello dettaglio della CA
3. Distribuisci il file KRL ai server:

\`\`\`bash
# Aggiungi a sshd_config
RevokedKeys /etc/ssh/revoked_keys
\`\`\`

> ⚠ I server devono essere configurati per verificare la KRL. La revoca non ha effetto finché la KRL non viene distribuita.

## Buone pratiche

| Pratica | Raccomandazione |
|---------|-----------------|
| CA separate | Usa CA distinte per i certificati utente e host |
| Algoritmo di chiave | Ed25519 per le nuove installazioni, RSA 4096 per compatibilità con sistemi datati |
| Durata della CA | Mantieni le CA a lunga durata; usa certificati a breve scadenza |
| Backup | Esporta e conserva la chiave privata della CA in modo sicuro |
| Mappatura dei principals | Associa i principals a nomi utente specifici, non a caratteri jolly |
`
  }
}
