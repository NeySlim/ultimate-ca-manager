export default {
  helpContent: {
    title: 'Recuperación de claves',
    subtitle: 'Recuperar claves privadas archivadas bajo control dual',
    overview: 'La recuperación de claves obtiene la clave privada archivada de un certificado emitido previamente mediante un flujo de trabajo sujeto a aprobación y completamente auditado. Existe para las claves que no se exportaron en el momento de la emisión (el preset no lo permitía, o la exportación se omitió) y que se necesitan más tarde, con un rastro de aprobación asociado a la recuperación.',
    sections: [
      {
        title: 'Flujo de trabajo',
        items: [
          { label: 'Solicitud', text: 'Un usuario solicita la recuperación de la clave archivada de un certificado específico, indicando un motivo' },
          { label: 'Aprobación (cuatro ojos)', text: 'Un administrador revisa y aprueba; con el control dual activado (por defecto), el solicitante no puede aprobar su propia solicitud' },
          { label: 'Descarga', text: 'Una vez aprobada, la clave se entrega como un paquete PKCS#12 protegido con contraseña' },
          { label: 'Certificado sustituido (v2.251)', text: 'La aprobación y la recuperación responden 410 salvo que el certificado de la solicitud siga siendo aquel sobre el que se abrió. Una restauración que reemplaza cancela las solicitudes abiertas sobre los certificados que elimina' },
        ]
      },
      {
        title: 'Requisitos',
        items: [
          { label: 'Clave archivada', text: 'La clave privada del certificado debe estar almacenada en la base de datos, la recuperación no puede reconstruir una clave que nunca se archivó' },
          { label: 'Control dual', text: 'Activado por defecto: la solicitud y la aprobación son acciones separadas realizadas por personas distintas. Las solicitudes, aprobaciones y descargas quedan registradas en el registro de auditoría; una aprobación o descarga rechazada no' },
        ]
      },
    ],
    tips: [
      'La recuperación de claves es para claves que no se exportaron cuando se emitió el certificado; no sustituye la restricción de la exportación de claves en el momento de la emisión.',
      'Cada solicitud, aprobación y descarga queda registrada en el registro de auditoría; los rechazos no.',
    ],
    warnings: [
      'Un certificado cuya clave privada nunca se archivó no puede recuperarse, no hay nada que entregar.',
    ],
  },
  helpGuides: {
    title: 'Recuperación de claves',
    content: `
## Visión general

La recuperación de claves obtiene la **clave privada archivada** de un certificado emitido previamente mediante un flujo de trabajo sujeto a aprobación y completamente auditado. Está pensada para claves que **no se exportaron en el momento de la emisión**: el preset no permitía la exportación, o simplemente se omitió, y que se necesitan más tarde, con un rastro de aprobación asociado a la recuperación.

La recuperación solo funciona cuando la clave privada se archivó (se almacenó en la base de datos) en la emisión. No puede reconstruir una clave que nunca se conservó.

## Flujo de trabajo

### 1. Solicitud
Un usuario abre una solicitud de recuperación para un certificado específico e indica un motivo. La solicitud queda registrada y pasa al estado pendiente.

### 2. Aprobación (cuatro ojos)
Un administrador revisa la solicitud y la aprueba. Con el control dual activado (por defecto), el solicitante **no puede aprobar su propia solicitud**: la solicitud y la aprobación son acciones separadas realizadas por personas distintas.

### 3. Descarga
Una vez aprobada, la clave archivada se entrega como un paquete **PKCS#12 protegido con contraseña**. La descarga queda registrada en el registro de auditoría.

## Requisitos

- **Clave archivada**: la clave privada del certificado debe estar presente en la base de datos. Los certificados cuya clave nunca se archivó no pueden recuperarse.
- **Control dual**: activado por defecto, la solicitud y la aprobación son pasos distintos realizados por usuarios diferentes. Un administrador puede desactivarlo y entonces aprobar su propia solicitud.

## Permisos

- **read:key_recovery**: Ver las solicitudes
- **write:key_recovery**: Solicitar una recuperación
- **admin**: Aprobar o denegar una solicitud de recuperación pendiente
- **read:private_keys**: Necesario para la exportación *directa* de la clave privada desde la página Certificados (omitiendo este flujo de trabajo). De los roles integrados solo Admin lo posee; un rol personalizado puede concederlo

## Qué es (y qué no es)

La recuperación de claves añade un **rastro de aprobación** a la obtención de una clave archivada después de la emisión. La exportación directa de la clave privada está protegida por el ámbito **read:private_keys**: los roles que no lo tienen (incluido el rol Operator integrado) deben pasar por la recuperación de claves. Un administrador, o un rol personalizado con ese ámbito, exporta la clave directamente, sin aprobación, por lo que la aprobación de cuatro ojos solo obliga a los roles que no lo tienen.

> 💡 Cada solicitud, aprobación y descarga se registra en el registro de auditoría; los rechazos no.
`
  }
}
