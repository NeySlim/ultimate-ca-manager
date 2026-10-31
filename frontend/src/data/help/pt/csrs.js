export default {
  helpContent: {
    title: 'Requisições de Assinatura de Certificado',
    subtitle: 'Gerenciar fluxo de trabalho de CSR',
    overview: 'Envie, revise e assine Requisições de Assinatura de Certificado. CSRs permitem que sistemas externos solicitem certificados das suas CAs sem expor chaves privadas.',
    sections: [
      {
        title: 'Fluxo de Trabalho',
        items: [
          { label: 'Gerar CSR', text: 'Criar um novo CSR com par de chaves diretamente no UCM: RSA, EC, Brainpool ou ML-DSA-44/65/87' },
          { label: 'Enviar CSR', text: 'Aceitar arquivos CSR codificados em PEM ou colar texto PEM' },
          { label: 'Revisar', text: 'Inspecionar sujeito, SANs, tipo de chave e assinatura antes de assinar' },
          { label: 'Assinar', text: 'Selecionar uma CA, tipo de certificado, definir período de validade e emitir o certificado' },
          { label: 'Adicionar nomes', text: 'Ao assinar, adicione nomes de email, DNS, IP ou URI aos do pedido, por exemplo o endereço de email de um certificado S/MIME pedido a partir de um smartcard. Passam pelas restrições de nomes da CA, pelas políticas de emissão e pela aprovação como quaisquer outros' },
          { label: 'Assinar novamente', text: 'No Histórico, volte a colocar um pedido assinado em Pendentes para o assinar de novo com outros EKUs, nomes ou validade, sem gerar uma nova chave' },
          { label: 'Baixar', text: 'Baixar o CSR original em formato PEM' },
          { label: 'Descarregar chave', text: 'Descarregar a chave privada de um CSR gerado no UCM, para a implantar junto de um certificado emitido por uma CA externa (requer a permissão read:private_keys)' },
        ]
      },
      {
        title: 'Abas',
        items: [
          { label: 'Pendentes', text: 'CSRs aguardando revisão e assinatura' },
          { label: 'Histórico', text: 'Pedidos assinados com o respetivo certificado: descarregue um ou outro, ou assine o pedido novamente. Os dois separadores paginam, pesquisam e ordenam sobre todos os pedidos; o Histórico pesquisa também pela CA de assinatura' },
        ]
      },
    ],
    tips: [
      'CSRs preservam a chave privada do solicitante: ela nunca sai do sistema dele',
      'Você pode adicionar uma chave privada a um CSR após a assinatura se necessário para exportação PKCS#12',
      'Um certificado importado para um CSR gerado no UCM completa esse CSR: o registo mantém a sua chave privada, pelo que o certificado é exportado com ela',
      'Um certificado para uma chave ML-DSA mantém apenas bits de assinatura: keyEncipherment, dataEncipherment e keyAgreement pedidos pelo modelo são removidos, e o resultado di-lo',
      'Use o modo Microsoft CA para assinar CSRs via AD CS quando conectado a uma PKI Windows',
      'Ao assinar, use "EKU extras" para adicionar Microsoft RDP, smartcard logon, IPsec ou qualquer OID: o EKU existente do CSR é reconstruído com o conjunto fundido',
      'Quando uma política ou a expiração da CA emissora reduz a validade solicitada, o resultado informa: "Issued for N day(s) instead of the M requested", com o motivo',
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
Pedidos assinados, cada um com o certificado que produziu. **Descarregar certificado** e **Descarregar CSR** obtêm um ou outro, e **Assinar novamente** volta a colocar o pedido em Pendentes.

## Gerando um CSR

O UCM pode gerar um CSR e par de chaves diretamente:

1. Clique em **Gerar CSR**
2. Preencha os campos do Sujeito (CN obrigatório)
3. Adicione Nomes Alternativos do Sujeito se necessário
4. Selecione o tipo e tamanho da chave (RSA 2048/4096, ECDSA P-256/P-384/P-521, Brainpool, ML-DSA-44/65/87)
5. Clique em **Gerar**

O CSR e a chave privada são criados e armazenados no UCM. O CSR aparece na aba Pendentes pronto para assinatura.

> 💡 Isso é conveniente quando você quer que o UCM gerencie todo o ciclo de vida. CSR, assinatura e armazenamento de chave.

Um certificado assinado para uma chave **ML-DSA** mantém apenas bits de assinatura: keyEncipherment, dataEncipherment e keyAgreement pedidos pelo modelo são removidos, e o resultado indica o que foi removido.

## Enviando um CSR

1. Clique em **Enviar CSR**
2. Cole o texto PEM ou envie um arquivo PEM/DER
3. O UCM valida a assinatura do CSR e exibe os detalhes
4. O CSR aparece na aba Pendentes

## Revisando um CSR

Clique em um CSR para visualizar:
- **Sujeito**: CN, O, OU, C, etc.
- **SANs**: Nomes DNS, endereços IP, e-mails
- **Info da Chave**: Algoritmo, tamanho, impressão digital da chave pública
- **Assinatura**: Algoritmo e validade

## Assinando um CSR

### Assinatura por CA Local

1. Selecione um CSR pendente
2. Clique em **Assinar**
3. Escolha a **CA Assinante** (deve ter chave privada)
4. Selecione o **Tipo de Certificado** (servidor, cliente, assinatura de código, e-mail)
5. Defina o **período de validade** em dias
6. Opcionalmente aplique um modelo para Key Usage e extensões
7. Opcionalmente **Adicionar nomes** (email, DNS, IP, URI) aos do pedido
8. Clique em **Assinar**

O certificado resultante aparece na página de Certificados.

> 💡 Um pedido gerado num smartcard traz muitas vezes apenas um CN. Para um certificado S/MIME, escolha o tipo Email e adicione o endereço: passa a ser o nome alternativo do sujeito do certificado. Os nomes adicionados passam pelas restrições de nomes da CA, pelas políticas de emissão e pela aprovação como quaisquer outros, e o aprovador vê-os.

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

### Assinatura por CA Externa

Para um certificado de uma CA pública ou de terceiros, mantenha a chave no UCM e envie apenas a requisição:

1. **Gerar CSR** no UCM, depois **Descarregar CSR** e submeta-o à CA externa
2. Quando o certificado for devolvido, importe-o na página de Certificados (**Importar**, ficheiro ou PEM colado) ou através de **Operações → Smart Importar**
3. O UCM reconhece o certificado pela sua chave pública, completa o CSR pendente e mantém a sua chave privada: o certificado é então exportado com a chave (PEM, PKCS#12, JKS) como qualquer outro

O CSR passa de **Pendentes** para **Histórico**. Se o certificado tiver de ser instalado noutro local, **Descarregar Chave Privada** no CSR pendente fornece a chave (requer a permissão read:private_keys, como qualquer exportação direta de chave).

> 💡 A correspondência é feita com base no par de chaves, pelo que continua a funcionar quando a CA reescreve o sujeito (muitas CAs públicas mantêm apenas o CN).

## Assinar um Pedido Novamente

Um dispositivo que guarda a sua chave, como um smartcard, muitas vezes não consegue produzir o mesmo pedido duas vezes. No **Histórico**, **Assinar novamente** volta a colocar o pedido guardado em **Pendentes**, com a mesma chave pública, para o assinar de novo com outros EKUs, nomes ou validade. O certificado já emitido fica como está: revogue-o se deixar de dever ser utilizado.

> 💡 A renovação continua recusada para um certificado cuja chave privada o UCM não detém, pois revogaria o número de série que o dispositivo ainda apresenta.

## Adicionando uma Chave Privada

Após a assinatura, você pode anexar uma chave privada ao certificado para exportação PKCS#12. Clique em **Adicionar Chave** no certificado assinado.

> 💡 Isso é útil quando o solicitante envia tanto o CSR quanto a chave de forma segura.

## Excluindo CSRs

A exclusão remove o CSR do UCM. Se o CSR já foi assinado, o certificado resultante não é afetado.
`
  }
}
