export default {
  helpContent: {
    title: 'Logs de Auditoria',
    subtitle: 'Rastreamento de atividades e conformidade',
    overview: 'Trilha de auditoria completa de todas as operações realizadas no UCM. Rastreie quem fez o quê, quando e de onde. Suporta filtragem, pesquisa, exportação e verificação de integridade.',
    sections: [
      {
        title: 'Filtros',
        items: [
          { label: 'Tipo de Ação', text: 'Filtrar por tipo de operação (criar, atualizar, excluir, login, etc.)' },
          { label: 'Usuário', text: 'Filtrar pelo usuário que realizou a ação' },
          { label: 'Status', text: 'Mostrar apenas operações bem-sucedidas ou com falha' },
          { label: 'Intervalo de Datas', text: 'Definir datas de início/fim para limitar a janela de tempo' },
          { label: 'Pesquisa', text: 'Pesquisa de texto livre em todas as entradas de log' },
        ]
      },
      {
        title: 'Ações',
        items: [
          { label: 'Exportar', text: 'Baixar logs em formato JSON ou CSV' },
          { label: 'Limpeza', text: 'Purgar logs antigos com retenção configurável (dias)' },
          { label: 'Verificar Integridade', text: 'Verificar integridade da cadeia de logs para detectar adulteração' },
        ]
      },
    ],
    tips: [
      'Exporte logs regularmente para fins de conformidade e arquivamento',
      'Tentativas de login com falha são registradas com IP de origem para monitoramento de segurança',
      'As entradas de log incluem User Agent para identificar aplicações clientes',
    ],
    warnings: [
      'A limpeza de logs é irreversível — dados exportados não podem ser reimportados',
    ],
  },
  helpGuides: {
    title: 'Logs de Auditoria',
    content: `
## Visão Geral

Trilha de auditoria completa de todas as operações no UCM. Cada ação — emissão de certificado, revogação, login de usuário, alteração de configuração — é registrada com detalhes sobre quem, o quê, quando e onde.

## Detalhes da Entrada de Log

Cada entrada de log registra:
- **Data/Hora** — Quando a ação ocorreu
- **Usuário** — Quem realizou a ação
- **Ação** — O que foi feito (criar, atualizar, excluir, login, etc.)
- **Recurso** — O que foi afetado (certificado, CA, usuário, etc.)
- **Status** — Sucesso ou falha
- **Endereço IP** — IP de origem da requisição
- **User Agent** — Identificador da aplicação cliente
- **Detalhes** — Contexto adicional (mensagens de erro, valores alterados)

## Filtragem

### Por Tipo de Ação
Filtrar por categoria de operação:
- Operações de certificado (emitir, revogar, renovar, exportar)
- Operações de CA (criar, importar, excluir)
- Operações de usuário (login, logout, criar, atualizar)
- Operações do sistema (alteração de configurações, backup, restauração)

### Por Usuário
Mostrar apenas ações realizadas por um usuário específico.

### Por Status
- **Sucesso** — Operações concluídas com sucesso
- **Falha** — Operações que falharam (falhas de autenticação, permissão negada, erros)

### Por Intervalo de Datas
Defina datas **De** e **Até** para limitar a janela de tempo.

### Pesquisa de Texto
Pesquisa de texto livre em todos os campos de log.

## Exportação

Exporte logs filtrados em:
- **JSON** — Legível por máquina, inclui todos os campos
- **CSV** — Compatível com planilhas, inclui campos principais

As exportações incluem apenas os resultados filtrados atualmente.

## Limpeza

Purgar logs antigos com base no período de retenção:
1. Clique em **Limpeza**
2. Defina o período de retenção em dias
3. Confirme a limpeza

> ⚠ A limpeza de logs é irreversível. Exporte logs importantes antes de purgar.

## Verificação de Integridade

Clique em **Verificar Integridade** para verificar a cadeia de logs de auditoria. O UCM usa encadeamento de hash para detectar se alguma entrada de log foi adulterada ou excluída.

## Encaminhamento Syslog

Configure o encaminhamento remoto de syslog em **Configurações → Auditoria** para enviar eventos de log para um servidor SIEM ou syslog externo em tempo real.
`
  }
}
