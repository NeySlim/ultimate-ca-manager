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
          { label: 'Implantação de CRL', text: 'Associar um alvo SSH/SFTP para enviar automaticamente cada CRL regenerada. Cada vínculo define o formato PEM ou DER, o caminho de destino, as CRLs pai opcionais e seu próprio comando de recarga' },
          { label: 'URL do CDP', text: 'URL do Ponto de Distribuição de CRL para incorporar nos certificados' },
          { label: 'Validade', text: 'Validade da CRL por CA de 1 dia até 5 anos (90d/180d/1y/3y/5y para CAs offline que não podem reassinar no prazo). Um aviso aparece acima de um ano, as partes confiantes podem manter dados de revogação obsoletos durante toda a janela' },
          { label: 'CRL Externa', text: 'CAs sem chave/offline não podem autoassinar uma CRL, envie uma gerada junto à chave offline a partir do painel de detalhes da CA; ela é validada (assinatura, emissor, monotonicidade) e servida na mesma URL do CDP (v2.215)' },
        ]
      },
      {
        title: 'Serviço OCSP',
        items: [
          { label: 'Status', text: 'Indica se o respondedor OCSP está ativo para cada CA' },
          { label: 'URL do AIA', text: 'URLs de Acesso à Informação da Autoridade, endpoints do respondedor OCSP e download do certificado do emissor CA incorporados nos certificados emitidos' },
          { label: 'Cache', text: 'Cache de respostas com limpeza diária automática de entradas expiradas' },
          { label: 'Total de Consultas', text: 'Número de requisições OCSP processadas' },
          { label: 'Respondedor Delegado', text: 'Assinar as respostas com um certificado OCSPSigning dedicado em vez da chave da CA, atribua um por CA no painel de detalhes' },
          { label: 'Renovação Automática do Respondedor', text: 'Uma tarefa diária reemite o certificado do respondedor delegado antes da expiração (mesmo par de chaves, renovado de forma idêntica) e o revincula, ativada por padrão' },
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
- **Contagem de revogados**: Número de certificados na CRL
- **Última regeneração**: Quando a CRL foi reconstruída pela última vez
- **Regeneração automática**: Se as atualizações automáticas de CRL estão ativadas

### Regenerando uma CRL
Clique em **Regenerar** para reconstruir a CRL de uma CA imediatamente. Isso é útil após revogar certificados.

### Regeneração Automática
Ative a regeneração automática para reconstruir automaticamente a CRL sempre que um certificado for revogado. Alterne isso por CA.

### Validade da CRL
O agendamento da CRL (por CA) define por quanto tempo cada CRL publicada permanece válida. As opções vão de **1 dia a 5 anos**: 1d, 2d, 3d, 7d, 14d, 30d, 90d, 180d, 1y, 3y, 5y.

- **CAs online** devem manter uma validade curta (dias) para que as partes confiantes captem revogações rapidamente
- **CAs offline** (tipicamente uma raiz que não pode reassinar CRLs no prazo) são o caso de uso previsto para as opções longas: 90d até 5y
- Um aviso é mostrado acima de um ano: as partes confiantes podem manter dados de revogação obsoletos durante toda a janela de validade

### Ponto de Distribuição de CRL (CDP)
A URL do CDP é incorporada nos certificados para que clientes saibam onde baixar a CRL. Copie a URL dos detalhes da CRL.

\`\`\`
http://seu-servidor:8080/cdp/{ca_refid}.crl
\`\`\`

> 💡 **Ativação automática**: Quando você cria uma nova CA, o CDP é automaticamente ativado se uma URL Base de Protocolo ou servidor de protocolo HTTP estiver configurado. A URL do CDP é gerada automaticamente, nenhum passo manual necessário.

> ⚠️ **Importante**: As URLs são geradas automaticamente usando a porta do protocolo HTTP e o FQDN do servidor. Se você acessar o UCM via \`localhost\`, a URL não pode ser gerada. Configure seu **FQDN** ou **URL Base de Protocolo** em Configurações → Geral primeiro.

### Baixando CRLs
Baixe CRLs em formato DER ou PEM para distribuição a clientes ou integração com outros sistemas.

## Respondedor OCSP

### O que é OCSP?
O OCSP fornece verificação de status de certificado em tempo real. Em vez de baixar uma CRL inteira, clientes enviam uma consulta para um certificado específico e recebem uma resposta imediata.

### Status OCSP
A seção OCSP mostra:
- **Status do respondedor**: Ativo ou inativo por CA
- **Total de consultas**: Número de requisições OCSP processadas
- **Cache**: Cache de respostas com limpeza diária automática de entradas expiradas

### Cache OCSP

O UCM armazena em cache as respostas OCSP para desempenho. O cache é:
- **Limpo automaticamente**: Respostas expiradas são purgadas diariamente pelo agendador
- **Invalidado na revogação**: Quando um certificado é revogado, sua resposta OCSP em cache é imediatamente limpa
- **Invalidado na remoção de suspensão**: Quando uma Suspensão de Certificado é removida, o cache OCSP é atualizado

### Respondedor OCSP Delegado

Por padrão, as respostas OCSP são assinadas com a própria chave da CA. Um **respondedor delegado** usa em vez disso um certificado dedicado com o EKU **OCSPSigning**: atribua um por CA no painel de detalhes da CA (apenas certificados portando o EKU OCSPSigning e uma chave privada são elegíveis).

**Renovação automática**: uma tarefa diária reemite o certificado do respondedor antes que ele expire, mesmo par de chaves e extensões, renovado de forma idêntica, e revincula a configuração do respondedor da CA ao novo certificado. Certificados de assinatura OCSP de curta duração (ex. um modelo de 90 dias) rotacionam sem ação manual. Ativada por padrão; pode ser desativada e a janela de renovação ajustada em Configurações › Segurança.

### URLs AIA
A extensão Authority Information Access (AIA) é incorporada nos certificados para informar aos clientes onde encontrar:

**Respondedor OCSP**: verificação de revogação em tempo real:
\`\`\`
http://seu-servidor:8080/ocsp
\`\`\`

**Emissores CA** (RFC 5280 §4.2.2.1): baixar o certificado da CA emissora para construção de cadeia:
\`\`\`
http://seu-servidor:8080/ca/{ca_refid}.cer   (formato DER)
http://seu-servidor:8080/ca/{ca_refid}.pem   (formato PEM)
\`\`\`

Ative Emissores CA por CA na seção **AIA CA Issuers** do painel de detalhes. A URL é gerada automaticamente usando o servidor de protocolo HTTP e o FQDN configurado.

> ⚠️ **Pré-requisito**: As URLs de protocolo (CDP, OCSP, AIA) requerem um **FQDN** válido ou uma **URL Base de Protocolo** configurada em Configurações → Geral. Se você acessar o UCM via \`localhost\`, a ativação desses recursos falhará, defina o FQDN primeiro.

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
