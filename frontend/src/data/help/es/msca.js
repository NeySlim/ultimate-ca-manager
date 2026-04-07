export default {
  helpContent: {
    title: 'Integración con Microsoft AD CS',
    subtitle: 'Firmar certificados con Microsoft Certificate Authority',
    overview: 'Conecte UCM a Microsoft Active Directory Certificate Services (AD CS) para firmar CSRs usando su infraestructura PKI de Windows. Soporta métodos de autenticación por certificado (mTLS), Kerberos y Basic.',
    sections: [
      {
        title: 'Métodos de autenticación',
        items: [
          { label: 'Certificado de cliente (mTLS)', text: 'Más seguro. Genere un certificado de cliente en su CA de MS, exporte como PFX, suba el certificado y la clave PEM.' },
          { label: 'Basic Auth', text: 'Usuario/contraseña sobre HTTPS. Funciona sin unión al dominio. Active basic auth en IIS certsrv.' },
          { label: 'Kerberos', text: 'Requiere el paquete requests-kerberos y una máquina unida al dominio o keytab configurado.' },
        ]
      },
      {
        title: 'Firma de CSRs',
        items: [
          { label: 'Selección de plantilla', text: 'Elegir entre las plantillas de certificado disponibles en la CA de MS' },
          { label: 'Aprobación automática', text: 'Las plantillas con autoenroll devuelven el certificado de inmediato' },
          { label: 'Aprobación del administrador', text: 'Algunas plantillas requieren aprobación del administrador — UCM rastrea la solicitud pendiente' },
          { label: 'Consulta de estado', text: 'Verificar el estado de solicitudes pendientes desde el panel de detalle del CSR' },
        ]
      },
      {
        title: 'Enroll on Behalf Of (EOBO)',
        items: [
          { label: 'Descripción general', text: 'Enviar CSR en nombre de otro usuario usando certificados de agente de inscripción' },
          { label: 'Enrollee DN', text: 'Distinguished Name del usuario objetivo (se completa automáticamente desde el subject del CSR)' },
          { label: 'Enrollee UPN', text: 'User Principal Name del usuario objetivo (se completa automáticamente desde el email SAN del CSR)' },
          { label: 'Requisitos', text: 'La plantilla de la CA debe permitir la inscripción en nombre de otros. La cuenta de servicio de UCM necesita un certificado de agente de inscripción.' },
        ]
      },
    ],
    tips: [
      'Pruebe la conexión primero para verificar la autenticación y descubrir las plantillas disponibles.',
      'Active EOBO marcando la casilla en el modal de firma — los campos se completan automáticamente con los datos del CSR.',
      'La autenticación por certificado de cliente es recomendada para producción — no requiere unión al dominio.',
    ],
    warnings: [
      'Kerberos requiere que la máquina esté unida al dominio o un keytab configurado — no disponible en Docker.',
      'EOBO requiere un certificado de agente de inscripción configurado en el servidor AD CS.',
    ],
  },
  helpGuides: {
    title: 'Integración con Microsoft AD CS',
    content: `
## Descripción general

UCM se integra con Microsoft Active Directory Certificate Services (AD CS) para firmar CSRs usando su infraestructura PKI de Windows existente. Esto conecta su CA interna con la gestión del ciclo de vida de certificados de UCM.

## Configurar una conexión

1. Vaya a **Configuración → Microsoft CA**
2. Haga clic en **Agregar conexión**
3. Ingrese el **Nombre de conexión** y el **Nombre de host del servidor CA**
4. Opcionalmente ingrese el **Nombre común de la CA** (se detecta automáticamente si está vacío)
5. Seleccione el **Método de autenticación**
6. Ingrese las credenciales para el método elegido
7. Haga clic en **Probar conexión** para verificar
8. Establezca una **Plantilla predeterminada** y haga clic en **Guardar**

## Métodos de autenticación

| Método | Requisitos | Ideal para |
|--------|-----------|------------|
| **Certificado de cliente (mTLS)** | Certificado/clave PEM del cliente de la CA | Producción — no requiere unión al dominio |
| **Basic Auth** | Usuario + contraseña, HTTPS | Configuraciones simples — active basic auth en IIS certsrv |
| **Kerberos** | Máquina unida al dominio + keytab | Entornos empresariales AD |

### Configuración de certificado de cliente (Recomendado)

1. En su CA de Windows, cree un certificado para la cuenta de servicio de UCM
2. Exporte como PFX, luego convierta a PEM:
   \`\`\`bash
   openssl pkcs12 -in client.pfx -out client-cert.pem -clcerts -nokeys
   openssl pkcs12 -in client.pfx -out client-key.pem -nocerts -nodes
   \`\`\`
3. Pegue el contenido PEM del certificado y la clave en el formulario de conexión de UCM

## Firma de CSRs vía Microsoft CA

1. Navegue a **CSRs → Pendientes**
2. Seleccione un CSR y haga clic en **Firmar**
3. Cambie a la pestaña **Microsoft CA**
4. Seleccione la conexión y la plantilla de certificado
5. Haga clic en **Firmar**

### Plantillas con aprobación automática
El certificado se devuelve de inmediato y se importa en UCM.

### Plantillas con aprobación del administrador
UCM guarda la solicitud como **Pendiente** y rastrea el ID de solicitud de la CA de MS. Una vez aprobada en la CA de Windows, verifique el estado desde el panel de detalle del CSR para importar el certificado.

## Enroll on Behalf Of (EOBO)

EOBO permite que un agente de inscripción solicite certificados en nombre de otros usuarios. Esto es común en entornos empresariales donde un administrador de PKI gestiona certificados para los usuarios finales.

### Prerequisitos

- La cuenta de servicio de UCM necesita un **certificado de agente de inscripción** emitido por la CA
- La plantilla de certificado debe tener habilitado el permiso **"Inscribir en nombre de otros usuarios"**
- La pestaña de seguridad de la plantilla debe otorgar al agente de inscripción el derecho a inscribir

### Uso de EOBO en UCM

1. En el modal de firma, seleccione la conexión Microsoft CA y la plantilla
2. Marque la casilla **Enroll on Behalf Of (EOBO)**
3. Los campos se completan automáticamente desde el CSR:
   - **Enrollee DN** — desde el subject del CSR (ej., CN=John Doe,OU=Users,DC=corp,DC=local)
   - **Enrollee UPN** — desde el email SAN del CSR (ej., john.doe@corp.local)
4. Ajuste los valores si es necesario
5. Haga clic en **Firmar**

UCM pasa estos como atributos de solicitud ADCS:
- EnrolleeObjectName:<DN> — identifica al usuario objetivo en AD
- EnrolleePrincipalName:<UPN> — el nombre de inicio de sesión del usuario

### EOBO vs Inscripción directa

| Característica | Inscripción directa | EOBO |
|----------------|---------------------|------|
| Quién firma | El propio usuario | Agente de inscripción en nombre |
| Clave privada | Máquina del usuario | Puede estar en UCM (modelo CSR) |
| Permiso de plantilla | Inscripción estándar | Requiere derechos de agente de inscripción |
| Caso de uso | Autoservicio | Gestión centralizada de PKI |

## Resolución de problemas

| Problema | Solución |
|----------|----------|
| La prueba de conexión falla | Verifique el nombre de host, el puerto 443 y que certsrv sea accesible |
| No se encuentran plantillas | Verifique que la cuenta UCM tenga permisos de inscripción en la CA |
| EOBO denegado | Verifique el certificado de agente de inscripción y los permisos de la plantilla |
| Solicitud atascada como pendiente | Apruebe en la consola de la CA de Windows, luego actualice el estado en UCM |

> 💡 Use el botón **Probar conexión** para verificar la autenticación y descubrir las plantillas disponibles antes de firmar.
`
  }
}
