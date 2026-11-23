export default {
  helpContent: {
    title: "Actividad",
    subtitle: "El registro de auditoría de cada operación",
    overview: "Cada operación realizada en UCM, del certificado al registro: quién hizo qué, cuándo, desde dónde y con qué resultado. La lista lee el servidor página a página; los filtros, la exportación, la comprobación de integridad y la limpieza actúan sobre todo el registro.",
    sections: [
      {
        title: "Encontrar una entrada",
        items: [
          { label: "Buscar", text: "Texto libre en el nombre de usuario, el código de acción, los detalles, el tipo de recurso y la dirección IP; el nombre del recurso en sí no se busca" },
          { label: "Tipo de operación", text: "Emisiones, renovaciones, revocaciones, inicios de sesión, usuarios, ajustes y los demás tipos agrupan cada uno códigos de acción del servidor" },
          { label: "Filtros", text: "Fechas, usuario, resultado y códigos de acción uno a uno; cada filtro activo aparece como una etiqueta bajo la barra de herramientas, con su propio botón para quitarlo" },
          { label: "Atajos y filtros guardados", text: "Inicios fallidos o todos los fallos con un clic; los filtros actuales se pueden guardar con un nombre y volver a aplicar (se conservan en este navegador)" },
          { label: "Detalles", text: "El nombre del recurso o la flecha de una fila abre la entrada: su texto, usuario, fecha y hora, resultado, código de acción, dirección IP y cliente; Inspeccionar el certificado (o Ver la autoridad) abre lo que nombra la entrada. En un teléfono cada entrada es una tarjeta que se abre con un toque en cualquier punto" },
        ]
      },
      {
        title: "Acciones del registro",
        items: [
          { label: "Exportar el registro", text: "CSV o JSON, con la búsqueda y los filtros actuales, 10 000 entradas como máximo; en un teléfono está en el menú « ⋯ »" },
          { label: "Verificar integridad", text: "En el menú « ⋯ »: comprueba la cadena de hashes del registro; en un registro grande se ejecuta en segundo plano, y su progreso y Cancelar verificación aparecen en la línea de resumen" },
          { label: "Limpiar registros antiguos", text: "En el menú « ⋯ », con el derecho de eliminar el registro: elimina las entradas anteriores a un período de retención de 30 a 3650 días" },
        ]
      },
    ],
    tips: [
      "Exporte el registro con regularidad por cumplimiento normativo y archivo",
      "Los inicios de sesión fallidos se registran con su dirección IP de origen, y cada entrada con su cliente (user agent)",
      "El « Ver su actividad » de un certificado abre esta página con una búsqueda de su nombre",
    ],
    warnings: [
      "La limpieza es irreversible: un registro exportado no se puede volver a importar",
    ],
  },
  helpGuides: {
    title: "Actividad",
    content: `
## Resumen

Cada operación de UCM se anota en el registro de auditoría: emisión de certificados, revocación, inicio de sesión, cambio de ajustes. La página Actividad lo lista, de más reciente a más antiguo, con quién, qué, cuándo y el resultado. La cabecera cuenta las entradas de todo el registro; la línea de resumen bajo la barra de herramientas cuenta las que conservan los filtros, indica desde cuándo se remonta el registro y resume los últimos 30 días.

## Una entrada

Cada fila muestra la hora (y también el día cuando no es hoy), la operación (el pictograma de su tipo y el código de acción), el recurso, el usuario y el resultado (Correcta o Fallida, con todas las letras). El nombre del recurso o la flecha abre el detalle de la entrada:
- **Texto**: lo que registró el servidor (mensajes de error, valores)
- **Recurso**, **Usuario**, **Fecha / hora**, **Resultado**
- **Acción**: el código tal como lo almacena el servidor
- **Dirección IP** y **Cliente** (user agent), cuando se registraron

Cuando la entrada nombra un certificado o una autoridad, **Inspeccionar el certificado** (o **Ver la autoridad**) lo abre en el inspector.

En un teléfono cada entrada es una tarjeta con los mismos datos: un toque en cualquier punto, o en su flecha, abre el detalle.

## Encontrar entradas

### Buscar
Texto libre en el nombre de usuario, el código de acción, los detalles, el tipo de recurso y la dirección IP; el nombre del recurso en sí no se busca.

### Tipo de operación
El selector de la barra de herramientas agrupa los códigos de acción por tipo: emisiones, renovaciones, revocaciones, exportaciones, certificados y CSR, aprobaciones, publicaciones de CRL, ACME, SCEP, inicios de sesión, usuarios, copias de seguridad, ajustes, configuración, sistema. Solo se ofrecen los tipos que contiene el registro.

### Filtros
El botón **Filtros** abre las fechas (**Desde**, **Hasta**), el **Usuario**, el **Resultado** y los códigos de acción uno a uno (acotados al tipo elegido). Dos atajos fijan **Inicios fallidos** o **Todos los fallos**. Los filtros actuales se pueden guardar con un nombre y volver a aplicar más tarde; se conservan en este navegador. Cada filtro activo aparece como una etiqueta bajo la barra de herramientas, y **Restablecer los filtros** los quita todos.

La lista se lee página a página desde el servidor: 10, 25, 50 o 100 entradas por página, anterior y siguiente, o un número de página e **Ir**.

## Exportación

**Exportar el registro** descarga las entradas que conservan la búsqueda y los filtros, 10 000 como máximo:
- **CSV**: una fila por entrada, para una hoja de cálculo
- **JSON**: datos estructurados, todos los campos

En un teléfono el botón de la cabecera está oculto: la exportación está en el menú « ⋯ ».

## Limpieza

En el menú « ⋯ », con el derecho de eliminar el registro:
1. Elija **Limpiar registros antiguos…**
2. Indique el período de retención en días (30 a 3650)
3. Elija **Eliminar registros antiguos**

> ⚠ La limpieza es irreversible. Exporte antes las entradas que necesite.

## Verificación de integridad

**Verificar integridad**, en el menú « ⋯ », comprueba la cadena del registro de auditoría. UCM usa el encadenamiento de hashes para detectar una entrada modificada o eliminada dentro de la cadena; eliminar las últimas entradas no deja rastro en la propia cadena, por eso el reenvío a syslog conserva una copia en otro lugar.

En un registro grande la verificación se ejecuta en segundo plano: la línea de resumen indica cuántas entradas se han comprobado hasta el momento, **Cancelar verificación** la detiene, y salir de la página o recargarla no la detiene (la página la retoma). Solo se ejecuta una verificación a la vez.

## Reenvío a syslog

Configure el reenvío a un syslog remoto en **Configuración → Auditoría** para enviar los eventos del registro a un SIEM o servidor syslog externo en tiempo real.

Todo evento de auditoría se reenvía por defecto. Desmarcar una categoría (Certificados, AC, CSR, Usuarios, ACME, SCEP, Sistema) detiene solo sus eventos: ACME abarca todos los eventos ACME, Usuarios abarca los inicios y cierres de sesión, SSO incluido. Dejar todas las casillas desmarcadas reenvía todos los eventos. Los cambios de cuenta (creación, rol, contraseña, MFA, activación), los cambios del propio reenvío a syslog, las purgas de auditoría, las claves de API, los roles, los ajustes y las políticas se reenvían siempre. En Sistema, las descargas de la clave maestra, los cambios de cifrado, las restauraciones, los reinicios y cambios de base de datos, los ajustes de actualización, las eliminaciones de copias de seguridad y las descargas de paquetes de registros también se reenvían siempre. Un cambio de syslog se envía con la configuración anterior, de modo que el colector cuyo alcance se reduce o que se desactiva lo recibe, y un colector recién configurado lo recibe también.
`
  }
}
