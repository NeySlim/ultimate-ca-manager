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
          { label: 'Expirada', text: 'A solicitação não foi revisada antes do prazo' },
        ]
      },
    ],
    tips: [
      'Qualquer rejeição única interrompe imediatamente a aprovação — isso é intencional por segurança.',
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
A solicitação não foi revisada antes do prazo. Solicitações expiradas devem ser reenviadas.

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
