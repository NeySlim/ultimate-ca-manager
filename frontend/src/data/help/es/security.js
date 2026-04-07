export default {
  helpContent: {
    title: 'Configuración de seguridad',
    subtitle: 'Políticas de autenticación y acceso',
    overview: 'Configure políticas de contraseñas, gestión de sesiones, limitación de velocidad y seguridad de red. Estas configuraciones se aplican a nivel de sistema y afectan a todas las cuentas de usuario.',
    sections: [
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
    ],
    tips: [
      'Active la limitación de velocidad para protegerse contra herramientas de ataque automatizadas',
      'Use restricciones de IP para limitar el acceso de administración a redes de confianza',
    ],
    warnings: [
      'Restringir demasiado la política de contraseñas puede frustrar a los usuarios',
      'Siempre asegúrese de que al menos un administrador pueda acceder al sistema antes de activar las restricciones de IP',
    ],
  },
  helpGuides: {
    title: 'Configuración de seguridad',
    content: `
## Descripción general

Configuración de seguridad a nivel de sistema que afecta a todas las cuentas de usuario y patrones de acceso.

## Política de contraseñas

### Requisitos de complejidad
- **Longitud mínima** — De 8 a 32 caracteres
- **Requerir mayúsculas** — Al menos una letra mayúscula
- **Requerir minúsculas** — Al menos una letra minúscula
- **Requerir números** — Al menos un dígito
- **Requerir caracteres especiales** — Al menos un símbolo

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
Requerir que todos los usuarios activen 2FA. Los usuarios que no hayan configurado 2FA recibirán un aviso en su próximo inicio de sesión.

### Métodos soportados
- **TOTP** — Contraseñas de un solo uso basadas en tiempo (aplicaciones de autenticación)
- **WebAuthn** — Llaves de seguridad de hardware y biometría

> 💡 Aplique 2FA para las cuentas de administrador como mínimo. Considere aplicarla para todos los usuarios en entornos con alta exigencia de seguridad.
`
  }
}
