export default {
  helpContent: {
    title: 'Usuarios y grupos',
    subtitle: 'Gestión de identidad y acceso',
    overview: 'Gestionar las cuentas de usuario y la pertenencia a grupos. Asignar roles para controlar el acceso a las funciones de UCM. Los grupos permiten gestionar permisos en bloque para los equipos.',
    sections: [
      {
        title: 'Usuarios',
        items: [
          { label: 'Crear usuario', text: 'Añadir un usuario nuevo con nombre de usuario, correo electrónico y contraseña inicial' },
          { label: 'Roles', text: 'Asignar roles del sistema o personalizados para controlar los permisos' },
          { label: 'Estado', text: 'Los chips sobre la lista cuentan las cuentas Todas, Activas, Deshabilitadas y SSO. Deshabilitar… pide una confirmación; la propia cuenta no puede deshabilitarse ni eliminarse desde esta página' },
          { label: 'Restablecer contraseña', text: 'Restablecer la contraseña de un usuario (acción de administrador). Las sesiones abiertas del usuario se cierran, igual que con un restablecimiento de 2FA' },
          { label: 'Eliminar usuario', text: 'Eliminar un usuario revoca los certificados que inscribió para mTLS (cessationOfOperation) y luego lo elimina. Un certificado que la CA no puede revocar no bloquea la eliminación: sigue siendo válido, se nombra en la advertencia y en el registro de auditoría, y debe revocarse en Certificados. Un fallo tras algunas revocaciones conserva al usuario y nombra los certificados ya revocados. Quitar un usuario o uno de sus certificados mTLS avisa cuando la CA ACME que emitió un certificado no fue informada de su revocación' },
          { label: 'Claves API', text: 'En el detalle de un usuario, enumerar sus claves API y revocar una filtrada o sin uso: deja de funcionar al instante, y una clave revocada o caducada puede eliminarse después. Los propietarios crean sus claves en su página Mi cuenta' },
          { label: 'Origen', text: 'Muestra lo que abre cada cuenta: Local (su contraseña de UCM), o cada proveedor vinculado, por tipo y nombre (por ejemplo OAuth2 · Okta, SAML · AD FS). Una cuenta puede estar vinculada a varios proveedores.' },
          { label: 'Permisos', text: 'La pestaña Permisos de una cuenta muestra cada recurso por Lectura, Escritura y Eliminación, Permitido o No permitido, tal como los aplica la autorización: su rol, su rol personalizado y sus grupos juntos; la pestaña Permisos de un grupo lee la misma cuadrícula' },
          { label: 'Exportar la lista', text: 'Descarga todas las cuentas como archivo CSV: nombre, usuario, correo, origen, rol, estado y último acceso' },
          { label: 'Grupos', text: 'El botón Grupos de la cabecera de la página muestra los grupos, Cuentas vuelve a las cuentas' },
        ]
      },
      {
        title: 'Grupos',
        items: [
          { label: 'Crear grupo', text: 'Definir un grupo y asignar miembros' },
          { label: 'Permisos del grupo', text: 'Un grupo concede un conjunto de permisos, marcados en una cuadrícula de recursos por Lectura, Escritura y Eliminación; cada miembro los recibe además de los de su propio rol' },
          { label: 'Gestión de miembros', text: 'Añadir o quitar usuarios de los grupos' },
        ]
      },
    ],
    tips: [
      'Usar grupos para gestionar los permisos de los equipos en lugar de usuarios individuales',
      'Los usuarios deshabilitados no pueden iniciar sesión pero sus datos se conservan',
    ],
    warnings: [
      'Eliminar un usuario es permanente: considerar deshabilitarlo en su lugar',
    ],
  },
  helpGuides: {
    title: 'Usuarios y grupos',
    content: `
## Visión general

Gestionar las cuentas de usuario, los grupos y las asignaciones de roles. Los usuarios se autentican en UCM mediante contraseña, SSO, WebAuthn o mTLS. Los grupos permiten gestionar permisos en bloque.

## Pestaña Usuarios

### Crear un usuario
1. Hacer clic en **Crear usuario**
2. Introducir el **nombre de usuario** (único, no puede cambiarse después)
3. Introducir el **correo electrónico** (se usa para las notificaciones y la recuperación)
4. Fijar una **contraseña inicial**
5. Seleccionar un **rol** (Administrador, Operador, Auditor, Visor o personalizado)
6. Hacer clic en **Crear**

### Estado del usuario
- **Activo**: puede iniciar sesión y realizar acciones
- **Deshabilitado**: no puede iniciar sesión, los datos se conservan

Cambiar el estado de un usuario sin eliminar su cuenta.

### Restablecer contraseña
Los administradores pueden restablecer la contraseña de cualquier usuario. No se pide al usuario que la cambie en el siguiente inicio de sesión: darle la contraseña nueva y pedirle que la cambie en Mi cuenta.

### Llaves de seguridad
En el detalle de un usuario, los administradores ven sus llaves de seguridad y pueden desactivar o quitar una, típicamente una llave perdida, que de otro modo sigue permitiendo iniciar sesión sin contraseña. Quitar el último segundo factor de una cuenta que lo exige pide una segunda confirmación; el usuario vuelve entonces a inscribir un factor en el siguiente inicio de sesión.

### Eliminar un usuario
Eliminar un usuario revoca los certificados que inscribió para mTLS (motivo cessationOfOperation) y luego lo elimina. Un certificado que la CA no puede revocar no bloquea la eliminación: sigue siendo válido, la advertencia y el registro de auditoría lo nombran, y se revoca en Certificados. Si la eliminación falla tras algunas revocaciones, el mensaje nombra los certificados ya revocados: siguen revocados.

### Claves API
Cada usuario puede tener varias claves API para el acceso programático. Las claves API heredan los permisos del rol del usuario. Consultar la página Mi cuenta para gestionar las claves propias.

## Pestaña Grupos

### Crear un grupo
1. Hacer clic en **Crear grupo**
2. Introducir un **nombre** y una descripción opcional
3. Seleccionar los **permisos** que concede el grupo (los miembros los reciben además de los de su propio rol)
4. Hacer clic en **Crear**

### Gestionar miembros
- Hacer clic en un grupo para ver sus miembros
- Usar el **panel de transferencia** para añadir o quitar usuarios
- Los usuarios pueden pertenecer a varios grupos

### Permisos del grupo
Los permisos efectivos de un usuario son la **unión** de:
- Los permisos del rol que tiene asignado directamente
- Los permisos de su rol personalizado, si lo hay
- Los permisos concedidos por cada grupo al que pertenece

## Roles

### Roles del sistema
- **Administrador**: acceso completo a todas las funciones
- **Operador**: puede gestionar certificados, CA, CSR, ACME, SSH y la configuración del sistema; plantillas y grupos en solo lectura, sin acceso a usuarios ni a RBAC
- **Auditor**: acceso de solo lectura a todos los datos operativos para el cumplimiento y la auditoría
- **Visor**: acceso de solo lectura a certificados, CA y plantillas

### Roles personalizados
Crear roles con permisos granulares en la página **RBAC**.

> 💡 Usar grupos para gestionar los permisos de los equipos en lugar de asignar roles a usuarios individuales.

## Origen de autenticación

La columna **Origen** muestra lo que abre cada cuenta:
- **Local**: creada y gestionada en UCM (contraseña local)
- **LDAP / OAuth2 / SAML**: una entrada por proveedor vinculado a la cuenta, por tipo y nombre (por ejemplo \`LDAP · Corporate AD\`); una cuenta puede tener varios.

Desde la v2.133, los roles cambiados manualmente en UCM para usuarios SSO se **conservan** entre inicios de sesión, salvo que **"Sincronizar el rol en cada inicio de sesión"** esté activado en el proveedor (ver **Configuración → SSO**).

El panel de la cuenta enumera sus **Proveedores de inicio de sesión único**, cada uno vinculado, a la espera de su primer inicio de sesión, o abandonado por un proveedor eliminado. **Vincular un proveedor** añade uno: los proveedores ya vinculados siguen abriendo la cuenta, y el siguiente inicio de sesión mediante el nuevo con el nombre de usuario o el correo de la cuenta enlaza su identidad. **Restablecer identidad** borra la identidad de un proveedor cuyo IdP la cambió, y **Desvincular** quita un proveedor, cada uno tras una confirmación; vincular, restablecer y desvincular cierran todas las sesiones de la cuenta. Para pasar una cuenta a otro proveedor, vincular el nuevo y luego desvincular el antiguo. La contraseña que tenga la cuenta se conserva salvo que se marque la casilla que la elimina, tras lo cual ningún inicio de sesión con contraseña abre la cuenta; a una cuenta sin contraseña solo se le pide fijar una cuando se desvincula su último proveedor, y entonces pasa a ser una cuenta local.
`
  },
}
