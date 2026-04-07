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
    ],
    tips: [
      'Use contraseñas de desafío únicas por CA para una mejor auditoría de seguridad',
      'La aprobación automática es conveniente, pero revise las solicitudes manualmente en entornos de alta seguridad',
      'Formato de URL SCEP: https://su-servidor:puerto/scep',
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
https://su-servidor:8443/scep
\`\`\`

Los dispositivos necesitan esta URL más el identificador de CA para inscribirse.

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

### Microsoft Intune / JAMF
Configure el perfil SCEP con:
- URL del servidor: \`https://su-servidor:8443/scep\`
- Desafío: la contraseña de UCM
`
  }
}
