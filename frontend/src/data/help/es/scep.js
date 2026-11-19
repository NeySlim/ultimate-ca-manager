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
          { label: 'Configuración', text: 'Ajustes del servidor SCEP: selección de CA, aprobación automática' },
          { label: 'Perfiles', text: 'Endpoints de inscripción con nombre, cada uno con su propia URL, CA, plantilla y desafío' },
          { label: 'Registros de aplicación de Intune', text: 'Registros de aplicación en Entra (ID de inquilino, ID de cliente, secreto de cliente) compartidos por los perfiles que validan desafíos de Intune; un secreto vacío al editar conserva el actual, Probar conexión solicita un token y descubre el servicio sin consumir ningún desafío, y una app aún usada por un perfil no puede eliminarse' },
          { label: 'Desafíos', text: 'Ver y regenerar las contraseñas de desafío para la inscripción de dispositivos' },
          { label: 'Información', text: 'URL del endpoint SCEP e instrucciones de integración' },
        ]
      },
      {
        title: 'Configuración',
        items: [
          { label: 'CA firmante', text: 'Seleccionar qué CA firma los certificados inscritos por SCEP. Los dispositivos cifran su solicitud para esta CA, por lo que debe tener una clave RSA en software: las CA EC, con HSM, sin clave, sin conexión y revocadas no aparecen en la lista (v2.248)' },
          { label: 'Aprobación automática', text: 'Aprobar automáticamente solicitudes con contraseñas de desafío válidas, o renovaciones firmadas por un certificado que emitió el mismo endpoint' },
          { label: 'Servir en HTTP plano', text: 'Desactivado por defecto. Responde también a SCEP en el puerto del protocolo HTTP (8080 por defecto), en http://su-servidor:8080/scep/pkiclient.exe y las URL de perfil, para clientes como sscep que no pueden usar HTTPS. RFC 8894 §7.10: los mensajes SCEP ya están protegidos, el sobre CMS mantiene privada la contraseña de desafío' },
          { label: 'Contraseña de desafío', text: 'Secreto compartido que los dispositivos usan para autenticar la inscripción. Una renovación (RenewalReq) firmada por un certificado que emitió el mismo endpoint (perfil o global) se autentica con ese certificado, por lo que su desafío no se comprueba y rotar el secreto no impide renovar a los dispositivos inscritos (RFC 8894 §2.4). Cualquier otro certificado sigue necesitando el desafío del endpoint' },
          { label: 'Claves del dispositivo (v2.248)', text: 'Un dispositivo firma su solicitud con una clave RSA, ECDSA, Ed25519 o ML-DSA; una firma ML-DSA sigue la RFC 9882 (resumen SHA-512). Ed448 se rechaza, y ML-DSA también en modo FIPS' },
        ]
      },
      {
        title: 'Perfiles',
        items: [
          { label: 'Segmento de URL', text: 'Cada perfil se sirve en /scep/<segment>/pkiclient.exe, apunte cada flota de dispositivos o perfil MDM a su propia URL' },
          { label: 'Plantilla de certificado', text: 'Cuando se vincula una plantilla, sus KU/EKU y validez gobiernan cada certificado emitido por el perfil' },
          { label: 'Resumen de firma (v2.251)', text: 'Los certificados emitidos mediante un perfil se firman con el resumen de su plantilla, elevado al que corresponde a la clave de la CA, como preferencia que las políticas pueden anular. Sin plantilla, se aplica el resumen de la clave de la CA' },
          { label: 'Desafío por perfil', text: 'Cada perfil tiene su propia contraseña de desafío, almacenada cifrada, con la misma ventana de expiración que el desafío global' },
          { label: 'Endpoint por defecto', text: 'El endpoint /scep/pkiclient.exe sin segmento sigue sirviendo la configuración global' },
          { label: 'Validación de Microsoft Intune', text: 'Un perfil puede validarse contra el desafío SCEP propio de Intune por dispositivo en lugar de una contraseña estática: elija un registro de aplicación en la pestaña Registros de aplicación de Intune (permisos SCEP challenge validation + Application.Read.All), la aprobación automática sigue siendo obligatoria; al actualizar, cada perfil existente obtiene una app con su nombre, deduplicada por inquilino y cliente' },
          { label: 'Aprobación manual', text: 'Una solicitud que llegó a través de un perfil se aprueba con la plantilla de ese perfil (validez, usos de clave), exactamente como la emitiría la aprobación automática' },
          { label: 'Propósitos que ningún inscrito puede tener', text: 'Una plantilla vinculada a un perfil no puede llevar firma OCSP, sellado de tiempo, cualquier uso ni Smartcard Logon, y una renovación SCEP nunca los traslada; Smartcard Logon se permite cuando el perfil valida contra Intune, que avala la identidad' },
        ]
      },
    ],
    tips: [
      'Use contraseñas de desafío únicas por CA para una mejor auditoría de seguridad',
      'La aprobación automática es conveniente, pero revise las solicitudes manualmente en entornos de alta seguridad',
      'Formato de URL SCEP: https://su-servidor:puerto/scep',
      'Los perfiles de Intune necesitan la aprobación automática activada: la inscripción en Intune es un ciclo síncrono de validación y emisión, sin cola de aprobación en su lado',
    ],
    warnings: [
      'Las contraseñas de desafío se transmiten en la solicitud SCEP: use HTTPS para la seguridad del transporte',
    ],
  },
  helpGuides: {
    title: 'Servidor SCEP',
    content: `
## Descripción general

El Simple Certificate Enrollment Protocol (SCEP) permite que los dispositivos de red: routers, switches, firewalls, endpoints gestionados por MDM, soliciten y obtengan certificados automáticamente.

## Pestañas

### Solicitudes
Ver todas las solicitudes de inscripción SCEP:
- **Pendientes**: En espera de aprobación manual (si la aprobación automática está desactivada)
- **Aprobadas**: Emitidas exitosamente
- **Rechazadas**: Denegadas por un administrador

### Configuración
Configurar el servidor SCEP:
- **Activar/Desactivar**: Alternar el servicio SCEP
- **CA firmante**: Seleccionar qué CA firma los certificados inscritos por SCEP. Los dispositivos cifran su solicitud para esta CA, por lo que debe tener una clave RSA en software: las CA EC, con HSM, sin clave, sin conexión y revocadas no aparecen en la lista (v2.248)
- **Aprobación automática**: Aprobar automáticamente solicitudes con contraseñas de desafío válidas, o renovaciones firmadas por un certificado que emitió el mismo endpoint
- **Servir en HTTP plano**: desactivado por defecto. Responde también a SCEP en el puerto del protocolo HTTP (8080 por defecto) para clientes que no pueden usar HTTPS, como sscep. RFC 8894 §7.10: los mensajes SCEP ya están protegidos, por lo que TLS no es obligatorio; el sobre CMS mantiene privada la contraseña de desafío

### Perfiles
Endpoints de inscripción con nombre, cada uno servido en su propia URL:

\`\`\`
https://su-servidor:8443/scep/<profile>/pkiclient.exe
\`\`\`

Cada perfil está vinculado a:
- **Su propia CA**: distintas flotas de dispositivos pueden inscribirse contra CAs diferentes
- **Una plantilla de certificado opcional**: cuando está vinculada, el uso de clave, el uso extendido de clave y la validez de la plantilla gobiernan cada certificado emitido a través del perfil
- **Propósitos que ningún inscrito puede tener**: una plantilla vinculada a un perfil no puede llevar firma OCSP, sellado de tiempo, cualquier uso ni Smartcard Logon, y una renovación SCEP nunca los traslada; Smartcard Logon se permite cuando el perfil valida contra Intune, que avala la identidad
- **Una contraseña de desafío por perfil**: almacenada cifrada, con la misma ventana de expiración que el desafío global
- **Una política de aprobación**: aprobación automática o revisión manual por perfil

Apunte cada flota de dispositivos, perfil MDM o tenant a su propia URL de perfil. El endpoint \`/scep/pkiclient.exe\` sin etiqueta sigue sirviendo la configuración global sin cambios.

### Contraseñas de desafío
La pestaña **Desafíos** muestra las contraseñas de desafío. Los dispositivos deben incluir una contraseña de desafío válida en su solicitud de inscripción para autenticarse.

- **Ver contraseña**: Mostrar el desafío actual para una CA
- **Regenerar**: Crear una nueva contraseña de desafío (invalida la anterior)

### Información
Muestra la URL del endpoint SCEP e instrucciones de integración.

## Flujo de inscripción SCEP

1. El dispositivo envía una solicitud **GetCACert** para obtener el certificado de la CA
2. El dispositivo genera un par de claves y crea un CSR
3. El dispositivo envuelve el CSR con la **contraseña de desafío** y envía un **PKCSReq**
4. UCM valida la contraseña de desafío
5. Si la aprobación automática está activada, UCM firma y devuelve el certificado
6. Si la aprobación automática está desactivada, un administrador revisa y aprueba/rechaza

### Claves del dispositivo
El dispositivo firma su PKCSReq con su propia clave: RSA, ECDSA, Ed25519 o ML-DSA. Una firma ML-DSA se comprueba según la RFC 9882 (resumen SHA-512, el identificador de algoritmo propio de la clave, sin parámetros). Las firmas Ed448 se rechazan, y las ML-DSA también en modo FIPS. La solicitud sigue cifrándose para la CA firmante RSA.

## URL SCEP

\`\`\`
https://su-servidor:8443/scep/pkiclient.exe            (CA configurada)
https://su-servidor:8443/scep/<profile>/pkiclient.exe  (endpoint por perfil)
https://su-servidor:8443/cgi-bin/pkiclient.exe         (CA configurada, ruta heredada)
http://su-servidor:8080/scep/pkiclient.exe             (con Servir en HTTP plano)
\`\`\`

Los dispositivos necesitan la URL para inscribirse; \`/scep\` solo es la interfaz web, no un endpoint SCEP. Use una URL de perfil para apuntar a la CA, la plantilla y la contraseña de desafío de ese perfil.

### Rotación de CA (GetNextCACert)
GetNextCACert sirve el sucesor de la CA del endpoint, firmado por la CA actual: otra CA con el mismo padre y el mismo DN de sujeto, no revocada, no sin conexión, con una clave RSA en software y que expire más tarde. Una CA que solo comparte el nombre para mostrar nunca se sirve; sin sucesor la respuesta es 404.

## Aprobar/Rechazar solicitudes

Para solicitudes pendientes (aprobación automática desactivada):
1. Revise los detalles de la solicitud (asunto, ID de transacción, estado, CSR)
2. Haga clic en **Aprobar** para firmar y emitir el certificado
3. O haga clic en **Rechazar** con un motivo

Una solicitud que llegó a través de un perfil se emite con la plantilla de ese perfil (validez, usos de clave), exactamente como lo haría la aprobación automática.

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
Intune no admite una contraseña de desafío estática: emite su propio desafío cifrado por dispositivo que solo la API de Intune puede validar. En un **perfil** SCEP (no en el endpoint global), active **Validación de desafío SCEP de Microsoft Intune** y proporcione el ID de inquilino, el ID de cliente y el secreto de cliente de un registro de aplicación en Entra:

1. En Microsoft Entra ID, registre una aplicación y otórguele los permisos de aplicación **Intune API → SCEP challenge validation** (\`scep_challenge_provider\`) y **Microsoft Graph → Application.Read.All**, ambos con consentimiento de administrador
2. En **Registros de aplicación de Intune**, añada el registro de aplicación una sola vez (nombre, ID de inquilino, ID de cliente, secreto de cliente) y haga clic en **Probar conexión** para confirmar que UCM puede alcanzar Intune; luego elíjalo en el selector **Registro de aplicación** del perfil. Los perfiles del mismo inquilino lo comparten, así que el secreto se rota en un solo lugar
3. En Intune, apunte la URL del servidor del perfil SCEP del dispositivo al endpoint \`/scep/<segment>/pkiclient.exe\` de este perfil

Los perfiles con Intune activado deben tener la **aprobación automática** activada: la inscripción de Intune es un ciclo síncrono de validación y emisión, sin cola de aprobación en el lado de Intune para una revisión manual.
`
  }
}
