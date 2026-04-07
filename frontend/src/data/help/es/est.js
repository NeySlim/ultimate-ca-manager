export default {
  helpContent: {
    title: 'EST',
    subtitle: 'Enrollment over Secure Transport',
    overview: 'EST (RFC 7030) proporciona inscripción segura de certificados sobre HTTPS con TLS mutuo (mTLS) o autenticación HTTP Basic. Ideal para entornos empresariales modernos que requieren inscripción basada en estándares con seguridad de transporte robusta.',
    sections: [
      {
        title: 'Pestañas',
        items: [
          { label: 'Configuración', text: 'Activar EST, seleccionar CA firmante, configurar credenciales de autenticación y validez del certificado' },
          { label: 'Información', text: 'URLs de los endpoints EST para integración, estadísticas de inscripción y ejemplos de uso' },
        ]
      },
      {
        title: 'Autenticación',
        items: [
          { label: 'mTLS (Mutual TLS)', text: 'El cliente presenta un certificado durante el handshake TLS — método de autenticación más seguro' },
          { label: 'HTTP Basic Auth', text: 'Alternativa con usuario/contraseña cuando mTLS no está disponible' },
        ]
      },
      {
        title: 'Endpoints',
        items: [
          { label: '/cacerts', text: 'Obtener la cadena de certificados de la CA (no requiere autenticación)' },
          { label: '/simpleenroll', text: 'Enviar un CSR y recibir un certificado firmado' },
          { label: '/simplereenroll', text: 'Renovar un certificado existente (requiere mTLS)' },
          { label: '/csrattrs', text: 'Obtener los atributos de CSR recomendados por el servidor' },
          { label: '/serverkeygen', text: 'El servidor genera el par de claves y devuelve el certificado + clave' },
        ]
      },
    ],
    tips: [
      'EST es el reemplazo moderno de SCEP — prefiera EST para nuevas implementaciones',
      'Use autenticación mTLS para la máxima seguridad — Basic Auth es una alternativa',
      'El endpoint /simplereenroll requiere que el cliente presente su certificado actual vía mTLS',
      'Copie las URLs de los endpoints desde la pestaña Información para configurar sus clientes EST',
    ],
    warnings: [
      'EST requiere HTTPS — el cliente debe confiar en el certificado del servidor UCM o en la CA',
      'La autenticación mTLS requiere una configuración adecuada de terminación TLS (el proxy inverso debe reenviar los certificados del cliente)',
    ],
  },
  helpGuides: {
    title: 'Protocolo EST',
    content: `
## Descripción general

Enrollment over Secure Transport (EST) está definido en **RFC 7030** y proporciona inscripción de certificados, reinscripción y obtención de certificados de CA sobre HTTPS. EST es el reemplazo moderno de SCEP, ofreciendo mayor seguridad a través de la autenticación TLS mutuo (mTLS).

## Configuración

### Pestaña de Configuración

1. **Activar EST** — Activar o desactivar el protocolo EST
2. **CA firmante** — Seleccionar qué Autoridad de Certificación firma los certificados inscritos vía EST
3. **Autenticación** — Configurar credenciales de HTTP Basic Auth (usuario y contraseña)
4. **Validez del certificado** — Período de validez predeterminado para certificados emitidos por EST (en días)

### Guardar configuración

Haga clic en **Guardar** para aplicar los cambios. Los endpoints EST estarán disponibles inmediatamente cuando se active.

## Autenticación

EST soporta dos métodos de autenticación:

### Mutual TLS (mTLS) — Recomendado

El cliente presenta un certificado durante el handshake TLS. UCM valida el certificado y autentica al cliente automáticamente.

- **Método más seguro** — identidad criptográfica del cliente
- **Requerido para** \`/simplereenroll\` — el cliente debe presentar su certificado actual
- **Depende de** la configuración adecuada de terminación TLS (el proxy inverso debe pasar \`SSL_CLIENT_CERT\` a UCM)

### HTTP Basic Auth — Alternativa

Autenticación con usuario y contraseña sobre HTTPS. Se configura en la Configuración de EST.

- **Más fácil de configurar** — no se necesita certificado de cliente
- **Menos seguro** — las credenciales se transmiten por solicitud (protegido por HTTPS)
- **Usar cuando** la infraestructura mTLS no está disponible

## Endpoints EST

Todos los endpoints están bajo \`/.well-known/est/\`:

### GET /cacerts
Obtener la cadena de certificados de la CA. **No requiere autenticación.**

Use esto para establecer confianza — los clientes obtienen el certificado de CA antes de la inscripción.

\`\`\`bash
curl -k https://your-server:8443/.well-known/est/cacerts | \\
  base64 -d | openssl pkcs7 -inform DER -print_certs
\`\`\`

### POST /simpleenroll
Enviar un CSR PKCS#10 y recibir un certificado firmado.

Requiere autenticación (mTLS o Basic Auth).

\`\`\`bash
# Usando curl con Basic Auth
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simpleenroll
\`\`\`

### POST /simplereenroll
Renovar un certificado existente. **Requiere mTLS** — el cliente debe presentar el certificado que se está renovando.

\`\`\`bash
curl -k --cert client.pem --key client.key \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @csr.pem \\
  https://your-server:8443/.well-known/est/simplereenroll
\`\`\`

### GET /csrattrs
Obtener los atributos de CSR (OID) recomendados por el servidor.

### POST /serverkeygen
El servidor genera un par de claves y devuelve el certificado junto con la clave privada. Útil cuando el cliente no puede generar claves localmente.

## Pestaña de Información

La pestaña de Información muestra:
- **URLs de endpoints** — URLs listas para copiar y pegar para cada operación EST
- **Estadísticas de inscripción** — Número de inscripciones, reinscripciones y errores
- **Última actividad** — Operaciones EST más recientes de los registros de auditoría

## Ejemplos de integración

### Usando est client (libest)
\`\`\`bash
estclient -s your-server -p 8443 \\
  --srp-user est-user --srp-password est-password \\
  -o /tmp/certs --enroll
\`\`\`

### Usando OpenSSL
\`\`\`bash
# Obtener certificados de CA
curl -k https://your-server:8443/.well-known/est/cacerts | \\
  base64 -d > cacerts.p7

# Generar CSR
openssl req -new -newkey rsa:2048 -nodes \\
  -keyout client.key -out client.csr \\
  -subj "/CN=my-device/O=MyOrg"

# Inscribir (Basic Auth)
curl -k --user est-user:est-password \\
  -H "Content-Type: application/pkcs10" \\
  --data-binary @<(openssl req -in client.csr -outform DER | base64) \\
  https://your-server:8443/.well-known/est/simpleenroll | \\
  base64 -d | openssl x509 -inform DER -out client.pem
\`\`\`

### Windows (certutil)
\`\`\`cmd
certutil -enrollmentServerURL add \\
  "https://your-server:8443/.well-known/est" \\
  kerberos
\`\`\`

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
