export default {
  helpContent: {
    title: 'EST',
    subtitle: 'Enrollment over Secure Transport',
    overview: 'EST (RFC 7030) proporciona inscripción segura de certificados por HTTPS con TLS mutuo (mTLS) o autenticación HTTP Basic. Ideal para entornos empresariales modernos que requieren una inscripción basada en estándares con un transporte muy seguro.',
    sections: [
      {
        title: 'Pestañas',
        items: [
          { label: 'Puntos de inscripción', text: 'El punto por defecto y uno por etiqueta de CA (/.well-known/est/<etiqueta>/), con Autoridad, Autenticación (certificado de cliente, o certificado de cliente o contraseña una vez guardadas las credenciales HTTP Basic) y Estado. Un punto abre su detalle con sus cinco URL y los totales de inscripción' },
          { label: 'Configuración', text: 'Habilitar EST, CA emisora, validez, cadena en las respuestas, etiquetas de CA y credenciales HTTP Basic, en un formulario con su barra de guardado; una etiqueta repetida bloquea el guardado' },
        ]
      },
      {
        title: 'Autenticación',
        items: [
          { label: 'mTLS (TLS mutuo)', text: 'El cliente presenta un certificado durante el handshake TLS, el método de autenticación más fuerte' },
          { label: 'HTTP Basic Auth', text: 'Alternativa con usuario y contraseña cuando mTLS no está disponible. Con allow_empty_username establecido mediante PATCH /api/v2/est/config, un cliente también puede enviar un nombre de usuario vacío con la contraseña (RFC 7030 §3.2.3, v2.252)' },
          { label: 'Certificado presentado', text: 'Para /simpleenroll y /serverkeygen con mTLS, un certificado firmado por la CA de EST debe ser uno que esta aún conserva: los certificados revocados, sustituidos o eliminados se rechazan (RFC 7030 §3.3.2). Un certificado que emitió otra CA de este servidor se rechaza en cuanto él o una CA superior se revoca, o una vez caducado (v2.252); el de una autoridad que este servidor no conserva se deja a la capa TLS' },
          { label: 'Vinculación tls-unique', text: 'Una CSR con un challengePassword debe llevar el valor tls-unique de su conexión TLS 1.2 con UCM (RFC 7030 §3.5); se rechaza con 400 cuando el valor difiere o no puede verificarse (TLS 1.3, un proxy delante). /csrattrs no lo pide. ignore_challenge_password, establecido mediante PATCH /api/v2/est/config, omite la comprobación para un cliente que pone ahí una contraseña (v2.252)' },
          { label: 'Claves comprometidas', text: 'Una CSR cuya clave se revocó como comprometida (keyCompromise) se rechaza con 400 (v2.252)' },
        ]
      },
      {
        title: 'Endpoints',
        items: [
          { label: '/cacerts', text: 'Obtener la cadena de certificados de la CA (no requiere autenticación)' },
          { label: '/simpleenroll', text: 'Enviar una CSR y recibir un certificado firmado' },
          { label: '/simplereenroll', text: 'Renovar un certificado existente (requiere mTLS; sin certificado de cliente: 403). Una CSR sin SubjectAltName renueva los nombres propios del certificado, o ninguno si no tenía, en lugar de un nombre construido a partir del CN (RFC 7030 §4.2.2, v2.252)' },
          { label: '/csrattrs', text: 'Obtener los atributos de CSR recomendados por el servidor: keyUsage, subjectAltName y extKeyUsage como OID simples (RFC 9908 §5.2, v2.252). csrattrs_legacy_encoding, establecido mediante PATCH /api/v2/est/config, sirve la forma anterior (los OID dentro de una extensionRequest) para un cliente que la necesite' },
          { label: 'Errores', text: 'Los rechazos de inscripción, incluida la limitación de frecuencia, llegan como un mensaje de texto plano (text/plain, RFC 8951 §5) que indica el motivo, por ejemplo un cuerpo que no es base64 ni una CSR PKCS#10, o las restricciones de nombres de la CA (v2.252)' },
          { label: '/serverkeygen', text: 'El servidor genera un par de claves y devuelve el certificado y la clave. La clave toma la fortaleza de la CA emisora, en la familia de la clave de la solicitud si es RSA o EC (se ignora su tamaño o curva), si no la de la CA, llevada al tipo más cercano que permitan las políticas. La clave llega como PKCS#8 sin cifrar bajo TLS; una CSR que nombra la clave del certificado mTLS (AsymmetricDecryptKeyIdentifier) la recibe cifrada para ese certificado, por transporte de clave para RSA de 2048 bits o más (keyEncipherment) o por acuerdo de clave para EC (keyAgreement), con los algoritmos que lista la SMIMECapabilities de la CSR, en un paquete de clave firmado por un certificado «EST key generator» que la CA emisora expide para este fin (Ed25519 bajo una CA Ed448, v2.252)' },
        ]
      },
    ],
    tips: [
      'EST es el sustituto moderno de SCEP: prefiera EST para nuevas implementaciones',
      'Use autenticación mTLS para la máxima seguridad; Basic Auth es una alternativa',
      'El endpoint /simplereenroll requiere que el cliente presente su certificado actual mediante mTLS',
      'Copie las URL de los endpoints desde el detalle de un punto de inscripción para configurar sus clientes EST',
    ],
    warnings: [
      'EST requiere HTTPS: el cliente debe confiar en el certificado del servidor UCM o en la CA',
      'La autenticación mTLS requiere una configuración correcta de la terminación TLS (el proxy inverso debe reenviar los certificados de cliente)',
    ],
  },
  helpGuides: {
    title: 'Protocolo EST',
    content: `
## Descripción general

Enrollment over Secure Transport (EST) está definido en la **RFC 7030** y proporciona inscripción de certificados, reinscripción y obtención del certificado de la CA por HTTPS. EST es el sustituto moderno de SCEP y ofrece mayor seguridad gracias a la autenticación TLS mutua (mTLS).

## Configuración

### Configuración

1. **Habilitar EST**: activar o desactivar el protocolo EST
2. **CA firmante**: seleccionar qué autoridad de certificación firma los certificados inscritos por EST
3. **Autenticación**: configurar las credenciales HTTP Basic Auth (nombre de usuario y contraseña)
4. **Validez del certificado**: período de validez por defecto de los certificados emitidos por EST (en días)
5. **Etiquetas de CA**: servir otras CA bajo \`/.well-known/est/<etiqueta>/\`. Un nombre de operación (\`cacerts\`, \`simpleenroll\`, \`simplereenroll\`, \`fullcmc\`, \`serverkeygen\`, \`csrattrs\`) no puede ser una etiqueta (RFC 7030 §3.2.2, v2.252)

### Guardar la configuración

Pulse **Guardar** para aplicar los cambios. Los endpoints EST quedan disponibles de inmediato cuando está habilitado.

## Autenticación

EST admite dos métodos de autenticación:

### TLS mutuo (mTLS): recomendado

El cliente presenta un certificado durante el handshake TLS. UCM valida el certificado y autentica al cliente automáticamente.

- **Método más fuerte**: identidad criptográfica del cliente
- **Obligatorio para** \`/simplereenroll\`: el cliente debe presentar su certificado actual
- **Puerto 8443**: cuando UCM termina el TLS, el handshake acepta los certificados de la CA de confianza mTLS (Ajustes → Seguridad) y de las CA situadas por debajo de ella únicamente; para reinscribir certificados de una CA de EST fuera de esa rama, confíe en una CA situada por encima de ambas (v2.252)
- **Certificado presentado**: para \`/simpleenroll\` y \`/serverkeygen\`, un certificado firmado por la CA de EST debe ser uno que esta aún conserva: los certificados revocados, sustituidos o eliminados se rechazan (RFC 7030 §3.3.2). Un certificado que emitió otra CA de este servidor se rechaza en cuanto él o una CA superior se revoca, o una vez caducado (v2.252); el de una autoridad que este servidor no conserva se deja a la capa TLS
- **Vinculación tls-unique**: una CSR con un \`challengePassword\` debe llevar el valor \`tls-unique\` de su conexión TLS 1.2 con UCM (RFC 7030 §3.5), y se rechaza con 400 cuando el valor difiere o no puede verificarse (TLS 1.3, un proxy delante); \`/csrattrs\` no lo pide. \`ignore_challenge_password\`, establecido mediante \`PATCH /api/v2/est/config\`, omite la comprobación para un cliente que pone ahí una contraseña (v2.252)
- **Depende de** una configuración correcta de la terminación TLS (el proxy inverso debe pasar \`SSL_CLIENT_CERT\` a UCM)

### HTTP Basic Auth: alternativa

Autenticación con usuario y contraseña sobre HTTPS. Se configura en los ajustes de EST.

- **Más sencillo de configurar**: no necesita certificado de cliente
- **Menos seguro**: las credenciales se transmiten en cada solicitud (protegidas por HTTPS)
- **Úselo cuando** no haya infraestructura mTLS disponible
- **Solo contraseña**: con \`allow_empty_username\` establecido mediante \`PATCH /api/v2/est/config\`, un cliente puede enviar un nombre de usuario vacío con la contraseña (RFC 7030 §3.2.3, v2.252)

Una CSR cuya clave se revocó como comprometida se rechaza con 400, y todo rechazo de inscripción, incluida la limitación de frecuencia, llega como un mensaje de texto plano que indica el motivo (RFC 8951 §5, v2.252).

## Endpoints EST

Todos los endpoints están bajo \`/.well-known/est/\`:

### GET /cacerts
Obtener la cadena de certificados de la CA. **No requiere autenticación.**

Sirve para establecer la confianza inicial: los clientes obtienen el certificado de la CA antes de inscribirse.

\`\`\`bash
curl -k https://your-server:8443/.well-known/est/cacerts | \\
  base64 -d | openssl pkcs7 -inform DER -print_certs
\`\`\`

### POST /simpleenroll
Enviar una CSR PKCS#10 y recibir un certificado firmado.

Requiere autenticación (mTLS o Basic Auth).

\`\`\`bash
# Con curl y Basic Auth
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simpleenroll
\`\`\`

### POST /simplereenroll
Renovar un certificado existente. **Requiere mTLS**: el cliente debe presentar el certificado que se renueva, o recibe 403. Una CSR sin SubjectAltName renueva los nombres propios del certificado, o ninguno si no tenía, y no un nombre construido a partir del CN (RFC 7030 §4.2.2, v2.252).

\`\`\`bash
curl -k --cert client.pem --key client.key \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simplereenroll
\`\`\`

### GET /csrattrs
Obtener los atributos de CSR recomendados por el servidor: keyUsage, subjectAltName y extKeyUsage como OID simples, la forma que da la RFC 9908 §5.2 para un OID pedido sin valor (v2.252). Un cliente que necesite la forma anterior (los OID dentro de un atributo extensionRequest) la obtiene con \`csrattrs_legacy_encoding\` establecido mediante \`PATCH /api/v2/est/config\`.

### POST /serverkeygen
El servidor genera un par de claves y devuelve el certificado junto con la clave privada. Útil cuando el cliente no puede generar claves localmente.

La clave generada toma la fortaleza de la CA emisora: la familia de la clave de la solicitud cuando es RSA o EC (se ignora su tamaño o curva), si no la de la CA, llevada al tipo más cercano que permitan las políticas.

La clave privada llega como PKCS#8 sin cifrar (\`application/pkcs8\`), protegida por TLS. Para obtenerla cifrada, autentíquese con mTLS y ponga el identificador de clave del certificado de cliente en la CSR (AsymmetricDecryptKeyIdentifier): la clave llega entonces en un paquete de clave RFC 5958 envuelto para ese certificado, por transporte de clave para un certificado RSA de 2048 bits o más que declare keyEncipherment o por acuerdo de clave (ECDH) para un certificado EC que declare keyAgreement, con los algoritmos de transporte o acuerdo de clave y de contenido tomados de la SMIMECapabilities de la CSR en el orden del cliente. El paquete lo firma un certificado «EST key generator» que la CA emisora expide en el primer uso y renueva por sí misma; encadena con la CA que sirve \`/cacerts\` y tiene la familia de claves de la CA, Ed25519 bajo una CA Ed448 (v2.252).

## Puntos de acceso

El detalle de un punto de inscripción muestra:
- **URL de los endpoints**: URL listas para copiar y pegar para cada operación EST
- **Estadísticas de inscripción**: inscripciones totales, correctas y fallidas

## Ejemplos de integración

### Con el cliente est (libest)
Use \`estclient\` con credenciales HTTP Basic (\`-u\` y \`-h\`) o un certificado de cliente. Sus opciones TLS-SRP no se aplican: UCM no ofrece TLS-SRP.

### Con OpenSSL
\`\`\`bash
# Obtener los certificados de la CA
curl -k https://your-server:8443/.well-known/est/cacerts | \\
  base64 -d > cacerts.p7

# Generar la CSR
openssl req -new -newkey rsa:2048 -nodes \\
  -keyout client.key -out client.csr \\
  -subj "/CN=my-device/O=MyOrg"

# Inscribir (Basic Auth)
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @<(openssl req -in client.csr -outform DER | base64) \\
  https://your-server:8443/.well-known/est/simpleenroll | \\
  base64 -d | openssl pkcs7 -inform DER -print_certs -out client.pem
\`\`\`

La respuesta es un PKCS#7 en base64 (solo certificados), no un certificado suelto: léala con \`openssl pkcs7\`, no con \`openssl x509\`.

### Windows
Windows no tiene un cliente EST integrado: \`certutil -enrollmentServerURL\` registra un servicio web de inscripción de certificados (WSTEP), no un servidor EST. Para equipos Windows, use la inscripción automática de Windows (XCEP/WSTEP).

## EST vs SCEP

| Característica | EST | SCEP |
|----------------|-----|------|
| Transporte | HTTPS (TLS) | HTTP o HTTPS |
| Autenticación | mTLS + Basic Auth | Contraseña de desafío |
| Estándar | RFC 7030 (2013) | RFC 8894 (2020, pero heredado) |
| Generación de claves | Opción en servidor | Solo en cliente |
| Renovación | Reinscripción mTLS | Reinscripción |
| Seguridad | Fuerte (basada en TLS) | Más débil (secreto compartido) |
| Recomendación | ✅ Preferido para nuevos | Solo dispositivos heredados |

> 💡 Use EST para nuevas implementaciones. Use SCEP solo para dispositivos de red heredados que no soporten EST.
`
  }
}
