export default {
  helpContent: {
    title: 'Certificados SSH',
    subtitle: 'Emitir e gerenciar certificados OpenSSH',
    overview: 'Emita certificados SSH assinados pelas suas CAs SSH. Os certificados substituem o gerenciamento manual de authorized_keys, fornecendo acesso com tempo limitado, escopo por principal e expiração automática. São suportados certificados de usuário e de host.',
    sections: [
      {
        title: 'Modos de Emissão',
        items: [
          { label: 'Modo Assinatura', text: 'Cole uma chave pública SSH existente para assiná-la. A chave privada permanece na máquina do usuário — o UCM nunca a acessa.' },
          { label: 'Modo Geração', text: 'O UCM gera um novo par de chaves e assina o certificado. Baixe a chave privada imediatamente — ela não poderá ser recuperada depois.' },
        ]
      },
      {
        title: 'Campos do Certificado',
        items: [
          { label: 'Key ID', text: 'Identificador único do certificado. Aparece nos logs SSH para auditoria.' },
          { label: 'Principals', text: 'Nomes de usuário (certificado de usuário) ou nomes de host (certificado de host) para os quais este certificado é válido. Separados por vírgula.' },
          { label: 'Validade', text: 'Tempo de vida do certificado. Escolha um preset (1h, 8h, 24h, 7d, 30d, 90d, 365d) ou defina segundos personalizados.' },
          { label: 'Extensions', text: 'Extensões SSH como permit-pty, permit-agent-forwarding. Aplicável apenas a certificados de usuário.' },
          { label: 'Critical Options', text: 'Restrições como force-command ou source-address para limitar o uso do certificado.' },
        ]
      },
      {
        title: 'Tipos de Certificado',
        items: [
          { label: 'Certificado de Usuário', text: 'Autentica um usuário em um servidor. O servidor deve confiar na CA assinante via TrustedUserCAKeys.' },
          { label: 'Certificado de Host', text: 'Autentica um servidor para os clientes. Os clientes confiam na CA via @cert-authority no known_hosts.' },
        ]
      },
      {
        title: 'Gerenciamento',
        items: [
          { label: 'Revogar', text: 'Adiciona um certificado à Key Revocation List (KRL) da CA. Os servidores devem estar configurados para verificar o KRL.' },
          { label: 'Download', text: 'Baixe o certificado, a chave pública ou a chave privada (somente no modo geração).' },
        ]
      },
    ],
    tips: [
      'Use certificados de curta duração (8h–24h) para acesso de usuários, minimizando o impacto de comprometimento de chaves.',
      'O modo assinatura é preferível — a chave privada do usuário nunca sai da sua máquina.',
      'Os Key IDs devem ser descritivos (ex.: "jdoe-prod-2025") para facilitar a auditoria de logs.',
      'Para certificados de host, o principal deve corresponder ao nome de host que os clientes usam para se conectar.',
    ],
    warnings: [
      'No modo geração, baixe a chave privada imediatamente — ela não é armazenada e não pode ser recuperada.',
      'Revogar um certificado só funciona se os servidores estiverem configurados para verificar o arquivo KRL da CA.',
    ],
  },
  helpGuides: {
    title: 'Certificados SSH',
    content: `
## Visão Geral

Certificados SSH são chaves públicas SSH assinadas com metadados: identidade, período de validade, principals permitidos e extensões. Eles substituem a abordagem tradicional de \`authorized_keys\` por um controle de acesso centralizado, com tempo limitado e auditável.

O UCM emite certificados no formato OpenSSH, compatíveis com OpenSSH 5.4+ em qualquer plataforma.

## Modos de Emissão

### Modo Assinatura (Recomendado)
O usuário gera seu próprio par de chaves e fornece apenas a **chave pública** ao UCM. A chave privada nunca sai da máquina do usuário.

**Fluxo de trabalho do usuário:**
\`\`\`bash
# 1. Gerar um par de chaves (máquina do usuário)
ssh-keygen -t ed25519 -f ~/.ssh/id_work -C "jdoe@example.com"

# 2. Copiar o conteúdo da chave pública
cat ~/.ssh/id_work.pub

# 3. Colar no formulário de assinatura do UCM
# 4. Baixar o certificado assinado
# 5. Salvar como ~/.ssh/id_work-cert.pub

# 6. Conectar
ssh -i ~/.ssh/id_work user@server
\`\`\`

### Modo Geração
O UCM gera tanto o par de chaves quanto o certificado. Use quando precisar provisionar credenciais de forma centralizada.

> ⚠ **Baixe a chave privada imediatamente** — ela não é armazenada no UCM e não pode ser recuperada.

**Fluxo de trabalho:**
1. Selecione uma CA e preencha os detalhes do certificado
2. Escolha o modo "Gerar"
3. Clique em **Emitir**
4. Baixe os três arquivos:
   - Chave privada (\`keyid\`) — **Armazene com segurança!**
   - Certificado (\`keyid-cert.pub\`)
   - Chave pública (\`keyid.pub\`)

## Campos do Certificado

### Key ID
Um identificador único incorporado no certificado. Ele aparece nos logs do servidor SSH quando o certificado é usado, sendo essencial para auditoria.

**Bons Key IDs:** \`jdoe-prod-2025\`, \`webserver-01\`, \`deploy-ci-pipeline\`

### Principals
Os Principals definem **quem** (certificados de usuário) ou **o quê** (certificados de host) o certificado é válido:

- **Certificados de usuário**: lista de nomes de usuário com os quais o portador pode fazer login (ex.: \`deploy\`, \`admin\`)
- **Certificados de host**: lista de nomes de host/IPs pelos quais o servidor é conhecido (ex.: \`web01.example.com\`, \`10.0.1.5\`)

> 💡 Se nenhum principal for especificado, o certificado funciona para qualquer principal — o que geralmente é permissivo demais.

### Validade

Escolha um preset ou defina uma duração personalizada:

| Preset | Caso de Uso |
|--------|----------|
| 1 hora | Pipelines CI/CD, tarefas pontuais |
| 8 horas | Acesso durante o dia de trabalho |
| 24 horas | Acesso estendido |
| 7 dias | Acesso por sprint |
| 30 dias | Rotação mensal |
| 365 dias | Contas de serviço de longa duração |

Certificados de curta duração (8h–24h) são recomendados para usuários humanos. Validade mais longa é aceitável para contas de serviço automatizadas.

### Extensions (Apenas Certificados de Usuário)

| Extension | Descrição |
|-----------|-------------|
| permit-pty | Permitir sessões de terminal interativas |
| permit-agent-forwarding | Permitir encaminhamento do agente SSH |
| permit-X11-forwarding | Permitir encaminhamento de exibição X11 |
| permit-port-forwarding | Permitir encaminhamento de porta TCP |
| permit-user-rc | Permitir execução de ~/.ssh/rc no login |

### Critical Options

| Opção | Descrição |
|--------|-------------|
| force-command | Restringir o certificado a um único comando |
| source-address | Restringir a endereços IP/CIDRs de origem específicos |

**Exemplo:** Um certificado com \`force-command=ls\` e \`source-address=10.0.0.0/8\` só pode executar \`ls\` e somente a partir da rede 10.x.x.x.

## Usando Certificados

### Certificado de Usuário
\`\`\`bash
# Coloque o certificado ao lado da chave privada
# Se a chave é ~/.ssh/id_work, o certificado deve ser ~/.ssh/id_work-cert.pub
cp downloaded-cert.pub ~/.ssh/id_work-cert.pub

# O SSH usa o certificado automaticamente
ssh user@server
\`\`\`

### Certificado de Host
\`\`\`bash
# No servidor: coloque o certificado de host
sudo cp host-cert.pub /etc/ssh/ssh_host_ed25519_key-cert.pub

# Adicione ao sshd_config
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

Nos clientes, adicione a Host CA ao known_hosts:
\`\`\`
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Revogação

1. Selecione um certificado na tabela
2. Clique em **Revogar** no painel de detalhes
3. O certificado é adicionado à Key Revocation List (KRL) da CA
4. Baixe e implante o KRL atualizado nos servidores (a partir da página CAs SSH)

> ⚠ A revogação só entra em vigor quando os servidores verificam o KRL via \`RevokedKeys\` no sshd_config.

## Solução de Problemas

| Problema | Solução |
|-------|----------|
| Permission denied (publickey) | Verifique se a CA é confiável no servidor (TrustedUserCAKeys) |
| Certificado não utilizado | Certifique-se de que o arquivo do certificado está nomeado como \`<key>-cert.pub\` ao lado da chave privada |
| Incompatibilidade de principal | O nome de usuário usado no SSH deve estar listado nos principals do certificado |
| Certificado expirado | Emita um novo certificado com validade apropriada |
| Falha na verificação de host | Adicione a Host CA ao known_hosts com @cert-authority |
`
  }
}
