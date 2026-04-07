export default {
  helpContent: {
    title: 'Plantillas de certificados',
    subtitle: 'Perfiles de certificados reutilizables',
    overview: 'Defina perfiles de certificados reutilizables con campos de sujeto, uso de clave, uso extendido de clave, períodos de validez y otras extensiones preconfiguradas. Aplique plantillas al emitir o firmar certificados.',
    sections: [
      {
        title: 'Tipos de plantilla',
        definitions: [
          { term: 'End-Entity', description: 'Para certificados de servidor, cliente, firma de código y correo electrónico' },
          { term: 'CA', description: 'Para crear Autoridades de Certificación intermedias' },
        ]
      },
      {
        title: 'Características',
        items: [
          { label: 'Valores predeterminados del sujeto', text: 'Prellenar Organización, OU, País, Estado, Ciudad' },
          { label: 'Uso de clave', text: 'Firma digital, cifrado de clave, etc.' },
          { label: 'Uso extendido de clave', text: 'Autenticación de servidor, autenticación de cliente, firma de código, protección de correo' },
          { label: 'Validez', text: 'Período de validez predeterminado en días' },
          { label: 'Duplicar', text: 'Clonar una plantilla existente y modificarla' },
          { label: 'Importar/Exportar', text: 'Compartir plantillas como archivos JSON entre instancias de UCM' },
        ]
      },
    ],
    tips: [
      'Cree plantillas separadas para servidores TLS, clientes y firma de código',
      'Use la acción Duplicar para crear rápidamente variaciones de una plantilla',
    ],
  },
  helpGuides: {
    title: 'Plantillas de certificados',
    content: `
## Descripción general

Las plantillas definen perfiles de certificados reutilizables. En lugar de configurar manualmente el uso de clave, uso extendido de clave, validez y campos de sujeto cada vez, aplique una plantilla para prellenar todo.

## Tipos de plantilla

### Plantillas End-Entity
Para certificados de servidor, certificados de cliente, firma de código y protección de correo. Estas plantillas típicamente establecen:
- **Uso de clave** — Firma digital, cifrado de clave
- **Uso extendido de clave** — Autenticación de servidor, autenticación de cliente, firma de código, protección de correo

### Plantillas CA
Para crear CAs intermedias. Estas establecen:
- **Uso de clave** — Firma de certificado, firma de CRL
- **Restricciones básicas** — CA:TRUE, longitud de ruta opcional

## Crear una plantilla

1. Haga clic en **Crear plantilla**
2. Ingrese un **nombre** y una descripción opcional
3. Seleccione el **tipo** de plantilla (End-Entity o CA)
4. Configure los **valores predeterminados del sujeto** (O, OU, C, ST, L)
5. Seleccione las opciones de **uso de clave**
6. Seleccione los valores de **uso extendido de clave**
7. Establezca el **período de validez predeterminado** en días
8. Haga clic en **Crear**

## Usar plantillas

Al emitir un certificado o firmar un CSR, seleccione una plantilla del menú desplegable. La plantilla prellena:
- Campos del sujeto (puede sobrescribirlos)
- Uso de clave y uso extendido de clave
- Período de validez

## Duplicar plantillas

Haga clic en **Duplicar** para crear una copia de una plantilla existente. Modifique la copia sin afectar la original.

## Importar y exportar

### Exportar
Exporte plantillas como JSON para compartir entre instancias de UCM.

### Importar
Importe desde:
- **Archivo JSON** — Suba un archivo JSON de plantilla
- **Pegar JSON** — Pegue JSON directamente en el área de texto

## Ejemplos comunes de plantillas

### Servidor TLS
- Uso de clave: Firma digital, cifrado de clave
- Uso extendido de clave: Autenticación de servidor
- Validez: 365 días

### Autenticación de cliente
- Uso de clave: Firma digital
- Uso extendido de clave: Autenticación de cliente
- Validez: 365 días

### Firma de código
- Uso de clave: Firma digital
- Uso extendido de clave: Firma de código
- Validez: 365 días
`
  }
}
