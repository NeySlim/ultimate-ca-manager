export default {
  helpContent: {
    title: 'Certificados',
    subtitle: 'Emitir, gestionar y supervisar certificados',
    overview: 'Gestión centralizada de todos los certificados X.509. Emita nuevos certificados desde sus CA, importe certificados existentes, controle las fechas de expiración y gestione las renovaciones y revocaciones.',
    sections: [
      {
        title: "Análisis de conformidad",
        content: "La acción « Analizar » en el detalle de un certificado lo pasa por analizadores de estándares y muestra los hallazgos. Solo informativo — nunca bloquea la emisión.",
        items: [
          { label: "Perfiles", text: "RFC 5280 (siempre relevante) y CA/Browser Forum Baseline Requirements (certificados TLS de servidor)" },
          { label: "Severidades", text: "Los hallazgos se clasifican: fatal, error, warning, notice, info" },
          { label: "Motor", text: "Impulsado por pkilint (y zlint si su binario está presente) — dependencia opcional del servidor" },
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
          { label: 'Renovar', text: 'In situ desde v2.214: mismos id/refid, nuevo número de serie y validez — el número de serie sustituido permanece en la CRL hasta la expiración antigua. Un certificado revocado no puede renovarse' },
          { label: 'Renombrar', text: 'Definir un nombre para mostrar independiente del CN (por defecto el CN o el primer nombre DNS de los SAN para certificados sin CN)' },
          { label: 'Revocar', text: 'Marcar como revocado con un motivo — aparecerá en la CRL' },
          { label: 'Levantar suspensión', text: 'Quitar la suspensión de un certificado revocado con el motivo «Suspensión de certificado» — lo restaura al estado válido' },
          { label: 'Revocar y reemplazar', text: 'Revocar y emitir inmediatamente un reemplazo' },
          { label: 'Exportar', text: 'Descargar en formato PEM, DER o PKCS#12' },
          { label: 'Modo compatibilidad PKCS#12 (v2.222)', text: 'Los diálogos de exportación ofrecen un perfil 3DES/SHA-1 para los importadores que rechazan el archivo AES-256 por defecto como contraseña incorrecta: Android 15 y anteriores, macOS 14 y anteriores, Windows Server 2016 y anteriores, Java antiguo. Desactivado por defecto, protege menos el archivo' },
          { label: 'Comparar', text: 'Comparación lado a lado de dos certificados' },
        ]
      },
      {
        title: 'EKU adicionales personalizados (RFC 5280 §4.2.1.12)',
        content: 'El formulario de emisión y el modal de firma de CSR muestran un selector múltiple "EKU adicionales" que añade OID Extended Key Usage por encima de los EKU por defecto del tipo de certificado:',
        items: [
          { label: 'Catálogo', text: '18 EKU conocidos (Microsoft RDP 1.3.6.1.4.1.311.54.1.2, smartcard logon, document signing, IPsec, Kerberos PKINIT, etc.)' },
          { label: 'OID libre', text: 'Cualquier OID punteado bien formado que cumpla ^[0-2](?:\\.(?:0|[1-9]\\d*)){1,15}$' },
          { label: 'Límite', text: 'Hasta 16 OID en total por certificado' },
          { label: 'Fusión, nunca reemplazo', text: 'Los EKU por defecto del tipo (por ej. serverAuth) permanecen fijos — los extras se añaden encima' },
          { label: 'Rechazado', text: 'anyExtendedKeyUsage (2.5.29.37.0) está explícitamente prohibido' },
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
        content: 'Envíe este certificado a hosts remotos por SSH/SFTP — solo administradores, los destinos se gestionan en Ajustes › Despliegue.',
        items: [
          { label: 'Asociar destino', text: 'Desde la vista de detalle del certificado: elija un destino de despliegue y defina rutas de destino absolutas para el certificado, la clave privada y/o la cadena completa (al menos una)' },
          { label: 'Mismo host', text: 'Para desplegar en el propio host de UCM, use un destino SFTP en 127.0.0.1 con una cuenta SSH dedicada; el servicio aislado no puede escribir fuera de su directorio de datos' },
          { label: 'Automático', text: 'En la emisión y renovación, los archivos vinculados se envían de nuevo y se ejecuta el comando de recarga del destino — las entregas se encolan con reintentos' },
          { label: 'Archivos', text: 'Se escriben de forma atómica en las rutas exactas configuradas (el directorio padre debe existir): clave 0600, certificado/cadena 0644' },
          { label: 'Desplegar ahora', text: 'Envío manual desde la vista de detalle, con el estado de entrega y el último error mostrados por destino' },
        ]
      },

    ],
    tips: [
      'Marque con estrella ⭐ los certificados importantes para añadirlos a su lista de favoritos',
      'Utilice los filtros para encontrar rápidamente certificados por estado, CA o texto de búsqueda — su selección se conserva tras recargar la página',
      'La renovación conserva el mismo registro (id, refid, fecha de creación) — las claves en poder de UCM se regeneran, los certificados inscritos por protocolo (SCEP/EST/ACME) conservan su clave del lado cliente',
      '¿Necesita un EKU no estándar (Microsoft RDP, smartcard logon, document signing)? Añádalo vía "EKU adicionales" en lugar de editar plantillas',
    ],
    warnings: [
      'La revocación es generalmente permanente — excepto para «Suspensión de certificado» que puede levantarse',
      'Un certificado válido no revocado no puede eliminarse (409) — revóquelo primero para que la revocación llegue a la CRL/OCSP; las revocaciones sobreviven a la eliminación',
    ],
  },
  helpGuides: {
    title: 'Certificados',
    content: `
## Descripción general

Gestión centralizada de todos los certificados X.509. Emita nuevos certificados, importe certificados existentes, controle las fechas de expiración, gestione las renovaciones y revocaciones.

## Estado del certificado

- **Válido** — Dentro del período de validez y no revocado
- **Por expirar** — Expirará dentro de 30 días (configurable)
- **Expirado** — Posterior a la fecha «Not After»
- **Revocado** — Revocado explícitamente, publicado en la CRL
- **Huérfano** — La CA emisora ya no existe en UCM
- **Archivado** — Sustituido por una renovación o reinscripción que conservó el registro antiguo como historial (SCEP, EST, WSTEP, ACME, respondedor OCSP)

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
- **PEM** — Certificados individuales o agrupados
- **DER** — Formato binario
- **PKCS#12 (P12/PFX)** — Certificado + clave + cadena (se requiere contraseña)
- **PKCS#7 (P7B)** — Cadena de certificados sin claves

## Renovar un certificado

Desde v2.214, la renovación actualiza el certificado **in situ**:
- Mismo registro: **id, refid y fecha de creación nunca cambian** — las integraciones conservan sus referencias
- Mismos Sujeto y SAN; nuevo número de serie y nuevo período de validez
- Los certificados cuya clave posee UCM se **regeneran con una clave nueva**; los certificados inscritos por protocolo (SCEP/EST/ACME) se vuelven a firmar con su clave pública existente
- El **número de serie sustituido permanece publicado en la CRL** (motivo \`superseded\`) y responde \`revoked\` vía OCSP hasta la expiración original del certificado antiguo
- \`renewed_at\` / \`renewed_times\` registran el historial de renovaciones
- Un certificado revocado no puede renovarse (409) — emita uno nuevo en su lugar

**Eliminación**: un certificado válido no revocado no puede eliminarse (409) — revóquelo primero para que las partes que confían vean el cambio. Las revocaciones se persisten independientemente del registro del certificado y sobreviven a la eliminación.

## Revocar un certificado

1. Seleccione el certificado → **Revocar**
2. Elija un motivo de revocación (Compromiso de clave, Compromiso de CA, Cambio de afiliación, Reemplazo, Cese de operación, Suspensión de certificado, etc.)
3. Confirme la revocación

Los certificados revocados se publican en la CRL en la próxima regeneración.

> ⚠ La revocación es generalmente permanente — excepto para la **Suspensión de certificado** que puede levantarse.

### Levantar suspensión

Si un certificado fue revocado con el motivo **Suspensión de certificado**, puede restaurarse al estado válido:

1. Abra los detalles del certificado revocado
2. El botón **Levantar suspensión** aparece en la barra de acciones (solo para revocaciones de tipo Suspensión de certificado)
3. Haga clic en **Levantar suspensión** para restaurar el certificado
4. El certificado vuelve al estado válido, la CRL se regenera y la caché OCSP se actualiza

> 💡 La suspensión de certificado es útil para suspensiones temporales (por ejemplo, dispositivo perdido, investigación en curso).

### Revocar y reemplazar
Combina la revocación con una reemisión inmediata. El nuevo certificado hereda el mismo sujeto y SAN.

## Exportar certificados

Formatos de exportación:
- **PEM** — Solo el certificado
- **PEM + Cadena** — Certificado con la cadena completa del emisor
- **DER** — Formato binario
- **PKCS#12** — Certificado + clave + cadena, protegido con contraseña

## Favoritos

Marque con estrella ⭐ los certificados importantes para guardarlos en favoritos. Los favoritos aparecen primero en las vistas filtradas y son accesibles desde el filtro de favoritos.

## Comparar certificados

Seleccione dos certificados y haga clic en **Comparar** para ver una comparación lado a lado de su sujeto, SAN, uso de la clave, validez y extensiones.

## Filtrado y búsqueda

- **Filtro por estado** — Válido, Por expirar, Expirado, Revocado, Huérfano, Archivado
- **Filtro por CA** — Mostrar certificados de una CA específica
- **Filtro por origen** — Filtrar por cómo entró el certificado en UCM (emitido, importado, ACME, SCEP, etc.)
- **Filtro por plantilla** — Encontrar certificados **modificados respecto a la plantilla**: emitidos desde una plantilla pero con el tipo de clave, la validez o el digest sobrescritos explícitamente al solicitarlos. Los campos divergentes se listan en el detalle del certificado; el registro queda congelado en la emisión
- **Búsqueda de texto** — Buscar por CN, número de serie o SAN
- **Ordenación** — Por nombre, fecha de expiración, fecha de creación, estado
## Análisis de conformidad

La acción **Analizar** (detalle del certificado) comprueba la conformidad con los estándares X.509. Solo informativo.

- **RFC 5280** — perfil X.509 del IETF, siempre relevante
- **CA/Browser Forum** — Baseline Requirements para certificados TLS públicos (ruido esperado en PKI interna)
- Severidades: fatal / error / warning / notice / info
- Motor: pkilint (+ zlint si está presente) — dependencia opcional del servidor, degradación elegante si falta

`
  }
}
