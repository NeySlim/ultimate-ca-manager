export default {
  helpContent: {
    title: 'CRL & OCSP',
    subtitle: 'Servicios de revocación de certificados',
    overview: 'Gestionar las listas de revocación de certificados (CRL) y los servicios OCSP (Online Certificate Status Protocol). Estos servicios permiten a los clientes verificar si un certificado ha sido revocado.',
    sections: [
      {
        title: 'Gestión de CRL',
        items: [
          { label: 'Lista y detalle', text: 'Cada autoridad con su número de CRL, su publicación, su próxima actualización, OCSP y un estado leído de las fechas de la CRL (Al día, Menos de 24 h, Expirada, Sin CRL). Un nombre abre su detalle: Vista general, Publicación (programación, CRL delta, despliegue), OCSP (respondedor, respondedor delegado) y Puntos de distribución (URL con nombre, URL de CDP, OCSP y CA Issuers, CPS)' },
          { label: 'Regeneración automática', text: 'Activar o desactivar la regeneración automática de la CRL por CA, en la pestaña Publicación de su detalle' },
          { label: 'Regenerar manualmente', text: 'Forzar la regeneración inmediata de la CRL' },
          { label: 'Descargar la CRL', text: 'Descargar la CRL en PEM (archivo .crl); la forma DER se sirve en la URL del CDP' },
          { label: 'Despliegue de CRL', text: 'Vincular un destino SSH/SFTP para enviar automáticamente cada CRL regenerada. Cada vínculo elige PEM o DER, su ruta de destino, las CRL superiores opcionales y su propio comando de recarga' },
          { label: 'URL del CDP', text: 'URL del punto de distribución de CRL que se incorpora a los certificados' },
          { label: 'Validez', text: 'Validez de la CRL por CA, de 1 día a 5 años (90d/180d/1y/3y/5y para las CA sin conexión que no pueden volver a firmar según el calendario). Aparece una advertencia más allá de un año: las partes confiantes pueden conservar datos de revocación obsoletos durante toda la ventana' },
          { label: 'Resumen de firma', text: 'SHA-256, SHA-384 o SHA-512 para una CA RSA o EC. Una CA Ed25519, Ed448 o ML-DSA firma sin él: un resumen guardado antes para ella se muestra como ignorado, con un botón Borrar' },
          { label: 'Resumen por defecto (v2.251)', text: 'Sin resumen definido, una CA P-384 o P-521 firma sus CRL con SHA-384 o SHA-512. Las CRL ya emitidas conservan el suyo: la siguiente sigue la regla' },
          { label: 'CRL externa', text: 'Las CA sin clave o sin conexión no pueden autofirmar una CRL: cargar una generada junto a la clave sin conexión desde la vista de detalle de la CA; se valida (firma, emisor, monotonía) y se sirve en la misma URL del CDP (v2.215)' },
          { label: 'CRL delta', text: 'Cuando las CRL delta están activadas, se genera una nueva delta justo después de cada CRL completa, de modo que la delta servida siempre se refiere a la última base' },
          { label: 'Número de CRL', text: 'Las CRL base y delta de una CA comparten un único número creciente, nunca asignado a dos CRL, incluso cuando dos generaciones se ejecutan a la vez. El número más alto alcanzado se guarda por nombre y clave de CA y viaja en las copias de seguridad, de modo que una CA restaurada en otro servidor, o eliminada e importada de nuevo, continúa desde él' },
        ]
      },
      {
        title: 'Servicio OCSP',
        items: [
          { label: 'Estado', text: 'Indica si el respondedor OCSP está activo para cada CA' },
          { label: 'URL AIA', text: 'URL de Authority Information Access, respondedor OCSP y puntos de descarga del certificado CA Issuers incorporados a los certificados emitidos' },
          { label: 'Caché', text: 'Caché de respuestas con limpieza diaria automática de las entradas caducadas' },
          { label: 'Consultas totales', text: 'Número de solicitudes OCSP respondidas desde el inicio del servicio, y cuántas se sirvieron desde la caché' },
          { label: 'Caché HTTP', text: 'Una respuesta sin nonce puede ser conservada por las cachés HTTP hasta su nextUpdate, una hora como máximo (RFC 5019 §6.2: Expires, Last-Modified, ETag); una respuesta con nonce no se reutiliza' },
          { label: 'Respondedor delegado', text: 'Firmar las respuestas con un certificado OCSPSigning dedicado en lugar de la clave de la CA; asignar uno por CA desde su panel en esta página' },
          { label: 'Renovación automática del respondedor', text: 'Una tarea diaria vuelve a emitir el certificado del respondedor delegado antes de que caduque (mismo par de claves, renovado a la par) y lo vuelve a vincular; activada por defecto. El interruptor y su ventana (días antes de la caducidad, 30 por defecto) están en Configuración › Seguridad' },
        ]
      },
    ],
    tips: [
      'Activar la regeneración automática para mantener las CRL al día tras las revocaciones de certificados',
      'Copiar las URL de CDP, OCSP y AIA CA Issuers para incorporarlas a los perfiles de certificado',
      'OCSP proporciona verificación de revocación en tiempo real y se prefiere a la CRL',
    ],
  },
  helpGuides: {
    title: 'CRL & OCSP',
    content: `
## Visión general

Las listas de revocación de certificados (CRL) y el Online Certificate Status Protocol (OCSP) permiten a los clientes verificar si un certificado ha sido revocado. UCM admite ambos mecanismos.

## Gestión de CRL

### ¿Qué es una CRL?
Una CRL es una lista firmada de números de serie de certificados revocados, publicada por una CA. Los clientes descargan la CRL y comprueban si el número de serie de un certificado aparece en ella.

### CRL por CA
Cada CA tiene su propia CRL. La lista de CRL muestra todas las CA con:
- **Número de revocados**: número de certificados en la CRL
- **Última regeneración**: cuándo se reconstruyó la CRL por última vez
- **Regeneración automática**: si las actualizaciones automáticas de la CRL están activadas

### Regenerar una CRL
Hacer clic en **Regenerar** para reconstruir de inmediato la CRL de una CA. Es útil después de revocar certificados.

### Regeneración automática
Activar la regeneración automática para reconstruir la CRL automáticamente cada vez que se revoca un certificado. Se activa o desactiva por CA.

### Validez de la CRL
La programación de la CRL (por CA) fija cuánto tiempo sigue siendo válida cada CRL publicada. Las opciones van de **1 día a 5 años**: 1d, 2d, 3d, 7d, 14d, 30d, 90d, 180d, 1y, 3y, 5y.

- Las **CA en línea** deben mantener una validez corta (días) para que las partes confiantes reciban las revocaciones rápidamente
- Las **CA sin conexión** (típicamente una raíz que no puede volver a firmar las CRL según el calendario) son el caso de uso previsto para las opciones largas: de 90d a 5y
- Se muestra una advertencia más allá de un año: las partes confiantes pueden conservar datos de revocación obsoletos durante toda la ventana de validez

### Números de CRL
Cada CRL lleva un número de CRL (RFC 5280 §5.2.3). Las CRL base y delta de una CA comparten una única secuencia creciente, y ningún número se asigna jamás a dos CRL, incluso cuando una revocación y el planificador generan una al mismo tiempo.

El número más alto alcanzado se guarda para cada nombre y clave de CA, fuera de la propia CA, y lo llevan las copias de seguridad. Una CA restaurada en otro servidor, o eliminada e importada de nuevo, continúa desde él en lugar de empezar otra vez en 1.

### Punto de distribución de CRL (CDP)
La URL del CDP se incorpora a los certificados para que los clientes sepan dónde descargar la CRL. Copiar la URL desde los detalles de la CRL.

\`\`\`
http://your-server:8080/cdp/{ca_refid}.crl
\`\`\`

> 💡 **Activación automática**: al crear una CA nueva, el CDP se activa automáticamente si hay una URL base de protocolos o un servidor del protocolo HTTP configurados. La URL del CDP se genera automáticamente, sin pasos manuales.

> ⚠️ **Importante**: las URL se generan automáticamente con el puerto del protocolo HTTP y el FQDN del servidor. Si se accede a UCM mediante \`localhost\`, la URL no puede generarse. Configurar antes el **FQDN** o la **URL base de protocolos** en Configuración → General.

### Descargar las CRL
El botón de descarga guarda la CRL en PEM (un archivo .crl). La URL del CDP la sirve en DER para los clientes y otros sistemas.

## Respondedor OCSP

### ¿Qué es OCSP?
OCSP proporciona verificación del estado de un certificado en tiempo real. En lugar de descargar una CRL entera, los clientes envían una consulta sobre un certificado concreto y obtienen una respuesta inmediata.

### Estado de OCSP
La sección OCSP muestra:
- **Estado del respondedor**: activo o inactivo por CA
- **Consultas totales**: número de solicitudes OCSP respondidas desde el inicio del servicio, y cuántas procedían de la caché
- **Caché**: caché de respuestas con limpieza diaria automática de las entradas caducadas

### Caché de OCSP

UCM guarda en caché las respuestas OCSP para mejorar el rendimiento. La caché es:
- **Limpiada automáticamente**: el planificador purga a diario las respuestas caducadas
- **Invalidada al revocar**: cuando se revoca un certificado, su respuesta OCSP en caché se borra de inmediato
- **Invalidada al levantar la suspensión**: cuando se retira un Certificate Hold, la caché de OCSP se actualiza

### Respondedor OCSP delegado

Por defecto, las respuestas OCSP se firman con la propia clave de la CA. Un **respondedor delegado** usa en su lugar un certificado dedicado con la EKU **OCSPSigning**. Asignar uno por CA desde la sección **Respondedor delegado** de la CA seleccionada en la lista de esta página (solo son elegibles los certificados que llevan la EKU OCSPSigning y una clave privada).

**Renovación automática**: una tarea diaria vuelve a emitir el certificado del respondedor antes de que caduque, con el mismo par de claves y las mismas extensiones, renovado a la par, y vuelve a vincular la configuración del respondedor de la CA al nuevo certificado. Los certificados de firma OCSP de corta duración (por ejemplo, una plantilla de 90 días) rotan sin acción manual. Está activada por defecto; puede desactivarse y la ventana de renovación ajustarse en Configuración › Seguridad.

### URL AIA
La extensión Authority Information Access (AIA) se incorpora a los certificados para indicar a los clientes dónde encontrar:

**Respondedor OCSP**: verificación de revocación en tiempo real:
\`\`\`
http://your-server:8080/ocsp
\`\`\`

**CA Issuers** (RFC 5280 §4.2.2.1): descargar el certificado de la CA emisora para construir la cadena:
\`\`\`
http://your-server:8080/ca/{ca_refid}.cer   (DER format)
http://your-server:8080/ca/{ca_refid}.pem   (PEM format)
\`\`\`

Activar CA Issuers por CA en la sección **AIA CA Issuers** del panel de esa CA en esta página. La URL se genera automáticamente con el servidor del protocolo HTTP y el FQDN configurado.

> ⚠️ **Requisito previo**: las URL de protocolo (CDP, OCSP, AIA) requieren un **FQDN** válido o una **URL base de protocolos** configurada en Configuración → General. Si se accede a UCM mediante \`localhost\`, activar estas funciones fallará: definir primero el FQDN.

### OCSP frente a CRL

| Característica | CRL | OCSP |
|---------|-----|------|
| Frecuencia de actualización | Periódica | Tiempo real |
| Ancho de banda | Lista completa cada vez | Una sola consulta |
| Privacidad | Sin seguimiento | El servidor ve las consultas |
| Uso sin conexión | Sí (en caché) | Requiere conectividad |

> 💡 Buena práctica: activar tanto CRL como OCSP para la máxima compatibilidad.
`
  }
}
