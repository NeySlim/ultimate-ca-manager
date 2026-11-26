export default {
  helpContent: {
    title: 'Hosts SSH',
    subtitle: 'Inscribir servidores y renovar sus certificados de host',
    overview: 'El agente SSH instalado en un servidor mantiene sshd al día con UCM: descarga la KRL de una CA de usuario y, con un token de inscripción de un solo uso, obtiene un certificado de host para la clave del propio servidor, que luego renueva por sí mismo. Esta página lista los servidores inscritos y los tokens de inscripción.',
    sections: [
      {
        title: 'Inscripción',
        items: [
          { label: 'Token', text: 'Cree un token para una CA de host y los nombres de host del servidor. Se muestra una vez, sirve una vez y caduca tras la duración elegida, una hora por defecto.' },
          { label: 'Comando', text: 'Ejecute como root en el servidor el comando mostrado con el token: el agente envía la clave pública de host del servidor e instala el certificado de host recibido como HostCertificate.' },
          { label: 'Nombres', text: 'El servidor puede pedir una parte de los nombres del token; un nombre que el token no incluye se rechaza.' },
        ]
      },
      {
        title: 'Renovación',
        items: [
          { label: 'Cuándo', text: 'En cuanto a un certificado le queda el 30 % de su vida (ajustable por token), el agente pide un desafío a UCM en su siguiente sincronización, cada 15 minutos.' },
          { label: 'Prueba', text: 'El agente firma el desafío con la clave de host que certifica el certificado. UCM no guarda ningún secreto del host: la clave es la prueba.' },
          { label: 'Pausar y revocar', text: 'Pausar la renovación detiene las renovaciones hasta reanudarlas. Revocar el host revoca su certificado, que la KRL lista entonces, y pone fin a sus renovaciones.' },
        ]
      },
      {
        title: 'Estados',
        items: [
          { label: 'Válido, caducado, revocado', text: 'El estado del certificado que el host presenta ahora.' },
          { label: 'Última descarga de la KRL', text: 'Cuándo el agente del servidor descargó una KRL por última vez, según lo declara el agente. No declarado cuando el servidor no sigue ninguna KRL.' },
        ]
      },
    ],
    tips: [
      'Dé a los certificados de host una validez de semanas o meses: el agente los renueva, y revocar un host lo detiene al instante.',
      'Cree un token por servidor, con la duración necesaria para ejecutarlo allí.',
    ],
    warnings: [
      'Un token se muestra una vez: UCM solo guarda su huella.',
      'Quitar el agente de un servidor no revoca el host: revóquelo aquí.',
    ],
  },
  helpGuides: {
    title: 'Hosts SSH',
    content: `
## Descripción general

El agente SSH es un script de shell POSIX que UCM sirve a sus servidores. No contiene ningún secreto y solo descarga desde UCM: UCM nunca se conecta a un servidor. Hace dos cosas:

- mantiene sshd en la **KRL** de una CA de usuario, para que un certificado de usuario revocado se rechace en pocos minutos;
- **inscribe** el servidor en una CA de host, con un token de un solo uso, y **renueva** por sí mismo el certificado de host.

Necesita \`ssh-keygen\` y \`curl\` o \`wget\`, y se ejecuta con un temporizador de systemd, o una tarea cron, cada 15 minutos.

## Seguir una KRL

Abra la CA de usuario en **CA SSH**, pestaña **Instalación rápida**, y ejecute el comando **Agente SSH** como root en el servidor:

\`\`\`bash
curl -fsSL https://ucm.example.com:8443/ssh/setup/<refid>/agent | sudo sh
\`\`\`

El agente descarga primero la KRL en \`/etc/ssh/ucm/revoked_keys\`, luego añade \`RevokedKeys\` a sshd (en \`/etc/ssh/sshd_config.d\` cuando sshd_config lo incluye, si no al principio de sshd_config) y comprueba el resultado con \`sshd -t\`. En cada sincronización solo descarga la KRL si su versión cambió, la comprueba con \`ssh-keygen\`, rechaza una KRL más antigua que la instalada, reemplaza el archivo en un solo paso y recarga sshd.

La KRL es pública, como una CRL: \`/ssh/krl/<refid>\`. Su versión solo cambia cuando se revoca un certificado de la CA.

## Inscribir un servidor

1. Abra **Hosts SSH** y luego **Nuevo token de inscripción**
2. Elija la CA de host e introduzca los nombres de host del servidor (por ejemplo \`web01.example.com, web01\`)
3. Elija si lo desea la validez de los certificados, la duración del token y cuándo renovar
4. Copie el comando mostrado con el token y ejecútelo como root en el servidor antes de que caduque el token

\`\`\`bash
curl -fsSL https://ucm.example.com:8443/ssh/setup/<refid>/agent | sudo UCM_ENROLL_TOKEN=ucmh_... sh
\`\`\`

El agente envía la clave pública de host del servidor (Ed25519 primero, luego ECDSA, luego RSA; \`--host-key\` elige otra) con el token firmado por esa clave, lo que prueba que el servidor la posee, comprueba que el certificado recibido certifica esa clave, lo escribe junto a la clave y apunta \`HostCertificate\` a él. Añada \`-s -- --principal web01\` para pedir solo una parte de los nombres del token.

El token se muestra una vez y sirve una vez. El servidor nunca lo conserva: el agente se lo pasa a curl por una tubería (a wget, que no lee tuberías, por un archivo que solo root puede leer, borrado tras la solicitud). Un token sin usar puede revocarse en **Tokens de inscripción**.

Los clientes confían en la CA de host con una línea en \`known_hosts\`:

\`\`\`
@cert-authority *.example.com ssh-ed25519 AAAA...
\`\`\`

## Renovación

En cuanto al certificado de host le queda el 30 % de su vida (la proporción se ajusta por token), el agente pide un desafío a UCM, lo firma con la clave de host (\`ssh-keygen -Y sign\`) y recibe un nuevo certificado para los mismos nombres. UCM comprueba la firma con la clave que certifica el certificado actual: no se guarda ninguna contraseña ni token para el host.

Una renovación se rechaza cuando el host o su certificado está revocado, cuando el certificado ha caducado o cuando la renovación está en pausa. Tras un rechazo así el agente deja de pedir, salvo en una pausa; \`ucm-ssh-agent status\` indica el motivo. Un servidor rechazado definitivamente se inscribe de nuevo con un nuevo token.

## La página Hosts SSH

| Columna | Significado |
|---------|-------------|
| Principales | Los nombres del certificado de host |
| Caducidad | El fin del certificado actual |
| Renovación automática | Activa, o En pausa |
| Última descarga de la KRL | Cuándo el agente descargó una KRL por última vez, según lo declara |
| Estado | Válido, Caducado o Revocado |

**Pausar la renovación** detiene las renovaciones hasta **Reanudar la renovación**. **Revocar el host** revoca todos los certificados no caducados de su clave, el actual y los que sus renovaciones reemplazaron, que la KRL de la CA de host lista entonces, y pone fin a las renovaciones. Cada inscripción, renovación y rechazo figura en el registro de auditoría.

## Quitar el agente

\`\`\`bash
curl -fsSL https://ucm.example.com:8443/ssh/setup/<refid>/agent | sudo sh -s -- --uninstall
\`\`\`

El agente quita su temporizador, sus ajustes de sshd, la KRL y el certificado que instaló, y restaura un certificado que encontró en ese lugar. El host sigue listado en UCM: revóquelo allí.
`
  }
}
