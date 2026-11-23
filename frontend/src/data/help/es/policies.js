export default {
  helpContent: {
    title: 'Políticas de certificados',
    subtitle: 'Reglas de emisión y cumplimiento normativo',
    overview: 'Definir y gestionar políticas de certificados que controlan las reglas de emisión, los requisitos de clave, los límites de validez y los flujos de aprobación. Las políticas se evalúan por orden de prioridad cuando se solicitan certificados.',
    sections: [
      {
        title: 'Operaciones',
        items: [
          { label: 'Emisión', text: 'El formulario de emisión, la firma de CSR y la firma masiva, y las renovaciones que realiza un operador' },
          { label: 'Renovación', text: 'Las renovaciones de un operador, una o en masa, y las del planificador, que pone su renovación en cola en lugar de realizarla' },
          { label: 'Revocación', text: 'Las revocaciones de certificados y de CA intermedias por un operador (una CA también bajo las políticas con ella como alcance); un cliente ACME no puede esperar una decisión, por lo que su revocación se rechaza' },
          { label: 'Varias a la vez', text: 'Una política puede regir varias operaciones; una sin ninguna (un antiguo tipo de renovación o de revocación, nunca aplicado) no rige nada hasta que se elija' },
        ]
      },
      {
        title: 'Reglas',
        items: [
          { label: 'Validez máxima', text: 'Duración máxima del certificado en días' },
          { label: 'Tipos de clave permitidos', text: 'Restringir qué algoritmos y tamaños de clave pueden usarse, incluidos ML-DSA-44, ML-DSA-65 y ML-DSA-87; el modo FIPS elimina ML-DSA cuando el módulo FIPS no lo aprueba' },
          { label: 'Esquemas de firma (solo API)', text: 'La regla allowed_signature_schemes, ausente del formulario de política: PKCS#1 v1.5, RSA-PSS, ECDSA, EdDSA, ML-DSA o SLH-DSA, contrastada con la clave de la CA firmante. Los hashes de firma permitidos no vinculan a una CA ML-DSA, que firma sin un resumen aparte' },
          { label: 'Restricciones de SAN', text: 'Limitar el número de nombres DNS (los demás tipos de SAN no se cuentan); un patrón DNS por política (*.company.com, o company.com para incluir el propio dominio) limita la política a los nombres coincidentes' },
          { label: 'Hashes de firma permitidos', text: 'SHA-256, SHA-384 o SHA-512; ninguno seleccionado permite cualquiera. Cuando nadie eligió el hash, se aplica el predeterminado si está permitido, y si no el más débil de los permitidos. El formulario de emisión solo ofrece los tipos de clave permitidos, Crear CA solo los tipos de clave y los hashes permitidos' },
        ]
      },
      {
        title: 'Flujos de aprobación',
        items: [
          { label: 'Grupos de aprobación', text: 'Asignar un grupo de usuarios responsable de aprobar las solicitudes' },
          { label: 'Aprobadores mínimos', text: 'Número de aprobaciones requeridas antes de la emisión' },
          { label: 'Notificaciones', text: 'Correo cuando la política rechaza una operación o retiene una para su aprobación; a las direcciones indicadas, y si no a sus aprobadores. Un rechazo repetido se notifica una vez por hora' },
        ]
      },
    ],
    tips: [
      'Un número de prioridad más bajo = mayor precedencia para la aprobación. Las reglas de todas las políticas dentro del alcance se aplican juntas, prevaleciendo la más estricta.',
      'Limitar las políticas a CA concretas para un control más fino.',
      'Activar las notificaciones para detectar pronto las infracciones de política.',
    ],
  },
  helpGuides: {
    title: 'Políticas de certificados',
    content: `
## Visión general

Las políticas de certificados definen las reglas y restricciones que se aplican cuando se emiten, renuevan o revocan certificados. Las políticas se evalúan por **orden de prioridad** (número más bajo = mayor precedencia) y pueden limitarse a CA concretas.

## La lista

Las políticas se enumeran por prioridad, el orden en que el servidor las aplica, y por nombre entre prioridades iguales, con su alcance, sus operaciones, su prioridad, su aprobación y su estado (**Aplicada** o **Deshabilitada**); los chips filtran por estado, y la búsqueda y el filtro de operaciones acotan la lista. Un nombre abre la política en el inspector, con sus propiedades, reglas y aprobación; **Editar política**, **Deshabilitar** o **Habilitar** requieren write:policies, **Eliminar política…** requiere delete:policies y una confirmación.

## Operaciones

Una política rige una o varias operaciones: su requisito de aprobación y sus reglas se aplican a ellas.

### Emisión
El formulario de emisión, la firma de CSR y la firma masiva, y las renovaciones que realiza un operador. Es la elección más habitual. Controla los tipos de clave, los períodos de validez, las restricciones de SAN y si se requiere aprobación.

### Renovación
Las renovaciones de un operador, una o en masa, y las del planificador. Bajo una política de renovación que exige aprobación, el planificador pone la renovación en cola en lugar de realizarla, y la aprobación vuelve a firmar la clave que el servidor custodia.

### Revocación
Las revocaciones de certificados (uno, en masa, desde los certificados de usuario) y de CA intermedias. Con alcance por la CA emisora, la plantilla y el patrón DNS; la revocación de una CA también la retienen las políticas con esa CA como alcance, ya que todos los certificados que emitió caen con ella. Las demás reglas no se aplican. Un cliente ACME no puede esperar una decisión: su revocación se rechaza y se deja a los operadores. Quitar una inscripción mTLS se rechaza hasta que su certificado esté revocado, sea quien sea su titular; los administradores saltan la regla.

Una política creada antes de que existieran las operaciones conserva lo que hacía: una política de emisión sigue siéndolo, y un tipo renovación o revocación, nunca aplicado, no rige nada hasta que se elijan sus operaciones.

## Configuración de reglas

### Validez máxima
Duración máxima del certificado en días. Valores habituales:
- **90 días**: automatización de corta duración (estilo ACME)
- **397 días**: referencia del CA/Browser Forum para TLS público
- **730 días**: PKI interna o privada
- **365 días**: firma de código

### Tipos de clave permitidos
Restringir qué algoritmos y tamaños de clave pueden usarse:
- **RSA-2048**: mínimo para la confianza pública
- **RSA-3072**: el tamaño de clave por defecto para las CA nuevas
- **RSA-4096**: mayor seguridad, certificados más grandes
- **EC-P256**: moderna, rápida, recomendada
- **EC-P384**: curva elíptica de mayor seguridad
- **EC-P521**: seguridad máxima (rara vez necesaria)
- **ML-DSA-44 / ML-DSA-65 / ML-DSA-87**: poscuánticos (FIPS 204), niveles NIST 2, 3 y 5; eliminados en modo FIPS cuando el módulo FIPS no los aprueba

La regla \`allowed_signature_schemes\`, que solo se define por la API (el formulario de política no la muestra), restringe cómo firma la CA firmante (PKCS#1 v1.5, RSA-PSS, ECDSA, EdDSA, ML-DSA, SLH-DSA). Los hashes de firma permitidos no vinculan a una CA ML-DSA, que firma sin un resumen aparte.

**Hashes de firma permitidos** restringe el hash de firma de la misma manera (SHA-256, SHA-384, SHA-512); ninguno seleccionado permite cualquiera. Cuando nadie eligió el hash, se aplica el predeterminado si está permitido, y si no el más débil de los permitidos. El formulario de emisión solo ofrece los tipos de clave permitidos, Crear CA solo los tipos de clave y los hashes permitidos.

### Restricciones de SAN
- **SANs máximos**: limita el número de nombres DNS en el SAN; las entradas IP, de correo y URI no se cuentan. En ACME, un nombre DNS que lleva solo el CN también cuenta (RFC 8555 §7.4)
- **Restricción de patrón DNS**: limita la política a las solicitudes cuyo CN o SAN DNS coinciden, etiqueta por etiqueta y sin distinguir mayúsculas: \`*.company.com\` cubre los nombres bajo company.com, \`company.com\` cubre también company.com. Los demás nombres no se rechazan: la política no se les aplica

## Flujos de aprobación

Cuando **Requerir aprobación antes de la emisión** está activado, la emisión del certificado queda en pausa hasta que el número requerido de aprobadores del grupo asignado haya aprobado la solicitud.

### Configuración
- **Grupo de aprobación**: seleccionar un grupo de usuarios responsable de las aprobaciones
- **Aprobadores mínimos**: número de aprobaciones requeridas (por ejemplo 2 de 3 miembros del grupo)
- **Notificaciones**: correo cuando la política rechaza una operación (una regla incumplida) o retiene una para su aprobación. Van a las direcciones de notificación de la política, y si no a sus aprobadores (los miembros de su grupo de aprobación, o todo usuario que pueda aprobar). Cada solicitud retenida se notifica una vez, con un enlace a ella; el mismo rechazo repetido, por un cliente ACME que reintenta por ejemplo, una vez por hora. Debe estar configurado SMTP

> 💡 Usar flujos de aprobación para certificados de alto valor, como la firma de código y los certificados comodín.

## Sistema de prioridades

Las políticas se evalúan por orden de prioridad. Los números más bajos tienen mayor precedencia:
- **1-10**: políticas de seguridad críticas (firma de código, comodín)
- **10-20**: cumplimiento estándar (TLS público, PKI interna)
- **20+**: valores por defecto permisivos

Cuando varias políticas coinciden con una solicitud de certificado, la de mayor prioridad (número más bajo) decide la aprobación; las reglas de todas las políticas coincidentes se aplican juntas (la menor validez máxima, la intersección de los tipos de clave permitidos, y así sucesivamente). Entre políticas coincidentes de la misma prioridad el servidor no sigue ningún orden fijo: darles prioridades distintas.

## Alcance

### Todas las CA
La política se aplica a todas las CA del sistema. Usarla para reglas de toda la organización.

### CA concreta
La política se aplica solo a los certificados emitidos por la CA seleccionada. Usarla para un control más fino.

## Políticas por defecto

Una instalación nueva no tiene ninguna política: crear las que la organización necesite. Una instalación actualizada desde una versión anterior puede enumerar cinco políticas de ejemplo (Code Signing, Wildcard Certificates, Web Server TLS, Short-Lived Automation, Internal PKI), todas deshabilitadas.
`
  },
}
