export default {
  helpContent: {
    title: 'CRL & OCSP',
    subtitle: 'Servicios de revocación de certificados',
    overview: 'Gestione las listas de revocación de certificados (CRL) y los servicios del protocolo de estado de certificados en línea (OCSP). Estos servicios permiten a los clientes verificar si un certificado ha sido revocado.',
    sections: [
      {
        title: 'Gestión de CRL',
        items: [
          { label: 'Auto-regeneración', text: 'Activar la regeneración automática de CRL por CA' },
          { label: 'Regenerar manualmente', text: 'Forzar la regeneración inmediata de la CRL' },
          { label: 'Descargar CRL', text: 'Descargar el archivo CRL en formato DER o PEM' },
          { label: 'CDP URL', text: 'URL del punto de distribución de CRL para incluir en los certificados' },
        ]
      },
      {
        title: 'Servicio OCSP',
        items: [
          { label: 'Estado', text: 'Indica si el respondedor OCSP está activo para cada CA' },
          { label: 'AIA URL', text: 'URLs de acceso a información de autoridad — puntos de acceso del respondedor OCSP y descarga del certificado del emisor CA incluidos en los certificados emitidos' },
          { label: 'Caché', text: 'Caché de respuestas con limpieza diaria automática de las entradas expiradas' },
          { label: 'Total de consultas', text: 'Número de solicitudes OCSP procesadas' },
        ]
      },
    ],
    tips: [
      'Active la auto-regeneración para mantener las CRL actualizadas tras las revocaciones de certificados',
      'Copie las URLs de CDP, OCSP y AIA CA Issuers para incluirlas en sus perfiles de certificados',
      'OCSP proporciona verificación de revocación en tiempo real y es preferible a CRL',
    ],
  },
  helpGuides: {
    title: 'CRL & OCSP',
    content: `
## Descripción general

Las listas de revocación de certificados (CRL) y el protocolo de estado de certificados en línea (OCSP) permiten a los clientes verificar si un certificado ha sido revocado. UCM soporta ambos mecanismos.

## Gestión de CRL

### ¿Qué es una CRL?
Una CRL es una lista firmada de números de serie de certificados revocados, publicada por una CA. Los clientes descargan la CRL y verifican si el número de serie de un certificado aparece en ella.

### CRL por CA
Cada CA tiene su propia CRL. La lista de CRL muestra todas sus CA con:
- **Cantidad de revocados** — Número de certificados en la CRL
- **Última regeneración** — Cuándo se reconstruyó la CRL por última vez
- **Auto-regeneración** — Si las actualizaciones automáticas de la CRL están activadas

### Regenerar una CRL
Haga clic en **Regenerar** para reconstruir la CRL de una CA inmediatamente. Esto es útil después de revocar certificados.

### Auto-regeneración
Active la auto-regeneración para reconstruir automáticamente la CRL cada vez que se revoque un certificado. Active esta opción por CA.

### Punto de distribución de CRL (CDP)
La URL del CDP se incluye en los certificados para que los clientes sepan dónde descargar la CRL. Copie la URL desde los detalles de la CRL.

\`\`\`
http://su-servidor:8080/cdp/{ca_refid}.crl
\`\`\`

> 💡 **Activación automática**: Al crear una nueva CA, el CDP se activa automáticamente si hay una URL base de protocolo o un servidor de protocolo HTTP configurado. La URL del CDP se genera automáticamente — no se requieren pasos manuales.

> ⚠️ **Importante**: Las URLs se generan automáticamente usando el puerto del protocolo HTTP y el FQDN del servidor. Si accede a UCM mediante \`localhost\`, la URL no puede generarse. Configure su **FQDN** o **URL base de protocolo** en Configuración → General primero.

### Descargar CRL
Descargue las CRL en formato DER o PEM para distribuirlas a los clientes o integrarlas con otros sistemas.

## Respondedor OCSP

### ¿Qué es OCSP?
OCSP proporciona verificación del estado de certificados en tiempo real. En lugar de descargar una CRL completa, los clientes envían una consulta para un certificado específico y obtienen una respuesta inmediata.

### Estado de OCSP
La sección OCSP muestra:
- **Estado del respondedor** — Activo o inactivo por CA
- **Total de consultas** — Número de solicitudes OCSP procesadas
- **Caché** — Caché de respuestas con limpieza diaria automática de entradas expiradas

### Caché OCSP

UCM almacena en caché las respuestas OCSP para mejorar el rendimiento. La caché se:
- **Limpia automáticamente** — Las respuestas expiradas se eliminan diariamente por el programador
- **Invalida al revocar** — Cuando un certificado se revoca, su respuesta OCSP en caché se elimina inmediatamente
- **Invalida al levantar suspensión** — Cuando se levanta una suspensión de certificado, la caché OCSP se actualiza

### URLs AIA
La extensión de acceso a información de autoridad (AIA) se incluye en los certificados para indicar a los clientes dónde encontrar:

**Respondedor OCSP** — verificación de revocación en tiempo real:
\`\`\`
http://su-servidor:8080/ocsp
\`\`\`

**CA Issuers** (RFC 5280 §4.2.2.1) — descargar el certificado de la CA emisora para construir la cadena:
\`\`\`
http://su-servidor:8080/ca/{ca_refid}.cer   (formato DER)
http://su-servidor:8080/ca/{ca_refid}.pem   (formato PEM)
\`\`\`

Active CA Issuers por CA en la sección **AIA CA Issuers** del panel de detalles. La URL se genera automáticamente usando el servidor de protocolo HTTP y el FQDN configurado.

> ⚠️ **Requisito previo**: Las URLs de protocolo (CDP, OCSP, AIA) requieren un **FQDN** válido o una **URL base de protocolo** configurada en Configuración → General. Si accede a UCM mediante \`localhost\`, activar estas funciones fallará — configure el FQDN primero.

### OCSP vs CRL

| Característica | CRL | OCSP |
|----------------|-----|------|
| Frecuencia de actualización | Periódica | Tiempo real |
| Ancho de banda | Lista completa cada vez | Consulta individual |
| Privacidad | Sin seguimiento | El servidor ve las consultas |
| Soporte sin conexión | Sí (en caché) | Requiere conectividad |

> 💡 Buena práctica: active tanto CRL como OCSP para máxima compatibilidad.
`
  }
}
