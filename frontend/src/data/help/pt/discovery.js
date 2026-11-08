export default {
  helpContent: {
    title: 'Descoberta de Certificados',
    subtitle: 'Encontre certificados TLS na sua rede',
    overview: 'Varra sua rede para encontrar certificados TLS implantados em servidores e endpoints e compará-los com o inventário da sua PKI gerenciada. Localize certificados não rastreados, detecte mudanças e monitore certificados expirando fora do controle do UCM.',
    sections: [
      {
        title: 'Abas',
        items: [
          { label: 'Descobertos', text: 'Todos os certificados encontrados pelas varreduras, com status, expiração e detalhes do endpoint' },
          { label: 'Perfis', text: 'Configurações de varredura salvas, alvos, portas, agendamento, notificações' },
          { label: 'Histórico', text: 'Execuções de varredura passadas com duração, alvos varridos e certificados encontrados' },
        ]
      },
      {
        title: 'Varredura',
        items: [
          { label: 'Varredura Rápida', text: 'Varredura ad-hoc sem salvar um perfil, insira alvos e portas, os resultados chegam ao vivo' },
          { label: 'Alvos', text: 'Inseridos como etiquetas, uma por alvo: hostname, IP, sub-rede CIDR (192.168.1.0/24) ou host:port (10.0.0.1:8443)' },
          { label: 'Portas', text: 'Portas TCP separadas por vírgula (ex. 443, 8443, 636), ou a predefinição de portas comuns' },
          { label: 'Opções avançadas', text: 'Resolução DNS reversa (registros PTR), timeout e concorrência' },
          { label: 'Agendamento', text: 'Os perfis executam manualmente ou automaticamente a cada 1h / 6h / 12h / 24h / 7d' },
          { label: 'Notificações', text: 'Alertas por e-mail sobre novos certificados, mudanças de certificado ou expiração próxima. Um certificado encontrado por SNI num alvo IP é contado como novo a cada varredura' },
        ]
      },
      {
        title: 'Status dos Resultados',
        items: [
          { label: 'Gerenciado', text: 'A impressão digital SHA-256 do certificado corresponde a um certificado no inventário do UCM' },
          { label: 'Não gerenciado', text: 'Encontrado na rede mas não no inventário, candidato a ser trazido para gerenciamento' },
          { label: 'Erro', text: 'O endpoint respondeu mas o handshake TLS ou o certificado falhou (SNI rejeitado, certificado ilegível). Uma conexão recusada, um timeout, uma falha de DNS ou de rede não deixa linha. Tente novamente uma linha, ou Repetir todos os erros da página atual' },
          { label: 'Alterado', text: 'Um endpoint apresentando um certificado diferente da varredura anterior é marcado com um timestamp de Última alteração' },
        ]
      },
    ],
    tips: [
      'Filtre os resultados com os marcadores de status: Todos, Gerenciado, Não gerenciado, Erro',
      'A exportação baixa todos os certificados descobertos como CSV, quaisquer que sejam os filtros',
      'Agende uma varredura diária das sub-redes dos seus servidores com a notificação de novos certificados ativada',
    ],
    warnings: [
      'Executar varreduras e gerenciar perfis requer permissões de administrador; uma sub-rede de perfil é limitada a 1024 endereços (/22), um CIDR inserido como alvo a 65.536 hosts',
    ],
  },
  helpGuides: {
    title: 'Descoberta de Certificados',
    content: `
## Visão Geral

A Descoberta de Certificados varre sua rede para encontrar certificados TLS implantados em servidores e endpoints e compará-los com o inventário da sua PKI gerenciada. Use-a para localizar certificados não rastreados, detectar mudanças e monitorar certificados expirando fora do controle do UCM.

## Abas

### Descobertos
Todos os certificados encontrados pelas varreduras, com status, expiração e detalhes do endpoint. Clique em uma linha para abrir o painel de detalhes com informações do certificado, Subject Alternative Names e histórico de varreduras (visto pela primeira vez, visto pela última vez, última alteração).

### Perfis
Configurações de varredura salvas para varreduras recorrentes: alvos, portas, agendamento e notificações.

### Histórico
Execuções de varredura passadas com duração, alvos varridos e certificados encontrados.

## Varredura Rápida

Execute uma varredura ad-hoc sem salvar um perfil:

1. Clique em **Varredura Rápida**
2. Insira os **alvos**, cada um como etiqueta: hostname, IP, sub-rede CIDR (\`192.168.1.0/24\`) ou \`host:port\` (\`10.0.0.1:8443\`)
3. Insira as **portas**: portas TCP separadas por vírgula (ex. \`443, 8443, 636\`), ou escolha a predefinição de portas comuns
4. Opcionalmente ajuste as **opções avançadas**: resolução DNS reversa (registros PTR), timeout, concorrência
5. Clique em **Iniciar Varredura**: o progresso é atualizado ao vivo via WebSocket

## Perfis de Varredura

Os perfis salvam uma configuração de alvos para uso repetido:

- **Alvos e portas**: mesmos formatos da Varredura Rápida
- **Agendamento**: manual, ou automático a cada 1h / 6h / 12h / 24h / 7d
- **Notificações**: alertas por e-mail quando novos certificados são descobertos, quando um certificado muda em um endpoint ou quando certificados descobertos estão expirando. Um certificado encontrado por SNI num alvo IP é contado como novo a cada varredura

Execute um perfil sob demanda com **Varrer**, ou deixe o agendador executá-lo no intervalo configurado.

## Status dos Resultados

- **Gerenciado**: A impressão digital SHA-256 do certificado corresponde a um certificado no inventário do UCM
- **Não gerenciado**: Encontrado na rede mas não no inventário: candidato a ser trazido para gerenciamento
- **Erro**: O endpoint respondeu mas o handshake TLS ou o certificado falhou (SNI rejeitado, certificado ilegível). Uma conexão recusada, um timeout, uma falha de DNS ou de rede não é registrada

### Detecção de Mudanças
Quando um endpoint apresenta um certificado diferente da varredura anterior, a mudança é registrada (impressão digital anterior mantida, timestamp de **Última alteração**) e pode disparar uma notificação.

## Filtragem e Exportação

- **Marcadores de filtro de status**: Todos, Gerenciado, Não gerenciado, Erro
- **Filtro de perfil**: Restringir os resultados a um perfil de varredura
- **Exportar**: Baixar todos os certificados descobertos como CSV, quaisquer que sejam os filtros
- **Tentar novamente**: Varrer novamente alvos com erro individualmente, ou **Repetir todos os erros** mostrados na página atual
- **Resolver DNS**: Resolução DNS reversa em massa para os IPs descobertos

## Limites e Segurança

- Uma sub-rede de perfil é limitada a 1024 endereços (equivalente a um /22 IPv4), um CIDR inserido como alvo a 65.536 hosts; até 1000 alvos por varredura de perfil
- Faixas privadas RFC1918 e loopback são varríveis: o modelo de implantação on-prem do UCM; faixas link-local, multicast e reservadas são bloqueadas
- As varreduras iniciadas à mão e as alterações de perfil são registradas na auditoria; as execuções agendadas não

## Permissões

- **read:certificates**: Visualizar certificados descobertos, perfis e histórico
- **admin:system**: Criar/editar perfis e executar varreduras
- **delete:certificates**: Excluir resultados descobertos

> 💡 Agende uma varredura diária das sub-redes dos seus servidores e ative a notificação de novos certificados: ela captura certificados implantados fora do seu processo de PKI.
`
  }
}
