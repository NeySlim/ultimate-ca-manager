export default {
  helpContent: {
    title: 'Autoridades de certificación SSH',
    subtitle: 'Gestionar las CA SSH para la autenticación de usuarios y hosts',
    overview: 'Cree y gestione autoridades de certificación SSH conforme a los estándares de OpenSSH. Las CA SSH eliminan la necesidad de distribuir claves públicas individuales: los servidores y los usuarios confían en la CA, y la CA firma los certificados que conceden el acceso.',
    sections: [
      {
        title: 'Tipos de CA',
        items: [
          { label: 'CA de usuario', text: 'Firma certificados de usuario para el inicio de sesión SSH. Los servidores confían en esta CA y aceptan cualquier certificado que firme.' },
          { label: 'CA de host', text: 'Firma certificados de host para demostrar la identidad del servidor. Los clientes confían en esta CA para verificar que se conectan al servidor correcto.' },
        ]
      },
      {
        title: 'Algoritmos de clave',
        items: [
          { label: 'Ed25519', text: 'Moderno, rápido, claves pequeñas (256 bits). Recomendado para nuevas implementaciones.' },
          { label: 'ECDSA P-256 / P-384 / P-521', text: 'Claves de curva elíptica, ampliamente compatibles. Buen equilibrio entre seguridad y compatibilidad.' },
          { label: 'RSA 4096', text: 'Algoritmo tradicional, siempre de 4096 bits. La mayor compatibilidad con sistemas antiguos.' },
        ]
      },
      {
        title: 'CA SSH respaldadas por HSM',
        items: [
          { label: 'Almacenamiento de clave', text: 'Al crearla, elija Local o HSM, luego el proveedor y una clave de firma sin usar. La CA toma su tipo de clave de la clave y la clave privada nunca sale del HSM' },
          { label: 'Algoritmos', text: 'Claves RSA y ECDSA P-256, P-384 o P-521. No se ofrecen claves Ed25519: la firma HSM de UCM no cubre EdDSA, por lo que una CA SSH Ed25519 es una clave en software. Tampoco se ofrecen claves Brainpool ni ML-DSA: UCM firma con ellas en un HSM para las CA X.509, pero los certificados OpenSSH no tienen un tipo de clave para ellas' },
          { label: 'Una clave, una autoridad', text: 'Una clave respalda una sola autoridad, X.509 o SSH. Una clave ya en uso no se ofrece, y una solicitud que la nombra se rechaza (409) con el nombre de la CA que la tiene. Ni la clave ni su proveedor pueden eliminarse mientras exista la CA' },
          { label: 'Permisos', text: 'write:ssh_cas y read:hsm. Sin read:hsm la opción HSM está deshabilitada, y un rechazo (403) indica el permiso que falta' },
          { label: 'FIPS y HA', text: 'En modo FIPS no se ofrece una clave que el modo FIPS rechaza. En modo HA, una clave en SoftHSM o en un lector local de tarjetas inteligentes se rechaza (409), porque existe en un solo nodo' },
          { label: 'Token inaccesible', text: 'Si no se puede alcanzar el proveedor al crear la CA (503), no se crea nada: compruebe el proveedor en la gestión de HSM y vuelva a intentarlo' },
        ]
      },
      {
        title: 'Configuración del servidor',
        items: [
          { label: 'Script de instalación para Linux/macOS', text: 'Descargue un script de shell POSIX (.sh) que configura automáticamente sshd para que confíe en esta CA. Instalación rápida: curl -sSL <url> | sudo bash' },
          { label: 'Script de instalación para Windows', text: 'Descargue un script de PowerShell (.ps1) que configura el servidor OpenSSH de Windows (escribe la clave pública de la CA en %ProgramData%\\ssh, restringe las ACL, añade TrustedUserCAKeys / HostCertificate a sshd_config, valida con sshd -T y reinicia sshd). Instalación rápida: iwr <url> | iex' },
          { label: 'Bloque de diagnóstico', text: 'Si falla Add-WindowsCapability (WSUS / unido al dominio), el script imprime un bloque etiquetado que explica el estado de la política y tres vías de solución; nunca modifica por sí mismo la política de WSUS / WU' },
          { label: 'Simulación', text: 'Ambos scripts admiten un indicador -DryRun / --dry-run para previsualizar los cambios sin aplicarlos' },
          { label: 'Configuración manual', text: 'Copie la clave pública de la CA y añada TrustedUserCAKeys (CA de usuario) o HostCertificate (CA de host) a sshd_config' },
        ]
      },
      {
        title: 'Revocación de claves',
        items: [
          { label: 'KRL (lista de revocación de claves)', text: 'Formato binario compacto para revocar certificados individuales. Se configura mediante RevokedKeys en sshd_config.' },
          { label: 'Descargar KRL', text: 'Descargue el archivo KRL actual desde el panel de detalle de la CA.' },
        ]
      },
      {
        title: 'Formatos de TTL',
        items: [
          { label: 'Duraciones con sufijo', text: 'TTL predeterminado y TTL máximo aceptan 24h, 7d, 365d, con los sufijos s, m, h, d, w, y' },
          { label: 'Números sin sufijo', text: 'Un número sin más se interpreta como segundos (p. ej., 3600 = 1 hora)' },
          { label: 'Validación', text: 'Los valores mal formados se rechazan con un error que indica los formatos aceptados' },
        ]
      },
      {
        title: 'Principals permitidos',
        items: [
          { label: 'Principals permitidos', text: 'Patrones separados por comas (p. ej., deploy, team-*). Todo principal de una solicitud debe coincidir con alguno de ellos.' },
          { label: 'Permitir cualquier principal', text: 'Una CA con la lista vacía firma para cualquier nombre, root incluido, solo cuando esta opción está marcada. En otro caso no firma nada.' },
          { label: 'Actualización', text: 'Las CA creadas antes de la 2.245 sin lista siguen firmando para cualquier principal: la actualización marca la opción para ellas.' },
        ]
      },
      {
        title: 'ID de clave',
        items: [
          { label: 'Definido por la CA', text: 'sshd registra el ID de clave como la identidad del titular. Por defecto la CA nombra cada certificado principals@nombre de la CA, y una solicitud que define otro ID de clave se rechaza.' },
          { label: 'Permitir que los solicitantes definan el ID de clave', text: 'Márquela para que los solicitantes elijan el suyo, p. ej. un número de ticket o de empleado.' },
          { label: 'Actualización', text: 'Desde la 2.249, las CA existentes también empiezan con la opción desactivada.' },
        ]
      },
    ],
    tips: [
      'Use CA distintas para los certificados de usuario y de host, nunca las mezcle.',
      'Se recomienda Ed25519 para nuevas implementaciones por su velocidad y seguridad.',
      'Descargue el script de instalación para configurar el servidor fácilmente: gestiona la copia de seguridad y la validación automáticamente.',
    ],
    warnings: [
      'No se puede eliminar una CA mientras queden certificados firmados por ella: elimínelos primero y actualice la confianza de los servidores.',
      'Si la clave privada de la CA se ve comprometida, todos los certificados firmados por ella deben considerarse no fiables.',
    ],
  },
  helpGuides: {
    title: 'Autoridades de certificación SSH',
    content: `
## Descripción general

Las autoridades de certificación (CA) SSH son la base de la autenticación SSH mediante certificados. En lugar de distribuir claves públicas individuales a cada servidor, se crea una CA y se configuran los servidores para que confíen en ella. Cualquier certificado firmado por la CA se acepta entonces automáticamente.

UCM admite el formato de certificado de OpenSSH (RFC 4253 y extensiones de OpenSSH), que OpenSSH 5.4+ entiende de forma nativa: no hace falta software adicional en servidores ni clientes.

## Tipos de CA

### CA de usuario
Una CA de usuario firma certificados que autentican a **los usuarios ante los servidores**. Cuando un servidor confía en una CA de usuario, cualquier usuario que presente un certificado válido firmado por esa CA puede iniciar sesión (sujeto a la coincidencia de principals).

**Configuración del servidor:**
\`\`\`
# /etc/ssh/sshd_config
TrustedUserCAKeys /etc/ssh/user_ca.pub
\`\`\`

### CA de host
Una CA de host firma certificados que autentican **los servidores ante los clientes**. Cuando un cliente confía en una CA de host, puede verificar que el servidor al que se conecta es legítimo: se eliminan los avisos de «confianza en el primer uso» (TOFU).

**Configuración del cliente:**
\`\`\`
# ~/.ssh/known_hosts
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Crear una CA

1. Pulse **Crear CA SSH**
2. Introduzca un nombre descriptivo (p. ej., "CA de usuarios de producción")
3. Seleccione el tipo de CA: **Usuario** o **Host**
4. Elija el algoritmo de clave:
   - **Ed25519**: recomendado. Rápido, claves pequeñas, seguridad moderna.
   - **ECDSA P-256/P-384/P-521**: buena compatibilidad y seguridad.
   - **RSA 4096**: la mayor compatibilidad, claves más grandes.
5. Opcionalmente, defina la validez máxima y las extensiones predeterminadas
6. Indique los principals permitidos o marque **Permitir cualquier principal**
7. Pulse **Crear**

### Con una clave de HSM

Una CA SSH puede conservar su clave privada en un proveedor HSM.

1. En **Crear CA SSH**, defina **Almacenamiento de clave** como **HSM**
2. Elija el **Proveedor HSM** y luego la **Clave HSM existente**: solo se listan las claves de firma RSA y ECDSA P-256/P-384/P-521 sin usar
3. Pulse **Crear**. La CA toma su tipo de clave de la clave, y la clave privada nunca sale del token

Conviene saber:
- Una CA SSH en un HSM toma una clave RSA o ECDSA P-256, P-384 o P-521. No se ofrecen claves Ed25519: la firma HSM de UCM no cubre EdDSA, por lo que una CA SSH Ed25519 es una clave en software. Tampoco se ofrecen claves Brainpool ni ML-DSA: UCM firma con ellas en un HSM para las CA X.509, pero los certificados OpenSSH no tienen un tipo de clave para ellas.
- Una clave de HSM respalda una sola autoridad, X.509 o SSH. Una clave que ya tiene una CA se rechaza con el nombre de esa CA, y ni la clave ni su proveedor pueden eliminarse mientras exista la CA.
- Requiere \`write:ssh_cas\` y \`read:hsm\`. Sin \`read:hsm\` la opción **HSM** está deshabilitada.
- En modo FIPS no se ofrece una clave que el modo FIPS rechaza. En modo HA, una clave en SoftHSM o en un lector local de tarjetas inteligentes se rechaza, porque existe en un solo nodo.
- Si no se puede alcanzar el proveedor al crear la CA, no se crea nada.

### Principals permitidos

El campo **Principals permitidos** restringe los nombres para los que firma una CA, como patrones separados por comas (\`deploy\`, \`team-*\`, \`web??.example.com\`). Todo principal de una solicitud debe coincidir con alguno de ellos.

Una CA con la lista vacía no firma nada salvo que se marque **Permitir cualquier principal**: entonces firma para cualquier nombre, \`root\` incluido. Las CA creadas antes de la 2.245 sin lista se comportaban así de forma implícita; la actualización marca la opción para ellas, de modo que siguen funcionando.

### ID de clave

sshd registra el ID de clave de un certificado como la identidad del titular. La CA lo define como \`principals@nombre de la CA\` y rechaza una solicitud que defina otro, salvo que se marque **Permitir que los solicitantes definan el ID de clave**. La opción está desactivada en todas las CA, también en las existentes desde la 2.249.

### Formatos de TTL

Los campos **TTL predeterminado** y **TTL máximo** aceptan duraciones legibles:

- Valores con sufijo: \`24h\`, \`7d\`, \`365d\` (sufijos aceptados: \`s\`, \`m\`, \`h\`, \`d\`, \`w\`, \`y\`)
- Números sin sufijo: se interpretan como **segundos** (p. ej., \`3600\` = 1 hora)

Los valores mal formados se rechazan con un error que indica los formatos aceptados.

> 💡 Use CA distintas para los certificados de usuario y de host. Nunca use una misma CA para ambos fines.

## Configuración del servidor

### Script de instalación automática

UCM genera un script de shell POSIX que configura automáticamente su servidor:

1. Abra la CA y luego su pestaña **Instalación rápida**
2. Pulse **Descargar .sh (Linux/macOS)**
3. Transfiera el script a su servidor
4. Ejecútelo:

\`\`\`bash
chmod +x setup-ssh-ca.sh
sudo ./setup-ssh-ca.sh
\`\`\`

El script:
- Detecta su sistema operativo y su sistema de inicio
- Hace una copia de seguridad de sshd_config antes de cualquier cambio
- Instala la clave pública de la CA
- Añade TrustedUserCAKeys (CA de usuario) o HostCertificate (CA de host)
- Valida la configuración con \`sshd -t\`
- Reinicia sshd solo si la validación se supera
- Admite \`--dry-run\` para previsualizar los cambios

### Configuración manual

#### CA de usuario
\`\`\`bash
# Copiar la clave pública de la CA al servidor
echo "ssh-ed25519 AAAA... user-ca" | sudo tee /etc/ssh/user_ca.pub

# Añadir a sshd_config
echo "TrustedUserCAKeys /etc/ssh/user_ca.pub" | sudo tee -a /etc/ssh/sshd_config

# Reiniciar sshd
sudo systemctl restart sshd
\`\`\`

#### CA de host
\`\`\`bash
# Firmar la clave de host del servidor
# Después, añadir a sshd_config:
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

## Listas de revocación de claves (KRL)

Las CA SSH admiten listas de revocación de claves para invalidar certificados comprometidos:

1. Revoque los certificados desde la página Certificados SSH
2. Descargue la KRL actualizada desde el panel de detalle de la CA
3. Despliegue el archivo KRL en los servidores:

\`\`\`bash
# Añadir a sshd_config
RevokedKeys /etc/ssh/revoked_keys
\`\`\`

> ⚠ Los servidores deben estar configurados para comprobar la KRL. La revocación no surte efecto hasta que se despliega la KRL.

## Buenas prácticas

| Práctica | Recomendación |
|----------|---------------|
| CA separadas | Use CA distintas para los certificados de usuario y de host |
| Algoritmo de clave | Ed25519 para nuevas implementaciones, RSA 4096 por compatibilidad con sistemas antiguos |
| Vida de la CA | Mantenga las CA de larga duración; use en su lugar certificados de corta duración |
| Copia de seguridad | Conserve las copias de seguridad de UCM: la clave privada de la CA no puede exportarse por sí sola |
| Asignación de principals | Asigne los principals a nombres de usuario concretos, no a comodines |
`
  }
}
