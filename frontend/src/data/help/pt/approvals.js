export default {
  helpContent: {
    title: 'Solicitações de Aprovação',
    subtitle: 'Gerenciamento do fluxo de aprovação de certificados',
    overview: 'Revise e gerencie solicitações de aprovação de certificados. Quando uma política requer aprovação, a emissão do certificado é pausada até que o número necessário de aprovadores tenha revisado e aprovado a solicitação.',
    sections: [
      {
        title: 'Ciclo de Vida da Solicitação',
        items: [
          { label: 'Pendente', text: 'Aguardando revisão — o certificado ainda não pode ser emitido' },
          { label: 'Aprovada', text: 'Todas as aprovações necessárias foram recebidas — o certificado pode ser emitido' },
          { label: 'Rejeitada', text: 'Qualquer rejeição interrompe imediatamente a solicitação' },
          { label: 'Expirada', text: 'Não decidida em sete dias; encerrada como expirada e nunca contada como pendente' },
        ]
      },
      {
        title: 'De onde vêm as solicitações',
        items: [
          { label: 'Formulário de emissão', text: 'Uma solicitação de certificado que corresponde a uma política que exige aprovação' },
          { label: 'Assinar CSR e assinatura em lote', text: 'Assinar uma solicitação armazenada, sozinha ou a partir de Operações, entra na fila da mesma forma; a aprovação executa a assinatura' },
          { label: 'Renovação', text: 'Renovar um certificado, sozinho ou em lote, também entra na fila; uma renovação que não poderia ser atendida (revogado, chave não detida pelo servidor) é recusada de imediato' },
          { label: 'Administradores', text: 'Ignoram a fila em todos os caminhos, como no formulário de emissão' },
        ]
      },
      {
        title: 'Solicitações encerradas por você',
        items: [
          { label: 'Assinada ou renovada diretamente', text: 'Uma solicitação na fila cujo alvo um administrador assinou ou renovou entretanto é encerrada como aprovada por essa ação e vinculada ao certificado' },
          { label: 'Excluído ou revogado', text: 'Uma solicitação cujo alvo foi excluído ou revogado é encerrada como rejeitada; uma suspensão de certificado mantém a solicitação de renovação aguardando a remoção da suspensão' },
          { label: 'Já atendida', text: 'Aprovar uma solicitação já atendida encerra-a sobre o certificado existente; aprovar uma de várias solicitações para o mesmo alvo encerra as outras como aprovadas por você' },
          { label: 'Alvo inexistente', text: 'Aprovar uma solicitação cuja solicitação armazenada, certificado ou CA não existe mais encerra-a como rejeitada' },
          { label: 'Prazo', text: 'Uma solicitação aguarda sete dias; passado esse prazo, é encerrada como expirada, nunca contada como pendente, e o agendador de renovação retoma o seu certificado' },
        ]
      },
    ],
    tips: [
      'Qualquer rejeição única interrompe imediatamente a aprovação — isso é intencional por segurança.',
      'Enquanto uma renovação aguarda aprovação, o agendador deixa o certificado a essa decisão, desde que ela possa ocorrer antes de o certificado expirar.',
      'Os comentários de aprovação são registrados na trilha de auditoria para conformidade.',
    ],
  },
  helpGuides: {
    title: 'Solicitações de Aprovação',
    content: `
## Visão Geral

A página de Aprovações mostra todas as solicitações de certificado que requerem aprovação manual antes da emissão. Os fluxos de aprovação são configurados em **Políticas** — quando uma política tem "Exigir Aprovação" ativado, qualquer solicitação de certificado correspondente cria uma solicitação de aprovação aqui.

## Ciclo de Vida da Solicitação

### Pendente
A solicitação está aguardando revisão. O certificado não pode ser emitido até que o número necessário de aprovadores tenha aprovado. Solicitações pendentes aparecem primeiro por padrão.

### Aprovada
Todas as aprovações necessárias foram recebidas. O certificado será emitido automaticamente após a aprovação.

### Rejeitada
Qualquer rejeição única interrompe imediatamente a solicitação. O certificado não será emitido. Um comentário de rejeição é obrigatório para explicar o motivo.

### Expirada
A solicitação não foi decidida em sete dias. Solicitações expiradas devem ser reenviadas.

## De onde vêm as solicitações
Além do formulário de emissão, uma política que exige aprovação também coloca na fila:
- **Assinar CSR** e **assinatura em lote** a partir de Operações: a aprovação executa a assinatura
- **Renovar** e **renovação em lote**: a aprovação executa a renovação; uma renovação que não poderia ser atendida (certificado revogado, chave não detida pelo servidor) é recusada de imediato em vez de entrar na fila

Os administradores ignoram a fila em todos os caminhos.

## Solicitações encerradas por você
- Uma solicitação na fila cujo alvo um administrador **assinou ou renovou diretamente** entretanto é encerrada como aprovada por essa ação e vinculada ao certificado
- Uma solicitação cujo alvo foi **excluído ou revogado** é encerrada como rejeitada; uma suspensão de certificado mantém a solicitação de renovação aguardando a remoção da suspensão
- Aprovar uma solicitação **já atendida** encerra-a sobre o certificado existente; aprovar uma de várias solicitações para o mesmo alvo encerra as outras como aprovadas por você
- Aprovar uma solicitação cuja solicitação armazenada, certificado ou CA **não existe mais** encerra-a como rejeitada

Os webhooks são notificados desses encerramentos como para uma rejeição.

## Prazo
Uma solicitação aguarda **sete dias** por uma decisão. Passado esse prazo, é encerrada como expirada, nunca é contada como pendente e o agendador de renovação retoma o seu certificado. Enquanto uma renovação aguarda aprovação, o agendador deixa o certificado a essa decisão, desde que ela possa ocorrer antes de o certificado expirar.

## Aprovando uma Solicitação

1. Clique em uma solicitação pendente para ver seus detalhes
2. Revise os detalhes do certificado, solicitante e política associada
3. Clique em **Aprovar** e opcionalmente adicione um comentário
4. A aprovação é registrada com seu nome de usuário e data/hora

## Rejeitando uma Solicitação

1. Clique em uma solicitação pendente para ver seus detalhes
2. Clique em **Rejeitar**
3. Insira um **motivo de rejeição** (obrigatório) — isso é registrado para conformidade de auditoria
4. A solicitação é imediatamente interrompida

> ⚠ Qualquer rejeição única interrompe toda a solicitação. Isso é intencional — se qualquer revisor identificar um problema, a emissão não deve prosseguir.

## Histórico de Aprovação

Cada solicitação mantém uma linha do tempo completa de aprovação mostrando:
- Quem aprovou ou rejeitou (nome de usuário)
- Quando a ação foi tomada (data/hora)
- Comentário fornecido (se houver)

Este histórico é imutável e faz parte da trilha de auditoria.

## Filtragem

Use a barra de filtro de status no topo para mostrar:
- **Pendente** — Solicitações aguardando sua revisão
- **Aprovada** — Solicitações aprovadas recentemente
- **Rejeitada** — Solicitações rejeitadas com motivos
- **Total** — Todas as solicitações independente do status

## Permissões

- **read:approvals** — Visualizar solicitações de aprovação
- **write:approvals** — Aprovar ou rejeitar solicitações

> 💡 Configure notificações por e-mail nas políticas para que os aprovadores sejam alertados quando novas solicitações chegarem.
`
  }
}
