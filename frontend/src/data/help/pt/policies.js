export default {
  helpContent: {
    title: 'Políticas de Certificado',
    subtitle: 'Regras de emissão e aplicação de conformidade',
    overview: 'Defina e gerencie políticas de certificado que controlam regras de emissão, requisitos de chave, limites de validade e fluxos de aprovação. As políticas são avaliadas em ordem de prioridade quando certificados são solicitados.',
    sections: [
      {
        title: 'Tipos de Política',
        items: [
          { label: 'Emissão', text: 'Regras aplicadas quando novos certificados são criados' },
          { label: 'Renovação', text: 'Regras aplicadas quando certificados são renovados' },
          { label: 'Revogação', text: 'Regras aplicadas quando certificados são revogados' },
        ]
      },
      {
        title: 'Regras',
        items: [
          { label: 'Validade Máxima', text: 'Tempo máximo de vida do certificado em dias' },
          { label: 'Tipos de Chave Permitidos', text: 'Restringir quais algoritmos e tamanhos de chave podem ser usados' },
          { label: 'Restrições de SAN', text: 'Limitar o número de SANs e aplicar padrões de nomes DNS' },
        ]
      },
      {
        title: 'Fluxos de Aprovação',
        items: [
          { label: 'Grupos de Aprovação', text: 'Atribuir um grupo de usuários responsável por aprovar solicitações' },
          { label: 'Mín. Aprovadores', text: 'Número de aprovações necessárias antes da emissão' },
          { label: 'Notificações', text: 'Alertar administradores quando políticas são violadas' },
        ]
      },
    ],
    tips: [
      'Número de prioridade menor = maior precedência. Use 1–10 para políticas críticas.',
      'Atribua políticas a CAs específicas para controle granular.',
      'Ative notificações para detectar violações de políticas rapidamente.',
    ],
  },
  helpGuides: {
    title: 'Políticas de Certificado',
    content: `
## Visão Geral

Políticas de certificado definem as regras e restrições aplicadas quando certificados são emitidos, renovados ou revogados. As políticas são avaliadas em **ordem de prioridade** (número menor = maior precedência) e podem ser atribuídas a CAs específicas.

## Tipos de Política

### Políticas de Emissão
Regras aplicadas quando novos certificados são criados. Este é o tipo mais comum. Controla tipos de chave, períodos de validade, restrições de SAN e se aprovação é necessária.

### Políticas de Renovação
Regras aplicadas quando certificados são renovados. Podem impor validade mais curta na renovação ou exigir reaprovação.

### Políticas de Revogação
Regras aplicadas quando certificados são revogados. Podem exigir aprovação antes da revogação de certificados críticos.

## Configuração de Regras

### Validade Máxima
Tempo máximo de vida do certificado em dias. Valores comuns:
- **90 dias** — Automação de curta duração (estilo ACME)
- **397 dias** — Baseline CA/Browser Forum para TLS público
- **730 dias** — PKI interna/privada
- **365 dias** — Assinatura de código

### Tipos de Chave Permitidos
Restringir quais algoritmos e tamanhos de chave podem ser usados:
- **RSA-2048** — Mínimo para confiança pública
- **RSA-4096** — Segurança superior, certificados maiores
- **EC-P256** — Moderno, rápido, recomendado
- **EC-P384** — Curva elíptica de segurança superior
- **EC-P521** — Segurança máxima (raramente necessário)

### Restrições de SAN
- **Máx. Nomes DNS** — Limitar o número de Nomes Alternativos do Sujeito
- **Padrão DNS** — Restringir a padrões de domínio específicos (ex.: \`*.empresa.com\`)

## Fluxos de Aprovação

Quando **Exigir Aprovação** está ativado, a emissão do certificado é pausada até que o número necessário de aprovadores do grupo atribuído tenha aprovado a solicitação.

### Configuração
- **Grupo de Aprovação** — Selecionar um grupo de usuários responsável por aprovações
- **Mín. Aprovadores** — Número de aprovações necessárias (ex.: 2 de 3 membros do grupo)
- **Notificações** — Alertar administradores quando políticas são violadas

> 💡 Use fluxos de aprovação para certificados de alto valor como assinatura de código e certificados curinga.

## Sistema de Prioridade

As políticas são avaliadas em ordem de prioridade. Números menores têm maior precedência:
- **1–10** — Políticas de segurança críticas (assinatura de código, curinga)
- **10–20** — Conformidade padrão (TLS público, PKI interna)
- **20+** — Padrões permissivos

Quando múltiplas políticas correspondem a uma solicitação de certificado, a política de maior prioridade (menor número) prevalece.

## Escopo

### Todas as CAs
A política se aplica a todas as CAs no sistema. Use para regras de toda a organização.

### CA Específica
A política se aplica apenas a certificados emitidos pela CA selecionada. Use para controle granular.

## Políticas Padrão

O UCM vem com 5 políticas integradas que refletem as melhores práticas PKI do mundo real:
- **Assinatura de Código** (prioridade 5) — Chaves fortes, aprovação necessária
- **Certificados Curinga** (prioridade 8) — Aprovação necessária, máx. 10 SANs
- **TLS para Servidor Web** (prioridade 10) — Conforme CA/B Forum, máx. 397 dias
- **Automação de Curta Duração** (prioridade 15) — 90 dias estilo ACME
- **PKI Interna** (prioridade 20) — 730 dias, regras relaxadas

> 💡 Personalize ou desative políticas padrão para corresponder aos requisitos da sua organização.
`
  }
}
