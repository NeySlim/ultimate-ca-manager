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
          { label: 'Descargar CRL', text: 'Descargar la CRL en PEM (archivo .crl); la forma DER se sirve en la URL del CDP' },
          { label: 'Despliegue de CRL', text: 'Asociar un destino SSH/SFTP para enviar automáticamente cada CRL regenerada. Cada vinculación define el formato PEM o DER, la ruta de destino, las CRL padre opcionales y su propio comando de recarga' },
          { label: 'CDP URL', text: 'URL del punto de distribución de CRL para incluir en los certificados' },
          { label: 'Validez', text: 'Validez de la CRL por CA desde 1 día hasta 5 años (90d/180d/1y/3y/5y para CAs sin conexión que no pueden volver a firmar según el calendario). Aparece una advertencia pasado un año, las partes que confían pueden conservar datos de revocación obsoletos durante toda la ventana' },
          { label: 'Resumen de firma', text: 'SHA-256, SHA-384 o SHA-512 para una CA RSA o EC. Una CA Ed25519, Ed448 o ML-DSA firma sin resumen: un resumen almacenado antes se muestra como ignorado, con un botón Borrar' },
          { label: 'Resumen predeterminado (v2.251)', text: 'Sin un resumen definido, una CA P-384 o P-521 firma sus CRL con SHA-384 o SHA-512. Las CRL ya emitidas conservan el suyo: la siguiente lo aplica' },
          { label: 'CRL externa', text: 'Las CAs sin clave o sin conexión no pueden autofirmar una CRL, suba una generada junto a la clave sin conexión desde el panel de detalles de la CA; se valida (firma, emisor, monotonía) y se sirve en la misma URL de CDP (v2.215)' },
          { label: 'CRL delta', text: 'Con las CRL delta activadas, se genera una nueva delta justo después de cada CRL completa, de modo que la delta servida siempre se refiere a la última base' },
          { label: 'Número de CRL', text: 'Las CRL base y delta de una CA comparten un número creciente, nunca dado a dos CRL, ni siquiera cuando dos generaciones se ejecutan a la vez. El número más alto alcanzado se conserva por nombre y clave de CA y viaja en las copias de seguridad, de modo que una CA restaurada en otro servidor, o eliminada e importada de nuevo, continúa desde él' },
        ]
      },
      {
        title: 'Servicio OCSP',
        items: [
          { label: 'Estado', text: 'Indica si el respondedor OCSP está activo para cada CA' },
          { label: 'AIA URL', text: 'URLs de acceso a información de autoridad, puntos de acceso del respondedor OCSP y descarga del certificado del emisor CA incluidos en los certificados emitidos' },
          { label: 'Caché', text: 'Caché de respuestas con limpieza diaria automática de las entradas expiradas' },
          { label: 'Total de consultas', text: 'Número de solicitudes OCSP respondidas desde que arrancó el servicio, y cuántas se sirvieron desde la caché' },
          { label: 'Caché HTTP', text: 'Las cachés HTTP pueden conservar una respuesta sin nonce hasta su nextUpdate, una hora como máximo (RFC 5019 §6.2: Expires, Last-Modified, ETag); una respuesta con nonce no se reutiliza' },
          { label: 'Respondedor delegado', text: 'Firma las respuestas con un certificado OCSPSigning dedicado en lugar de la clave de la CA, asigne uno por CA desde el panel de detalles' },
          { label: 'Auto-renovación del respondedor', text: 'Una tarea diaria reemite el certificado del respondedor delegado antes de que expire (mismo par de claves, renovado a la par) y lo vuelve a vincular, activado por defecto. El interruptor y su ventana (días antes de la expiración, 30 por defecto) están en Ajustes › Seguridad' },
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
- **Cantidad de revocados**: Número de certificados en la CRL
- **Última regeneración**: Cuándo se reconstruyó la CRL por última vez
- **Auto-regeneración**: Si las actualizaciones automáticas de la CRL están activadas

### Regenerar una CRL
Haga clic en **Regenerar** para reconstruir la CRL de una CA inmediatamente. Esto es útil después de revocar certificados.

### Auto-regeneración
Active la auto-regeneración para reconstruir automáticamente la CRL cada vez que se revoque un certificado. Active esta opción por CA.

### Validez de la CRL
El calendario de la CRL (por CA) establece cuánto tiempo permanece válida cada CRL publicada. Las opciones van de **1 día a 5 años**: 1d, 2d, 3d, 7d, 14d, 30d, 90d, 180d, 1y, 3y, 5y.

- **Las CAs en línea** deberían mantener una validez corta (días) para que las partes que confían recojan las revocaciones rápidamente
- **Las CAs sin conexión** (típicamente una raíz que no puede volver a firmar las CRL según el calendario) son el caso de uso previsto para las opciones largas: de 90d a 5y
- Se muestra una advertencia pasado un año: las partes que confían pueden conservar datos de revocación obsoletos durante toda la ventana de validez

### Números de CRL
Cada CRL lleva un número de CRL (RFC 5280 §5.2.3). Las CRL base y delta de una CA comparten una secuencia creciente, y ningún número se da a dos CRL, ni siquiera cuando una revocación y el programador generan una a la vez.

El número más alto alcanzado se conserva para cada nombre y clave de CA, fuera de la propia CA, y viaja en las copias de seguridad. Una CA restaurada en otro servidor, o eliminada e importada de nuevo, continúa desde él en lugar de empezar de nuevo en 1.

### Punto de distribución de CRL (CDP)
La URL del CDP se incluye en los certificados para que los clientes sepan dónde descargar la CRL. Copie la URL desde los detalles de la CRL.

\`\`\`
http://su-servidor:8080/cdp/{ca_refid}.crl
\`\`\`

> 💡 **Activación automática**: Al crear una nueva CA, el CDP se activa automáticamente si hay una URL base de protocolo o un servidor de protocolo HTTP configurado. La URL del CDP se genera automáticamente, no se requieren pasos manuales.

> ⚠️ **Importante**: Las URLs se generan automáticamente usando el puerto del protocolo HTTP y el FQDN del servidor. Si accede a UCM mediante \`localhost\`, la URL no puede generarse. Configure su **FQDN** o **URL base de protocolo** en Configuración → General primero.

### Descargar CRL
El botón de descarga guarda la CRL en PEM (un archivo .crl). La URL del CDP la sirve en DER para los clientes y otros sistemas.

## Respondedor OCSP

### ¿Qué es OCSP?
OCSP proporciona verificación del estado de certificados en tiempo real. En lugar de descargar una CRL completa, los clientes envían una consulta para un certificado específico y obtienen una respuesta inmediata.

### Estado de OCSP
La sección OCSP muestra:
- **Estado del respondedor**: Activo o inactivo por CA
- **Total de consultas**: Número de solicitudes OCSP respondidas desde que arrancó el servicio, y cuántas procedían de la caché
- **Caché**: Caché de respuestas con limpieza diaria automática de entradas expiradas

### Caché OCSP

UCM almacena en caché las respuestas OCSP para mejorar el rendimiento. La caché se:
- **Limpia automáticamente**: Las respuestas expiradas se eliminan diariamente por el programador
- **Invalida al revocar**: Cuando un certificado se revoca, su respuesta OCSP en caché se elimina inmediatamente
- **Invalida al levantar suspensión**: Cuando se levanta una suspensión de certificado, la caché OCSP se actualiza

### Respondedor OCSP delegado

Por defecto, las respuestas OCSP se firman con la propia clave de la CA. Un **respondedor delegado** utiliza en su lugar un certificado dedicado con el EKU **OCSPSigning**: asigne uno por CA desde el panel de detalles de la CA (solo son elegibles los certificados que llevan el EKU OCSPSigning y una clave privada).

**Renovación automática**: una tarea diaria reemite el certificado del respondedor antes de que expire, mismo par de claves y extensiones, renovado a la par, y vuelve a vincular la configuración del respondedor de la CA al nuevo certificado. Los certificados de firma OCSP de corta duración (por ejemplo, una plantilla de 90 días) rotan sin acción manual. Activado por defecto; puede desactivarse y la ventana de renovación ajustarse en Ajustes › Seguridad.

### URLs AIA
La extensión de acceso a información de autoridad (AIA) se incluye en los certificados para indicar a los clientes dónde encontrar:

**Respondedor OCSP**: verificación de revocación en tiempo real:
\`\`\`
http://su-servidor:8080/ocsp
\`\`\`

**CA Issuers** (RFC 5280 §4.2.2.1): descargar el certificado de la CA emisora para construir la cadena:
\`\`\`
http://su-servidor:8080/ca/{ca_refid}.cer   (formato DER)
http://su-servidor:8080/ca/{ca_refid}.pem   (formato PEM)
\`\`\`

Active CA Issuers por CA en la sección **AIA CA Issuers** del panel de detalles. La URL se genera automáticamente usando el servidor de protocolo HTTP y el FQDN configurado.

> ⚠️ **Requisito previo**: Las URLs de protocolo (CDP, OCSP, AIA) requieren un **FQDN** válido o una **URL base de protocolo** configurada en Configuración → General. Si accede a UCM mediante \`localhost\`, activar estas funciones fallará, configure el FQDN primero.

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
