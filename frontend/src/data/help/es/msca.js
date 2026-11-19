export default {
  helpContent: {
    title: 'Integración con Microsoft AD CS',
    subtitle: 'Firmar certificados con Microsoft Certificate Authority',
    overview: 'Conecte UCM a Microsoft Active Directory Certificate Services (AD CS) para firmar CSRs usando su infraestructura PKI de Windows y gestionar el ciclo de vida completo de los certificados. Soporta autenticación por certificado (mTLS), Kerberos y Basic, más un canal de administración WinRM opcional para revocación, CRL, inventario y gestión de solicitudes pendientes.',
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
          { label: 'Aprobación del administrador', text: 'Algunas plantillas requieren aprobación del administrador, UCM rastrea la solicitud pendiente' },
          { label: 'Solicitudes pendientes', text: 'Una solicitud que la CA retiene para su administrador sigue Pendiente en UCM, y la página no ofrece comprobar su estado: una vez emitida en la CA, importe el certificado, o deje que la Sincronización de inventario por el canal de administración WinRM importe los certificados que UCM aún no conoce' },
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
      {
        title: 'Ciclo de vida: renovar y revocar',
        items: [
          { label: 'Renovar', text: 'Renovar un certificado emitido por AD CS reenvía su CSR original a la misma conexión y plantilla, firma la CA emisora, no UCM.' },
          { label: 'Revocar', text: 'Revocar un certificado emitido por AD CS es local a UCM, salvo que el canal de administración WinRM esté configurado, en ese caso se propaga a la CA de Windows.' },
          { label: 'Renovación pendiente', text: 'Si la CA retiene la renovación para aprobación del administrador, UCM la rastrea como cualquier otra solicitud pendiente.' },
        ]
      },
      {
        title: 'Canal de administración WinRM (opcional)',
        items: [
          { label: 'Propósito', text: 'Ejecuta operaciones de gestión en la CA de Windows (revocar, anular revocación, publicar CRL, inventario, aprobar/denegar) vía PowerShell remoting + certutil, cosas que la inscripción web de AD CS no puede hacer.' },
          { label: 'Transporte', text: 'NTLM o Kerberos sobre HTTP/HTTPS. Se recomienda Kerberos + HTTPS; Kerberos reutiliza el keytab de la conexión.' },
          { label: 'Credenciales', text: 'Reutiliza por defecto las de la conexión. Las conexiones mTLS deben definir una cuenta WinRM dedicada (oficial "Emitir y administrar certificados" con privilegios mínimos).' },
          { label: 'Requisito', text: 'WinRM habilitado en la CA y el paquete opcional pywinrm instalado. Las operaciones de gestión requieren admin:system; propagar una revocación o un levantamiento de suspensión a la CA sigue el permiso write:certificates del certificado.' },
        ]
      },
      {
        title: 'Sincronización de revocaciones por CRL',
        items: [
          { label: 'Sincronización unidireccional', text: 'Obtiene periódicamente la CRL de la CA y marca como revocados en UCM los certificados revocados en la CA. Nunca anula una revocación.' },
          { label: 'Fuente de la CRL', text: 'Una URL de CRL explícita, o autodetectada desde el punto de distribución de CRL de los certificados emitidos.' },
          { label: 'Verificada', text: 'La firma de la CRL se comprueba contra el certificado de la CA antes de aplicar nada.' },
        ]
      },
      {
        title: 'Inventario de la CA y panel de control',
        items: [
          { label: 'Sincronización de inventario', text: 'Importa certificados emitidos directamente en la CA que UCM aún no conoce (incremental por id de solicitud); la reconciliación está disponible mediante la API.' },
          { label: 'Solicitudes pendientes', text: 'Listar, aprobar (reenvío + importación automática) o denegar solicitudes en espera de aprobación del administrador de la CA.' },
          { label: 'Salud de la CA', text: 'Estado del servicio de la CA, caducidad del certificado de la CA, próxima actualización de la CRL y número de solicitudes pendientes de un vistazo.' },
        ]
      },
    ],
    tips: [
      'Pruebe la conexión primero para verificar la autenticación y descubrir las plantillas disponibles.',
      'Active EOBO marcando la casilla en el modal de firma: los campos se completan automáticamente con los datos del CSR.',
      'La autenticación por certificado de cliente es recomendada para producción, no requiere unión al dominio.',
      'Habilite el canal de administración WinRM para propagar las revocaciones a la CA y gestionar las solicitudes pendientes desde UCM.',
    ],
    warnings: [
      'Kerberos requiere que la máquina esté unida al dominio o un keytab configurado, no disponible en Docker.',
      'EOBO requiere un certificado de agente de inscripción configurado en el servidor AD CS.',
      'Sin el canal de administración WinRM, revocar un certificado AD CS solo lo marca como revocado en UCM: la CA de Windows no es notificada.',
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
4. Opcionalmente ingrese el **Nombre común de la CA** (se usa el nombre de host del servidor si está vacío)
5. Seleccione el **Método de autenticación**
6. Ingrese las credenciales para el método elegido
7. Haga clic en **Probar conexión** para verificar
8. Establezca una **Plantilla predeterminada** y haga clic en **Guardar**

## Métodos de autenticación

| Método | Requisitos | Ideal para |
|--------|-----------|------------|
| **Certificado de cliente (mTLS)** | Certificado/clave PEM del cliente de la CA | Producción, no requiere unión al dominio |
| **Basic Auth** | Usuario + contraseña, HTTPS | Configuraciones simples: active basic auth en IIS certsrv |
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
UCM guarda la solicitud como **Pendiente** y rastrea el ID de solicitud de la CA de MS. La página no ofrece una comprobación de estado para ella: una vez emitida en la CA de Windows, importe el certificado, o deje que la **Sincronización de inventario** por el canal de administración WinRM importe los certificados que UCM aún no conoce.

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
   - **Enrollee DN**: desde el subject del CSR (ej., CN=John Doe,OU=Users,DC=corp,DC=local)
   - **Enrollee UPN**: desde el email SAN del CSR (ej., john.doe@corp.local)
4. Ajuste los valores si es necesario
5. Haga clic en **Firmar**

UCM pasa estos como atributos de solicitud ADCS:
- EnrolleeObjectName:<DN>: identifica al usuario objetivo en AD
- EnrolleePrincipalName:<UPN>: el nombre de inicio de sesión del usuario

### EOBO vs Inscripción directa

| Característica | Inscripción directa | EOBO |
|----------------|---------------------|------|
| Quién firma | El propio usuario | Agente de inscripción en nombre |
| Clave privada | Máquina del usuario | Puede estar en UCM (modelo CSR) |
| Permiso de plantilla | Inscripción estándar | Requiere derechos de agente de inscripción |
| Caso de uso | Autoservicio | Gestión centralizada de PKI |

## Ciclo de vida de los certificados

### Renovar un certificado AD CS
La renovación **no** vuelve a firmar localmente (la clave emisora reside en la CA de Windows). UCM reenvía la CSR original del certificado: misma clave, sujeto y SANs, a la conexión y plantilla que lo emitieron, y actualiza el certificado en su lugar. Si la CA retiene la renovación para aprobación del administrador, se rastrea como una solicitud pendiente.

### Revocar un certificado AD CS
La inscripción web de AD CS no tiene endpoint de revocación. Revocar un certificado emitido por AD CS:
- **Sin el canal de administración WinRM**: lo marca como revocado solo en UCM; la CA de Windows no es notificada. Revóquelo también en la CA.
- **Con el canal de administración WinRM**: UCM propaga la revocación a la CA de Windows (certutil -revoke + publicación de la CRL). Levantar un certificateHold también propaga la anulación de la revocación.

## Canal de administración WinRM (opcional)

El canal de administración permite a UCM ejecutar en la CA de Windows operaciones de gestión que la inscripción web no puede: revocar/anular revocación, publicar CRL, inventario, y aprobar/denegar solicitudes pendientes. Usa PowerShell remoting + certutil.

### Requisitos
- **WinRM habilitado** en la CA (Enable-PSRemoting; se recomienda listener HTTPS en 5986)
- El paquete opcional **pywinrm** instalado en UCM (pip install pywinrm)
- Una cuenta autorizada a **administrar certificados** en la CA ("Issue and Manage Certificates")

### Configuración
1. Edite la conexión y habilite el **canal de administración WinRM**
2. Configure el host (por defecto el servidor de la conexión), el puerto y el transporte
3. **Transporte**: Kerberos (recomendado, reutiliza el keytab de la conexión) o NTLM, sobre HTTP o HTTPS
4. **Credenciales**: deje vacío para reutilizar las de la conexión (Basic/Kerberos). Las conexiones mTLS no tienen credenciales WinRM reutilizables, configure una cuenta dedicada
5. Haga clic en **Probar canal de administración**

| Modo de autenticación de inscripción | ¿Reutiliza credenciales para WinRM? |
|--------------------------------------|--------------------------------------|
| Kerberos (keytab) | Sí: mismo principal/keytab |
| Basic (usuario/contraseña) | Sí: contraseña hacia NTLM/Kerberos |
| Certificado (mTLS) | No: configure una cuenta WinRM dedicada |

## Sincronización de revocaciones por CRL

Habilite **Sincronizar revocaciones desde la CRL de la CA** en la conexión para que UCM obtenga periódicamente la CRL de la CA y marque como revocados en UCM los certificados revocados en la CA. Es estrictamente unidireccional (de la CA a UCM) y nunca anula la revocación de un certificado revocado en UCM. La URL de la CRL se toma de la conexión o se autodetecta desde el punto de distribución de CRL de los certificados emitidos, y su firma se verifica contra el certificado de la CA antes de aplicar nada. Se ejecuta cada hora, más una acción **Sincronizar CRL ahora**.

## Sincronización de inventario de la CA

Habilite **Importar certificados emitidos directamente en la CA** para traer al almacén de UCM los certificados emitidos fuera de UCM (herramientas nativas, autoenrollment, o anteriores a UCM), de modo que UCM rastree todo el ciclo de vida. Lee la base de datos de la CA con certutil -view, importa los certificados que UCM aún no tiene (deduplicados por número de serie) y es incremental por id de solicitud (con opción de reexploración completa). Una vista de **reconciliación** lista los certificados presentes en la CA pero no en UCM, y viceversa. Se ejecuta cada 6 horas, más una acción **Importar desde la CA ahora**. Requiere el canal de administración WinRM.

## Panel de control de la CA

El panel de control (abierto desde la conexión, requiere el canal de administración) gestiona las solicitudes en espera de aprobación del administrador de la CA y muestra la salud de la CA:
- **Solicitudes pendientes**: listar, **Aprobar** (certutil -resubmit; el certificado emitido se importa automáticamente) o **Denegar** (certutil -deny)
- **Salud**: estado del servicio de la CA, caducidad del certificado de la CA, próxima actualización de la CRL y número de solicitudes pendientes

## Resolución de problemas

| Problema | Solución |
|----------|----------|
| La prueba de conexión falla | Verifique el nombre de host, el puerto 443 y que certsrv sea accesible |
| No se encuentran plantillas | Verifique que la cuenta UCM tenga permisos de inscripción en la CA |
| EOBO denegado | Verifique el certificado de agente de inscripción y los permisos de la plantilla |
| Solicitud atascada como pendiente | Apruébela desde el panel de control de la CA, o en la consola de la CA de Windows y luego actualice el estado en UCM |
| La prueba del canal de administración falla | Verifique que WinRM esté habilitado en la CA, el puerto/transporte, y que pywinrm esté instalado |
| La revocación no llega a la CA | Habilite el canal de administración WinRM: sin él, la revocación es local a UCM |
| Pendiente no detectado (CA no inglesa) | Corregido en v2.192. UCM ahora reconoce las páginas de pendiente localizadas de AD CS |

> 💡 Use el botón **Probar conexión** para verificar la autenticación y descubrir las plantillas disponibles antes de firmar. Habilite el **canal de administración WinRM** para gestionar revocación, CRL, inventario y solicitudes pendientes directamente desde UCM.
`
  }
}
