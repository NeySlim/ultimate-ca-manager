export default {
  helpContent: {
    title: 'Single Sign-On',
    subtitle: 'Integración con SAML, OAuth2 y LDAP',
    overview: 'Configure Single Sign-On para permitir a los usuarios autenticarse a través del proveedor de identidad de su organización. Compatible con los protocolos SAML 2.0, OAuth2/OIDC y LDAP.',
    sections: [
      {
        title: 'SAML 2.0',
        items: [
          { label: 'Identity Provider', text: 'Configure la URL de metadatos del IDP o cargue el XML' },
          { label: 'URL de metadatos SP', text: 'Proporcione esta URL a su IDP para configurar automáticamente UCM como proveedor de servicios' },
          { label: 'Certificado SP', text: 'El certificado HTTPS de UCM incluido en los metadatos, debe ser confiable para el IDP o los metadatos serán rechazados' },
          { label: 'Entity ID', text: 'Identificador de entidad del proveedor de servicios UCM' },
          { label: 'URL ACS', text: 'URL de devolución del Assertion Consumer Service' },
          { label: 'Mapeo de atributos', text: 'Columna izquierda: el nombre del atributo enviado por el IdP. Columna derecha: el campo de UCM que rellena (username, email, fullname o groups). Ejemplo: user.userprincipalname → username.' },
          { label: 'Grupos para el mapeo de roles', text: 'Se leen de los atributos mapeados a groups; si no, de groups y de los claims de grupos y roles de Microsoft Entra ID / AD FS. Cuando Entra ID envía groups.link en lugar de los grupos (usuarios en más de 150 grupos), se registra una advertencia y se aplica el rol predeterminado: emita solo los grupos asignados a la aplicación, o roles de aplicación.' },
          { label: 'Inicio de sesión iniciado por el IdP', text: 'Acepta inicios de sesión lanzados desde el portal del IdP, verificados como cualquier otra respuesta. Activado para los proveedores creados antes de la 2.243, desactivado para los nuevos: actívelo solo si los usuarios parten del portal del IdP.' },
          { label: 'Formato de NameID', text: 'No especificado (predeterminado del IdP), Persistente, Dirección de correo o Transitorio: se envía en cada solicitud de inicio de sesión y se publica en los metadatos del SP. Persistente da un identificador estable; un NameID transitorio nunca se usa para reconocer la cuenta.' },
          { label: 'Cierre de sesión único', text: 'Un LogoutRequest firmado por el IdP y enviado a la URL SLO de los metadatos SP (HTTP-Redirect) cierra la sesión UCM de ese NameID en este navegador, salvo que su SessionIndex nombre otra sesión. Un LogoutResponse vuelve a la URL SLO del IdP, firmado con la clave SP (sin firmar cuando el certificado SP no es RSA, lo que un IdP estricto rechaza); sin URL SLO del IdP, el navegador vuelve a la página de inicio de sesión. Una solicitud sin firmar, falsificada, obsoleta o repetida, o sin Destination, se rechaza.' },
        ]
      },
      {
        title: 'OAuth2 / OIDC',
        items: [
          { label: 'URL de autorización', text: 'Endpoint de autorización OAuth2' },
          { label: 'URL de token', text: 'Endpoint de token OAuth2' },
          { label: 'Client ID/Secret', text: 'Credenciales del cliente OAuth2 de su IDP' },
          { label: 'Scopes', text: 'Scopes OAuth2 a solicitar (openid, profile, email)' },
          { label: 'Crear usuarios automáticamente', text: 'Crear automáticamente cuentas UCM en el primer inicio de sesión SSO' },
        ]
      },
      {
        title: 'Aprovisionamiento de roles (#81)',
        items: [
          { label: 'Coincidencia de identidad', text: 'Un inicio de sesión abre la cuenta vinculada al identificador del IdP (sub de OIDC, NameID persistente de SAML, entryUUID u objectGUID de LDAP). Un nombre de usuario o correo solo coincide con una cuenta del mismo proveedor que aún no esté vinculada; una cuenta local, o una vinculada a otra identidad, se rechaza al iniciar sesión. Para fusionar una cuenta local, use primero Vincular a SSO en Usuarios: su siguiente inicio de sesión mediante ese proveedor vincula el identificador.' },
          { label: 'Rol predeterminado', text: 'Se asigna a las cuentas creadas en el primer inicio de sesión SSO cuando el proveedor no tiene regla de mapeo de roles, y como rol base de una cuenta nueva cuya regla solo da un rol personalizado (viewer si es Ninguno). Ninguno: nadie inicia sesión sin una regla. Los cambios de rol hechos después en UCM se conservan.' },
          { label: 'Mapeo de roles', text: 'Mapee grupos externos (Azure AD, Okta, LDAP) → roles UCM (admin / operator / auditor / viewer) o roles personalizados. Con al menos una regla, un usuario que ninguna regla cubre se rechaza en cada inicio de sesión SSO (OIDC, SAML, LDAP), cuenta nueva o existente; un inicio de sesión con passkey o certificado no se comprueba. Se usa al crear el usuario, y en cada inicio de sesión cuando la sincronización de roles está activada. Cuando varios grupos coinciden, gana el rol de mayor privilegio (admin > operator > auditor > viewer): el orden de las entradas no importa (#221). Cada grupo también puede nombrar un rol personalizado (elegido entre los roles personalizados existentes): se suma al rol base, o se usa solo. Si varios grupos coincidentes dan un rol personalizado, gana el primero de la lista. Con la sincronización de roles activada, un rol personalizado fijado por SSO se elimina cuando ningún grupo da uno; un rol personalizado asignado a mano en UCM nunca se toca. Los roles del sistema no pueden usarse como rol personalizado.' },
          { label: 'Sincronizar rol en cada inicio de sesión', text: 'DESACTIVADO (predeterminado): SSO nunca sobrescribe los roles gestionados en UCM. ACTIVADO: el rol se vuelve a sincronizar desde role_mapping en cada inicio de sesión; una regla coincidente que no da rol base conserva el almacenado (default_role nunca se vuelve a aplicar).' },
          { label: 'Exigir 2FA', text: 'Los usuarios de este proveedor deben registrar un segundo factor. Los inicios de sesión LDAP piden un código TOTP registrado o una llave de seguridad, como los inicios de sesión locales, con o sin esta opción; los inicios de sesión OIDC y SAML solo exigen el registro y confían en el proveedor de identidad para la MFA.' },
          { label: 'Actualizar usuarios automáticamente', text: 'Actualiza el correo y el nombre completo en cada inicio de sesión. NO toca el rol.' },
        ]
      },
      {
        title: 'LDAP',
        items: [
          { label: 'Servidor', text: 'Nombre de host y puerto del servidor LDAP (389 o 636 para SSL)' },
          { label: 'StartTLS', text: 'En un puerto LDAP sin cifrar, actualiza la conexión a TLS antes de cualquier bind, con la misma verificación de certificado que LDAPS. Activado por defecto para un proveedor nuevo sin SSL/TLS. Sin SSL/TLS ni StartTLS, el bind y las contraseñas de los usuarios circulan por la red en claro.' },
          { label: 'Bind DN', text: 'Distinguished Name para la autenticación de enlace LDAP' },
          { label: 'Base DN', text: 'Base de búsqueda para consultas de usuario' },
          { label: 'Filtro de usuario', text: 'Filtro LDAP para encontrar usuarios (ej., (uid={username}))' },
          { label: 'Mapeo de atributos', text: 'Mapee atributos LDAP a nombre de usuario, correo electrónico, nombre completo' },
          { label: 'Atributo de ID único', text: 'Id inmutable que reconoce la cuenta (entryUUID, objectGUID). Una cuenta vinculada por su DN pasa a este id en su siguiente inicio de sesión; cambiarlo de un atributo de id a otro rechaza a todos los usuarios vinculados hasta Desvincular y luego Vincular a SSO.' },
        ]
      },
    ],
    tips: [
      'Pruebe SSO con una cuenta que no sea de administrador primero para evitar bloqueos',
      'Mantenga el inicio de sesión de administrador local disponible como respaldo',
      'Mapee el atributo de correo del IDP para garantizar una identificación única del usuario',
      'Use la URL de metadatos SP para configurar automáticamente su IDP (SAML)',
      'El certificado HTTPS de UCM debe ser confiable para el IDP para que los metadatos SAML sean aceptados',
    ],
    warnings: [
      'Una configuración incorrecta de SSO puede bloquear a todos los usuarios: mantenga siempre un administrador local',
    ],
  },
  helpGuides: {
    title: 'Single Sign-On',
    content: `
## Descripción general

SSO permite a los usuarios autenticarse usando el proveedor de identidad (IDP) de su organización, eliminando la necesidad de credenciales UCM separadas. UCM soporta **SAML 2.0**, **OAuth2/OIDC** y **LDAP**.

## SAML 2.0

### URL de metadatos SP

UCM proporciona una **URL de metadatos del proveedor de servicios (SP)** que puede dar a su IDP para configuración automática:

\`\`\`
https://su-host-ucm:8443/api/v2/sso/saml/metadata
\`\`\`

Este URL devuelve un documento XML compatible con SAML 2.0 que contiene:
- **Entity ID**: Identificador del proveedor de servicios de UCM
- **URL ACS**: Endpoint del Assertion Consumer Service (HTTP-POST)
- **URL SLO**: Endpoint del servicio de cierre de sesión único
- **Certificado de firma**: Certificado HTTPS de UCM para verificación de firma
- **Formato NameID**: El ajuste **Formato de NameID** del proveedor (No especificado, Persistente, Dirección de correo o Transitorio), enviado también en cada solicitud de inicio de sesión. Persistente da un identificador estable; un NameID transitorio nunca se usa para reconocer la cuenta

Copie esta URL en la configuración "Agregar proveedor de servicios" o "Aplicación SAML" de su IDP.

> ⚠️ **Importante:** El certificado HTTPS de UCM debe ser **confiable para el IDP**. Si el IDP no puede validar el certificado (ej., autofirmado o emitido por una CA privada), rechazará los metadatos como inválidos. Importe el certificado de la CA de UCM en el almacén de confianza del IDP, o use un certificado firmado por una CA de confianza pública.

### Configuración
1. Obtenga la URL de metadatos del IDP o el archivo XML de su proveedor de identidad
2. En UCM, vaya a **Configuración → SSO**
3. Haga clic en **Agregar proveedor** → SAML
4. Ingrese la **URL de metadatos del IDP**: UCM completa automáticamente Entity ID, URLs SSO/SLO y certificado
5. O pegue el XML de metadatos del IDP directamente
6. Configure el **mapeo de atributos** (nombre de usuario, correo, grupos)
7. Haga clic en **Guardar** y **Activar**

### Mapeo de atributos
Mapee los atributos SAML del IDP a los campos de usuario de UCM:
- \`username\` → Nombre de usuario UCM (obligatorio)
- \`email\` → Correo electrónico UCM (obligatorio)
- \`groups\` → leído por las reglas de mapeo de roles (opcional); no hace al usuario miembro de grupos UCM

### Cierre de sesión único
Cuando el IdP termina una sesión, envía un **LogoutRequest** firmado a través del navegador a la URL SLO. UCM comprueba la firma del IdP, el emisor, Destination (obligatorio), IssueInstant (dentro de la ventana de reloj) y que la solicitud no se haya usado antes, cierra la sesión UCM de ese NameID en este navegador (cuando la solicitud lleva valores SessionIndex, solo una sesión que ellos nombren), y luego envía un **LogoutResponse** a la URL SLO del IdP, firmado con la clave SP; un certificado SP que no es RSA lo envía sin firmar, lo que un IdP estricto como AD FS rechaza. Sin URL SLO del IdP, el navegador vuelve a la página de inicio de sesión de UCM. Un LogoutRequest sin firmar o falsificado se rechaza y la sesión sigue abierta.

### Inicio de sesión iniciado por el IdP
Un inicio de sesión lanzado desde el portal del IdP llega sin solicitud de UCM. **Permitir el inicio de sesión iniciado por el IdP** lo acepta, con las mismas comprobaciones de firma, audiencia, Destination, validez y reutilización. Los proveedores creados antes de la 2.243 lo mantienen activado; los nuevos lo tienen desactivado. Actívelo solo si los usuarios parten del portal del IdP.

## OAuth2 / OIDC

### Configuración
1. Registre UCM como cliente en su proveedor OAuth2/OIDC
2. Establezca la **URI de redirección** a: \`https://su-host-ucm:8443/api/v2/sso/callback/oauth2\`
3. Copie el **Client ID** y el **Client Secret**
4. En UCM, vaya a **Configuración → SSO**
5. Haga clic en **Agregar proveedor** → OAuth2
6. Ingrese la **URL de autorización** y la **URL de token**
7. Ingrese la **URL de información del usuario** (para obtener atributos del usuario después del inicio de sesión)
8. Ingrese Client ID y Secret
9. Configure los scopes (openid, profile, email)
10. Haga clic en **Guardar** y **Activar**

### Crear usuarios automáticamente
Cuando está activado, se crea automáticamente una nueva cuenta de usuario UCM en el primer inicio de sesión SSO, usando los atributos proporcionados por el IDP, con el rol que da su regla de mapeo, o si no el rol predeterminado.

## Quién puede iniciar sesión

### Coincidencia de identidad
Un inicio de sesión abre la cuenta vinculada al identificador del IdP: \`sub\` de OIDC, NameID persistente de SAML, \`entryUUID\` u \`objectGUID\` de LDAP. Un nombre de usuario o correo solo coincide con una cuenta del mismo proveedor que aún no esté vinculada (creada antes de los identificadores estables, o vinculada por un administrador); un correo que el IdP OIDC marca como no verificado (\`email_verified\` falso) no coincide con ninguna. Un inicio de sesión SSO nunca abre una cuenta local, ni una vinculada a otra identidad: el inicio de sesión se rechaza y se registra en el registro de auditoría. Para fusionar una cuenta local en una identidad SSO, use primero **Vincular a SSO** en ese usuario; su siguiente inicio de sesión mediante ese proveedor vincula el identificador del IdP.

Cuando se elimina un proveedor, sus usuarios se conservan: un proveedor creado de nuevo para el mismo IdP (mismo emisor, entity ID, o servidor LDAP y base DN) los recupera en su siguiente inicio de sesión. En caso contrario, y para los usuarios que una restauración dejó sin proveedor, use **Desvincular** y luego **Vincular a SSO** en cada cuenta.

### Reglas de mapeo de roles
- **Al menos una regla**: un usuario que ninguna regla cubre se rechaza en cada inicio de sesión SSO (OIDC, SAML, LDAP), sea la cuenta nueva o ya exista; un inicio de sesión con passkey o certificado no se comprueba
- **Ninguna regla**: todo usuario que el proveedor autentica puede iniciar sesión; las cuentas nuevas reciben el **Rol predeterminado**
- Una regla que solo da un rol personalizado: una cuenta nueva recibe el **Rol predeterminado** como rol base (viewer si es Ninguno)
- **Rol predeterminado: Ninguno** sin regla: nadie puede iniciar sesión mediante el proveedor

La sección **Aprovisionamiento de usuarios** se abre sola y muestra una advertencia cuando el proveedor no tiene reglas.

## LDAP

### Configuración
1. En UCM, vaya a **Configuración → SSO**
2. Haga clic en **Agregar proveedor** → LDAP
3. Ingrese el **nombre de host del servidor LDAP** y el **Puerto** (389 para LDAP, 636 para LDAPS)
4. Active **Usar SSL/TLS** (LDAPS, puerto 636) o, en el puerto 389, **Usar StartTLS**: la conexión pasa a TLS antes de cualquier bind, con la misma verificación de certificado. Sin ninguno de los dos, el bind y las contraseñas de los usuarios circulan por la red en claro
5. Ingrese el **Bind DN** y la **contraseña de enlace** (credenciales de cuenta de servicio)
6. Ingrese el **Base DN** (base de búsqueda para consultas de usuario)
7. Configure el **filtro de usuario** (ej., \`(uid={username})\` o \`(sAMAccountName={username})\` para AD)
8. Mapee los atributos LDAP: **nombre de usuario**, **correo electrónico**, **nombre completo** y el **atributo de ID único** (\`entryUUID\`, \`objectGUID\`). Una cuenta vinculada por su DN pasa a este id en su siguiente inicio de sesión; cambiarlo de un atributo de id a otro rechaza a todos los usuarios vinculados hasta **Desvincular** y luego **Vincular a SSO**
9. Haga clic en **Probar conexión** para verificar, luego **Guardar** y **Activar**

### Active Directory
Para Microsoft Active Directory, use:
- Puerto: **389** (o 636 con SSL)
- Filtro de usuario: \`(sAMAccountName={username})\`
- Atributo de nombre de usuario: \`sAMAccountName\`
- Atributo de correo: \`mail\`
- Atributo de nombre completo: \`displayName\`

## Flujo de inicio de sesión
1. El usuario hace clic en **Iniciar sesión con SSO** en la página de inicio de sesión de UCM (o ingresa credenciales LDAP)
2. Para SAML/OAuth2: el usuario es redirigido al IDP, se autentica y luego es redirigido de vuelta
3. Para LDAP: las credenciales se verifican directamente contra el servidor LDAP
4. UCM crea o actualiza la cuenta del usuario
5. El usuario inicia sesión

> ⚠ Siempre mantenga al menos una cuenta de administrador local como respaldo en caso de que una mala configuración de SSO bloquee a todos.

> 💡 Pruebe SSO con una cuenta que no sea de administrador antes de convertirlo en el método de autenticación principal.

> 💡 Use el botón **Probar conexión** para verificar su configuración antes de activar un proveedor.
`
  }
}
