export default {
  helpContent: {
    title: 'Solicitudes de firma de certificado',
    subtitle: 'Gestionar el flujo de trabajo de CSR',
    overview: 'Cargue, revise y firme solicitudes de firma de certificado. Los CSR permiten a los sistemas externos solicitar certificados de sus CA sin exponer las claves privadas.',
    sections: [
      {
        title: 'Flujo de trabajo',
        items: [
          { label: 'Generar CSR', text: 'Crear un nuevo CSR con par de claves directamente en UCM: RSA, EC, Brainpool o ML-DSA-44/65/87' },
          { label: 'Cargar CSR', text: 'Aceptar archivos CSR codificados en PEM o pegar texto PEM' },
          { label: 'Revisar', text: 'Inspeccionar el sujeto, SAN, tipo de clave y firma antes de firmar' },
          { label: 'Firmar', text: 'Seleccionar una CA, tipo de certificado, establecer el período de validez y emitir el certificado' },
          { label: 'Añadir nombres', text: 'Al firmar, añada nombres de correo, DNS, IP o URI a los de la solicitud, por ejemplo la dirección de correo de un certificado S/MIME solicitado desde una tarjeta inteligente. Pasan por las restricciones de nombres de la CA, las políticas de emisión y la aprobación como cualquier otro' },
          { label: 'Firmar de nuevo', text: 'En Historial, devuelva una solicitud firmada a Pendientes para firmarla otra vez con otros EKU, nombres o validez, sin generar una clave nueva' },
          { label: 'Descargar', text: 'Descargar el CSR original en formato PEM' },
          { label: 'Descargar clave', text: 'Descargar la clave privada de un CSR generado en UCM, para desplegarla junto a un certificado emitido por una CA externa (requiere el permiso read:private_keys)' },
        ]
      },
      {
        title: 'Pestañas',
        items: [
          { label: 'Pendientes', text: 'CSR en espera de revisión y firma' },
          { label: 'Historial', text: 'Solicitudes firmadas con su certificado: descargue uno u otro, o firme la solicitud de nuevo. Ambas pestañas paginan, buscan y ordenan sobre todas las solicitudes; Historial también busca por CA firmante' },
        ]
      },
    ],
    tips: [
      'Los CSR preservan la clave privada del solicitante: nunca sale de su sistema',
      'Subir Clave adjunta una clave privada a un CSR pendiente, de modo que el certificado firmado pueda exportarse como PKCS#12',
      'Un certificado importado para un CSR generado en UCM completa ese CSR: el registro conserva su clave privada, por lo que el certificado se exporta con ella',
      'Utilice el modo Microsoft CA para firmar CSR a través de AD CS cuando esté conectado a una PKI Windows',
      'Un certificado para una clave ML-DSA conserva solo los bits de firma: keyEncipherment, dataEncipherment y keyAgreement pedidos por la plantilla se eliminan, y el resultado lo indica',
      'Un CSR generado con related_to (API, requiere read:private_keys) nombra un certificado existente A: al firmarlo se emite un certificado vinculado a A (RFC 9763), rechazado si declara un key usage o EKU que A no tenga',
      'Al firmar, use "EKU adicionales" para añadir Microsoft RDP, smartcard logon, IPsec o cualquier OID: el EKU existente del CSR se reconstruye con el conjunto fusionado',
      'Cuando una política o la expiración de la CA emisora acorta la validez solicitada, el resultado lo indica: "Issued for N day(s) instead of the M requested", con el motivo',
    ],
  },
  helpGuides: {
    title: 'Solicitudes de firma de certificado',
    content: `
## Descripción general

Las solicitudes de firma de certificado (CSR) permiten a los sistemas externos solicitar certificados sin exponer sus claves privadas. El CSR contiene la clave pública y la información del sujeto; la clave privada permanece con el solicitante.

## Pestañas

### Pendientes
CSR en espera de revisión y firma. Los nuevos CSR aparecen aquí tras la carga.

### Historial
Solicitudes firmadas, cada una con el certificado que produjo. **Descargar certificado** y **Descargar CSR** obtienen uno u otro, y **Firmar de nuevo** devuelve la solicitud a Pendientes.

## Generar un CSR

UCM puede generar un CSR y un par de claves directamente:

1. Haga clic en **Generar CSR**
2. Complete los campos del sujeto (CN obligatorio)
3. Añada nombres alternativos del sujeto si es necesario
4. Seleccione el tipo y tamaño de clave (RSA 2048/4096, ECDSA P-256/P-384/P-521, Brainpool, ML-DSA-44/65/87)
5. Haga clic en **Generar**

El CSR y la clave privada se crean y almacenan en UCM. El CSR aparece en la pestaña Pendientes listo para firmar.

> 💡 Esto es conveniente cuando desea que UCM gestione todo el ciclo de vida. CSR, firma y almacenamiento de claves.

Un certificado firmado para una clave **ML-DSA** conserva solo los bits de firma: keyEncipherment, dataEncipherment y keyAgreement pedidos por la plantilla se eliminan, y el resultado indica lo que se eliminó.

### Solicitudes de certificado relacionado (RFC 9763)

Mediante la API, \`related_to\` nombra un certificado existente **A** cuya clave privada conserva UCM; requiere el permiso \`read:private_keys\` y cada uso de la clave de A queda auditado. El CSR generado incluye entonces una **relatedCertRequest** firmada por la clave de A. Al firmarlo se emite un certificado vinculado a A, segundo miembro de un par híbrido, que se revoca y renueva junto con A. La firma se rechaza si A está revocado, expirado o no es de entidad final, o si el nuevo certificado declara un key usage o EKU que A no tenga.

## Cargar un CSR

1. Haga clic en **Cargar CSR**
2. Pegue texto PEM o suba un archivo PEM
3. UCM valida la firma del CSR y muestra los detalles
4. El CSR aparece en la pestaña Pendientes

## Revisar un CSR

Haga clic en un CSR para ver:
- **Sujeto**: CN, O, OU, C, etc.
- **SAN**: Nombres DNS, direcciones IP, correos electrónicos
- **Información de clave**: Algoritmo, tamaño, huella digital de la clave pública
- **Firma**: Algoritmo y validez

## Firmar un CSR

### Firma con CA local

1. Seleccione un CSR pendiente
2. Haga clic en **Firmar**
3. Elija la **CA de firma** (debe poseer una clave privada)
4. Seleccione el **tipo de certificado** (servidor, cliente, firma de código, correo electrónico)
5. Establezca el **período de validez** en días
6. Opcionalmente **Añadir nombres** (correo, DNS, IP, URI) a los de la solicitud
7. Haga clic en **Firmar**

En modo Microsoft CA, se elige la plantilla AD CS en lugar del tipo de certificado.

El certificado resultante aparece en la página de Certificados.

> 💡 Una solicitud generada en una tarjeta inteligente suele llevar solo un CN. Para un certificado S/MIME, elija el tipo «Email (S/MIME)» y añada la dirección: pasa a ser el nombre alternativo del sujeto del certificado. Los nombres añadidos pasan por las restricciones de nombres de la CA, las políticas de emisión y la aprobación como cualquier otro, y el aprobador los ve.

### Firma con Microsoft CA

Si hay conexiones de Microsoft CA configuradas, aparece una pestaña **Microsoft CA** en el diálogo de firma:

1. Seleccione un CSR pendiente y haga clic en **Firmar**
2. Cambie a la pestaña **Microsoft CA**
3. Seleccione la **conexión MS CA**
4. Seleccione la **plantilla de certificado** (cargada automáticamente desde la CA)
5. Haga clic en **Firmar**

Si la plantilla requiere aprobación del administrador, UCM rastrea la solicitud pendiente. Consulte su estado desde el panel de detalles del CSR.

### Inscripción en nombre de otro (EOBO)

Al firmar mediante Microsoft CA, puede inscribirse en nombre de otro usuario:

1. Seleccione la conexión MS CA y la plantilla
2. Marque **Inscripción en nombre de otro (EOBO)**
3. Los campos **DN del inscrito** y **UPN del inscrito** se rellenan automáticamente desde el sujeto del CSR y el correo electrónico del SAN
4. Ajuste los valores si es necesario y haga clic en **Firmar**

> ⚠️ EOBO requiere un certificado de agente de inscripción configurado en el servidor AD CS, y la plantilla debe permitir la inscripción en nombre de otros usuarios.

### Firma con CA externa

Para un certificado de una CA pública o de terceros, conserve la clave en UCM y envíe solo la solicitud:

1. **Generar CSR** en UCM, luego **Descargar CSR** y envíelo a la CA externa
2. Cuando llegue el certificado, impórtelo en la página de Certificados (**Importar**, archivo o PEM pegado) o mediante **Operaciones → Smart Importar**
3. UCM reconoce el certificado por su clave pública, completa el CSR pendiente y conserva su clave privada: el certificado se exporta entonces con la clave (PEM, PKCS#12, JKS) como cualquier otro

El CSR pasa de **Pendientes** a **Historial**. Si el certificado debe instalarse en otro lugar, **Descargar Clave Privada** en el CSR pendiente proporciona la clave (requiere el permiso read:private_keys, como toda exportación directa de clave).

> 💡 La correspondencia se realiza sobre el par de claves, por lo que sigue funcionando cuando la CA reescribe el sujeto (muchas CA públicas conservan solo el CN).

## Firmar una solicitud de nuevo

Un dispositivo que conserva su clave, como una tarjeta inteligente, a menudo no puede producir dos veces la misma solicitud. En **Historial**, **Firmar de nuevo** devuelve la solicitud almacenada a **Pendientes**, con la misma clave pública, para firmarla otra vez con otros EKU, nombres o validez. El certificado ya emitido no se modifica: revóquelo si ya no debe usarse.

> 💡 La renovación sigue rechazada para un certificado cuya clave privada UCM no posee, ya que revocaría el número de serie que el dispositivo sigue presentando.

## Añadir una clave privada

Antes de firmar, **Subir Clave** adjunta la clave privada a un CSR pendiente, de modo que el certificado firmado pueda exportarse como PKCS#12. Una solicitud firmada ya no ofrece esta acción.

> 💡 Esto es útil cuando el solicitante envía tanto el CSR como la clave de forma segura.

## Eliminar CSR

Eliminar quita un CSR pendiente de UCM. Una solicitud firmada es su certificado: se elimina desde la página Certificados, no desde aquí.
`
  }
}
