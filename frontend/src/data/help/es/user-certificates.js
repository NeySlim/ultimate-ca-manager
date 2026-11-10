export default {
  helpContent: {
    title: 'Certificados de usuario',
    subtitle: 'Gestione los certificados de cliente mTLS',
    overview: 'Gestión dedicada de los certificados de cliente mTLS inscritos desde la página Cuenta. Vea, exporte, revoque y elimine los certificados emitidos a los usuarios para la autenticación TLS mutua.',
    sections: [
      {
        title: 'Estado del certificado',
        definitions: [
          { term: 'Válido', description: 'Dentro del período de validez y no revocado' },
          { term: 'Por expirar', description: 'Expirará dentro de 30 días' },
          { term: 'Expirado', description: 'Posterior a la fecha «Not After»' },
          { term: 'Revocado', description: 'Revocado explícitamente por un operador o administrador' },
        ]
      },
      {
        title: 'Acciones',
        items: [
          { label: 'Exportar', text: 'Descargue como PEM (con clave y cadena) o PKCS#12 (protegido con contraseña)' },
          { label: 'Revocar', text: 'Revoque con un motivo, el certificado aparecerá en la CRL' },
          { label: 'Eliminar', text: 'Elimine el certificado y su asociación con el usuario de UCM' },
        ]
      },
      {
        title: 'Permisos',
        items: [
          { label: 'Viewers', text: 'Solo pueden ver sus propios certificados' },
          { label: 'Operators', text: 'Pueden ver, exportar, revocar y eliminar todos los certificados de usuario; exportar la clave privada del certificado de otro usuario requiere read:private_keys, que el rol no tiene' },
          { label: 'Admins', text: 'Acceso completo, claves privadas incluidas' },
          { label: 'Auditors', text: 'Pueden ver y exportar certificados, sin su clave privada' },
        ]
      },
    ],
    tips: [
      'Inscriba nuevos certificados mTLS desde Cuenta → pestaña mTLS',
      'Los certificados se almacenan y gestionan en UCM como cualquier otro certificado',
      'Use la barra de estadísticas para filtrar rápidamente por estado',
      'Haga clic en una fila para ver los detalles completos del certificado en el inspector',
    ],
    warnings: [
      'Revocar un certificado de usuario impide de inmediato el inicio de sesión mTLS con ese certificado',
      'La eliminación borra el certificado de forma permanente, no se puede recuperar',
    ],
  },
  helpGuides: {
    title: 'Certificados de usuario',
    content: `
## Descripción general

La página Certificados de usuario gestiona los certificados de cliente mTLS inscritos desde la pestaña **Cuenta → mTLS**. A diferencia de los certificados normales, estos están vinculados específicamente a cuentas de usuario para la autenticación TLS mutua.

Los certificados de esta página están totalmente gestionados por UCM: se almacenan en la base de datos con sus claves privadas y pueden exportarse, revocarse o eliminarse en cualquier momento.

## Inscribir un certificado

1. Vaya a la pestaña **Cuenta → mTLS**
2. Haga clic en **Inscribir certificado**
3. El sistema genera un par de claves y emite un certificado de cliente firmado por su CA mTLS
4. El certificado aparece en esta página y puede usarse para el inicio de sesión mTLS

## Estado del certificado

- **Válido**: Dentro del período de validez y no revocado
- **Por expirar**: Expirará dentro de 30 días
- **Expirado**: Posterior a la fecha «Not After»
- **Revocado**: Revocado explícitamente, publicado en la CRL

## Exportar un certificado

1. Seleccione un certificado → **Exportar**
2. Elija el formato:
   - **PEM**: Certificado + clave privada + cadena de CA en formato texto
   - **PKCS#12**: Paquete binario, protegido con contraseña (mín. 8 caracteres)
3. Haga clic en **Descargar**

El archivo exportado puede importarse en navegadores, sistemas operativos o clientes API para la autenticación mTLS.

> ⚠ La contraseña del PKCS#12 debe tener al menos 8 caracteres.

## Revocar un certificado

1. Seleccione un certificado → **Revocar**
2. Elija un motivo de revocación:
   - Key Compromise
   - Affiliation Changed
   - Superseded
   - Cessation of Operation
   - Unspecified
3. Confirme la revocación

> ⚠ Revocar un certificado impide de inmediato el inicio de sesión mTLS con ese certificado. La revocación es permanente.

## Eliminar un certificado

Eliminar borra tanto el certificado como la asociación usuario-certificado. Solo los administradores y operadores pueden eliminar.

> ⚠ La eliminación es permanente y no se puede deshacer.

## Permisos

| Rol | Ver | Exportar | Revocar | Eliminar |
|------|------|--------|--------|--------|
| Admin | Todos | Todos | Todos | Todos |
| Operator | Todos | Todos (la clave privada de otro usuario requiere read:private_keys) | Todos | Todos |
| Auditor | Todos | Solo el certificado, sin clave privada | ✗ | ✗ |
| Viewer | Solo propios | Solo propios | ✗ | ✗ |

### Permisos requeridos

- **read:user_certificates**: Ver la lista y los detalles de los certificados
- **write:user_certificates**: Revocar certificados
- **delete:user_certificates**: Eliminar certificados

> 💡 Inscriba nuevos certificados mTLS desde la página Cuenta. Esta página sirve para gestionar los certificados existentes.
`
  }
}
