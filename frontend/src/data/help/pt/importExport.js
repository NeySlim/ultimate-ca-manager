export default {
  helpContent: {
    title: 'Importação e Exportação',
    subtitle: 'Migração de dados e backup',
    overview: 'Importe certificados de fontes externas e exporte seus dados PKI. A Importação Inteligente detecta automaticamente os tipos de arquivo. A integração com OPNsense permite sincronização direta com seu firewall.',
    sections: [
      {
        title: 'Importação',
        items: [
          { label: 'Importação Inteligente', text: 'Envie qualquer arquivo de certificado — o UCM detecta automaticamente o formato (PEM, DER, P12, P7B)' },
          { label: 'Sincronização OPNsense', text: 'Conecte ao firewall OPNsense e importe seus certificados e CAs' },
        ]
      },
      {
        title: 'Exportação',
        items: [
          { label: 'Exportar Certificados', text: 'Download em massa de certificados como pacote PEM ou PKCS#7' },
          { label: 'Exportar CAs', text: 'Download em massa de certificados e cadeias de CA' },
        ]
      },
      {
        title: 'Integração OPNsense',
        items: [
          { label: 'Conexão', text: 'Fornecer URL do OPNsense, chave de API e segredo de API' },
          { label: 'Testar Conexão', text: 'Verificar conectividade antes de importar' },
          { label: 'Selecionar Itens', text: 'Escolher quais certificados e CAs importar' },
        ]
      },
    ],
    tips: [
      'A Importação Inteligente lida com pacotes PEM com múltiplos certificados em um único arquivo',
      'Teste a conexão OPNsense antes de executar uma importação completa',
      'Arquivos PKCS#12 requerem a senha correta para importar chaves privadas',
    ],
  },
  helpGuides: {
    title: 'Importação e Exportação',
    content: `
## Visão Geral

Importe certificados de fontes externas e exporte seus dados PKI para backup ou migração.

## Importação Inteligente

O assistente de Importação Inteligente detecta automaticamente os tipos de arquivo e os processa:

### Formatos Suportados
- **PEM** — Certificados únicos ou em pacote, CAs e chaves
- **DER** — Certificado ou chave em formato binário
- **PKCS#12 (P12/PFX)** — Certificado + chave + cadeia (requer senha)
- **PKCS#7 (P7B)** — Cadeia de certificados sem chaves

### Como Funciona
1. Clique em **Importar** ou arraste arquivos para a zona de soltar
2. O UCM analisa cada arquivo e identifica seu conteúdo
3. Revise os itens detectados (CAs, certificados, chaves)
4. Clique em **Importar** para adicioná-los ao UCM

> 💡 A Importação Inteligente lida com pacotes PEM com múltiplos certificados em um único arquivo. Ela distingue automaticamente CAs de certificados de entidade final.

## Integração OPNsense

Sincronize certificados e CAs de um firewall OPNsense:

### Configuração
1. No OPNsense, crie uma chave de API (Sistema → Acesso → Usuários → Chaves de API)
2. No UCM, insira a URL do OPNsense, chave de API e segredo de API
3. Clique em **Testar Conexão** para verificar

### Importação
1. Clique em **Conectar** para buscar certificados e CAs disponíveis
2. Selecione os itens que deseja importar
3. Clique em **Importar Selecionados**

O UCM importa certificados com suas chaves privadas (se disponíveis) e preserva a hierarquia de CA.

## Exportar Certificados

Exportação em massa de todos os certificados:
- **PEM** — Arquivos PEM individuais
- **Pacote P7B** — Todos os certificados em um único arquivo PKCS#7
- **ZIP** — Todos os certificados como arquivos PEM individuais em um ZIP

## Exportar CAs

Exportação em massa de todas as Autoridades Certificadoras:
- **PEM** — Cadeia de certificados em formato PEM
- **Cadeia completa** — Raiz → Intermediária → Sub-CA

## Migração Entre Instâncias UCM

Para migrar de uma instância UCM para outra:
1. Crie um **backup** na origem (Configurações → Backup)
2. Instale o UCM no destino
3. **Restaure** o backup no destino

Isso preserva todos os dados: certificados, CAs, chaves, usuários, configurações e logs de auditoria.
`
  }
}
