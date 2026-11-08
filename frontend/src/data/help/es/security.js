export default {
  helpContent: {
    title: 'Configuración de seguridad',
    subtitle: 'Políticas de autenticación y acceso',
    overview: 'Configure políticas de contraseñas, gestión de sesiones, limitación de velocidad y seguridad de red. Estas configuraciones se aplican a nivel de sistema y afectan a todas las cuentas de usuario.',
    sections: [
      {
        title: 'Cifrado de claves privadas',
        items: [
          { label: 'Estado y contadores', text: 'Muestra si el cifrado está activado y cuántas claves privadas almacenadas están cifradas frente a sin cifrar' },
          { label: 'Activar / Desactivar', text: 'Cifra todas las claves privadas de CA y de certificados con AES-128 (Fernet, con HMAC-SHA256) bajo un archivo de clave maestra. Al activar elimina las copias de claves en texto plano y al desactivar las vuelve a crear' },
          { label: 'Primer arranque', text: 'Sin clave maestra, UCM crea /etc/ucm/master.key (0600) al arrancar y cifra las claves ya almacenadas. Un contenedor solo lo hace cuando /etc/ucm es un volumen con nombre o un directorio del host. Se omite con KEY_ENCRYPTION_KEY definida, con claves cifradas o una cadena de auditoría con clave ya en la base de datos, después de desactivar el cifrado aquí, o con UCM_AUTO_MASTER_KEY=false. En cada arranque una clave cargada también cifra los valores aún almacenados sin cifrar, y una clave que no los descifra pone a UCM en modo seguro. Haga una copia del archivo de clave' },
          { label: 'Archivos de clave en disco', text: 'Muestra cuántas copias de claves en texto plano quedan; use hooks de despliegue cuando otro servicio necesite un archivo de clave' },
          { label: 'UCM_REQUIRE_DB_ENCRYPTION_KEY', text: 'Variable de entorno opcional: rechaza arrancar sin una clave de cifrado de base de datos explícita' },
          { label: 'UCM_REQUIRE_KEY_ENCRYPTION', text: 'Variable de entorno opcional: rechaza arrancar si el cifrado de claves privadas no está activado' },
          { label: 'Cifrar claves restantes', text: 'Se muestra mientras el cifrado está activado y algunas claves o secretos siguen almacenados sin cifrar: los cifra, dejando como están los ya cifrados' },
        ]
      },
      {
        title: 'Política de contraseñas',
        items: [
          { label: 'Longitud mínima', text: 'Número mínimo de caracteres requeridos, de 6 a 32' },
          { label: 'Complejidad', text: 'Requerir letras mayúsculas, números y caracteres especiales, cada uno activado por separado' },
        ]
      },
      {
        title: 'Sesión y acceso',
        items: [
          { label: 'Tiempo de sesión', text: 'Cierre de sesión automático tras un período de inactividad (Ajustes › General)' },
          { label: 'Duración de sesión', text: 'Duración máxima de la sesión en horas, sea cual sea la actividad' },
          { label: 'Bloqueo de cuenta', text: 'Máximo de intentos de inicio de sesión y duración del bloqueo (Ajustes › General) bloquean una cuenta tras fallos repetidos. Los límites de solicitudes por IP se definen con las variables de entorno RATE_LIMIT_*, no en esta página' },
          { label: 'Lista de acceso de administración', text: 'Limitar la interfaz web y la API de gestión a las direcciones IP y redes indicadas' },
          { label: 'Aplicación de 2FA', text: 'Requerir autenticación de dos factores para todos los usuarios' },
        ]
      },
      {
        title: 'Lista de acceso de administración',
        items: [
          { label: 'Redes', text: 'Una dirección IPv4 o IPv6 o red CIDR por línea, hasta 100. Vacía significa sin restricción. IPv4 e IPv6 se indican por separado: 0.0.0.0/0 no admite a un cliente IPv6, ni ::/0 a un cliente IPv4' },
          { label: 'Qué se bloquea', text: 'Desde otras direcciones: la interfaz web, el inicio de sesión, la API /api/v2 (claves API incluidas) y el canal WebSocket responden 403' },
          { label: 'Siempre accesibles', text: 'ACME, SCEP, EST, OCSP, CRL/AIA, TSA, XCEP/WSTEP, el script de configuración SSH y los endpoints de estado' },
          { label: 'Su dirección', text: 'La sección muestra la dirección que el servidor ve para usted; una lista que no la incluya se rechaza' },
          { label: 'UCM_ADMIN_ALLOWED_NETWORKS', text: 'Variable de entorno (separada por comas) que prevalece sobre el ajuste y lo deja en solo lectura' },
          { label: 'UCM_ADMIN_ALLOWLIST_DISABLE', text: 'Establézcala en 1 y reinicie para desactivar la comprobación tras un bloqueo de acceso' },
        ]
      },
      {
        title: 'Autenticación mTLS',
        items: [
          { label: 'CA de confianza', text: 'La CA cuyos certificados de cliente se aceptan al iniciar sesión, y el emisor por defecto cuando un usuario genera uno. Se puede elegir cualquier CA cuyo certificado no esté revocado, incluidas las sin clave o sin conexión: una CA así no emite nada, por lo que sus usuarios suben certificados emitidos en otro lugar (v2.248). Es la única ancla de confianza del puerto HTTPS: un certificado de cliente de su padre o de una CA hermana se rechaza en el handshake TLS, así que confíe en una raíz para aceptar toda su jerarquía (v2.252)' },
          { label: 'Requerir certificado de cliente', text: 'Opcionalmente, haga que mTLS sea obligatorio para la interfaz web, cambiar la configuración mTLS requiere un reinicio del servicio' },
          { label: 'Mismo número de serie, otra CA (v2.251)', text: 'Una inscripción se identifica por su emisor y número de serie, de modo que un certificado de cliente puede inscribirse, importarse o asignarse aunque el certificado inscrito de otra CA tenga el mismo número de serie' },
          { label: 'Encabezados de reverse proxy (v2.252)', text: 'Detrás de un proxy que reenvía el certificado de cliente como encabezados, envíe el DN del emisor (X-SSL-Client-I-DN) junto con el número de serie, leído como hexadecimal, o el propio certificado (X-SSL-Client-Cert). Un número de serie sin su emisor no abre ninguna inscripción que haya registrado uno, y un certificado presentado no puede inscribirse sin él' },
          { label: 'Emisor revocado', text: 'Un certificado de cliente emitido bajo una CA revocada, en cualquier nivel de su cadena, no abre sesión y no puede inscribirse ni importarse (v2.252)' },
          { label: 'Claves generadas (v2.251)', text: 'Un certificado mTLS de usuario generado por UCM recibe una clave de la fortaleza de la CA emisora, RSA o una curva NIST que aceptan los navegadores, llevada al tipo más cercano que permitan las políticas, en lugar de siempre RSA-2048' },
        ]
      },
    ],
    tips: [
      'Active la limitación de velocidad para protegerse contra herramientas de ataque automatizadas',
      'Use la lista de acceso de administración para limitar la interfaz web a su VLAN de gestión, bastión o VPN',
    ],
    warnings: [
      'Restringir demasiado la política de contraseñas puede frustrar a los usuarios',
      'Detrás de un proxy inverso, defina UCM_BEHIND_PROXY y UCM_TRUSTED_PROXIES antes de usar la lista de acceso de administración; de lo contrario, todas las solicitudes parecen provenir del proxy',
      'Las configuraciones sensibles de seguridad (sesión, bloqueo, HSTS, URL pública, política de contraseñas) requieren admin:settings, los campos están bloqueados para los operadores',
    ],
  },
  helpGuides: {
    title: 'Configuración de seguridad',
    content: `
## Descripción general

Configuración de seguridad a nivel de sistema que afecta a todas las cuentas de usuario y patrones de acceso.

## Cifrado de claves privadas

Cifre todas las claves privadas de CAs y certificados almacenadas en la base de datos con AES-128 (Fernet, con HMAC-SHA256), protegidas por un archivo de clave maestra guardado fuera de la base de datos.

- **Estado y contadores**: La sección muestra si el cifrado está activado y cuántas claves están actualmente **cifradas** frente a **sin cifrar**
- **Primer arranque**: Una instalación sin clave maestra crea \`/etc/ucm/master.key\` (modo 0600) al arrancar y cifra las claves y secretos ya almacenados. En un contenedor esto ocurre solo cuando \`/etc/ucm\` es un volumen con nombre o un directorio del host, nunca un volumen anónimo. No ocurre cuando \`KEY_ENCRYPTION_KEY\` está definida, cuando la base de datos ya contiene claves cifradas (modo seguro) o una cadena de auditoría sellada con una clave anterior, después de desactivar el cifrado aquí, ni con \`UCM_AUTO_MASTER_KEY=false\`. También elimina las copias de claves en texto plano bajo \`data/private\`. En cada arranque una clave cargada también cifra los valores aún almacenados sin cifrar, y una clave que no los descifra pone a UCM en modo seguro hasta que se restaure la anterior. Haga una copia del archivo de clave: las copias de seguridad de UCM no la necesitan, pero una copia de la base de datos no puede descifrarse sin él
- **Activar cifrado**: Genera el archivo de clave maestra y cifra todas las claves privadas almacenadas, cuando no se creó ninguna clave en el primer arranque; se rechaza en un contenedor cuyo \`/etc/ucm\` no sobreviviría. Haga una copia de seguridad del archivo de clave de inmediato: sin él, las claves cifradas se pierden de forma permanente
- **Desactivar cifrado**: Descifra todas las claves privadas y vuelve al almacenamiento en texto plano (requiere confirmación). UCM no crea entonces ninguna clave en los arranques posteriores, hasta que se vuelva a activar el cifrado
- **Cifrar claves restantes**: Se muestra mientras el cifrado está activado y algunas claves o secretos siguen almacenados sin cifrar; los cifra, dejando como están los ya cifrados

### Aplicación en el arranque

Sin una clave de cifrado configurada, UCM registra una advertencia en el arranque pero sigue funcionando. Dos **variables de entorno opcionales** lo convierten en un fallo fatal:

- \`UCM_REQUIRE_DB_ENCRYPTION_KEY\`: rechaza arrancar sin una clave de cifrado de base de datos explícita (de lo contrario, los secretos de integración recurren a una clave derivada del id de la máquina)
- \`UCM_REQUIRE_KEY_ENCRYPTION\`: rechaza arrancar si el cifrado de claves privadas no está activado

Ambas aceptan \`1\`/\`true\`/\`yes\`/\`on\`. Una clave inválida se trata como fatal en lugar de recurrir silenciosamente al texto plano.

## Política de contraseñas

### Requisitos de complejidad
- **Longitud mínima**: De 6 a 32 caracteres (8 por defecto)
- **Requerir mayúsculas**: Al menos una letra mayúscula
- **Requerir números**: Al menos un dígito
- **Requerir caracteres especiales**: Al menos un símbolo

UCM no tiene ajuste de expiración de contraseñas ni de historial de contraseñas.

## Gestión de sesiones

### Tiempo de sesión
En **Ajustes › General**: cerrar sesión automáticamente a los usuarios después de N minutos de inactividad. Se aplica solo a sesiones de la interfaz web, no a claves API.

### Duración de sesión
Duración máxima de la sesión en horas, sea cual sea la actividad. El número de sesiones simultáneas por usuario no está limitado.

## Protección de inicio de sesión

### Máximo de intentos de inicio de sesión
En **Ajustes › General**: el número de inicios de sesión fallidos tras el cual se bloquea la **cuenta**.

### Duración del bloqueo
Cuánto tiempo permanece bloqueada la cuenta, en minutos.
Una cuenta bloqueada responde a un inicio de sesión por contraseña o LDAP con el mismo «Invalid credentials» que un nombre desconocido hasta que termina el bloqueo, de modo que la respuesta no revela que la cuenta existe; el bloqueo se registra en el registro de auditoría.

### Límites de solicitudes
Las solicitudes también se limitan por dirección IP de cliente, mediante las variables de entorno \`RATE_LIMIT_*\` (cubos de autenticación, pesado, estándar y protocolos; los clientes de red privada están exentos con \`RATE_LIMIT_TRUST_LAN\`). Las rutas de inicio de sesión tienen su propio límite, 5 intentos por minuto, indicado con \`Retry-After\` en la respuesta 429.

## Lista de acceso de administración

Limite la interfaz web y la API de gestión a una lista de direcciones IP y redes CIDR, IPv4 o IPv6, una por línea (hasta 100). Una lista vacía no restringe nada. IPv4 e IPv6 se indican por separado: \`0.0.0.0/0\` no admite a un cliente IPv6, y \`::/0\` no admite a un cliente IPv4.

- **Bloqueado desde otras direcciones**: la interfaz web y sus recursos, el inicio de sesión, toda llamada a \`/api/v2\` (claves API incluidas) y el canal WebSocket responden **403**
- **Siempre accesibles**: ACME y el proxy ACME, SCEP, EST, OCSP, CRL y AIA, TSA, XCEP/WSTEP, el script de configuración SSH y los endpoints de estado y métricas, para que los dispositivos y las sondas sigan funcionando
- **Su dirección**: la sección muestra la dirección que el servidor ve para usted. Una lista que no la incluya se rechaza, así que guardar no puede dejarle sin acceso
- **Auditoría**: cada cambio de la lista se registra en el registro de auditoría

### Variables de entorno
- \`UCM_ADMIN_ALLOWED_NETWORKS\`: lista separada por comas que prevalece sobre el ajuste y deja el campo en solo lectura
- \`UCM_ADMIN_ALLOWLIST_DISABLE=1\`: desactiva la comprobación tras un reinicio; úsela para recuperarse de un bloqueo de acceso y luego elimínela

### Proxy inverso, Docker y Kubernetes
Detrás de un proxy inverso, defina \`UCM_BEHIND_PROXY=1\` e incluya el proxy en \`UCM_TRUSTED_PROXIES\`; de lo contrario, todas las solicitudes parecen provenir del proxy. Con Docker en modo bridge y sin proxy, la dirección vista puede ser la posterior al NAT de Docker: compruebe la dirección mostrada antes de guardar.

> ⚠ Este filtro actúa a nivel de aplicación. Mantenga también un cortafuegos delante del puerto HTTPS.

## Autenticación de dos factores

### Aplicación
Requerir que todos los usuarios activen 2FA. Los usuarios que no hayan configurado 2FA recibirán un aviso en su próximo inicio de sesión. Una aplicación TOTP o una llave de seguridad registrada la satisface, tanto en el registro como al iniciar sesión. Mientras esté impuesta, TOTP solo puede desactivarse si queda una llave de seguridad, y la última llave solo puede eliminarse si queda TOTP. Un usuario cuya llave se convirtió en su segundo factor la conserva cuando se retira la imposición.

### Métodos soportados
- **TOTP**: Contraseñas de un solo uso basadas en tiempo (aplicaciones de autenticación)
- **WebAuthn**: Llaves de seguridad de hardware y biometría

> 💡 Aplique 2FA para las cuentas de administrador como mínimo. Considere aplicarla para todos los usuarios en entornos con alta exigencia de seguridad.

## Autenticación mTLS

Permita a los usuarios iniciar sesión con un certificado de cliente en lugar de una contraseña:

- **CA de confianza**: La CA cuyos certificados de cliente se aceptan al iniciar sesión, y el emisor por defecto cuando un usuario genera uno. Se puede elegir cualquier CA cuyo certificado no esté revocado, incluidas las sin clave o sin conexión: una CA así no emite nada, por lo que sus usuarios suben certificados emitidos en otro lugar (v2.248). Es la única ancla de confianza del puerto HTTPS: un certificado de cliente de su padre o de una CA hermana se rechaza en el handshake TLS, así que confíe en una raíz para aceptar toda su jerarquía (v2.252)
- **Requerir certificado de cliente**: Opcionalmente, haga que mTLS sea obligatorio para la interfaz web
- Cambiar la configuración mTLS requiere un reinicio del servicio
- **Emisor revocado**: Un certificado de cliente emitido bajo una CA revocada, en cualquier nivel de su cadena, no abre sesión y no puede inscribirse ni importarse (v2.252)

## Permisos requeridos

Las configuraciones sensibles de seguridad: sesión, bloqueo, HSTS, URL pública y política de contraseñas, requieren el permiso **admin:settings**. Para los operadores (solo write:settings), esos campos se muestran bloqueados; el resto de la tarjeta se guarda con normalidad.
`
  }
}
