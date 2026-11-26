export default {
  helpContent: {
    title: 'Mi cuenta',
    subtitle: 'Configuración personal y seguridad',
    overview: 'Gestionar el perfil, la configuración de seguridad y las claves API. Activar la autenticación de dos factores y registrar llaves de seguridad para proteger mejor la cuenta.',
    sections: [
      {
        title: 'Organización de la página',
        content: 'El perfil, la seguridad y las claves API están en una sola página, cada uno en su marco; el índice de la izquierda lleva a ellos (en un teléfono, la lista Ir a la sección).',
        items: [
          { label: 'Acciones propias', text: 'El nombre y el correo se editan en su sitio: el estado de guardado, en la cabecera de la página, encima del formulario (al pie de la página en un teléfono), indica lo que se ha cambiado y no se ha guardado, Deshacer los cambios restablece los valores guardados y Guardar los envía (Intro en un campo también); Crear Clave abre el formulario de claves' },
          { label: 'Enlaces', text: 'Un enlace a /account?tab=security o /account?tab=api-keys abre la página en ese marco' },
          { label: 'Edición conservada', text: 'Un cambio de perfil aún no guardado se marca como Modificado en el índice, se conserva en esta pestaña al salir de la página y reaparece al volver; Deshacer los cambios lo olvida' },
          { label: 'Preferencias', text: 'Cerrar el inspector al navegar: los objetos abiertos en el inspector se cierran al ir a otra página. Desactivado por defecto: permanecen abiertos, igual que sus pestañas. La elección se conserva en este navegador' },
        ],
      },
      {
        title: 'Perfil',
        items: [
          { label: 'Nombre completo', text: 'El nombre que se muestra en toda la aplicación' },
          { label: 'Correo electrónico', text: 'Se usa para las notificaciones y la recuperación de la cuenta. Cambiarlo pide la contraseña, y se envía un aviso a la dirección anterior' },
          { label: 'Información de la cuenta', text: 'Fecha de creación, último inicio de sesión, número total de inicios de sesión' },
        ]
      },
      {
        title: 'Seguridad',
        items: [
          { label: 'Contraseña', text: 'Cambiar la contraseña actual. Las demás sesiones se cierran; esta se mantiene' },
          { label: '2FA (TOTP)', text: 'Activar contraseñas de un solo uso basadas en el tiempo mediante una aplicación de autenticación. Volver a activarlo mientras está activado se rechaza: desactivarlo primero. Cada código funciona una sola vez: tras usar uno, esperar al siguiente para confirmar otra acción' },
          { label: 'Claves de seguridad', text: 'Registrar llaves WebAuthn/FIDO2 (YubiKey, huella digital, etc.). Añadir una pide primero la contraseña, o el código de autenticación para una cuenta sin contraseña' },
          { label: 'mTLS', text: 'Gestionar los certificados de cliente para la autenticación TLS mutua. Añadir uno pide primero la contraseña, o el código de autenticación para una cuenta sin contraseña' },
          { label: 'Cambio de contraseña forzado (v2.245)', text: 'Una cuenta a la que se pidió una contraseña nueva, como el primer administrador cuya contraseña generó UCM en el primer arranque, no puede hacer nada más hasta cambiarla, API y WebSocket incluidos; el aviso no puede omitirse y su único otro botón es Cerrar sesión. Ese cambio elimina el archivo que contiene la contraseña generada. Una contraseña proporcionada mediante INITIAL_ADMIN_PASSWORD o INITIAL_ADMIN_PASSWORD_FILE no tiene que cambiarse, salvo que se defina INITIAL_ADMIN_PASSWORD_FORCE_CHANGE (el chart de Helm lo define para la contraseña que genera)' },
        ]
      },
      {
        title: 'Claves API',
        items: [
          { label: 'Crear clave', text: 'Generar una clave API nueva, con caducidad opcional tras un número de días' },
          { label: 'Permisos', text: 'Una clave lleva el alcance elegido al crearla, nunca más que los permisos propios. Una clave solo puede crear o regenerar una clave cuyos permisos posea ella misma, y que caduque como muy tarde cuando ella. Regenerar, que solo ofrece la API, conserva la duración de la clave; una clave revocada o caducada no puede regenerarse' },
          { label: 'Revocar', text: 'Invalidar de inmediato una clave API' },
          { label: 'Gestión de instancia', text: 'Ajuste para una consola que supervisa varias instancias: lee el estado de la instancia y los ajustes, inicia una copia de seguridad o una actualización, nada más. Solo para administradores' },
          { label: 'Direcciones de origen permitidas', text: 'Direcciones IP o redes CIDR desde las que puede usarse la clave; desde cualquier otra dirección la clave se rechaza (403) y su último uso no se actualiza. Una clave creada o regenerada por una clave limitada queda dentro de sus redes. Vacío: cualquier dirección' },
          { label: 'Usuarios desactivados', text: 'Las claves API de un usuario desactivado se rechazan aunque la propia clave siga siendo válida' },
          { label: 'Solo sesión interactiva', text: 'Las claves API, incluso las de Acceso completo, no pueden cambiar el perfil, la contraseña, el 2FA, las llaves de seguridad, los certificados mTLS ni las sesiones, ni alcanzar la propia cuenta mediante las acciones de administración de usuarios: iniciar sesión de forma interactiva' },
        ]
      },
      {
        title: 'Preferencias (sincronizadas en el servidor)',
        content: 'El idioma, la familia de tema y el modo de tema se guardan en la base de datos y siguen a la cuenta entre navegadores y dispositivos:',
        items: [
          { label: 'Almacenamiento', text: 'En users.preferences (JSON). Los endpoints nuevos GET/PUT /api/v2/account/preferences las gestionan' },
          { label: 'Aplicación automática', text: '/api/v2/auth/verify devuelve las preferencias y se aplican en cada carga de página' },
          { label: 'Navegador nuevo', text: 'Iniciar sesión desde un dispositivo nuevo, o tras borrar los datos del sitio, restablece el idioma y el tema elegidos, sin recurrir a la configuración regional del navegador' },
        ]
      },
    ],
    tips: [
      'Activar al menos un segundo factor (TOTP o llave de seguridad) en las cuentas de administrador',
      'Las claves API pueden caducar tras un número de días fijado, para integraciones de corta duración',
      'Las claves API también pueden crearse sin caducidad para automatizaciones de larga duración',
      'Escanear el código QR con cualquier aplicación TOTP: Google Authenticator, Authy, 1Password, etc.',
      'Las selecciones de filtro en las páginas de lista principales (Certificados, CA, Plantillas, Auditoría, Políticas, Almacén de confianza y otras) se conservan entre recargas; CSR, Aprobaciones, Recuperación de claves, Descubrimiento y Registros del sistema empiezan sin filtrar',
    ],
  },
  helpGuides: {
    title: 'Mi cuenta',
    content: `
## Visión general

Gestionar el perfil personal, la configuración de seguridad y las claves API.

## Perfil

- **Nombre completo**: el nombre que se muestra en todo UCM
- **Correo electrónico**: se usa para las notificaciones y la recuperación de la contraseña. Cambiarlo pide la contraseña, y se envía un aviso a la dirección anterior
- **Información de la cuenta**: fecha de creación, marca de tiempo del último inicio de sesión, número total de inicios de sesión

## Seguridad

### Cambio de contraseña
Cambiar la contraseña actual. Debe cumplir la política de contraseñas del sistema (longitud mínima, requisitos de complejidad). Las demás sesiones se cierran; la desde la que se cambió se mantiene. Un restablecimiento de contraseña o de 2FA por un administrador cierra todas las sesiones del usuario.

Cuando UCM pide una contraseña nueva al iniciar sesión (la cuenta \`admin\` del primer arranque cuando UCM generó su contraseña, por ejemplo), el cambio va antes que cualquier otra cosa: hasta que se realiza, el servidor rechaza cualquier otra solicitud de esa sesión, API incluida.

### Autenticación de dos factores (TOTP)
Añadir una contraseña de un solo uso basada en el tiempo con cualquier aplicación de autenticación:

1. Hacer clic en **Habilitar la autenticación de dos factores**
2. Escanear el código QR con la aplicación de autenticación (Google Authenticator, Authy, 1Password, etc.)
3. Introducir el código de 6 dígitos para confirmar
4. Guardar los **códigos de respaldo**: se muestran una sola vez

> ⚠ Si se pierde el acceso al autenticador y a los códigos de respaldo, un administrador debe desactivar el 2FA.

Para pasar el 2FA a un autenticador nuevo, desactivarlo primero: volver a activarlo mientras está activado se rechaza.

Cada código se acepta una sola vez (RFC 6238): un código usado para iniciar sesión no puede confirmar otra acción ni un segundo inicio de sesión, por lo que hay que esperar al siguiente.

### Llaves de seguridad (WebAuthn/FIDO2)
Registrar llaves de seguridad de hardware o autenticadores biométricos:
- YubiKey
- Lector de huellas digitales
- Windows Hello
- Touch ID

1. Hacer clic en **Agregar Clave**
2. Introducir un nombre para la llave
3. Seguir el aviso del navegador para autenticarse
4. La llave aparece en la lista de credenciales registradas

UCM pide primero la contraseña, o el código de la aplicación de autenticación para una cuenta sin contraseña local: una llave inicia sesión por sí sola, así que una sesión desatendida no puede añadir una. Añadir un certificado mTLS pide lo mismo.

Con el 2FA activado o impuesto, una llave registrada también puede responder al segundo paso de un inicio de sesión con contraseña: elegir **Usar la llave de seguridad en su lugar**.

Sin una aplicación de autenticación, activar **Llave de seguridad como segundo factor** en la sección Autenticación de dos factores: cada inicio de sesión con contraseña pide entonces una de las llaves, y la última llave no puede quitarse mientras esté activado.

### Certificados mTLS
Gestionar los certificados de cliente para la autenticación TLS mutua:
- Subir un certificado de cliente
- Descargar los certificados registrados
- Eliminar los certificados antiguos

## Claves API

### Crear una clave API
1. Hacer clic en **Crear Clave**
2. Introducir un **nombre** (descriptivo, por ejemplo "Pipeline CI/CD")
3. Opcionalmente, fijar una caducidad en **días**
4. Hacer clic en **Crear** y confirmar con la contraseña (o con el código de autenticación en una cuenta sin contraseña): una clave sigue funcionando tras un cambio de contraseña
5. Copiar la clave de inmediato: se muestra una sola vez

### Usar las claves API
Incluir la clave en la cabecera \`X-API-Key\`:

\`\`\`
X-API-Key: <your-api-key>
\`\`\`

O enviarla como token bearer: \`Authorization: Bearer <your-api-key>\`.

### Permisos
Cada clave lleva el alcance elegido al crearla (**Acceso completo**, **Solo lectura**, **Lectura y escritura**, **Solo certificados**) y nunca más acceso que la cuenta. **Solo certificados** emite certificados X.509 y SSH y lee las CA, las CA SSH y las CRL, pero no puede crear ni modificar una CA. Una clave solo puede crear o regenerar una clave cuyos permisos posea ella misma, y esa clave caduca como muy tarde cuando la que lo pide. Regenerar una clave, que solo ofrece la API (\`POST /api/v2/account/apikeys/<id>/regenerate\`), conserva sus permisos y su duración; una clave revocada o caducada no puede regenerarse.

Las claves API, incluso las de Acceso completo, no pueden cambiar el perfil, la contraseña, el 2FA, las llaves de seguridad, los certificados mTLS ni las sesiones, ni alcanzar la propia cuenta mediante las acciones de administración de usuarios: estas requieren una sesión interactiva.

### Gestión de instancia y direcciones de origen
El ajuste **Gestión de instancia**, ofrecido a los administradores, da a una clave lo que necesita una consola que supervisa varias instancias: \`read:instance\` (\`GET /api/v2/system/instance\`), \`read:settings\`, \`write:backups\` y \`write:updates\`, sin \`admin:system\`. **Direcciones de origen permitidas** limita una clave a direcciones IP o redes CIDR: desde cualquier otra dirección se rechaza (403). Una clave creada o regenerada por una clave limitada queda dentro de sus redes, y regenerarla las conserva.

### Revocar claves
**Revocar** en una clave en uso la revoca de inmediato: las solicitudes con ella se rechazan desde ese momento. Una clave revocada o caducada ofrece **Eliminar**, que la borra. La tabla muestra primero las claves en uso y después las caducadas y revocadas; se busca por nombre o prefijo, se ordena por cualquier columna y se pagina a partir de diez claves.

> 💡 Usar claves API de corta duración para CI/CD y automatización.
`
  },
}
