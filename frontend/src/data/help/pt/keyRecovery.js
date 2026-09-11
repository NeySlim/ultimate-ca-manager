export default {
  helpContent: {
    title: 'Recuperação de chaves',
    subtitle: 'Recuperar chaves privadas arquivadas sob controlo duplo',
    overview: 'A recuperação de chaves obtém a chave privada arquivada de um certificado emitido anteriormente através de um fluxo de trabalho sujeito a aprovação e totalmente auditado. Existe para chaves que não foram exportadas no momento da emissão (o preset não o permitia, ou a exportação foi omitida) e que são necessárias mais tarde — com um rasto de aprovação associado à obtenção.',
    sections: [
      {
        title: 'Fluxo de trabalho',
        items: [
          { label: 'Pedido', text: 'Um utilizador pede a recuperação da chave arquivada de um certificado específico, indicando um motivo' },
          { label: 'Aprovação (quatro olhos)', text: 'Um segundo operador autorizado analisa e aprova — o requerente não pode aprovar o seu próprio pedido' },
          { label: 'Transferência', text: 'Uma vez aprovada, a chave é disponibilizada como um pacote PKCS#12 protegido por palavra-passe' },
        ]
      },
      {
        title: 'Requisitos',
        items: [
          { label: 'Chave arquivada', text: 'A chave privada do certificado tem de estar armazenada na base de dados — a recuperação não pode reconstruir uma chave que nunca foi arquivada' },
          { label: 'Controlo duplo', text: 'O pedido e a aprovação são ações separadas realizadas por pessoas diferentes; cada passo é registado no registo de auditoria' },
        ]
      },
    ],
    tips: [
      'A recuperação de chaves destina-se a chaves que não foram exportadas quando o certificado foi emitido; não substitui a restrição da exportação de chaves no momento da emissão.',
      'Cada pedido, aprovação e transferência é registado no registo de auditoria para fins de conformidade.',
    ],
    warnings: [
      'Um certificado cuja chave privada nunca foi arquivada não pode ser recuperado — não há nada para disponibilizar.',
    ],
  },
  helpGuides: {
    title: 'Recuperação de chaves',
    content: `
## Visão geral

A recuperação de chaves obtém a **chave privada arquivada** de um certificado emitido anteriormente através de um fluxo de trabalho sujeito a aprovação e totalmente auditado. Destina-se a chaves que **não foram exportadas no momento da emissão** — o preset não permitia a exportação, ou esta foi simplesmente omitida — e que são necessárias mais tarde, com um rasto de aprovação associado à obtenção.

A recuperação só funciona se a chave privada tiver sido arquivada (armazenada na base de dados) na emissão. Não pode reconstruir uma chave que nunca foi conservada.

## Fluxo de trabalho

### 1. Pedido
Um utilizador abre um pedido de recuperação para um certificado específico e indica um motivo. O pedido é registado e passa ao estado pendente.

### 2. Aprovação (quatro olhos)
Um segundo operador autorizado analisa o pedido e aprova-o. O requerente **não pode aprovar o seu próprio pedido** — o pedido e a aprovação são ações separadas realizadas por pessoas diferentes (controlo duplo).

### 3. Transferência
Uma vez aprovada, a chave arquivada é disponibilizada como um pacote **PKCS#12 protegido por palavra-passe**. A transferência é registada no registo de auditoria.

## Requisitos

- **Chave arquivada** — a chave privada do certificado tem de estar presente na base de dados. Os certificados cuja chave nunca foi arquivada não podem ser recuperados.
- **Controlo duplo** — o pedido e a aprovação são passos distintos realizados por utilizadores diferentes.

## Permissões

- **read:key_recovery** — Pedir uma recuperação e consultar os pedidos
- **admin** — Aprovar ou recusar um pedido de recuperação pendente
- **read:private_keys** — Âmbito exclusivo de admin, necessário para a exportação *direta* da chave privada a partir da página Certificados (contornando este fluxo de trabalho)

## O que é (e o que não é)

A recuperação de chaves acrescenta um **rasto de aprovação** à obtenção de uma chave arquivada após a emissão. Não substitui a restrição da exportação de chaves privadas nos presets — se um perfil já pode exportar chaves diretamente, trata-se de uma via de acesso distinta a controlar por si própria.

> 💡 Cada pedido, aprovação e transferência é registado no registo de auditoria para fins de conformidade.
`
  }
}
