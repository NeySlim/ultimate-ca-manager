export default {
  helpContent: {
    title: 'Configurações de Segurança',
    subtitle: 'Autenticação e políticas de acesso',
    overview: 'Configure políticas de senha, gerenciamento de sessão, limitação de taxa e segurança de rede. Estas configurações se aplicam a todo o sistema e afetam todas as contas de usuário.',
    sections: [
      {
        title: 'Criptografia de Chaves Privadas',
        items: [
          { label: 'Status e contadores', text: 'Mostra se a criptografia está ativada e quantas chaves privadas armazenadas estão criptografadas vs não criptografadas' },
          { label: 'Ativar / Desativar', text: 'Criptografa todas as chaves privadas com AES-256. Ao ativar remove as cópias em texto claro e ao desativar as recria' },
          { label: 'Arquivos de chave no disco', text: 'Mostra quantas cópias de chaves em texto claro restam; use hooks de implantação quando outro serviço precisar de um arquivo de chave' },
          { label: 'UCM_REQUIRE_DB_ENCRYPTION_KEY', text: 'Variável de ambiente opcional: recusa iniciar sem uma chave de criptografia de banco de dados explícita' },
          { label: 'UCM_REQUIRE_KEY_ENCRYPTION', text: 'Variável de ambiente opcional: recusa iniciar a menos que a criptografia de chaves privadas esteja ativada' },
        ]
      },
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
          { label: 'Lista de acesso administrativo', text: 'Limitar a interface web e a API de gestão aos endereços IP e redes listados' },
          { label: 'Aplicação de 2FA', text: 'Exigir autenticação de dois fatores para todos os usuários' },
        ]
      },
      {
        title: 'Lista de Acesso Administrativo',
        items: [
          { label: 'Redes', text: 'Um endereço IPv4 ou IPv6 ou rede CIDR por linha, até 100. Vazia significa sem restrição' },
          { label: 'O que é bloqueado', text: 'A partir de outros endereços: a interface web, o login, a API /api/v2 (chaves de API incluídas) e o canal WebSocket respondem 403' },
          { label: 'Sempre acessíveis', text: 'ACME, SCEP, EST, OCSP, CRL/AIA, TSA, XCEP/WSTEP, o script de configuração SSH e os endpoints de saúde' },
          { label: 'Seu endereço', text: 'A seção mostra o endereço que o servidor vê para você; uma lista que não o inclua é recusada' },
          { label: 'UCM_ADMIN_ALLOWED_NETWORKS', text: 'Variável de ambiente (separada por vírgulas) que prevalece sobre a configuração e a torna somente leitura' },
          { label: 'UCM_ADMIN_ALLOWLIST_DISABLE', text: 'Defina como 1 e reinicie para desativar a verificação após um bloqueio de acesso' },
        ]
      },
      {
        title: 'Autenticação mTLS',
        items: [
          { label: 'CA Confiável', text: 'Selecionar a CA que emite e valida os certificados de cliente mTLS para login' },
          { label: 'Exigir certificado de cliente', text: 'Opcionalmente tornar o mTLS obrigatório para a interface web, alterar configurações mTLS requer reinício do serviço' },
        ]
      },
    ],
    tips: [
      'Ative a limitação de taxa para proteger contra ferramentas de ataque automatizadas',
      'Use a lista de acesso administrativo para limitar a interface web à sua VLAN de gestão, bastion ou VPN',
    ],
    warnings: [
      'Restringir a política de senha excessivamente pode frustrar os usuários',
      'Atrás de um proxy reverso, defina UCM_BEHIND_PROXY e UCM_TRUSTED_PROXIES antes de usar a lista de acesso administrativo, caso contrário todas as requisições parecem vir do proxy',
      'Configurações sensíveis à segurança (sessão, bloqueio, HSTS, URL pública, política de senha) requerem admin:settings, os campos ficam bloqueados para operators',
    ],
  },
  helpGuides: {
    title: 'Configurações de Segurança',
    content: `
## Visão Geral

Configuração de segurança de todo o sistema que afeta todas as contas de usuário e padrões de acesso.

## Criptografia de Chaves Privadas

Criptografe todas as chaves privadas de CAs e certificados armazenadas no banco de dados com AES-256, protegidas por um arquivo de chave mestra mantido fora do banco de dados.

- **Status e contadores**: A seção mostra se a criptografia está ativada e quantas chaves estão atualmente **criptografadas** vs **não criptografadas**
- **Ativar Criptografia**: Gera o arquivo de chave mestra e criptografa todas as chaves privadas armazenadas. Faça backup do arquivo de chave imediatamente: sem ele, as chaves criptografadas são perdidas permanentemente
- **Desativar Criptografia**: Descriptografa todas as chaves privadas de volta ao armazenamento em texto claro (confirmação necessária)

### Aplicação na Inicialização

Sem uma chave de criptografia configurada, o UCM registra um aviso na inicialização mas continua funcionando. Duas **variáveis de ambiente opcionais** transformam isso em falha imediata:

- \`UCM_REQUIRE_DB_ENCRYPTION_KEY\`: recusa iniciar sem uma chave de criptografia de banco de dados explícita (caso contrário, os segredos de integração recorrem a uma chave derivada do id da máquina)
- \`UCM_REQUIRE_KEY_ENCRYPTION\`: recusa iniciar a menos que a criptografia de chaves privadas esteja ativada

Ambas aceitam \`1\`/\`true\`/\`yes\`/\`on\`. Uma chave inválida é tratada como fatal em vez de recorrer silenciosamente ao texto claro.

## Política de Senha

### Requisitos de Complexidade
- **Comprimento mínimo**: 8 a 32 caracteres
- **Exigir maiúsculas**: Pelo menos uma letra maiúscula
- **Exigir minúsculas**: Pelo menos uma letra minúscula
- **Exigir números**: Pelo menos um dígito
- **Exigir caracteres especiais**: Pelo menos um símbolo

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

## Lista de Acesso Administrativo

Limite a interface web e a API de gestão a uma lista de endereços IP e redes CIDR, IPv4 ou IPv6, um por linha (até 100). Uma lista vazia não restringe nada.

- **Bloqueado a partir de outros endereços**: a interface web e seus recursos, o login, toda chamada \`/api/v2\` (chaves de API incluídas) e o canal WebSocket respondem **403**
- **Sempre acessíveis**: ACME e o proxy ACME, SCEP, EST, OCSP, CRL e AIA, TSA, XCEP/WSTEP, o script de configuração SSH e os endpoints de saúde e métricas, para que dispositivos e sondas continuem funcionando
- **Seu endereço**: a seção mostra o endereço que o servidor vê para você. Uma lista que não o inclua é recusada, então um salvamento não pode bloqueá-lo
- **Auditoria**: cada alteração da lista é registrada no log de auditoria

### Variáveis de Ambiente
- \`UCM_ADMIN_ALLOWED_NETWORKS\`: lista separada por vírgulas que prevalece sobre a configuração e torna o campo somente leitura
- \`UCM_ADMIN_ALLOWLIST_DISABLE=1\`: desativa a verificação após uma reinicialização; use para se recuperar de um bloqueio de acesso e depois remova

### Proxy Reverso, Docker e Kubernetes
Atrás de um proxy reverso, defina \`UCM_BEHIND_PROXY=1\` e liste o proxy em \`UCM_TRUSTED_PROXIES\`, caso contrário todas as requisições parecem vir do proxy. Com Docker em modo bridge e sem proxy, o endereço visto pode ser o posterior ao NAT do Docker: verifique o endereço exibido antes de salvar.

> ⚠ Este filtro atua no nível da aplicação. Mantenha também um firewall na frente da porta HTTPS.

## Autenticação de Dois Fatores

### Aplicação
Exigir que todos os usuários ativem 2FA. Usuários que não configuraram 2FA serão solicitados no próximo login. Um aplicativo TOTP ou uma chave de segurança registrada atende ao requisito, na configuração e no login. Enquanto for obrigatória, o TOTP só pode ser desativado se restar uma chave de segurança, e a última chave só pode ser removida se restar o TOTP. Um usuário cuja chave se tornou seu segundo fator a mantém quando a obrigatoriedade é retirada.

### Métodos Suportados
- **TOTP**: Senhas únicas baseadas em tempo (aplicativos autenticadores)
- **WebAuthn**: Chaves de segurança de hardware e biometria

> 💡 Aplique 2FA para contas de administrador no mínimo. Considere aplicar para todos os usuários em ambientes sensíveis à segurança.

## Autenticação mTLS

Permita que usuários façam login com um certificado de cliente em vez de senha:

- **CA Confiável**: Selecione a CA que emite e valida os certificados de cliente mTLS
- **Exigir certificado de cliente**: Opcionalmente torne o mTLS obrigatório para a interface web
- Alterar configurações mTLS requer reinício do serviço

## Permissões Necessárias

Configurações sensíveis à segurança: sessão, bloqueio, HSTS, URL pública e política de senha, requerem a permissão **admin:settings**. Para operators (apenas write:settings), esses campos aparecem bloqueados; o restante do cartão continua salvando normalmente.
`
  }
}
