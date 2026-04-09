export default {
  helpContent: {
    title: 'Certificados SSH',
    subtitle: 'Emitir y gestionar certificados OpenSSH',
    overview: 'Emita certificados SSH firmados por sus CA SSH. Los certificados reemplazan la gestión manual de authorized_keys proporcionando acceso limitado en el tiempo, restringido por principal, con caducidad automática. Se admiten tanto certificados de usuario como de host.',
    sections: [
      {
        title: 'Modos de emisión',
        items: [
          { label: 'Modo firma', text: 'Pegue una clave pública SSH existente para firmarla. La clave privada permanece en la máquina del usuario — UCM nunca la ve.' },
          { label: 'Modo generación', text: 'UCM genera un nuevo par de claves y firma el certificado. Descargue la clave privada de inmediato — no podrá recuperarse posteriormente.' },
        ]
      },
      {
        title: 'Campos del certificado',
        items: [
          { label: 'Key ID', text: 'Identificador único del certificado. Aparece en los registros SSH para auditoría.' },
          { label: 'Principals', text: 'Nombres de usuario (certificado de usuario) o nombres de host (certificado de host) para los que este certificado es válido. Separados por comas.' },
          { label: 'Validez', text: 'Tiempo de vida del certificado. Elija una opción predefinida (1h, 8h, 24h, 7d, 30d, 90d, 365d) o establezca una duración personalizada en segundos.' },
          { label: 'Extensions', text: 'Extensiones SSH como permit-pty, permit-agent-forwarding. Solo aplicables a certificados de usuario.' },
          { label: 'Critical Options', text: 'Restricciones como force-command o source-address para limitar el uso del certificado.' },
        ]
      },
      {
        title: 'Tipos de certificados',
        items: [
          { label: 'Certificado de usuario', text: 'Autentica a un usuario ante un servidor. El servidor debe confiar en la CA firmante mediante TrustedUserCAKeys.' },
          { label: 'Certificado de host', text: 'Autentica a un servidor ante los clientes. Los clientes confían en la CA a través de @cert-authority en known_hosts.' },
        ]
      },
      {
        title: 'Gestión',
        items: [
          { label: 'Revocar', text: 'Añade un certificado a la lista de revocación de claves (KRL) de la CA. Los servidores deben estar configurados para verificar la KRL.' },
          { label: 'Descargar', text: 'Descargue el certificado, la clave pública o la clave privada (solo modo generación).' },
        ]
      },
    ],
    tips: [
      'Use certificados efímeros (8h–24h) para el acceso de usuarios, minimizando el impacto de una clave comprometida.',
      'El modo firma es preferible — la clave privada del usuario nunca sale de su máquina.',
      'Los Key ID deben ser descriptivos (ej.: «jdoe-prod-2025») para facilitar la auditoría de registros.',
      'Para certificados de host, el principal debe coincidir con el nombre de host que usan los clientes para conectarse.',
    ],
    warnings: [
      'En modo generación, descargue la clave privada de inmediato — no se almacena y no puede recuperarse.',
      'La revocación de un certificado solo funciona si los servidores están configurados para verificar el archivo KRL de la CA.',
    ],
  },
  helpGuides: {
    title: 'Certificados SSH',
    content: `
## Descripción general

Los certificados SSH son claves públicas SSH firmadas con metadatos: identidad, período de validez, principals permitidos y extensiones. Reemplazan el enfoque tradicional de \`authorized_keys\` con un control de acceso centralizado, limitado en el tiempo y auditable.

UCM emite certificados en formato OpenSSH compatibles con OpenSSH 5.4+ en cualquier plataforma.

## Modos de emisión

### Modo firma (recomendado)
El usuario genera su propio par de claves y proporciona solo la **clave pública** a UCM. La clave privada nunca sale de la máquina del usuario.

**Flujo de trabajo del usuario:**
\`\`\`bash
# 1. Generar un par de claves (máquina del usuario)
ssh-keygen -t ed25519 -f ~/.ssh/id_work -C "jdoe@example.com"

# 2. Copiar el contenido de la clave pública
cat ~/.ssh/id_work.pub

# 3. Pegar en el formulario de firma de UCM
# 4. Descargar el certificado firmado
# 5. Guardar como ~/.ssh/id_work-cert.pub

# 6. Conectarse
ssh -i ~/.ssh/id_work user@server
\`\`\`

### Modo generación
UCM genera tanto el par de claves como el certificado. Úselo cuando necesite provisionar credenciales de forma centralizada.

> ⚠ **Descargue la clave privada de inmediato** — no se almacena en UCM y no puede recuperarse.

**Procedimiento:**
1. Seleccione una CA y complete los datos del certificado
2. Elija el modo «Generar»
3. Haga clic en **Emitir**
4. Descargue los tres archivos:
   - Clave privada (\`keyid\`) — **¡Guárdela de forma segura!**
   - Certificado (\`keyid-cert.pub\`)
   - Clave pública (\`keyid.pub\`)

## Campos del certificado

### Key ID
Un identificador único incorporado en el certificado. Aparece en los registros del servidor SSH cuando se utiliza el certificado, lo que lo hace esencial para la auditoría.

**Buenos ejemplos de Key ID:** \`jdoe-prod-2025\`, \`webserver-01\`, \`deploy-ci-pipeline\`

### Principals
Los principals definen **quién** (certificados de usuario) o **qué** (certificados de host) autoriza el certificado:

- **Certificados de usuario**: lista de nombres de usuario con los que el titular puede iniciar sesión (ej.: \`deploy\`, \`admin\`)
- **Certificados de host**: lista de nombres de host o IPs por los que el servidor es conocido (ej.: \`web01.example.com\`, \`10.0.1.5\`)

> 💡 Si no se especifican principals, el certificado funciona para cualquier principal — lo cual suele ser demasiado permisivo.

### Validez

Elija una opción predefinida o establezca una duración personalizada:

| Opción | Caso de uso |
|--------|-------------|
| 1 hora | Pipelines CI/CD, tareas puntuales |
| 8 horas | Acceso durante la jornada laboral |
| 24 horas | Acceso extendido |
| 7 días | Acceso por sprint |
| 30 días | Rotación mensual |
| 365 días | Cuentas de servicio de larga duración |

Los certificados efímeros (8h–24h) se recomiendan para usuarios humanos. Una validez más larga es aceptable para cuentas de servicio automatizadas.

### Extensions (solo certificados de usuario)

| Extension | Descripción |
|-----------|-------------|
| permit-pty | Permite sesiones de terminal interactivo |
| permit-agent-forwarding | Permite el reenvío del agente SSH |
| permit-X11-forwarding | Permite el reenvío de pantalla X11 |
| permit-port-forwarding | Permite el reenvío de puertos TCP |
| permit-user-rc | Permite la ejecución de ~/.ssh/rc al iniciar sesión |

### Critical Options

| Opción | Descripción |
|--------|-------------|
| force-command | Restringe el certificado a un único comando |
| source-address | Restringe a direcciones IP o CIDRs de origen específicos |

**Ejemplo:** Un certificado con \`force-command=ls\` y \`source-address=10.0.0.0/8\` solo puede ejecutar \`ls\` y solo desde la red 10.x.x.x.

## Uso de los certificados

### Certificado de usuario
\`\`\`bash
# Coloque el certificado junto a la clave privada
# Si la clave es ~/.ssh/id_work, el certificado debe ser ~/.ssh/id_work-cert.pub
cp downloaded-cert.pub ~/.ssh/id_work-cert.pub

# SSH utiliza el certificado automáticamente
ssh user@server
\`\`\`

### Certificado de host
\`\`\`bash
# En el servidor: coloque el certificado de host
sudo cp host-cert.pub /etc/ssh/ssh_host_ed25519_key-cert.pub

# Añada a sshd_config
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

En los clientes, añada la Host CA a known_hosts:
\`\`\`
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Revocación

1. Seleccione un certificado en la tabla
2. Haga clic en **Revocar** en el panel de detalle
3. El certificado se añade a la lista de revocación de claves (KRL) de la CA
4. Descargue y despliegue la KRL actualizada en los servidores (desde la página de CA SSH)

> ⚠ La revocación solo surte efecto cuando los servidores verifican la KRL mediante \`RevokedKeys\` en sshd_config.

## Solución de problemas

| Problema | Solución |
|----------|----------|
| Permission denied (publickey) | Verifique que la CA sea de confianza en el servidor (TrustedUserCAKeys) |
| Certificado no utilizado | Asegúrese de que el archivo del certificado se llame \`<clave>-cert.pub\` junto a la clave privada |
| Discrepancia de principal | El nombre de usuario SSH debe figurar en los principals del certificado |
| Certificado caducado | Emita un nuevo certificado con una validez adecuada |
| Verificación de host fallida | Añada la Host CA a known_hosts con @cert-authority |
`
  }
}
