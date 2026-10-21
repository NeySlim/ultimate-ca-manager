export default {
  helpContent: {
    title: 'Políticas de Certificado',
    subtitle: 'Regras de emissão e aplicação de conformidade',
    overview: 'Defina e gerencie políticas de certificado que controlam regras de emissão, requisitos de chave, limites de validade e fluxos de aprovação. As políticas são avaliadas em ordem de prioridade quando certificados são solicitados.',
    sections: [
      {
        title: 'Operações',
        items: [
          { label: 'Emissão', text: 'O formulário de emissão, a assinatura de CSR e em lote, e as renovações feitas por um operador' },
          { label: 'Renovação', text: 'Renovações por um operador, uma ou em lote, e pelo agendador, que coloca a sua renovação na fila em vez de a executar' },
          { label: 'Revogação', text: 'Revogações de certificados e de CAs intermédias por um operador (uma CA também sob as políticas delimitadas a ela); um cliente ACME não pode aguardar uma decisão, por isso a sua revogação é recusada' },
          { label: 'Várias ao mesmo tempo', text: 'Uma política pode governar várias operações; uma sem nenhuma (um antigo tipo de renovação ou revogação, nunca aplicado) não governa nada até você escolher' },
        ]
      },
      {
        title: 'Regras',
        items: [
          { label: 'Validade Máxima', text: 'Tempo máximo de vida do certificado em dias' },
          { label: 'Tipos de Chave Permitidos', text: 'Restringir quais algoritmos e tamanhos de chave podem ser usados' },
          { label: 'Restrições de SAN', text: 'Limitar o número de SANs e aplicar padrões de nomes DNS' },
          { label: 'Hashes de Assinatura Permitidos', text: 'SHA-256, SHA-384 ou SHA-512; nenhum selecionado permite qualquer um. Quando ninguém escolheu o hash, aplica-se o padrão se permitido, senão o mais fraco permitido. O formulário de emissão e Criar CA oferecem apenas os tipos de chave e hashes que as políticas permitem' },
        ]
      },
      {
        title: 'Fluxos de Aprovação',
        items: [
          { label: 'Grupos de Aprovação', text: 'Atribuir um grupo de usuários responsável por aprovar solicitações' },
          { label: 'Mín. Aprovadores', text: 'Número de aprovações necessárias antes da emissão' },
          { label: 'Notificações', text: 'E-mail quando a política recusa uma operação ou a retém para aprovação; enviado aos endereços listados, senão aos seus aprovadores. Uma recusa repetida é notificada uma vez por hora' },
        ]
      },
    ],
    tips: [
      'Número de prioridade menor = maior precedência. Use 1–10 para políticas críticas.',
      'Atribua políticas a CAs específicas para controle granular.',
      'Ative notificações para detectar violações de políticas rapidamente.',
    ],
  },
  helpGuides: {
    title: 'Políticas de Certificado',
    content: `
## Visão Geral

Políticas de certificado definem as regras e restrições aplicadas quando certificados são emitidos, renovados ou revogados. As políticas são avaliadas em **ordem de prioridade** (número menor = maior precedência) e podem ser atribuídas a CAs específicas.

## Operações

Uma política governa uma ou mais operações: a sua exigência de aprovação e as suas regras aplicam-se a elas.

### Emissão
O formulário de emissão, a assinatura de CSR e em lote, e as renovações feitas por um operador. Esta é a escolha mais comum. Controla tipos de chave, períodos de validade, restrições de SAN e se aprovação é necessária.

### Renovação
Renovações por um operador, uma ou em lote, e pelo agendador. Sob uma política de renovação que exige aprovação, o agendador coloca a renovação na fila em vez de a executar, e a aprovação reassina a chave detida pelo servidor.

### Revogação
Revogações de certificados (um, em lote, a partir dos certificados de usuário) e de CAs intermédias. Delimitada pela CA emissora, pelo modelo e pelo padrão DNS; a revogação de uma CA é retida também pelas políticas delimitadas a essa CA, pois todos os certificados que ela emitiu caem com ela. As outras regras não se aplicam. Um cliente ACME não pode aguardar uma decisão: a sua revogação é recusada e deixada aos operadores. Remover um registro mTLS é recusado até que o seu certificado seja revogado, quem quer que o detenha; os administradores ignoram a fila.

Uma política criada antes de existirem as operações mantém o que fazia: uma política de emissão continua a sê-lo, e um tipo de renovação ou revogação, nunca aplicado, não governa nada até você escolher as suas operações.

## Configuração de Regras

### Validade Máxima
Tempo máximo de vida do certificado em dias. Valores comuns:
- **90 dias**: Automação de curta duração (estilo ACME)
- **397 dias**: Baseline CA/Browser Forum para TLS público
- **730 dias**: PKI interna/privada
- **365 dias**: Assinatura de código

### Tipos de Chave Permitidos
Restringir quais algoritmos e tamanhos de chave podem ser usados:
- **RSA-2048**: Mínimo para confiança pública
- **RSA-3072**: O tamanho de chave padrão para novas CAs
- **RSA-4096**: Segurança superior, certificados maiores
- **EC-P256**: Moderno, rápido, recomendado
- **EC-P384**: Curva elíptica de segurança superior
- **EC-P521**: Segurança máxima (raramente necessário)

**Hashes de Assinatura Permitidos** restringe o hash da assinatura da mesma forma (SHA-256, SHA-384, SHA-512); nenhum selecionado permite qualquer um. Quando ninguém escolheu o hash, aplica-se o padrão se permitido, senão o mais fraco permitido. O formulário de emissão e Criar CA oferecem apenas os tipos de chave e hashes que as políticas permitem.

### Restrições de SAN
- **Máx. Nomes DNS**: Limitar o número de Nomes Alternativos do Sujeito
- **Padrão DNS**: Restringir a padrões de domínio específicos (ex.: \`*.empresa.com\`)

## Fluxos de Aprovação

Quando **Exigir Aprovação** está ativado, a emissão do certificado é pausada até que o número necessário de aprovadores do grupo atribuído tenha aprovado a solicitação.

### Configuração
- **Grupo de Aprovação**: Selecionar um grupo de usuários responsável por aprovações
- **Mín. Aprovadores**: Número de aprovações necessárias (ex.: 2 de 3 membros do grupo)
- **Notificações**: e-mail quando a política recusa uma operação (uma regra violada) ou a retém para aprovação. Vai para os endereços de notificação da política, senão para seus aprovadores (os membros do grupo de aprovação, ou todo usuário que pode aprovar). Cada solicitação retida é notificada uma vez, com um link para ela; a mesma recusa repetida, por exemplo por um cliente ACME que tenta de novo, uma vez por hora. O SMTP deve estar configurado

> 💡 Use fluxos de aprovação para certificados de alto valor como assinatura de código e certificados curinga.

## Sistema de Prioridade

As políticas são avaliadas em ordem de prioridade. Números menores têm maior precedência:
- **1–10**: Políticas de segurança críticas (assinatura de código, curinga)
- **10–20**: Conformidade padrão (TLS público, PKI interna)
- **20+**: Padrões permissivos

Quando múltiplas políticas correspondem a uma solicitação de certificado, a política de maior prioridade (menor número) prevalece.

## Escopo

### Todas as CAs
A política se aplica a todas as CAs no sistema. Use para regras de toda a organização.

### CA Específica
A política se aplica apenas a certificados emitidos pela CA selecionada. Use para controle granular.

## Políticas Padrão

O UCM vem com 5 políticas integradas que refletem as melhores práticas PKI do mundo real:
- **Assinatura de Código** (prioridade 5): Chaves fortes, aprovação necessária
- **Certificados Curinga** (prioridade 8): Aprovação necessária, máx. 10 SANs
- **TLS para Servidor Web** (prioridade 10): Conforme CA/B Forum, máx. 397 dias
- **Automação de Curta Duração** (prioridade 15): 90 dias estilo ACME
- **PKI Interna** (prioridade 20): 730 dias, regras relaxadas

> 💡 Personalize ou desative políticas padrão para corresponder aos requisitos da sua organização.
`
  }
}
