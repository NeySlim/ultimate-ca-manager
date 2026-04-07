export default {
  helpContent: {
    title: 'Usuários e Grupos',
    subtitle: 'Gerenciamento de identidade e acesso',
    overview: 'Gerencie contas de usuário e associações a grupos. Atribua funções para controlar o acesso aos recursos do UCM. Grupos permitem gerenciamento de permissões em massa para equipes.',
    sections: [
      {
        title: 'Usuários',
        items: [
          { label: 'Criar Usuário', text: 'Adicionar um novo usuário com nome de usuário, e-mail e senha inicial' },
          { label: 'Funções', text: 'Atribuir funções do sistema ou personalizadas para controlar permissões' },
          { label: 'Status', text: 'Ativar ou desativar contas de usuário' },
          { label: 'Redefinir Senha', text: 'Redefinir a senha de um usuário (ação de administrador)' },
          { label: 'Chaves de API', text: 'Gerenciar chaves de API por usuário para acesso programático' },
        ]
      },
      {
        title: 'Grupos',
        items: [
          { label: 'Criar Grupo', text: 'Definir um grupo e atribuir membros' },
          { label: 'Herança de Função', text: 'Grupos podem herdar funções — todos os membros recebem as permissões do grupo' },
          { label: 'Gerenciamento de Membros', text: 'Adicionar ou remover usuários dos grupos' },
        ]
      },
    ],
    tips: [
      'Use grupos para gerenciar permissões de equipes em vez de usuários individuais',
      'Usuários desativados não podem fazer login, mas seus dados são preservados',
    ],
    warnings: [
      'Excluir um usuário é permanente — considere desativar em vez disso',
    ],
  },
  helpGuides: {
    title: 'Usuários e Grupos',
    content: `
## Visão Geral

Gerencie contas de usuário, grupos e atribuições de funções. Os usuários se autenticam no UCM via senha, SSO, WebAuthn ou mTLS. Grupos permitem gerenciamento de permissões em massa.

## Aba Usuários

### Criando um Usuário
1. Clique em **Criar Usuário**
2. Insira o **nome de usuário** (único, não pode ser alterado depois)
3. Insira o **e-mail** (usado para notificações e recuperação)
4. Defina uma **senha inicial**
5. Selecione uma **função** (Admin, Operador, Auditor, Visualizador ou personalizada)
6. Clique em **Criar**

### Status do Usuário
- **Ativo** — Pode fazer login e realizar ações
- **Desativado** — Não pode fazer login, dados são preservados

Alterne o status de um usuário sem excluir sua conta.

### Redefinir Senha
Administradores podem redefinir a senha de qualquer usuário. O usuário será solicitado a alterá-la no próximo login.

### Chaves de API
Cada usuário pode ter múltiplas chaves de API para acesso programático. As chaves de API herdam as permissões da função do usuário. Veja a página Conta para gerenciar suas próprias chaves.

## Aba Grupos

### Criando um Grupo
1. Clique em **Criar Grupo**
2. Insira um **nome** e descrição opcional
3. Atribua uma **função** (membros do grupo herdam esta função)
4. Clique em **Criar**

### Gerenciando Membros
- Clique em um grupo para ver seus membros
- Use o **painel de transferência** para adicionar/remover usuários
- Usuários podem pertencer a múltiplos grupos

### Herança de Função
As permissões efetivas de um usuário são a **união** de:
- Sua função atribuída diretamente
- Todas as funções dos grupos aos quais pertence

## Funções

### Funções do Sistema
- **Admin** — Acesso total a todos os recursos
- **Operador** — Pode gerenciar certificados, CAs, CSRs, mas não configurações do sistema
- **Auditor** — Acesso somente leitura a todos os dados operacionais para conformidade e auditoria
- **Visualizador** — Acesso somente leitura a certificados, CAs e modelos

### Funções Personalizadas
Crie funções com permissões granulares na página **RBAC**.

> 💡 Use grupos para gerenciar permissões de equipes em vez de atribuir funções a usuários individuais.
`
  }
}
