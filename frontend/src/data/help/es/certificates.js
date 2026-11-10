export default {
  helpContent: {
    title: 'Certificados',
    subtitle: 'Emitir, gestionar y supervisar certificados',
    overview: 'Gestión centralizada de todos los certificados X.509. Emita nuevos certificados desde sus CA, importe certificados existentes, controle las fechas de expiración y gestione las renovaciones y revocaciones.',
    sections: [
      {
        title: "Análisis de conformidad",
        content: "La acción « Analizar » en el detalle de un certificado lo pasa por analizadores de estándares y muestra los hallazgos. Solo informativo, nunca bloquea la emisión.",
        items: [
          { label: "Perfiles", text: "RFC 5280 (siempre relevante), CA/Browser Forum Baseline Requirements (certificados TLS de servidor) y ETSI EN 319 412 (certificados cualificados y relacionados con eIDAS, incluido qcStatements)" },
          { label: "Severidades", text: "Los hallazgos se clasifican: fatal, error, warning, notice, info" },
          { label: "Motor", text: "Impulsado por pkilint (y zlint si su binario está presente): dependencia opcional del servidor" },
          { label: "PKI interna", text: "Las reglas de CA/Browser Forum apuntan a certificados públicos; espere hallazgos no aplicables en una PKI interna" },
        ]
      },
      {
        title: 'Estado del certificado',
        definitions: [
          { term: 'Válido', description: 'Dentro del período de validez y no revocado' },
          { term: 'Por expirar', description: 'Expirará dentro de 30 días' },
          { term: 'Expirado', description: 'Posterior a la fecha «Not After»' },
          { term: 'Revocado', description: 'Revocado explícitamente (publicado en la CRL)' },
          { term: 'Huérfano', description: 'La CA emisora ya no existe en el sistema' },
          { term: 'Archivado', description: 'Sustituido por una renovación o reinscripción que conservó el registro antiguo como historial (SCEP, EST, WSTEP, ACME, respondedor OCSP); se lista con el filtro de estado «Archivado»' },
        ]
      },
      {
        title: 'Acciones',
        items: [
          { label: 'Emitir', text: 'Crear un nuevo certificado firmado por una de sus CA' },
          { label: 'Importar', text: 'Importar un certificado existente (PEM, DER o PKCS#12)' },
          { label: 'Renovar', text: 'In situ desde v2.214: mismos id/refid, nuevo número de serie y validez, el número de serie sustituido permanece en la CRL hasta la expiración antigua. Un certificado revocado no puede renovarse. Pide la validez del nuevo certificado en días, rellenada con la duración actual; las políticas y la expiración de la CA siguen limitándola' },
          { label: 'Renombrar', text: 'Definir un nombre para mostrar independiente del CN (por defecto el CN o el primer nombre DNS de los SAN para certificados sin CN)' },
          { label: 'Revocar', text: 'Marcar como revocado con un motivo, aparecerá en la CRL' },
          { label: 'Levantar suspensión', text: 'Quitar la suspensión de un certificado revocado con el motivo «Suspensión de certificado», lo restaura al estado válido' },
          { label: 'Revocar un certificado suspendido', text: 'Un certificado suspendido también puede revocarse de forma definitiva con otro motivo, sin pasar por válido. La CRL y OCSP dan entonces el nuevo motivo, y la fecha de invalidez es el inicio de la suspensión salvo que se indique una' },
          { label: 'Exportar', text: 'Descargar en formato PEM, DER, PKCS#12 o JKS' },
          { label: 'Modo compatibilidad PKCS#12 (v2.222)', text: 'Los diálogos de exportación ofrecen un perfil 3DES/SHA-1 para los importadores que rechazan el archivo AES-256 por defecto como contraseña incorrecta: Android 15 y anteriores, macOS 14 y anteriores, Windows Server 2016 y anteriores, Java antiguo. Desactivado por defecto, protege menos el archivo' },
          { label: 'Comparar', text: 'Comparación lado a lado de dos certificados' },
          { label: 'Otras extensiones (v2.251)', text: 'Los detalles del certificado y de la CA enumeran bajo Otras extensiones las que UCM no tiene sección para mostrar, con su OID, nombre si se conoce, criticidad y valor sin procesar. El formulario de emisión puede añadir extensiones personalizadas además de las de la plantilla' },
          { label: 'Claves comprometidas (v2.251)', text: 'Una clave revocada como keyCompromise sigue conocida tras eliminar su certificado, sea cual sea la CA que lo emitió, Let\'s Encrypt incluida: el cliente ACME la rechaza en la solicitud, la renovación y la finalización, y EST rechaza un CSR que la lleve. Las demás rutas de emisión no consultan esta lista' },
          { label: 'Certificados del cliente ACME (v2.251)', text: 'Un certificado obtenido por el cliente ACME también se renueva in situ, conservando su id y su refid. Las copias que renovaciones anteriores importaron como filas nuevas permanecen en el inventario hasta que se archivan o eliminan' },
        ]
      },
      {
        title: 'EKU adicionales personalizados (RFC 5280 §4.2.1.12)',
        content: 'El formulario de emisión y el modal de firma de CSR muestran un selector múltiple "EKU adicionales" que añade OID Extended Key Usage por encima de los EKU por defecto del tipo de certificado:',
        items: [
          { label: 'Catálogo', text: '26 EKU conocidos (Microsoft RDP 1.3.6.1.4.1.311.54.1.2, smartcard logon, document signing, IPsec, Kerberos PKINIT, etc.)' },
          { label: 'OID libre', text: 'Cualquier OID punteado bien formado que cumpla ^[0-2](?:\\.(?:0|[1-9]\\d*)){1,15}$' },
          { label: 'Límite', text: 'Hasta 16 OID en total por certificado' },
          { label: 'Fusión, nunca reemplazo', text: 'Los EKU por defecto del tipo (por ej. serverAuth) permanecen fijos, los extras se añaden encima' },
          { label: 'Rechazado', text: 'anyExtendedKeyUsage (2.5.29.37.0) está explícitamente prohibido' },
        ]
      },
      {
        title: 'Pares de certificados híbridos (RFC 9763)',
        content: 'Un certificado clásico (A) y uno ML-DSA (B) para el mismo sujeto, vinculados: B incluye la extensión relatedCertificate que nombra a A por su hash. Los clientes que conocen ML-DSA comprueban ambos; los demás siguen usando A.',
        items: [
          { label: 'Emisión', text: 'Marque "Emitir un par híbrido (RFC 9763)" en el formulario de emisión de certificados y elija la clave clásica y el nivel ML-DSA; ambos salen de la misma CA, con el mismo sujeto, nombres y validez, y B no declara ningún key usage ni EKU que A no tenga. Solo se ofrece cuando las políticas de la CA permiten ambos, nunca en modo FIPS. Con los perfiles ANSSI, BSI y EU ACM, ML-DSA-65 y ML-DSA-87 se ofrecen solo en el par. Una política que exige aprobación rechaza el par por ahora' },
          { label: 'Vinculado por solicitud', text: 'Un CSR con una relatedCertRequest firmada por la clave de A (Firmar CSR, ACME, EST, WSTEP) emite un B vinculado a A. A debe estar en UCM, ser válido, no revocado y de entidad final; un B más reciente que nombre el mismo A releva al par' },
          { label: 'Vinculado', text: 'Cada miembro muestra una insignia Vinculado en la lista y en sus detalles, con un enlace que abre el otro miembro' },
          { label: 'Revocación', text: 'Revocar un miembro, solo o en lote, revoca también el otro salvo que desmarque "Revocar también el certificado vinculado", p. ej. para conservar A cuando solo la clave ML-DSA está comprometida; con una política que exige aprobación, ambos van juntos. Una advertencia nombra al otro miembro cuando no se pudo revocar. La revocación ACME revoca solo el certificado presentado' },
          { label: 'Renovación', text: 'Renovar uno de los miembros renueva ambos, manualmente, en lote o automáticamente, y el nuevo B nombra al nuevo A. Un miembro renovado solo, estando el otro revocado, sale del par' },
          { label: 'Exportación', text: 'El formato Paquete híbrido descarga un ZIP con ambos certificados y, si incluye la clave y puede exportar claves, ambas claves' },
        ]
      },
      {
        title: 'Archivos de certificado en disco (v2.140)',
        items: [
          { label: 'Auto-materializados', text: 'Los archivos .crt / .key se escriben en data/certs/ en cada ruta de creación (UI, firma CSR, ACME, SCEP, importación)' },
          { label: 'CA también', text: 'Los archivos .crt / .key de las CA se escriben en data/cas/ por el mismo mecanismo' },
          { label: 'Red de seguridad', text: 'Un escaneo de regeneración al arranque reconstruye cualquier archivo faltante desde la base de datos' },
          { label: 'No bloqueante', text: 'Los errores de escritura se loggean pero nunca abortan la transacción de DB' },
        ]
      },
      {
        title: 'Despliegue (v2.215)',
        content: 'Envíe este certificado a hosts remotos por SSH/SFTP o a una API HTTP, solo administradores, los destinos se gestionan en Ajustes › Despliegue.',
        items: [
          { label: 'Asociar destino', text: 'Desde la vista de detalle del certificado: elija un destino de despliegue y defina rutas de destino absolutas para el certificado, la clave privada y/o la cadena completa (al menos una). La cadena completa omite la CA raíz salvo que se marque Incluir CA raíz' },
          { label: 'API HTTP (v2.252)', text: "Un destino HTTP no usa rutas: en la emisión, la renovación y Desplegar ahora, UCM envía una solicitud construida a partir de la plantilla de cuerpo del destino (certificado, cadena, sujeto, número de serie y la clave privada solo si el destino lo permite)" },
          { label: 'Mismo host', text: 'Para desplegar en el propio host de UCM, use un destino SFTP en 127.0.0.1 con una cuenta SSH dedicada; el servicio aislado no puede escribir fuera de su directorio de datos' },
          { label: 'Automático', text: 'En la emisión y renovación, los archivos vinculados se envían de nuevo y se ejecuta el comando de recarga opcional de ese despliegue; las entregas se encolan con reintentos' },
          { label: 'Archivos', text: 'Se escriben de forma atómica en las rutas exactas configuradas (el directorio padre debe existir): clave 0600, certificado/cadena 0644' },
          { label: 'Desplegar ahora', text: 'Envío manual desde la vista de detalle, con el estado de entrega y el último error mostrados por destino' },
        ]
      },

    ],
    tips: [
      'Marque con estrella ⭐ los certificados importantes para añadirlos a su lista de favoritos',
      'Utilice los filtros para encontrar rápidamente certificados por estado, CA o texto de búsqueda: su selección se conserva tras recargar la página',
      'La renovación conserva el mismo registro (id, refid, fecha de creación). Renovar desde la página genera una clave nueva; la renovación automática conserva la clave. Un certificado cuya clave UCM no posee (inscripción SCEP, EST, WSTEP o ACME, importación sin la clave) se rechaza (409): renuévelo mediante su protocolo o firme una nueva solicitud',
      '¿Necesita un EKU no estándar (Microsoft RDP, smartcard logon, document signing)? Añádalo vía "EKU adicionales" en lugar de editar plantillas',
      'Cuando una política o la expiración de la CA emisora acorta la validez solicitada, el resultado lo indica: "Issued for N day(s) instead of the M requested", con el motivo',
      'Una firma RSA-PSS se muestra con su hash y la longitud de sal, p. ej. RSASSA-PSS SHA-256 (salt 32)',
      'En una vista de enlace (abierta desde el resumen), el botón Borrar todos los filtros que aparece cuando nada coincide vacía los estados del enlace y la búsqueda y conserva los demás filtros del enlace; quitar un chip elimina ese filtro, el botón Borrar de la fila de chips sale de la vista de enlace, y sus filtros guardados no se tocan',
    ],
    warnings: [
      'La revocación es generalmente permanente: excepto para «Suspensión de certificado» que puede levantarse',
      'Un certificado válido no revocado no puede eliminarse por sí solo: Eliminar explica el motivo y ofrece «Revocar y luego eliminar», para que la revocación llegue a la CRL/OCSP; las revocaciones sobreviven a la eliminación',
      'UCM firma solo con SHA-256, SHA-384 o SHA-512: SHA-224 y los nombres de hash desconocidos se rechazan en lugar de sustituirse por SHA-256',
    ],
  },
  helpGuides: {
    title: 'Certificados',
    content: `
## Descripción general

Gestión centralizada de todos los certificados X.509. Emita nuevos certificados, importe certificados existentes, controle las fechas de expiración, gestione las renovaciones y revocaciones.

## Estado del certificado

- **Válido**: Dentro del período de validez y no revocado
- **Por expirar**: Expirará dentro de 30 días
- **Expirado**: Posterior a la fecha «Not After»
- **Revocado**: Revocado explícitamente, publicado en la CRL
- **Huérfano**: La CA emisora ya no existe en UCM
- **Archivado**: Sustituido por una renovación o reinscripción que conservó el registro antiguo como historial (SCEP, EST, WSTEP, ACME, respondedor OCSP)

## Emitir un certificado

1. Haga clic en **Emitir certificado**
2. Seleccione la **CA de firma** (debe poseer una clave privada)
3. Complete el sujeto (CN es obligatorio, los demás campos son opcionales)
4. Añada nombres alternativos del sujeto (SAN): nombres DNS, IP, correos electrónicos
5. Elija el tipo y tamaño de la clave
6. Establezca el período de validez
7. Opcionalmente aplique una **plantilla** para prerellenar la configuración
8. Haga clic en **Emitir**

### Uso de plantillas
Las plantillas prerellenan el uso de la clave, el uso extendido de la clave, los valores predeterminados del sujeto y la validez. Seleccione una plantilla antes de rellenar el formulario para ahorrar tiempo.

## Importar certificados

Formatos admitidos:
- **PEM**: Certificados individuales o agrupados
- **DER**: Formato binario
- **PKCS#12 (P12/PFX)**: Certificado + clave + cadena (se requiere contraseña)
- **PKCS#7 (P7B)**: Cadena de certificados sin claves

## Renovar un certificado

Desde v2.214, la renovación actualiza el certificado **in situ**:
- Mismo registro: **id, refid y fecha de creación nunca cambian**: las integraciones conservan sus referencias
- Mismos Sujeto y SAN; nuevo número de serie y nuevo período de validez
- Renovar desde la página genera una **clave nueva**; la renovación automática conserva la clave
- Un certificado cuya clave UCM no posee (inscripción SCEP, EST, WSTEP o ACME, importación sin la clave) se rechaza (409): renuévalo mediante su protocolo de inscripción o firma una nueva solicitud
- El **número de serie sustituido permanece publicado en la CRL** (motivo \`superseded\`) y responde \`revoked\` vía OCSP hasta la expiración original del certificado antiguo
- \`renewed_at\` / \`renewed_times\` registran el historial de renovaciones
- Un certificado revocado no puede renovarse (409): emita uno nuevo en su lugar
- **Renovar** pide la validez del nuevo certificado en días, rellenada con la duración actual; las políticas de emisión y la expiración de la CA siguen limitándola

**Eliminación**: un certificado válido no revocado no puede eliminarse por sí solo: **Eliminar** explica el motivo y ofrece **Revocar y luego eliminar**, para que las partes que confían vean el cambio. Las revocaciones se persisten independientemente del registro del certificado y sobreviven a la eliminación.

## Revocar un certificado

1. Seleccione el certificado → **Revocar**
2. Elija un motivo de revocación (Compromiso de clave, Compromiso de CA, Cambio de afiliación, Reemplazo, Cese de operación, Suspensión de certificado, etc.)
3. Confirme la revocación

Los certificados revocados se publican en la CRL en la próxima regeneración.

> ⚠ La revocación es generalmente permanente: excepto para la **Suspensión de certificado** que puede levantarse.

### Levantar suspensión

Si un certificado fue revocado con el motivo **Suspensión de certificado**, puede restaurarse al estado válido:

1. Abra los detalles del certificado revocado
2. El botón **Levantar suspensión** aparece en la barra de acciones (solo para revocaciones de tipo Suspensión de certificado)
3. Haga clic en **Levantar suspensión** para restaurar el certificado
4. El certificado vuelve al estado válido, la CRL se regenera y la caché OCSP se actualiza

> 💡 La suspensión de certificado es útil para suspensiones temporales (por ejemplo, dispositivo perdido, investigación en curso).

### Revocar definitivamente un certificado suspendido

Un certificado suspendido puede revocarse con otro motivo (por ejemplo Compromiso de clave cuando la investigación lo confirme) desde el mismo botón **Revocar**, sin pasar antes a válido. La CRL y OCSP dan el nuevo motivo; salvo que se indique una fecha de invalidez, el inicio de la suspensión se registra como la fecha en que el certificado pasó a ser inválido.

## Exportar certificados

Formatos de exportación:
- **PEM**: Solo el certificado
- **PEM + Cadena**: Certificado con sus CAs emisoras (**Incluir cadena CA**); la CA raíz solo se añade si está marcada **Incluir CA raíz**
- **DER**: Formato binario
- **PKCS#12**: Certificado + clave + cadena, protegido con contraseña

## Pares de certificados híbridos (RFC 9763)

Un par híbrido vincula un certificado clásico (**A**, RSA o EC) y uno poscuántico (**B**, ML-DSA) para el mismo sujeto. B incluye la extensión no crítica **relatedCertificate**, que nombra a A por su hash, de modo que una parte confiante pueda exigir ambos.

- **Emisión**: marque **Emitir un par híbrido (RFC 9763)** en el formulario de emisión de certificados (o envíe \`hybrid\` en \`POST /api/v2/certificates\`) para emitir ambos desde la misma CA, con el mismo sujeto, nombres y validez. B copia las extensiones de A con su propio identificador de clave y key usage, y no declara ningún key usage ni EKU que A no tenga. Con los perfiles de conformidad ANSSI, BSI y EU ACM, ML-DSA-65 y ML-DSA-87 se aceptan solo como B: nunca solos, y ML-DSA-44 en ningún caso
- **Vinculación por solicitud**: un CSR con una **relatedCertRequest** firmada por la clave de A emite un B vinculado a A, mediante Firmar CSR, ACME, EST o WSTEP. A debe estar en UCM, ser válido, no revocado, de entidad final y emitido por una CA de esta instancia cuya cadena sea válida ahora, y la solicitud no debe tener más de 7 días. Un certificado más reciente que nombre el mismo A releva al par, y el anterior lo abandona. Un certificado indicado en línea en la ubicación de la solicitud debe ser A; otras ubicaciones no se descargan
- **Revocación** de uno de los miembros, solo o en lote, revoca el otro salvo que se desmarque **Revocar también el certificado vinculado**. Con una política que exige aprobación, el par va junto, y dos políticas de aprobación distintas en los dos miembros dejan la revocación a un administrador. Si el otro miembro no se puede revocar, la respuesta lo indica (\`related_not_revoked\`) y debe revocarse por separado. ACME revokeCert revoca solo el certificado presentado (RFC 8555)
- **Renovación** de uno de los miembros, manual, en lote o automática, renueva ambos, y el nuevo B nombra al nuevo A. Un miembro renovado solo, estando el otro revocado, sale del par, al igual que el otro miembro cuando se elimina uno
- **Exportación**: el formato **hybrid-bundle** es un ZIP con ambos certificados y, si se incluye la clave, ambas claves privadas; se rechaza cuando ya ninguno de los certificados nombra al otro

> ⚠ Una política que exige aprobación rechaza por ahora emitir un par híbrido: emítalo bajo una política sin aprobación.

## Favoritos

Marque con estrella ⭐ los certificados importantes para guardarlos en favoritos. Los favoritos se listan en la paleta de comandos (Ctrl+K).

## Comparar certificados

Seleccione dos certificados y haga clic en **Comparar** para ver una comparación lado a lado de su sujeto, SAN, uso de la clave, validez y extensiones.

## Filtrado y búsqueda

- **Filtro por estado**: Válido, Por expirar, Expirado, Revocado, Huérfano, Archivado
- **Filtro por CA**: Mostrar certificados de una CA específica
- **Filtro por origen**: Filtrar por cómo entró el certificado en UCM (emitido, importado, ACME, SCEP, etc.)
- **Filtro por plantilla**: Encontrar certificados **modificados respecto a la plantilla**: emitidos desde una plantilla pero con el tipo de clave o la validez sobrescritos explícitamente al solicitarlos. Los campos divergentes se listan en el detalle del certificado; el registro queda congelado en la emisión
- **Búsqueda de texto**: Buscar por sujeto, emisor, nombre para mostrar o número de serie (los SAN no se buscan)
- **Ordenación**: Por nombre, fecha de expiración, fecha de creación, estado
## Análisis de conformidad

La acción **Analizar** (detalle del certificado) comprueba la conformidad con los estándares X.509. Solo informativo.

- **RFC 5280**: perfil X.509 del IETF, siempre relevante
- **CA/Browser Forum**: Baseline Requirements para certificados TLS públicos (ruido esperado en PKI interna)
- Severidades: fatal / error / warning / notice / info
- Motor: pkilint (+ zlint si está presente): dependencia opcional del servidor, degradación elegante si falta

`
  }
}
