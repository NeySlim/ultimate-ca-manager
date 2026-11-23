export default {
  helpContent: {
    title: "Registros del sistema",
    subtitle: "El registro de aplicación del servidor",
    overview: "Vuelve a leer lo que UCM escribió, sin acceso de shell al host. Es el registro que explica un fallo de protocolo para el que la solicitud nunca llegó a crear un registro: una inscripción SCEP rechazada durante la validación se descarta antes de que exista una fila de solicitud, y por eso aparece aquí y en ningún otro sitio.",
    sections: [
      {
        title: "Orígenes",
        items: [
          { label: "Aplicación", text: "El registro propio de UCM. Solo este origen tiene componentes" },
          { label: "Acceso", text: "Registro de acceso de Gunicorn: peticiones HTTP y códigos de estado, solo instalaciones nativas" },
          { label: "Errores", text: "Registro de errores de Gunicorn: arranque de los workers y trazas no gestionadas, solo instalaciones nativas" },
          { label: "Diario", text: "El diario de la unidad systemd, si el usuario del servicio puede leerlo" },
        ]
      },
      {
        title: "Filtros",
        items: [
          { label: "Origen", text: "Qué registro se lee. Solo se ofrecen los orígenes que esta instalación tiene" },
          { label: "Componente", text: "Un subsistema del registro de aplicación, o todos. Se listan todos, no solo los que aparecen en pantalla" },
          { label: "Nivel de registro", text: "Un mínimo, no una coincidencia exacta: WARNING muestra también errores y críticos" },
          { label: "Buscar", text: "Sin distinguir mayúsculas, en el mensaje y en el nombre del componente. Texto literal, no un patrón" },
          { label: "Excluir", text: "Quita las líneas que coinciden: la forma más rápida de silenciar un latido" },
          { label: "Fecha", text: "Una ventana Desde/Hasta, aplicada en el servidor" },
          { label: "Líneas", text: "Cuántas líneas coincidentes devolver, de la más reciente a la más antigua" },
        ]
      },
      {
        title: "Registros en vivo",
        items: [
          "Consulta cada cinco segundos; la línea más reciente es la primera fila",
          "Limpia la ventana de fechas, que plantea la pregunta opuesta",
          "El botón Registros en vivo permanece pulsado mientras consulta",
        ]
      },
    ],
    tips: [
      "Las horas se escriben en la hora local del servidor, sin desfase en la línea; la zona se indica al pie de la página",
      "Una línea que no coincide con ningún formato conocido se muestra igualmente, sin nivel, en lugar de ocultarse",
      "Una traza es una sola entrada, no una por línea: la celda del mensaje se ajusta para mostrarla entera",
      "Los secretos se redactan en el servidor antes de que nada salga del proceso",
    ],
    warnings: [
      "Un componente que no ha registrado nada recientemente sigue en la lista, así que elegirlo puede no devolver nada",
      "La lectura de este registro es solo para administradores y no se audita a propósito: el rastro de auditoría se repite en este mismo registro, y anotar cada lectura enterraría las líneas que debe poner de relieve",
    ],
  },
  helpGuides: {
    title: "Registros del sistema",
    content: `
## Resumen

Vuelve a leer lo que UCM escribió, sin acceso de shell al host. Es el registro que explica un fallo para el que nunca se creó un registro: una inscripción SCEP rechazada durante la validación se descarta antes de que exista una fila de solicitud, así que aparece aquí y en ningún otro sitio.

Las líneas se muestran de más reciente a más antigua y todos los filtros se aplican en el servidor, de modo que un filtro nunca oculta líneas que simplemente no se hayan recuperado.

## Orígenes

**Origen** y **Componente** están en el cuadro **Filtros**: elija el registro y luego acótelo a un subsistema. Cada filtro elegido aparece bajo la barra de herramientas, y su cruz lo quita.

- **Aplicación**: el registro propio de UCM. Es el único origen con componentes.
- **Acceso**: el registro de acceso de Gunicorn, con las peticiones HTTP y los códigos de estado. Solo instalaciones nativas.
- **Errores**: el registro de errores de Gunicorn, con el arranque de los workers y las trazas no gestionadas. Solo instalaciones nativas.
- **Diario**: el diario de la unidad systemd, si el usuario del servicio puede leerlo.

Solo se ofrecen los orígenes que esta instalación tiene realmente. Un origen sin nada detrás se omite en lugar de mostrarse vacío.

### Componentes

**Todos los componentes** es el registro de aplicación completo. La lista contiene todos los subsistemas desde los que UCM puede registrar (\`services\`, \`api\`, \`utils\`, \`security\` y el resto), hayan registrado recientemente o no, además de los registradores concretos de los que proceden las líneas en pantalla.

Elegir uno abarca todo lo que hay debajo. \`services\` coincide con \`services.scep.scep_service\` y con cualquier otro servicio; \`services.scep\` acota al subárbol de SCEP.

## Filtrado

### Nivel de registro
Un mínimo, no una coincidencia exacta. **WARNING** muestra advertencias, errores y críticos. **DEBUG** lo muestra todo.

Este filtro nunca oculta un registro cuyo nivel no se pudo leer: su gravedad es desconocida, y adivinarla ocultaría las líneas que más conviene ver.

### Buscar y Excluir
Ambos recorren el mensaje y el nombre del componente, y ninguno distingue mayúsculas. **Excluir** quita lo que coincide: la forma más rápida de silenciar un latido que se repite cada minuto y entierra el único error.

Ambos son texto literal y no patrones, así que \`.*\` encuentra esos dos caracteres y nada más. Un patrón enviado desde el navegador es trabajo sin límite para el único worker que responde a ACME, SCEP y OCSP desde este mismo proceso.

### Fecha
Una ventana **Desde**/**Hasta**, aplicada en el servidor. A diferencia del mínimo de nivel, un registro sin marca de tiempo queda fuera cuando se fija un límite: una ventana pide un instante, y ese registro no tiene ninguno.

### Líneas
Cuántas líneas coincidentes devolver, de 100 a 5000. El pie de página indica cuándo se dejaron fuera líneas más antiguas y cuántas coincidían en total.

## Registros en vivo

Consulta cada cinco segundos. Limpia la ventana de fechas, que plantea la pregunta opuesta, y es la forma más rápida de seguir una inscripción o una renovación mientras ocurre.

## Copiar

**Copiar todo**, en la cabecera de la página, toma todas las líneas en pantalla. Marque la casilla junto a una línea y la barra de selección ofrece **Copiar selección**. Ambos copian una línea tal como la escribe el archivo: hora, componente, nivel, mensaje. Lo que llega al portapapeles se lee como un registro, y al pegarlo de nuevo en esta página se analiza como tal.

## Leer el pie de página

El pie de la página indica el archivo que se lee, la zona horaria en la que se escriben sus marcas de tiempo y si se cortó algo:

- **Mostrando las N líneas más recientes de M coincidentes**: coincidieron más líneas de las que permite el ajuste **Líneas**. Aumente el valor para ver más atrás.
- **Solo se leyó la parte más reciente del archivo**: el archivo es mayor que la ventana que recorre el lector, así que las líneas más antiguas quedan fuera de alcance con cualquier número de líneas.

Las marcas de tiempo no llevan desfase propio: son la hora local del servidor, y la zona aparece junto a la ruta.

## Acceso

La lectura de este registro exige derechos de administrador. No se audita a propósito: el rastro de auditoría se escribe en este mismo registro, y anotar cada lectura enterraría las líneas que la página existe para poner de relieve. El paquete de diagnóstico de **Configuración → Acerca de** sí se audita, por ser un acto poco frecuente y deliberado que se lleva una copia del archivo.
`
  }
}
