export default {
  helpContent: {
    title: 'SCEP',
    subtitle: 'Simple Certificate Enrollment Protocol',
    overview: 'SCEP permite que los dispositivos de red (routers, switches, firewalls) y las soluciones MDM soliciten y obtengan certificados automáticamente. Los dispositivos se autentican mediante una contraseña de desafío.',
    sections: [
      {
        title: 'Pestañas',
        items: [
          { label: 'Solicitudes', text: 'Solicitudes de inscripción SCEP pendientes, aprobadas y rechazadas' },
          { label: 'Configuración', text: 'Ajustes del servidor SCEP: selección de CA, identificador de CA, aprobación automática' },
          { label: 'Perfiles', text: 'Endpoints de inscripción con nombre, cada uno con su propia URL, CA, plantilla y desafío' },
          { label: 'Contraseñas de desafío', text: 'Gestionar contraseñas de desafío por CA para la inscripción de dispositivos' },
          { label: 'Información', text: 'URL del endpoint SCEP e instrucciones de integración' },
        ]
      },
      {
        title: 'Configuración',
        items: [
          { label: 'CA firmante', text: 'Seleccionar qué CA firma los certificados inscritos por SCEP' },
          { label: 'Aprobación automática', text: 'Aprobar automáticamente solicitudes con contraseñas de desafío válidas' },
          { label: 'Contraseña de desafío', text: 'Secreto compartido que los dispositivos usan para autenticar la inscripción' },
        ]
      },
      {
        title: 'Perfiles',
        items: [
          { label: 'Segmento de URL', text: 'Cada perfil se sirve en /scep/<segment>/pkiclient.exe — apunte cada flota de dispositivos o perfil MDM a su propia URL' },
          { label: 'Plantilla de certificado', text: 'Cuando se vincula una plantilla, sus KU/EKU y validez gobiernan cada certificado emitido por el perfil' },
          { label: 'Desafío por perfil', text: 'Cada perfil tiene su propia contraseña de desafío, almacenada cifrada, con la misma ventana de expiración que el desafío global' },
          { label: 'Endpoint por defecto', text: 'El endpoint /scep/pkiclient.exe sin segmento sigue sirviendo la configuración global' },
          { label: 'Validación de Microsoft Intune', text: 'Un perfil puede validarse contra el desafío SCEP propio de Intune por dispositivo en lugar de una contraseña estática — requiere un registro de aplicación en Entra (permisos SCEP challenge validation + Application.Read.All) y aprobación automática activada' },
        ]
      },
    ],
    tips: [
      'Use contraseñas de desafío únicas por CA para una mejor auditoría de seguridad',
      'La aprobación automática es conveniente, pero revise las solicitudes manualmente en entornos de alta seguridad',
      'Formato de URL SCEP: https://su-servidor:puerto/scep',
      'Los perfiles de Intune necesitan la aprobación automática activada — la inscripción en Intune es un ciclo síncrono de validación y emisión, sin cola de aprobación en su lado',
    ],
    warnings: [
      'Las contraseñas de desafío se transmiten en la solicitud SCEP — use HTTPS para la seguridad del transporte',
    ],
  },
  helpGuides: {
    title: 'Servidor SCEP',
    content: `
## Descripción general

El Simple Certificate Enrollment Protocol (SCEP) permite que los dispositivos de red — routers, switches, firewalls, endpoints gestionados por MDM — soliciten y obtengan certificados automáticamente.

## Pestañas

### Solicitudes
Ver todas las solicitudes de inscripción SCEP:
- **Pendientes** — En espera de aprobación manual (si la aprobación automática está desactivada)
- **Aprobadas** — Emitidas exitosamente
- **Rechazadas** — Denegadas por un administrador

### Configuración
Configurar el servidor SCEP:
- **Activar/Desactivar** — Alternar el servicio SCEP
- **CA firmante** — Seleccionar qué CA firma los certificados inscritos por SCEP
- **Identificador de CA** — El identificador que los dispositivos usan para localizar la CA correcta
- **Aprobación automática** — Aprobar automáticamente solicitudes con contraseñas de desafío válidas

### Perfiles
Endpoints de inscripción con nombre, cada uno servido en su propia URL:

\`\`\`
https://su-servidor:8443/scep/<profile>/pkiclient.exe
\`\`\`

Cada perfil está vinculado a:
- **Su propia CA** — distintas flotas de dispositivos pueden inscribirse contra CAs diferentes
- **Una plantilla de certificado opcional** — cuando está vinculada, el uso de clave, el uso extendido de clave y la validez de la plantilla gobiernan cada certificado emitido a través del perfil
- **Una contraseña de desafío por perfil** — almacenada cifrada, con la misma ventana de expiración que el desafío global
- **Una política de aprobación** — aprobación automática o revisión manual por perfil

Apunte cada flota de dispositivos, perfil MDM o tenant a su propia URL de perfil. El endpoint \`/scep/pkiclient.exe\` sin etiqueta sigue sirviendo la configuración global sin cambios.

### Contraseñas de desafío
Gestionar contraseñas de desafío por CA. Los dispositivos deben incluir una contraseña de desafío válida en su solicitud de inscripción para autenticarse.

- **Ver contraseña** — Mostrar el desafío actual para una CA
- **Regenerar** — Crear una nueva contraseña de desafío (invalida la anterior)

### Información
Muestra la URL del endpoint SCEP e instrucciones de integración.

## Flujo de inscripción SCEP

1. El dispositivo envía una solicitud **GetCACert** para obtener el certificado de la CA
2. El dispositivo genera un par de claves y crea un CSR
3. El dispositivo envuelve el CSR con la **contraseña de desafío** y envía un **PKCSReq**
4. UCM valida la contraseña de desafío
5. Si la aprobación automática está activada, UCM firma y devuelve el certificado
6. Si la aprobación automática está desactivada, un administrador revisa y aprueba/rechaza

## URL SCEP

\`\`\`
https://su-servidor:8443/scep                          (endpoint global)
https://su-servidor:8443/scep/<profile>/pkiclient.exe  (endpoint por perfil)
\`\`\`

Los dispositivos necesitan la URL más el identificador de CA para inscribirse. Use una URL de perfil para apuntar a la CA, la plantilla y la contraseña de desafío de ese perfil.

## Aprobar/Rechazar solicitudes

Para solicitudes pendientes (aprobación automática desactivada):
1. Revise los detalles de la solicitud (asunto, tipo de clave, desafío)
2. Haga clic en **Aprobar** para firmar y emitir el certificado
3. O haga clic en **Rechazar** con un motivo

> ⚠ Las contraseñas de desafío se transmiten en la solicitud SCEP. Siempre use HTTPS para el endpoint SCEP.

## Integración de dispositivos

### Cisco IOS
\`\`\`
crypto pki trustpoint UCM
  enrollment url https://su-servidor:8443/scep
  password <contraseña-de-desafío>
\`\`\`

### JAMF
Configure el perfil SCEP con:
- URL del servidor: \`https://su-servidor:8443/scep\`
- Desafío: la contraseña de UCM

### Microsoft Intune
Intune no admite una contraseña de desafío estática — emite su propio desafío cifrado por dispositivo que solo la API de Intune puede validar. En un **perfil** SCEP (no en el endpoint global), active **Validación de desafío SCEP de Microsoft Intune** y proporcione el ID de inquilino, el ID de cliente y el secreto de cliente de un registro de aplicación en Entra:

1. En Microsoft Entra ID, registre una aplicación y otórguele los permisos de aplicación **Intune API → SCEP challenge validation** (\`scep_challenge_provider\`) y **Microsoft Graph → Application.Read.All**, ambos con consentimiento de administrador
2. Introduzca el ID de inquilino, el ID de cliente y el secreto de cliente en el perfil, luego haga clic en **Probar conexión** para confirmar que UCM puede alcanzar Intune antes de guardar
3. En Intune, apunte la URL del servidor del perfil SCEP del dispositivo al endpoint \`/scep/<segment>/pkiclient.exe\` de este perfil

Los perfiles con Intune activado deben tener la **aprobación automática** activada — la inscripción de Intune es un ciclo síncrono de validación y emisión, sin cola de aprobación en el lado de Intune para una revisión manual.
`
  }
}
