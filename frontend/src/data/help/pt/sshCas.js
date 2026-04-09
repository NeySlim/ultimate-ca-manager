export default {
  helpContent: {
    title: 'Autoridades Certificadoras SSH',
    subtitle: 'Gerenciar CAs SSH para autenticação de usuários e hosts',
    overview: 'Crie e gerencie Autoridades Certificadoras SSH seguindo os padrões OpenSSH. As CAs SSH eliminam a necessidade de distribuir chaves públicas individuais — em vez disso, servidores e usuários confiam na CA, e a CA assina certificados que concedem acesso.',
    sections: [
      {
        title: 'Tipos de CA',
        items: [
          { label: 'User CA', text: 'Assina certificados de usuário para login SSH. Os servidores confiam nesta CA e aceitam qualquer certificado assinado por ela.' },
          { label: 'Host CA', text: 'Assina certificados de host para comprovar a identidade do servidor. Os clientes confiam nesta CA para verificar que estão se conectando ao servidor correto.' },
        ]
      },
      {
        title: 'Algoritmos de Chave',
        items: [
          { label: 'Ed25519', text: 'Moderno, rápido, chaves pequenas (256 bits). Recomendado para novas implantações.' },
          { label: 'ECDSA P-256 / P-384', text: 'Chaves de curva elíptica, amplamente suportadas. Bom equilíbrio entre segurança e compatibilidade.' },
          { label: 'RSA 2048 / 4096', text: 'Algoritmo tradicional. Use 4096 bits para CAs de longa duração. Maior compatibilidade com sistemas antigos.' },
        ]
      },
      {
        title: 'Configuração do Servidor',
        items: [
          { label: 'Script de Configuração', text: 'Baixe um script shell POSIX que configura automaticamente o sshd para confiar nesta CA. Suporta todas as principais distribuições Linux.' },
          { label: 'Configuração Manual', text: 'Copie a chave pública da CA e adicione TrustedUserCAKeys (User CA) ou HostCertificate (Host CA) ao sshd_config.' },
        ]
      },
      {
        title: 'Revogação de Chaves',
        items: [
          { label: 'KRL (Key Revocation List)', text: 'Formato binário compacto para revogar certificados individuais. Configurado via RevokedKeys no sshd_config.' },
          { label: 'Download do KRL', text: 'Baixe o arquivo KRL atual no painel de detalhes da CA.' },
        ]
      },
    ],
    tips: [
      'Use CAs separadas para certificados de usuário e de host — nunca misture.',
      'Ed25519 é recomendado para novas implantações devido à velocidade e segurança.',
      'Baixe o script de configuração para facilitar a configuração do servidor — ele gerencia backup e validação automaticamente.',
    ],
    warnings: [
      'Excluir uma CA não revoga os certificados assinados por ela — revogue-os primeiro ou atualize a confiança do servidor.',
      'Se a chave privada da CA for comprometida, todos os certificados assinados por ela devem ser considerados não confiáveis.',
    ],
  },
  helpGuides: {
    title: 'Autoridades Certificadoras SSH',
    content: `
## Visão Geral

As Autoridades Certificadoras (CAs) SSH são a base da autenticação baseada em certificados SSH. Em vez de distribuir chaves públicas individuais para cada servidor, você cria uma CA e configura os servidores para confiar nela. Qualquer certificado assinado pela CA é automaticamente aceito.

O UCM suporta o formato de certificado OpenSSH (RFC 4253 + extensões OpenSSH), que é nativamente compreendido pelo OpenSSH 5.4+ — sem necessidade de software adicional nos servidores ou clientes.

## Tipos de CA

### User CA
Uma User CA assina certificados que autenticam **usuários nos servidores**. Quando um servidor confia em uma User CA, qualquer usuário que apresente um certificado válido assinado por essa CA é autorizado a fazer login (sujeito à correspondência de principals).

**Configuração do servidor:**
\`\`\`
# /etc/ssh/sshd_config
TrustedUserCAKeys /etc/ssh/user_ca.pub
\`\`\`

### Host CA
Uma Host CA assina certificados que autenticam **servidores para os clientes**. Quando um cliente confia em uma Host CA, ele pode verificar que o servidor ao qual se conecta é legítimo — eliminando avisos de "Trust On First Use" (TOFU).

**Configuração do cliente:**
\`\`\`
# ~/.ssh/known_hosts
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Criando uma CA

1. Clique em **Criar SSH CA**
2. Insira um nome descritivo (ex.: "Production User CA")
3. Selecione o tipo de CA: **User** ou **Host**
4. Escolha o algoritmo de chave:
   - **Ed25519** — Recomendado. Rápido, chaves pequenas, segurança moderna.
   - **ECDSA P-256/P-384** — Boa compatibilidade e segurança.
   - **RSA 2048/4096** — Maior compatibilidade, chaves maiores.
5. Opcionalmente, defina a validade máxima e extensões padrão
6. Clique em **Criar**

> 💡 Use CAs separadas para certificados de usuário e de host. Nunca use uma CA para ambos os propósitos.

## Configuração do Servidor

### Script de Configuração Automática

O UCM gera um script shell POSIX que configura automaticamente o seu servidor:

1. Abra o painel de detalhes da CA
2. Clique em **Baixar Script de Configuração**
3. Transfira o script para o seu servidor
4. Execute:

\`\`\`bash
chmod +x setup-ssh-ca.sh
sudo ./setup-ssh-ca.sh
\`\`\`

O script:
- Detecta o seu SO e sistema de inicialização
- Faz backup do sshd_config antes de qualquer alteração
- Instala a chave pública da CA
- Adiciona TrustedUserCAKeys (User CA) ou HostCertificate (Host CA)
- Valida a configuração com \`sshd -t\`
- Reinicia o sshd somente se a validação for bem-sucedida
- Suporta \`--dry-run\` para visualizar as alterações

### Configuração Manual

#### User CA
\`\`\`bash
# Copie a chave pública da CA para o servidor
echo "ssh-ed25519 AAAA... user-ca" | sudo tee /etc/ssh/user_ca.pub

# Adicione ao sshd_config
echo "TrustedUserCAKeys /etc/ssh/user_ca.pub" | sudo tee -a /etc/ssh/sshd_config

# Reinicie o sshd
sudo systemctl restart sshd
\`\`\`

#### Host CA
\`\`\`bash
# Assine a chave de host do servidor
# Em seguida, adicione ao sshd_config:
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

## Listas de Revogação de Chaves (KRL)

As CAs SSH suportam Key Revocation Lists para invalidar certificados comprometidos:

1. Revogue certificados na página de Certificados SSH
2. Baixe o KRL atualizado no painel de detalhes da CA
3. Implante o arquivo KRL nos servidores:

\`\`\`bash
# Adicione ao sshd_config
RevokedKeys /etc/ssh/revoked_keys
\`\`\`

> ⚠ Os servidores devem estar configurados para verificar o KRL. A revogação não entra em vigor até que o KRL seja implantado.

## Melhores Práticas

| Prática | Recomendação |
|----------|---------------|
| CAs separadas | Use CAs distintas para certificados de usuário e de host |
| Algoritmo de chave | Ed25519 para novas implantações, RSA 4096 para compatibilidade legada |
| Vida útil da CA | Mantenha CAs com longa duração; use certificados de curta duração |
| Backup | Exporte e armazene com segurança a chave privada da CA |
| Mapeamento de principals | Mapeie principals para nomes de usuário específicos, não curingas |
`
  }
}
