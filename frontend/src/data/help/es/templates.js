export default {
  helpContent: {
    title: 'Plantillas de certificados',
    subtitle: 'Perfiles de certificados reutilizables',
    overview: 'Defina perfiles de certificados reutilizables con campos de sujeto, uso de clave, uso extendido de clave, períodos de validez y otras extensiones preconfiguradas. Aplique plantillas al emitir o firmar certificados.',
    sections: [
      {
        title: 'Origen',
        definitions: [
          { term: 'Sistema', description: 'Creadas en la instalación. Duplique una para obtener una copia editable: la plantilla en sí no puede editarse ni eliminarse' },
          { term: 'Personalizada', description: 'Creadas o importadas aquí, y las únicas que pueden editarse o eliminarse' },
        ]
      },
      {
        title: 'Características',
        items: [
          { label: 'Tipo', text: 'Web Server, Email, VPN Server o Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon o Custom. Define los valores predeterminados de uso de clave, EKU y SAN' },
          { label: 'Valores predeterminados del sujeto', text: 'Prellenar Organización, OU, País, Estado, Ciudad' },
          { label: 'Uso de clave', text: 'Firma digital, cifrado de clave, etc.' },
          { label: 'Uso extendido de clave', text: 'Autenticación de servidor, autenticación de cliente, firma de código, protección de correo' },
          { label: 'Validez', text: 'Período de validez predeterminado en días' },
          { label: 'Duplicar', text: 'Clonar una plantilla existente y modificarla' },
          { label: 'Mostrar sistema', text: 'Oculte las plantillas integradas para trabajar solo con las suyas. Se recuerda por navegador' },
          { label: 'Importar/Exportar', text: 'Compartir plantillas como archivos JSON entre instancias de UCM' },
        ]
      },
      {
        title: 'Autoinscripción de Windows',
        items: [
          { label: 'Permitir autoinscripción', text: 'Anuncia la plantilla como autoEnroll=true en la Directiva de inscripción de certificados para que los clientes GPO/Kerberos la soliciten automáticamente al iniciar sesión. Desactivado por defecto, la inscripción manual sigue siendo posible sin él' },
          { label: 'Crear sujeto desde Active Directory', text: 'Deriva el sujeto y el SAN del objeto de AD del solicitante (mediante el conector de AD) en lugar de exigir que el cliente proporcione uno, para la autoinscripción GPO desatendida' },
          { label: 'Restringir la inscripción a un grupo de AD', text: 'Solo los miembros del grupo de AD configurado (incluida la pertenencia anidada) pueden inscribirse por el punto de conexión Kerberos. Vacío = cualquier principal autenticado. No se aplica en el punto de conexión Usuario/Contraseña' },
          { label: 'Campos de sujeto fijados', text: 'Fuerza los valores C/ST/L/O/OU en cada certificado emitido mediante WSTEP, sobrescribiendo el CSR o la derivación desde AD para esos campos. CN y SAN nunca se ven afectados, deje un campo vacío para mantenerlo dinámico' },
        ]
      },
    ],
    tips: [
      'Cree plantillas separadas para servidores TLS, clientes y firma de código',
      'Use la acción Duplicar para crear rápidamente variaciones de una plantilla, incluida una de sistema',
      'Las plantillas con indicadores de autoinscripción muestran las insignias AD / Auto / ACL / Pinned en la lista',
    ],
  },
  helpGuides: {
    title: 'Plantillas de certificados',
    content: `
## Descripción general

Las plantillas definen perfiles de certificados reutilizables. En lugar de configurar manualmente el uso de clave, uso extendido de clave, validez y campos de sujeto cada vez, aplique una plantilla para prellenar todo.

## Sistema y personalizadas

Cada plantilla es de un tipo u otro, como muestra la columna **Origen**.

### Sistema
Las plantillas creadas en la instalación: Web Server (TLS/SSL), Email Certificate (S/MIME), VPN Server, VPN Client, Code Signing, OCSP Signing, Client Authentication y Smartcard Logon. Editar y Eliminar se rechazan para ellas, tanto en la interfaz como en la API. **Duplicar** le da una copia editable sobre la que trabajar.

### Personalizadas
Todo lo creado o importado aquí. Estas pueden editarse y eliminarse libremente.

Desactive **Mostrar sistema** en la barra de herramientas para ocultar las plantillas integradas y trabajar solo con las suyas. La elección se recuerda, salvo que aún no tenga plantillas personalizadas, en cuyo caso las integradas permanecen visibles.

Las autoridades de certificación no se crean a partir de plantillas: créelas en la página **CAs**.

## Crear una plantilla

1. Haga clic en **Crear plantilla**
2. Ingrese un **nombre** y una descripción opcional
3. Seleccione el **tipo** de plantilla: Web Server, Email, VPN Server, VPN Client, Code Signing, Client Auth, OCSP Signing, Smartcard Logon o Custom. Define los valores predeterminados de uso de clave, uso extendido de clave y SAN, que luego puede cambiar
4. Configure los **valores predeterminados del sujeto** (O, OU, C, ST, L)
5. Seleccione las opciones de **uso de clave**
6. Seleccione los valores de **uso extendido de clave**
7. Establezca el **período de validez predeterminado** en días
8. Haga clic en **Crear**

## Usar plantillas

Al emitir un certificado o firmar un CSR, seleccione una plantilla del menú desplegable. La plantilla prellena:
- Campos del sujeto (puede sobrescribirlos)
- Uso de clave y uso extendido de clave
- Período de validez

## Indicadores de autoinscripción de Windows

Las plantillas llevan tres indicadores opcionales utilizados por los protocolos de autoinscripción de Windows (XCEP/WSTEP, configurados en **Configuración → Autoinscripción de Windows**):

- **Permitir autoinscripción**: Anuncia la plantilla como \`autoEnroll=true\` en la Directiva de inscripción de certificados, de modo que los clientes autenticados por GPO/Kerberos la soliciten automáticamente al iniciar sesión sin acción del usuario. Desactivado por defecto: como en un ADCS real, una plantilla puede seguir inscribiéndose manualmente (MMC «Solicitar nuevo certificado», \`certreq\`) sin este indicador, ya que Enroll y Autoenroll son permisos separados.
- **Crear sujeto desde Active Directory**: Para la autoinscripción GPO desatendida: deriva el sujeto y el SAN del certificado a partir del objeto de AD del solicitante (mediante el conector de AD) en lugar de exigir que el cliente proporcione uno.
- **Restringir la inscripción a un grupo de AD**: Solo los principales que pertenecen al grupo de Active Directory configurado (incluida la pertenencia anidada) pueden inscribirse con esta plantilla por el punto de conexión autenticado con Kerberos. Introduzca un nombre de grupo o un DN completo; déjelo vacío para permitir cualquier principal autenticado, igual que el comportamiento por defecto de un ADCS real. No se aplica en el punto de conexión Usuario/Contraseña, que no tiene identidad por solicitud que comprobar.

Las plantillas con estos indicadores muestran las insignias **AD**, **Auto** y **ACL** en la lista de plantillas.

## Campos de sujeto fijados

Una plantilla puede **fijar** los campos organizativos del sujeto: **C, ST, L, O, OU**: para los certificados emitidos mediante WSTEP. Un valor fijado se fuerza en cada certificado emitido, sobrescribiendo lo que proporcione el CSR del cliente o la derivación desde Active Directory para ese campo.

- **El Common Name y el Subject Alternative Name nunca se ven afectados**: permanecen dinámicos por solicitante
- Deje un campo vacío para mantenerlo dinámico
- Las plantillas con campos fijados muestran una insignia **Pinned**, y los valores fijados aparecen en el panel de detalles de la plantilla

Utilícelo para garantizar una identidad organizativa uniforme (por ejemplo, \`O\` y \`C\` fijos) en toda una flota autoinscrita, independientemente de lo que envíe cada cliente de Windows.

## Duplicar plantillas

Haga clic en **Duplicar** para crear una copia de una plantilla existente. Modifique la copia sin afectar la original.

## Importar y exportar

### Exportar
Exporte plantillas como JSON para compartir entre instancias de UCM.

### Importar
Importe desde:
- **Archivo JSON**: Suba un archivo JSON de plantilla
- **Pegar JSON**: Pegue JSON directamente en el área de texto

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
