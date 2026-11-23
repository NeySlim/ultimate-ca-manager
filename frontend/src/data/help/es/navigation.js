export default {
  helpContent: {
    title: 'Navegación',
    subtitle: 'La barra superior, el menú Módulos y los módulos fijados',
    overview: 'La barra superior contiene las páginas principales (Vista general, Certificados, Autoridades y Actividad, el registro de auditoría para quien puede leerlo), hasta tres módulos que se fijan, el menú Módulos, la búsqueda y la cuenta. El menú Módulos enumera todas las demás páginas que se pueden abrir, en cuatro grupos con su número, cada una con una línea que dice para qué sirve; las páginas a las que no se tiene derecho no se muestran.',
    sections: [
      {
        title: 'Menú Módulos',
        items: [
          { label: 'Abrir', text: 'Seleccionar Módulos, o pulsar la flecha Abajo sobre el botón; el foco pasa a la primera página' },
          { label: 'Moverse', text: 'Las flechas Arriba y Abajo, Inicio y Fin permiten pasar de una página a otra; Esc cierra el menú y vuelve al botón' },
          { label: 'Fijar', text: 'El botón de chincheta junto a una página la mantiene en la barra superior; tres como máximo, y un mensaje lo indica al intentar fijar una cuarta' },
          { label: 'Fijados', text: 'Los módulos fijados aparecen después de Actividad en la barra principal; la cabecera del menú cuenta sus páginas y los módulos fijados' },
        ]
      },
      {
        title: 'Búsqueda y atajos',
        items: [
          { label: 'Búsqueda', text: 'Pulsar Ctrl K (Cmd K en macOS) o seleccionar el campo de búsqueda para ir a cualquier página del menú que se pueda abrir (bajo su nombre de menú, con su grupo como indicación), ejecutar una acción (Emitir un certificado abre su formulario), abrir una pestaña de las páginas ACME, SCEP, EST y TSA escribiendo su nombre (ACME: Proveedores DNS) o encontrar un certificado, una CA, un usuario, una plantilla, una cuenta ACME o un perfil SCEP. La flecha Abajo pasa del campo a los resultados, la flecha Arriba vuelve del primer resultado al campo, y Intro en el campo abre el primer resultado. Un objeto encontrado se abre en el detalle de su página' },
          { label: 'Dirección', text: 'El objeto abierto en el panel de detalle de una página y su sección forman parte de la dirección: una recarga o un enlace compartido los vuelve a abrir, y el botón Atrás del navegador cierra el panel' },
          { label: 'Ayuda', text: 'Pulsar ? fuera de un campo de texto, o seleccionar el botón de ayuda de la barra, para abrir la ayuda de la página actual; en una pantalla estrecha, donde la barra no tiene botón de ayuda, buscar Ayuda de esta página' },
          { label: 'Ancho de teléfono', text: 'La barra superior muestra una sola lista de páginas en lugar de los enlaces y el menú' },
          { label: 'Ancho de columnas', text: 'En una lista, arrastrar la línea entre dos cabeceras de columna, tomada a uno u otro lado, o enfocarla con Tab y usar las flechas Izquierda y Derecha (Mayús para pasos mayores, Esc para cancelar), para fijar el ancho de una columna; un doble clic o Supr devuelve su ancho automático, el ancho se conserva en este navegador para cada lista, y Restablecer columnas, en el pie de la lista o en el diálogo Columnas de los certificados, los borra todos' },
          { label: 'Guía', text: 'Abrir en una pestaña nueva, en lo alto de la ayuda, abre la guía completa en el capítulo de la página, junto a la consola; Guía en la búsqueda hace lo mismo. La guía enumera todos los capítulos a la izquierda y las secciones del capítulo se leen en En esta página, busca en todos ellos, e imprime un capítulo o la guía completa' },
        ]
      },
      {
        title: 'Menú de cuenta',
        items: [
          { label: 'Cuenta', text: 'Las iniciales junto al nombre, el rol y el identificador, luego lo que el servidor sabe de la sesión, leído de nuevo cada vez que se abre el menú: correo electrónico, método de inicio de sesión (con el proveedor SSO o LDAP), doble factor activado o desactivado y sus métodos, bloqueo por inactividad y fin de la sesión; después Mi cuenta, Configuración (para quien puede abrirla) y, aparte, Bloquear y Cerrar sesión; en un teléfono, también el idioma. El idioma se elige desde el botón del globo de la barra superior, en Mi cuenta y en la página de inicio de sesión; Configuración también está en el menú Módulos y en la búsqueda' },
        ]
      },
      {
        title: 'Sesión',
        items: [
          { label: 'Aviso', text: 'Cinco minutos antes del fin por inactividad, un banner muestra el tiempo restante; Prolongar mantiene la sesión e indica por cuánto tiempo, otra actividad ya no lo hace' },
          { label: 'Bloqueo', text: 'Al final la sesión se bloquea: el servidor la conserva solo para la cuenta y no sirve nada más, y nada de la consola queda abierto detrás de la pantalla' },
          { label: 'Bloquear ahora', text: 'Bloquear en el menú de cuenta, o Alt+Mayús+L (Option+Mayús+L en Mac) fuera de un campo de texto, bloquea la sesión y la pantalla de inmediato, y la pantalla indica que la sesión se bloqueó en lugar de haber caducado; todas las pestañas del navegador se bloquean con ella' },
          { label: 'Desbloquear', text: 'La pantalla de bloqueo ofrece a la vez los medios de que dispone la cuenta: su contraseña (luego su segundo factor, como al iniciar sesión), Desbloquear con el certificado si tiene un certificado de cliente, Desbloquear con una clave de acceso si tiene una. Nada más reabre la sesión: ni un certificado de cliente que el navegador presente por sí mismo ni un inicio de sesión SSO. Con un certificado de cliente, el bloqueo protege tanto como el propio certificado, ya que el mismo certificado desbloquea: conviene guardarlo en una tarjeta inteligente con PIN, o en un almacén de certificados que pregunte antes de usarlo' },
          { label: 'Volver', text: 'Desbloquear vuelve a la página que estaba abierta; Iniciar sesión con otra cuenta cierra primero la sesión y empieza de nuevo. Una sesión que terminó entretanto pide iniciar sesión de nuevo con la misma cuenta' },
        ]
      },
      {
        title: 'Menú de tema',
        items: [
          { label: 'Elegir', text: 'El botón de tema ofrece dos grupos que se eligen por separado: el tema, Atelier o Aurore, y el modo, Sistema, Oscuro o Claro, con los actuales marcados; Sistema sigue el dispositivo en cualquiera de los temas, el icono muestra el modo aplicado (destellos para Aurore)' },
          { label: 'Teclado', text: 'Las flechas Arriba y Abajo recorren las opciones en bucle; Esc o Tab cierra el menú y vuelve al botón' },
          { label: 'Guardado', text: 'La elección es la de Configuración, Apariencia, y sigue a la cuenta en todos los navegadores' },
        ]
      },
      {
        title: 'Notificaciones',
        items: [
          { label: 'Campana', text: 'El número es el de elementos sin leer del panel: elementos críticos y aprobaciones de la cola de la vista general, y copias de seguridad programadas fallidas, restauraciones fallidas o sesiones revocadas del registro de auditoría' },
          { label: 'Orden', text: 'El panel agrupa los elementos por día, el más reciente primero: hoy, ayer, luego la fecha' },
          { label: 'Acciones', text: 'Una renovación ACME fallida ofrece Reintentar y una CRL por publicar ofrece Publicar, para quien puede hacerlo; los demás elementos solo abren su página' },
          { label: 'Derechos', text: 'Solo se ven los elementos de las fuentes que se pueden leer; una fuente sobre la que no se tiene derecho no muestra nada' },
          { label: 'Leído', text: 'Marcar un elemento o todos como leídos; las marcas se guardan con las preferencias, y un elemento que se resuelve sale del panel' },
          { label: 'Teclado', text: 'Esc cierra el panel estando el foco donde esté y vuelve a la campana; un clic fuera u otro menú de la barra también lo cierra. Solo hay un menú o panel de la barra abierto a la vez: abrir otro, la ayuda o la búsqueda cierra el que estaba abierto. Tras Marcar como leído el foco se queda en la línea, tras Marcar todo como leído pasa al título' },
          { label: 'Abrir', text: 'Abrir va a la página del elemento y lo marca como leído; las aprobaciones se deciden en su propia página' },
          { label: 'Correo', text: 'Para quien puede leer la configuración, el pie indica si la notificación por correo está activada y enlaza con su configuración' },
        ]
      },
      {
        title: 'Alta disponibilidad',
        items: [
          { label: 'Barra de estado', text: 'En modo de alta disponibilidad la barra de estado muestra los nodos, o cuántos han dejado de enviar latidos, y el nodo en el que se está; seleccionarla enumera los nodos' },
          { label: 'Aprobaciones', text: 'Para quien puede leerlas, la barra de estado enlaza las aprobaciones que esperan una decisión, con su número' },
          { label: 'Degradado', text: 'Cuando un nodo deja de enviar latidos, un banner lo indica y dice qué sigue funcionando: lectura y emisión en los nodos que responden, tareas programadas en el nodo líder' },
          { label: 'Mantenimiento', text: 'Durante un mantenimiento del clúster, una restauración por ejemplo, el servidor rechaza toda escritura: el banner indica hasta cuándo, y los botones de escritura de todas las páginas se desactivan con ese motivo' },
          { label: 'Sin conexión', text: 'Cuando se pierde la red, un banner lo indica: la lectura continúa con los datos ya cargados, los botones de escritura de todas las páginas se desactivan, y vuelven solos con la red' },
          { label: 'Conexión en vivo', text: 'El icono tras el estado del servicio en la barra de estado es la conexión en vivo con el servidor; seleccionarlo la restablece' },
        ]
      },
      {
        title: 'Barra de estado y ventanas separadas',
        items: [
          { label: 'Actividad', text: 'El centro de la barra de estado resume lo que está en curso, según lo que el rol puede leer: las aprobaciones que esperan una decisión, una copia de seguridad, una restauración o una verificación de la cadena de auditoría en curso, las intervenciones de la cola de la vista general y las ventanas separadas. Cada parte lleva a su página; cuando todo está en calma, la barra dice Nada pendiente. Se lee de nuevo cuando cambian los datos y una vez por minuto' },
          { label: 'Separar', text: 'Separar en una ventana, entre las herramientas del detalle de un certificado, una autoridad o una solicitud, la abre en una ventana sobre la página. Varias ventanas permanecen abiertas a la vez, entre páginas, hasta que se cierran o se cierra la sesión; ninguna se abre en un teléfono' },
          { label: 'Mover y redimensionar', text: 'Arrastrar la barra de título para mover una ventana, y un borde o una esquina para redimensionarla. Con el teclado, enfocar el botón de mover al inicio de la barra de título: las flechas mueven la ventana, Mayús con las flechas la redimensiona. Una ventana permanece dentro de la ventana del navegador y conserva su posición y tamaño durante la sesión' },
          { label: 'Maximizar', text: 'El botón de maximizar de la barra de título, o un doble clic en la barra, extiende la ventana sobre la página entre la barra superior y la barra de estado; maximizada, no se mueve ni se redimensiona. El mismo botón, u otro doble clic, devuelve su posición y tamaño. Cada ventana conserva su estado durante la sesión, también la ventana de comparación' },
          { label: 'Primer plano y cierre', text: 'La ventana en la que se hace clic o a la que se mueve el foco pasa al primer plano; la lista de ventanas de la barra de estado trae una de vuelta al primer plano. La cruz, o Esc mientras el foco está en la ventana, la cierra' },
        ]
      },
      {
        title: 'Primer uso',
        items: [
          { label: 'Configuración inicial', text: 'En una instancia sin ninguna CA ni certificado, los administradores ven el asistente de Configuración inicial en la vista general y en la lista de certificados: una raíz, una CA emisora, un protocolo. Mientras sus pasos no estén hechos, la lista de certificados vacía y la página Autoridades vacía ofrecen Abrir el asistente de configuración' },
          { label: 'Pasos', text: 'Cada paso abre la pantalla que lo realiza, y se marca en cuanto existe lo que crea' },
          { label: 'Más tarde y Ocultar', text: 'Más tarde pliega la tarjeta en una línea y Reanudar la vuelve a abrir; Ocultar cierra una configuración terminada, que ya no se muestra' },
        ]
      },
    ],
    tips: [
      'Los módulos fijados siguen a la cuenta en todos los navegadores y dispositivos desde los que se inicia sesión',
      'Una página fijada a la que se pierde el derecho de acceso se oculta, y vuelve si el derecho se restablece antes de cambiar los módulos fijados',
    ],
  },
}
