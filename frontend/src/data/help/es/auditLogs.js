export default {
  helpContent: {
    title: 'Registros de auditoría',
    subtitle: 'Seguimiento de actividad y cumplimiento',
    overview: 'Pista de auditoría completa de todas las operaciones realizadas en UCM. Rastrea quién hizo qué, cuándo y desde dónde. Soporta filtrado, búsqueda, exportación y verificación de integridad.',
    sections: [
      {
        title: 'Filtros',
        items: [
          { label: 'Tipo de acción', text: 'Filtra por tipo de operación (crear, actualizar, eliminar, inicio de sesión, etc.)' },
          { label: 'Usuario', text: 'Filtra por el usuario que realizó la acción' },
          { label: 'Estado', text: 'Muestra solo operaciones exitosas o fallidas' },
          { label: 'Rango de fechas', text: 'Establece fechas desde/hasta para acotar la ventana de tiempo' },
          { label: 'Búsqueda', text: 'Búsqueda de texto libre en todos los registros' },
        ]
      },
      {
        title: 'Acciones',
        items: [
          { label: 'Exportar', text: 'Descarga registros en formato JSON o CSV' },
          { label: 'Limpieza', text: 'Purga registros antiguos con retención configurable (días)' },
          { label: 'Verificar integridad', text: 'Comprueba la integridad de la cadena de registros para detectar manipulaciones' },
        ]
      },
    ],
    tips: [
      'Exporta los registros regularmente para fines de cumplimiento y archivo',
      'Los intentos de inicio de sesión fallidos se registran con la IP de origen para monitoreo de seguridad',
      'Los registros incluyen el User Agent para identificar las aplicaciones cliente',
    ],
    warnings: [
      'La limpieza de registros es irreversible: los datos exportados no pueden ser reimportados',
    ],
  },
  helpGuides: {
    title: 'Registros de auditoría',
    content: `
## Descripción general

Pista de auditoría completa de todas las operaciones en UCM. Cada acción: emisión de certificados, revocación, inicio de sesión de usuario, cambio de configuración, se registra con detalles sobre quién, qué, cuándo y dónde.

## Detalles del registro

Cada entrada de registro incluye:
- **Marca de tiempo**: Cuándo ocurrió la acción
- **Usuario**: Quién realizó la acción
- **Acción**: Qué se hizo (crear, actualizar, eliminar, inicio de sesión, etc.)
- **Recurso**: Qué fue afectado (certificado, CA, usuario, etc.)
- **Estado**: Éxito o fallo
- **Dirección IP**: IP de origen de la solicitud
- **User Agent**: Identificador de la aplicación cliente
- **Detalles**: Contexto adicional (mensajes de error, valores modificados)

## Filtrado

### Por acción
Selecciona uno o varios nombres de acción, por ejemplo \`certificate_issued\` o \`login_success\`.

### Por usuario
Muestra solo las acciones realizadas por un usuario específico.

### Por estado
- **Éxito**: Operaciones completadas correctamente
- **Fallido**: Operaciones que fallaron (fallos de autenticación, permiso denegado, errores)

### Por rango de fechas
Establece las fechas **Desde** y **Hasta** para acotar la ventana de tiempo.

### Búsqueda de texto
Búsqueda de texto libre en el nombre de usuario, la acción, los detalles, el tipo de recurso y la dirección IP; el nombre y el id del recurso no se buscan.

## Exportar

Exporta los registros filtrados en:
- **JSON**: Legible por máquinas, incluye todos los campos
- **CSV**: Compatible con hojas de cálculo, incluye los campos principales

Las exportaciones aplican solo el rango de fechas, hasta 10 000 entradas: los demás filtros no se aplican.

## Limpieza

Purga registros antiguos según el período de retención:
1. Haz clic en **Limpieza**
2. Establece el período de retención en días
3. Confirma la limpieza

> ⚠ La limpieza de registros es irreversible. Exporta los registros importantes antes de purgar.

## Verificación de integridad

Haz clic en **Verificar integridad** para comprobar la cadena de registros de auditoría. UCM utiliza encadenamiento de hashes para detectar una entrada modificada o eliminada dentro de la cadena; eliminar las últimas entradas no deja rastro en la propia cadena, por lo que el reenvío a syslog conserva una copia en otro lugar.

## Reenvío a syslog

Configura el reenvío remoto a syslog en **Configuración → Auditoría** para enviar eventos de registro a un servidor SIEM o syslog externo en tiempo real.
`
  }
}
