export default {
  helpContent: {
    title: 'Integración con Microsoft AD CS',
    subtitle: 'Firmar certificados con la CA de Microsoft',
    overview: 'Conecte UCM a Microsoft Active Directory Certificate Services (AD CS) para firmar CSR con su infraestructura PKI de Windows y gestionar todo el ciclo de vida de los certificados. Admite autenticación por certificado (mTLS), Kerberos y Basic, además de un canal de administración WinRM opcional para la revocación, la CRL, el inventario y la gestión de solicitudes pendientes.',
    sections: [
      {
        title: 'Métodos de autenticación',
        items: [
          { label: 'Certificado cliente (mTLS)', text: 'El más seguro. Genere un certificado cliente en su CA de Microsoft, expórtelo como PFX y suba el certificado y la clave en PEM.' },
          { label: 'Auth básica', text: 'Usuario y contraseña sobre HTTPS. Funciona sin unir al dominio. Active la autenticación básica en certsrv de IIS.' },
          { label: 'Kerberos', text: 'Requiere el paquete requests-kerberos y una máquina unida al dominio o un keytab configurado.' },
        ]
      },
      {
        title: 'Firma de CSR',
        items: [
          { label: 'Selección de plantilla', text: 'Elija entre las plantillas de certificado disponibles en la CA de Microsoft' },
          { label: 'Aprobación automática', text: 'Las plantillas con inscripción automática devuelven el certificado de inmediato' },
          { label: 'Aprobación de un responsable', text: 'Algunas plantillas requieren la aprobación de un responsable: UCM hace el seguimiento de la solicitud pendiente' },
          { label: 'Solicitudes pendientes', text: 'Una solicitud que la CA retiene para su responsable permanece Pendiente en UCM: use Verificar estado en los detalles de la CSR, o apruébela desde el panel de control de la CA. La sincronización del inventario también completa una solicitud pendiente que la CA muestra como emitida, y marca la que muestra como denegada. Una solicitud cuya CSR se firma en otro lugar (una CA local, una importación) se cierra; si sus detalles siguen abiertos, Verificar estado muestra "Esta CSR se firmó en otro lugar: su solicitud en Microsoft CA está cerrada". Un certificado que la CA aún emite para ella entra como un certificado aparte cuando la solicitud se aprueba desde el panel de control de la CA, o mediante una sincronización de inventario completa (full: true en POST /api/v2/microsoft-cas/{id}/inventory-sync): Importar de la CA ahora y la sincronización programada son incrementales y pueden no verlo' },
        ]
      },
      {
        title: 'Inscripción en nombre de (EOBO)',
        items: [
          { label: 'Resumen', text: 'Enviar una CSR en nombre de otro usuario mediante certificados de agente de inscripción' },
          { label: 'DN del inscrito', text: 'Nombre distinguido del usuario de destino (se rellena a partir del sujeto de la CSR)' },
          { label: 'UPN del inscrito', text: 'Nombre principal de usuario del usuario de destino (se rellena a partir del correo del SAN de la CSR)' },
          { label: 'Requisitos', text: 'La plantilla de la CA debe permitir la inscripción en nombre de otros. La cuenta de servicio de UCM necesita un certificado de agente de inscripción.' },
        ]
      },
      {
        title: 'Ciclo de vida: renovar y revocar',
        items: [
          { label: 'Renovar', text: 'Renovar un certificado emitido por AD CS vuelve a enviar su CSR original a la misma conexión y plantilla: lo firma la CA emisora, no UCM.' },
          { label: 'Revocar', text: 'Revocar un certificado emitido por AD CS es local a UCM salvo que el canal de administración WinRM esté configurado; en ese caso se propaga a la CA de Windows.' },
          { label: 'Renovación pendiente', text: 'Si la CA retiene la renovación para la aprobación de un responsable, UCM la sigue como una solicitud pendiente más.' },
        ]
      },
      {
        title: 'Canal de administración WinRM (opcional)',
        items: [
          { label: 'Finalidad', text: 'Ejecuta operaciones de gestión en la CA de Windows (revocar, anular la revocación, publicar la CRL, inventario, aprobar/denegar) mediante PowerShell remoting y certutil, cosas que AD CS Web Enrollment no puede hacer.' },
          { label: 'Transporte', text: 'NTLM o Kerberos sobre HTTP/HTTPS. Se recomienda Kerberos con HTTPS; Kerberos reutiliza el keytab de la conexión.' },
          { label: 'Credenciales', text: 'Reutiliza por defecto las propias de la conexión. Las conexiones inscritas con mTLS deben definir una cuenta WinRM dedicada (oficial "Issue and Manage Certificates" con privilegios mínimos).' },
          { label: 'Requisito', text: 'WinRM habilitado en la CA y el paquete opcional pywinrm instalado. Las operaciones de gestión requieren admin:system; propagar una revocación o el levantamiento de una retención a la CA sigue el permiso write:certificates del certificado.' },
        ]
      },
      {
        title: 'Sincronización de revocaciones por CRL',
        items: [
          { label: 'Sincronización unidireccional', text: 'Obtiene periódicamente la CRL de la CA y marca como revocados en UCM los certificados revocados en la CA. Nunca anula una revocación.' },
          { label: 'Origen de la CRL', text: 'Una URL de CRL explícita, o detectada automáticamente a partir del punto de distribución de CRL de los certificados emitidos.' },
          { label: 'Verificada', text: 'La firma de la CRL se comprueba con el certificado de la CA antes de aplicar nada.' },
        ]
      },
      {
        title: 'Inventario de la CA y panel de control',
        items: [
          { label: 'Sincronización del inventario', text: 'Importa los certificados emitidos directamente en la CA que UCM aún no conoce (incremental por ID de solicitud); la conciliación está disponible mediante la API.' },
          { label: 'Solicitudes pendientes', text: 'Listar, aprobar (reenvío e importación automática) o denegar solicitudes a la espera de la aprobación del responsable de la CA.' },
          { label: 'Estado de la CA', text: 'Estado del servicio de la CA, caducidad del certificado de la CA, próxima actualización de la CRL y número de pendientes de un vistazo.' },
        ]
      },
    ],
    tips: [
      'Pruebe primero la conexión para verificar la autenticación y descubrir las plantillas disponibles.',
      'Active EOBO marcando la casilla en el diálogo de firma: los campos se rellenan con los datos de la CSR.',
      'Se recomienda la autenticación con certificado cliente en producción: no requiere unir al dominio.',
      'Active el canal de administración WinRM para propagar las revocaciones a la CA y gestionar las solicitudes pendientes desde UCM.',
    ],
    warnings: [
      'Kerberos requiere que la máquina esté unida al dominio o un keytab configurado, no disponible en Docker.',
      'EOBO requiere un certificado de agente de inscripción configurado en el servidor AD CS.',
      'Sin el canal de administración WinRM, revocar un certificado de AD CS solo lo marca como revocado en UCM: la CA de Windows no recibe ningún aviso.',
    ],
  },
  helpGuides: {
    title: 'Integración con Microsoft AD CS',
    content: `
## Descripción general

UCM se integra con Microsoft Active Directory Certificate Services (AD CS) para firmar CSR con su infraestructura PKI de Windows existente. Así se une su CA interna con la gestión del ciclo de vida de certificados de UCM.

## Configurar una conexión

1. Vaya a **Ajustes → CA de Microsoft**
2. Pulse **Agregar conexión**
3. Introduzca el **Nombre de conexión** y el **Nombre de host del servidor CA**
4. Opcionalmente, introduzca el **Nombre común de la CA** (si queda vacío, se usa el nombre de host del servidor)
5. Seleccione el **Método de autenticación**
6. Introduzca las credenciales del método elegido
7. Pulse **Probar conexión** para verificar
8. Defina una **Plantilla de certificado predeterminada** y pulse **Guardar**

## Métodos de autenticación

| Método | Requisitos | Idóneo para |
|--------|------------|-------------|
| **Certificado cliente (mTLS)** | Certificado y clave cliente en PEM de la CA | Producción, sin unir al dominio |
| **Auth básica** | Usuario y contraseña, HTTPS | Configuraciones sencillas: active la autenticación básica en certsrv de IIS |
| **Kerberos** | Máquina unida al dominio y keytab | Entornos empresariales con AD |

### Configuración del certificado cliente (recomendada)

1. En su CA de Windows, cree un certificado para la cuenta de servicio de UCM
2. Expórtelo como PFX y conviértalo a PEM:
   \`\`\`bash
   openssl pkcs12 -in client.pfx -out client-cert.pem -clcerts -nokeys
   openssl pkcs12 -in client.pfx -out client-key.pem -nocerts -nodes
   \`\`\`
3. Pegue el contenido PEM del certificado y de la clave en el formulario de conexión de UCM

## Firmar CSR con la CA de Microsoft

1. Vaya a **CSR → Pendiente**
2. Seleccione una CSR y pulse **Firmar**
3. Cambie a la pestaña **Microsoft CA**
4. Seleccione la conexión y la plantilla de certificado
5. Pulse **Firmar**

### Plantillas de aprobación automática
El certificado se devuelve de inmediato y se importa en UCM.

### Plantillas con aprobación de un responsable
UCM guarda la solicitud como **Pendiente** y hace el seguimiento del ID de solicitud de la CA de Microsoft. Abra la CSR en **CSR → Pendiente** y pulse **Verificar estado**: si la CA emitió el certificado (aprobado, por ejemplo, en la consola de la CA de Windows), UCM lo importa en la solicitud; si la CA lo denegó, la solicitud pasa a Denegada; en otro caso sigue Pendiente. Aprobar desde el **panel de control de la CA** también importa el certificado. La **sincronización del inventario** completa las solicitudes pendientes del mismo modo, y las informa como completadas, aparte de los certificados que importa. Una solicitud cuya CSR se firma en otro lugar (una CA local, una importación) se cierra; si sus detalles siguen abiertos, **Verificar estado** muestra *Esta CSR se firmó en otro lugar: su solicitud en Microsoft CA está cerrada*. Un certificado que la CA aún emite para ella entra como un certificado aparte cuando la solicitud se aprueba desde el **panel de control de la CA**, o mediante una sincronización de inventario completa (\`full: true\` en \`POST /api/v2/microsoft-cas/{id}/inventory-sync\`): **Importar de la CA ahora** y la sincronización programada son incrementales y pueden no verlo.

## Inscripción en nombre de (EOBO)

EOBO permite que un agente de inscripción solicite certificados en nombre de otros usuarios. Es habitual en entornos empresariales donde un administrador de PKI gestiona los certificados de los usuarios finales.

### Requisitos previos

- La cuenta de servicio de UCM necesita un **certificado de agente de inscripción** emitido por la CA
- La plantilla de certificado debe tener habilitado el permiso **"Enroll on behalf of other users"**
- La pestaña de seguridad de la plantilla debe conceder al agente de inscripción el derecho de inscribirse

### Usar EOBO en UCM

1. En el diálogo de firma, seleccione la conexión a la CA de Microsoft y la plantilla
2. Marque la casilla **Inscripción en nombre de (EOBO)**
3. Los campos se rellenan a partir de la CSR:
   - **DN del inscrito**: del sujeto de la CSR (p. ej., CN=John Doe,OU=Users,DC=corp,DC=local)
   - **UPN del inscrito**: del correo del SAN de la CSR (p. ej., john.doe@corp.local)
4. Ajuste los valores si hace falta
5. Pulse **Firmar**

UCM los pasa como atributos de solicitud de ADCS:
- EnrolleeObjectName:<DN>: identifica al usuario de destino en AD
- EnrolleePrincipalName:<UPN>: el nombre de inicio de sesión del usuario

### EOBO frente a inscripción directa

| Característica | Inscripción directa | EOBO |
|----------------|---------------------|------|
| Quién firma | El propio usuario | El agente de inscripción en su nombre |
| Clave privada | Equipo del usuario | Puede estar en UCM (modelo CSR) |
| Permiso de plantilla | Inscripción estándar | Requiere derechos de agente de inscripción |
| Caso de uso | Autoservicio | Gestión centralizada de la PKI |

## Ciclo de vida del certificado

### Renovar un certificado de AD CS
La renovación **no** vuelve a firmar localmente (la clave emisora reside en la CA de Windows). UCM reenvía la CSR original del certificado: misma clave, sujeto y SAN, a la conexión y la plantilla que lo emitieron, y actualiza el certificado en su sitio. Si la CA retiene la renovación para la aprobación de un responsable, se sigue como una solicitud pendiente.

### Revocar un certificado de AD CS
AD CS Web Enrollment no tiene un endpoint de revocación. Al revocar un certificado emitido por AD CS:
- **Sin el canal de administración WinRM**: se marca como revocado solo en UCM; la CA de Windows no recibe ningún aviso. Revóquelo también en la CA.
- **Con el canal de administración WinRM**: UCM propaga la revocación a la CA de Windows (certutil -revoke y publicación de la CRL). Levantar un certificateHold propaga también la anulación de la revocación.

## Canal de administración WinRM (opcional)

El canal de administración permite que UCM ejecute en la CA de Windows operaciones de gestión que Web Enrollment no puede: revocar/anular la revocación, publicar la CRL, inventario, y aprobar/denegar solicitudes pendientes. Usa PowerShell remoting y certutil.

### Requisitos
- **WinRM habilitado** en la CA (Enable-PSRemoting; se recomienda un listener HTTPS en 5986)
- El paquete opcional **pywinrm** instalado en UCM (pip install pywinrm)
- Una cuenta autorizada para **gestionar certificados** en la CA ("Issue and Manage Certificates")

### Configuración
1. Edite la conexión y active **Canal de administración**
2. Defina el host (por defecto, el servidor de la conexión), el puerto y el transporte
3. **Transporte**: Kerberos (recomendado, reutiliza el keytab de la conexión) o NTLM, sobre HTTP o HTTPS
4. **Credenciales**: déjelas vacías para reutilizar las propias de la conexión (Basic/Kerberos). Las conexiones mTLS no tienen una credencial WinRM reutilizable: defina una cuenta dedicada
5. Pulse **Probar canal de administración**

| Modo de autenticación de inscripción | ¿Reutiliza las credenciales para WinRM? |
|--------------------------------------|------------------------------------------|
| Kerberos (keytab) | Sí: mismo principal y keytab |
| Basic (usuario y contraseña) | Sí: la contraseña para NTLM/Kerberos |
| Certificado (mTLS) | No: defina una cuenta WinRM dedicada |

## Sincronización de revocaciones por CRL

Active **Sincronizar revocaciones desde la CRL de la CA** en la conexión para que UCM obtenga periódicamente la CRL de la CA y marque como revocados en UCM los certificados revocados en la CA. Es estrictamente unidireccional (de la CA a UCM) y nunca anula la revocación de un certificado revocado en UCM. La URL de la CRL se toma de la conexión o se detecta automáticamente a partir del punto de distribución de CRL de los certificados emitidos, y su firma se verifica con el certificado de la CA antes de aplicar nada. Se ejecuta cada hora, además de la acción **Sincronizar CRL ahora**.

## Sincronización del inventario de la CA

Active **Importar certificados emitidos directamente en la CA** para llevar al almacén de UCM los certificados emitidos fuera de UCM (herramientas nativas, inscripción automática, o anteriores a UCM), de modo que UCM haga el seguimiento de todo el ciclo de vida. Lee la base de datos de la CA con certutil -view, importa los certificados que UCM aún no tiene (deduplicados por número de serie) y es incremental por ID de solicitud (con opción de reexploración completa). Una vista de **conciliación** lista los certificados presentes en la CA pero no en UCM, y viceversa. Se ejecuta cada 6 horas, además de la acción **Importar de la CA ahora**. Requiere el canal de administración WinRM.

## Panel de control de la CA

El panel de control (se abre desde la conexión y requiere el canal de administración) gestiona las solicitudes a la espera de la aprobación del responsable de la CA y muestra el estado de la CA:
- **Solicitudes pendientes**: listar, **Aprobar** (certutil -resubmit; el certificado emitido se importa automáticamente) o **Denegar** (certutil -deny)
- **Estado**: estado del servicio de la CA, caducidad del certificado de la CA, próxima actualización de la CRL y número de solicitudes pendientes

## Solución de problemas

| Problema | Solución |
|----------|----------|
| Falla la prueba de conexión | Verifique el nombre de host, el puerto 443 y que certsrv sea accesible |
| No se encuentran plantillas | Compruebe que la cuenta de UCM tiene permisos de inscripción en la CA |
| EOBO denegado | Verifique el certificado de agente de inscripción y los permisos de la plantilla |
| Solicitud atascada en pendiente | Pulse Verificar estado en la CSR, ejecute una sincronización del inventario, o apruébela desde el panel de control de la CA |
| Falla la prueba del canal de administración | Verifique que WinRM esté habilitado en la CA, el puerto y el transporte, y que pywinrm esté instalado |
| Revocación ausente en la CA | Active el canal de administración WinRM: sin él, la revocación es local a UCM |
| Pendiente no detectado (CA no inglesa) | Corregido en la v2.192. UCM ahora reconoce las páginas de pendiente de AD CS localizadas |

> 💡 Use el botón **Probar conexión** para verificar la autenticación y descubrir las plantillas disponibles antes de firmar. Active el **canal de administración WinRM** para gestionar la revocación, las CRL, el inventario y las solicitudes pendientes directamente desde UCM.
`
  }
}
