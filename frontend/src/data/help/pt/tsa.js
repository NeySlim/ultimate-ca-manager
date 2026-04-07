export default {
  helpContent: {
    title: 'TSA',
    subtitle: 'Autoridade de Carimbo de Tempo',
    overview: 'TSA (RFC 3161) fornece carimbos de tempo confiáveis que provam que um documento ou hash existia em um ponto específico no tempo. Usado para assinatura de código, conformidade legal e trilhas de auditoria.',
    sections: [
      {
        title: 'Abas',
        items: [
          { label: 'Configurações', text: 'Ativar TSA, selecionar a CA assinante e configurar o OID da política TSA' },
          { label: 'Informações', text: 'URL do endpoint TSA, exemplos de uso com OpenSSL e estatísticas de requisições' },
        ]
      },
      {
        title: 'Configuração',
        items: [
          { label: 'CA Assinante', text: 'A CA cuja chave privada assina tokens de carimbo de tempo — deve ser uma CA válida e não expirada' },
          { label: 'OID da Política', text: 'Object Identifier para a política TSA (ex.: 1.2.3.4.1) — incluído em cada resposta de carimbo de tempo' },
          { label: 'Ativar/Desativar', text: 'Alternar o endpoint TSA sem perder a configuração' },
        ]
      },
      {
        title: 'Uso',
        items: [
          { label: 'Criar Requisição', text: 'openssl ts -query -data arquivo.txt -sha256 -no_nonce -out requisicao.tsq' },
          { label: 'Enviar para TSA', text: 'curl -H "Content-Type: application/timestamp-query" --data-binary @requisicao.tsq https://seu-servidor/tsa -o resposta.tsr' },
          { label: 'Verificar', text: 'openssl ts -verify -data arquivo.txt -in resposta.tsr -CAfile cadeia-ca.pem' },
        ]
      },
    ],
    tips: [
      'Carimbos de tempo TSA são usados em assinatura de código para garantir que assinaturas permaneçam válidas após a expiração do certificado',
      'O endpoint TSA aceita HTTP POST com Content-Type: application/timestamp-query',
      'Use algoritmos de hash SHA-256 ou mais fortes ao criar requisições de carimbo de tempo',
      'Nenhuma autenticação é necessária — o endpoint TSA é acessível publicamente como CRL/OCSP',
    ],
    warnings: [
      'Uma CA assinante válida deve ser configurada antes de ativar o TSA',
      'O endpoint TSA é um endpoint de protocolo público — não coloque dados sensíveis nas requisições de carimbo de tempo',
    ],
  },
  helpGuides: {
    title: 'Protocolo TSA',
    content: `
## Visão Geral

Time Stamp Authority (TSA) implementa a **RFC 3161** para fornecer carimbos de tempo confiáveis que provam criptograficamente que um documento, hash ou assinatura digital existia em um ponto específico no tempo. TSA é amplamente usado para assinatura de código, conformidade legal, arquivamento de longo prazo e trilhas de auditoria.

## Como Funciona

1. **Cliente cria uma requisição de carimbo de tempo** — faz hash de um arquivo com SHA-256/SHA-512 e cria um \`TimeStampReq\` (codificado em ASN.1 DER)
2. **Cliente envia requisição para TSA** — HTTP POST para o endpoint \`/tsa\` com \`Content-Type: application/timestamp-query\`
3. **UCM assina o carimbo de tempo** — a CA configurada assina o hash + hora atual em um \`TimeStampResp\`
4. **Cliente recebe e armazena a resposta** — o arquivo \`.tsr\` pode posteriormente provar que o documento existia naquele momento

## Configuração

### Aba Configurações

1. **Ativar TSA** — Alternar o servidor TSA
2. **CA Assinante** — Selecionar qual Autoridade Certificadora assina tokens de carimbo de tempo
3. **OID da Política** — Object Identifier para a política TSA (ex.: \`1.2.3.4.1\`), incluído em cada resposta de carimbo de tempo

### Escolhendo uma CA Assinante

A chave privada da CA assinante é usada para assinar cada token de carimbo de tempo. Melhores práticas:

- Use uma **sub-CA dedicada** para carimbos de tempo em vez da sua CA raiz
- O certificado da CA deve incluir o Extended Key Usage **id-kp-timeStamping** (OID 1.3.6.1.5.5.7.3.8)
- Garanta que o certificado da CA tenha **validade suficiente** — carimbos de tempo devem permanecer verificáveis por anos

### OID da Política

O OID da Política identifica a política TSA sob a qual os carimbos de tempo são emitidos. Ele é incorporado em cada \`TimeStampResp\`.

- Padrão: \`1.2.3.4.1\` (placeholder)
- Para produção, registre um OID sob o arco da sua organização ou use um do seu CP/CPS

## Aba Informações

A aba Informações exibe:

- **URL do Endpoint TSA** — URL pronta para copiar e colar para configuração do cliente
- **Exemplos de Uso** — Comandos OpenSSL para criar requisições, enviá-las e verificar respostas
- **Estatísticas** — Total de requisições de carimbo de tempo processadas (bem-sucedidas e com falha)

## Exemplos de Uso

### Criar uma Requisição de Carimbo de Tempo

\`\`\`bash
# Fazer hash de um arquivo e criar uma requisição de carimbo de tempo
openssl ts -query -data arquivo.txt -sha256 -no_nonce -out requisicao.tsq
\`\`\`

### Enviar Requisição para TSA

\`\`\`bash
# Enviar a requisição e receber uma resposta de carimbo de tempo
curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @requisicao.tsq \\
  https://seu-servidor:8443/tsa -o resposta.tsr
\`\`\`

### Verificar um Carimbo de Tempo

\`\`\`bash
# Verificar a resposta de carimbo de tempo contra o arquivo original
openssl ts -verify -data arquivo.txt -in resposta.tsr \\
  -CAfile cadeia-ca.pem
\`\`\`

### Assinatura de Código com Carimbos de Tempo

Ao assinar código, adicione a URL TSA para garantir que assinaturas permaneçam válidas após a expiração do certificado:

\`\`\`bash
# Assinar com carimbo de tempo (osslsigncode)
osslsigncode sign -certs cert.pem -key key.pem \\
  -ts https://seu-servidor:8443/tsa \\
  -in app.exe -out app-assinado.exe

# Assinar com carimbo de tempo (signtool.exe no Windows)
signtool sign /fd SHA256 /tr https://seu-servidor:8443/tsa \\
  /td SHA256 /f cert.pfx app.exe
\`\`\`

### Carimbos de Tempo em Documentos PDF

\`\`\`bash
# Criar um carimbo de tempo separado para um PDF
openssl ts -query -data documento.pdf -sha256 -cert \\
  -out documento.tsq

curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @documento.tsq \\
  https://seu-servidor:8443/tsa -o documento.tsr
\`\`\`

## Detalhes do Protocolo

| Propriedade | Valor |
|-------------|-------|
| RFC | 3161 (Internet X.509 PKI TSP) |
| Endpoint | \`/tsa\` (POST) |
| Content-Type | \`application/timestamp-query\` |
| Tipo de Resposta | \`application/timestamp-reply\` |
| Algoritmos de Hash | SHA-256, SHA-384, SHA-512, SHA-1 (legado) |
| Autenticação | Nenhuma (endpoint público) |
| Transporte | HTTP ou HTTPS |

## Considerações de Segurança

- O endpoint TSA é **público** — nenhuma autenticação é necessária (mesmo que CRL/OCSP)
- Cada resposta de carimbo de tempo é **assinada** pela chave da CA — clientes verificam a assinatura para garantir autenticidade
- Use algoritmos de hash **SHA-256 ou mais fortes** ao criar requisições (SHA-1 é aceito mas desencorajado)
- O TSA **não** vê o documento original — apenas o hash é transmitido
- Considere **limitação de taxa** se o endpoint TSA estiver exposto na internet

> 💡 Carimbos de tempo são essenciais para assinatura de código: eles garantem que seu software assinado permaneça confiável mesmo após o certificado de assinatura expirar.
`
  }
}
