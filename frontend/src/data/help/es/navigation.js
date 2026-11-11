export default {
  helpContent: {
    title: 'Navegación',
    subtitle: 'La barra superior, el menú Módulos y los módulos fijados',
    overview: 'La barra superior contiene las páginas principales, hasta tres módulos que usted fija, el menú Módulos, la búsqueda y su cuenta. El menú Módulos lista todas las páginas que puede abrir, en cuatro grupos; las páginas a las que no tiene derecho no se muestran.',
    sections: [
      {
        title: 'Menú Módulos',
        items: [
          { label: 'Abrir', text: 'Seleccione Módulos, o pulse la flecha Abajo en el botón; el foco pasa a la primera página' },
          { label: 'Moverse', text: 'Las flechas Arriba y Abajo, Inicio y Fin permiten pasar de una página a otra; Escape cierra el menú y vuelve al botón' },
          { label: 'Fijar', text: 'El botón de chincheta junto a una página la mantiene en la barra superior; tres como máximo, y el menú lo indica si intenta una cuarta' },
        ]
      },
      {
        title: 'Búsqueda y atajos',
        items: [
          { label: 'Búsqueda', text: 'Pulse Ctrl K (Cmd K en macOS) o seleccione el campo de búsqueda para ir a una página o encontrar un certificado' },
          { label: 'Ayuda', text: 'Pulse ? fuera de un campo de texto para abrir la ayuda de la página actual' },
          { label: 'Ancho de teléfono', text: 'La barra superior muestra una sola lista de páginas en lugar de los enlaces y del menú' },
        ]
      },
      {
        title: 'Menú de la cuenta',
        items: [
          { label: 'Cuenta', text: 'Su perfil y ajustes, el idioma y el cierre de sesión' },
        ]
      },
      {
        title: 'Menú del tema',
        items: [
          { label: 'Elegir', text: 'El botón de sol o luna define el tema de color y el modo; Sistema sigue su dispositivo, y el icono muestra el modo aplicado' },
          { label: 'Teclado', text: 'Las flechas Arriba y Abajo recorren las opciones en bucle; Escape o Tab cierra el menú y vuelve al botón' },
          { label: 'Guardado', text: 'La elección es la de Ajustes, Apariencia, y le sigue en todos los navegadores' },
        ]
      },
      {
        title: 'Notificaciones',
        items: [
          { label: 'Campana', text: 'El contador es el número de elementos sin leer del panel: elementos críticos y aprobaciones de la cola del resumen, y copias de seguridad programadas fallidas o sesiones revocadas del registro de auditoría' },
          { label: 'Orden', text: 'Primero van los elementos de la cola, luego los del registro de auditoría, del más reciente al más antiguo' },
          { label: 'Derechos', text: 'Solo ve los elementos de las fuentes que puede leer; una fuente sobre la que no tiene ningún derecho no muestra nada' },
          { label: 'Leído', text: 'Marque un elemento o todos como leídos; las marcas se guardan con sus preferencias, y un elemento resuelto sale del panel' },
          { label: 'Abrir', text: 'Abrir lleva a la página del elemento; desde el panel no se aprueba ni se reintenta nada' },
        ]
      },
    ],
    tips: [
      'Sus chinchetas le siguen en todos los navegadores y dispositivos desde los que inicia sesión',
      'Una página fijada que ya no tiene derecho a abrir se oculta, y vuelve si el derecho se restablece antes de que cambie sus fijaciones',
    ],
  },
}
