export default {
  helpContent: {
    title: 'Configurações de Segurança',
    subtitle: 'Autenticação e políticas de acesso',
    overview: 'Configure políticas de senha, gerenciamento de sessão, limitação de taxa e segurança de rede. Estas configurações se aplicam a todo o sistema e afetam todas as contas de usuário.',
    sections: [
      {
        title: 'Política de Senha',
        items: [
          { label: 'Comprimento Mínimo', text: 'Número mínimo de caracteres obrigatórios' },
          { label: 'Complexidade', text: 'Exigir letras maiúsculas, minúsculas, números, caracteres especiais' },
          { label: 'Expiração', text: 'Forçar alteração de senha após um número definido de dias' },
          { label: 'Histórico', text: 'Impedir reutilização de senhas anteriores' },
        ]
      },
      {
        title: 'Sessão e Acesso',
        items: [
          { label: 'Tempo Limite de Sessão', text: 'Logout automático após período de inatividade' },
          { label: 'Limitação de Taxa', text: 'Limitar tentativas de login para prevenir ataques de força bruta' },
          { label: 'Restrições de IP', text: 'Permitir ou negar acesso de faixas de IP específicas' },
          { label: 'Aplicação de 2FA', text: 'Exigir autenticação de dois fatores para todos os usuários' },
        ]
      },
    ],
    tips: [
      'Ative a limitação de taxa para proteger contra ferramentas de ataque automatizadas',
      'Use restrições de IP para limitar acesso administrativo a redes confiáveis',
    ],
    warnings: [
      'Restringir a política de senha excessivamente pode frustrar os usuários',
      'Sempre garanta que pelo menos um administrador pode acessar o sistema antes de ativar restrições de IP',
    ],
  },
  helpGuides: {
    title: 'Configurações de Segurança',
    content: `
## Visão Geral

Configuração de segurança de todo o sistema que afeta todas as contas de usuário e padrões de acesso.

## Política de Senha

### Requisitos de Complexidade
- **Comprimento mínimo** — 8 a 32 caracteres
- **Exigir maiúsculas** — Pelo menos uma letra maiúscula
- **Exigir minúsculas** — Pelo menos uma letra minúscula
- **Exigir números** — Pelo menos um dígito
- **Exigir caracteres especiais** — Pelo menos um símbolo

### Expiração de Senha
Forçar usuários a alterar suas senhas após um número definido de dias. Defina como 0 para desativar.

### Histórico de Senha
Impedir reutilização das últimas N senhas. Os usuários não podem definir uma senha que corresponda a qualquer uma de suas N senhas anteriores.

## Gerenciamento de Sessão

### Tempo Limite de Sessão
Logout automático de usuários após N minutos de inatividade. Aplica-se apenas a sessões da interface web, não a chaves de API.

### Sessões Simultâneas
Limitar o número de sessões simultâneas por usuário. Logins adicionais encerrarão a sessão mais antiga.

## Limitação de Taxa

### Tentativas de Login
Limitar tentativas de login com falha por endereço IP dentro de uma janela de tempo. Após exceder o limite, o IP é temporariamente bloqueado.

### Duração do Bloqueio
Por quanto tempo um IP fica bloqueado após exceder o limite de tentativas de login.

## Restrições de IP

### Lista de Permissão
Permitir conexões apenas de IPs ou faixas CIDR especificadas. Todos os outros IPs são bloqueados.

### Lista de Negação
Bloquear IPs ou faixas CIDR específicas. Todos os outros IPs são permitidos.

> ⚠ Tenha extremo cuidado com restrições de IP. Configuração incorreta pode bloquear todos os usuários, incluindo administradores. Sempre teste com um único IP primeiro.

## Autenticação de Dois Fatores

### Aplicação
Exigir que todos os usuários ativem 2FA. Usuários que não configuraram 2FA serão solicitados no próximo login.

### Métodos Suportados
- **TOTP** — Senhas únicas baseadas em tempo (aplicativos autenticadores)
- **WebAuthn** — Chaves de segurança de hardware e biometria

> 💡 Aplique 2FA para contas de administrador no mínimo. Considere aplicar para todos os usuários em ambientes sensíveis à segurança.
`
  }
}
