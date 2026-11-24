export default {
  helpContent: {
    title: "Certificados",
    subtitle: "Emita, gestione y supervise certificados",
    overview: "Gestión centralizada de todos los certificados X.509. Emita nuevos certificados desde sus CA, importe los existentes, controle las fechas de expiración y gestione las renovaciones y revocaciones.",
    sections: [
      {
        title: "Análisis de conformidad",
        content: "La acción Analizar en el detalle de un certificado lo pasa por analizadores de estándares y muestra los hallazgos. Solo informativo, nunca bloquea la emisión.",
        items: [
          { label: "Perfiles", text: "RFC 5280 (siempre relevante), CA/Browser Forum Baseline Requirements (certificados TLS de servidor) y ETSI EN 319 412 (certificados cualificados y relacionados con eIDAS, incluido qcStatements)" },
          { label: "Severidades", text: "Los hallazgos se clasifican en fatal, error, warning, notice e info" },
          { label: "Motor", text: "Impulsado por pkilint (y zlint si su binario está presente): dependencia opcional del servidor" },
          { label: "PKI interna", text: "Las reglas de CA/Browser Forum apuntan a certificados públicos; espere hallazgos no aplicables en una PKI interna" },
        ]
      },
      {
        title: "Estado del certificado",
        definitions: [
          { term: "Válido", description: "Dentro del período de validez y no revocado" },
          { term: "Por renovar", description: "Expirará dentro de 30 días" },
          { term: "Expirado", description: "Posterior a la fecha «Not After»" },
          { term: "Revocado", description: "Revocado explícitamente (publicado en la CRL)" },
          { term: "Huérfano", description: "La CA emisora ya no existe en el sistema" },
          { term: "Archivado", description: "Sustituido por una renovación o reinscripción que conservó el registro antiguo como historial (SCEP, EST, WSTEP, ACME, respondedor OCSP); se lista en la pestaña «Archivado»" },
        ]
      },
      {
        title: "Acciones",
        items: [
          { label: "Emitir", text: "Dos pasos. Configurar: plantilla, autoridad, nombre común, origen de la clave (generada en UCM, o una CSR aportada que se une a la lista de CSR y luego se firma), algoritmo de clave, validez en días o fecha de fin, nombres alternativos tipados; Avanzado contiene el tipo de certificado, los EKU, el sujeto completo, el par híbrido y las extensiones personalizadas. La columna de la derecha indica lo que imponen la plantilla y las políticas de la CA. Una autoridad o una plantilla se elige por usted solo cuando es la única; Avanzado permanece plegado hasta que lo abra, y su línea plegada indica cuándo la plantilla fija valores ahí. Revisar muestra exactamente la solicitud que se va a enviar y contiene el único botón Emitir; una pantalla de resultado ofrece entonces ver el certificado o, cuando una política exige una aprobación, indica que la solicitud la espera y enlaza a ella. Un formulario cerrado sin emitir conserva su borrador para su próxima apertura, uno por operación (emisión, renovación de un certificado concreto), solo en memoria y nunca con una clave ni una contraseña" },
          { label: "Importar", text: "Importa un certificado existente (PEM, DER o PKCS#12)" },
          { label: "Renovar", text: "In situ desde v2.214: mismos id/refid, nuevo número de serie y validez, y el número de serie sustituido permanece en la CRL hasta la expiración antigua. Un certificado revocado no puede renovarse. Abre el mismo formulario de emisión en modo renovación: la plantilla, la autoridad, los nombres, el algoritmo de clave y los valores de Avanzado se muestran de solo lectura, pues la renovación los toma del certificado; solo cambia la validez en días (si se deja tal cual, se conserva la duración actual, incluso por encima de 3650 días; una escrita va de 1 a 3650), luego el paso Revisar y una pantalla de resultado. Un certificado de una CA de Microsoft solo pide una confirmación, pues la CA fija la duración. Las políticas y la expiración de la CA siguen limitándola" },
          { label: "Renombrar", text: "Define un nombre para mostrar independiente del CN (por defecto el CN o el primer nombre DNS de los SAN para certificados sin CN)" },
          { label: "Comentario", text: "Una nota en texto sin formato junto al nombre para mostrar, de 4 000 caracteres como máximo, con los saltos de línea conservados: Añadir comentario o Editar comentario en el Resumen del inspector, para quien puede escribir certificados; un texto vacío lo elimina, y la auditoría registra solo su longitud. La búsqueda de la lista y la búsqueda global lo encuentran, el botón Columnas añade su columna y la exportación de la lista lo incluye" },
          { label: "Revocar", text: "Marca como revocado con un motivo; aparecerá en la CRL" },
          { label: "Eliminar suspensión", text: "Quita la suspensión de un certificado revocado con el motivo «Suspensión (temporal)» y lo restaura al estado válido" },
          { label: "Revocar un certificado suspendido", text: "Un certificado suspendido también puede revocarse de forma definitiva con otro motivo, sin pasar por válido. La CRL y OCSP dan entonces el nuevo motivo, y la fecha de invalidez es el inicio de la suspensión salvo que se indique otra" },
          { label: "Revocación en la CA ACME", text: "Revocar un certificado obtenido por ACME (por el cliente, o por el proxy bajo una cuenta upstream que UCM posee) lo revoca también en esa CA, ya se revoque solo, en lote, mediante una solicitud aprobada, como certificado de usuario, junto con la inscripción o el usuario al que pertenece, como miembro vinculado de un par, o por su clave en el propio servidor ACME de UCM. Si la CA no lo confirma, la revocación queda pendiente y la tarea de renovación la vuelve a enviar; una suspensión se queda en UCM, pues ACME no tiene ninguna. Si ninguna cuenta de UCM puede hablar en su nombre, se queda en local y un aviso indica que debe revocarse directamente en la CA. El motivo se envía cuando es keyCompromise, affiliationChanged, superseded, cessationOfOperation o privilegeWithdrawn" },
          { label: "Exportar", text: "Elija PEM, DER, PKCS#7, PKCS#12, JKS o solo la clave privada; los formatos que llevan la clave siguen en la lista, atenuados, cuando UCM no la posee o usted no puede exportar claves. El diálogo previsualiza lo que contendrá el archivo (cadena, CA raíz, clave) antes de la descarga" },
          { label: "Modo de compatibilidad PKCS#12 (v2.222)", text: "Los diálogos de exportación ofrecen un perfil 3DES/SHA-1 para los importadores que rechazan el archivo AES-256 por defecto como contraseña incorrecta: Android 15 y anteriores, macOS 14 y anteriores, Windows Server 2016 y anteriores, Java antiguo. Desactivado por defecto, protege peor el archivo" },
          { label: "Comparar", text: "Comparación lado a lado de dos a cuatro certificados: márquelos y luego haga clic en Comparar en la barra de selección. La comparación se abre en una ventana separada (en un diálogo en un teléfono), una columna por certificado: sujeto, emisor, validez, algoritmo y tamaño de clave, nombres alternativos, usos de la clave, huellas, número de serie y cualquier otra extensión; una línea idéntica para todos se fusiona en una sola celda marcada Identical, una línea que difiere se marca con un trazo junto a su etiqueta y, en una lista, + marca el elemento que no tienen todos los certificados; Mostrar solo las diferencias oculta las líneas idénticas" },
          { label: "Separar", text: "Separar en una ventana, en la barra de herramientas del inspector, mueve el certificado a una ventana sobre la página, con sus secciones y acciones; abra varias para verlas lado a lado. Véase Navegación para mover, redimensionar y cerrar las ventanas" },
          { label: "Exportar la lista", text: "El botón de exportación de la barra de herramientas y Exportar… de la barra de selección abren un mismo diálogo: los certificados en PEM, o sus metadatos (nombre, descripción, emisor, origen, estado, expiración, algoritmo, número de serie, plantilla, comentario) en CSV o JSON, nunca una clave privada. Una vez marcada toda la página, Seleccionar los N resultados toma todos los resultados de la búsqueda y los filtros, 10 000 como máximo" },
          { label: "Filtros", text: "El botón Filtros, al final de la barra de herramientas, contiene el filtro de plantilla (certificados modificados respecto a su plantilla, mostrado como una etiqueta que se puede quitar una vez activo) y los filtros guardados: la búsqueda, el estado y los filtros bajo un nombre, en este navegador, que se aplican de nuevo con un clic" },
          { label: "Otras extensiones (v2.251)", text: "Los detalles del certificado y de la CA enumeran bajo Otras extensiones las que UCM no tiene sección para mostrar, con su OID, nombre si se conoce, criticidad y valor sin procesar. El formulario de emisión puede añadir extensiones personalizadas además de las de la plantilla" },
          { label: "Claves comprometidas (v2.251)", text: "Una clave revocada como keyCompromise sigue conocida tras eliminar su certificado, sea cual sea la CA que lo emitió, Let's Encrypt incluida: el cliente ACME la rechaza en la solicitud, la renovación y la finalización, y EST rechaza una CSR que la lleve. Las demás vías de emisión no consultan esta lista" },
          { label: "Certificados del cliente ACME (v2.251)", text: "Un certificado obtenido por el cliente ACME también se renueva in situ, conservando su id y su refid. Las copias que renovaciones anteriores importaron como filas nuevas permanecen en el inventario hasta que se archiven o se eliminen" },
        ]
      },
      {
        title: "EKU adicionales personalizados (RFC 5280 §4.2.1.12)",
        content: "El formulario Emitir certificado (Avanzado, como usos marcados y un campo Otro OID) y el diálogo Firmar CSR (un selector múltiple «EKU adicionales») añaden OID de Extended Key Usage además de los valores por defecto del tipo de certificado:",
        items: [
          { label: "Catálogo", text: "26 EKU conocidos en una lista desplegable: Microsoft RDP (1.3.6.1.4.1.311.54.1.2), inicio de sesión con tarjeta inteligente, firma de documentos, IPsec, Kerberos PKINIT, etc." },
          { label: "OID libres", text: "Cualquier OID punteado bien formado que cumpla ^[0-2](?:\\.(?:0|[1-9]\\d*)){1,15}$" },
          { label: "Límite", text: "Hasta 16 OID en total por certificado" },
          { label: "Fusión, nunca reemplazo", text: "Los EKU por defecto del tipo de certificado (p. ej. serverAuth) permanecen fijos como etiquetas, los extras se añaden encima" },
          { label: "Rechazado", text: "anyExtendedKeyUsage (2.5.29.37.0) está explícitamente prohibido" },
        ]
      },
      {
        title: "Pares de certificados híbridos (RFC 9763)",
        content: "Un certificado clásico (A) y uno ML-DSA (B) para el mismo sujeto, vinculados: B incluye la extensión relatedCertificate que nombra a A por su hash. Los clientes que conocen ML-DSA comprueban ambos; los demás siguen usando A.",
        items: [
          { label: "Emisión", text: "Marque «Emitir un par híbrido (RFC 9763)» en Avanzado, en el formulario Emitir certificado, y elija la clave clásica y el nivel ML-DSA; ambos salen de la misma CA, con el mismo sujeto, nombres y validez, y B no declara ningún uso de clave ni EKU que A no tenga. Solo se ofrece cuando las políticas de la CA permiten ambos, nunca en modo FIPS. Con los perfiles ANSSI, BSI y EU ACM, ML-DSA-65 y ML-DSA-87 se ofrecen solo en el par. Una política que exige aprobación rechaza por ahora el par" },
          { label: "Vinculado por solicitud", text: "Una CSR con una relatedCertRequest firmada por la clave de A (Firmar CSR, ACME, EST, WSTEP) emite un B vinculado a A. A debe estar en UCM, ser válido, no revocado y de entidad final; un B más reciente que nombre el mismo A releva al par" },
          { label: "Vinculado", text: "Cada miembro lleva una marca de vínculo tras su nombre en la lista y una insignia Vinculado en sus detalles, con un enlace que abre el otro miembro; el botón Columnas añade a la lista una columna Vinculado" },
          { label: "Revocación", text: "Revocar un miembro, solo o en una operación en lote, revoca también el otro salvo que desmarque «Revocar también el certificado vinculado», p. ej. para conservar A cuando solo la clave ML-DSA está comprometida; con una política que exige aprobación, ambos van juntos. Un aviso nombra al otro miembro cuando no se pudo revocar. La revocación ACME revoca solo el certificado presentado" },
          { label: "Renovación", text: "Renovar cualquiera de los miembros renueva ambos, manualmente, en lote o automáticamente, y el nuevo B nombra al nuevo A. Un miembro renovado solo nombra únicamente el certificado que nombraba su original; cuando este ya se ha renovado, revocado, archivado o expirado, sale del par y la renovación indica el motivo. Un miembro que no se puede leer rechaza la renovación" },
          { label: "Exportación", text: "El formato Paquete híbrido descarga un ZIP con ambos certificados y, si incluye la clave y puede exportar claves, ambas claves" },
        ]
      },
      {
        title: "Archivos de certificado en disco (v2.140)",
        items: [
          { label: "Materialización automática", text: "Los archivos .crt / .key se escriben en data/certs/ en cada vía de creación (interfaz, firma de CSR, ACME, SCEP, importación)" },
          { label: "Las CA también", text: "Los archivos .crt / .key de las CA se escriben en data/cas/ por el mismo mecanismo" },
          { label: "Red de seguridad", text: "Un escaneo de regeneración al arranque reconstruye cualquier archivo faltante desde la base de datos" },
          { label: "No bloqueante", text: "Los errores de escritura de archivos se registran pero nunca abortan la transacción de la base de datos" },
        ]
      },
      {
        title: "Despliegue (v2.215)",
        content: "Envíe este certificado a hosts remotos por SSH/SFTP o a una API HTTP, solo administradores; los destinos se gestionan en Configuración › Despliegue.",
        items: [
          { label: "Asociar destino", text: "Desde la vista de detalle del certificado: elija un destino de despliegue y defina rutas de destino absolutas para el certificado, la clave privada y/o la cadena completa (al menos una). La cadena completa omite la CA raíz salvo que esté marcada Incluir CA raíz" },
          { label: "API HTTP (v2.252)", text: "Un destino HTTP no usa rutas: en la emisión, la renovación y Desplegar ahora, UCM envía una solicitud construida a partir de la plantilla de cuerpo del destino (certificado, cadena, sujeto, número de serie y la clave privada solo cuando el destino lo permite)" },
          { label: "Mismo host", text: "Para desplegar en el propio host de UCM, use un destino SFTP en 127.0.0.1 con una cuenta SSH dedicada; el servicio aislado no puede escribir fuera de su directorio de datos" },
          { label: "Automático", text: "En la emisión y la renovación, los archivos vinculados se envían de nuevo y se ejecuta el comando de recarga opcional de ese despliegue; las entregas se encolan con reintentos" },
          { label: "Archivos", text: "Se escriben de forma atómica en las rutas exactas configuradas (el directorio padre debe existir): clave 0600, certificado/cadena 0644" },
          { label: "Desplegar ahora", text: "Envío manual desde la vista de detalle, con el estado de entrega y el último error mostrados por destino" },
          { label: "Renovación sin la clave", text: "Una renovación EST, SCEP o WSTEP mueve los despliegues al nuevo certificado, salvo uno que envía la clave privada cuando UCM no posee la clave nueva: muestra No sigue la renovación, aparece en la campana y en el resumen, y ofrece Vincular al certificado renovado cuando UCM posea la clave o el despliegue deje de enviarla. Importar la clave lo mueve por sí solo" },
        ]
      },
    ],
    tips: [
      "Marque con una estrella ⭐ los certificados importantes para añadirlos a su lista de favoritos",
      "Las pestañas sobre la lista filtran por estado y cuentan cada uno; la pestaña forma parte de la dirección, así que una recarga o un enlace compartido la conserva. La búsqueda, el orden, la página y los filtros de CA, origen y plantilla forman parte de la dirección también; una dirección sin más muestra toda la lista, y el navegador no guarda ningún filtro aparte. Los certificados abiertos en el inspector forman parte igualmente de la dirección (item para el que se muestra, open cuando hay varios), de modo que una recarga reabre cada uno",
      "Un clic en cualquier punto de una fila abre su certificado en el inspector, salvo en su casilla o sus botones o al final de una selección de texto; con el teclado lo hacen el nombre y el chevrón. Una fila conserva una sola acción, Exportar. El encabezado del inspector tiene Exportar y Renovar; su ⋯ abre el diálogo Acciones del certificado: copiar el nombre común, ver su actividad en el registro de auditoría, revocar, y luego analizar, subir la clave, renombrar, favoritos, añadir la CA emisora al almacén de confianza y eliminar. Marque filas para comparar dos certificados o exportarlos; mientras haya filas marcadas, los nombres y las acciones de fila esperan. Inspeccionar la autoridad, en la cadena, la abre en la página Autoridades. Escape cierra el inspector desde cualquier punto de la página",
      "La columna Vencimiento da días por debajo de 60, luego meses, luego años y meses (45 d, 16 m, 1 a 4 m, 9 a, Expirado); pase el cursor por encima para ver la fecha y la hora exactas. La lista muestra 12 certificados por página por defecto (25, 50 o 100 a elección, se recuerda), con un campo de número de página para ir a cualquiera. Columnas abre un diálogo para elegir las columnas; el nombre y el estado se muestran siempre. Cada columna se muestra entera mientras haya sitio; si falta, el nombre y los textos largos ceden juntos, luego la lista pliega sus columnas menos necesarias, la descripción y después los calificadores, y su pie indica cuántas; una columna plegada sigue marcada en Columnas. Un encabezado que ordena es un botón que ocupa toda su celda con un signo de dos triangulitos, la columna ordenada se lee en negrita con una flecha, el orden permanece en la dirección, y en un teléfono un selector Ordenar por y un botón que muestra el sentido sustituyen a los encabezados. El botón de densidad alterna las filas entre 36 y 44 px, en todas las listas de la interfaz. Por debajo de 800 px de ancho, cada certificado es un registro con su estado y su fecha de expiración, y el inspector ocupa toda la pantalla; la página se desplaza hasta sus páginas. En un inspector estrecho el resumen conserva dos columnas, con la cadena de confianza bajo la validez; Más detalles la sigue y, en el panel anclado a la derecha o en una ventana separada, permanece a la vista al pie del panel",
      "Renovar conserva el mismo registro (id, refid, fecha de creación). Renovar desde la página genera una clave nueva; la renovación automática conserva la clave. Un certificado cuya clave UCM no posee (inscripción SCEP, EST, WSTEP o ACME, importación sin la clave) se rechaza (409): renuévelo mediante su protocolo o firme una solicitud nueva",
      "¿Necesita un EKU no estándar (Microsoft RDP, inicio de sesión con tarjeta inteligente, firma de documentos)? Añádalo mediante «EKU adicionales» en lugar de editar plantillas",
      'Cuando una política o la expiración de la CA emisora acorta la validez solicitada, el resultado lo indica: "Issued for N day(s) instead of the M requested", con el motivo',
      "Una firma RSA-PSS se muestra con su hash y la longitud de sal, p. ej. RSASSA-PSS SHA-256 (salt 32)",
      "En una vista de enlace (abierta desde el resumen), los filtros del enlace se muestran como etiquetas bajo la barra de herramientas; quitar una etiqueta elimina ese filtro, Borrar todos los filtros sale de la vista de enlace, y sus filtros guardados no se tocan. Cuando nada coincide, Restablecer los filtros borra la búsqueda y los filtros; el enlace de clave débil de la tarjeta de cumplimiento se muestra como una sola etiqueta, Cumplimiento: clave débil, RSA < 3072",
      "Escape cierra primero un menú abierto de la barra de herramientas (un filtro, los filtros guardados, la exportación) y luego el inspector; el foco vuelve a la fila que lo abrió",
    ],
    warnings: [
      "La revocación es generalmente permanente: excepto «Suspensión (temporal)», que puede eliminarse o hacerse permanente con otro motivo",
      "Un certificado válido no revocado no puede eliminarse por sí solo: Eliminar explica el motivo y ofrece «Revocar y luego eliminar», para que la revocación llegue a la CRL/OCSP; las revocaciones sobreviven a la eliminación",
      "Bajo una CA guardada sin su clave (una CA pública importada), o sin CA, UCM no publica ninguna revocación: Eliminar quita un certificado válido sin revocarlo, y un administrador levanta una revocación hecha allí con Levantar la revocación, tras una confirmación registrada en el registro de auditoría. La revocación de una CA cuya clave guarda UCM nunca se levanta, salvo una suspensión con Eliminar suspensión",
      "UCM firma solo con SHA-256, SHA-384 o SHA-512: SHA-224 y los nombres de hash desconocidos se rechazan en lugar de sustituirse por SHA-256",
    ],
  },
  helpGuides: {
    title: "Certificados",
    content: `
## Descripción general

Gestión centralizada de todos los certificados X.509. Emita nuevos certificados, importe los existentes, controle las fechas de expiración y gestione las renovaciones y revocaciones.

## Estado del certificado

- **Válido**: dentro del período de validez y no revocado
- **Por renovar**: expirará dentro de 30 días
- **Expirado**: posterior a la fecha «Not After»
- **Revocado**: revocado explícitamente, publicado en la CRL
- **Huérfano**: la CA emisora ya no existe en UCM
- **Archivado**: sustituido por una renovación o reinscripción que conservó el registro antiguo como historial (SCEP, EST, WSTEP, ACME, respondedor OCSP)

## Emitir un certificado

1. Haga clic en **Emitir certificado**
2. Seleccione la **CA firmante** (debe poseer una clave privada)
3. Complete el sujeto (el CN es obligatorio, los demás campos son opcionales)
4. Añada nombres alternativos del sujeto (SAN): nombres DNS, IP, correos electrónicos. Un nombre DNS sigue la RFC 5280: etiquetas separadas por puntos, un comodín solo como primera etiqueta, sin espacios ni punto final; un nombre internacionalizado se emite como su A-label. Un CN de servidor o combinado que contenga un guion bajo (\`my_host.example.com\`) se rechaza cuando sería el nombre DNS del certificado, es decir, sin SAN indicado y con una plantilla que permita nombres DNS. Una dirección de correo en el sujeto pasa también al SAN, sea cual sea el tipo
5. Elija el tipo y el tamaño de la clave
6. Establezca el período de validez
7. Opcionalmente aplique una **plantilla** para prerellenar la configuración
8. Haga clic en **Emitir certificado**

### Uso de plantillas
Las plantillas prerellenan el uso de la clave, el uso extendido de la clave, los valores predeterminados del sujeto y la validez. Seleccione una plantilla antes de rellenar el formulario para ahorrar tiempo.

## Importar certificados

Formatos admitidos:
- **PEM**: certificados individuales o agrupados
- **DER**: formato binario
- **PKCS#12 (P12/PFX)**: certificado, clave y cadena (se requiere contraseña)
- **PKCS#7 (P7B)**: cadena de certificados sin claves

## Renovar un certificado

Desde v2.214, la renovación actualiza el certificado **in situ**:
- Mismo registro: **id, refid y fecha de creación nunca cambian**: las integraciones conservan sus referencias
- Mismos sujeto y SAN; nuevo número de serie y nuevo período de validez
- Renovar desde la página genera una **clave nueva**; la renovación automática conserva la clave
- Un certificado cuya clave UCM no posee (inscripción SCEP, EST, WSTEP o ACME, importación sin la clave) se rechaza (409): renuévelo mediante su protocolo de inscripción o firme una solicitud nueva
- El **número de serie sustituido permanece publicado en la CRL** (motivo \`superseded\`) y responde \`revoked\` vía OCSP hasta la expiración original del certificado antiguo
- \`renewed_at\` / \`renewed_times\` registran el historial de renovaciones
- Un certificado revocado no puede renovarse (409): emita uno nuevo en su lugar
- **Renovar** pide la validez del nuevo certificado en días, rellenada con la duración actual; las políticas de emisión y la expiración de la CA siguen limitándola
- **La renovación mediante EST, SCEP o WSTEP** almacena un certificado nuevo: sus despliegues y el enlace HTTPS pasan a él. Un despliegue que envía la clave privada, y el enlace HTTPS, se quedan en el certificado anterior cuando UCM no posee la clave nueva: el despliegue muestra **No sigue la renovación**, la campana y el resumen lo listan, y se envía el evento \`certificate.binding_left_behind\`. **Vincular al certificado renovado** cuando UCM posea su clave o el despliegue deje de enviarla; importar la clave del certificado renovado los mueve por sí solo

**Eliminación**: un certificado válido no revocado no puede eliminarse por sí solo: **Eliminar** explica el motivo y ofrece **Revocar y luego eliminar**, para que las partes que confían vean el cambio. Las revocaciones se persisten independientemente del registro del certificado y sobreviven a la eliminación. Bajo una CA guardada sin su clave (una CA pública importada), o para un certificado no vinculado a ninguna CA, UCM no firma ni CRL ni respuestas OCSP: **Eliminar** quita un certificado válido sin revocarlo, y lo indica. Un certificado obtenido de una CA de Microsoft o por ACME sigue necesitando su revocación primero: UCM la comunica a su CA, que la publica.

## Revocar un certificado

1. Seleccione el certificado → **Revocar**
2. Elija un motivo de revocación (Clave comprometida, CA comprometida, Cambio de afiliación, Sustituido, Cese de operaciones, Suspensión (temporal), etc.)
3. Confirme la revocación

Los certificados revocados se publican en la CRL en la próxima regeneración.

Un certificado obtenido por ACME (por el cliente ACME, o por el proxy bajo una cuenta upstream que UCM posee) se revoca también en esa CA, ya se revoque solo, en lote, mediante una solicitud aprobada, como certificado de usuario, junto con la inscripción o el usuario al que pertenece, como miembro vinculado de un par, o por su clave en el propio servidor ACME de UCM. Si la CA no lo confirma, la revocación queda pendiente y la tarea de renovación la vuelve a enviar hasta que la CA lo confirme o el certificado expire; una suspensión se queda en UCM, pues ACME no tiene ninguna. Si ninguna cuenta de UCM puede hablar en su nombre, la revocación se queda en local y un aviso indica que debe revocarse directamente en la CA. El motivo se envía cuando es keyCompromise, affiliationChanged, superseded, cessationOfOperation o privilegeWithdrawn.

> ⚠ La revocación es generalmente permanente: excepto la **Suspensión (temporal)**, que puede eliminarse.

### Eliminar la suspensión

Si un certificado fue revocado con el motivo **Suspensión (temporal)**, puede restaurarse al estado válido:

1. Abra el certificado revocado en el inspector
2. El botón **Eliminar suspensión** aparece en la barra de acciones (solo para revocaciones de tipo Suspensión)
3. Haga clic en **Eliminar suspensión** para restaurar el certificado
4. El certificado vuelve al estado válido, la CRL se regenera y la caché OCSP se actualiza

> 💡 La suspensión es útil para interrupciones temporales (por ejemplo, dispositivo perdido, investigación en curso).

### Levantar una revocación local

Una revocación hecha bajo una CA guardada sin su clave nunca se publicó. Un administrador (\`admin:system\`) la levanta desde las acciones del certificado con **Levantar la revocación**, tras una confirmación: cada copia guardada del certificado vuelve a ser válida y su registro de revocación se elimina, de modo que una nueva importación y la reparación horaria lo dejan válido. El registro de auditoría anota \`certificate_local_revocation_lifted\`. Una revocación registrada por una versión anterior pudo publicarse si la CA guardaba entonces su clave en UCM: la confirmación lo indica. Una clave revocada como comprometida sigue rechazada por UCM tras levantar la revocación. Una CA cuya clave guarda UCM (software, HSM o proveedor de claves), una CA fuera de línea o una CA con un respondedor OCSP delegado publica sus revocaciones, una CA que obtiene su clave publica las registradas antes, y una CRL que UCM firmó para la CA después de una revocación puede incluirla: nunca se levantan, salvo una **Suspensión** con **Eliminar suspensión** (RFC 5280 §5.3.1). Una CRL externa que sirve UCM solo publica lo que incluye: una revocación que no incluye sigue siendo local, y un certificado válido que no incluye se elimina sin revocarlo. Tampoco se levanta una revocación que UCM comunica a una CA de Microsoft o a una CA ACME, ni una de la que UCM no guarda ningún registro.

### Revocar definitivamente un certificado suspendido

Un certificado suspendido puede revocarse con otro motivo (por ejemplo Clave comprometida cuando la investigación lo confirme) desde el mismo botón **Revocar**, sin pasar antes a válido. La CRL y OCSP dan el nuevo motivo; salvo que se indique una fecha de invalidez, el inicio de la suspensión se registra como la fecha en que el certificado pasó a ser inválido.


## Exportar certificados

Formatos de exportación:
- **PEM**: solo el certificado
- **PEM + cadena**: certificado con sus CA emisoras (**Incluir cadena de certificados**); la CA raíz solo se añade si está marcada **Incluir CA raíz**
- **DER**: formato binario
- **PKCS#12**: certificado, clave y cadena, protegido con contraseña

> ⚠ Exportar la **clave privada** (PKCS#12/PFX, JKS o archivo de clave) requiere el permiso **read:private_keys**, reservado a administradores. Los roles que no lo tienen, incluido el rol Operador integrado, deben recuperar las claves archivadas mediante el flujo de **Recuperación de claves**, sujeto a aprobación.

## Pares de certificados híbridos (RFC 9763)

Un par híbrido vincula un certificado clásico (**A**, RSA o EC) y uno poscuántico (**B**, ML-DSA) para el mismo sujeto. B incluye la extensión no crítica **relatedCertificate**, que nombra a A por su hash, de modo que una parte confiante pueda exigir ambos.

- **Emisión**: marque **Emitir un par híbrido (RFC 9763)** en el formulario Emitir certificado (o envíe \`hybrid\` en \`POST /api/v2/certificates\`) para emitir ambos desde la misma CA, con el mismo sujeto, nombres y validez. B copia las extensiones de A con su propio identificador de clave y uso de clave, y no declara ningún uso de clave ni EKU que A no tenga. Con los perfiles de cumplimiento ANSSI, BSI y EU ACM, ML-DSA-65 y ML-DSA-87 se aceptan solo como B: nunca solos, y ML-DSA-44 en ningún caso
- **Vinculación por solicitud**: una CSR con una **relatedCertRequest** firmada por la clave de A emite un B vinculado a A, mediante Firmar CSR, ACME, EST o WSTEP. A debe estar en UCM, ser válido, no revocado, de entidad final y emitido por una CA de esta instancia cuya cadena sea válida ahora, y la solicitud no debe tener más de 7 días. Un certificado más reciente que nombre el mismo A releva al par, y el anterior lo abandona. Un certificado indicado en línea en la ubicación de la solicitud debe ser A; otras ubicaciones no se descargan
- **Revocar** cualquiera de los miembros, solo o en lote, revoca el otro salvo que se desmarque **Revocar también el certificado vinculado**. Con una política que exige aprobación, el par va junto, y dos políticas de aprobación distintas en los dos miembros dejan la revocación a un administrador. Si el otro miembro no se puede revocar, la respuesta lo indica (\`related_not_revoked\`) y debe revocarse por separado. ACME revokeCert revoca solo el certificado presentado (RFC 8555)
- **Renovar** cualquiera de los miembros, a mano, en lote o automáticamente, renueva ambos, y el nuevo B nombra al nuevo A: UCM posee ambas claves y renueva el par como uno solo. Un miembro renovado solo nombra únicamente el certificado que nombraba su original: cuando este ya se ha renovado, revocado, archivado o expirado, el miembro renovado no lleva la extensión relatedCertificate y sale del par, y la renovación indica el motivo (un aviso tras una renovación desde esta página, el registro de auditoría en todos los casos). El otro miembro también sale del par cuando se elimina uno. Una renovación se rechaza, sin cambiar nada, cuando no se puede leer el otro miembro o la extensión relatedCertificate
- **Exportar**: el formato **Paquete híbrido** (hybrid-bundle) es un ZIP con ambos certificados y, si se incluye la clave, ambas claves privadas; se rechaza cuando ya ninguno de los certificados nombra al otro

> ⚠ Una política que exige aprobación rechaza por ahora emitir un par híbrido: emítalo bajo una política sin aprobación.

## Favoritos

Marque con una estrella ⭐ los certificados importantes para guardarlos como favoritos. Los favoritos se listan en la paleta de comandos (Ctrl+K).

## Comparar certificados

Marque de dos a cuatro certificados en la lista y haga clic en **Comparar** en la barra de selección para verlos lado a lado en una ventana separada (un diálogo en un teléfono): sujeto, emisor, validez, algoritmo y tamaño de clave, nombres alternativos, usos de la clave, huellas, número de serie y las demás extensiones, una columna por certificado. Una línea idéntica para todos se fusiona en una sola celda marcada *Identical*; una línea que difiere se marca con un trazo junto a su etiqueta, y en una lista (nombres, usos, extensiones) **+** marca el elemento que no tienen todos los certificados. **Mostrar solo las diferencias** oculta las líneas idénticas.

**Separar en una ventana**, entre las herramientas del inspector, abre el certificado en una ventana sobre la página con las mismas secciones y acciones. Varias ventanas permanecen abiertas a la vez, incluso en otras páginas: arrastre una por su barra de título, redimensiónela por un borde o una esquina, o use el botón de mover al inicio de su barra de título con las teclas de flecha (Mayús y las flechas redimensionan). Su botón de maximizar, o un doble clic en la barra de título, la extiende entre la barra superior y la barra de estado, y devuelve su lugar y su tamaño la vez siguiente; la ventana de comparación tiene el mismo botón. La barra de estado lista las ventanas abiertas para traer una al frente; la cruz o Escape la cierra.

## Filtrado y búsqueda

- **Pestañas de estado**: Todos, Por renovar, Válidos, Expirados, Revocados y Archivados, más Huérfanos cuando los hay; cada una muestra su recuento, salvo Archivados. La pestaña forma parte de la dirección, así que una recarga o un enlace compartido la conserva
- **Filtro por CA**: muestra los certificados de una CA específica
- **Filtro por origen**: filtra por cómo entró el certificado en UCM (emitido, importado, ACME, SCEP, etc.)
- **Filtro por plantilla** (en el diálogo **Filtros**, al final de la barra de herramientas, una etiqueta una vez activo): encuentra los certificados **modificados respecto a la plantilla**: emitidos desde una plantilla pero con el tipo de clave o la validez sobrescritos explícitamente al solicitarlos. Los campos divergentes se listan en el detalle del certificado; el registro queda congelado en la emisión
- **Búsqueda de texto**: busca por sujeto, emisor, nombre para mostrar, comentario o número de serie (los SAN no se buscan); la búsqueda se ejecuta cuando deja de escribir e indica cuántos resultados encontró
- **Filtros guardados**: el diálogo **Filtros**, al final de la barra de herramientas, guarda la búsqueda, el estado y los filtros bajo un nombre en este navegador, y aplica de nuevo un conjunto guardado
- **Exportar la lista**: el botón de exportación de la barra de herramientas exporta todos los resultados, y **Exportar…** de la barra de selección los certificados marcados: en PEM, o sus metadatos en CSV o JSON. Una vez marcada toda la página, **Seleccionar los N resultados** extiende la selección a todos los resultados
- **Ordenación**: por nombre, fecha de expiración, fecha de creación, estado
- **Columnas**: nombre común, descripción, estado, emisor, origen, vencimiento y algoritmo de clave por defecto; el botón **Columnas** añade la nota de cumplimiento, el vínculo híbrido, la fecha de creación y el comentario
- **Acciones de fila**: Exportar en la fila; las demás acciones, en el inspector que abre un clic en la fila: Exportar y Renovar en su encabezado, Renombrar, Revocar, Eliminar y el resto en su menú ⋯
- **Inspector**: se abre bajo la lista, dentro de los márgenes de la página, o a su derecha a partir de 1200 px de ancho; su lugar y su tamaño siguen a su cuenta en todas las páginas. Un certificado abierto desde otra página (la búsqueda, una aprobación, una autoridad) llega aquí, a este inspector. Arrastre su borde o use las teclas de flecha sobre él para redimensionarlo, pliéguelo a su franja de pestañas, agrándelo. Los certificados abiertos permanecen como pestañas; los que no caben pasan a un menú +N. Sus pestañas son Resumen, Cadena, Extensiones, Historial y PEM; Historial lista las fechas del registro y, con read:audit, las entradas de auditoría de este certificado entre las últimas 100 sobre certificados

## Análisis de conformidad

La acción **Analizar** (detalle del certificado) comprueba la conformidad con los estándares X.509. Solo informativo.

- **RFC 5280**: perfil X.509 del IETF, siempre relevante
- **CA/Browser Forum**: Baseline Requirements para certificados TLS públicos (ruido esperado en una PKI interna)
- Severidades: fatal / error / warning / notice / info
- Motor: pkilint (+ zlint si está presente): dependencia opcional del servidor, que se degrada con elegancia si falta
`
  }
}
