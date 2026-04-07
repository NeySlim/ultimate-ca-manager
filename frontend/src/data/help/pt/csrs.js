export default {
  helpContent: {
    title: 'Requisições de Assinatura de Certificado',
    subtitle: 'Gerenciar fluxo de trabalho de CSR',
    overview: 'Envie, revise e assine Requisições de Assinatura de Certificado. CSRs permitem que sistemas externos solicitem certificados das suas CAs sem expor chaves privadas.',
    sections: [
      {
        title: 'Fluxo de Trabalho',
        items: [
          { label: 'Gerar CSR', text: 'Criar um novo CSR com par de chaves diretamente no UCM' },
          { label: 'Enviar CSR', text: 'Aceitar arquivos CSR codificados em PEM ou colar texto PEM' },
          { label: 'Revisar', text: 'Inspecionar sujeito, SANs, tipo de chave e assinatura antes de assinar' },
          { label: 'Assinar', text: 'Selecionar uma CA, tipo de certificado, definir período de validade e emitir o certificado' },
          { label: 'Baixar', text: 'Baixar o CSR original em formato PEM' },
        ]
      },
      {
        title: 'Abas',
        items: [
          { label: 'Pendentes', text: 'CSRs aguardando revisão e assinatura' },
          { label: 'Histórico', text: 'CSRs previamente assinados ou rejeitados' },
        ]
      },
    ],
    tips: [
      'CSRs preservam a chave privada do solicitante — ela nunca sai do sistema dele',
      'Você pode adicionar uma chave privada a um CSR após a assinatura se necessário para exportação PKCS#12',
      'Use o modo Microsoft CA para assinar CSRs via AD CS quando conectado a uma PKI Windows',
    ],
  },
  helpGuides: {
    title: 'Requisições de Assinatura de Certificado',
    content: `
## Visão Geral

Requisições de Assinatura de Certificado (CSRs) permitem que sistemas externos solicitem certificados sem expor suas chaves privadas. O CSR contém a chave pública e informações do sujeito; a chave privada fica com o solicitante.

## Abas

### Pendentes
CSRs aguardando revisão e assinatura. Novos CSRs aparecem aqui após o envio.

### Histórico
CSRs previamente assinados ou rejeitados, com links para os certificados resultantes.

## Gerando um CSR

O UCM pode gerar um CSR e par de chaves diretamente:

1. Clique em **Gerar CSR**
2. Preencha os campos do Sujeito (CN obrigatório)
3. Adicione Nomes Alternativos do Sujeito se necessário
4. Selecione o tipo e tamanho da chave (RSA 2048/4096, ECDSA P-256/P-384)
5. Clique em **Gerar**

O CSR e a chave privada são criados e armazenados no UCM. O CSR aparece na aba Pendentes pronto para assinatura.

> 💡 Isso é conveniente quando você quer que o UCM gerencie todo o ciclo de vida — CSR, assinatura e armazenamento de chave.

## Enviando um CSR

1. Clique em **Enviar CSR**
2. Cole o texto PEM ou envie um arquivo PEM/DER
3. O UCM valida a assinatura do CSR e exibe os detalhes
4. O CSR aparece na aba Pendentes

## Revisando um CSR

Clique em um CSR para visualizar:
- **Sujeito** — CN, O, OU, C, etc.
- **SANs** — Nomes DNS, endereços IP, e-mails
- **Info da Chave** — Algoritmo, tamanho, impressão digital da chave pública
- **Assinatura** — Algoritmo e validade

## Assinando um CSR

### Assinatura por CA Local

1. Selecione um CSR pendente
2. Clique em **Assinar**
3. Escolha a **CA Assinante** (deve ter chave privada)
4. Selecione o **Tipo de Certificado** (servidor, cliente, assinatura de código, e-mail)
5. Defina o **período de validade** em dias
5. Opcionalmente aplique um modelo para Key Usage e extensões
6. Clique em **Assinar**

O certificado resultante aparece na página de Certificados.

### Assinatura por Microsoft CA

Se conexões com Microsoft CA estiverem configuradas, uma aba **Microsoft CA** aparece no modal de assinatura:

1. Selecione um CSR pendente e clique em **Assinar**
2. Mude para a aba **Microsoft CA**
3. Selecione a **conexão MS CA**
4. Selecione o **modelo de certificado** (carregado automaticamente da CA)
5. Clique em **Assinar**

Se o modelo requer aprovação do gerente, o UCM rastreia a solicitação pendente. Verifique o status no painel de detalhes do CSR.

### Inscrição em Nome de Outro (EOBO)

Ao assinar via Microsoft CA, você pode se inscrever em nome de outro usuário:

1. Selecione a conexão MS CA e o modelo
2. Marque **Inscrição em Nome de Outro (EOBO)**
3. Os campos **DN do Inscrito** e **UPN do Inscrito** são preenchidos automaticamente a partir do sujeito e e-mail SAN do CSR
4. Ajuste os valores se necessário e clique em **Assinar**

> ⚠️ EOBO requer um certificado de agente de inscrição configurado no servidor AD CS, e o modelo deve permitir inscrição em nome de outros usuários.

## Adicionando uma Chave Privada

Após a assinatura, você pode anexar uma chave privada ao certificado para exportação PKCS#12. Clique em **Adicionar Chave** no certificado assinado.

> 💡 Isso é útil quando o solicitante envia tanto o CSR quanto a chave de forma segura.

## Excluindo CSRs

A exclusão remove o CSR do UCM. Se o CSR já foi assinado, o certificado resultante não é afetado.
`
  }
}
