export default {
  helpContent: {
    title: 'Certificados SSH',
    subtitle: 'Emitir y gestionar certificados OpenSSH',
    overview: 'Emitir certificados SSH firmados por las CA SSH. Los certificados sustituyen la gestión manual de authorized_keys con un acceso limitado en el tiempo y restringido por principal, con caducidad automática. Se admiten certificados de usuario y de host.',
    sections: [
      {
        title: 'Modos de emisión',
        items: [
          { label: 'Firmar clave pública', text: 'Pegar una clave pública SSH existente para firmarla. La clave privada permanece en el equipo del usuario, UCM nunca la ve.' },
          { label: 'Generar par de claves', text: 'UCM genera un par de claves nuevo y firma el certificado. Descargar la clave privada de inmediato: no puede recuperarse después.' },
        ]
      },
      {
        title: 'Campos del certificado',
        items: [
          { label: 'ID de clave', text: 'Identificador que sshd registra para el titular. La CA lo fija como principals@nombre de la CA, salvo que permita a los solicitantes elegirlo.' },
          { label: 'Principales', text: 'Nombres de usuario (certificado de usuario) o nombres de host (certificado de host) para los que este certificado es válido. Separados por comas.' },
          { label: 'Validez', text: 'Duración del certificado. Elegir un valor predefinido (1h, 8h, 24h, 7d, 30d, 90d, 365d) o indicar segundos personalizados. Válido desde 5 minutos antes de la emisión, para los servidores cuyo reloj va con retraso (v2.252).' },
          { label: 'Extensiones', text: 'Extensiones SSH como permit-pty, permit-agent-forwarding. Solo aplicables a los certificados de usuario.' },
          { label: 'Opciones críticas', text: 'Solo certificados de usuario: force-command, source-address (direcciones o redes CIDR, separadas por comas) y verify-required, más las opciones de proveedor con la forma nombre@dominio. Los certificados de host no llevan ninguna, y cualquier otra opción se rechaza (v2.252).' },
        ]
      },
      {
        title: 'Tipos de certificado',
        items: [
          { label: 'Certificado de usuario', text: 'Autentica a un usuario ante un servidor. El servidor debe confiar en la CA firmante mediante TrustedUserCAKeys.' },
          { label: 'Certificado de host', text: 'Autentica a un servidor ante los clientes. Los clientes confían en la CA mediante @cert-authority en known_hosts.' },
        ]
      },
      {
        title: 'Gestión',
        items: [
          { label: 'Revocar', text: 'Añadir un certificado a la lista de revocación de claves (KRL) de la CA. Los servidores deben estar configurados para comprobar la KRL. Un certificado revocado permanece en la KRL y no puede eliminarse hasta que caduque (v2.252).' },
          { label: 'Descargar', text: 'Descargar el certificado, la clave pública o la clave privada (solo en el modo de generación).' },
        ]
      },
    ],
    tips: [
      'Usar certificados de corta duración (8h-24h) para el acceso de usuarios, a fin de reducir el impacto de un compromiso de la clave.',
      'Se prefiere firmar una clave pública: la clave privada del usuario nunca sale de su equipo.',
      'Cuando una CA permite a los solicitantes fijar el ID de clave, mantenerlo descriptivo (por ejemplo "jdoe-prod-2025") para facilitar la auditoría de los registros.',
      'En los certificados de host, el principal debe coincidir con el nombre de host que usan los clientes para conectarse.',
    ],
    warnings: [
      'Al generar el par de claves, descargar la clave privada de inmediato: no se guarda y no puede recuperarse.',
      'Revocar un certificado solo funciona si los servidores están configurados para comprobar el archivo KRL de la CA.',
    ],
  },
  helpGuides: {
    title: 'Certificados SSH',
    content: `
## Visión general

Los certificados SSH son claves públicas SSH firmadas con metadatos: identidad, período de validez, principales permitidos y extensiones. Sustituyen el enfoque tradicional de \`authorized_keys\` por un control de acceso centralizado, limitado en el tiempo y auditable.

UCM emite certificados en formato OpenSSH compatibles con OpenSSH 5.4+ en cualquier plataforma.

## Modos de emisión

### Firmar clave pública (recomendado)
El usuario genera su propio par de claves y entrega a UCM solo la **clave pública**. La clave privada nunca sale de su equipo.

**Flujo del usuario:**
\`\`\`bash
# 1. Generar un par de claves (equipo del usuario)
ssh-keygen -t ed25519 -f ~/.ssh/id_work -C "jdoe@example.com"

# 2. Copiar el contenido de la clave pública
cat ~/.ssh/id_work.pub

# 3. Pegarlo en el formulario de firma de UCM
# 4. Descargar el certificado firmado
# 5. Save as ~/.ssh/id_work-cert.pub

# 6. Connect
ssh -i ~/.ssh/id_work user@server
\`\`\`

### Generar par de claves
UCM genera tanto el par de claves como el certificado. Usarlo cuando se necesite aprovisionar credenciales de forma centralizada.

> ⚠ **Descargar la clave privada de inmediato**: no se guarda en UCM y no puede recuperarse.

**Flujo:**
1. Seleccionar una CA y rellenar los detalles del certificado
2. Elegir el modo "Generar"
3. Hacer clic en **Emitir certificado**
4. Descargar los tres archivos:
   - Clave privada (\`keyid\`): **¡guardarla de forma segura!**
   - Certificado (\`keyid-cert.pub\`)
   - Clave pública (\`keyid.pub\`)

## Campos del certificado

### ID de clave
Un identificador incorporado al certificado. El servidor SSH lo registra cuando se usa el certificado, como identidad del titular.

La CA lo fija como \`principals@nombre de la CA\` (por ejemplo \`deploy@Production User CA\`). Un solicitante solo puede elegir otro en una CA donde **Permitir que los solicitantes definan el ID de clave** está marcado; en las demás, una solicitud así se rechaza.

**Buenos ID de clave, donde se permite:** \`jdoe-prod-2025\`, \`webserver-01\`, \`deploy-ci-pipeline\`

### Principales
Los principales definen **quién** (certificados de usuario) o **qué** (certificados de host) puede usar el certificado:

- **Certificados de usuario**: lista de nombres de usuario con los que el titular puede iniciar sesión (por ejemplo, \`deploy\`, \`admin\`)
- **Certificados de host**: lista de nombres de host o IP con los que se conoce el servidor (por ejemplo, \`web01.example.com\`, \`10.0.1.5\`)

> 💡 Se requiere al menos un principal: indicar los nombres de usuario o de host para los que el certificado es válido.

### Validez

Elegir un valor predefinido o fijar una duración personalizada:

| Valor | Caso de uso |
|--------|----------|
| 1 hora | Canalizaciones CI/CD, tareas puntuales |
| 8 horas | Acceso de una jornada laboral estándar |
| 24 horas | Acceso ampliado |
| 7 días | Acceso por sprint |
| 30 días | Rotación mensual |
| 365 días | Cuentas de servicio de larga duración |

Se recomiendan certificados de corta duración (8h-24h) para los usuarios humanos. Una validez mayor es aceptable para las cuentas de servicio automatizadas.

Un certificado es válido desde 5 minutos antes de su emisión, de modo que un servidor cuyo reloj va ligeramente retrasado lo acepta de inmediato; la duración sigue contando desde la emisión (v2.252).

### Extensiones (solo certificados de usuario)

| Extensión | Descripción |
|-----------|-------------|
| permit-pty | Permitir sesiones de terminal interactivas |
| permit-agent-forwarding | Permitir el reenvío del agente SSH |
| permit-X11-forwarding | Permitir el reenvío de pantalla X11 |
| permit-port-forwarding | Permitir el reenvío de puertos TCP |
| permit-user-rc | Permitir la ejecución de ~/.ssh/rc al iniciar sesión |

### Opciones críticas (solo certificados de usuario)

| Opción | Descripción |
|--------|-------------|
| force-command | Restringir el certificado a un único comando |
| source-address | Restringir a direcciones de origen o redes CIDR, separadas por comas (\`10.0.0.0/8,2001:db8::/32\`) |
| verify-required | Exigir una clave FIDO que haya verificado al usuario (PIN o biometría), sin valor |

Un servidor rechaza un certificado que lleva una opción crítica que no conoce, por lo que UCM solo firma estas y las opciones de proveedor con la forma \`nombre@dominio\`. OpenSSH no define ninguna opción crítica para los certificados de host: una solicitud de host que lleve una se rechaza (v2.252).

**Ejemplo:** un certificado con \`force-command=ls\` y \`source-address=10.0.0.0/8\` solo puede ejecutar \`ls\` y solo desde la red 10.x.x.x.

## Uso de los certificados

### Certificado de usuario
\`\`\`bash
# Colocar el certificado junto a la clave privada
# Si la clave es ~/.ssh/id_work, el certificado debe ser ~/.ssh/id_work-cert.pub
cp downloaded-cert.pub ~/.ssh/id_work-cert.pub

# SSH usa el certificado automáticamente
ssh user@server
\`\`\`

### Certificado de host
\`\`\`bash
# En el servidor: colocar el certificado de host
sudo cp host-cert.pub /etc/ssh/ssh_host_ed25519_key-cert.pub

# Add to sshd_config
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

En los clientes, añadir la CA de host a known_hosts:
\`\`\`
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Revocación

1. Seleccionar un certificado en la tabla
2. Hacer clic en **Revocar certificado** en el panel de detalle
3. El certificado se añade a la lista de revocación de claves (KRL) de la CA
4. Descargar y desplegar la KRL actualizada en los servidores (desde la página CA SSH)

Un certificado revocado permanece en la KRL, y en la lista, hasta que caduque: eliminarlo antes se rechaza, ya que la KRL se construye a partir de estos registros y el certificado volvería a aceptarse. Cada descarga de la KRL lleva un número de versión superior (v2.252).

La KRL nombra un certificado por su número de serie, que UCM asigna una sola vez por CA. Una instalación actualizada desde la 2.x, o que restauró un archivo 2.x, puede contener dos certificados de una misma CA con el mismo número de serie: la lista los marca como **Serie compartida**, y revocar uno los revoca todos; cuando uno de ellos ya estaba revocado, los demás se revocan con él. Revocarlos y emitir certificados nuevos. Un certificado de número de serie 0, que OpenSSH lee como sin numerar (uno importado, por ejemplo), figura en la KRL por su ID de clave una vez revocado, como hace OpenSSH: todos los certificados de la CA con ese ID de clave, sea cual sea su número de serie, se rechazan con él, y UCM los revoca con él. Un certificado con ese ID de clave ya no puede emitirse ni importarse bajo la CA. La clave en sí y los certificados de otras CA siguen siendo válidos.

> ⚠ La revocación solo surte efecto cuando los servidores comprueban la KRL mediante \`RevokedKeys\` en sshd_config.

## Solución de problemas

| Problema | Solución |
|-------|----------|
| Permission denied (publickey) | Verificar que el servidor confía en la CA (TrustedUserCAKeys) |
| El certificado no se usa | Asegurar que el archivo del certificado se llama \`<clave>-cert.pub\` junto a la clave privada |
| Principal no coincide | El nombre de usuario con el que se conecta por SSH debe figurar en los principales del certificado |
| Certificado caducado | Emitir un certificado nuevo con la validez adecuada |
| Falla la verificación del host | Añadir la CA de host a known_hosts con @cert-authority |
`
  },
}
