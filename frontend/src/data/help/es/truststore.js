export default {
  helpContent: {
    title: 'Almacén de confianza',
    subtitle: 'Administrar certificados de confianza',
    overview: 'Importe y administre certificados de CA raíz e intermedias de confianza. El almacén de confianza se utiliza para la validación de cadenas y puede sincronizarse con el almacén de confianza del sistema operativo.',
    sections: [
      {
        title: 'Tipos de certificado',
        definitions: [
          { term: 'CA raíz', description: 'Ancla de confianza autofirmada de nivel superior' },
          { term: 'Intermedia', description: 'Certificado CA firmado por una raíz u otra intermedia' },
          { term: 'Autenticación de cliente', description: 'Certificado utilizado para autenticación de cliente (mTLS)' },
          { term: 'Firma de código', description: 'Certificado utilizado para verificación de firma de código' },
          { term: 'Personalizado', description: 'Certificado de confianza categorizado manualmente' },
        ]
      },
      {
        title: 'Acciones',
        items: [
          { label: 'Importar archivo', text: 'Suba archivos de certificado PEM, DER o PKCS#7' },
          { label: 'Importar URL', text: 'Obtener un certificado desde una URL remota' },
          { label: 'Agregar PEM', text: 'Pegue texto de certificado codificado en PEM directamente' },
          { label: 'Sincronizar desde el sistema', text: 'Importar las CAs de confianza del SO a UCM' },
          { label: 'Exportar', text: 'Descargar certificados de confianza individualmente' },
        ]
      },
    ],
    tips: [
      'Use "Sincronizar desde el sistema" para poblar rápidamente el almacén de confianza con las CAs del SO',
      'Filtre por propósito para enfocarse en categorías de certificados específicas',
    ],
  },
  helpGuides: {
    title: 'Almacén de confianza',
    content: `
## Descripción general

El almacén de confianza administra los certificados CA de confianza utilizados para la validación de cadenas. Importe CAs raíz e intermedias de fuentes externas o sincronice con el almacén de confianza del sistema operativo.

## Categorías de certificados

- **CA raíz** — Anclas de confianza autofirmadas
- **Intermedia** — CAs firmadas por una raíz u otras intermedias
- **Autenticación de cliente** — Certificados para autenticación de cliente mTLS
- **Firma de código** — Certificados para verificación de firma de código
- **Personalizado** — Certificados categorizados manualmente

## Importar certificados

### Desde archivo
Suba archivos de certificado en estos formatos:
- **PEM** — Codificado en Base64 (individual o agrupado)
- **DER** — Formato binario
- **PKCS#7 (P7B)** — Cadena de certificados

### Desde URL
Obtener un certificado de un endpoint HTTPS remoto. UCM descarga e importa la cadena de certificados del servidor.

### Pegar PEM
Pegue texto de certificado codificado en PEM directamente en el área de texto.

### Sincronizar desde el sistema
Importe todas las CAs de confianza del almacén de confianza del sistema operativo. Esto llena UCM con las mismas CAs raíz que confía el SO (ej., el paquete de CAs de Mozilla en Linux).

> 💡 Sincronizar desde el sistema es una importación única. Los cambios en el almacén de confianza del SO no se reflejan automáticamente.

## Administrar entradas

- **Filtrar por propósito** — Reduzca la lista por categoría de certificado
- **Buscar** — Encuentre certificados por nombre del sujeto
- **Exportar** — Descargue certificados individuales en formato PEM
- **Eliminar** — Elimine un certificado del almacén de confianza

## Casos de uso

### Validación de cadena
Al verificar una cadena de certificados, UCM comprueba el almacén de confianza en busca de CAs raíz reconocidas.

### mTLS
Los certificados de cliente presentados durante la autenticación TLS mutua se validan contra el almacén de confianza.

### ACME
Cuando UCM actúa como cliente ACME (Let's Encrypt), el almacén de confianza se usa para verificar el certificado de la CA ACME.
`
  }
}
