export default {
  helpContent: {
    title: 'EST',
    subtitle: 'Inscrição via Transporte Seguro',
    overview: 'EST (RFC 7030) fornece inscrição segura de certificados via HTTPS com TLS mútuo (mTLS) ou autenticação HTTP Basic. Ideal para ambientes empresariais modernos que requerem inscrição baseada em padrões com forte segurança de transporte.',
    sections: [
      {
        title: 'Abas',
        items: [
          { label: 'Configurações', text: 'Ativar EST, selecionar CA assinante, configurar credenciais de autenticação e validade de certificado' },
          { label: 'Informações', text: 'URLs de endpoints EST para integração, estatísticas de inscrição e exemplos de uso' },
        ]
      },
      {
        title: 'Autenticação',
        items: [
          { label: 'mTLS (TLS Mútuo)', text: 'Cliente apresenta um certificado durante o handshake TLS — método de autenticação mais forte' },
          { label: 'HTTP Basic Auth', text: 'Fallback com usuário/senha quando mTLS não está disponível' },
        ]
      },
      {
        title: 'Endpoints',
        items: [
          { label: '/cacerts', text: 'Recuperar a cadeia de certificados da CA (sem autenticação necessária)' },
          { label: '/simpleenroll', text: 'Enviar um CSR e receber um certificado assinado' },
          { label: '/simplereenroll', text: 'Renovar um certificado existente (requer mTLS)' },
          { label: '/csrattrs', text: 'Obter atributos de CSR recomendados pelo servidor' },
          { label: '/serverkeygen', text: 'Servidor gera o par de chaves e retorna certificado + chave' },
        ]
      },
    ],
    tips: [
      'EST é o substituto moderno do SCEP — prefira EST para novas implantações',
      'Use autenticação mTLS para maior segurança — Basic Auth é um fallback',
      'O endpoint /simplereenroll requer que o cliente apresente seu certificado atual via mTLS',
      'Copie as URLs de endpoint da aba Informações para configurar seus clientes EST',
    ],
    warnings: [
      'EST requer HTTPS — o cliente deve confiar no certificado do servidor UCM ou na CA',
      'A autenticação mTLS requer configuração adequada de terminação TLS (proxy reverso deve encaminhar certificados de cliente)',
    ],
  },
  helpGuides: {
    title: 'Protocolo EST',
    content: `
## Visão Geral

Enrollment over Secure Transport (EST) é definido na **RFC 7030** e fornece inscrição de certificados, reinscrição e recuperação de certificados CA via HTTPS. EST é o substituto moderno do SCEP, oferecendo segurança mais forte através de autenticação TLS mútua (mTLS).

## Configuração

### Aba Configurações

1. **Ativar EST** — Alternar o protocolo EST
2. **CA Assinante** — Selecionar qual Autoridade Certificadora assina certificados inscritos via EST
3. **Autenticação** — Configurar credenciais HTTP Basic Auth (usuário e senha)
4. **Validade do Certificado** — Período de validade padrão para certificados emitidos via EST (em dias)

### Salvando Configuração

Clique em **Salvar** para aplicar as alterações. Os endpoints EST ficam disponíveis imediatamente quando ativados.

## Autenticação

EST suporta dois métodos de autenticação:

### TLS Mútuo (mTLS) — Recomendado

O cliente apresenta um certificado durante o handshake TLS. O UCM valida o certificado e autentica o cliente automaticamente.

- **Método mais forte** — identidade criptográfica do cliente
- **Obrigatório para** \`/simplereenroll\` — o cliente deve apresentar seu certificado atual
- **Depende de** configuração adequada de terminação TLS (proxy reverso deve passar \`SSL_CLIENT_CERT\` para o UCM)

### HTTP Basic Auth — Fallback

Autenticação com usuário e senha via HTTPS. Configurada nas Configurações EST.

- **Mais simples de configurar** — não precisa de certificado de cliente
- **Menos seguro** — credenciais transmitidas por requisição (protegido por HTTPS)
- **Use quando** a infraestrutura mTLS não estiver disponível

## Endpoints EST

Todos os endpoints estão em \`/.well-known/est/\`:

### GET /cacerts
Recuperar a cadeia de certificados da CA. **Sem autenticação necessária.**

Use isto para inicializar a confiança — clientes buscam o certificado da CA antes da inscrição.

\`\`\`bash
curl -k https://seu-servidor:8443/.well-known/est/cacerts | \\
  base64 -d | openssl pkcs7 -inform DER -print_certs
\`\`\`

### POST /simpleenroll
Enviar um CSR PKCS#10 e receber um certificado assinado.

Requer autenticação (mTLS ou Basic Auth).

\`\`\`bash
# Usando curl com Basic Auth
curl -k --user usuario-est:senha-est \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://seu-servidor:8443/.well-known/est/simpleenroll
\`\`\`

### POST /simplereenroll
Renovar um certificado existente. **Requer mTLS** — o cliente deve apresentar o certificado sendo renovado.

\`\`\`bash
curl -k --cert cliente.pem --key cliente.key \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://seu-servidor:8443/.well-known/est/simplereenroll
\`\`\`

### GET /csrattrs
Obter os atributos de CSR (OIDs) recomendados pelo servidor.

### POST /serverkeygen
Servidor gera um par de chaves e retorna o certificado junto com a chave privada. Útil quando o cliente não pode gerar chaves localmente.

## Aba Informações

A aba Informações exibe:
- **URLs de Endpoint** — URLs prontas para copiar e colar para cada operação EST
- **Estatísticas de Inscrição** — Número de inscrições, reinscrições e erros
- **Última atividade** — Operações EST mais recentes dos logs de auditoria

## Exemplos de Integração

### Usando cliente est (libest)
\`\`\`bash
estclient -s seu-servidor -p 8443 \\
  --srp-user usuario-est --srp-password senha-est \\
  -o /certs --enroll
\`\`\`

### Usando OpenSSL
\`\`\`bash
# Buscar certificados da CA
curl -k https://seu-servidor:8443/.well-known/est/cacerts | \\
  base64 -d > cacerts.p7

# Gerar CSR
openssl req -new -newkey rsa:2048 -nodes \\
  -keyout cliente.key -out cliente.csr \\
  -subj "/CN=meu-dispositivo/O=MinhaOrg"

# Inscrever (Basic Auth)
curl -k --user usuario-est:senha-est \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @<(openssl req -in cliente.csr -outform DER | base64) \\
  https://seu-servidor:8443/.well-known/est/simpleenroll | \\
  base64 -d | openssl x509 -inform DER -out cliente.pem
\`\`\`

### Windows (certutil)
\`\`\`cmd
certutil -enrollmentServerURL add \\
  "https://seu-servidor:8443/.well-known/est" \\
  kerberos
\`\`\`

## EST vs SCEP

| Recurso | EST | SCEP |
|---------|-----|------|
| Transporte | HTTPS (TLS) | HTTP ou HTTPS |
| Autenticação | mTLS + Basic Auth | Senha de desafio |
| Padrão | RFC 7030 (2013) | RFC 8894 (2020, mas legado) |
| Geração de chave | Opção no servidor | Apenas no cliente |
| Renovação | Reinscrição mTLS | Reinscrição |
| Segurança | Forte (baseada em TLS) | Mais fraca (segredo compartilhado) |
| Recomendação | ✅ Preferido para novos | Apenas dispositivos legados |

> 💡 Use EST para novas implantações. Use SCEP apenas para dispositivos de rede legados que não suportam EST.
`
  }
}
