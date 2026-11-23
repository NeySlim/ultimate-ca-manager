export default {
  helpContent: {
    title: 'Certificados de usuario',
    subtitle: 'Gestione los certificados de cliente mTLS',
    overview: 'Gestión dedicada de los certificados de cliente mTLS inscritos desde la página Mi cuenta. Vea, exporte, revoque y elimine los certificados emitidos a los usuarios para la autenticación TLS mutua.',
    sections: [
      {
        title: 'Estado del certificado',
        definitions: [
          { term: 'Válido', description: 'Dentro del período de validez y no revocado' },
          { term: 'Por caducar', description: 'Caducará dentro de 30 días' },
          { term: 'Caducado', description: 'Posterior a la fecha «Not After»' },
          { term: 'Revocado', description: 'Revocado explícitamente por un operador o administrador' },
        ]
      },
      {
        title: 'Acciones',
        items: [
          { label: 'Exportar', text: 'En el detalle del certificado: PEM, DER, PKCS#7, PKCS#12 o JKS, con la clave privada solo si está marcada y permitida' },
          { label: 'Revocar', text: 'En el menú ⋯ del detalle: revocar con un motivo, el certificado aparecerá en la CRL' },
          { label: 'Eliminar', text: 'En el menú ⋯ del detalle: quitar de UCM el certificado y su asociación con el usuario' },
          { label: 'Exportar la lista', text: 'Todos los certificados que conservan la búsqueda y el filtro de estado, en CSV o JSON (10 000 como máximo)' },
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
      'Inscriba nuevos certificados mTLS desde Mi cuenta → Seguridad',
      'Los certificados se almacenan y gestionan en UCM como cualquier otro certificado',
      'Los indicadores de estado sobre la lista cuentan y filtran los certificados Válidos, Por caducar, Caducados y Revocados',
      'Haga clic en un nombre para abrir su detalle bajo la lista; Inspeccionar el certificado abre el propio certificado en la página Certificados',
    ],
    warnings: [
      'Revocar un certificado de usuario impide de inmediato el inicio de sesión mTLS con ese certificado',
      'La eliminación borra el certificado de forma permanente: no se puede recuperar',
    ],
  },
  helpGuides: {
    title: 'Certificados de usuario',
    content: `
## Descripción general

La página Certificados de usuario gestiona los certificados de cliente mTLS inscritos desde **Mi cuenta → Seguridad**, sección **Client Certificados (mTLS)**. A diferencia de los certificados normales, estos están vinculados específicamente a cuentas de usuario para la autenticación TLS mutua.

Los certificados de esta página están totalmente gestionados por UCM: se almacenan en la base de datos con sus claves privadas y pueden exportarse, revocarse o eliminarse en cualquier momento.

## Inscribir un certificado

1. Vaya a **Mi cuenta → Seguridad**, sección **Client Certificados (mTLS)**
2. Haga clic en **Agregar Certificado**, deje **Generar** y haga clic en **Generar certificado**
3. El sistema genera un par de claves y emite un certificado de cliente firmado por su CA mTLS
4. El certificado aparece en esta página y puede usarse para el inicio de sesión mTLS

## Estado del certificado

- **Válido**: Dentro del período de validez y no revocado
- **Por caducar**: Caducará dentro de 30 días
- **Caducado**: Posterior a la fecha «Not After»
- **Revocado**: Revocado explícitamente, publicado en la CRL

## Exportar un certificado

1. Haga clic en el nombre del certificado: su detalle se abre bajo la lista
2. Haga clic en **Exportar** y elija el formato:
   - **PEM**: Certificado, con la cadena de CA y la clave privada si está marcada, en formato texto
   - **PKCS#12**: Paquete binario, protegido con contraseña (mín. 8 caracteres)
3. Haga clic en **Descargar**

**Exportar la lista**, en el encabezado de la página, guarda todos los certificados que conservan la búsqueda y el filtro de estado, en CSV o JSON.

El archivo exportado puede importarse en navegadores, sistemas operativos o clientes API para la autenticación mTLS.

> ⚠ La contraseña del PKCS#12 debe tener al menos 8 caracteres.

## Revocar un certificado

1. Abra el certificado y, en su menú **⋯**, elija **Revocar**
2. Elija un motivo de revocación:
   - Key Compromise
   - Affiliation Changed
   - Superseded
   - Cessation of Operation
   - Unspecified
3. Confirme la revocación

> ⚠ Revocar un certificado impide de inmediato el inicio de sesión mTLS con ese certificado. La revocación es permanente.

## Eliminar un certificado

Eliminar, en el menú **⋯** del detalle del certificado, borra tanto el certificado como la asociación usuario-certificado. Solo los administradores y operadores pueden eliminar.

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
