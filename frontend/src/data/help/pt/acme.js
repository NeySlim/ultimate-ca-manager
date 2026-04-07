export default {
  helpContent: {
    title: 'ACME',
    subtitle: 'Gerenciamento Automatizado de Certificados',
    overview: 'O UCM suporta dois modos ACME: cliente ACME para certificados públicos de qualquer CA compatível com RFC 8555 (Let\'s Encrypt, ZeroSSL, Buypass, HARICA, etc.), e servidor ACME local para automação de PKI interna com mapeamento de domínios multi-CA.',
    sections: [
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
        title: 'Resolução Multi-CA',
        content: 'Quando um cliente ACME solicita um certificado, o UCM resolve a CA assinante nesta ordem:',
        items: [
          '1. Mapeamento de Domínio Local — correspondência exata do domínio, depois domínio pai',
          '2. Mapeamento de Domínio DNS — verifica a CA emissora configurada para o provedor DNS',
          '3. Padrão global — a CA definida na configuração do servidor ACME',
          '4. Primeira CA disponível com chave privada',
        ]
      },
    ],
    tips: [
      'URL do diretório ACME: https://seu-servidor:porta/acme/directory',
      'Use uma URL de diretório personalizada para conectar ao ZeroSSL, Buypass, HARICA ou qualquer CA RFC 8555',
      'As credenciais EAB (Key ID + HMAC Key) são fornecidas pela sua CA após o registro',
      'Chaves ECDSA P-256 oferecem segurança equivalente ao RSA-2048 com tamanho muito menor',
      'Use Domínios Locais para atribuir diferentes CAs a diferentes domínios internos',
      'Qualquer CA com chave privada pode ser selecionada como CA emissora',
      'Domínios curinga (*.example.com) requerem validação DNS-01',
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
`
  }
}
