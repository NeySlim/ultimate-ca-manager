export default {
  helpContent: {
    title: 'ACME',
    subtitle: 'Gestión automatizada de certificados',
    overview: 'UCM soporta dos modos ACME: cliente ACME para certificados públicos de cualquier CA compatible con RFC 8555 (Let\'s Encrypt, ZeroSSL, Buypass, HARICA, etc.), y servidor ACME local para automatización PKI interna con mapeo de dominios multi-CA.',
    sections: [
      {
        title: 'Cliente ACME',
        items: [
          { label: 'Cliente', text: 'Solicita certificados de cualquier CA ACME — Let\'s Encrypt, ZeroSSL, Buypass, HARICA o personalizada' },
          { label: 'Servidor personalizado', text: 'Establece una URL de directorio ACME personalizada para usar cualquier CA compatible con RFC 8555' },
          { label: 'EAB', text: 'Soporte de External Account Binding para CAs que requieren pre-registro (ZeroSSL, HARICA, etc.)' },
          { label: 'Tipos de clave', text: 'RSA-2048, RSA-4096, ECDSA P-256, ECDSA P-384 para claves de certificado' },
          { label: 'Claves de cuenta', text: 'Algoritmos ES256 (P-256), ES384 (P-384) o RS256 para claves de cuenta ACME' },
          { label: 'Proveedores DNS', text: 'Configura proveedores de desafío DNS-01 (Cloudflare, Route53, etc.)' },
          { label: 'Dominios', text: 'Mapea dominios a proveedores DNS para validación automática' },
        ]
      },
      {
        title: 'Servidor ACME local',
        items: [
          { label: 'Configuración', text: 'Activa/desactiva el servidor ACME integrado, selecciona la CA predeterminada' },
          { label: 'Dominios locales', text: 'Mapea dominios internos a CAs específicas para emisión multi-CA' },
          { label: 'Cuentas', text: 'Visualiza y gestiona las cuentas de clientes ACME registradas' },
          { label: 'Historial', text: 'Rastrea todas las órdenes de emisión de certificados ACME' },
        ]
      },
      {
        title: 'Resolución multi-CA',
        content: 'Cuando un cliente ACME solicita un certificado, UCM resuelve la CA firmante en este orden:',
        items: [
          '1. Mapeo de dominio local — coincidencia exacta de dominio, luego dominio padre',
          '2. Mapeo de dominio DNS — verifica la CA emisora configurada para el proveedor DNS',
          '3. Predeterminado global — la CA establecida en la configuración del servidor ACME',
          '4. Primera CA disponible con clave privada',
        ]
      },
    ],
    tips: [
      'URL del directorio ACME: https://tu-servidor:puerto/acme/directory',
      'Usa una URL de directorio personalizada para conectar con ZeroSSL, Buypass, HARICA o cualquier CA RFC 8555',
      'Las credenciales EAB (Key ID + clave HMAC) son proporcionadas por tu CA al registrarte',
      'Las claves ECDSA P-256 ofrecen seguridad equivalente a RSA-2048 con un tamaño mucho menor',
      'Usa dominios locales para asignar diferentes CAs a diferentes dominios internos',
      'Cualquier CA con clave privada puede ser seleccionada como CA emisora',
      'Los dominios comodín (*.ejemplo.com) requieren validación DNS-01',
    ],
    warnings: [
      'La validación de dominio es obligatoria — tu servidor debe ser accesible o el DNS debe estar configurado',
      'Cambiar el tipo de clave de cuenta requiere volver a registrar tu cuenta ACME',
    ],
  },
  helpGuides: {
    title: 'ACME',
    content: `
## Descripción general

UCM soporta ACME (Automated Certificate Management Environment) en dos modos:

- **Cliente ACME** — Obtén certificados de cualquier CA compatible con RFC 8555 (Let's Encrypt, ZeroSSL, Buypass, HARICA o personalizada)
- **Servidor ACME local** — Servidor ACME integrado para automatización PKI interna con soporte multi-CA

## Cliente ACME

### Configuración del cliente
Gestiona la configuración de tu cliente ACME:
- **Entorno** — Staging (pruebas) o Producción (certificados reales)
- **Email de contacto** — Requerido para el registro de cuenta
- **Renovación automática** — Renueva automáticamente los certificados antes de su expiración
- **Tipo de clave de certificado** — RSA-2048, RSA-4096, ECDSA P-256 o ECDSA P-384
- **Algoritmo de clave de cuenta** — ES256, ES384 o RS256 para la firma de cuenta ACME

### Servidor ACME personalizado
Usa cualquier CA compatible con RFC 8555, no solo Let's Encrypt:

| Proveedor CA | URL del directorio |
|---|---|
| **Let's Encrypt** | *(predeterminado, dejar vacío)* |
| **ZeroSSL** | \`https://acme.zerossl.com/v2/DV90\` |
| **Buypass** | \`https://api.buypass.com/acme/directory\` |
| **HARICA** | \`https://acme-v02.harica.gr/acme/<token>/directory\` |
| **Google Trust** | \`https://dv.acme-v02.api.pki.goog/directory\` |

Establece la URL del directorio de tu CA en **Configuración** → **Servidor ACME personalizado**.

### External Account Binding (EAB)
Algunas CAs requieren credenciales EAB para vincular tu cuenta ACME con una cuenta existente en la CA:

1. Regístrate en el portal de tu CA para obtener el **EAB Key ID** y la **clave HMAC**
2. Introduce ambos valores en **Configuración** → **Servidor ACME personalizado**
3. La clave HMAC está codificada en base64url (proporcionada por la CA)

> 💡 EAB es requerido por ZeroSSL, HARICA, Google Trust Services y la mayoría de CAs empresariales.

### ECDSA vs RSA

| Tipo de clave | Tamaño | Seguridad | Rendimiento |
|---|---|---|---|
| **RSA-2048** | 2048 bit | Estándar | Base |
| **RSA-4096** | 4096 bit | Superior | Más lento |
| **ECDSA P-256** | 256 bit | ≈ RSA-3072 | Mucho más rápido |
| **ECDSA P-384** | 384 bit | ≈ RSA-7680 | Más rápido |

Las claves ECDSA son recomendadas para despliegues modernos — más pequeñas, más rápidas e igualmente seguras.

### Proveedores DNS
Configura proveedores de desafío DNS-01 para la validación de dominio. Los proveedores soportados incluyen:
- Cloudflare
- AWS Route 53
- Google Cloud DNS
- DigitalOcean
- OVH
- Y más

Cada proveedor requiere credenciales API específicas del servicio DNS.

### Dominios
Mapea tus dominios a proveedores DNS. Al solicitar un certificado para un dominio, UCM usa el proveedor mapeado para crear los registros de desafío DNS-01.

1. Haz clic en **Añadir dominio**
2. Introduce el nombre del dominio (p. ej., \`ejemplo.com\` o \`*.ejemplo.com\`)
3. Selecciona el proveedor DNS
4. Haz clic en **Guardar**

> 💡 Los certificados comodín (\`*.ejemplo.com\`) requieren validación DNS-01.

## Servidor ACME local

### Configuración
- **Activar/Desactivar** — Activa o desactiva el servidor ACME integrado
- **CA predeterminada** — Selecciona qué CA firma los certificados por defecto
- **Términos de servicio** — URL opcional de términos de servicio para los clientes

### URL del directorio ACME
\`\`\`
https://tu-servidor:8443/acme/directory
\`\`\`

Clientes como certbot, acme.sh o Caddy usan esta URL para descubrir los endpoints ACME.

### Dominios locales (multi-CA)
Mapea dominios internos a CAs específicas. Esto permite que diferentes dominios sean firmados por diferentes CAs.

1. Haz clic en **Añadir dominio**
2. Introduce el dominio (p. ej., \`interno.corp\` o \`*.dev.local\`)
3. Selecciona la **CA emisora**
4. Activa/desactiva **Aprobación automática**
5. Haz clic en **Guardar**

### Orden de resolución de CA
Cuando un cliente ACME solicita un certificado, UCM determina la CA firmante en este orden:
1. **Mapeo de dominio local** — Coincidencia exacta, luego coincidencia de dominio padre
2. **Mapeo de dominio DNS** — La CA configurada para el proveedor DNS
3. **Predeterminado global** — La CA establecida en la configuración del servidor ACME
4. **Primera disponible** — Cualquier CA con clave privada

### Cuentas
Visualiza las cuentas de clientes ACME registradas:
- ID de cuenta y email de contacto
- Fecha de registro
- Número de órdenes

### Historial
Consulta todas las órdenes de emisión de certificados:
- Estado de la orden (pendiente, válida, inválida, lista)
- Nombres de dominio solicitados
- CA firmante utilizada
- Marca de tiempo de emisión

## Uso de certbot

\`\`\`
# Registrar cuenta (Let's Encrypt — predeterminado)
certbot register --agree-tos --email admin@ejemplo.com

# Registrar con CA ACME personalizada + EAB
certbot register \\
  --server 'https://acme.zerossl.com/v2/DV90' \\
  --eab-kid 'tu-key-id' \\
  --eab-hmac-key 'tu-clave-hmac' \\
  --agree-tos --email admin@ejemplo.com

# Solicitar certificado con clave ECDSA
certbot certonly --server https://tu-servidor:8443/acme/directory \\
  --standalone -d miservidor.interno.corp \\
  --key-type ecdsa --elliptic-curve secp256r1

# Renovar
certbot renew --server https://tu-servidor:8443/acme/directory
\`\`\`

## Uso de acme.sh

\`\`\`
# Predeterminado (Let's Encrypt)
acme.sh --issue -d ejemplo.com --standalone

# CA ACME personalizada con EAB y ECDSA
acme.sh --issue \\
  --server 'https://acme-v02.harica.gr/acme/TOKEN/directory' \\
  --eab-kid 'tu-key-id' \\
  --eab-hmac-key 'tu-clave-hmac' \\
  --keylength ec-256 \\
  -d ejemplo.com --standalone
\`\`\`

> ⚠ Para ACME interno, los clientes deben confiar en la CA de UCM. Instala el certificado de la CA raíz en el almacén de confianza del cliente.
`
  }
}
