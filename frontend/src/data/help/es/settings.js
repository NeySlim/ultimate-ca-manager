export default {
  helpContent: {
    title: 'Configuración',
    subtitle: 'Configuración del sistema',
    overview: 'Configure todos los aspectos del sistema UCM. La configuración está organizada por categorías: general, apariencia, correo electrónico, seguridad, SSO, respaldo, auditoría, base de datos, HTTPS, actualizaciones y webhooks.',
    sections: [
      {
        title: 'Disposición de la página',
        content: 'Todas las secciones están en una sola página, cada una en su propio marco; el índice de la izquierda las lista una bajo otra (en un teléfono, la lista Ir a la sección).',
        items: [
          { label: 'Barra de guardado', text: 'Al pie de la página: Ningún cambio pendiente, con la fecha y la cuenta del último guardado de la configuración cuando se puede leer el registro de auditoría (una ejecución de renovación o un consentimiento OAuth no es un guardado); en cuanto cambia un campo, los nombres de los campos modificados (sus secciones cuando un campo no tiene etiqueta), con Deshacer los cambios (vuelve a los valores cargados) y Guardar. Guardar, o Intro en un campo, almacena cada sección modificada por su ruta habitual' },
          { label: 'Guardado con error', text: 'Un valor fuera de los límites que la página conoce (un puerto fuera de 1 a 65535, una duración, un número, un servidor obligatorio, una dirección o una URL mal formada) se marca en su campo con lo que se espera, y no se envía nada hasta corregirlo. Una sección cuyo guardado falla se marca Por corregir en el índice y nombra el error en su marco, y lo escrito se conserva. Las partes con una ruta propia (SMTP y alertas de expiración, syslog, mTLS, CT, Autorrenovación, actualizaciones automáticas, los ajustes de Autoinscripción de Windows) se guardan o fallan por separado; los demás campos van a la configuración general en una sola solicitud, de modo que cuando se rechaza, se marcan todas las secciones con un cambio de este tipo y ninguna se guarda' },
          { label: 'Acciones propias', text: 'Una prueba, una importación, una generación o una lista (proveedores SSO, webhooks, conexiones, perfiles de Windows, copias de seguridad) conserva su botón en su sección y actúa de inmediato. El resultado de una prueba (SMTP, syslog, renovación) se muestra junto a su botón; estas pruebas leen los valores guardados, así que guarde primero sus cambios' },
          { label: 'Enlaces', text: 'Un enlace a /settings?tab=<sección> (resumen, paleta, otras páginas) abre la página en esa sección' },
          { label: 'Salir', text: 'Salir de la página con cambios pendientes no pregunta nada: los cambios se conservan en esta pestaña y reaparecen, aún pendientes, al volver; recargar o cerrar la pestaña consulta antes al navegador' },
          { label: 'Historial de cambios', text: 'Bajo las secciones, los últimos guardados de la configuración tal como los registra el registro de auditoría (con read:audit)' },
        ]
      },
      {
        title: "Métricas Prometheus",
        content: "Endpoint /metrics opcional que expone contadores (certificados, CA, planificador, webhooks, ACME) en formato Prometheus.",
        items: [
          { label: "Activación", text: "Defina un token de métricas en Configuración › General; sin token, el endpoint devuelve 404 (desactivado)" },
          { label: "Autenticación", text: "Recopile con Authorization: Bearer <token>" },
          { label: "Contadores", text: "ucm_certificates, ucm_certificate_authorities, ucm_scheduler_task_*, ucm_webhook_deliveries, ucm_acme_*" },
        ]
      },
      {
        title: "Vhost ACME público",
        content: "Configuración › General: nombre de host y puerto públicos para las URL del directorio ACME detrás de un reverse proxy.",
        items: [
          { label: "Admin", text: "admin.ucm.example.com, GUI y API (mTLS según política)" },
          { label: "ACME", text: "acme.ucm.example.com, /acme/* y /acme/proxy/* (sin mTLS de cliente)" },
          { label: "TLS wildcard", text: "Use aquí un nombre de host concreto (p. ej. acme.ucm.example.com). Un SAN *.ucm.example.com en el certificado cubre TLS de los vhosts de admin y ACME; no introduzca *.ucm.example.com como vhost" },
          { label: "Antes de guardar", text: "Tenga DNS y TLS funcionando para el vhost ACME primero: los clientes que releen el directorio cambian de URL de inmediato y las renovaciones fallan si el vhost es inalcanzable" },
          { label: "ID del certificado TLS", text: "Metadatos del certificado desplegado en el vhost ACME (p. ej. wildcard)" },
        ]
      },
      {
        title: "Historial de entrega de webhooks",
        content: "Cada endpoint de webhook mantiene un registro de entrega con estado, intentos y reintento manual.",
        items: [
          { label: "Estados", text: "pending / delivered / failed, con el último código HTTP y error" },
          { label: "Reintentar", text: "Volver a encolar manualmente un evento fallido o ya entregado" },
          { label: "Asíncrono", text: "Las entregas se ejecutan desde una cola duradera con retroceso exponencial (hasta 5 intentos)" },
        ]
      },
      {
        title: "Vista del planificador",
        content: "Configuración › Planificador enumera las tareas en segundo plano con su estado y última ejecución.",
        items: [
          { label: "Tareas", text: "Comprobaciones de expiración, actualización de CRL, entrega de webhooks, copias programadas, autorrenovación, etc." },
          { label: "Ejecutar ahora", text: "Desencadenar cualquier tarea bajo demanda" },
          { label: "Visibilidad", text: "Estado en palabras (correcta, fallida, omitida), última ejecución, última duración y número de ejecuciones por tarea; en un teléfono cada tarea es una tarjeta con su botón Ejecutar ahora" },
          { label: "Inspector", text: "Una tarea se abre desde su fila en el inspector, que muestra todas las columnas de la lista, también las que una ventana estrecha pliega, y su botón Ejecutar ahora" },
          { label: 'Proceso del planificador (v2.251)', text: 'Las tareas se ejecutan en un proceso propio del planificador, que arranca con el servicio y se reinicia en pocos segundos tras un fallo o una recarga, de modo que una tarea larga no retrasa ni las solicitudes ni los workers. Ocupa unos 150 MB de memoria' },
          { label: 'Estado obsoleto (v2.251)', text: 'Cuando el proceso del planificador lleva un tiempo sin informar, la pestaña avisa de que el estado mostrado puede estar desactualizado' },
          { label: 'Tareas largas (v2.251)', text: 'Ejecutar ahora espera hasta 30 segundos el resultado. Una tarea que sigue en curso se notifica como iniciada y en ejecución, y su resultado aparece en una actualización posterior' },
        ]
      },
      {
        title: "Copias de seguridad programadas",
        content: "Copias de seguridad automáticas y cifradas de la base de datos, con cadencia configurable y retención.",
        items: [
          { label: "Cadencia", text: "Diaria / semanal / mensual, o Desactivada (no recomendado), que detiene las copias programadas" },
          { label: "Retención", text: "Las copias más antiguas que el número de días fijado (30 por defecto) se eliminan" },
          { label: "Límite de tamaño", text: "Un límite en MB para todos los archivos (0 para ninguno): los más antiguos se eliminan, cada uno auditado, hasta que el total encaje. En un solo nodo, la retención nunca elimina el archivo más reciente que coincide con su registro de validación, hasta 2 archivos sin registro de validación y el mínimo conservado; en HA, el mínimo conservado: el total puede quedar por encima del límite, y se informa de ello. Una copia manual no elimina nada. Configuración > Respaldo muestra el espacio usado" },
          { label: "Cifrado", text: "Las copias se cifran con la contraseña de copia de seguridad configurada" },
          { label: "Alta disponibilidad", text: "En HA los archivos se almacenan en PostgreSQL: cada nodo los lista con el nodo que los escribió y los descarga, y la retención se ejecuta en el líder. Se pierden con la base de datos: descargue fuera del clúster los que conserve y respalde PostgreSQL con sus propias herramientas" },
          { label: "Derivación de clave", text: "Automática (Argon2id si está disponible, PBKDF2 en modo FIPS), PBKDF2-HMAC-SHA256 o Argon2id. Los archivos escritos con Argon2id no se pueden restaurar en una instancia en modo FIPS" },
        ]
      },
      {
        title: "Copia de seguridad manual",
        items: [
          { label: "En segundo plano", text: "Crear respaldo se ejecuta en el servidor: el diálogo muestra qué parte de la base de datos se está exportando y ofrece el archivo para descargar cuando está listo. Una copia hecha en menos de 25 segundos se descarga de inmediato, como antes. Cerrar el diálogo o recargar la página no la detiene: Crear respaldo la vuelve a mostrar" },
          { label: "Cancelar", text: "Cancelar la copia de seguridad la detiene entre dos partes de la exportación: no se conserva ningún archivo y se elimina su archivo temporal" },
          { label: "Una a la vez", text: "Solo se ejecuta una copia manual a la vez en toda la instalación, clúster HA incluido: una segunda se rechaza (409) y nombra la que está en curso. Una copia que encuentra una copia programada o una restauración con el bloqueo de copias espera hasta 15 segundos y luego se rechaza (409)" },
        ]
      },
      {
        title: 'Restauración (v2.251)',
        items: [
          { label: 'Reemplazar o fusionar', text: 'Restaurar desde copia de seguridad reemplaza los datos de aquí por los del archivo y elimina lo que el archivo no contiene; la entrada de auditoría enumera lo eliminado. La API también acepta mode=merge, que añade el archivo a los datos de aquí' },
          { label: 'Informe y tamaño', text: 'El selector acepta los tamaños de archivo que acepta el servidor: lee la cabecera del archivo para aplicar el límite de su formato antes de la subida, deja al servidor un archivo que no reconoce y muestra el avance de la subida. Cuando la restauración termina con algo por hacer, un informe queda abierto hasta cerrarlo: lo que se restauró y luego una lista Por hacer con una línea por aviso (secciones no restauradas, CAs cuya CRL no se pudo firmar, secretos que hay que introducir de nuevo, vinculaciones de despliegue restablecidas a la cadena automática) y el estado del reinicio. Sin nada por hacer, la página se recarga tras dos segundos. Un archivo sin datos no restaura nada, y el informe lo dice. El informe se conserva con el trabajo en segundo plano de la restauración; la restauración misma se registra en el registro de auditoría' },
          { label: 'Bloqueo compartido', text: 'Las copias y las restauraciones comparten un único bloqueo: se rechaza una restauración (409) mientras se ejecuta una copia, y una copia manual espera a que termine una restauración en curso' },
          { label: 'Modo HA', text: 'En modo HA, una restauración desde cualquier nodo hace primero que todos los nodos rechacen las escrituras (503) y salgan de la rotación del balanceador hasta que termine; se rechaza, nombrando el nodo, cuando un nodo no confirma en 30 s. Los nodos se reinician entonces de uno en uno, y cada uno sirve el estado restaurado una vez reiniciado' },
          { label: 'Límite de subida', text: 'Un archivo creado desde la 3.0 se restaura por fragmentos y no tiene límite de tamaño salvo que BACKUP_MAX_ARCHIVE_MB fije uno. Un archivo anterior se acepta hasta BACKUP_MAX_UPLOAD_MB (512 MB por defecto). Ambos se definen en el entorno del servidor y un rechazo nombra su ajuste. Un reverse proxy delante de UCM mantiene su propio límite de cuerpo' },
          { label: 'Qué contiene un archivo', text: 'Los archivos incluyen los pedidos del cliente ACME, las solicitudes de aprobación y las solicitudes de recuperación de claves. Restaurar un archivo escrito antes de esta versión deja esas filas de aquí como están' },
          { label: 'Mismos nombres', text: 'Un proveedor DNS, una cuenta de CA ACME o un webhook cuyo nombre ya tiene otra fila aquí se restaura como «nombre (2)», y el resultado de la restauración que devuelve la API lo enumera' },
          { label: 'Ajustes que nombran una fila', text: 'Las CA emisoras de SCEP y ACME, los respondedores OCSP y ajustes similares siguen las filas archivadas. Al restaurar un archivo antiguo en otra instalación, quedan vacíos y hay que elegirlos de nuevo' },
          { label: 'Restauración en segundo plano', text: 'La restauración se ejecuta en segundo plano, en el proceso del planificador. Pasados 25 segundos el diálogo muestra su avance y un botón Cancelar la restauración, que no restaura nada hasta que la restauración se confirma. Mientras se ejecuta, toda escritura se rechaza (503), en un solo nodo como en HA, y se sirven lecturas, OCSP y CRL. En un solo nodo con SQLite, mientras la restauración escribe las filas del archivo, su transacción retiene la base de datos: solo responden entonces el avance, el botón Cancelar y las comprobaciones de estado, cualquier otra solicitud responde 503 con Retry-After y OCSP responde tryLater. Termina cerrando todas las sesiones: el diálogo pide volver a iniciar sesión y el informe se muestra tras el inicio de sesión. Un inicio de sesión rechazado entretanto (503; en HA hasta que ese nodo se haya reiniciado) lo reintenta la propia página de inicio de sesión, tras la espera que pide el servidor, y un botón Reintentar ahora lo intenta de inmediato. Un inicio de sesión con llave de seguridad nunca se reintenta solo: Reintentar ahora vuelve a pedir la llave. Nada más se ejecuta junto a una restauración: una copia o una verificación iniciada entretanto se rechaza (409). Una restauración que se confirmó pero no pudo terminar lo dice en un mensaje que permanece hasta cerrarlo: reinicie la aplicación antes de usarla' },
        ]
      },
      {
        title: "Actualizaciones automáticas (v2.215)",
        content: 'Configuración › Actualizaciones: una comprobación diaria en segundo plano de nuevas versiones y una instalación desatendida opcional.',
        items: [
          { label: "Canal", text: "Stable sigue solo las versiones finales; Release candidates acepta además únicamente versiones rcN, nunca alfa/beta" },
          { label: 'Notificación', text: 'Una versión recién disponible dispara el evento webhook/correo system.update_available, una vez por versión' },
          { label: "Versiones principales", text: "Las actualizaciones se mantienen dentro de la versión principal instalada, en ambos canales. La última versión final de la siguiente versión principal (instalada + 1) se muestra aparte con su propio botón Actualizar y una confirmación; las actualizaciones automáticas nunca la instalan, y system.update_available se emite una vez por versión principal ofrecida, con major_upgrade activado" },
          { label: 'Instalación automática', text: 'Desactivada por defecto. Cuando está activada, UCM descarga, verifica e instala la actualización a la hora elegida y luego se reinicia, solo instalaciones DEB/RPM' },
          { label: 'Suma de comprobación', text: 'Una instalación desatendida requiere el SHA256 publicado de la versión para la verificación; una instalación manual también verifica siempre que se publique una suma de comprobación' },
          { label: 'Docker', text: 'Los contenedores no pueden actualizarse a sí mismos, la comprobación y la notificación siguen funcionando; descargue la nueva imagen para actualizar' },
          { label: 'Modo HA', text: 'En modo HA con DEB/RPM, Instalar actualización y la instalación automática actualizan los nodos de uno en uno; el siguiente nodo arranca cuando el anterior ha vuelto con la nueva versión. La pantalla muestra los nodos terminados, el nodo en curso y el nodo donde se detuvo con el motivo; Reanudar continúa desde él. Docker y Kubernetes lo dejan al orquestador' },
          { label: 'Ventana tras actualizar', text: 'Opcional (v2.217): muestra una vez las notas de la versión tras instalar una actualización, por usuario. Desactivado por defecto' },
        ]
      },
      {
        title: "HSTS (Strict Transport Security)",
        content: "Política HSTS configurable por el operador para que las instancias con certificados autofirmados durante la configuración inicial puedan excluirse por completo.",
        items: [
          { label: "Predeterminado", text: "HSTS activado, includeSubDomains, max-age 1 año (compatible con versiones anteriores)" },
          { label: "Desactivar", text: "Desactivar para instancias con certificados autofirmados durante la configuración inicial (evita el bloqueo del navegador)" },
          { label: "Variable de entorno", text: "UCM_HSTS_ENABLED, UCM_HSTS_INCLUDE_SUBDOMAINS, UCM_HSTS_MAX_AGE en /etc/ucm/ucm.env prevalecen sobre el ajuste de la base de datos" },
          { label: "Subdominios", text: "Quitar includeSubDomains cuando los subdominios alojen servicios separados con sus propios certificados" },
        ]
      },
      {
        title: 'Categorías',
        items: [
          { label: 'General', text: 'Nombre de host de syslog (enviado como HOSTNAME en los mensajes syslog reenviados), URL base y valores predeterminados del sistema' },
          { label: 'Apariencia', text: 'Selección de tema (claro/oscuro/sistema), color de acento, modo escritorio' },
          { label: 'SMTP', text: 'Servidor SMTP, credenciales, editor de plantillas de correo y notificaciones de alerta de expiración. Admite OAuth2 (XOAUTH2) para Gmail, Outlook.com y Microsoft 365 además de la autenticación heredada por contraseña' },
          { label: 'Seguridad', text: 'Política de contraseñas, duración de sesión, lista de acceso de administración, mTLS, cifrado de claves privadas; el tiempo de inactividad y el bloqueo de cuenta están en General' },
          { label: 'SSO', text: 'Integración de inicio de sesión único con SAML 2.0, OAuth2/OIDC y LDAP' },
          { label: 'Respaldo', text: 'Copias de seguridad manuales y programadas de la base de datos' },
          { label: 'Auditoría', text: 'Retención de registros, reenvío a syslog, verificación de integridad' },
          { label: 'Base de datos', text: 'Backend activo (SQLite o PostgreSQL nativo), tamaño, número de tablas, interfaz de migración bidireccional con comprobaciones de seguridad' },
          { label: 'Esquema de PostgreSQL (v2.251)', text: 'Se admite una URL de PostgreSQL cuyo search_path nombra un esquema distinto de public: la verificación de integridad cuenta las tablas de ese esquema y una migración hacia él realinea sus secuencias' },
          { label: 'HTTPS', text: 'Certificado TLS para la interfaz web de UCM. El certificado aplicado se recuerda y se vuelve a aplicar cuando se renueva (v2.217); el certificado vinculado se muestra con un botón para desvincularlo y dejar de seguir las renovaciones (v2.218). Una renovación por protocolo cuya clave UCM no posee deja HTTPS en el certificado anterior y lo indica, hasta que se importe la clave del certificado renovado' },
          { label: 'Actualizaciones', text: 'Buscar nuevas versiones, ver registro de cambios, comprobación diaria programada con instalación desatendida opcional (DEB/RPM)' },
          { label: 'Webhooks', text: 'Webhooks HTTP para eventos de certificados (emisión, revocación, expiración): se permiten URL internas de la LAN; las IP de metadatos de la nube están bloqueadas. Autenticación saliente opcional: Bearer, Basic, API key o encabezado personalizado' },
          { label: 'Nombres de webhook únicos (v2.251)', text: 'Se rechaza (409) un nombre de webhook ya en uso, al crear y al renombrar. La actualización renombró los duplicados anteriores como «nombre (2)», «nombre (3)», empezando por el más antiguo' },
          { label: 'Despliegue', text: 'Los destinos de despliegue son conexiones SSH/SFTP reutilizables, o una solicitud a una API HTTP (v2.252); cada despliegue de certificado o de CRL define sus propias rutas y su comando de recarga opcional (solo administradores, v2.215)' },
          { label: 'Active Directory', text: 'Conexión propia de UCM a AD/LDAP para búsquedas relacionadas con certificados (resolución de entidades de seguridad Kerberos, sujetos derivados de AD)' },
          { label: 'Autoinscripción de Windows', text: 'Inscripción nativa de Windows MS-XCEP/MS-WSTEP: descubrimiento de directivas, emisión de certificados y vinculación Kerberos/SPNEGO' },
          { label: 'Acerca de', text: 'Información del sistema, Enlaces y recursos y Apoyar UCM enlazan a Ko-fi (los administradores ven además una tarjeta de Ko-fi descartable una vez por versión de UCM). Con admin:system, Comprobar la preparación para FIPS enumera lo que el modo FIPS rechazaría en esta instancia, con un remedio para cada caso, y no modifica nada' },
          { label: 'Perfiles de cumplimiento', text: 'En Acerca de, con admin:system: Comprobar el perfil enumera lo que ANSSI, BSI o EU ACM (reglas alineadas con un texto de referencia) rechazaría o desaconsejaría en esta instancia, sin modificar nada. Con admin:settings, Perfil predeterminado para las CA nuevas define el perfil que recibe una CA cuando no se elige ninguno; las CA existentes no se modifican' },
        ]
      },
      {
        title: 'Hooks de despliegue (v2.215)',
        content: 'Configuración › Despliegue (solo administradores): conexiones SSH/SFTP reutilizables, o solicitudes a una API HTTP, para los despliegues de certificados y de CRL. Las rutas y el comando de recarga opcional se configuran en cada despliegue SSH.',
        items: [
          { label: 'Destino', text: 'Host, puerto, usuario SSH. UCM genera una clave ed25519 (instale la clave pública mostrada en el destino) o acepta una clave privada importada, almacenada cifrada' },
          { label: 'Destino de API HTTP (v2.252)', text: "URL, método (POST, PUT, PATCH), cabeceras de la solicitud almacenadas cifradas y que no se vuelven a mostrar, y una plantilla de cuerpo con {{cert_pem}}, {{fullchain_pem}}, {{cn}}, {{serial}}... más los filtros |json, |jsonstr, |b64 y |urlencode. Un cuerpo JSON se valida al guardar. La clave privada ({{key_pem}}) solo sale con la aceptación explícita del destino y una URL https; el certificado TLS siempre se verifica, contra un ancla de confianza pegada si el equipo es autofirmado. Se rechazan las redirecciones y se bloquean las direcciones de metadatos de la nube y de loopback. Solo certificados: las CRL permanecen en destinos SSH" },
          { label: 'Clave de host', text: 'Se fija en la primera conexión exitosa (trust-on-first-use); cualquier cambio posterior hace fallar la conexión. Cambiar el host vuelve a fijarla' },
          { label: 'Comando de recarga', text: 'Un comando opcional, configurado en cada vinculación de certificado o de CRL y ejecutado tras un envío exitoso (p. ej. systemctl reload nginx): exit 0 = éxito, sin plantillas' },
          { label: 'Vinculaciones', text: 'Los certificados se asocian desde la vista de detalle del certificado; las CRL, desde CRL y OCSP. Cada vinculación tiene sus propias rutas, opciones de archivo y comando de recarga' },
          { label: 'Entrega', text: 'Los envíos se ejecutan de forma asíncrona mediante una cola duradera con reintentos y backoff; estado por entrega, despliegue manual inmediato y reintento, traza de auditoría completa' },
          { label: 'Privilegio mínimo', text: 'Use una cuenta SSH dedicada en cada destino: acceso de escritura a las rutas de los certificados y permiso para recargar el servicio, nada más' },
        ]
      },
      {
        title: 'SMTP OAuth2 (XOAUTH2)',
        content: 'Autenticación OAuth2 moderna para el correo saliente, que sustituye los flujos heredados de contraseña de aplicación que Microsoft y Google están dejando de admitir:',
        items: [
          { label: 'Gmail', text: 'Configurar un cliente OAuth2 de Google Cloud con el scope https://mail.google.com/' },
          { label: 'Microsoft 365 / Outlook.com', text: 'Registrar una app de Azure AD con el permiso delegado SMTP.Send' },
          { label: 'Refresh tokens', text: 'UCM almacena el refresh token y renueva los access tokens automáticamente antes de cada envío' },
          { label: 'Alternativa', text: 'La autenticación por contraseña sigue admitida cuando OAuth2 no está configurado' },
        ]
      },
      {
        title: 'Conector de Active Directory',
        content: 'Conexión LDAP propia de UCM a Active Directory, independiente de cualquier proveedor LDAP configurado en SSO: ese sirve para iniciar sesión en UCM, este para las consultas de AD relacionadas con certificados.',
        items: [
          { label: 'Propósito', text: 'Resuelve una entidad de seguridad de máquina o usuario Kerberos a su objeto de AD, para que UCM pueda derivar un sujeto/SAN de certificado, tal como lo haría una CA de Windows real' },
          { label: 'Conectores', text: 'Uno por directorio (bosque o dominio), listado con su realm, el SID de dominio leído y su estado. Un conector que usan perfiles de inscripción de Windows no se puede eliminar, y el rechazo los enumera' },
          { label: 'Campos', text: 'Nombre, controladores de dominio (uno por fila, cada uno por su propio nombre de host, probados en orden con conmutación por error), puerto, LDAPS con verificación de CA opcional, Base DN, Bind DN y contraseña (ambos obligatorios mientras el conector esté activado)' },
          { label: 'Conector desactivado', text: 'Un conector desactivado no consulta nada, pero su base DN sigue nombrando el realm del perfil predeterminado como último recurso, cuando ningún conector activado, SPN o keytab lo hace' },
          { label: 'Probar conexión', text: 'Verificar la conectividad y las credenciales antes de guardar; la prueba también lee el SID del dominio' },
          { label: 'Comprobación de estado', text: 'Cada controlador de dominio se sondea con un bind real según el Intervalo de comprobación de estado; uno inalcanzable se omite en el momento de la inscripción hasta que se recupere. El veredicto se muestra en la fila de ajustes y junto a cada DC' },
        ]
      },
      {
        title: 'Autoinscripción de Windows (XCEP/WSTEP)',
        content: 'Inscripción de certificados nativa de Windows mediante el descubrimiento de directivas MS-XCEP y la emisión MS-WSTEP: admite la inscripción manual con MMC/certreq y la autoinscripción GPO desatendida.',
        items: [
          { label: 'Perfiles', text: 'Un perfil por realm de Active Directory, enrutado por el realm de la entidad de seguridad Kerberos del cliente: su propia CA emisora y de directiva, subconjunto de plantillas, conector de AD y keytab; las cuentas UsernamePassword pertenecen al perfil predeterminado. La lista está paginada y filtrada por el servidor (nombre o realm, CA, estado: completo, falta el keytab, conector con fallos, desactivado)' },
          { label: 'Realm', text: 'En mayúsculas exactamente como lo escribe el KDC (CORP.EXAMPLE): un KDC compara los realms carácter por carácter. El perfil predeterminado sin realm rechaza Kerberos hasta que se defina uno. Un perfil desactivado rechaza las máquinas de su realm; sus claves permanecen en el keytab servido para que el rechazo se audite por realm' },
          { label: 'XCEP', text: 'Permite a los clientes Windows descubrir las plantillas de certificado disponibles antes de inscribirse' },
          { label: 'WSTEP', text: 'Gestiona la solicitud y renovación del certificado una vez descubierta la directiva' },
          { label: 'Kerberos/SPNEGO', text: 'Vincula los puntos de conexión autenticados por Kerberos usados para la autoinscripción GPO silenciosa (un SPN compartido por todos los perfiles y un keytab por perfil, del controlador de dominio de su realm; el formulario lista las entradas de un archivo elegido por realm y señala un realm que no es el del perfil)' },
          { label: 'Lista de verificación de configuración', text: 'El formulario de cada perfil lista lo que a ese perfil aún le falta: realm, CA emisora, keytab, un conector alcanzable, una plantilla que permita la autoinscripción, el perfil activado' },
          { label: 'URL de directiva', text: 'Las mismas para todos los perfiles: el enrutamiento es por realm, no por URL' },
          { label: 'Sujetos derivados de AD', text: 'Las plantillas pueden optar por derivar su sujeto/SAN de Active Directory (mediante el conector de AD) para la inscripción desatendida' },
          { label: 'Plantillas ML-DSA (v2.248)', text: 'Se anuncian por el OID de su algoritmo de clave con el Microsoft Software Key Storage Provider, aún no probadas con un cliente Windows real, y ocultas en modo FIPS cuando el módulo FIPS no aprueba ML-DSA. La renovación con certificado no puede usar un certificado ML-DSA (XML-DSig no tiene firma ML-DSA): inscriba uno nuevo' },
          { label: 'Plantillas ECDSA (v2.251)', text: 'Se anuncian en el esquema de directiva 3 con su curva (ECDSA_P256, ECDSA_P384, ECDSA_P521) como clave de firma y un hash de solicitud, el más fuerte entre el resumen de la plantilla y el que corresponde a la curva. Las plantillas RSA fuera del modo FIPS siguen en el esquema 2, donde Windows firma su solicitud CMC con SHA-1, que UCM acepta (un PKCS#10 SHA-1 simple sigue rechazándose)' },
          { label: 'Plantilla nombrada en la solicitud (v2.252)', text: 'Cada directiva anuncia su extensión de plantilla (szOID_CERTIFICATE_TEMPLATE), que Windows copia en su solicitud, de modo que se emite un certificado con la plantilla elegida en el cliente aunque otra tenga los mismos EKU. Una solicitud que no nombra ninguna plantilla se asocia por sus EKU. Una plantilla cuyos EKU nunca se emiten a un inscrito, como OCSP Signing, no se anuncia, y se rechaza una solicitud para ella' },
          { label: 'Plantilla y clave (v2.251)', text: 'La clave de la solicitud debe ajustarse a la plantilla con la que se emite: la misma curva o el mismo conjunto ML-DSA, o una clave RSA al menos igual de larga, de modo que una solicitud P-384 ya no se emite con una plantilla P-256 que comparta su EKU. Se acepta el sobre de solicitud que Windows firma con una clave ECDSA' },
          { label: 'Renovación desde Windows (v2.248)', text: 'certreq ... Renew se autentica con el certificado que se renueva como certificado de cliente TLS: requiere mTLS activado y la CA de WSTEP, o una de sus ancestras, de confianza. Desde la 3.0 solo un certificado emitido mediante la inscripción de Windows se renueva así: uno firmado en la interfaz se rechaza y debe reemitirse mediante la inscripción de Windows. Una renovación conserva la plantilla y los EKU del certificado que renueva, y su SubjectAltName cuando la CSR no trae ninguno (v2.252)' },
          { label: 'Renovación por certificado (3.0)', text: 'La sirve el perfil que registra el certificado (un certificado WSTEP de la 2.x: el perfil predeterminado), bajo su CA emisora, y se rechaza cuando ese perfil se eliminó o está desactivado; cada rechazo se audita con el perfil y el motivo. Solo se vuelve a comprobar el SID, por el conector del perfil: un equipo retirado del grupo sigue renovando hasta que se revoque su certificado. Por TLS requiere que la CA emisora del perfil sea la CA mTLS o esté bajo ella; los demás perfiles renuevan por Kerberos, donde sirve el perfil del realm y el nuevo certificado lo registra' },
          { label: 'Tipo de certificado', text: 'Sin Server Auth, una plantilla con Email Protection o EFS emite un certificado S/MIME, una con Client Auth o Smartcard Logon uno de cliente: una solicitud de usuario CN=jdoe sin SAN no obtiene ningún nombre DNS de su CN. Una solicitud sin Key Usage recibe el Key Usage que configura la plantilla, o si no el del tipo de plantilla: Digital Signature, Key Encipherment y Non Repudiation para S/MIME o EFS, Digital Signature y Key Encipherment para Smartcard Logon, solo Digital Signature para Client Auth. Cualquier otra plantilla, o ninguna, emite uno de servidor' },
          { label: 'Kerberos en Docker (v2.251)', text: 'Las imágenes Docker incluyen el backend Kerberos de pyspnego, por lo que la vinculación Kerberos funciona en un contenedor igual que en las instalaciones DEB y RPM' },
        ]
      },
      {
        title: 'Autorrenovación',
        items: [
          { label: 'Fuentes', text: 'El planificador renueva los certificados cuya clave privada posee el servidor: por defecto los emitidos desde el formulario o desde una solicitud firmada («manual»), y las inscripciones SCEP, ACME y EST con clave generada por el servidor. Los dispositivos que poseen su propia clave se renuevan a través de su protocolo' },
          { label: 'En espera de aprobación', text: 'Un certificado cuya renovación está en cola de aprobación se deja a esa decisión, siempre que pueda llegar antes de que expire el certificado' },
          { label: 'Renovado entretanto', text: 'Un certificado que un operador renovó durante el lote no se renueva una segunda vez; uno eliminado durante el lote se omite' },
          { label: 'Certificados de corta duración', text: 'La renovación nunca empieza antes del último tercio de la vigencia de un certificado: uno de 27 días se renueva cuando le quedan 9, no desde su emisión' },
          { label: 'Ejecutar ahora', text: 'Ejecuta una pasada de renovación de inmediato e informa de los certificados por expirar que dejó sin tocar, contados por motivo: aún no en el último tercio de su vigencia, clave privada no en poder del servidor, fuente no seleccionada' },
          { label: 'Resumen de firma (v2.251)', text: 'Una renovación conserva el resumen del certificado original mientras sea al menos el que corresponde a la clave de la CA y las políticas lo permitan; si no, sigue la regla de emisión: bajo una CA P-384 o P-521, un original SHA-256 se renueva con SHA-384 o SHA-512' },
        ]
      },
    ],
    tips: [
      'Use la barra de estado inferior para comprobar que el servicio responde',
      'Pruebe la configuración SMTP antes de confiar en las notificaciones por correo',
      'Personalice la plantilla de correo con su marca mediante el editor HTML/texto integrado',
      'Programe copias de seguridad automáticas en los entornos de producción',
      'El cambio SQLite ↔ PostgreSQL es bidireccional: la interfaz ejecuta comprobaciones de seguridad (controlador cargado, destino alcanzable, destino vacío) antes de migrar',
    ],
    warnings: [
      'Cambiar el certificado HTTPS recarga el listener TLS sin reiniciar, también en un contenedor (HA: reinicio progresivo)',
      'Modificar la configuración de seguridad puede bloquear a los usuarios: verifique el acceso antes de guardar',
    ],
  },
  helpGuides: {
    title: 'Configuración',
    content: `
## Descripción general

Configuración de todo el sistema organizada en pestañas. Los cambios surten efecto inmediatamente a menos que se indique lo contrario.

## General

- **Nombre de host de syslog**: Se envía como HOSTNAME en los mensajes syslog reenviados; vacío, se usa el nombre de host de la máquina
- **URL base**: URL HTTPS canónica de la interfaz de administración y la API; los demás nombres de host e IP redirigen a ella. Los correos de restablecimiento de contraseña enlazan a ella, o si no al FQDN del servidor (\`UCM_FQDN\`); con ninguno de los dos, la página de inicio de sesión oculta Olvidé mi contraseña y se rechaza el restablecimiento
- **URL base de protocolo**: URL base escrita en las direcciones CDP y OCSP; use http:// para evitar bucles de verificación TLS, o déjela vacía para usar la URL base
- **Puerto HTTP de protocolo**: Puerto HTTP plano que sirve CDP y OCSP, y SCEP cuando su opción Servir en HTTP plano está activada; 0 lo desactiva, un cambio requiere reinicio
- **Vhost ACME público**: Nombre de host concreto en las URL del directorio ACME (p. ej. \`acme.ucm.example.com\`: no \`*.ucm.example.com\`). Un **SAN de certificado TLS** wildcard \`*.ucm.example.com\` cubre tanto \`admin.ucm.example.com\` como \`acme.ucm.example.com\`. Configure DNS y TLS para el vhost ACME **antes** de guardar: los clientes que relean el directorio cambian de URL al instante.

## Apariencia

- **Tema**: Claro, Oscuro o Sistema (sigue la preferencia del SO)
- **Color de acento**: Color principal usado para botones, enlaces y resaltados
- **Forzar modo escritorio**: Desactivar el diseño responsivo para móviles

## SMTP

Configure SMTP para notificaciones por correo (alertas de expiración, invitaciones de usuario):
- **Host SMTP** y **Puerto**
- **Nombre de usuario** y **Contraseña**
- **Cifrado**: Ninguno, STARTTLS o SSL/TLS
- **Dirección de remitente**: Dirección de correo del remitente
- **Tipo de contenido**: HTML, texto plano o ambos
- **Destinatarios de alertas**: Una o varias direcciones separadas por comas; una dirección no válida se nombra bajo el campo y no se conserva

Haga clic en **Probar** para enviar un correo de prueba y verificar la configuración.

### Editor de plantillas de correo

Haga clic en **Editar plantilla** para abrir el editor de plantillas, un diálogo amplio con el código fuente junto a su vista previa en vivo (solo en pantalla ancha):
- **HTML**: Edite la plantilla HTML del correo; la vista previa de la derecha la sigue mientras escribe
- **Texto plano**: Edite la versión de texto plano para clientes de correo que no soportan HTML
- Las variables del formato elegido se listan sobre el código fuente: \`{{title}}\`, \`{{content}}\`, \`{{datetime}}\`, \`{{instance_url}}\`, más \`{{logo}}\` y \`{{title_color}}\` en HTML
- **Restablecer a predeterminado**, mostrado para una plantilla personalizada, restaura tras una confirmación la plantilla incorporada con la marca UCM
- **Guardar** conserva ambas versiones; **Cerrar** o Escape sale sin guardar

### Alertas de expiración

Cuando SMTP está configurado, active alertas automáticas de expiración de certificados:
- Active/desactive las alertas
- Seleccione umbrales de advertencia (90d, 60d, 30d, 14d, 7d, 3d, 1d)
- Ejecute **Verificar ahora** para activar un escaneo inmediato
- **Omitir los certificados emitidos por ACME**: deja fuera los certificados emitidos por el servidor ACME de UCM, que sus clientes renuevan; desactivado por defecto

## Seguridad

### Política de contraseñas
- Longitud mínima (6-32 caracteres)
- Requerir mayúsculas, números, caracteres especiales

### Gestión de sesiones
- Duración de sesión (horas, sea cual sea la actividad); el tiempo de inactividad está en General

### Bloqueo de cuenta
- Máximo de intentos de inicio de sesión y duración del bloqueo, en General: bloquean la cuenta, no la dirección IP

### Lista de acceso de administración
Limita la interfaz web y la API de gestión a las direcciones IP y redes CIDR indicadas; los protocolos PKI siguen siendo accesibles desde cualquier lugar. Consulte la guía de Configuración de seguridad.

### Aplicación de 2FA
Requerir que todos los usuarios activen la autenticación de dos factores.

### Cifrado de claves privadas
Cifre todas las claves privadas almacenadas en la base de datos con AES-128 (Fernet, con HMAC-SHA256), protegidas por un archivo de clave maestra. La sección muestra el estado del cifrado y los contadores de claves **cifradas / sin cifrar**. Dos variables de entorno opcionales hacen que la ausencia de claves sea fatal en el arranque: \`UCM_REQUIRE_DB_ENCRYPTION_KEY\` (cifrado de secretos de integración) y \`UCM_REQUIRE_KEY_ENCRYPTION\` (cifrado de claves privadas).
Una instalación nueva crea la clave maestra en su primer arranque (en un contenedor, solo cuando \`/etc/ucm\` es un volumen propio); la sección Seguridad de Configuración muestra el estado del cifrado, y el Resumen muestra un banner mientras no se haya cargado ninguna clave.

> 💡 Las configuraciones sensibles de seguridad (sesión, bloqueo, HSTS, URL pública, política de contraseñas) requieren el permiso **admin:settings**: los campos están bloqueados para los operadores.

> ⚠ Se rechaza una lista que no incluya su propia dirección. Si pierde el acceso de todos modos, defina \`UCM_ADMIN_ALLOWLIST_DISABLE=1\` y reinicie UCM.

## SSO (Single Sign-On)

### SAML 2.0
- Proporcione a su IDP la **URL de metadatos SP**: \`/api/v2/sso/saml/metadata\`
- O configure manualmente: cargue/enlace el XML de metadatos del IDP, configure Entity ID y URL ACS
- Mapee atributos del IDP a campos de usuario de UCM (nombre de usuario, correo, rol)

### OAuth2 / OIDC
- URL de autorización y URL de token
- Client ID y Client Secret
- URL de información del usuario (para obtener atributos)
- Scopes (openid, profile, email)
- Crear usuarios automáticamente en el primer inicio de sesión SSO

### LDAP
- Nombre de host del servidor, puerto (389/636), opción SSL
- Bind DN y contraseña (cuenta de servicio)
- Base DN y filtro de usuario
- Mapeo de atributos (nombre de usuario, correo, nombre completo)

> 💡 Siempre mantenga una cuenta de administrador local como respaldo en caso de que SSO falle.

## Respaldo

### Respaldo manual
Haga clic en **Crear respaldo** para generar una instantánea de la base de datos. Los respaldos incluyen los certificados, CAs, claves y configuración; el registro de auditoría y otras tablas de historial no se incluyen.

Un respaldo manual se ejecuta en el servidor: el diálogo muestra su avance, permite cancelarlo (no se conserva ningún archivo) y ofrece el archivo para descargar cuando está listo; cerrar el diálogo o recargar la página no lo detiene. Solo se ejecuta un respaldo manual a la vez en toda la instalación.

### Respaldo programado
Configure copias de seguridad automáticas:
- Frecuencia (diaria, semanal, mensual, o Desactivada, no recomendado, que detiene los respaldos programados)
- Retención en días: los respaldos más antiguos se eliminan (30 por defecto)
- **Derivación de clave**: Automática (Argon2id si está disponible, PBKDF2 en modo FIPS), PBKDF2-HMAC-SHA256 o Argon2id. Los archivos escritos con Argon2id no se pueden restaurar en una instancia en modo FIPS

### Restaurar
Suba un archivo de respaldo para restaurar UCM a un estado anterior.

- Las copias y las restauraciones comparten un único bloqueo: se rechaza una restauración (409) mientras se ejecuta una copia, y una copia manual espera a que termine una restauración en curso
- En modo HA, una restauración desde cualquier nodo hace primero que todos los nodos rechacen las escrituras (503) y salgan de la rotación del balanceador hasta que termine; se rechaza, nombrando el nodo, cuando un nodo no confirma en 30 s. Los nodos se reinician entonces de uno en uno, y cada uno sirve el estado restaurado una vez reiniciado
- Un archivo creado desde la 3.0 se restaura por fragmentos, sin límite de tamaño salvo que \`BACKUP_MAX_ARCHIVE_MB\` fije uno; un archivo anterior se acepta hasta \`BACKUP_MAX_UPLOAD_MB\` (512 MB por defecto). Ambos se definen en el entorno del servidor; un reverse proxy delante de UCM mantiene su propio límite de cuerpo
- La restauración se ejecuta en segundo plano: pasados 25 segundos su diálogo la sigue y puede cancelarla hasta que se confirma; entretanto toda escritura se rechaza (503), también en un solo nodo, y el informe se muestra tras el inicio de sesión que pide su final
- Los archivos incluyen los pedidos del cliente ACME, las solicitudes de aprobación y las solicitudes de recuperación de claves (v2.251)
- Un proveedor DNS, una cuenta de CA ACME o un webhook cuyo nombre ya tiene otra fila aquí se restaura como \`nombre (2)\`
- La API también acepta \`mode=merge\`, que añade el archivo a los datos de aquí en lugar de reemplazarlos

> ⚠ Restaurar un respaldo reemplaza TODOS los datos actuales.

## Auditoría

- **Retención de registros**: Limpieza automática de registros antiguos tras N días
- **Reenvío a syslog**: Enviar eventos a un servidor syslog remoto por TLS (RFC 5425), TCP o UDP
- **Verificación de integridad**: Comprueba la cadena de hashes que enlaza cada entrada de auditoría; la cadena siempre está activa, no hay nada que activar

## Base de datos

UCM admite dos backends de base de datos:

- **SQLite** (predeterminado): basado en archivo, sin configuración, ideal para un solo nodo
- **PostgreSQL 13+**: recomendado para HA, varias instancias, o cuando ya opera un clúster PG gestionado

El backend activo se selecciona con la variable de entorno \`DATABASE_URL\`. Sin definir, UCM usa SQLite en \`DATA_DIR/ucm.db\`.

### Panel de estado
- Backend activo (sqlite / postgresql) y la versión de su motor
- Tamaño de la base de datos y número de tablas

### Probar conexión
Valide una \`DATABASE_URL\` (p. ej. \`postgresql://user:pass@host:5432/ucm\`) antes de cambiar. La prueba abre una conexión real e informa de cualquier error. Se rechazan los servidores PostgreSQL anteriores a la 13: UCM requiere PostgreSQL 13 o posterior.

### Cambiar de backend
Guarda \`DATABASE_URL\` en \`/etc/ucm/ucm.env\` (DEB/RPM) y reinicia UCM. Solo se copian al nuevo backend las tablas de cuentas, roles, SSO y MFA, de modo que aún pueda iniciar sesión; use **Migrar** primero si quiere conservar sus demás datos.

### Migrar datos
Copia todas las filas del backend actual al de destino. Funciona en ambos sentidos (SQLite ↔ PostgreSQL):

1. Se hace una copia de la base de datos de origen en \`/opt/ucm/data/backups/db_migration/\`
2. El esquema se crea en el destino mediante SQLAlchemy
3. Las comprobaciones de claves foráneas se desactivan durante la carga masiva
4. Las columnas se asocian por nombre; solo se descartan las columnas heredadas conocidas, y cualquier otra columna que falte en el destino rechaza la migración
5. Las secuencias de PostgreSQL se restablecen tras la carga
6. El servicio se reinicia automáticamente (DEB/RPM): en Docker, defina \`DATABASE_URL\` en su archivo compose y reinicie el contenedor manualmente

**Comprobaciones de seguridad (fallo rápido, origen intacto):**
- El destino debe estar vacío. Si alguna de sus tablas ya contiene filas, la migración se rechaza con HTTP 409 y una indicación de limpieza:
  - PostgreSQL: \`psql ... -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'\`
  - PostgreSQL en un esquema distinto de \`public\` (un \`search_path\` en la URL): la indicación nombra ese esquema, cuyas secuencias realinea la migración (v2.251)
  - SQLite: elimine el archivo \`.db\` de destino
- Si la migración falla a medias, el origen queda intacto y el mensaje de error apunta a la copia del origen. Restablezca el destino antes de reintentar.

> ⚠ Haga siempre una copia de seguridad completa de UCM (Configuración → Respaldo) antes de migrar entre backends.

## HTTPS

Administre el certificado TLS usado por la interfaz web de UCM:
- Ver los detalles del certificado actual
- Importar un certificado nuevo (PEM o PKCS#12)
- Generar un certificado autofirmado
- Cuando el certificado vinculado se renueva mediante un protocolo sin que su clave llegue a UCM, la página lo indica: HTTPS sigue sirviendo el certificado anterior hasta que se importe la clave del renovado, lo que lo aplica

- Aplicar, regenerar o renovar el certificado recarga el listener TLS sin detener el servicio, también en un contenedor (HA: reinicio progresivo de los nodos)
- *Renovado, aún no servido* significa que el listener presenta todavía otro certificado distinto del que está en disco: el registro del servicio dice por qué falló la recarga

## Actualizaciones

- Buscar nuevas versiones de UCM en las versiones de GitHub
- Ver el registro de cambios de las actualizaciones disponibles
- Versión actual e información de compilación
- **Actualización automática**: en instalaciones compatibles (DEB/RPM), haga clic en **Instalar actualización** para descargar e instalar la última versión automáticamente
- **Modo HA**: con DEB/RPM, **Instalar actualización** y la instalación automática actualizan los nodos de uno en uno, y la pantalla sigue la actualización progresiva (nodos terminados, nodo en curso, paquete de cada nodo, nodo donde se detuvo y por qué, **Reanudar**)
- **Canal de actualización**: stable, preliminar (release candidates) o dev

## Webhooks

Los webhooks se muestran en una tabla que se busca por nombre, dirección o evento, se ordena por cualquier columna y se pagina a partir de diez webhooks.

Configure webhooks HTTP para notificar a sistemas externos de eventos:

### Eventos admitidos
- Certificado emitido, revocado, renovado, por expirar, expirado, importado, eliminado
- CA creada, actualizada, eliminada
- CSR enviada, aprobada, rechazada
- Plantilla creada, actualizada
- Comprobación previa ACME, renovación fallida, revocación fallida
- Actualización disponible, iniciada, instalada, fallida

Las importaciones de certificados y los cambios de plantillas hechos desde la interfaz web no emiten su evento.

### Autenticación

Autenticación saliente opcional (todas se aplican además de la firma HMAC opcional):

- **Ninguna**: Sin cabecera de autenticación (webhooks públicos)
- **Bearer**: Authorization: Bearer {token}
- **Basic**: Authorization: Basic base64(usuario:contraseña)
- **API Key**: Cabecera personalizada (p. ej. X-Api-Key: {token})
- **Personalizada**: Authorization: {esquema} {token} (p. ej. auth-key VALOR)

Los tokens se almacenan cifrados y nunca se devuelven en la interfaz.

### Crear un webhook
1. Haga clic en **Añadir webhook**
2. Introduzca la **URL** (se recomienda HTTPS; se acepta http://)
3. Seleccione los **eventos** a los que suscribirse
4. Elija el **tipo de autenticación** y proporcione las credenciales (opcional)
5. Opcionalmente defina un **secreto** para la verificación de la firma HMAC
6. Haga clic en **Crear**

### Pruebas
Haga clic en **Probar** para enviar un evento de ejemplo a la URL del webhook y verificar que es alcanzable.

## Métricas Prometheus

Endpoint **\`/metrics\`** opcional, protegido por token.

- Se activa definiendo un token de métricas (Configuración › General); sin token → 404
- Recopile con la cabecera \`Authorization: Bearer <token>\`
- Expone \`ucm_certificates\`, \`ucm_certificate_authorities\`, \`ucm_scheduler_task_*\`, \`ucm_webhook_deliveries\`, \`ucm_acme_*\`

## Historial de entrega de webhooks

Abra el historial (icono de reloj) de un webhook para ver sus entregas.

- Estados **pending / delivered / failed** con el último código HTTP y error
- **Reintentar** una entrega manualmente
- Cola duradera con retroceso exponencial (hasta 5 intentos)

## Vista del planificador

Configuración › Planificador muestra las tareas en segundo plano.

- Lista de tareas con **estado**, **última ejecución**, **duración** y **fallos**
- **Ejecutar ahora** en cualquier tarea: espera hasta 30 segundos, y una tarea que sigue en curso se notifica como iniciada, y su resultado aparece en una actualización posterior
- Cubre expiración, CRL, entrega de webhooks, respaldos, autorrenovación…
- **Proceso del planificador** (v2.251): las tareas se ejecutan en un proceso propio, que arranca con el servicio y se reinicia en pocos segundos tras un fallo o una recarga, de modo que una tarea larga no retrasa ni las solicitudes ni los workers. Se muestra un aviso cuando lleva un tiempo sin informar

## Autorrenovación
Los ajustes de autorrenovación gobiernan el planificador de renovaciones.
- **Fuentes**: el planificador renueva los certificados cuya clave privada posee el servidor: por defecto los emitidos desde el formulario o desde una solicitud firmada («manual»), y las inscripciones SCEP, ACME y EST con clave generada por el servidor. Los dispositivos que poseen su propia clave se renuevan a través de su protocolo
- **En espera de aprobación**: un certificado cuya renovación está en cola de aprobación se deja a esa decisión, siempre que pueda llegar antes de que expire el certificado
- **Renovado entretanto**: un certificado que un operador renovó durante el lote no se renueva una segunda vez; uno eliminado durante el lote se omite
- **Ejecutar ahora**: ejecuta una pasada de renovación de inmediato e informa de los certificados por expirar que dejó sin tocar, contados por motivo: aún no en el último tercio de su vigencia, clave privada no en poder del servidor, fuente no seleccionada

## Copias de seguridad programadas

Configuración › Respaldo activa las copias de seguridad automáticas.

- Cadencia **diaria / semanal / mensual**
- **Retención**: los respaldos más antiguos que el número de días fijado se eliminan
- **Límite de tamaño**: un límite en MB para todos los archivos (0 para ninguno); los más antiguos se eliminan, cada uno auditado, hasta que el total encaje. En un solo nodo, la retención nunca elimina el archivo más reciente que coincide con su registro de validación, hasta 2 archivos sin registro de validación y el mínimo conservado; en HA, el mínimo conservado; por ello el total puede quedar por encima del límite, y se informa de ello
- Los respaldos se **cifran** con la contraseña de respaldo
- **Alta disponibilidad**: los archivos se almacenan en PostgreSQL, así que cada nodo los lista, con el nodo que los escribió, y los descarga; la retención se ejecuta en el líder. Se pierden con la base de datos: descargue fuera del clúster los que conserve y respalde PostgreSQL con sus propias herramientas

## Conector de Active Directory

Conexión LDAP propia de UCM a Active Directory, independiente de cualquier proveedor LDAP configurado en SSO. Ese sirve para iniciar sesión en UCM; este se usa para las consultas de AD relacionadas con certificados y funciona tenga o no SSO configurado.

- **Conectores**: Uno por directorio (bosque o dominio), listado en Configuración → Active Directory con su nombre, su realm, el SID de dominio leído y su estado. Un perfil de inscripción de Windows nombra el conector que sirve su realm; un conector que usan perfiles no se puede eliminar, y el rechazo los enumera
- **Propósito**: Resuelve una entidad de seguridad de máquina o usuario Kerberos a su objeto de AD, para que UCM pueda derivar un sujeto/SAN de certificado de la misma forma que lo haría una CA de Windows real
- **Controladores de dominio**: Uno por fila, cada uno por su propio nombre de host, sin puerto ni esquema, probados en orden: las consultas pasan al siguiente cuando un DC está caído. Un nombre de dominio simple falla en la verificación del certificado, ya que el certificado de un controlador de dominio nombra solo su propio host
- **LDAPS**: Interruptor para usar LDAP sobre SSL/TLS; **Verificar certificado SSL** valida el certificado del DC (opcionalmente contra un paquete de CA personalizado cuando no es de confianza pública)
- **Base DN** y **Bind DN / contraseña**: el base DN del dominio, con sus componentes DC (\`DC=corp,DC=example\`, que también nombra el realm Kerberos servido) en un puerto de controlador de dominio (389 o 636, no un Catálogo Global), y la cuenta de servicio usada para las consultas; Bind DN y contraseña son obligatorios mientras el conector esté activado
- **Probar conexión**: Verificar la conectividad y las credenciales antes de guardar
- **Intervalo de comprobación de estado**: Cada controlador de dominio se sondea con un bind real a este intervalo; uno inalcanzable se omite en el momento de la inscripción hasta que se recupere. El veredicto se muestra en la fila del conector y junto a cada DC
- **Conector desactivado**: Un conector desactivado no consulta nada, pero su base DN sigue nombrando el realm del perfil predeterminado como último recurso, cuando ningún conector activado, SPN o keytab lo hace

Las URL de la directiva de inscripción de certificados que se registran en la Directiva de grupo son las mismas para todos los perfiles y se muestran en Configuración → Autoinscripción de Windows.

## Autoinscripción de Windows (XCEP/WSTEP)

Inscripción de certificados nativa de Windows mediante **MS-XCEP** (descubrimiento de directivas) y **MS-WSTEP** (emisión y renovación de certificados): los mismos protocolos que usa el ADCS real para «Solicitar nuevo certificado» de MMC, \`certreq\` y la autoinscripción GPO desatendida.

### Perfiles

Un **perfil por realm de Active Directory**. UCM enruta a un cliente a su perfil por el realm de su entidad de seguridad Kerberos, de modo que cada perfil tiene su propia CA emisora, CA de directiva, plantillas, conector de AD y keytab; las cuentas UsernamePassword pertenecen al perfil predeterminado. La lista está paginada y filtrada por el servidor (nombre o realm, CA, estado), así que cien perfiles se abren tan rápido como uno:
- **Realm**: En mayúsculas, exactamente como lo escribe el KDC (\`CORP.EXAMPLE\`): un KDC compara los realms carácter por carácter, así que un nombre en minúsculas nunca coincide con un ticket. El formulario lo rechaza y dice por qué
- **Conector**: El conector de AD que sirve el realm. Cuando su dominio difiere del realm del perfil, el formulario avisa, sin bloquear; el servidor comprueba el par cuando se elige cualquiera de los dos
- **CA emisora** y **CA de directiva**: La CA que emite y la que XCEP anuncia (la CA emisora cuando está vacía). El identificador de la directiva y los OID de las plantillas pertenecen al perfil: se fijan en su creación y no cambian cuando cambia alguna de las dos CA
- **Plantillas**: El subconjunto ofrecido; sin ninguna seleccionada se ofrecen las plantillas de la CA. Un grupo de AD obligatorio y campos de sujeto fijados pueden sustituir a los de la propia plantilla para todo el perfil
- **Estado**: Completo, Falta el keytab, Conector con fallos o Desactivado. Un perfil desactivado rechaza las máquinas de su realm; sus claves permanecen en el keytab servido para que el rechazo se haga y se audite por realm

El **perfil predeterminado** es aquel en el que se convirtió una instalación 2.x; sirve la vinculación UsernamePassword y conserva sus cuentas. Una instalación nueva no tiene ninguno: mientras ningún perfil sea el predeterminado, el editor de perfiles ofrece **Perfil predeterminado** (en un perfil nuevo o ya guardado), y las cuentas aparecen una vez marcado. El predeterminado ya no se retira ni se mueve, desde esta pantalla ni desde la API. Sin realm, Kerberos se rechaza hasta que se defina uno (en mayúsculas, o leído de su keytab); la pantalla lo dice.

### Lista de verificación de configuración, por perfil

El formulario del perfil lista lo que a ese perfil aún le falta: realm, CA emisora, keytab, un conector alcanzable cuando se ha elegido uno, una plantilla con la autoinscripción permitida, y el perfil activado.

### Descubrimiento de directivas (XCEP)

- **Autoridad de certificación**: La CA cuyas plantillas se anuncian y que emite los certificados mediante el perfil
- **Validez (días)**: Validez de los certificados emitidos por WSTEP cuando la solicitud no coincide con ninguna plantilla; si coincide, se aplica la validez propia de la plantilla

Una plantilla con un tipo de clave **ML-DSA** se anuncia por el OID de su algoritmo de clave, con el Microsoft Software Key Storage Provider y una especificación de clave solo de firma. Se oculta en modo FIPS cuando el módulo FIPS no aprueba ML-DSA, y la inscripción desde un cliente Windows real aún no se ha probado.

Una plantilla **ECDSA** se anuncia en el esquema de directiva 3 con su curva (\`ECDSA_P256\`, \`ECDSA_P384\`, \`ECDSA_P521\`) como clave de firma y un hash de solicitud, el más fuerte entre el resumen de la plantilla y el que corresponde a la curva; las plantillas RSA fuera del modo FIPS siguen en el esquema 2, que no nombra ningún hash de solicitud: Windows firma entonces su solicitud CMC con SHA-1, que UCM acepta como exigen esos clientes; un PKCS#10 simple firmado con SHA-1 sigue rechazándose. La clave de la solicitud debe ajustarse a la plantilla con la que se emite: la misma curva o el mismo conjunto ML-DSA, o una clave RSA al menos igual de larga (v2.251).

Una solicitud que nombra su plantilla, por OID (\`szOID_CERTIFICATE_TEMPLATE\`) o por nombre (\`szOID_ENROLL_CERTTYPE\`), se emite con esa plantilla; se rechazan una plantilla que la CA no ofrece o que está inactiva, dos nombres para dos plantillas, o EKU que la plantilla no emite. Cada directiva anuncia la extensión \`szOID_CERTIFICATE_TEMPLATE\` de su plantilla, que el CertEnroll de Windows copia en su solicitud, de modo que se distinguen dos plantillas con los mismos EKU (v2.252). Una solicitud que no nombra ninguna se asocia a una plantilla por sus EKU. Una plantilla cuyos EKU nunca se emiten a un inscrito, como OCSP Signing, no se anuncia, y se rechaza una solicitud para ella. El certificado lleva los EKU de su plantilla, no los que pide la solicitud.

WSTEP atiende solo el tipo de solicitud Issue, renovaciones incluidas, y rechaza un mensaje cuyo \`wsu:Timestamp\` expiró hace más de 5 minutos. Un PKCS#10 simple o una solicitud CMC se reconoce por su contenido sea cual sea su ValueType, y cada respuesta lleva la CMC Full PKI Response junto al certificado.

### Kerberos / SPNEGO

Vincula los endpoints XCEP/WSTEP autenticados por Kerberos usados para la autoinscripción GPO silenciosa, de modo que las máquinas y los usuarios se autentican con su ticket Kerberos en lugar de una solicitud de credenciales:
- **Service Principal Name (SPN)**: p. ej. \`HTTP/ucm.example.com@EXAMPLE.COM\`, compartido por todos los perfiles con los interruptores XCEP, WSTEP y Kerberos
- **Keytab**: Uno por perfil, generado con \`ktpass\` o \`ktutil\` en el controlador de dominio de su realm. Cada entrada debe ser \`HTTP/<host>@<realm del perfil>\`; el formulario lista las entradas del archivo elegido por realm y señala un realm que no es el del perfil. Los keytabs de todos los perfiles se sirven como un solo archivo

> ⚠ Kerberos requiere el **backend \`gssapi\`** del lado del servidor (la biblioteca Python \`gssapi\` más las bibliotecas Kerberos del sistema): el paquete SPNEGO base por sí solo no basta. Sin él, la autenticación Kerberos no funcionará aunque se active aquí, y la vinculación Kerberos no se anuncia; la pestaña muestra un aviso.

Las imágenes Docker incluyen este backend desde la v2.251.

### URL de la directiva de inscripción

Las mismas para todos los perfiles: el enrutamiento es por realm, no por URL.
- **Usuario/contraseña**: Solicita credenciales; para la inscripción interactiva «Solicitar nuevo certificado», no requiere Active Directory
- **Kerberos**: Sin solicitud de credenciales; requiere un cliente unido al dominio y configuración GPO

### Vinculación de renovación por certificado

Además de Usuario/contraseña y Kerberos, WSTEP admite la **renovación con certificado de cliente**, reflejando los endpoints CES del ADCS real: la solicitud de renovación (RST) debe estar firmada con XML-DSig con la clave privada de un certificado **emitido por la propia UCM**. El certificado presentado se compara **byte a byte** con el certificado almacenado para la CA configurada; el número de serie o el sujeto por sí solos nunca bastan. Esto permite a los clientes Windows renovar de forma desatendida con su certificado actual, sin credenciales ni ticket Kerberos.

XML-DSig no tiene método de firma ML-DSA, así que un certificado **ML-DSA** no puede renovar así: UCM nombra la clave en su rechazo, y el cliente inscribe un certificado nuevo.

Windows también puede renovar con \`certreq ... Renew\`, autenticado por el certificado que se renueva como certificado de cliente TLS: active mTLS con la CA de WSTEP, o una de sus ancestras, de confianza. Una renovación conserva la plantilla y los EKU del certificado que renueva (v2.248). Desde la 3.0 solo un certificado emitido mediante la inscripción de Windows se renueva así: uno firmado en la interfaz se rechaza (\`not issued through Windows enrollment\`) y debe reemitirse mediante la inscripción de Windows.

Desde la 3.0 una renovación por certificado la sirve el perfil que registra el certificado (un certificado WSTEP de la 2.x: el perfil predeterminado), bajo la CA emisora de ese perfil, y se rechaza cuando el perfil se eliminó o está desactivado; cada rechazo se audita con el perfil y el motivo. Solo se vuelve a comprobar el SID, por el conector del perfil: revoque el certificado de un equipo retirado del grupo. El certificado de cliente TLS solo funciona para un perfil cuya CA emisora es la CA mTLS o una CA bajo ella, y para una antigua CA que el perfil lista (más abajo): un certificado que el listener no considera de confianza se rechaza durante el handshake TLS, antes de que UCM vea una solicitud, así que UCM no audita nada (lea la salida del cliente y el registro del servicio). Los demás perfiles renuevan solo por Kerberos (sirve el perfil del realm de la entidad de seguridad y el nuevo certificado lo registra), y cuando Kerberos rechaza (solicitante retirado del grupo de AD, perfil desactivado) no pueden renovar. El keytab de Kerberos conserva las claves de los perfiles desactivados, de modo que sus solicitudes se rechazan con una entrada de auditoría: solo eliminar el perfil las quita.

Por Kerberos, una solicitud firmada por el propio certificado válido del solicitante, del perfil, lo renueva cuando nombra la plantilla de ese certificado (o el certificado no lleva ninguna, como uno emitido antes de la 3.0): el certificado renovado se marca como reemplazado por el nuevo, como en la vinculación por certificado, la entrada de auditoría es \`certificate.renewed\` y el webhook \`cert.renewed\`, y una segunda renovación del mismo se rechaza en cualquiera de las dos vinculaciones (\`Renewed certificate superseded by a newer one\`). Una solicitud que nombra otra plantilla es una inscripción (\`certificate.issued\`), incluso cuando el certificado que la firma ya fue renovado. Tras un cambio de la CA emisora del perfil, un certificado de la CA anterior se renueva de la misma forma: lo emite la nueva CA, y la entrada de auditoría \`certificate.renewed\` nombra el serial antiguo y la CA antigua.

Tras un cambio de la CA emisora del perfil, la CA saliente se lista en el perfil bajo **CAs anteriores que aún renuevan**, y la auditoría del cambio lo indica. Un certificado que UCM emitió bajo el perfil con una CA listada se renueva en ambas vinculaciones con las mismas reglas (misma plantilla, mismo sujeto, válido, registrado): la CA actual emite el certificado nuevo, el antiguo se marca como reemplazado y \`certificate.renewed\` nombra el serial antiguo y la CA antigua. Una CA anterior quitada de la lista, revocada o eliminada no renueva nada desde ese momento: la vinculación por certificado rechaza la renovación, y por Kerberos la solicitud se juzga como una inscripción. La lista solo se reduce: quite una CA para detener sus renovaciones, por ejemplo tras su compromiso; una CA que nunca fue la CA emisora del perfil no se puede listar. Con mTLS activado, el listener TLS también confía en cada CA anterior listada que no esté bajo la CA mTLS, de modo que \`certreq ... Renew\` con un certificado de esa CA llegue a UCM; un guardado que cambia en qué se confía recarga el listener TLS (reinicio progresivo en HA). Un certificado de cliente que el listener deja pasar solo por una CA anterior sirve únicamente para la renovación WSTEP y nada más: el inicio de sesión por certificado, EST y todas las demás rutas no lo ven, y mientras se confíe en una CA anterior esto vale para cualquier certificado de cliente cuyo emisor no sea una CA de UCM bajo la CA mTLS.

### Extensión de seguridad SID (KB5014754)

En la **emisión autenticada por Kerberos**, UCM incrusta el SID de AD del solicitante en la extensión de seguridad SID de Microsoft (\`szOID_NTDS_CA_SECURITY_EXT\`) del certificado emitido. Los controladores de dominio la usan para el **mapeo fuerte de certificados** (KB5014754): exigido desde que AD impone el mapeo fuerte para la autenticación basada en certificados (inicio de sesión con tarjeta inteligente, PKINIT). Con el conector de AD activado, una solicitud cuyo SID no puede resolverse se rechaza en lugar de emitirse sin él, incluida una entidad de seguridad de un realm distinto del dominio del conector. Una renovación WSTEP, EST o SCEP conserva la extensión SID del certificado que renueva, nunca una de la CSR; con el conector de AD activado, ese SID debe seguir nombrando una cuenta del directorio.

### Sujetos derivados de AD

Una plantilla de certificado puede optar por **Construir el sujeto desde Active Directory** (Plantillas → Inscripción): para la autoinscripción GPO desatendida, el sujeto y el SAN se derivan del objeto de AD del solicitante mediante el conector de AD en lugar de exigir que el cliente aporte uno, igual que se configura una plantilla ADCS real para la autoinscripción. En los endpoints Kerberos, el sujeto de una plantilla así y de toda plantilla de máquina (tipos Web Server, VPN, OCSP Signing) procede siempre de Active Directory, nombre lo que nombre la solicitud: una plantilla de máquina toma el nombre DNS del equipo, se rechaza a una cuenta de usuario, y una plantilla «Construir el sujeto desde Active Directory» se rechaza a un equipo. Una plantilla sin ninguna de las dos conserva el sujeto que aporta el cliente, siempre que configure sus EKU, y lo mismo toda plantilla en los endpoints Usuario/contraseña, que no tienen identidad de directorio de la que construirlo. En los endpoints Kerberos, una solicitud que no coincide con ninguna plantilla obtiene también su sujeto de Active Directory: el nombre DNS de un equipo, el de un usuario solo cuando una plantilla lo ha activado, y si no se rechaza. Con independencia de lo anterior, **Permitir autoinscripción** anuncia la plantilla como \`autoEnroll=true\` en la directiva de inscripción de certificados, para que los clientes autenticados por GPO/Kerberos la soliciten automáticamente al iniciar sesión.

## Acerca de

- **Información del sistema**, **Enlaces y recursos** y el enlace **Apoyar UCM** a Ko-fi. Los administradores ven además una tarjeta de Ko-fi descartable una vez por versión de UCM
- **Comprobar la preparación para FIPS** (admin:system): lista lo que el modo FIPS rechazaría en esta instancia (hashes de contraseña scrypt, autoridades Ed25519 en un módulo sin EdDSA, respaldos Argon2id, PostgreSQL sin TLS, secretos HMAC de menos de 14 bytes...), con un remedio para cada caso. No se cambia nada. En modo FIPS, sus bloqueos también se escriben en el registro en cada arranque, una línea de error por cada uno con su remedio, y el estado del servicio los lleva; UCM arranca igualmente y rechaza cada operación afectada cuando se usa
`
  }
}
