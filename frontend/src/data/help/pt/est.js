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
          { label: 'Endpoints EST', text: 'URLs de endpoints EST para integração e estatísticas de inscrição' },
        ]
      },
      {
        title: 'Autenticação',
        items: [
          { label: 'mTLS (TLS Mútuo)', text: 'Cliente apresenta um certificado durante o handshake TLS, método de autenticação mais forte' },
          { label: 'HTTP Basic Auth', text: 'Fallback com usuário/senha quando mTLS não está disponível. Com allow_empty_username definido por PATCH /api/v2/est/config, um cliente pode também enviar um nome de usuário vazio com a senha (RFC 7030 §3.2.3, v2.252)' },
          { label: 'Certificado apresentado', text: 'Para /simpleenroll e /serverkeygen via mTLS, um certificado assinado pela CA EST deve ser um que ela ainda mantenha: certificados revogados, substituídos ou excluídos são recusados (RFC 7030 §3.3.2). Um certificado emitido por outra CA deste servidor é recusado quando ele ou uma CA acima dele é revogado, ou quando expirou (v2.252); um de uma autoridade que este servidor não mantém fica a cargo da camada TLS' },
          { label: 'Vínculo tls-unique', text: 'Um CSR com challengePassword deve conter o valor tls-unique da sua conexão TLS 1.2 com o UCM (RFC 7030 §3.5); é recusado com 400 quando o valor difere ou não pode ser verificado (TLS 1.3, um proxy à frente). /csrattrs não pede um. ignore_challenge_password, definido por PATCH /api/v2/est/config, dispensa a verificação para um cliente que coloca uma senha ali (v2.252)' },
          { label: 'Chaves comprometidas', text: 'Um CSR cuja chave foi revogada como comprometida (keyCompromise) é recusado com 400 (v2.252)' },
        ]
      },
      {
        title: 'Endpoints',
        items: [
          { label: '/cacerts', text: 'Recuperar a cadeia de certificados da CA (sem autenticação necessária)' },
          { label: '/simpleenroll', text: 'Enviar um CSR e receber um certificado assinado' },
          { label: '/simplereenroll', text: 'Renovar um certificado existente (requer mTLS; sem certificado de cliente: 403). Um CSR sem SubjectAltName renova os nomes do próprio certificado, ou nenhum quando não tinha, em vez de um nome construído a partir do CN (RFC 7030 §4.2.2, v2.252)' },
          { label: '/csrattrs', text: 'Obter atributos de CSR recomendados pelo servidor: keyUsage, subjectAltName e extKeyUsage como OIDs simples (RFC 9908 §5.2, v2.252). csrattrs_legacy_encoding, definido por PATCH /api/v2/est/config, serve a forma anterior (os OIDs dentro de um extensionRequest) para um cliente que a necessite' },
          { label: 'Erros', text: 'As recusas de inscrição, o limite de taxa incluído, chegam como mensagem em texto simples (text/plain, RFC 8951 §5) dizendo o motivo, como um corpo que não é base64 nem um CSR PKCS#10, ou as restrições de nome da CA (v2.252)' },
          { label: '/serverkeygen', text: 'O servidor gera um par de chaves e retorna certificado + chave. A chave tem a força da CA emissora, na família da chave do pedido quando RSA ou EC (o seu tamanho ou curva é ignorado), senão a da CA, movida para o tipo mais próximo que as políticas permitem. A chave vem como PKCS#8 não cifrado sob TLS; um CSR que indique a chave do certificado mTLS (AsymmetricDecryptKeyIdentifier) recebe-a cifrada para esse certificado, por transporte de chave para RSA de 2048 bits ou mais (keyEncipherment) ou por acordo de chave para EC (keyAgreement), com os algoritmos que as SMIMECapabilities do CSR listam, num pacote de chave assinado por um certificado EST key generator que a CA emissora emite para esse fim (Ed25519 sob uma CA Ed448, v2.252)' },
        ]
      },
    ],
    tips: [
      'EST é o substituto moderno do SCEP: prefira EST para novas implantações',
      'Use autenticação mTLS para maior segurança. Basic Auth é um fallback',
      'O endpoint /simplereenroll requer que o cliente apresente seu certificado atual via mTLS',
      'Copie as URLs de endpoint da aba Endpoints EST para configurar seus clientes EST',
    ],
    warnings: [
      'EST requer HTTPS: o cliente deve confiar no certificado do servidor UCM ou na CA',
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

1. **Ativar EST**: Alternar o protocolo EST
2. **CA Assinante**: Selecionar qual Autoridade Certificadora assina certificados inscritos via EST
3. **Autenticação**: Configurar credenciais HTTP Basic Auth (usuário e senha)
4. **Validade do Certificado**: Período de validade padrão para certificados emitidos via EST (em dias)

### Salvando Configuração

Clique em **Salvar** para aplicar as alterações. Os endpoints EST ficam disponíveis imediatamente quando ativados.

## Autenticação

EST suporta dois métodos de autenticação:

### TLS Mútuo (mTLS): Recomendado

O cliente apresenta um certificado durante o handshake TLS. O UCM valida o certificado e autentica o cliente automaticamente.

- **Método mais forte**: identidade criptográfica do cliente
- **Obrigatório para** \`/simplereenroll\`: o cliente deve apresentar seu certificado atual
- **Certificado apresentado**: para \`/simpleenroll\` e \`/serverkeygen\`, um certificado assinado pela CA do EST deve ser um que ela ainda detém: certificados revogados, substituídos ou excluídos são recusados (RFC 7030 §3.3.2); um certificado de outra autoridade confiável continua sendo aceito
- **Depende de** configuração adequada de terminação TLS (proxy reverso deve passar \`SSL_CLIENT_CERT\` para o UCM)

### HTTP Basic Auth. Fallback

Autenticação com usuário e senha via HTTPS. Configurada nas Configurações EST.

- **Mais simples de configurar**: não precisa de certificado de cliente
- **Menos seguro**: credenciais transmitidas por requisição (protegido por HTTPS)
- **Use quando** a infraestrutura mTLS não estiver disponível

## Endpoints EST

Todos os endpoints estão em \`/.well-known/est/\`:

### GET /cacerts
Recuperar a cadeia de certificados da CA. **Sem autenticação necessária.**

Use isto para inicializar a confiança: clientes buscam o certificado da CA antes da inscrição.

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
Renovar um certificado existente. **Requer mTLS**: o cliente deve apresentar o certificado sendo renovado.

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

A chave gerada tem a força da CA emissora: a família da chave do pedido quando é RSA ou EC (o seu tamanho ou curva é ignorado), senão a da CA, movida para o tipo mais próximo que as políticas permitem.

A chave privada vem como PKCS#8 não cifrado (\`application/pkcs8\`), protegida pelo TLS. Para a receber cifrada, autentique-se com mTLS e coloque o identificador de chave do certificado de cliente no CSR (AsymmetricDecryptKeyIdentifier): a chave chega então num pacote de chave RFC 5958 envelopado para esse certificado, por transporte de chave para um certificado RSA de 2048 bits ou mais que declare keyEncipherment ou por acordo de chave (ECDH) para um certificado EC que declare keyAgreement, com os algoritmos de transporte ou acordo de chave e de conteúdo tirados das SMIMECapabilities do CSR, pela ordem do cliente. O pacote é assinado por um certificado "EST key generator" que a CA emissora emite na primeira utilização e renova sozinha; encadeia com a CA que \`/cacerts\` serve e tem a família de chave da CA, Ed25519 sob uma CA Ed448 (v2.252).

## Aba Endpoints EST

A aba Endpoints EST exibe:
- **URLs de Endpoint**: URLs prontas para copiar e colar para cada operação EST
- **Estatísticas de Inscrição**: inscrições totais, bem-sucedidas e com falha

## Exemplos de Integração

### Usando cliente est (libest)
Use o \`estclient\` com credenciais HTTP Basic (\`-u\` e \`-h\`) ou um certificado de cliente. As suas opções TLS-SRP não se aplicam: o UCM não oferece TLS-SRP.

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
  base64 -d | openssl pkcs7 -inform DER -print_certs -out cliente.pem
\`\`\`

A resposta é um PKCS#7 em base64 (somente certificados), não um certificado simples: leia-a com \`openssl pkcs7\`, não com \`openssl x509\`.

### Windows
O Windows não tem cliente EST integrado: \`certutil -enrollmentServerURL\` registra um serviço web de inscrição de certificados (WSTEP), não um servidor EST. Para máquinas Windows, use a Inscrição Automática do Windows (XCEP/WSTEP).

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
