export default {
  helpContent: {
    title: 'CRL e OCSP',
    subtitle: 'Serviços de revogação de certificados',
    overview: 'Gerencie Listas de Revogação de Certificados (CRL) e serviços de Protocolo de Status de Certificado Online (OCSP). Esses serviços permitem que clientes verifiquem se um certificado foi revogado.',
    sections: [
      {
        title: 'Gerenciamento de CRL',
        items: [
          { label: 'Regeneração Automática', text: 'Alternar a regeneração automática de CRL por CA' },
          { label: 'Regenerar Manualmente', text: 'Forçar a regeneração da CRL imediatamente' },
          { label: 'Baixar CRL', text: 'Baixar o arquivo CRL em formato DER ou PEM' },
          { label: 'URL do CDP', text: 'URL do Ponto de Distribuição de CRL para incorporar nos certificados' },
        ]
      },
      {
        title: 'Serviço OCSP',
        items: [
          { label: 'Status', text: 'Indica se o respondedor OCSP está ativo para cada CA' },
          { label: 'URL do AIA', text: 'URLs de Acesso à Informação da Autoridade — endpoints do respondedor OCSP e download do certificado do emissor CA incorporados nos certificados emitidos' },
          { label: 'Cache', text: 'Cache de respostas com limpeza diária automática de entradas expiradas' },
          { label: 'Total de Consultas', text: 'Número de requisições OCSP processadas' },
        ]
      },
    ],
    tips: [
      'Ative a regeneração automática para manter as CRLs atualizadas após revogações de certificados',
      'Copie as URLs de CDP, OCSP e AIA CA Issuers para incorporá-las nos seus perfis de certificado',
      'O OCSP fornece verificação de revogação em tempo real e é preferido em relação à CRL',
    ],
  },
  helpGuides: {
    title: 'CRL e OCSP',
    content: `
## Visão Geral

Listas de Revogação de Certificados (CRL) e Protocolo de Status de Certificado Online (OCSP) permitem que clientes verifiquem se um certificado foi revogado. O UCM suporta ambos os mecanismos.

## Gerenciamento de CRL

### O que é uma CRL?
Uma CRL é uma lista assinada de números de série de certificados revogados, publicada por uma CA. Clientes baixam a CRL e verificam se o número de série de um certificado aparece nela.

### CRL por CA
Cada CA possui sua própria CRL. A lista de CRL mostra todas as suas CAs com:
- **Contagem de revogados** — Número de certificados na CRL
- **Última regeneração** — Quando a CRL foi reconstruída pela última vez
- **Regeneração automática** — Se as atualizações automáticas de CRL estão ativadas

### Regenerando uma CRL
Clique em **Regenerar** para reconstruir a CRL de uma CA imediatamente. Isso é útil após revogar certificados.

### Regeneração Automática
Ative a regeneração automática para reconstruir automaticamente a CRL sempre que um certificado for revogado. Alterne isso por CA.

### Ponto de Distribuição de CRL (CDP)
A URL do CDP é incorporada nos certificados para que clientes saibam onde baixar a CRL. Copie a URL dos detalhes da CRL.

\`\`\`
http://seu-servidor:8080/cdp/{ca_refid}.crl
\`\`\`

> 💡 **Ativação automática**: Quando você cria uma nova CA, o CDP é automaticamente ativado se uma URL Base de Protocolo ou servidor de protocolo HTTP estiver configurado. A URL do CDP é gerada automaticamente — nenhum passo manual necessário.

> ⚠️ **Importante**: As URLs são geradas automaticamente usando a porta do protocolo HTTP e o FQDN do servidor. Se você acessar o UCM via \`localhost\`, a URL não pode ser gerada. Configure seu **FQDN** ou **URL Base de Protocolo** em Configurações → Geral primeiro.

### Baixando CRLs
Baixe CRLs em formato DER ou PEM para distribuição a clientes ou integração com outros sistemas.

## Respondedor OCSP

### O que é OCSP?
O OCSP fornece verificação de status de certificado em tempo real. Em vez de baixar uma CRL inteira, clientes enviam uma consulta para um certificado específico e recebem uma resposta imediata.

### Status OCSP
A seção OCSP mostra:
- **Status do respondedor** — Ativo ou inativo por CA
- **Total de consultas** — Número de requisições OCSP processadas
- **Cache** — Cache de respostas com limpeza diária automática de entradas expiradas

### Cache OCSP

O UCM armazena em cache as respostas OCSP para desempenho. O cache é:
- **Limpo automaticamente** — Respostas expiradas são purgadas diariamente pelo agendador
- **Invalidado na revogação** — Quando um certificado é revogado, sua resposta OCSP em cache é imediatamente limpa
- **Invalidado na remoção de suspensão** — Quando uma Suspensão de Certificado é removida, o cache OCSP é atualizado

### URLs AIA
A extensão Authority Information Access (AIA) é incorporada nos certificados para informar aos clientes onde encontrar:

**Respondedor OCSP** — verificação de revogação em tempo real:
\`\`\`
http://seu-servidor:8080/ocsp
\`\`\`

**Emissores CA** (RFC 5280 §4.2.2.1) — baixar o certificado da CA emissora para construção de cadeia:
\`\`\`
http://seu-servidor:8080/ca/{ca_refid}.cer   (formato DER)
http://seu-servidor:8080/ca/{ca_refid}.pem   (formato PEM)
\`\`\`

Ative Emissores CA por CA na seção **AIA CA Issuers** do painel de detalhes. A URL é gerada automaticamente usando o servidor de protocolo HTTP e o FQDN configurado.

> ⚠️ **Pré-requisito**: As URLs de protocolo (CDP, OCSP, AIA) requerem um **FQDN** válido ou uma **URL Base de Protocolo** configurada em Configurações → Geral. Se você acessar o UCM via \`localhost\`, a ativação desses recursos falhará — defina o FQDN primeiro.

### OCSP vs CRL

| Recurso | CRL | OCSP |
|---------|-----|------|
| Frequência de atualização | Periódica | Tempo real |
| Largura de banda | Lista completa a cada vez | Consulta única |
| Privacidade | Sem rastreamento | Servidor vê consultas |
| Suporte offline | Sim (em cache) | Requer conectividade |

> 💡 Melhor prática: ative tanto CRL quanto OCSP para máxima compatibilidade.
`
  }
}
