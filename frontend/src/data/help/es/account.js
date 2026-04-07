export default {
  helpContent: {
    title: 'Mi cuenta',
    subtitle: 'Configuración personal y seguridad',
    overview: 'Gestiona tu perfil, configuración de seguridad y claves API. Activa la autenticación de dos factores y registra claves de seguridad para una protección mejorada de la cuenta.',
    sections: [
      {
        title: 'Perfil',
        items: [
          { label: 'Nombre completo', text: 'Tu nombre para mostrar en toda la aplicación' },
          { label: 'Email', text: 'Utilizado para notificaciones y recuperación de cuenta' },
          { label: 'Info de cuenta', text: 'Fecha de creación, último inicio de sesión, total de inicios de sesión' },
        ]
      },
      {
        title: 'Seguridad',
        items: [
          { label: 'Contraseña', text: 'Cambia tu contraseña actual' },
          { label: '2FA (TOTP)', text: 'Activa contraseñas de un solo uso basadas en tiempo mediante una app de autenticación' },
          { label: 'Claves de seguridad', text: 'Registra claves WebAuthn/FIDO2 (YubiKey, huella dactilar, etc.)' },
          { label: 'mTLS', text: 'Gestiona certificados de cliente para autenticación TLS mutua' },
        ]
      },
      {
        title: 'Claves API',
        items: [
          { label: 'Crear clave', text: 'Genera una nueva clave API con expiración opcional' },
          { label: 'Permisos', text: 'Las claves API heredan los permisos de tu rol' },
          { label: 'Revocar', text: 'Invalida inmediatamente una clave API' },
        ]
      },
    ],
    tips: [
      'Activa al menos un segundo factor (TOTP o clave de seguridad) para las cuentas de administrador',
      'Las claves API pueden tener una fecha de expiración para integraciones de corta duración',
      'Escanea el código QR con cualquier app TOTP: Google Authenticator, Authy, 1Password, etc.',
    ],
  },
  helpGuides: {
    title: 'Mi cuenta',
    content: `
## Descripción general

Gestiona tu perfil personal, configuración de seguridad y claves API.

## Perfil

- **Nombre completo** — Tu nombre para mostrar en UCM
- **Email** — Utilizado para notificaciones, recuperación de contraseña y registro ACME
- **Info de cuenta** — Fecha de creación, marca de tiempo del último inicio de sesión, total de inicios de sesión

## Seguridad

### Cambio de contraseña
Cambia tu contraseña actual. Debe cumplir con la política de contraseñas del sistema (longitud mínima, requisitos de complejidad).

### Autenticación de dos factores (TOTP)
Añade una contraseña de un solo uso basada en tiempo usando cualquier app de autenticación:

1. Haz clic en **Activar 2FA**
2. Escanea el código QR con tu app de autenticación (Google Authenticator, Authy, 1Password, etc.)
3. Introduce el código de 6 dígitos para confirmar
4. Guarda los **códigos de recuperación** — solo se muestran una vez

> ⚠ Si pierdes el acceso a tu autenticador y a los códigos de recuperación, un administrador deberá desactivar tu 2FA.

### Claves de seguridad (WebAuthn/FIDO2)
Registra claves de seguridad de hardware o autenticadores biométricos:
- YubiKey
- Lector de huellas dactilares
- Windows Hello
- Touch ID

1. Haz clic en **Registrar clave de seguridad**
2. Introduce un nombre para la clave
3. Sigue la solicitud del navegador para autenticarte
4. La clave aparece en tu lista de credenciales registradas

### Certificados mTLS
Gestiona certificados de cliente para autenticación TLS mutua:
- Sube un certificado de cliente
- Descarga tus certificados registrados
- Elimina certificados antiguos

## Claves API

### Crear una clave API
1. Haz clic en **Crear clave API**
2. Introduce un **nombre** (descriptivo, p. ej., "Pipeline CI/CD")
3. Opcionalmente establece una **fecha de expiración**
4. Haz clic en **Crear**
5. Copia la clave inmediatamente — solo se muestra una vez

### Uso de claves API
Incluye la clave en el encabezado \`X-API-Key\`:

\`\`\`
X-API-Key: <tu-clave-api>
\`\`\`

### Permisos
Las claves API heredan los permisos del rol de tu usuario. No pueden tener más acceso que tu cuenta.

### Revocar claves
Haz clic en **Eliminar** para invalidar inmediatamente una clave API. Las sesiones activas que usen la clave serán terminadas.

> 💡 Usa claves API de corta duración con fechas de expiración para CI/CD y automatización.
`
  }
}
