export default {
  helpContent: {
    title: 'Single Sign-On',
    subtitle: 'Integración con SAML, OAuth2 y LDAP',
    overview: 'Configure Single Sign-On para que los usuarios se autentiquen mediante el proveedor de identidad de su organización. Admite los protocolos SAML 2.0, OAuth2/OIDC y LDAP.',
    sections: [
      {
        title: 'SAML 2.0',
        items: [
          { label: 'Proveedor de identidad', text: 'Configure la URL de metadatos del IdP o cargue el XML' },
          { label: 'URL de metadatos SP', text: 'Proporcione esta URL a su IdP para configurar automáticamente UCM como proveedor de servicios' },
          { label: 'Certificado SP', text: 'El certificado HTTPS de UCM incluido en los metadatos; el IdP debe confiar en él o rechazará los metadatos' },
          { label: 'ID de entidad', text: 'Identificador de entidad del proveedor de servicios UCM' },
          { label: 'URL ACS', text: 'URL de devolución del Assertion Consumer Service' },
          { label: 'Mapeo de atributos', text: 'Columna izquierda: el nombre del atributo enviado por el IdP. Columna derecha: el campo de UCM que rellena (username, email, fullname o groups). Ejemplo: user.userprincipalname → username. Un atributo ocupa una fila: una segunda fila con el mismo nombre se marca y el proveedor no se guarda hasta que se cambie o se quite una de ellas.' },
          { label: 'Grupos para el mapeo de roles', text: 'Se leen de los atributos mapeados a groups; si no, de groups y de los claims de grupos y roles de Microsoft Entra ID / AD FS. Cuando Entra ID envía groups.link en lugar de los grupos (usuarios en más de 150 grupos), se registra una advertencia y, si existen reglas de mapeo de roles, el usuario se rechaza: emita solo los grupos asignados a la aplicación, o roles de aplicación.' },
          { label: 'Inicio de sesión iniciado por el IdP', text: 'Acepta inicios de sesión lanzados desde el portal del IdP, verificados como cualquier otra respuesta. Activado para los proveedores creados antes de la 2.243, desactivado para los nuevos: actívelo solo si los usuarios parten del portal del IdP.' },
          { label: 'Formato de NameID', text: 'No especificado (predeterminado del IdP), Persistente, Dirección de correo o Transitorio: se envía en cada solicitud de inicio de sesión y se publica en los metadatos del SP. Persistente da un identificador estable; un NameID transitorio nunca se usa para reconocer la cuenta.' },
          { label: 'Single Logout', text: 'Un LogoutRequest firmado por el IdP y enviado a la URL SLO de los metadatos del SP (HTTP-Redirect) cierra la sesión UCM de ese NameID en este navegador, salvo que su SessionIndex nombre otra sesión. Un LogoutResponse vuelve a la URL SLO del IdP, firmado con la clave del SP (sin firmar cuando el certificado SP no es RSA, lo que un IdP estricto rechaza); sin URL SLO del IdP, el navegador vuelve a la página de inicio de sesión. Una solicitud sin firmar, falsificada, caducada o repetida, o sin Destination, se rechaza.' },
        ]
      },
      {
        title: 'OAuth2 / OIDC',
        items: [
          { label: 'URL de autorización', text: 'Endpoint de autorización OAuth2' },
          { label: 'URL de token', text: 'Endpoint de token OAuth2' },
          { label: 'Client ID/Secret', text: 'Credenciales de cliente OAuth2 de su IdP' },
          { label: 'Ámbitos (Scopes)', text: 'Ámbitos OAuth2 que solicitar (openid, profile, email)' },
          { label: 'Crear usuarios automáticamente', text: 'Crear automáticamente cuentas UCM en el primer inicio de sesión SSO' },
          { label: 'Grupos para el mapeo de roles', text: 'Los valores de los claims roles y groups, tomados juntos del token de ID del inicio de sesión y de la respuesta UserInfo. Microsoft Entra ID los envía solo en el token de ID: añada el claim groups en la configuración de tokens de la aplicación (sus valores son ID de objeto de grupo, por lo que las claves del mapeo son esos ID), o use roles de aplicación. Un usuario en más de unos 200 grupos no recibe claim groups de Entra ID: se registra una advertencia y solo pueden coincidir los roles de aplicación. Emita solo los grupos asignados a la aplicación, o roles de aplicación.' },
        ]
      },
      {
        title: 'Aprovisionamiento de roles (#81)',
        items: [
          { label: 'Coincidencia de identidad', text: 'Un inicio de sesión abre la cuenta vinculada al identificador del IdP (sub de OIDC, NameID persistente de SAML, entryUUID u objectGUID de LDAP). Un nombre de usuario o un correo solo coincide con una cuenta asociada a este proveedor y aún no vinculada; una cuenta local, una asociada solo a otros proveedores o una vinculada a otra identidad se rechaza al iniciar sesión. Vincular un proveedor en Usuarios añade un proveedor a cualquier cuenta, cuyos otros proveedores siguen abriéndola: su próximo inicio de sesión por el nuevo vincula el identificador.' },
          { label: 'Rol predeterminado', text: 'Se asigna a las cuentas creadas en el primer inicio de sesión SSO cuando el proveedor no tiene regla de mapeo de roles, y como rol base de una cuenta nueva cuya regla coincidente solo da un rol personalizado (viewer si es Ninguno). Ninguno: nadie inicia sesión sin una regla. Los cambios de rol hechos después en UCM se conservan.' },
          { label: 'Mapeo de roles', text: 'Mapee grupos externos (Azure AD, Okta, LDAP) → roles de UCM (admin / operator / auditor / viewer) o roles personalizados. Con al menos una regla, un usuario que ninguna regla cubre se rechaza en cada inicio de sesión SSO (OIDC, SAML, LDAP), sea cuenta nueva o existente; un inicio de sesión con passkey o certificado no se comprueba. Se usa al crear el usuario y en cada inicio de sesión cuando la sincronización de roles está activada. Cuando coinciden varios grupos, gana el rol de mayor privilegio (admin > operator > auditor > viewer): el orden de las entradas no importa (#221). Cada grupo también puede nombrar un rol personalizado (elegido entre los roles personalizados existentes): se añade al rol base, o se usa solo. Si varios grupos coincidentes dan un rol personalizado, gana el primero de la lista. Con la sincronización de roles activada, un rol personalizado establecido por SSO se quita cuando ningún grupo lo da; un rol personalizado asignado a mano en UCM nunca se toca. Los roles del sistema no pueden usarse como rol personalizado.' },
          { label: 'Sincronizar el rol desde SSO en cada inicio de sesión', text: 'DESACTIVADO (predeterminado): SSO nunca sobrescribe los roles gestionados en UCM. ACTIVADO: el rol se vuelve a sincronizar desde role_mapping en cada inicio de sesión; una regla coincidente que no da rol base conserva el almacenado (default_role nunca se vuelve a aplicar). Una cuenta con varios proveedores sigue las reglas del proveedor por el que inició sesión por última vez.' },
          { label: 'Exigir 2FA', text: 'Los usuarios de este proveedor deben registrar un segundo factor. Los inicios de sesión LDAP piden un código TOTP registrado o una llave de seguridad, como los inicios de sesión locales, con o sin esta opción; los inicios de sesión OIDC y SAML solo exigen el registro y confían en el proveedor de identidad para la MFA.' },
          { label: 'Actualizar info de usuario en cada inicio', text: 'Actualiza el correo y el nombre completo en cada inicio de sesión. NO toca el rol.' },
        ]
      },
      {
        title: 'LDAP',
        items: [
          { label: 'Servidor', text: 'Nombre de host y puerto del servidor LDAP (389, o 636 para LDAPS)' },
          { label: 'StartTLS', text: 'En un puerto LDAP sin cifrar, actualiza la conexión a TLS antes de cualquier bind, con la misma verificación de certificado que LDAPS. Activado de forma predeterminada para un proveedor nuevo sin SSL/TLS. Sin SSL/TLS ni StartTLS, el bind y las contraseñas de los usuarios circulan por la red en claro.' },
          { label: 'Bind DN', text: 'Distinguished Name para la autenticación bind de LDAP' },
          { label: 'Base DN', text: 'Base de búsqueda para consultas de usuario' },
          { label: 'Filtro de usuario', text: 'Filtro LDAP para encontrar usuarios (p. ej., (uid={username}))' },
          { label: 'Mapeo de atributos', text: 'Mapee atributos LDAP a nombre de usuario, correo electrónico y nombre completo' },
          { label: 'Atributo de ID estable', text: 'Id inmutable que reconoce la cuenta (entryUUID, objectGUID). Una cuenta vinculada por su DN pasa a este id en su siguiente inicio de sesión; cambiarlo de un atributo de id a otro rechaza a todos los usuarios vinculados hasta que se restablezca su identidad (Restablecer identidad) en cada cuenta.' },
          { label: 'Grupos', text: 'Con memberOf, se leen de la propia entrada del usuario; con member o uniqueMember, se buscan bajo la Base de búsqueda de grupos cuando está definida; si no, bajo el padre del Base DN cuando el directorio lo contiene, luego bajo el Base DN si esa búsqueda falla, y en otro caso bajo el Base DN; el filtro de grupo es por defecto (objectClass=*). Solo pertenencia directa, salvo que la opción Grupos anidados y grupo primario esté activada: en Active Directory añade todos los grupos por encima de los del usuario, a cualquier profundidad, buscados bajo las mismas bases que una búsqueda de miembros (también con memberOf), y el grupo primario (normalmente RID 513, Domain Users en un dominio en inglés), cuyo propio nombre cuenta solo bajo esa base y a través del filtro de grupo; cuando existen reglas o grupos requeridos, en otro directorio, o cuando esa búsqueda falla o supera los 1000 grupos, el inicio de sesión se rechaza. Los nombres se comparan con las reglas y los grupos requeridos sin distinguir mayúsculas, espacios en los extremos ni la longitud de las series de espacios interiores. Cuando existen reglas o grupos requeridos y los grupos no pueden leerse, el inicio de sesión se rechaza indicándolo. Probar mapeo lee los grupos y decide como lo hace el inicio de sesión.' },
        ]
      },
    ],
    tips: [
      'Pruebe SSO primero con una cuenta que no sea de administrador para evitar bloqueos',
      'Mantenga disponible el inicio de sesión de administrador local como respaldo',
      'Mapee el atributo de correo del IdP para garantizar una identificación única del usuario',
      'Use la URL de metadatos SP para configurar automáticamente su IdP (SAML)',
      'El certificado HTTPS de UCM debe ser de confianza para el IdP para que los metadatos SAML se acepten',
    ],
    warnings: [
      'Una configuración incorrecta de SSO puede bloquear a todos los usuarios: mantenga siempre un administrador local',
    ],
  },
  helpGuides: {
    title: 'Single Sign-On',
    content: `
## Descripción general

SSO permite a los usuarios autenticarse con el proveedor de identidad (IdP) de su organización, sin necesidad de credenciales UCM separadas. UCM admite **SAML 2.0**, **OAuth2/OIDC** y **LDAP**.

## SAML 2.0

### URL de metadatos SP

UCM ofrece una **URL de metadatos del proveedor de servicios (SP)** que puede dar a su IdP para la configuración automática:

\`\`\`
https://your-ucm-host:8443/api/v2/sso/saml/metadata
\`\`\`

Esta URL devuelve un documento XML conforme a SAML 2.0 que contiene:
- **ID de entidad**: el identificador del proveedor de servicios de UCM
- **URL ACS**: endpoint del Assertion Consumer Service (HTTP-POST)
- **URL SLO**: endpoint del IdP que recibe el LogoutResponse por HTTP-Redirect; la importación de metadatos conserva el ResponseLocation del Single Logout Service HTTP-Redirect y, si no lo hay, su Location. Véase Single Logout más abajo
- **Certificado de firma**: el certificado HTTPS de UCM para la verificación de firmas
- **Formato de NameID**: el ajuste **Formato de NameID** del proveedor (No especificado, Persistente, Dirección de correo o Transitorio), enviado también en cada solicitud de inicio de sesión. Persistente da un identificador estable; un NameID transitorio nunca se usa para reconocer la cuenta

Copie esta URL en la configuración «Añadir proveedor de servicios» o «Aplicación SAML» de su IdP.

> ⚠️ **Importante:** el certificado HTTPS de UCM debe ser **de confianza para el IdP**. Si el IdP no puede validar el certificado (por ejemplo, autofirmado o emitido por una CA privada), rechazará los metadatos por no válidos. Importe el certificado de la CA de UCM en el almacén de confianza del IdP, o use un certificado firmado por una CA de confianza pública.

### Configuración
1. Obtenga la URL de metadatos del IdP o el archivo XML de su proveedor de identidad
2. En UCM, vaya a **Configuración → SSO**
3. En la tarjeta **SAML 2.0**, haga clic en **Configurar**
4. Introduzca la **URL de metadatos del IdP**: UCM rellena automáticamente el ID de entidad, las URL SSO/SLO y el certificado
5. O pegue directamente el XML de metadatos del IdP
6. Configure el **mapeo de atributos** (username, email, groups)
7. Haga clic en **Guardar** y **Habilitar**

### Mapeo de atributos
Mapee los atributos SAML del IdP a los campos de usuario de UCM:
- \`username\` → nombre de usuario de UCM (obligatorio)
- \`email\` → correo de UCM (obligatorio)
- \`groups\` → leído por las reglas de mapeo de roles (opcional); no hace al usuario miembro de grupos de UCM

Los grupos se leen de los atributos mapeados a \`groups\`; si no, de \`groups\` y de las URI de claims de Microsoft. Keycloak envía los roles en \`Role\` y los grupos en \`member\`, Shibboleth envía \`urn:oid:1.3.6.1.4.1.5923.1.5.1.1\` (isMemberOf), otros IdP \`memberOf\`: solo se leen una vez mapeados a \`groups\`. Los botones bajo el mapeo de atributos añaden una fila así, que surte efecto al guardarla. Un atributo se identifica por su Name, nunca por su FriendlyName (SAML Core 2.0 §2.7.3.1): mapee \`urn:oid:1.3.6.1.4.1.5923.1.5.1.1\`, no \`isMemberOf\`. Una fila de la forma nueva (\`atributo → groups\`) sustituye a una fila de la forma antigua (\`groups → atributo\`), que deja de leerse; la pantalla nombra, bajo el mapeo, los atributos que ninguna fila lee ya. Para seguir leyendo ambos, sustituya la fila antigua por una fila \`atributo → groups\`.

### Single Logout
Cuando el IdP cierra una sesión, envía un **LogoutRequest** firmado a través del navegador a la URL SLO. UCM comprueba la firma del IdP, el emisor, el Destination (obligatorio), el IssueInstant (dentro de la ventana de reloj) y que la solicitud no se haya usado antes, cierra la sesión UCM de ese NameID en este navegador (cuando la solicitud lleva valores SessionIndex, solo una sesión que ellos nombren) y envía después un **LogoutResponse** a la URL SLO del IdP, firmado con la clave del SP; un certificado SP que no es RSA lo envía sin firmar, lo que un IdP estricto como AD FS rechaza. Sin URL SLO del IdP, el navegador vuelve a la página de inicio de sesión de UCM. Un LogoutRequest sin firmar o falsificado se rechaza y la sesión sigue abierta.

### Inicio de sesión iniciado por el IdP
Un inicio de sesión lanzado desde el portal del IdP llega a UCM sin una solicitud de UCM. **Permitir el inicio de sesión iniciado por el IdP** lo acepta, con las mismas comprobaciones de firma, audiencia, Destination, validez y repetición. Los proveedores creados antes de la 2.243 lo mantienen activado; los nuevos lo tienen desactivado. Actívelo solo si los usuarios parten del portal del IdP.

## OAuth2 / OIDC

### Configuración
1. Registre UCM como cliente en su proveedor OAuth2/OIDC
2. Establezca el **URI de redirección** en: \`https://your-ucm-host:8443/api/v2/sso/callback/oauth2\`
3. Copie el **Client ID** y el **Client Secret**
4. En UCM, vaya a **Configuración → SSO**
5. En la tarjeta **OAuth2 / OIDC**, haga clic en **Configurar**
6. Introduzca la **URL de autorización** y la **URL de token**
7. Introduzca la **URL de userinfo** (para obtener los atributos del usuario tras el inicio de sesión)
8. Introduzca el Client ID y el Secret
9. Configure los ámbitos (openid, profile, email)
10. Haga clic en **Guardar** y **Habilitar**

### Preajustes
- **Microsoft Entra** (un solo inquilino) rellena las URL y el emisor \`https://login.microsoftonline.com/{tenant}/v2.0\`: sustituya \`{tenant}\` por el ID del directorio (tenant) en las tres. Un proveedor guardado con \`{tenant}\` sin sustituir se rechaza. Para una aplicación multiinquilino, establezca el emisor en \`https://login.microsoftonline.com/organizations/v2.0\` (o \`common\`), las URL con la misma autoridad, y liste los ID de inquilino (GUID) en **Inquilinos aceptados**: un token solo se acepta cuando su \`tid\` figura en la lista, su emisor es la plantilla de descubrimiento \`https://login.microsoftonline.com/{tenantid}/v2.0\` con ese \`tid\`, y su clave de firma, cuando nombra un emisor, nombra ese. No hay comodín: el inquilino de cuentas personales de Microsoft solo se acepta si figura en la lista, y la verificación del token de ID debe seguir activada. Una identidad pertenece a su inquilino: el mismo \`sub\` en dos inquilinos son dos cuentas, y un inquilino retirado de la lista ya no inicia sesión. Una cuenta vinculada antes de que el proveedor aceptara varios inquilinos conserva su \`sub\` sin más: restablezca su identidad SSO y elija su inquilino para que su próximo inicio de sesión vincule el del inquilino. Aceptar un inquilino es confiar en sus administradores, que eligen los nombres de usuario y los correos de sus usuarios: una cuenta asociada aún no vinculada solo se vincula por su nombre de usuario o correo mediante un inicio de sesión desde el **Inquilino esperado** elegido al vincular el proveedor o al restablecer la identidad (por defecto, el inquilino de la identidad anterior), y una asociación sin él no la vincula ningún inicio de sesión. El mapeo de roles lee los roles y grupos solo de los inquilinos listados en **Inquilinos cuyos roles se respetan**, lo que confía a sus administradores los roles de UCM. Cuando el mapeo de roles tiene reglas, un usuario de otro inquilino aceptado no coincide con ninguna y se rechaza al iniciar sesión, incluida una cuenta existente; sin reglas, todo inquilino aceptado recibe el rol predeterminado, de modo que un rol predeterminado de administrador convierte en administrador toda cuenta nueva de todo inquilino aceptado.
- **Google** rellena el emisor \`https://accounts.google.com\`.
- **GitHub** no es un proveedor OpenID Connect y no emite token de ID: el preajuste desactiva **Verificar la firma del ID token** y mapea \`login\` al nombre de usuario. La cuenta se reconoce por su \`id\` numérico de GitHub (UCM lee el \`sub\` de UserInfo y, si no, \`id\`), nunca por el login ni el correo.
- Cambiar de preajuste restablece el emisor y el ajuste de verificación que fijó el anterior, salvo que se hayan cambiado después.

### Firma del token de ID
Se aceptan RS256, RS384, RS512, PS256, PS384, PS512, ES256, ES384, ES512 y EdDSA (Ed25519, Ed448), nunca \`none\` ni HS256, HS384 o HS512. La clave de firma debe ser del tipo y la curva que nombra el algoritmo, su \`alg\` y \`use\`, cuando existen, el algoritmo del token y \`sig\`, y una clave RSA de 2048 bits o más. Sin URI JWKS, el algoritmo debe figurar también en el documento de descubrimiento. En modo FIPS, EdDSA solo se acepta cuando el módulo FIPS lo aprueba, y una clave RSA debe tener un tamaño par de 2048 a 16384 bits. Un algoritmo rechazado se nombra en la entrada de auditoría.

### Crear usuarios automáticamente
Cuando está activado, se crea automáticamente una cuenta de usuario de UCM en el primer inicio de sesión SSO, con los atributos que da el IdP, con el rol que da su regla de mapeo y, si no, el rol predeterminado.

### Grupos para el mapeo de roles
Las reglas de mapeo de roles comparan sus claves con los valores de los claims **roles** y **groups**, leídos juntos del token de ID del inicio de sesión y de la respuesta UserInfo. Microsoft Entra ID envía grupos y roles de aplicación solo en el token de ID: en el registro de la aplicación, añada el claim groups en **Configuración de tokens** (los valores son ID de objeto de grupo, por lo que las claves del mapeo son esos ID), o defina roles de aplicación y mapee sus valores. Un usuario en más de unos 200 grupos no recibe claim groups de Entra ID: UCM registra una advertencia y solo pueden coincidir los roles de aplicación. Emita solo los grupos asignados a la aplicación, o roles de aplicación. Con **Verificar la firma del ID token** desactivado, los grupos del token de ID solo cuentan cuando la URL de token es HTTPS con la verificación TLS activada, y el emisor y el client ID están definidos y coinciden con el token.

Una fila \`claim → groups\` en el mapeo de atributos hace de ese claim la fuente de los grupos, en el token de ID y en UserInfo bajo las mismas condiciones, en lugar de **roles** y **groups**. El nombre se busca tal cual en primer lugar (\`https://example.com/groups\`) y después como ruta con puntos a través de objetos anidados: para Keycloak, \`realm_access.roles\` para los roles de realm y \`resource_access.<client id>.roles\` para los roles de cliente. Un valor que no es ni una cadena ni una lista de cadenas no da ningún grupo. Una fila de la forma nueva (\`atributo → groups\`) sustituye a una fila de la forma antigua (\`groups → atributo\`), que deja de leerse; la pantalla nombra, bajo el mapeo, los atributos que ninguna fila lee ya. Para seguir leyendo ambos, sustituya la fila antigua por una fila \`atributo → groups\`.

## Quién puede iniciar sesión

### Coincidencia de identidad
Un inicio de sesión abre la cuenta vinculada al identificador del IdP: \`sub\` de OIDC, NameID persistente de SAML, \`entryUUID\` u \`objectGUID\` de LDAP. Un nombre de usuario o un correo solo coincide con una cuenta del mismo proveedor que aún no esté vinculada (creada antes de los identificadores estables, o enlazada por un administrador); un correo que el IdP OIDC marca como no verificado (\`email_verified\` falso) no coincide con ninguna. Un inicio de sesión SSO nunca abre una cuenta local, ni una vinculada a otra identidad: el inicio de sesión se rechaza y queda registrado en el registro de auditoría. Cuando ninguna cuenta coincide, se rechaza, en lugar de dar una segunda cuenta, un inicio de sesión cuyo correo pertenece a una cuenta asociada solo a otros proveedores o dejada por otro IdP o por uno desconocido (tras una restauración, por ejemplo), o, mientras el correo no esté verificado, a una asociada a este proveedor y aún no vinculada. Una cuenta puede estar asociada a varios proveedores, cada uno con su propia identidad, y ningún inicio de sesión asocia un proveedor a una cuenta existente por su nombre o correo: lo hace un administrador con **Vincular un proveedor** en ese usuario. Admite una cuenta local y una de otros proveedores, que siguen abriéndola; **Restablecer identidad** borra la identidad de una asociación que el IdP cambió. El siguiente inicio de sesión por ese proveedor vincula el identificador del IdP, y a una cuenta sin contraseña local no se le pide una.

Cuando se elimina un proveedor, sus asociaciones se conservan como huérfanas y los otros proveedores de cada cuenta siguen abriéndola: un proveedor creado de nuevo para el mismo IdP (mismo emisor, ID de entidad, o servidor LDAP y base DN) las recupera en su siguiente inicio de sesión. En otro caso, y para las asociaciones que una restauración no pudo colocar, use **Vincular un proveedor** en cada cuenta.

### Reglas de mapeo de roles
- **Al menos una regla**: un usuario que ninguna regla cubre se rechaza en cada inicio de sesión SSO (OIDC, SAML, LDAP), sea la cuenta nueva o ya existente; un inicio de sesión con passkey o certificado no se comprueba
- **Ninguna regla**: todo usuario que el proveedor autentica puede iniciar sesión; las cuentas nuevas reciben el **Rol predeterminado**
- Una regla que da solo un rol personalizado: una cuenta nueva recibe el **Rol predeterminado** como rol base (viewer si es Ninguno)
- **Rol predeterminado: Ninguno** sin ninguna regla: nadie puede iniciar sesión con el proveedor

La sección **Aprovisionamiento de usuarios** se abre sola y muestra una advertencia cuando el proveedor no tiene ninguna regla.

### Diagnosticar un inicio de sesión rechazado
Un inicio de sesión rechazado porque ninguna regla coincide, o porque el proveedor no tiene regla ni rol predeterminado, se registra en **Registros de auditoría** como un inicio de sesión fallido (filtro rápido **Inicios fallidos**). La entrada da los valores de grupo que UCM leyó (20 como máximo, cada uno cortado a 64 caracteres) y dónde se leyeron: el token de ID, UserInfo o ambos para OIDC, con el motivo por el que no se usó el token de ID; los atributos leídos para SAML; la base de búsqueda de grupos o \`memberOf\` para LDAP. Cuando no se leyó nada por OIDC o SAML, nombra los claims o atributos recibidos que parecen listas de grupos, nunca sus valores: mapee uno de ellos a \`groups\`. Después, añada una regla de mapeo de roles para uno de los valores, o establezca un rol predeterminado. El usuario rechazado solo ve el mensaje de rechazo (ninguna regla coincide, o ni rol predeterminado ni regla de mapeo de roles), nunca los valores de grupo.

### Probar un inicio de sesión
**Probar inicio de sesión**, junto a **Probar conexión** en un proveedor OIDC o SAML guardado, habilitado o no, abre el IdP en una ventana nueva: inicie sesión allí con la identidad que quiera probar. El IdP vuelve al mismo URI de redirección o URL ACS que un inicio de sesión, y UCM aplica las mismas comprobaciones y la misma decisión sobre la cuenta. La pantalla del proveedor muestra entonces la identidad y los grupos leídos, el veredicto, el rol, la cuenta que se abriría o se crearía y, si es un rechazo, su motivo con los atributos que mapear a \`groups\`. Nadie inicia sesión y ninguna cuenta cambia; la ventana solo indica que la prueba terminó. La prueba usa el proveedor guardado (los cambios sin guardar se avisan, no se envían); solo el administrador que la inició lee el resultado, durante 10 minutos. El registro de auditoría la anota como \`sso_sign_in_test\`, aparte de los inicios de sesión.

## LDAP

### Configuración
1. En UCM, vaya a **Configuración → SSO**
2. En la tarjeta **LDAP / Active Directory**, haga clic en **Configurar**
3. Introduzca el nombre de host del **Servidor LDAP** y el **Puerto** (389 para LDAP, 636 para LDAPS)
4. Active **Usar SSL/TLS** (LDAPS, puerto 636) o, en el puerto 389, **Usar StartTLS**: la conexión pasa a TLS antes de cualquier bind, con la misma verificación de certificado. Sin ninguna de las dos, el bind y las contraseñas de los usuarios circulan por la red en claro
5. Introduzca el **Bind DN** y la **Contraseña Bind** (credenciales de la cuenta de servicio)
6. Introduzca el **Base DN** (base de búsqueda para consultas de usuario)
7. Configure el **Filtro de usuario** (p. ej., \`(uid={username})\` o \`(sAMAccountName={username})\` para AD)
8. Mapee los atributos LDAP: **username**, **email**, **nombre completo** y el **atributo de ID estable** (\`entryUUID\`, \`objectGUID\`). Una cuenta vinculada por su DN pasa a este id en su siguiente inicio de sesión; cambiarlo de un atributo de id a otro rechaza a todos los usuarios vinculados hasta usar **Restablecer identidad** en cada cuenta
9. Haga clic en **Probar conexión** para verificar y después en **Guardar** y **Habilitar**

### Grupos
- **memberOf**: se lee de la propia entrada del usuario (una búsqueda base sobre su DN); no se usa el filtro de grupo
- **member / uniqueMember**: se buscan solo bajo la Base de búsqueda de grupos cuando está definida; si no, bajo el padre del Base DN cuando el directorio lo contiene, luego bajo el Base DN si esa búsqueda falla, con el filtro de grupo (\`(objectClass=*)\` cuando está vacío); se encuentran los grupos junto a los usuarios (\`ou=groups\` junto a \`ou=people\`)
- **Solo pertenencia directa** de forma predeterminada: no se ven los grupos anidados ni el grupo primario de Active Directory (normalmente RID 513, Domain Users en un dominio en inglés)
- **Grupos anidados y grupo primario** (solo Active Directory, desactivado de forma predeterminada): añade todos los grupos por encima de los del usuario a cualquier profundidad (regla de coincidencia 1.2.840.113556.1.4.1941) y el grupo primario, leído por su SID dondequiera que esté, de modo que los grupos padre dan sus roles. Los grupos padre se buscan bajo las mismas bases que una búsqueda de miembros (también con memberOf); el propio nombre del grupo primario cuenta solo bajo esa base y a través del filtro de grupo. También se siguen los grupos de distribución: el filtro de grupo (&(objectClass=group)(groupType:1.2.840.113556.1.4.803:=2147483648)) conserva solo los grupos de seguridad que encuentra esta búsqueda. Con reglas o grupos requeridos, en otro directorio, o cuando la búsqueda falla, agota el tiempo o supera los 1000 grupos, el inicio de sesión se rechaza, nunca se limita a los grupos directos
- **Comparación**: los nombres de grupo se comparan con las reglas y los grupos requeridos sin distinguir mayúsculas ni espacios en los extremos, y una serie de espacios interiores cuenta como uno
- **Grupos ilegibles**: con reglas o grupos requeridos, un inicio de sesión cuyos grupos no pueden leerse se rechaza con «your groups could not be read from the directory»
- **Probar mapeo** lee los grupos y decide como lo hace el inicio de sesión, sin la contraseña; muestra un rol solo para un usuario admitido

### Active Directory
Para Microsoft Active Directory, use:
- Puerto: **389** (o 636 con SSL)
- Filtro de usuario: \`(sAMAccountName={username})\`
- Atributo de nombre de usuario: \`sAMAccountName\`
- Atributo de correo: \`mail\`
- Atributo de nombre completo: \`displayName\`

## Flujo de inicio de sesión
1. El usuario hace clic en el botón de su proveedor en la página de inicio de sesión de UCM (o introduce credenciales LDAP)
2. Para SAML/OAuth2: el usuario es redirigido al IdP, se autentica y es redirigido de vuelta
3. Para LDAP: las credenciales se verifican directamente contra el servidor LDAP
4. UCM crea o actualiza la cuenta de usuario
5. El usuario inicia sesión

> ⚠ Mantenga siempre al menos una cuenta de administrador local como respaldo, por si una configuración errónea de SSO bloquea a todos.

> 💡 Pruebe SSO primero con una cuenta que no sea de administrador antes de convertirlo en el método de autenticación principal.

> 💡 Use el botón **Probar conexión** para verificar su configuración antes de habilitar un proveedor.
`
  }
}
