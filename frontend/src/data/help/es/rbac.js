export default {
  helpContent: {
    title: 'Control de acceso basado en roles',
    subtitle: 'Gestión de permisos granular',
    overview: 'Defina roles personalizados con permisos granulares. Los roles del sistema (Admin, Operator, Auditor, Viewer) están integrados. Los roles personalizados le permiten controlar exactamente qué operaciones puede realizar cada usuario.',
    sections: [
      {
        title: 'Roles del sistema',
        definitions: [
          { term: 'Admin', description: 'Acceso completo a todas las funciones y configuraciones' },
          { term: 'Operator', description: 'Puede gestionar certificados y CA pero no la configuración del sistema' },
          { term: 'Auditor', description: 'Acceso de solo lectura a todos los datos operativos para cumplimiento y auditoría' },
          { term: 'Viewer', description: 'Acceso básico de solo lectura a certificados, CA y plantillas' },
        ]
      },
      {
        title: 'Roles personalizados',
        items: [
          { label: 'Crear rol', text: 'Definir un nuevo rol con nombre y descripción' },
          { label: 'Matriz de permisos', text: 'Marcar/desmarcar permisos por categoría (CA, Certificados, Usuarios, etc.)' },
          { label: 'Cobertura', text: 'Porcentaje visual del total de permisos otorgados al rol' },
          { label: 'Cantidad de usuarios', text: 'Ver cuántos usuarios están asignados a cada rol' },
        ]
      },
    ],
    tips: [
      'Siga el principio de mínimo privilegio — otorgue solo los permisos necesarios',
      'Los roles del sistema no se pueden modificar ni eliminar',
      'Active/desactive categorías completas para configurar roles rápidamente',
    ],
  },
  helpGuides: {
    title: 'Control de acceso basado en roles',
    content: `
## Descripción general

RBAC proporciona una gestión de permisos granular. Defina roles personalizados con permisos específicos y asígnelos a usuarios o grupos.

## Roles del sistema

Cuatro roles integrados que no se pueden modificar ni eliminar:

- **Admin** — Acceso completo a todo
- **Operator** — Gestiona certificados, CA, CSR y plantillas. Sin acceso a configuración del sistema, usuarios ni RBAC
- **Auditor** — Acceso de solo lectura a todos los datos operativos (certificados, CA, ACME, SCEP, HSM, registros de auditoría, políticas, grupos) pero no a configuración ni gestión de usuarios
- **Viewer** — Acceso básico de solo lectura a certificados, CA, CSR, plantillas y almacén de confianza

## Roles personalizados

### Crear un rol personalizado
1. Haga clic en **Crear rol**
2. Introduzca un **nombre** y una descripción opcional
3. Configure los permisos usando la **matriz de permisos**
4. Haga clic en **Crear**

### Matriz de permisos
Los permisos están organizados por categoría:
- **CA** — Crear, leer, actualizar, eliminar, importar, exportar
- **Certificados** — Emitir, leer, revocar, renovar, eliminar, exportar (solo el certificado — véase Claves privadas)
- **Claves privadas** — Exportación directa de la clave privada (\`read:private_keys\`), solo administradores: ningún rol integrado salvo Admin la posee. Los roles sin ella pasan por la Recuperación de claves
- **CSR** — Crear, leer, firmar, eliminar
- **Plantillas** — Crear, leer, actualizar, eliminar
- **Usuarios** — Crear, leer, actualizar, eliminar
- **Grupos** — Crear, leer, actualizar, eliminar
- **Configuración** — Leer, actualizar
- **Auditoría** — Leer, exportar, limpiar
- **ACME** — Configurar, gestionar cuentas
- **SCEP** — Configurar, aprobar solicitudes
- **Almacén de confianza** — Gestionar certificados de confianza
- **HSM** — Gestionar proveedores y claves
- **SSH** — Gestionar CA SSH y certificados SSH
- **Políticas** — Ver políticas de certificados
- **Aprobaciones** — Ver y decidir solicitudes de aprobación
- **Recuperación de claves** — Solicitar recuperaciones y ver solicitudes (la aprobación es solo para administradores)
- **Respaldo** — Crear, restaurar

### Alternar categorías
Haga clic en el encabezado de una categoría para activar/desactivar todos los permisos de esa categoría de una vez.

### Indicador de cobertura
Una insignia de porcentaje muestra cuánto del conjunto total de permisos cubre el rol. 100% = equivalente a Admin.

## Asignación de roles

Los roles se asignan:
- **Directamente** — En la página de Usuarios, edite un usuario y seleccione un rol
- **Mediante grupos** — Un grupo otorga un conjunto de permisos; cada miembro lo recibe además de su propio rol

## Permisos efectivos

Los permisos efectivos de un usuario se calculan como la unión de:
1. Los permisos del rol asignado directamente
2. Los permisos otorgados por los grupos a los que pertenece

La regla más permisiva prevalece (modelo aditivo, sin reglas de denegación).

> ⚠ Los roles del sistema no se pueden editar ni eliminar. Cree roles personalizados para necesidades específicas.
`
  }
}
