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
          { label: 'Certificado SP', text: 'El certificado HTTPS de UCM incluido en los metadatos — debe ser confiable para el IDP o los metadatos serán rechazados' },
          { label: 'Entity ID', text: 'Identificador de entidad del proveedor de servicios UCM' },
          { label: 'URL ACS', text: 'URL de devolución del Assertion Consumer Service' },
          { label: 'Mapeo de atributos', text: 'Mapee atributos del IDP a campos de usuario de UCM' },
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
        title: 'LDAP',
        items: [
          { label: 'Servidor', text: 'Nombre de host y puerto del servidor LDAP (389 o 636 para SSL)' },
          { label: 'Bind DN', text: 'Distinguished Name para la autenticación de enlace LDAP' },
          { label: 'Base DN', text: 'Base de búsqueda para consultas de usuario' },
          { label: 'Filtro de usuario', text: 'Filtro LDAP para encontrar usuarios (ej., (uid={username}))' },
          { label: 'Mapeo de atributos', text: 'Mapee atributos LDAP a nombre de usuario, correo electrónico, nombre completo' },
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
      'Una configuración incorrecta de SSO puede bloquear a todos los usuarios — mantenga siempre un administrador local',
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
- **Entity ID** — Identificador del proveedor de servicios de UCM
- **URL ACS** — Endpoint del Assertion Consumer Service (HTTP-POST)
- **URL SLO** — Endpoint del servicio de cierre de sesión único
- **Certificado de firma** — Certificado HTTPS de UCM para verificación de firma
- **Formato NameID** — Formato de identificador de nombre solicitado

Copie esta URL en la configuración "Agregar proveedor de servicios" o "Aplicación SAML" de su IDP.

> ⚠️ **Importante:** El certificado HTTPS de UCM debe ser **confiable para el IDP**. Si el IDP no puede validar el certificado (ej., autofirmado o emitido por una CA privada), rechazará los metadatos como inválidos. Importe el certificado de la CA de UCM en el almacén de confianza del IDP, o use un certificado firmado por una CA de confianza pública.

### Configuración
1. Obtenga la URL de metadatos del IDP o el archivo XML de su proveedor de identidad
2. En UCM, vaya a **Configuración → SSO**
3. Haga clic en **Agregar proveedor** → SAML
4. Ingrese la **URL de metadatos del IDP** — UCM completa automáticamente Entity ID, URLs SSO/SLO y certificado
5. O pegue el XML de metadatos del IDP directamente
6. Configure el **mapeo de atributos** (nombre de usuario, correo, grupos)
7. Haga clic en **Guardar** y **Activar**

### Mapeo de atributos
Mapee los atributos SAML del IDP a los campos de usuario de UCM:
- \`username\` → Nombre de usuario UCM (obligatorio)
- \`email\` → Correo electrónico UCM (obligatorio)
- \`groups\` → Membresía de grupo UCM (opcional)

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
Cuando está activado, se crea automáticamente una nueva cuenta de usuario UCM en el primer inicio de sesión SSO, usando los atributos proporcionados por el IDP. Se asigna el rol predeterminado.

## LDAP

### Configuración
1. En UCM, vaya a **Configuración → SSO**
2. Haga clic en **Agregar proveedor** → LDAP
3. Ingrese el **nombre de host del servidor LDAP** y el **Puerto** (389 para LDAP, 636 para LDAPS)
4. Active **Usar SSL** para conexiones cifradas
5. Ingrese el **Bind DN** y la **contraseña de enlace** (credenciales de cuenta de servicio)
6. Ingrese el **Base DN** (base de búsqueda para consultas de usuario)
7. Configure el **filtro de usuario** (ej., \`(uid={username})\` o \`(sAMAccountName={username})\` para AD)
8. Mapee los atributos LDAP: **nombre de usuario**, **correo electrónico**, **nombre completo**
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
