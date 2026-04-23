export default {
  helpContent: {
    title: 'Usuarios y grupos',
    subtitle: 'Gestión de identidad y acceso',
    overview: 'Administre cuentas de usuario y membresías de grupo. Asigne roles para controlar el acceso a las funciones de UCM. Los grupos permiten la gestión masiva de permisos para equipos.',
    sections: [
      {
        title: 'Usuarios',
        items: [
          { label: 'Crear usuario', text: 'Agregar un nuevo usuario con nombre de usuario, correo electrónico y contraseña inicial' },
          { label: 'Roles', text: 'Asignar roles del sistema o personalizados para controlar los permisos' },
          { label: 'Estado', text: 'Activar o desactivar cuentas de usuario' },
          { label: 'Restablecer contraseña', text: 'Restablecer la contraseña de un usuario (acción de administrador)' },
          { label: 'Claves API', text: 'Administrar claves API por usuario para acceso programático' },
          { label: 'Origen', text: 'Muestra el origen de cada usuario: Local (gestionado en UCM) o LDAP / OAuth2 / SAML (provisionado por un proveedor SSO). La insignia muestra el nombre del proveedor de origen.' },
        ]
      },
      {
        title: 'Grupos',
        items: [
          { label: 'Crear grupo', text: 'Definir un grupo y asignar miembros' },
          { label: 'Herencia de roles', text: 'Los grupos pueden heredar roles — todos los miembros obtienen los permisos del grupo' },
          { label: 'Gestión de miembros', text: 'Agregar o eliminar usuarios de los grupos' },
        ]
      },
    ],
    tips: [
      'Use grupos para gestionar permisos de equipos en lugar de usuarios individuales',
      'Los usuarios desactivados no pueden iniciar sesión pero sus datos se conservan',
    ],
    warnings: [
      'Eliminar un usuario es permanente — considere desactivarlo en su lugar',
    ],
  },
  helpGuides: {
    title: 'Usuarios y grupos',
    content: `
## Descripción general

Administre cuentas de usuario, grupos y asignaciones de roles. Los usuarios se autentican en UCM mediante contraseña, SSO, WebAuthn o mTLS. Los grupos permiten la gestión masiva de permisos.

## Pestaña de usuarios

### Crear un usuario
1. Haga clic en **Crear usuario**
2. Ingrese el **nombre de usuario** (único, no se puede cambiar después)
3. Ingrese el **correo electrónico** (usado para notificaciones y recuperación)
4. Establezca una **contraseña inicial**
5. Seleccione un **rol** (Admin, Operator, Auditor, Viewer o personalizado)
6. Haga clic en **Crear**

### Estado del usuario
- **Activo** — Puede iniciar sesión y realizar acciones
- **Desactivado** — No puede iniciar sesión, los datos se conservan

Alterne el estado de un usuario sin eliminar su cuenta.

### Restablecer contraseña
Los administradores pueden restablecer la contraseña de cualquier usuario. Se le pedirá al usuario que la cambie en el próximo inicio de sesión.

### Claves API
Cada usuario puede tener múltiples claves API para acceso programático. Las claves API heredan los permisos del rol del usuario. Consulte la página de Cuenta para gestionar sus propias claves.

## Pestaña de grupos

### Crear un grupo
1. Haga clic en **Crear grupo**
2. Ingrese un **nombre** y una descripción opcional
3. Asigne un **rol** (los miembros del grupo heredan este rol)
4. Haga clic en **Crear**

### Gestión de miembros
- Haga clic en un grupo para ver sus miembros
- Use el **panel de transferencia** para agregar/eliminar usuarios
- Los usuarios pueden pertenecer a múltiples grupos

### Herencia de roles
Los permisos efectivos de un usuario son la **unión** de:
- Su rol asignado directamente
- Todos los roles de los grupos a los que pertenece

## Roles

### Roles del sistema
- **Admin** — Acceso completo a todas las funciones
- **Operator** — Puede gestionar certificados, CAs, CSRs pero no la configuración del sistema
- **Auditor** — Acceso de solo lectura a todos los datos operativos para cumplimiento y auditoría
- **Viewer** — Acceso de solo lectura a certificados, CAs y plantillas

### Roles personalizados
Cree roles con permisos granulares en la página **RBAC**.

> 💡 Use grupos para gestionar permisos de equipos en lugar de asignar roles a usuarios individuales.

## Origen de autenticación

La columna **Origen** indica de dónde proviene cada usuario:
- **Local** — creado y gestionado en UCM (contraseña local)
- **LDAP / OAuth2 / SAML** — provisionado automáticamente en el primer inicio de sesión SSO; el nombre del proveedor de origen aparece en la insignia (p. ej. \`LDAP · Corporate AD\`).

Desde v2.133, los roles modificados manualmente en UCM para usuarios SSO se **conservan** entre inicios de sesión, salvo que **«Sincronizar rol en cada inicio de sesión»** esté activado en el proveedor (ver **Configuración → SSO**).
`
  }
}
