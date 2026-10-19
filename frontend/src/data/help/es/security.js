export default {
  helpContent: {
    title: 'Configuración de seguridad',
    subtitle: 'Políticas de autenticación y acceso',
    overview: 'Configure políticas de contraseñas, gestión de sesiones, limitación de velocidad y seguridad de red. Estas configuraciones se aplican a nivel de sistema y afectan a todas las cuentas de usuario.',
    sections: [
      {
        title: 'Cifrado de claves privadas',
        items: [
          { label: 'Estado y contadores', text: 'Muestra si el cifrado está activado y cuántas claves privadas almacenadas están cifradas frente a sin cifrar' },
          { label: 'Activar / Desactivar', text: 'Cifra todas las claves privadas con AES-256. Al activar elimina las copias de claves en texto plano y al desactivar las vuelve a crear' },
          { label: 'Archivos de clave en disco', text: 'Muestra cuántas copias de claves en texto plano quedan; use hooks de despliegue cuando otro servicio necesite un archivo de clave' },
          { label: 'UCM_REQUIRE_DB_ENCRYPTION_KEY', text: 'Variable de entorno opcional: rechaza arrancar sin una clave de cifrado de base de datos explícita' },
          { label: 'UCM_REQUIRE_KEY_ENCRYPTION', text: 'Variable de entorno opcional: rechaza arrancar si el cifrado de claves privadas no está activado' },
        ]
      },
      {
        title: 'Política de contraseñas',
        items: [
          { label: 'Longitud mínima', text: 'Número mínimo de caracteres requeridos' },
          { label: 'Complejidad', text: 'Requerir mayúsculas, minúsculas, números y caracteres especiales' },
          { label: 'Expiración', text: 'Forzar el cambio de contraseña después de un número determinado de días' },
          { label: 'Historial', text: 'Evitar la reutilización de contraseñas anteriores' },
        ]
      },
      {
        title: 'Sesión y acceso',
        items: [
          { label: 'Tiempo de sesión', text: 'Cierre de sesión automático tras un período de inactividad' },
          { label: 'Limitación de velocidad', text: 'Limitar intentos de inicio de sesión para prevenir ataques de fuerza bruta' },
          { label: 'Restricciones de IP', text: 'Permitir o denegar acceso desde rangos de IP específicos' },
          { label: 'Aplicación de 2FA', text: 'Requerir autenticación de dos factores para todos los usuarios' },
        ]
      },
      {
        title: 'Autenticación mTLS',
        items: [
          { label: 'CA de confianza', text: 'Seleccione la CA que emite y valida los certificados de cliente para el inicio de sesión mTLS' },
          { label: 'Requerir certificado de cliente', text: 'Opcionalmente, haga que mTLS sea obligatorio para la interfaz web, cambiar la configuración mTLS requiere un reinicio del servicio' },
        ]
      },
    ],
    tips: [
      'Active la limitación de velocidad para protegerse contra herramientas de ataque automatizadas',
      'Use restricciones de IP para limitar el acceso de administración a redes de confianza',
    ],
    warnings: [
      'Restringir demasiado la política de contraseñas puede frustrar a los usuarios',
      'Siempre asegúrese de que al menos un administrador pueda acceder al sistema antes de activar las restricciones de IP',
      'Las configuraciones sensibles de seguridad (sesión, bloqueo, HSTS, URL pública, política de contraseñas) requieren admin:settings, los campos están bloqueados para los operadores',
    ],
  },
  helpGuides: {
    title: 'Configuración de seguridad',
    content: `
## Descripción general

Configuración de seguridad a nivel de sistema que afecta a todas las cuentas de usuario y patrones de acceso.

## Cifrado de claves privadas

Cifre todas las claves privadas de CAs y certificados almacenadas en la base de datos con AES-256, protegidas por un archivo de clave maestra guardado fuera de la base de datos.

- **Estado y contadores**: La sección muestra si el cifrado está activado y cuántas claves están actualmente **cifradas** frente a **sin cifrar**
- **Activar cifrado**: Genera el archivo de clave maestra y cifra todas las claves privadas almacenadas. Haga una copia de seguridad del archivo de clave de inmediato: sin él, las claves cifradas se pierden de forma permanente
- **Desactivar cifrado**: Descifra todas las claves privadas y vuelve al almacenamiento en texto plano (requiere confirmación)

### Aplicación en el arranque

Sin una clave de cifrado configurada, UCM registra una advertencia en el arranque pero sigue funcionando. Dos **variables de entorno opcionales** lo convierten en un fallo fatal:

- \`UCM_REQUIRE_DB_ENCRYPTION_KEY\`: rechaza arrancar sin una clave de cifrado de base de datos explícita (de lo contrario, los secretos de integración recurren a una clave derivada del id de la máquina)
- \`UCM_REQUIRE_KEY_ENCRYPTION\`: rechaza arrancar si el cifrado de claves privadas no está activado

Ambas aceptan \`1\`/\`true\`/\`yes\`/\`on\`. Una clave inválida se trata como fatal en lugar de recurrir silenciosamente al texto plano.

## Política de contraseñas

### Requisitos de complejidad
- **Longitud mínima**: De 8 a 32 caracteres
- **Requerir mayúsculas**: Al menos una letra mayúscula
- **Requerir minúsculas**: Al menos una letra minúscula
- **Requerir números**: Al menos un dígito
- **Requerir caracteres especiales**: Al menos un símbolo

### Expiración de contraseñas
Forzar a los usuarios a cambiar su contraseña después de un número determinado de días. Establezca en 0 para desactivar.

### Historial de contraseñas
Evitar la reutilización de las últimas N contraseñas. Los usuarios no pueden establecer una contraseña que coincida con ninguna de sus N contraseñas anteriores.

## Gestión de sesiones

### Tiempo de sesión
Cerrar sesión automáticamente a los usuarios después de N minutos de inactividad. Se aplica solo a sesiones de la interfaz web, no a claves API.

### Sesiones simultáneas
Limitar el número de sesiones simultáneas por usuario. Los inicios de sesión adicionales cerrarán la sesión más antigua.

## Limitación de velocidad

### Intentos de inicio de sesión
Limitar los intentos de inicio de sesión fallidos por dirección IP dentro de una ventana de tiempo. Después de superar el límite, la IP se bloquea temporalmente.

### Duración del bloqueo
Tiempo durante el cual una IP permanece bloqueada después de superar el límite de intentos de inicio de sesión.

## Restricciones de IP

### Lista de permitidos
Solo permitir conexiones desde IP o rangos CIDR especificados. Todas las demás IP se bloquean.

### Lista de denegados
Bloquear IP o rangos CIDR específicos. Todas las demás IP se permiten.

> ⚠ Tenga mucho cuidado con las restricciones de IP. Una mala configuración puede bloquear a todos los usuarios, incluidos los administradores. Siempre pruebe primero con una sola IP.

## Autenticación de dos factores

### Aplicación
Requerir que todos los usuarios activen 2FA. Los usuarios que no hayan configurado 2FA recibirán un aviso en su próximo inicio de sesión. Una aplicación TOTP o una llave de seguridad registrada la satisface, tanto en el registro como al iniciar sesión. Mientras esté impuesta, TOTP solo puede desactivarse si queda una llave de seguridad, y la última llave solo puede eliminarse si queda TOTP. Un usuario cuya llave se convirtió en su segundo factor la conserva cuando se retira la imposición.

### Métodos soportados
- **TOTP**: Contraseñas de un solo uso basadas en tiempo (aplicaciones de autenticación)
- **WebAuthn**: Llaves de seguridad de hardware y biometría

> 💡 Aplique 2FA para las cuentas de administrador como mínimo. Considere aplicarla para todos los usuarios en entornos con alta exigencia de seguridad.

## Autenticación mTLS

Permita a los usuarios iniciar sesión con un certificado de cliente en lugar de una contraseña:

- **CA de confianza**: Seleccione la CA que emite y valida los certificados de cliente mTLS
- **Requerir certificado de cliente**: Opcionalmente, haga que mTLS sea obligatorio para la interfaz web
- Cambiar la configuración mTLS requiere un reinicio del servicio

## Permisos requeridos

Las configuraciones sensibles de seguridad: sesión, bloqueo, HSTS, URL pública y política de contraseñas, requieren el permiso **admin:settings**. Para los operadores (solo write:settings), esos campos se muestran bloqueados; el resto de la tarjeta se guarda con normalidad.
`
  }
}
