export default {
  helpContent: {
    title: 'Ferramentas de Certificado',
    subtitle: 'Decodificar, converter e verificar certificados',
    overview: 'Um conjunto de ferramentas para trabalhar com certificados, CSRs e chaves. Decodifique certificados para inspecionar seu conteúdo, converta entre formatos, verifique endpoints SSL remotos e verifique correspondência de chaves.',
    sections: [
      {
        title: 'Ferramentas Disponíveis',
        items: [
          { label: 'Verificador SSL', text: 'Conectar a um host remoto e inspecionar sua cadeia de certificados SSL/TLS' },
          { label: 'Decodificador de CSR', text: 'Cole um CSR em formato PEM para visualizar seu sujeito, SANs e informações de chave' },
          { label: 'Decodificador de Certificado', text: 'Cole um certificado em formato PEM para inspecionar todos os campos' },
          { label: 'Verificador de Correspondência', text: 'Verificar se um certificado, CSR e chave privada pertencem ao mesmo conjunto' },
          { label: 'Conversor', text: 'Converter entre formatos PEM, DER, PKCS#12 e PKCS#7' },
        ]
      },
      {
        title: 'Detalhes do Conversor',
        items: [
          'Conversão PEM ↔ DER',
          'PEM → PKCS#12 com senha e cadeia completa',
          'PKCS#12 → Extração PEM',
          'PEM → PKCS#7 (P7B) empacotamento de cadeia',
        ]
      },
    ],
    tips: [
      'O Verificador SSL suporta portas personalizadas — use-o para verificar qualquer serviço TLS',
      'O Verificador de Correspondência compara hashes de módulo para verificar pares correspondentes',
      'O Conversor preserva a cadeia completa de certificados ao criar PKCS#12',
    ],
  },
  helpGuides: {
    title: 'Ferramentas de Certificado',
    content: `
## Visão Geral

Um kit de ferramentas para inspecionar, converter e verificar certificados sem sair do UCM.

## Verificador SSL

Inspecione o certificado SSL/TLS de um servidor remoto:

1. Insira o **nome do host** (ex.: \`google.com\`)
2. Opcionalmente altere a **porta** (padrão: 443)
3. Clique em **Verificar**

Os resultados incluem:
- Sujeito e emissor do certificado
- Datas de validade
- SANs (Nomes Alternativos do Sujeito)
- Tipo e tamanho da chave
- Cadeia completa de certificados
- Versão do protocolo TLS

## Decodificador de CSR

Analise e exiba o conteúdo de um CSR:

1. Cole um CSR em formato PEM
2. Clique em **Decodificar**

Mostra: Sujeito, SANs, algoritmo de chave, tamanho da chave, algoritmo de assinatura.

## Decodificador de Certificado

Analise e exiba os detalhes de um certificado:

1. Cole um certificado em formato PEM
2. Clique em **Decodificar**

Mostra: Sujeito, Emissor, SANs, validade, número de série, key usage, extensões, impressões digitais.

## Verificador de Correspondência

Verifique se um certificado, CSR e chave privada pertencem ao mesmo conjunto:

1. Cole o **certificado** PEM
2. Cole a **chave privada** PEM (opcionalmente criptografada — forneça a senha)
3. Opcionalmente cole um **CSR** PEM
4. Clique em **Verificar**

O UCM compara os hashes de módulo (RSA) ou chave pública (EC). Uma correspondência confirma que formam um par válido.

## Conversor

Converta entre formatos de certificado e chave:

### PEM → DER
Converte um PEM codificado em Base64 para formato binário DER.

### PEM → PKCS#12
Cria um arquivo P12/PFX protegido por senha a partir de:
- Certificado PEM
- Chave privada PEM
- Certificados de cadeia opcionais
- Senha para o arquivo P12

### PKCS#12 → PEM
Extrai certificado, chave e cadeia de um arquivo P12:
- Envie o arquivo P12
- Insira a senha
- Baixe os componentes PEM extraídos

### PEM → PKCS#7
Empacota múltiplos certificados em um único arquivo P7B (sem chaves).

> 💡 O conversor preserva a cadeia completa de certificados ao criar arquivos PKCS#12.
`
  }
}
