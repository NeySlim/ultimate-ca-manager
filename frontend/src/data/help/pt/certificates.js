export default {
  helpContent: {
    title: 'Certificados',
    subtitle: 'Emitir, gerenciar e monitorar certificados',
    overview: 'Gerenciamento central de todos os certificados X.509. Emita novos certificados das suas CAs, importe certificados existentes, acompanhe datas de expiração e gerencie renovações e revogações.',
    sections: [
      {
        title: "Análise de conformidade",
        content: "A ação « Analisar » no detalhe de um certificado passa-o por linters de padrões e mostra os resultados. Apenas informativo — nunca bloqueia a emissão.",
        items: [
          { label: "Perfis", text: "RFC 5280 (sempre relevante) e CA/Browser Forum Baseline Requirements (certificados TLS de servidor)" },
          { label: "Severidades", text: "Os resultados são classificados: fatal, error, warning, notice, info" },
          { label: "Motor", text: "Alimentado por pkilint (e zlint quando o seu binário está presente) — dependência opcional do servidor" },
          { label: "PKI interna", text: "As regras do CA/Browser Forum visam certificados públicos; espere resultados não aplicáveis numa PKI interna" },
        ]
      },
      {
        title: 'Status do Certificado',
        definitions: [
          { term: 'Válido', description: 'Dentro do período de validade e não revogado' },
          { term: 'Expirando', description: 'Expirará dentro de 30 dias' },
          { term: 'Expirado', description: 'Passou da data "Não Depois"' },
          { term: 'Revogado', description: 'Explicitamente revogado (publicado na CRL)' },
          { term: 'Órfão', description: 'A CA emissora não existe mais no sistema' },
          { term: 'Arquivado', description: 'Substituído por uma renovação ou reinscrição que manteve o registro antigo para histórico (SCEP, EST, WSTEP, ACME, respondedor OCSP); listado com o filtro de status "Arquivado"' },
        ]
      },
      {
        title: 'Ações',
        items: [
          { label: 'Emitir', text: 'Criar um novo certificado assinado por uma das suas CAs' },
          { label: 'Importar', text: 'Importar um certificado existente (PEM, DER ou PKCS#12)' },
          { label: 'Renovar', text: 'No lugar desde a v2.214: mesmos id/refid, novo número de série e nova validade — o número de série substituído permanece na CRL até a expiração antiga. Um certificado revogado não pode ser renovado' },
          { label: 'Renomear', text: 'Definir um nome de exibição independente do CN (por padrão o CN, ou o primeiro nome DNS dos SANs para certificados sem CN)' },
          { label: 'Revogar', text: 'Marcar como revogado com um motivo — aparecerá na CRL' },
          { label: 'Remover Suspensão', text: 'Remover suspensão de um certificado revogado com motivo "Suspensão de Certificado" — restaura para status válido' },
          { label: 'Revogar e Substituir', text: 'Revogar e emitir imediatamente um substituto' },
          { label: 'Exportar', text: 'Baixar em formato PEM, DER, PKCS#12 ou JKS' },
          { label: 'Modo de compatibilidade PKCS#12 (v2.222)', text: 'Os diálogos de exportação oferecem um perfil 3DES/SHA-1 para os importadores que rejeitam o arquivo AES-256 por defeito como senha incorreta: Android 15 e anteriores, macOS 14 e anteriores, Windows Server 2016 e anteriores, Java antigo. Desativado por defeito, protege menos o ficheiro' },
          { label: 'Comparar', text: 'Comparação lado a lado de dois certificados' },
        ]
      },
      {
        title: 'EKU extras personalizados (RFC 5280 §4.2.1.12)',
        content: 'O formulário de emissão e o modal de assinatura de CSR expõem um seletor múltiplo "EKU extras" que adiciona OIDs Extended Key Usage além dos padrões do tipo de certificado:',
        items: [
          { label: 'Catálogo', text: '18 EKUs conhecidos (Microsoft RDP 1.3.6.1.4.1.311.54.1.2, smartcard logon, document signing, IPsec, Kerberos PKINIT, etc.)' },
          { label: 'OID livre', text: 'Qualquer OID pontuado bem formado correspondendo a ^[0-2](?:\\.(?:0|[1-9]\\d*)){1,15}$' },
          { label: 'Limite', text: 'Até 16 OIDs no total por certificado' },
          { label: 'Fusão, nunca substituição', text: 'Os EKUs padrão do tipo (ex. serverAuth) permanecem fixos — os extras são adicionados por cima' },
          { label: 'Rejeitado', text: 'anyExtendedKeyUsage (2.5.29.37.0) é explicitamente proibido' },
        ]
      },
      {
        title: 'Arquivos de certificado em disco (v2.140)',
        items: [
          { label: 'Auto-materializados', text: 'Os arquivos .crt / .key são escritos em data/certs/ em cada caminho de criação (UI, assinatura CSR, ACME, SCEP, import)' },
          { label: 'CAs também', text: 'Os arquivos .crt / .key das CAs são escritos em data/cas/ pelo mesmo mecanismo' },
          { label: 'Rede de segurança', text: 'Uma varredura de regeneração na inicialização reconstrói qualquer arquivo ausente a partir da base de dados' },
          { label: 'Não bloqueante', text: 'Erros de escrita são logados mas nunca abortam a transação de DB' },
        ]
      },
      {
        title: 'Implantação (v2.215)',
        content: 'Envie este certificado para hosts remotos via SSH/SFTP — somente admin, os alvos são gerenciados em Configurações › Implantação.',
        items: [
          { label: 'Anexar alvo', text: 'A partir da visão de detalhe do certificado: escolha um alvo de implantação e defina caminhos de destino absolutos para o certificado, a chave privada e/ou a cadeia completa (pelo menos um)' },
          { label: 'Mesmo host', text: 'Para implantar no próprio host UCM, use um alvo SFTP em 127.0.0.1 com uma conta SSH dedicada; o serviço isolado não pode gravar fora do diretório de dados' },
          { label: 'Automático', text: 'Na emissão e na renovação, os arquivos vinculados são reenviados e o comando de recarga do alvo é executado — as entregas são enfileiradas com tentativas de repetição' },
          { label: 'Arquivos', text: 'Gravados de forma atômica exatamente nos caminhos configurados (o diretório pai deve existir): chave 0600, certificado/cadeia 0644' },
          { label: 'Implantar agora', text: 'Envio manual a partir da visão de detalhe, com o status da entrega e o último erro exibidos por alvo' },
        ]
      },

    ],
    tips: [
      'Marque com estrela ⭐ certificados importantes para adicioná-los à sua lista de favoritos',
      'Use filtros para encontrar rapidamente certificados por status, CA ou texto de pesquisa — sua seleção é preservada ao recarregar',
      'A renovação mantém o mesmo registro (id, refid, data de criação) — chaves mantidas pelo UCM são regeneradas, certificados inscritos via protocolo (SCEP/EST/ACME) mantêm sua chave do lado do cliente',
      'Precisa de um EKU não padrão (Microsoft RDP, smartcard logon, document signing)? Adicione via "EKU extras" em vez de editar templates',
    ],
    warnings: [
      'A revogação é geralmente permanente — exceto "Suspensão de Certificado" que pode ser removida',
      'Um certificado válido e não revogado não pode ser excluído (409) — revogue-o primeiro para que a revogação chegue à CRL/OCSP; as revogações sobrevivem à exclusão',
    ],
  },
  helpGuides: {
    title: 'Certificados',
    content: `
## Visão Geral

Gerenciamento central de todos os certificados X.509. Emita novos certificados, importe existentes, acompanhe datas de expiração, gerencie renovações e revogações.

## Status do Certificado

- **Válido** — Dentro do período de validade e não revogado
- **Expirando** — Expirará dentro de 30 dias (configurável)
- **Expirado** — Passou da data "Não Depois"
- **Revogado** — Explicitamente revogado, publicado na CRL
- **Órfão** — A CA emissora não existe mais no UCM
- **Arquivado** — Substituído por uma renovação ou reinscrição que manteve o registro antigo para histórico (SCEP, EST, WSTEP, ACME, respondedor OCSP)

## Emitindo um Certificado

1. Clique em **Emitir Certificado**
2. Selecione a **CA Assinante** (deve ter chave privada)
3. Preencha o Sujeito (CN é obrigatório, outros campos opcionais)
4. Adicione Nomes Alternativos do Sujeito (SANs): nomes DNS, IPs, e-mails
5. Escolha o tipo e tamanho da chave
6. Defina o período de validade
7. Opcionalmente aplique um **Modelo** para pré-preencher configurações
8. Clique em **Emitir**

### Usando Modelos
Modelos pré-preenchem Key Usage, Extended Key Usage, padrões de sujeito e validade. Selecione um modelo antes de preencher o formulário para economizar tempo.

## Importando Certificados

Formatos suportados:
- **PEM** — Certificados únicos ou em pacote
- **DER** — Formato binário
- **PKCS#12 (P12/PFX)** — Certificado + chave + cadeia (senha obrigatória)
- **PKCS#7 (P7B)** — Cadeia de certificados sem chaves

## Renovando um Certificado

Desde a v2.214, a renovação atualiza o certificado **no lugar**:
- Mesmo registro: **id, refid e data de criação nunca mudam** — as integrações mantêm suas referências
- Mesmos Sujeito e SANs; novo número de série e novo período de validade
- Certificados cuja chave o UCM detém têm sua **chave regenerada**; certificados inscritos via protocolo (SCEP/EST/ACME) são reassinados com sua chave pública existente
- O **número de série substituído continua publicado na CRL** (motivo \`superseded\`) e responde \`revoked\` via OCSP até a expiração original do certificado antigo
- \`renewed_at\` / \`renewed_times\` registram o histórico de renovações
- Um certificado revogado não pode ser renovado (409) — emita um novo em vez disso

**Exclusão**: um certificado válido e não revogado não pode ser excluído (409) — revogue-o primeiro para que as partes confiantes vejam a mudança. As revogações são persistidas independentemente do registro do certificado e sobrevivem à exclusão.

## Revogando um Certificado

1. Selecione o certificado → **Revogar**
2. Escolha um motivo de revogação (Comprometimento de Chave, Comprometimento da CA, Mudança de Afiliação, Substituído, Cessação de Operação, Suspensão de Certificado, etc.)
3. Confirme a revogação

Certificados revogados são publicados na CRL na próxima regeneração.

> ⚠ A revogação é geralmente permanente — exceto **Suspensão de Certificado** que pode ser removida.

### Remover Suspensão

Se um certificado foi revogado com o motivo **Suspensão de Certificado**, ele pode ser restaurado para o status válido:

1. Abra os detalhes do certificado revogado
2. O botão **Remover Suspensão** aparece na barra de ações (apenas para revogações por Suspensão de Certificado)
3. Clique em **Remover Suspensão** para restaurar o certificado
4. O certificado retorna ao status válido, a CRL é regenerada e o cache OCSP é atualizado

> 💡 A Suspensão de Certificado é útil para suspensões temporárias (ex.: dispositivo perdido, investigação pendente).

### Revogar e Substituir
Combina revogação com reemissão imediata. O novo certificado herda o mesmo Sujeito e SANs.

## Exportando Certificados

Formatos de exportação:
- **PEM** — Apenas o certificado
- **PEM + Cadeia** — Certificado com cadeia completa do emissor
- **DER** — Formato binário
- **PKCS#12** — Certificado + chave + cadeia, protegido por senha

## Favoritos

Marque com estrela ⭐ certificados importantes para salvá-los nos favoritos. Favoritos aparecem primeiro em visualizações filtradas e são acessíveis pelo filtro de favoritos.

## Comparando Certificados

Selecione dois certificados e clique em **Comparar** para ver uma comparação lado a lado de Sujeito, SANs, Key Usage, validade e extensões.

## Filtragem e Pesquisa

- **Filtro de status** — Válido, Expirando, Expirado, Revogado, Órfão, Arquivado
- **Filtro de CA** — Mostrar certificados de uma CA específica
- **Filtro de origem** — Filtrar pela forma como o certificado entrou no UCM (emitido, importado, ACME, SCEP, etc.)
- **Filtro de modelo** — Encontrar certificados **modificados a partir do modelo**: emitidos a partir de um modelo, mas com o tipo de chave, a validade ou o digest explicitamente sobrescritos no momento da solicitação. Os campos divergentes são listados nos detalhes do certificado; o registro é congelado na emissão
- **Pesquisa de texto** — Pesquisar por CN, número de série ou SAN
- **Ordenação** — Por nome, data de expiração, data de criação, status
## Análise de conformidade

A ação **Analisar** (detalhe do certificado) verifica a conformidade com os padrões X.509. Apenas informativo.

- **RFC 5280** — perfil X.509 do IETF, sempre relevante
- **CA/Browser Forum** — Baseline Requirements para certificados TLS públicos (ruído esperado em PKI interna)
- Severidades: fatal / error / warning / notice / info
- Motor: pkilint (+ zlint quando presente) — dependência opcional do servidor, degradação graciosa se ausente

`
  }
}
