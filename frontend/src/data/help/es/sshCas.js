export default {
  helpContent: {
    title: 'Autoridades de certificación SSH',
    subtitle: 'Gestiona las CA SSH para la autenticación de usuarios y hosts',
    overview: 'Crea y gestiona autoridades de certificación SSH siguiendo los estándares de OpenSSH. Las CA SSH eliminan la necesidad de distribuir claves públicas individualmente — en su lugar, los servidores y usuarios confían en la CA, y la CA firma certificados que otorgan acceso.',
    sections: [
      {
        title: 'Tipos de CA',
        items: [
          { label: 'User CA', text: 'Firma certificados de usuario para la conexión SSH. Los servidores confían en esta CA y aceptan cualquier certificado firmado por ella.' },
          { label: 'Host CA', text: 'Firma certificados de host para acreditar la identidad del servidor. Los clientes confían en esta CA para verificar que se conectan al servidor correcto.' },
        ]
      },
      {
        title: 'Algoritmos de clave',
        items: [
          { label: 'Ed25519', text: 'Moderno, rápido, claves pequeñas (256 bits). Recomendado para nuevos despliegues.' },
          { label: 'ECDSA P-256 / P-384', text: 'Claves de curva elíptica, ampliamente soportadas. Buen equilibrio entre seguridad y compatibilidad.' },
          { label: 'RSA 2048 / 4096', text: 'Algoritmo tradicional. Use 4096 bits para CAs de larga duración. Mayor compatibilidad con sistemas antiguos.' },
        ]
      },
      {
        title: 'Configuración del servidor',
        items: [
          { label: 'Script de configuración', text: 'Descargue un script shell POSIX que configura automáticamente sshd para confiar en esta CA. Compatible con las principales distribuciones Linux.' },
          { label: 'Configuración manual', text: 'Copie la clave pública de la CA y añada TrustedUserCAKeys (User CA) o HostCertificate (Host CA) en sshd_config.' },
        ]
      },
      {
        title: 'Revocación de claves',
        items: [
          { label: 'KRL (Key Revocation List)', text: 'Formato binario compacto para revocar certificados individuales. Se configura mediante RevokedKeys en sshd_config.' },
          { label: 'Descargar KRL', text: 'Descargue el archivo KRL actual desde el panel de detalle de la CA.' },
        ]
      },
    ],
    tips: [
      'Use CAs separadas para certificados de usuario y de host — nunca las mezcle.',
      'Ed25519 es recomendado para nuevos despliegues por su velocidad y seguridad.',
      'Descargue el script de configuración para una puesta en marcha sencilla del servidor — gestiona la copia de seguridad y la validación automáticamente.',
    ],
    warnings: [
      'Eliminar una CA no revoca los certificados que ha firmado — revóquelos primero o actualice la confianza del servidor.',
      'Si la clave privada de la CA se ve comprometida, todos los certificados firmados por ella deben considerarse no confiables.',
    ],
  },
  helpGuides: {
    title: 'Autoridades de certificación SSH',
    content: `
## Descripción general

Las autoridades de certificación SSH (CA) son la base de la autenticación basada en certificados SSH. En lugar de distribuir claves públicas individuales a cada servidor, se crea una CA y se configuran los servidores para que confíen en ella. Cualquier certificado firmado por la CA se acepta automáticamente.

UCM soporta el formato de certificado OpenSSH (RFC 4253 + extensiones OpenSSH), que es comprendido de forma nativa por OpenSSH 5.4+ — no se requiere software adicional en servidores ni clientes.

## Tipos de CA

### User CA
Una User CA firma certificados que autentican **usuarios ante servidores**. Cuando un servidor confía en una User CA, cualquier usuario que presente un certificado válido firmado por esa CA puede iniciar sesión (sujeto a la coincidencia de principals).

**Configuración del servidor:**
\`\`\`
# /etc/ssh/sshd_config
TrustedUserCAKeys /etc/ssh/user_ca.pub
\`\`\`

### Host CA
Una Host CA firma certificados que autentican **servidores ante clientes**. Cuando un cliente confía en una Host CA, puede verificar que el servidor al que se conecta es legítimo — eliminando las advertencias TOFU (Trust On First Use).

**Configuración del cliente:**
\`\`\`
# ~/.ssh/known_hosts
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Crear una CA

1. Haga clic en **Crear CA SSH**
2. Introduzca un nombre descriptivo (ej.: «CA de usuario Producción»)
3. Seleccione el tipo de CA: **User** o **Host**
4. Elija el algoritmo de clave:
   - **Ed25519** — Recomendado. Rápido, claves pequeñas, seguridad moderna.
   - **ECDSA P-256/P-384** — Buena compatibilidad y seguridad.
   - **RSA 2048/4096** — Mayor compatibilidad, claves más grandes.
5. Opcionalmente, defina la validez máxima y las extensiones predeterminadas
6. Haga clic en **Crear**

> 💡 Use CAs separadas para certificados de usuario y de host. Nunca use una misma CA para ambos propósitos.

## Configuración del servidor

### Script de configuración automática

UCM genera un script shell POSIX que configura automáticamente su servidor:

1. Abra el panel de detalle de la CA
2. Haga clic en **Descargar script de configuración**
3. Transfiera el script a su servidor
4. Ejecútelo:

\`\`\`bash
chmod +x setup-ssh-ca.sh
sudo ./setup-ssh-ca.sh
\`\`\`

El script:
- Detecta su sistema operativo y sistema de inicio
- Realiza una copia de seguridad de sshd_config antes de cualquier cambio
- Instala la clave pública de la CA
- Añade TrustedUserCAKeys (User CA) o HostCertificate (Host CA)
- Valida la configuración con \`sshd -t\`
- Reinicia sshd solo si la validación es exitosa
- Soporta \`--dry-run\` para previsualizar los cambios

### Configuración manual

#### User CA
\`\`\`bash
# Copie la clave pública de la CA al servidor
echo "ssh-ed25519 AAAA... user-ca" | sudo tee /etc/ssh/user_ca.pub

# Añada a sshd_config
echo "TrustedUserCAKeys /etc/ssh/user_ca.pub" | sudo tee -a /etc/ssh/sshd_config

# Reinicie sshd
sudo systemctl restart sshd
\`\`\`

#### Host CA
\`\`\`bash
# Firme la clave de host del servidor
# Luego añada a sshd_config:
echo "HostCertificate /etc/ssh/ssh_host_ed25519_key-cert.pub" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
\`\`\`

## Listas de revocación de claves (KRL)

Las CA SSH soportan listas de revocación de claves para invalidar certificados comprometidos:

1. Revoque certificados desde la página de Certificados SSH
2. Descargue la KRL actualizada desde el panel de detalle de la CA
3. Despliegue el archivo KRL en los servidores:

\`\`\`bash
# Añada a sshd_config
RevokedKeys /etc/ssh/revoked_keys
\`\`\`

> ⚠ Los servidores deben estar configurados para verificar la KRL. La revocación no surte efecto hasta que la KRL se haya desplegado.

## Buenas prácticas

| Práctica | Recomendación |
|----------|---------------|
| CAs separadas | Use CAs distintas para certificados de usuario y de host |
| Algoritmo de clave | Ed25519 para nuevos despliegues, RSA 4096 para compatibilidad con sistemas antiguos |
| Duración de la CA | Mantenga las CAs con larga vigencia; use certificados efímeros en su lugar |
| Copia de seguridad | Exporte y almacene la clave privada de la CA de forma segura |
| Asignación de principals | Asigne principals a nombres de usuario específicos, no a comodines |
`
  }
}
