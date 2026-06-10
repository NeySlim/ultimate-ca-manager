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
        title: 'Proxy ACME',
        items: [
          { label: 'CA upstream', text: 'Seleccione un preajuste (Let\'s Encrypt Producción/Staging) o introduzca una URL personalizada para cualquier CA RFC 8555' },
          { label: 'Estado de cuenta', text: 'Muestra si UCM está registrado con la CA upstream. Las cuentas se registran automáticamente en la primera solicitud proxy' },
          { label: 'Probar conexión', text: 'Verifique la conectividad con la CA upstream y compruebe si se requieren credenciales EAB' },
          { label: 'Restablecer cuenta', text: 'Borre las credenciales de la cuenta upstream para forzar un nuevo registro (usar después de cambiar de CA)' },
          { label: 'Credenciales EAB', text: 'Credenciales External Account Binding para CAs que las requieren (ej: ZeroSSL, Google Trust)' },
          { label: 'Desafíos DNS', text: 'UCM maneja los desafíos DNS-01 en nombre de los clientes usando los proveedores DNS configurados' },
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
      {
        title: 'Credenciales EAB (lado servidor)',
        content: 'Cuando UCM actúa como servidor ACME, External Account Binding (RFC 8555 §7.3.4) permite exigir credenciales pre-emitidas antes de que los clientes registren cuentas:',
        items: [
          { label: 'Emitir', text: 'Generar un nuevo par kid + clave HMAC desde ACME → EAB Credentials' },
          { label: 'Distribuir', text: 'Entregar el kid + HMAC al cliente (cert-manager, certbot, acme.sh)' },
          { label: 'Vincular', text: 'El cliente firma un JWS sobre la clave MAC en newAccount para vincular su cuenta ACME' },
          { label: 'Rotar / Revocar', text: 'Revocar un kid en cualquier momento — las cuentas existentes siguen funcionando, los nuevos vínculos se rechazan' },
          { label: 'Auditoría', text: 'Emisión, rotación y revocación se auditan bajo el operador que las realizó' },
        ]
      },
      {
        title: 'Resolutores DNS personalizados (DNS-01)',
        items: [
          { label: 'Override por cuenta', text: 'Sobrescribir resolutores del sistema al validar registros TXT _acme-challenge' },
          { label: 'Split-horizon', text: 'Útil cuando su servidor autoritativo es interno pero la vista pública se cachea en otro lugar' },
          { label: 'Registros obsoletos', text: 'Evita el caching de resolutores públicos durante renovaciones automáticas rápidas' },
        ]
      },
      {
        title: 'ACME en IP internas / privadas',
        content: 'La validación HTTP-01 y TLS-ALPN-01 funciona de forma nativa para destinos RFC1918, loopback, .lan / .local / .corp — el modelo de despliegue principal de UCM.',
        items: [
          { label: 'Conmutador', text: 'Settings → SystemConfig → acme.allow_private_ips (predeterminado: true)' },
          { label: 'Siempre bloqueado', text: 'Las IP de metadatos cloud (169.254.169.254, fd00:ec2::254, etc.) se bloquean incondicionalmente' },
        ]
      },

      {
        title: 'Certificados de dirección IP (RFC 8738)',
        content: 'El servidor ACME local puede emitir certificados para direcciones IPv4 e IPv6, no solo nombres DNS. Use el tipo de identificador « ip » en el pedido.',
        items: [
          { label: 'Identificador', text: 'Pedido con { "type": "ip", "value": "192.0.2.10" } (IPv4) o un literal IPv6 como 2001:db8::1' },
          { label: 'Desafíos', text: 'Solo se ofrecen HTTP-01 y TLS-ALPN-01 — DNS-01 está prohibido para identificadores IP según RFC 8738' },
          { label: 'SNI TLS-ALPN-01', text: 'La validación usa la forma reverse-DNS (in-addr.arpa / ip6.arpa) como nombre de host SNI' },
          { label: 'SAN emitido', text: 'El certificado lleva un SAN iPAddress; se admiten pedidos mixtos DNS + IP' },
          { label: 'IP internas', text: 'Las direcciones RFC1918 y loopback se validan de forma nativa — el modelo de despliegue principal de UCM' },
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
      'Cuando UCM es el servidor ACME, emita sus propias credenciales EAB en ACME → EAB Credentials',
      'Para Kubernetes/cert-manager: vea los manifiestos de referencia en examples/kubernetes/cert-manager/',
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


## Modo Proxy ACME

El proxy ACME permite a los clientes internos solicitar certificados de una CA pública (Let's Encrypt, ZeroSSL, etc.) a través de UCM, sin acceso directo a Internet. UCM actúa como intermediario, gestionando los desafíos DNS-01 y reenviando las solicitudes a la CA upstream.

### Cuándo usar el modo proxy
- Servidores internos sin acceso directo a Internet
- Gestión centralizada de desafíos DNS-01 a través de los proveedores DNS configurados en UCM
- Auditoría y seguimiento de todas las emisiones de certificados públicos

### Configuración
1. Vaya a **ACME** → pestaña **Let's Encrypt**
2. Desplácese hasta la sección **Proxy ACME**
3. Active el interruptor **Proxy ACME**
4. Seleccione una **CA upstream**: Let's Encrypt Producción, Let's Encrypt Staging o Personalizado
5. Para CAs personalizadas, introduzca la URL del directorio ACME manualmente
6. Si la CA upstream requiere EAB, expanda **Credenciales EAB** e introduzca el Key ID y la clave HMAC
7. Haga clic en **Probar conexión** para verificar la conectividad con la CA upstream
8. UCM registra automáticamente una cuenta en la primera solicitud proxy

### Gestión de cuentas
- La **insignia de estado de cuenta** muestra si UCM está registrado con la CA upstream
- Cambiar de CA upstream borra automáticamente las credenciales obsoletas y fuerza un nuevo registro
- Use el botón **Restablecer cuenta** para borrar credenciales manualmente si es necesario
- **Probar conexión** verifica si el directorio upstream es accesible y si se requiere EAB

### Uso del proxy
Dirija sus clientes ACME internos al directorio proxy:
\`\`\`
https://su-servidor-ucm:8443/acme/proxy/directory
\`\`\`

> 💡 Las credenciales EAB del proxy son distintas de las del cliente — autentican UCM ante la CA upstream, no sus clientes ante UCM.

> ⚠ El modo proxy requiere al menos un proveedor DNS configurado en UCM para la resolución de desafíos.

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
## Certificados de dirección IP (RFC 8738)

El servidor ACME local puede emitir certificados para **direcciones IP** (IPv4 e IPv6), no solo nombres DNS. Útil para servicios internos, dispositivos y hosts direccionados directamente por IP.

### Pedir un certificado IP
Use el tipo de identificador \`ip\` en el pedido ACME:
\`\`\`json
{
  "identifiers": [
    { "type": "ip", "value": "192.0.2.10" },
    { "type": "ip", "value": "2001:db8::1" }
  ]
}
\`\`\`
También se admiten pedidos mixtos DNS + IP.

### Validación
- **HTTP-01** y **TLS-ALPN-01** son los únicos desafíos ofrecidos para identificadores IP. **DNS-01 está prohibido** para IP por la RFC 8738.
- **HTTP-01** se conecta directamente a la IP (los literales IPv6 van entre corchetes, ej. \`http://[2001:db8::1]/...\`).
- **TLS-ALPN-01** usa la forma reverse-DNS de la IP (\`in-addr.arpa\` / \`ip6.arpa\`) como nombre de host SNI.

### Certificado emitido
El certificado firmado contiene una entrada SubjectAltName **iPAddress** por cada IP validada.

> 💡 Las direcciones internas (RFC1918, loopback) se validan de forma nativa — el modelo de despliegue principal de UCM. Las IP de metadatos cloud siguen bloqueadas.

`
  }
}
