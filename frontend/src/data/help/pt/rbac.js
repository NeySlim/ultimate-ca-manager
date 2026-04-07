export default {
  helpContent: {
    title: 'Controle de Acesso Baseado em Funções',
    subtitle: 'Gerenciamento granular de permissões',
    overview: 'Defina funções personalizadas com permissões granulares. As funções do sistema (Admin, Operador, Auditor, Visualizador) são integradas. Funções personalizadas permitem controlar exatamente quais operações cada usuário pode realizar.',
    sections: [
      {
        title: 'Funções do Sistema',
        definitions: [
          { term: 'Admin', description: 'Acesso total a todos os recursos e configurações' },
          { term: 'Operador', description: 'Pode gerenciar certificados e CAs, mas não configurações do sistema' },
          { term: 'Auditor', description: 'Acesso somente leitura a todos os dados operacionais para conformidade e auditoria' },
          { term: 'Visualizador', description: 'Acesso básico somente leitura a certificados, CAs e modelos' },
        ]
      },
      {
        title: 'Funções Personalizadas',
        items: [
          { label: 'Criar Função', text: 'Definir uma nova função com nome e descrição' },
          { label: 'Matriz de Permissões', text: 'Marcar/desmarcar permissões por categoria (CAs, Certs, Usuários, etc.)' },
          { label: 'Cobertura', text: 'Percentual visual do total de permissões concedidas à função' },
          { label: 'Contagem de Usuários', text: 'Ver quantos usuários estão atribuídos a cada função' },
        ]
      },
    ],
    tips: [
      'Siga o princípio do menor privilégio — conceda apenas permissões necessárias',
      'As funções do sistema não podem ser modificadas ou excluídas',
      'Alterne categorias inteiras para configuração rápida de funções',
    ],
  },
  helpGuides: {
    title: 'Controle de Acesso Baseado em Funções',
    content: `
## Visão Geral

RBAC fornece gerenciamento granular de permissões. Defina funções personalizadas com permissões específicas e atribua-as a usuários ou grupos.

## Funções do Sistema

Quatro funções integradas que não podem ser modificadas ou excluídas:

- **Admin** — Acesso total a tudo
- **Operador** — Gerenciar certificados, CAs, CSRs, modelos. Sem acesso a configurações do sistema, usuários ou RBAC
- **Auditor** — Acesso somente leitura a todos os dados operacionais (certificados, CAs, ACME, SCEP, HSM, logs de auditoria, políticas, grupos) mas não configurações ou gerenciamento de usuários
- **Visualizador** — Acesso básico somente leitura a certificados, CAs, CSRs, modelos e armazenamento de confiança

## Funções Personalizadas

### Criando uma Função Personalizada
1. Clique em **Criar Função**
2. Insira um **nome** e descrição opcional
3. Configure permissões usando a **matriz de permissões**
4. Clique em **Criar**

### Matriz de Permissões
As permissões são organizadas por categoria:
- **CAs** — Criar, ler, atualizar, excluir, importar, exportar
- **Certificados** — Emitir, ler, revogar, renovar, exportar, excluir
- **CSRs** — Criar, ler, assinar, excluir
- **Modelos** — Criar, ler, atualizar, excluir
- **Usuários** — Criar, ler, atualizar, excluir
- **Grupos** — Criar, ler, atualizar, excluir
- **Configurações** — Ler, atualizar
- **Auditoria** — Ler, exportar, limpeza
- **ACME** — Configurar, gerenciar contas
- **SCEP** — Configurar, aprovar solicitações
- **Armazenamento de Confiança** — Gerenciar certificados confiáveis
- **HSM** — Gerenciar provedores e chaves
- **Backup** — Criar, restaurar

### Alternância de Categorias
Clique no cabeçalho de uma categoria para ativar/desativar todas as permissões daquela categoria de uma vez.

### Indicador de Cobertura
Um badge percentual mostra quanto do conjunto total de permissões a função cobre. 100% = equivalente a Admin.

## Atribuindo Funções

Funções são atribuídas:
- **Diretamente** — Na página de Usuários, edite um usuário e selecione uma função
- **Via Grupos** — Atribua uma função a um grupo; todos os membros herdam

## Permissões Efetivas

As permissões efetivas de um usuário são calculadas como a união de:
1. As permissões da função atribuída diretamente
2. Todas as funções dos grupos aos quais pertence

A regra mais permissiva prevalece (modelo aditivo, sem regras de negação).

> ⚠ As funções do sistema não podem ser editadas ou excluídas. Crie funções personalizadas para necessidades específicas.
`
  }
}
