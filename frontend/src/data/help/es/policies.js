export default {
  helpContent: {
    title: 'Políticas de certificados',
    subtitle: 'Reglas de emisión y cumplimiento normativo',
    overview: 'Defina y gestione políticas de certificados que controlan las reglas de emisión, requisitos de clave, límites de validez y flujos de aprobación. Las políticas se evalúan en orden de prioridad cuando se solicitan certificados.',
    sections: [
      {
        title: 'Operaciones',
        items: [
          { label: 'Emisión', text: 'El formulario de emisión, la firma de CSR y la firma masiva, y las renovaciones que realiza un operador' },
          { label: 'Renovación', text: 'Renovaciones por un operador, una o masivas, y por el planificador, que encola su renovación en lugar de realizarla' },
          { label: 'Revocación', text: 'Revocaciones de certificados y de CA intermedias por un operador (una CA también bajo las políticas limitadas a ella); un cliente ACME no puede esperar una decisión, por lo que su revocación se rechaza' },
          { label: 'Varias a la vez', text: 'Una política puede regir varias operaciones; una sin ninguna (un antiguo tipo de renovación o revocación, nunca aplicado) no rige nada hasta que elijas' },
        ]
      },
      {
        title: 'Reglas',
        items: [
          { label: 'Validez máxima', text: 'Duración máxima del certificado en días' },
          { label: 'Tipos de clave permitidos', text: 'Restringir qué algoritmos y tamaños de clave se pueden utilizar' },
          { label: 'Restricciones de SAN', text: 'Limitar el número de SAN y aplicar patrones de nombres DNS' },
        ]
      },
      {
        title: 'Flujos de aprobación',
        items: [
          { label: 'Grupos de aprobación', text: 'Asignar un grupo de usuarios responsable de aprobar solicitudes' },
          { label: 'Aprobadores mínimos', text: 'Número de aprobaciones requeridas antes de la emisión' },
          { label: 'Notificaciones', text: 'Correo cuando la política rechaza una operación o la retiene para aprobación; a las direcciones indicadas o, si no hay, a sus aprobadores. Un rechazo repetido se notifica una vez por hora' },
        ]
      },
    ],
    tips: [
      'Un número de prioridad más bajo = mayor precedencia. Use 1–10 para políticas críticas.',
      'Aplique políticas a CA específicas para un control granular.',
      'Active las notificaciones para detectar infracciones de políticas a tiempo.',
    ],
  },
  helpGuides: {
    title: 'Políticas de certificados',
    content: `
## Descripción general

Las políticas de certificados definen las reglas y restricciones aplicadas cuando se emiten, renuevan o revocan certificados. Las políticas se evalúan en **orden de prioridad** (número menor = mayor precedencia) y pueden aplicarse a CA específicas.

## Operaciones

Una política rige una o varias operaciones: su requisito de aprobación y sus reglas se aplican a ellas.

### Emisión
El formulario de emisión, la firma de CSR y la firma masiva, y las renovaciones que realiza un operador. Es la opción más común. Controla tipos de clave, períodos de validez, restricciones de SAN y si se requiere aprobación.

### Renovación
Renovaciones por un operador, una o masivas, y por el planificador. Con una política de renovación que requiere aprobación, el planificador encola la renovación en lugar de realizarla, y la aprobación vuelve a firmar la clave que conserva el servidor.

### Revocación
Revocaciones de certificados (uno, masivas, desde los certificados de usuario) y de CA intermedias. Se limita por la CA emisora, la plantilla y el patrón DNS; la revocación de una CA la retienen también las políticas limitadas a esa CA, ya que todos los certificados que emitió caen con ella. Las demás reglas no se aplican. Un cliente ACME no puede esperar una decisión: su revocación se rechaza y se deja a los operadores. Eliminar un registro mTLS se rechaza hasta que se revoque su certificado, sea quien sea su titular; los administradores lo omiten.

Una política creada antes de que existieran las operaciones conserva lo que hacía: una política de emisión sigue siéndolo, y un tipo de renovación o revocación, nunca aplicado, no rige nada hasta que elijas sus operaciones.

## Configuración de reglas

### Validez máxima
Duración máxima del certificado en días. Valores comunes:
- **90 días**: Automatización de corta duración (estilo ACME)
- **397 días**: Línea base del CA/Browser Forum para TLS público
- **730 días**: PKI interna/privada
- **365 días**: Firma de código

### Tipos de clave permitidos
Restringir qué algoritmos y tamaños de clave se pueden utilizar:
- **RSA-2048**: Mínimo para confianza pública
- **RSA-4096**: Mayor seguridad, certificados más grandes
- **EC-P256**: Moderno, rápido, recomendado
- **EC-P384**: Curva elíptica de mayor seguridad
- **EC-P521**: Máxima seguridad (raramente necesario)

### Restricciones de SAN
- **Máximo de nombres DNS**: Limitar el número de Subject Alternative Names
- **Patrón DNS**: Restringir a patrones de dominio específicos (p. ej. \`*.company.com\`)

## Flujos de aprobación

Cuando se activa **Requerir aprobación**, la emisión del certificado se pausa hasta que el número requerido de aprobadores del grupo asignado hayan aprobado la solicitud.

### Configuración
- **Grupo de aprobación**: Seleccionar un grupo de usuarios responsable de las aprobaciones
- **Aprobadores mínimos**: Número de aprobaciones requeridas (p. ej. 2 de 3 miembros del grupo)
- **Notificaciones**: correo cuando la política rechaza una operación (una regla incumplida) o la retiene para aprobación. Se envía a las direcciones de notificación de la política o, si no hay, a sus aprobadores (los miembros de su grupo de aprobación, o todo usuario que pueda aprobar). Cada solicitud retenida se notifica una vez, con un enlace a ella; el mismo rechazo repetido, por ejemplo por un cliente ACME que reintenta, una vez por hora. Debe haber SMTP configurado

> 💡 Use flujos de aprobación para certificados de alto valor como firma de código y certificados comodín.

## Sistema de prioridad

Las políticas se evalúan en orden de prioridad. Los números más bajos tienen mayor precedencia:
- **1–10**: Políticas de seguridad críticas (firma de código, comodín)
- **10–20**: Cumplimiento estándar (TLS público, PKI interna)
- **20+**: Valores predeterminados permisivos

Cuando varias políticas coinciden con una solicitud de certificado, la de mayor prioridad (número más bajo) prevalece.

## Alcance

### Todas las CA
La política se aplica a todas las CA del sistema. Úsela para reglas a nivel de organización.

### CA específica
La política se aplica solo a certificados emitidos por la CA seleccionada. Úsela para un control granular.

## Políticas predeterminadas

UCM incluye 5 políticas integradas que reflejan las mejores prácticas de PKI del mundo real:
- **Firma de código** (prioridad 5): Claves fuertes, aprobación requerida
- **Certificados comodín** (prioridad 8): Aprobación requerida, máximo 10 SAN
- **TLS para servidor web** (prioridad 10): Conforme al CA/B Forum, máximo 397 días
- **Automatización de corta duración** (prioridad 15): Estilo ACME de 90 días
- **PKI interna** (prioridad 20): 730 días, reglas flexibles

> 💡 Personalice o desactive las políticas predeterminadas para adaptarlas a los requisitos de su organización.
`
  }
}
