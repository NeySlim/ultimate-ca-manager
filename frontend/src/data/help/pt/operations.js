export default {
  helpContent: {
    title: 'Operações',
    subtitle: 'Importação, exportação e ações em massa',
    overview: 'Centro de operações centralizado. Importe certificados de arquivos ou OPNsense, exporte pacotes em formatos PEM/P7B e realize ações em massa em todos os tipos de recursos com pesquisa e filtros inline.',
    sections: [
      {
        title: 'Abas da Barra Lateral',
        items: [
          { label: 'Importar', text: 'Importação Inteligente com detecção automática de formato, além de sincronização OPNsense para importar certificados de firewalls' },
          { label: 'Exportar', text: 'Baixar pacotes de certificados por tipo de recurso em formato PEM ou P7B via cartões de ação' },
          { label: 'Ações em Massa', text: 'Selecionar um tipo de recurso e realizar operações em lote em múltiplos itens' },
        ]
      },
      {
        title: 'Ações em Massa',
        items: [
          { label: 'Certificados', text: 'Revogar, renovar, excluir ou exportar — filtrar por status e CA emissora' },
          { label: 'CAs', text: 'Excluir ou exportar autoridades certificadoras' },
          { label: 'CSRs', text: 'Assinar com uma CA ou excluir solicitações pendentes' },
          { label: 'Modelos', text: 'Excluir modelos de certificado' },
          { label: 'Usuários', text: 'Excluir contas de usuário' },
        ]
      },
    ],
    tips: [
      'Use os chips de recurso para alternar rapidamente entre tipos de recursos',
      'A pesquisa inline e os filtros (Status, CA) permitem refinar itens sem sair da barra de ferramentas',
      'Alterne entre os modos de visualização Tabela e Cesta (painel de transferência) no desktop',
      'Visualize as alterações antes de confirmar operações em massa',
    ],
    warnings: [
      'A exclusão em massa é irreversível — sempre crie um backup primeiro',
      'A revogação em massa publicará CRLs atualizadas para todas as CAs afetadas',
    ],
  },
  helpGuides: {
    title: 'Operações',
    content: `
## Visão Geral

Operações em massa e gerenciamento de dados. Realize ações em lote em múltiplos recursos simultaneamente.

## Aba Importar/Exportar

Igual à página de Importação/Exportação — assistente de Importação Inteligente e funcionalidade de exportação em massa.

## Aba OPNsense

Igual à integração OPNsense de Importação/Exportação — conecte, navegue e importe do OPNsense.

## Ações em Massa

Realize operações em lote em múltiplos recursos de uma vez.

### Como Funciona
1. Selecione o **tipo de recurso** (Certificados, CAs, CSRs, Modelos, Usuários)
2. Navegue pelos itens disponíveis no **painel esquerdo**
3. Mova itens para o **painel direito** (selecionados) usando as setas de transferência
4. Escolha a **ação** a ser realizada
5. Confirme e execute

### Ações Disponíveis por Recurso

#### Certificados
- **Revogar em Massa** — Revogar múltiplos certificados de uma vez
- **Renovar em Massa** — Renovar múltiplos certificados
- **Exportar em Massa** — Baixar certificados selecionados como pacote
- **Excluir em Massa** — Remover permanentemente certificados selecionados

#### CAs
- **Exportar em Massa** — Baixar CAs selecionadas
- **Excluir em Massa** — Remover CAs selecionadas (não devem ter CAs filhas)

#### CSRs
- **Assinar em Massa** — Assinar múltiplos CSRs com uma CA selecionada
- **Excluir em Massa** — Remover CSRs selecionados

#### Modelos
- **Exportar em Massa** — Exportar como JSON
- **Excluir em Massa** — Remover modelos selecionados

#### Usuários
- **Desativar em Massa** — Desativar contas de usuário selecionadas
- **Excluir em Massa** — Remover permanentemente usuários selecionados

> ⚠ Operações em massa são irreversíveis. Sempre crie um backup antes de realizar exclusões ou revogações em massa.

> 💡 Use a pesquisa e filtro no painel esquerdo para encontrar rapidamente itens específicos.
`
  }
}
