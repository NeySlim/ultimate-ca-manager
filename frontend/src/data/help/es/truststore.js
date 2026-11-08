export default {
  helpContent: {
    title: 'Almacén de confianza',
    subtitle: 'Administrar certificados de confianza',
    overview: 'Conserve certificados de CA raíz e intermedias de confianza. La vista de cadena de un certificado y sus exportaciones completan la cadena con un certificado del almacén de confianza cuyo sujeto coincida con el nombre del emisor. El almacén puede llenarse desde el almacén de confianza del sistema operativo o desde las CAs que UCM administra.',
    sections: [
      {
        title: 'Tipos de certificado',
        definitions: [
          { term: 'CA raíz', description: 'Ancla de confianza autofirmada de nivel superior' },
          { term: 'Intermedia', description: 'Certificado CA firmado por una raíz u otra intermedia' },
          { term: 'Sistema', description: 'Importado desde el almacén de confianza del sistema operativo' },
          { term: 'Firma de código', description: 'Certificado utilizado para verificación de firma de código' },
          { term: 'Correo electrónico', description: 'Certificado utilizado para S/MIME' },
          { term: 'Personalizado', description: 'Certificado de confianza categorizado manualmente' },
        ]
      },
      {
        title: 'Acciones',
        items: [
          { label: 'Agregar', text: 'Agrega certificados de las CAs que UCM administra. Un certificado externo se agrega mediante la API (POST /api/v2/truststore con PEM, o /api/v2/truststore/import con un archivo PEM o DER)' },
          { label: 'Sincronizar desde el sistema', text: 'Importar las CAs de confianza del SO a UCM, hasta el número elegido (500 por defecto, 1000 como máximo)' },
          { label: 'Exportar', text: 'Descargar certificados de confianza individualmente' },
          { label: 'Eliminar selección', text: 'Seleccione varios certificados y elimínelos a la vez, por ejemplo las CAs del sistema filtradas como caducadas; solo se eliminan las filas que muestran los filtros actuales' },
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

El almacén de confianza conserva certificados CA de confianza. Llénelo desde las CAs que UCM administra o desde el almacén de confianza del sistema operativo.

## Categorías de certificados

- **CA raíz**: Anclas de confianza autofirmadas
- **Intermedia**: CAs firmadas por una raíz u otras intermedias
- **Sistema**: Importados desde el almacén de confianza del sistema operativo
- **Firma de código**: Certificados para verificación de firma de código
- **Correo electrónico**: Certificados para S/MIME
- **Personalizado**: Certificados categorizados manualmente

## Agregar certificados

### Desde las CAs administradas
**Agregar** lista las CAs que UCM administra: seleccione las que quiera considerar de confianza.

### Certificados externos
La página no tiene un formulario de subida para un certificado ajeno a UCM. Agréguelo mediante la API: \`POST /api/v2/truststore\` con su PEM, o \`POST /api/v2/truststore/import\` con un archivo PEM o DER.

### Sincronizar desde el sistema
Importe las CAs de confianza del almacén de confianza del sistema operativo (ej., el paquete de CAs de Mozilla en Linux), hasta el número elegido: 500 por defecto, 1000 como máximo.

> 💡 Sincronizar desde el sistema es una importación única. Los cambios en el almacén de confianza del SO no se reflejan automáticamente.

## Administrar entradas

- **Filtrar por propósito**: Reduzca la lista por categoría de certificado
- **Buscar**: Encuentre certificados por nombre del sujeto
- **Exportar**: Descargue certificados individuales en formato PEM
- **Eliminar**: Elimine un certificado del almacén de confianza
- **Eliminar selección**: Seleccione varios certificados y elimínelos a la vez, por ejemplo las CAs del sistema filtradas como caducadas; solo se eliminan las filas que muestran los filtros actuales

## Casos de uso

### Cadenas
La vista de cadena de un certificado, y sus exportaciones con la cadena, toman un certificado del almacén de confianza cuyo sujeto coincida con el nombre del emisor para completar la cadena. No se verifica ninguna firma contra el almacén de confianza.

El almacén de confianza no interviene en la autenticación de cliente mTLS (que usa la CA de confianza elegida en Configuración › Seguridad) ni en la conexión del cliente ACME con su CA.
`
  }
}
