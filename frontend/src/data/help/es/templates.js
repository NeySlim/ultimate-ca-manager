export default {
  helpContent: {
    title: 'Plantillas de certificado',
    subtitle: 'Perfiles de certificado reutilizables',
    overview: 'Defina perfiles de certificado reutilizables con campos de sujeto, uso de clave, uso extendido de clave, períodos de validez y otras extensiones preconfigurados. Aplique las plantillas al emitir o firmar certificados.',
    sections: [
      {
        title: 'Origen',
        definitions: [
          { term: 'Sistema', description: 'Creadas en la instalación. Copie una para obtener una versión editable: la plantilla en sí no puede editarse ni eliminarse' },
          { term: 'Personalizada', description: 'Creadas o importadas aquí, y las únicas que pueden editarse o eliminarse' },
        ]
      },
      {
        title: 'Características',
        items: [
          { label: 'Tipo', text: 'Web Server, Email, VPN Server o Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon o Custom. Define los valores predeterminados de uso de clave, EKU y SAN' },
          { label: 'Valores predeterminados del sujeto', text: 'Prellenar Organización, OU, País, Estado, Ciudad y Email. El Email también se convierte en un SAN, sea cual sea el tipo de certificado' },
          { label: 'Uso de clave', text: 'Firma digital, cifrado de clave, etc.' },
          { label: 'Uso extendido de clave', text: 'Cualquier propósito que el servidor conozca: autenticación de servidor, autenticación de cliente, firma de código, protección de email, Smartcard Logon, sellado de tiempo, firma OCSP, IPsec, Microsoft RDP y otros' },
          { label: 'Tipos de SAN', text: 'Los tipos de nombre (DNS, IP, Email, URI, UPN) que puede llevar una solicitud hecha con la plantilla. Con «Aplicar los tipos de SAN permitidos» activado, el formulario de emisión, la firma de CSR, los protocolos de inscripción, las renovaciones y las aprobaciones rechazan cualquier otro tipo, y un nombre solo deducido del CN se omite. Las plantillas nuevas lo tienen activado; las anteriores y las integradas lo tienen desactivado. Ninguno marcado: se permiten todos los tipos' },
          { label: 'Validez', text: 'Período de validez predeterminado en días' },
          { label: 'Copiar', text: 'Clonar una plantilla existente y modificarla' },
          { label: 'Filtro de origen', text: 'Elija Personalizada en la barra de herramientas para ocultar las plantillas integradas y trabajar solo con las suyas. Se recuerda por navegador' },
          { label: 'Desactivar', text: 'Una plantilla desactivada, incluidas las integradas, deja de ofrecerse en el formulario Emitir certificado y a la autoinscripción de Windows, y muestra una insignia Inactiva. Activar la restablece. Una plantilla integrada se puede desactivar, no editar: cópiela para modificarla' },
          { label: 'Importar/Exportar', text: 'Compartir plantillas como archivos JSON entre instancias de UCM: la página exporta una plantilla a la vez, y un archivo de importación puede contener una o varias' },
          { label: 'qcStatements', text: 'Declaraciones opcionales ETSI EN 319 412-5 añadidas a cada certificado emitido desde la plantilla: QcCompliance, QcType (firma, sello o sitio web), QcSSCD, QcPDS (URL HTTPS e idioma de dos letras), QcRetentionPeriod, QcLimitValue, QcCClegislation (para un certificado cualificado según un marco jurídico fuera de la UE) y el identificador de semántica. No se aplican en la emisión EST, WSTEP ni mTLS, y una extensión qcStatements presente en una CSR se ignora. QcIdentMethod, QcQSCDlegislation y las declaraciones PSD2 no son compatibles' },
          { label: 'OID de política', text: 'OID de política de certificado adicionales (por ejemplo las políticas ETSI QCP-n, QCP-l, QCP-n-qscd, QCP-l-qscd y QCP-w), añadidos después de la política propia de la CA' },
          { label: 'Extensiones personalizadas', text: 'Extensiones que UCM no modela, cada una con un OID, un indicador de criticidad y el valor DER en hexadecimal, añadidas tal cual a cada certificado emitido desde la plantilla (formulario de emisión, firma de CSR, ACME, SCEP, WSTEP, aprobaciones; las renovaciones las conservan). El formulario de emisión puede añadir más o sustituir la del mismo OID. Se rechazan las extensiones que UCM establece por sí mismo: use sus propios ajustes. Un cliente que no reconoce una extensión crítica rechaza el certificado' },
          { label: 'Tipo de clave', text: 'RSA-2048, RSA-3072, RSA-4096, EC-P256, EC-P384 o EC-P521, con un resumen SHA-256, SHA-384 o SHA-512, o ML-DSA-44, ML-DSA-65 o ML-DSA-87. El resumen es el hash de firma de la CA emisora, no el de la clave final: se aplica siempre a una clave final ML-DSA bajo una CA RSA o EC, y una CA ML-DSA lo ignora' },
          { label: 'Preferencia de resumen (v2.251)', text: 'Toda vía que emite desde la plantilla (formulario de emisión, Sign CSR, ACME, SCEP, WSTEP, firmante TSA; EST no usa plantilla) firma con su resumen, elevado al que corresponde a la clave de la CA: SHA-384 para P-384, SHA-512 para P-521. Cuando una política lo prohíbe, firma en su lugar el resumen más fuerte más cercano permitido, y el resultado indica «Signature digest X replaced by Y by policy»' },
          { label: 'Brainpool', text: 'EC-BP256, EC-BP384 y EC-BP512 (RFC 5639, agrupadas en Brainpool en las listas de tipos de clave, ocultas en modo FIPS). OpenSSL y Windows leen sus cadenas y firmas, pero Chrome, Firefox, Go, rustls, GnuTLS y Java sin Bouncy Castle las rechazan para TLS, y Windows Schannel no las habilita de forma predeterminada. En un HSM, solo las conservan los proveedores PKCS#11' },
        ]
      },
      {
        title: 'Autoinscripción de Windows',
        items: [
          { label: 'Permitir autoinscripción', text: 'Anuncia la plantilla como autoEnroll=true en la Directiva de inscripción de certificados para que los clientes GPO/Kerberos la soliciten automáticamente al iniciar sesión. Desactivado de forma predeterminada, la inscripción manual sigue siendo posible sin él' },
          { label: 'Crear sujeto desde Active Directory', text: 'Deriva el sujeto y el SAN del objeto de AD del solicitante (mediante el conector de AD) en lugar de exigir que el cliente los proporcione, para la autoinscripción GPO desatendida. En los endpoints Kerberos, un sujeto indicado en la solicitud se ignora y las cuentas de equipo se rechazan; las plantillas de equipo toman siempre el nombre DNS del equipo' },
          { label: 'Restringir inscripción a grupo de AD', text: 'Solo los miembros del grupo de AD configurado (incluida la pertenencia anidada) pueden inscribirse por el endpoint Kerberos. Vacío = cualquier principal autenticado. No se aplica en el endpoint Usuario/Contraseña' },
          { label: 'Campos de asunto fijados', text: 'Fuerza los valores C/ST/L/O/OU en cada certificado emitido mediante WSTEP, sobrescribiendo el CSR o la derivación desde AD para esos campos. El CN y los SAN nunca se ven afectados; deje un campo vacío para mantenerlo dinámico' },
          { label: 'Patrón del nombre común', text: 'Construye el CN a partir de texto fijo y variables del directorio, por ejemplo {hostname}-WiFi o {displayName}, para una plantilla cuyo sujeto construye UCM. Solo cambia el CN: el SAN y la extensión SID siguen siendo los del directorio. Una variable vacía o un CN de más de 64 caracteres rechaza la solicitud, igual que un sujeto que un certificado de la misma CA ya lleva para otra cuenta' },
        ]
      },
    ],
    tips: [
      'Cree plantillas separadas para servidores TLS, clientes y firma de código',
      'Use la acción Copiar para crear rápidamente variaciones de una plantilla, incluida una del sistema',
      'Las plantillas con indicadores de autoinscripción muestran AD / Auto / ACL / Fijado en Marcas en su detalle',
    ],
  },
  helpGuides: {
    title: 'Plantillas de certificado',
    content: `
## Descripción general

Las plantillas definen perfiles de certificado reutilizables. En lugar de configurar manualmente el uso de clave, el uso extendido de clave, la validez y los campos de sujeto cada vez, aplique una plantilla para prellenarlo todo.

## Sistema y personalizadas

Cada plantilla es de un tipo u otro, como muestra la columna **Origen**.

### Sistema
Las plantillas creadas en la instalación: Web Server (TLS/SSL), Email Certificate (S/MIME), VPN Server, VPN Client, Code Signing, OCSP Signing, Client Authentication y Smartcard Logon. Editar y Eliminar se rechazan para ellas, tanto en la interfaz como en la API. **Copiar** le da una copia editable sobre la que trabajar.

### Personalizadas
Todo lo creado o importado aquí. Estas pueden editarse y eliminarse libremente.

Elija **Personalizada** en el filtro de origen de la barra de herramientas para ocultar las plantillas integradas y trabajar solo con las suyas. La elección se recuerda; si aún no hay ninguna plantilla personalizada, la lista lo indica y **Borrar todos los filtros** devuelve las integradas.

Las autoridades de certificación no se crean a partir de plantillas: créelas en la página **CAs**.

## Crear una plantilla

1. Haga clic en **Crear plantilla**
2. Introduzca un **nombre** y una descripción opcional
3. Seleccione el **tipo** de plantilla: Web Server, Email, VPN Server, VPN Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon o Custom. Define los valores predeterminados de uso de clave, uso extendido de clave y SAN, que luego puede cambiar
4. Configure los **valores predeterminados del sujeto** (O, OU, C, ST, L, CN, Email). El Email también se convierte en un SAN de email, sea cual sea el tipo de certificado
5. Seleccione las opciones de **uso de clave**
6. Seleccione los valores de **uso extendido de clave** entre los propósitos que el servidor conoce (Smartcard Logon, sellado de tiempo, Microsoft RDP y otros)
7. Establezca el **Tipo de clave** (RSA-2048, RSA-3072, RSA-4096, EC-P256, EC-P384, EC-P521, Brainpool EC-BP256/384/512 o ML-DSA-44/65/87), el resumen y el **período de validez predeterminado** en días. El resumen es el hash de firma de la CA emisora, por lo que sigue aplicándose a una clave ML-DSA bajo una CA RSA o EC; una CA ML-DSA lo ignora
8. Haga clic en **Crear**

## Usar plantillas

Al emitir un certificado o firmar un CSR, seleccione una plantilla del menú desplegable. La plantilla prellena:
- Campos del sujeto (puede sobrescribirlos)
- Uso de clave y uso extendido de clave
- Período de validez

## Indicadores de autoinscripción de Windows

Las plantillas llevan tres indicadores opcionales utilizados por los protocolos de autoinscripción de Windows (XCEP/WSTEP, configurados por realm en **Configuración → Autoinscripción de Windows**):

- **Permitir autoinscripción**: Anuncia la plantilla como \`autoEnroll=true\` en la Directiva de inscripción de certificados, de modo que los clientes autenticados por GPO/Kerberos la soliciten automáticamente al iniciar sesión sin acción del usuario. Desactivado de forma predeterminada: como en un ADCS real, una plantilla puede seguir inscribiéndose manualmente (MMC «Solicitar nuevo certificado», \`certreq\`) sin este indicador, ya que Inscribir y Autoinscribir son permisos separados.
- **Crear sujeto desde Active Directory**: Para la autoinscripción GPO desatendida: deriva el sujeto y el SAN del certificado a partir del objeto de AD del solicitante (mediante el conector de AD) en lugar de exigir que el cliente proporcione uno. En los endpoints Kerberos, un sujeto indicado en la solicitud se ignora y las cuentas de equipo se rechazan; las plantillas de equipo toman siempre el nombre DNS del equipo.
- **Restringir inscripción a grupo de AD**: Solo los principales que pertenecen al grupo de Active Directory configurado (incluida la pertenencia anidada) pueden inscribirse con esta plantilla por el endpoint autenticado con Kerberos. Introduzca un nombre de grupo o un DN completo; déjelo vacío para permitir cualquier principal autenticado, igual que el comportamiento predeterminado de un ADCS real. No se aplica en el endpoint Usuario/Contraseña, que no tiene identidad por solicitud que comprobar.

Las plantillas con estos indicadores muestran **AD**, **Auto** y **ACL** en **Marcas** en su detalle.

## Campos de sujeto fijados

Una plantilla puede **fijar** los campos organizativos del sujeto: **C, ST, L, O, OU**: para los certificados emitidos mediante WSTEP. Un valor fijado se fuerza en cada certificado emitido, sobrescribiendo lo que proporcione el CSR del cliente o la derivación desde Active Directory para ese campo.

- **El Common Name y el Subject Alternative Name nunca se ven afectados**: permanecen dinámicos por solicitante
- Deje un campo vacío para mantenerlo dinámico
- Las plantillas con campos fijados muestran **Fijado** en **Marcas**, y los valores fijados aparecen en la pestaña **Inscripción** del detalle de la plantilla

Utilícelo para garantizar una identidad organizativa uniforme (por ejemplo, \`O\` y \`C\` fijos) en toda una flota autoinscrita, independientemente de lo que envíe cada cliente de Windows.

## Patrón del nombre común

Para la inscripción de Windows, una plantilla cuyo sujeto construye UCM (una plantilla de equipo, o una plantilla de usuario con **Crear sujeto desde Active Directory**) puede tomar su CN de un patrón: texto fijo y variables entre llaves, leídas del objeto del directorio del solicitante, nunca de la solicitud.

- **Plantillas de equipo**: \`{hostname}\` (el nombre de la cuenta sin \`$\`), \`{fqdn}\` (su dNSHostName)
- **Plantillas de usuario**: \`{username}\` (sAMAccountName), \`{upn}\`, \`{mail}\`, \`{displayName}\`, \`{givenName}\`, \`{surname}\`
- **Ambas**: \`{domain}\` (los componentes DC del DN del objeto), \`{realm}\` (el realm del perfil)
- Escriba \`{{\` y \`}}\` para una llave literal. Una variable desconocida, una variable del otro tipo o un patrón en una plantilla cuyo solicitante proporciona el sujeto se rechazan al guardar la plantilla
- **Conservar la ruta del directorio** desactivado: el sujeto es solo el CN, más los campos fijados. Activado: el DN del objeto tras su propio nombre sigue al CN (para un usuario, el atributo de email se mantiene como sin patrón)
- **Solo cambia el CN**: el SAN (el nombre DNS del equipo, el UPN y el email del usuario) y la extensión SID se mantienen como sin patrón, y un patrón nunca añade un SAN
- **Rechazado, nunca recortado**: una variable que el directorio deja vacía, un resultado de más de 64 caracteres o con un carácter de control rechaza la solicitud; el motivo nombra la plantilla y la variable y consta en el registro de auditoría
- **Un sujeto por cuenta** (RFC 5280), comprobado en la emisión: se rechaza un sujeto que un certificado de la misma CA, sea cual sea su estado, ya lleva para otra cuenta (se ignoran mayúsculas y espacios de más), y la auditoría nombra el número de serie de ese certificado; la misma cuenta renueva y se inscribe de nuevo
- \`{displayName}\`, \`{givenName}\`, \`{surname}\` y \`{mail}\` no son únicos, ni tampoco \`{username}\` o \`{hostname}\` entre dominios: añada \`{upn}\`, \`{fqdn}\`, o \`{username}\`/\`{hostname}\` con \`{domain}\` o **Conservar la ruta del directorio**
- La **renovación** con el certificado toma el patrón vigente, para la cuenta que nombra el SID del certificado; se rechaza si ningún conector del perfil encuentra esa cuenta
- El endpoint Usuario/Contraseña no tiene identidad de directorio: el patrón no se aplica allí y el cliente proporciona el sujeto

## Extensiones personalizadas

Una plantilla puede añadir extensiones para las que UCM no tiene ningún ajuste. Cada una es un **OID**, un indicador **Crítica** y el **valor**: la codificación DER del valor de la extensión, en hexadecimal. UCM copia los bytes tal cual y nunca los analiza, así que compruebe antes la codificación con sus propias herramientas.

- Todo certificado emitido desde la plantilla las lleva: formulario de emisión, firma de CSR, perfiles ACME vinculados a la plantilla, perfiles SCEP, WSTEP y aprobaciones. Las renovaciones las conservan
- El formulario de emisión puede añadir más para un solo certificado; una entrada con el OID de una de las de la plantilla la sustituye
- Se rechazan las extensiones que UCM establece por sí mismo (uso de clave, EKU, nombres, identificadores de clave, punteros CRL y OCSP, políticas, restricciones de nombre, qcStatements...): use sus propios ajustes
- Un cliente que no reconoce una extensión **crítica** debe rechazar el certificado (RFC 5280, sección 4.2). Déjela no crítica salvo que todas las partes que confían en el certificado la entiendan

El inspector enumera esas extensiones para certificados y CA en la pestaña Extensiones, cada una con su OID, su nombre si se conoce, su criticidad y su valor; para un certificado, un botón copia el valor completo.

## Copiar plantillas

Abra una plantilla y, en su menú **⋯**, haga clic en **Copiar** para crear una copia. Modifique la copia sin afectar a la original.

## Importar y exportar

### Exportar
Exporte plantillas como JSON para compartirlas entre instancias de UCM.

### Importar
Importe desde:
- **Archivo JSON**: Suba un archivo JSON de plantilla, una plantilla o varias en un solo archivo
- **Pegar JSON**: Pegue JSON directamente en el área de texto

Una plantilla cuyo nombre ya existe se omite, y la importación indica cuáles fueron.

## Ejemplos comunes de plantillas

### Servidor TLS
- Uso de clave: Firma digital, cifrado de clave
- Uso extendido de clave: Autenticación de servidor
- Validez: 365 días

### Autenticación de cliente
- Uso de clave: Firma digital
- Uso extendido de clave: Autenticación de cliente
- Validez: 365 días

### Firma de código
- Uso de clave: Firma digital
- Uso extendido de clave: Firma de código
- Validez: 365 días
`
  }
}
