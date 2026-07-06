export default {
  helpContent: {
    title: 'ACME',
    subtitle: 'Gerenciamento Automatizado de Certificados',
    overview: 'O UCM suporta dois modos ACME: cliente ACME para certificados públicos de qualquer CA compatível com RFC 8555 (Let\'s Encrypt, ZeroSSL, Buypass, HARICA, etc.), e servidor ACME local para automação de PKI interna com mapeamento de domínios multi-CA.',
    sections: [
      {
        title: "Renewal Information (ARI, RFC 9773)",
        content: "O servidor ACME local publica um recurso renewalInfo para que os clientes saibam o momento ideal para renovar cada certificado.",
        items: [
          { label: "Janela sugerida", text: "Retorna uma janela início/fim centrada antes da expiração, para distribuir as renovações" },
          { label: "Revogação", text: "Um certificado revogado retorna uma janela no passado → clientes conformes renovam imediatamente" },
          { label: "Sem autenticação", text: "renewalInfo é um GET simples — não requer conta nem JWS (RFC 9773)" },
        ]
      },
      {
        title: 'Cliente ACME',
        items: [
          { label: 'Cliente', text: 'Solicitar certificados de qualquer CA ACME — Let\'s Encrypt, ZeroSSL, Buypass, HARICA ou personalizada' },
          { label: 'Servidor Personalizado', text: 'Definir uma URL de diretório ACME personalizada para usar qualquer CA compatível com RFC 8555' },
          { label: 'EAB', text: 'Suporte a External Account Binding para CAs que requerem pré-registro (ZeroSSL, HARICA, etc.)' },
          { label: 'Tipos de Chave', text: 'RSA-2048, RSA-4096, ECDSA P-256, ECDSA P-384 para chaves de certificado' },
          { label: 'Chaves de Conta', text: 'Algoritmos ES256 (P-256), ES384 (P-384) ou RS256 para chaves de conta ACME' },
          { label: 'Provedores DNS', text: 'Configurar provedores de desafio DNS-01 (Cloudflare, Route53, etc.)' },
          { label: 'Domínios', text: 'Mapear domínios para provedores DNS para validação automática' },
        ]
      },
      {
        title: 'Servidor ACME Local',
        items: [
          { label: 'Configuração', text: 'Ativar/desativar o servidor ACME integrado, selecionar CA padrão' },
          { label: 'Domínios Locais', text: 'Mapear domínios internos para CAs específicas para emissão multi-CA' },
          { label: 'Contas', text: 'Visualizar e gerenciar contas de clientes ACME registradas' },
          { label: 'Histórico', text: 'Rastrear todos os pedidos de emissão de certificados ACME' },
        ]
      },
      {
        title: 'Proxy ACME',
        items: [
          { label: 'CA upstream', text: 'Selecione uma predefinição (Let\'s Encrypt Production/Staging) ou insira uma URL de diretório ACME personalizada para qualquer CA RFC 8555' },
          { label: 'Estado da conta', text: 'Mostra se o UCM está registrado na CA upstream. As contas são registradas automaticamente na primeira solicitação de proxy' },
          { label: 'Testar conexão', text: 'Verifica a conectividade com a CA upstream e se são necessárias credenciais EAB' },
          { label: 'Redefinir conta', text: 'Limpa as credenciais de conta upstream salvas para forçar novo registro (use após mudar a CA upstream)' },
          { label: 'Credenciais EAB', text: 'Credenciais de External Account Binding para CAs que as exigem (ex.: ZeroSSL, Google Trust)' },
          { label: 'Desafios DNS', text: 'O UCM lida com desafios DNS-01 em nome dos clientes usando os provedores DNS configurados' },
        ]
      },
      {
        title: 'Credenciais EAB (lado servidor)',
        content: 'Quando UCM atua como servidor ACME, External Account Binding (RFC 8555 §7.3.4) permite exigir credenciais pré-emitidas antes que clientes registrem contas:',
        items: [
          { label: 'Emitir', text: 'Gerar um novo par kid + chave HMAC em ACME → EAB Credentials' },
          { label: 'Distribuir', text: 'Entregar o kid + HMAC ao cliente (cert-manager, certbot, acme.sh)' },
          { label: 'Vincular', text: 'O cliente assina um JWS sobre a chave MAC em newAccount para vincular sua conta ACME' },
          { label: 'Rotacionar / Revogar', text: 'Revogar um kid a qualquer momento — contas existentes continuam, novos vínculos são recusados' },
          { label: 'Auditoria', text: 'Emissão, rotação e revogação são auditadas sob o operador que as realizou' },
        ]
      },
      {
        title: 'Resolvedores DNS personalizados (DNS-01)',
        items: [
          { label: 'Override por conta', text: 'Sobrescrever resolvedores do sistema ao validar registros TXT _acme-challenge' },
          { label: 'Split-horizon', text: 'Útil quando seu servidor autoritativo é interno mas a visão pública é cacheada em outro lugar' },
          { label: 'Registros obsoletos', text: 'Evita o cache de resolvedores públicos durante renovações automáticas rápidas' },
        ]
      },
      {
        title: 'ACME em IPs internos / privados',
        content: 'A validação HTTP-01 e TLS-ALPN-01 funciona nativamente para alvos RFC1918, loopback, .lan / .local / .corp — o modelo de implantação principal do UCM.',
        items: [
          { label: 'Toggle', text: 'Settings → SystemConfig → acme.allow_private_ips (padrão: true)' },
          { label: 'Sempre bloqueado', text: 'IPs de metadados cloud (169.254.169.254, fd00:ec2::254, etc.) são bloqueados incondicionalmente' },
        ]
      },
      {
        title: 'Resolução Multi-CA',
        content: 'Quando um cliente ACME solicita um certificado, o UCM resolve a CA assinante nesta ordem:',
        items: [
          '1. Mapeamento de Domínio Local — correspondência exata do domínio, depois domínio pai',
          '2. Mapeamento de Domínio DNS — verifica a CA emissora configurada para o provedor DNS',
          '3. Padrão global — a CA definida na configuração do servidor ACME',
          '4. Primeira CA disponível com chave privada',
        ]
      },
      {
        title: 'Certificados de endereço IP (RFC 8738)',
        content: 'O servidor ACME local pode emitir certificados para endereços IPv4 e IPv6, não apenas nomes DNS. Use o tipo de identificador « ip » no pedido.',
        items: [
          { label: 'Identificador', text: 'Pedido com { "type": "ip", "value": "192.0.2.10" } (IPv4) ou um literal IPv6 como 2001:db8::1' },
          { label: 'Desafios', text: 'Apenas HTTP-01 e TLS-ALPN-01 são oferecidos — DNS-01 é proibido para identificadores IP conforme RFC 8738' },
          { label: 'SNI TLS-ALPN-01', text: 'A validação usa a forma reverse-DNS (in-addr.arpa / ip6.arpa) como hostname SNI' },
          { label: 'SAN emitido', text: 'O certificado contém um SAN iPAddress; pedidos mistos DNS + IP são suportados' },
          { label: 'IPs internos', text: 'Endereços RFC1918 e loopback validam nativamente — o modelo de implantação principal do UCM' },
        ]
      }
    ],
    tips: [
      'URL do diretório ACME: https://seu-servidor:porta/acme/directory',
      'Use uma URL de diretório personalizada para conectar ao ZeroSSL, Buypass, HARICA ou qualquer CA RFC 8555',
      'As credenciais EAB (Key ID + HMAC Key) são fornecidas pela sua CA após o registro',
      'Chaves ECDSA P-256 oferecem segurança equivalente ao RSA-2048 com tamanho muito menor',
      'Use Domínios Locais para atribuir diferentes CAs a diferentes domínios internos',
      'Qualquer CA com chave privada pode ser selecionada como CA emissora',
      'Domínios curinga (*.example.com) requerem validação DNS-01',
      'Quando UCM é o servidor ACME, emita suas próprias credenciais EAB em ACME → EAB Credentials',
      'Para Kubernetes/cert-manager: veja os manifestos de referência em examples/kubernetes/cert-manager/',
    ],
    warnings: [
      'A validação de domínio é obrigatória — seu servidor deve estar acessível ou o DNS configurado',
      'Alterar o tipo de chave da conta requer re-registrar sua conta ACME',
    ],
  },
  helpGuides: {
    title: 'ACME',
    content: `
## Visão Geral

O UCM suporta ACME (Automated Certificate Management Environment) em dois modos:

- **Cliente ACME** — Obter certificados de qualquer CA compatível com RFC 8555 (Let's Encrypt, ZeroSSL, Buypass, HARICA ou personalizada)
- **Servidor ACME Local** — Servidor ACME integrado para automação de PKI interna com suporte multi-CA

## Cliente ACME

### Configurações do Cliente
Gerencie a configuração do seu cliente ACME:
- **Ambiente** — Staging (testes) ou Produção (certificados reais)
- **E-mail de Contato** — Obrigatório para registro da conta
- **Renovação Automática** — Renovar automaticamente certificados antes da expiração
- **Tipo de Chave do Certificado** — RSA-2048, RSA-4096, ECDSA P-256 ou ECDSA P-384
- **Algoritmo de Chave da Conta** — ES256, ES384 ou RS256 para assinatura da conta ACME

### Servidor ACME Personalizado
Use qualquer CA compatível com RFC 8555, não apenas Let's Encrypt:

| Provedor CA | URL do Diretório |
|---|---|
| **Let's Encrypt** | *(padrão, deixar vazio)* |
| **ZeroSSL** | \`https://acme.zerossl.com/v2/DV90\` |
| **Buypass** | \`https://api.buypass.com/acme/directory\` |
| **HARICA** | \`https://acme-v02.harica.gr/acme/<token>/directory\` |
| **Google Trust** | \`https://dv.acme-v02.api.pki.goog/directory\` |

Defina a URL do diretório da sua CA em **Configurações** → **Servidor ACME Personalizado**.

### External Account Binding (EAB)
Algumas CAs requerem credenciais EAB para vincular sua conta ACME a uma conta existente na CA:

1. Registre-se no portal da sua CA para obter o **EAB Key ID** e a **HMAC Key**
2. Insira ambos os valores em **Configurações** → **Servidor ACME Personalizado**
3. A chave HMAC é codificada em base64url (fornecida pela CA)

> 💡 EAB é exigido pelo ZeroSSL, HARICA, Google Trust Services e pela maioria das CAs empresariais.

### Chaves ECDSA vs RSA

| Tipo de Chave | Tamanho | Segurança | Desempenho |
|---|---|---|---|
| **RSA-2048** | 2048 bit | Padrão | Base |
| **RSA-4096** | 4096 bit | Superior | Mais lento |
| **ECDSA P-256** | 256 bit | ≈ RSA-3072 | Muito mais rápido |
| **ECDSA P-384** | 384 bit | ≈ RSA-7680 | Mais rápido |

Chaves ECDSA são recomendadas para implantações modernas — menores, mais rápidas e igualmente seguras.

### Origem da chave
Ao solicitar um certificado, escolha de onde vem a chave privada:

- **Gerar nova chave** *(padrão)* — o UCM cria um novo par de chaves para cada ordem
- **Reutilizar chave na renovação** — mantém a mesma chave privada entre renovações (necessário para DANE/TLSA e key pinning); a primeira emissão gera a chave, as renovações a recarregam
- **Fornecer CSR externo** — cole um CSR PEM gerado externamente; o UCM envia-o no finalize e a chave privada nunca entra no UCM. Os domínios do CSR devem corresponder exatamente aos identificadores da ordem

### Preflight (ensaio)
**Executar preflight** no formulário de solicitação valida todo o pedido contra o diretório **staging** do Let's Encrypt, sem consumir limites de produção:

- Verifica sintaxe dos domínios, email de contato, conta ACME / EAB e conectividade com a CA
- O modo **Completo** cria uma ordem staging e mostra os registros TXT \`_acme-challenge\` exatos a publicar
- **Somente validar** verifica configuração e conectividade sem criar ordem
- Opcionalmente verifica a propagação DNS dos TXT após adicionar os registros

> 💡 CAs personalizadas não têm endpoint staging — o preflight valida apenas configuração e conectividade.

### Provedores DNS
Configure provedores de desafio DNS-01 para validação de domínio. Provedores suportados incluem:
- Cloudflare
- AWS Route 53
- Google Cloud DNS
- DigitalOcean
- OVH
- E outros

Cada provedor requer credenciais de API específicas para o serviço DNS.

### Domínios
Mapeie seus domínios para provedores DNS. Ao solicitar um certificado para um domínio, o UCM usa o provedor mapeado para criar registros de desafio DNS-01.

1. Clique em **Adicionar Domínio**
2. Insira o nome do domínio (ex.: \`example.com\` ou \`*.example.com\`)
3. Selecione o provedor DNS
4. Clique em **Salvar**

> 💡 Certificados curinga (\`*.example.com\`) requerem validação DNS-01.


## Modo Proxy ACME

O proxy ACME permite que clientes internos solicitem certificados de uma CA pública (Let's Encrypt, ZeroSSL, etc.) através do UCM, sem acesso direto à Internet. O UCM atua como intermediário, gerenciando os desafios DNS-01 e encaminhando as solicitações à CA upstream.

### Quando usar o modo proxy
- Servidores internos sem acesso direto à Internet
- Gerenciamento centralizado de desafios DNS-01 através dos provedores DNS configurados no UCM
- Auditoria e rastreamento de todas as emissões de certificados públicos

### Configuração
1. Vá para **ACME** → aba **Let's Encrypt**
2. Role até a seção **Proxy ACME**
3. Ative o botão **Proxy ACME**
4. Selecione uma **Conta CA upstream** em **Contas CA externas** (Let's Encrypt, Actalis, ZeroSSL, URL personalizada, EAB)
5. Clique em **Testar conexão** para verificar a conectividade com a CA upstream
6. Registre a conta upstream se necessário (email + **Registrar conta**)
7. O UCM registra automaticamente uma conta na primeira solicitação proxy se ainda não estiver

### Caminhos proxy dedicados (multi-CA)
Cada conta CA externa pode expor seu próprio endpoint proxy ACME:

1. Abra **Contas CA externas** (mesma aba Let's Encrypt)
2. Edite ou crie uma conta CA
3. Ative **Expor via proxy ACME**
4. Defina um **slug** único — ex. \`actalis-production\`, \`letsencrypt-staging\`
5. Salve — a URL aparece na seção proxy e no cartão da conta

Os clientes usam:
\`\`\`
https://seu-servidor-ucm:8443/acme/proxy/<slug>/directory
\`\`\`

O caminho padrão legacy permanece para a conta selecionada nas definições do proxy:
\`\`\`
https://seu-servidor-ucm:8443/acme/proxy/directory
\`\`\`

Slugs reservados (proibidos): \`directory\`, \`new-order\`, \`challenge\`, \`acct\`, etc.

### Gerenciamento de contas
- O **emblema de status da conta** mostra se o UCM está registrado junto à CA upstream
- A troca de CA upstream limpa automaticamente credenciais obsoletas e força um novo registro
- Use o botão **Redefinir conta** para limpar credenciais manualmente, se necessário
- **Testar conexão** verifica se o diretório upstream está acessível e se EAB é necessário

### Uso do proxy
Direcione seus clientes ACME internos para o diretório proxy do CA alvo.

**URL por slug** (recomendado com vários CAs):
\`\`\`
https://seu-servidor-ucm:8443/acme/proxy/<slug>/directory
\`\`\`

**URL padrão** (conta selecionada nas definições do proxy):
\`\`\`
https://seu-servidor-ucm:8443/acme/proxy/directory
\`\`\`

Exemplo com certbot (substitua \`<slug>\`):
\`\`\`
certbot certonly \\
  --server https://seu-servidor-ucm:8443/acme/proxy/<slug>/directory \\
  --preferred-challenges dns-01 \\
  --authenticator manual \\
  --manual-auth-hook /bin/true \\
  --manual-cleanup-hook /bin/true \\
  --non-interactive --agree-tos -m you@example.com \\
  -d subdomain.example.com
\`\`\`

> 💡 As credenciais EAB do proxy são distintas das do cliente — elas autenticam o UCM junto à CA upstream, não seus clientes junto ao UCM.

> ⚠ Pré-requisito: o domínio deve estar em ACME Domains com provedor DNS. O proxy suporta apenas dns-01.

> ⚠ Evite solicitações simultâneas para o mesmo FQDN (Certbot + interface UCM).

> ℹ️ Em lab / certificado autoassinado, adicione \`--no-verify-ssl\` ao Certbot.

## Servidor ACME Local

### Configuração
- **Ativar/Desativar** — Alternar o servidor ACME integrado
- **CA Padrão** — Selecionar qual CA assina certificados por padrão
- **Termos de Serviço** — URL opcional de ToS para clientes

### URL do Diretório ACME
\`\`\`
https://seu-servidor:8443/acme/directory
\`\`\`

Clientes como certbot, acme.sh ou Caddy usam esta URL para descobrir os endpoints ACME.

### Domínios Locais (Multi-CA)
Mapeie domínios internos para CAs específicas. Isso permite que diferentes domínios sejam assinados por diferentes CAs.

1. Clique em **Adicionar Domínio**
2. Insira o domínio (ex.: \`internal.corp\` ou \`*.dev.local\`)
3. Selecione a **CA Emissora**
4. Ative/desative **Auto-Aprovar**
5. Clique em **Salvar**

### Ordem de Resolução de CA
Quando um cliente ACME solicita um certificado, o UCM determina a CA assinante nesta ordem:
1. **Mapeamento de Domínio Local** — Correspondência exata, depois correspondência de domínio pai
2. **Mapeamento de Domínio DNS** — A CA configurada para o provedor DNS
3. **Padrão global** — A CA definida na configuração do servidor ACME
4. **Primeira disponível** — Qualquer CA com chave privada

### Contas
Visualize contas de clientes ACME registradas:
- ID da conta e e-mail de contato
- Data de registro
- Número de pedidos

### Histórico
Navegue por todos os pedidos de emissão de certificados:
- Status do pedido (pendente, válido, inválido, pronto)
- Nomes de domínio solicitados
- CA assinante usada
- Data e hora da emissão

## Usando certbot

\`\`\`
# Registrar conta (Let's Encrypt — padrão)
certbot register --agree-tos --email admin@example.com

# Registrar com CA ACME personalizada + EAB
certbot register \\
  --server 'https://acme.zerossl.com/v2/DV90' \\
  --eab-kid 'seu-key-id' \\
  --eab-hmac-key 'sua-hmac-key' \\
  --agree-tos --email admin@example.com

# Solicitar certificado com chave ECDSA
certbot certonly --server https://seu-servidor:8443/acme/directory \\
  --standalone -d meuservidor.internal.corp \\
  --key-type ecdsa --elliptic-curve secp256r1

# Renovar
certbot renew --server https://seu-servidor:8443/acme/directory
\`\`\`

## Usando acme.sh

\`\`\`
# Padrão (Let's Encrypt)
acme.sh --issue -d example.com --standalone

# CA ACME personalizada com EAB e ECDSA
acme.sh --issue \\
  --server 'https://acme-v02.harica.gr/acme/TOKEN/directory' \\
  --eab-kid 'seu-key-id' \\
  --eab-hmac-key 'sua-hmac-key' \\
  --keylength ec-256 \\
  -d example.com --standalone
\`\`\`

> ⚠ Para ACME interno, os clientes devem confiar na CA do UCM. Instale o certificado da CA Raiz no armazenamento de confiança do cliente.
## Certificados de endereço IP (RFC 8738)

O servidor ACME local pode emitir certificados para **endereços IP** (IPv4 e IPv6), não apenas nomes DNS. Útil para serviços internos, appliances e hosts endereçados diretamente por IP.

### Pedir um certificado IP
Use o tipo de identificador \`ip\` no pedido ACME:
\`\`\`json
{
  "identifiers": [
    { "type": "ip", "value": "192.0.2.10" },
    { "type": "ip", "value": "2001:db8::1" }
  ]
}
\`\`\`
Pedidos mistos DNS + IP também são suportados.

### Validação
- **HTTP-01** e **TLS-ALPN-01** são os únicos desafios oferecidos para identificadores IP. **DNS-01 é proibido** para IPs pela RFC 8738.
- **HTTP-01** conecta-se diretamente ao IP (literais IPv6 ficam entre colchetes, ex. \`http://[2001:db8::1]/...\`).
- **TLS-ALPN-01** usa a forma reverse-DNS do IP (\`in-addr.arpa\` / \`ip6.arpa\`) como hostname SNI.

### Certificado emitido
O certificado assinado contém uma entrada SubjectAltName **iPAddress** para cada IP validado.

> 💡 Endereços internos (RFC1918, loopback) validam nativamente — o modelo de implantação principal do UCM. IPs de metadados cloud permanecem bloqueados.

## Renewal Information (ARI, RFC 9773)

O servidor ACME local anuncia \`renewalInfo\` no seu directory e serve uma **janela de renovação sugerida** por certificado.

- Janela centrada antes da expiração → renovações distribuídas
- Certificado revogado → janela no passado (renovar já)
- GET não autenticado em \`/acme/renewalInfo/<certID>\`

`
  }
}
