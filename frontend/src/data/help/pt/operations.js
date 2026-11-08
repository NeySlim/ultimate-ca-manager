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
          { label: 'Certificados', text: 'Revogar, renovar, excluir ou exportar, filtrar por status e CA emissora' },
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
      'Revogar, renovar, assinar e excluir pedem confirmação antes de executar; uma exportação começa de imediato',
    ],
    warnings: [
      'A exclusão em massa é irreversível: sempre crie um backup primeiro',
      'A revogação em massa publicará CRLs atualizadas para todas as CAs afetadas',
    ],
  },
  helpGuides: {
    title: 'Operações',
    content: `
## Visão Geral

Operações em massa e gerenciamento de dados. Realize ações em lote em múltiplos recursos simultaneamente.

## Aba Importar

Igual à página de Importação/Exportação: o assistente de Importação Inteligente e a integração OPNsense (conectar, navegar e importar do OPNsense).

## Aba Exportar

Exportação em massa de certificados e CAs.

## Ações em Massa

Realize operações em lote em múltiplos recursos de uma vez.

### Como Funciona
1. Selecione o **tipo de recurso** (Certificados, CAs, CSRs, Modelos, Usuários)
2. Marque os itens na tabela (a vista opcional Cesta os move entre dois painéis)
3. Escolha a **ação** a ser realizada
4. Confirme e execute

### Ações Disponíveis por Recurso

#### Certificados
- **Revogar em Massa**: Revogar múltiplos certificados de uma vez
- **Renovar em Massa**: Renovar múltiplos certificados
- **Exportar em Massa**: Baixar certificados selecionados como pacote
- **Excluir em Massa**: Remover permanentemente certificados selecionados

#### CAs
- **Exportar em Massa**: Baixar CAs selecionadas
- **Excluir em Massa**: Remover CAs selecionadas (não devem ter CAs filhas)

#### CSRs
- **Assinar em Massa**: Assinar múltiplos CSRs com uma CA selecionada
- **Excluir em Massa**: Remover CSRs selecionados

#### Modelos
- **Excluir em Massa**: Remover modelos selecionados

#### Usuários
- **Excluir em Massa**: Remover permanentemente usuários selecionados

> ⚠ Operações em massa são irreversíveis. Sempre crie um backup antes de realizar exclusões ou revogações em massa.

> 💡 Use a pesquisa e os filtros acima da tabela para encontrar rapidamente itens específicos.
`
  }
}
