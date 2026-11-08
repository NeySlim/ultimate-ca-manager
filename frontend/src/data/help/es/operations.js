export default {
  helpContent: {
    title: 'Operaciones',
    subtitle: 'Importar, exportar y acciones masivas',
    overview: 'Centro de operaciones centralizado. Importe certificados desde archivos u OPNsense, exporte paquetes en formatos PEM/P7B y realice acciones masivas en todos los tipos de recursos con búsqueda en línea y filtros.',
    sections: [
      {
        title: 'Pestañas laterales',
        items: [
          { label: 'Importar', text: 'Importación inteligente con detección automática de formato, más sincronización OPNsense para obtener certificados de firewalls' },
          { label: 'Exportar', text: 'Descargar paquetes de certificados por tipo de recurso en formato PEM o P7B mediante tarjetas de acción' },
          { label: 'Acciones masivas', text: 'Seleccionar un tipo de recurso y realizar operaciones por lotes en múltiples elementos' },
        ]
      },
      {
        title: 'Acciones masivas',
        items: [
          { label: 'Certificados', text: 'Revocar, renovar, eliminar o exportar, filtrar por estado y CA emisora' },
          { label: 'CAs', text: 'Eliminar o exportar autoridades de certificación' },
          { label: 'CSRs', text: 'Firmar con una CA o eliminar solicitudes pendientes' },
          { label: 'Plantillas', text: 'Eliminar plantillas de certificado' },
          { label: 'Usuarios', text: 'Eliminar cuentas de usuario' },
        ]
      },
    ],
    tips: [
      'Use las fichas de recursos para cambiar rápidamente entre tipos de recursos',
      'La búsqueda en línea y los filtros (Estado, CA) le permiten reducir los elementos sin salir de la barra de herramientas',
      'Cambie entre los modos de vista Tabla y Cesta (panel de transferencia) en escritorio',
      'Revocar, renovar, firmar y eliminar piden confirmación antes de ejecutarse; una exportación se inicia de inmediato',
    ],
    warnings: [
      'La eliminación masiva es irreversible: siempre cree una copia de seguridad primero',
      'La revocación masiva publicará CRLs actualizadas para todas las CAs afectadas',
    ],
  },
  helpGuides: {
    title: 'Operaciones',
    content: `
## Descripción general

Operaciones masivas y gestión de datos. Realice acciones por lotes en múltiples recursos simultáneamente.

## Pestaña Importar

Igual que la página de Importar/Exportar: el asistente de importación inteligente y la integración OPNsense (conectar, explorar e importar desde OPNsense).

## Pestaña Exportar

Exportación masiva de certificados y CAs.

## Acciones masivas

Realice operaciones por lotes en múltiples recursos a la vez.

### Cómo funciona
1. Seleccione el **tipo de recurso** (Certificados, CAs, CSRs, Plantillas, Usuarios)
2. Marque los elementos en la tabla (la vista Cesta opcional los mueve entre dos paneles)
3. Elija la **acción** a realizar
4. Confirme y ejecute

### Acciones disponibles por recurso

#### Certificados
- **Revocación masiva**: Revocar múltiples certificados a la vez
- **Renovación masiva**: Renovar múltiples certificados
- **Exportación masiva**: Descargar los certificados seleccionados como un paquete
- **Eliminación masiva**: Eliminar permanentemente los certificados seleccionados

#### CAs
- **Exportación masiva**: Descargar las CAs seleccionadas
- **Eliminación masiva**: Eliminar las CAs seleccionadas (no deben tener hijos)

#### CSRs
- **Firma masiva**: Firmar múltiples CSRs con una CA seleccionada
- **Eliminación masiva**: Eliminar los CSRs seleccionados

#### Plantillas
- **Eliminación masiva**: Eliminar las plantillas seleccionadas

#### Usuarios
- **Eliminación masiva**: Eliminar permanentemente los usuarios seleccionados

> ⚠ Las operaciones masivas son irreversibles. Siempre cree una copia de seguridad antes de realizar eliminaciones o revocaciones masivas.

> 💡 Use la búsqueda y los filtros sobre la tabla para encontrar rápidamente elementos específicos.
`
  }
}
