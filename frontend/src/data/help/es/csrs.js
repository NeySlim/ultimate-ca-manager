export default {
  helpContent: {
    title: 'Solicitudes de firma de certificado',
    subtitle: 'Gestionar el flujo de las CSR',
    overview: 'Subir, revisar y firmar solicitudes de firma de certificado. Las CSR permiten que sistemas externos soliciten certificados a sus CA sin exponer las claves privadas.',
    sections: [
      {
        title: 'Flujo de trabajo',
        items: [
          { label: 'Generar CSR', text: 'Crear una CSR nueva con su par de claves directamente en UCM: RSA, EC, Brainpool o ML-DSA-44/65/87' },
          { label: 'Subir CSR', text: 'Aceptar archivos de CSR codificados en PEM o pegar el texto PEM' },
          { label: 'Revisar', text: 'Inspeccionar el sujeto, los SAN, el tipo de clave y la firma antes de firmar' },
          { label: 'Firmar', text: 'Seleccionar una CA y un tipo de certificado, fijar el período de validez y emitir el certificado' },
          { label: 'Comprobaciones de la solicitud', text: 'El sujeto y los nombres de la solicitud se someten a las reglas del formulario de emisión: CN de 64 caracteres como máximo, C de dos letras, nombres DNS con la sintaxis de la RFC 5280 (sin espacio, guion bajo, punto final, dirección IP, última etiqueta solo numérica ni comodín más allá de la primera etiqueta). Un CN con sintaxis de nombre DNS da un nombre DNS (una sola etiqueta solo para un certificado de servidor o de dispositivo, ninguno para S/MIME); otro no da ninguno, con un aviso cuando el CN de un servidor parece un host. Una sub-CA no recibe ninguno, y un emailAddress válido en el sujeto se añade al SAN. Cada rechazo indica su motivo' },
          { label: 'Añadir nombres', text: 'Al firmar, añadir nombres de correo, DNS, IP o URI a los de la solicitud, por ejemplo la dirección de correo de un certificado S/MIME solicitado desde una tarjeta inteligente. Pasan por las restricciones de nombres de la CA, las políticas de emisión y la aprobación como cualquier otro' },
          { label: 'Firmar de nuevo', text: 'En Historial, volver a poner una solicitud firmada en Pendiente para firmarla otra vez con otros EKU, nombres o validez, sin generar una clave nueva' },
          { label: 'Descargar', text: 'Descargar la CSR original en formato PEM' },
          { label: 'Descargar clave', text: 'Descargar la clave privada de una CSR generada en UCM, para desplegarla junto a un certificado emitido por una CA externa (requiere el permiso read:private_keys)' },
        ]
      },
      {
        title: 'Estados',
        items: [
          { label: 'Pendiente', text: 'CSR a la espera de revisión y firma' },
          { label: 'Firmada', text: 'Solicitudes firmadas con su certificado: descargue uno u otra, o firme la solicitud de nuevo. Ambas listas paginan, buscan y ordenan sobre todas las solicitudes; la de firmadas busca también por CA firmante' },
          { label: 'Detalle', text: 'El nombre de una solicitud abre su detalle bajo la lista: Resumen (sujeto, solicitante, clave, estado), Detalles (campos del sujeto, nombres) y PEM. Firmar y Descargar son sus botones; la clave, Verificar estado, Firmar de nuevo, Regenerar clave y Eliminar están en su menú ⋯' },
        ]
      },
    ],
    tips: [
      'Las CSR preservan la clave privada del solicitante: nunca sale de su sistema',
      'Subir Clave adjunta una clave privada a una CSR pendiente, de modo que el certificado firmado pueda exportarse como PKCS#12',
      'Un certificado importado para una CSR generada en UCM completa esa CSR: el registro conserva su clave privada, por lo que el certificado se exporta con ella',
      'Use el modo CA de Microsoft para firmar CSR mediante AD CS cuando esté conectado a una PKI de Windows',
      'Un certificado para una clave ML-DSA conserva solo los bits de firma: keyEncipherment, dataEncipherment y keyAgreement pedidos por la plantilla se eliminan, y el resultado lo indica',
      'Una CSR generada con related_to (API, requiere read:private_keys) nombra un certificado existente A: firmarla emite un certificado vinculado a A (RFC 9763), rechazado si declara un uso de clave o EKU que A no tiene',
      'Al firmar, use «Usos de clave adicionales» para añadir Microsoft RDP, smartcard logon, IPsec o cualquier otro OID con puntos: el EKU existente de la CSR se reconstruye con el conjunto fusionado',
      'Cuando una política o la caducidad de la CA emisora acorta la validez solicitada, el resultado lo indica: "Issued for N day(s) instead of the M requested", con el motivo',
    ],
  },
  helpGuides: {
    title: 'Solicitudes de firma de certificado',
    content: `
## Descripción general

Las solicitudes de firma de certificado (CSR) permiten que sistemas externos soliciten certificados sin exponer sus claves privadas. La CSR contiene la clave pública y la información del sujeto; la clave privada permanece en poder del solicitante.

## Estados

Los chips situados sobre la lista alternan entre las dos listas, cada una con su recuento.

### Pendiente
CSR a la espera de revisión y firma. Las CSR nuevas aparecen aquí tras subirlas.

### Firmada
Solicitudes firmadas, cada una con el certificado que produjo. **Descargar certificado** y, en el menú **⋯**, **Descargar CSR** obtienen uno u otra, y **Firmar de nuevo** devuelve la solicitud a Pendiente.

## Generar una CSR

UCM puede generar directamente una CSR y su par de claves:

1. Pulse **Generar CSR**
2. Rellene los campos del sujeto (CN obligatorio)
3. Añada nombres alternativos del sujeto si hace falta
4. Seleccione el tipo y el tamaño de clave (RSA 2048/4096, ECDSA P-256/P-384/P-521, Brainpool, ML-DSA-44/65/87)
5. Pulse **Generar**

La CSR y la clave privada se crean y se almacenan en UCM. La CSR aparece en la pestaña Pendiente, lista para firmar.

> 💡 Es práctico cuando se quiere que UCM gestione todo el ciclo de vida: CSR, firma y almacenamiento de claves.

Un certificado firmado para una clave **ML-DSA** conserva solo los bits de firma: keyEncipherment, dataEncipherment y keyAgreement pedidos por la plantilla se eliminan, y el resultado indica lo que se quitó.

### Solicitudes de certificado relacionado (RFC 9763)

Mediante la API, \`related_to\` nombra un certificado existente **A** cuya clave privada conserva UCM; requiere el permiso \`read:private_keys\`, y cada uso de la clave de A queda auditado. La CSR generada lleva entonces una **relatedCertRequest** firmada con la clave de A. Firmarla emite un certificado vinculado a A, segundo miembro de un par híbrido, que se revoca y renueva con A. La firma se rechaza cuando A está revocado, caducado o no es un certificado de entidad final, o cuando el nuevo certificado declara un uso de clave o EKU que A no tiene.

## Subir una CSR

1. Pulse **Subir CSR**
2. Pegue el texto PEM o suba un archivo PEM
3. UCM valida la firma de la CSR y muestra los detalles
4. La CSR aparece en la pestaña Pendiente

## Revisar una CSR

Pulse el nombre de una solicitud: su detalle se abre bajo la lista, con:
- **Sujeto**: CN, O, OU, C, etc.
- **SAN**: nombres DNS, direcciones IP, correos
- **Información de la clave**: algoritmo, tamaño, huella de la clave pública
- **Firma**: algoritmo y validez

## Firmar una CSR

### Firma con una CA local

1. Seleccione una CSR pendiente
2. Pulse **Firmar**
3. Elija la **CA firmante** (debe tener una clave privada)
4. Seleccione el **Tipo de certificado** (servidor, cliente, firma de código, correo)
5. Fije el **período de validez** en días
6. Opcionalmente, **Añada nombres** (correo, DNS, IP, URI) a los de la solicitud
7. Pulse **Firmar**

En el modo CA de Microsoft, se elige la plantilla de AD CS en lugar del tipo de certificado.

El certificado resultante aparece en la página Certificados.

> 💡 Una solicitud generada en una tarjeta inteligente suele llevar solo un CN. Para un certificado S/MIME, elija el tipo Correo y añada la dirección: pasa a ser el nombre alternativo del sujeto del certificado. Los nombres añadidos pasan por las restricciones de nombres de la CA, las políticas de emisión y la aprobación como cualquier otro, y quien aprueba los ve.

Lo que una solicitud puede llevar se comprueba como en el formulario de emisión, y un rechazo indica su motivo:
- **Sujeto**: CN, O y OU de 64 caracteres como máximo, L y ST de 128, C un código de país de dos letras como PrintableString (RFC 5280, apéndice A)
- **Nombres DNS**: letras, dígitos y guiones en etiquetas separadas por puntos (sin guion bajo), un comodín solo como primera etiqueta completa, sin punto final, una última etiqueta no solo numérica, nunca una dirección IP. Un nombre internacionalizado escrito en el formulario se emite como su A-label (\`xn--\`)
- **Nombres a partir del CN**: una solicitud sin SAN recibe un nombre DNS de su CN solo cuando el CN tiene sintaxis de nombre DNS (nunca \`John Doe\`); una sola etiqueta como \`intranet\` cuenta únicamente para un certificado de servidor o de dispositivo, no para cliente, correo o firma de código, y un certificado de correo (S/MIME) no recibe ninguno, ni siquiera de un CN con puntos como \`john.doe\`; un CN de servidor con aspecto de host que no da ninguno se nombra en un aviso, y una sub-CA no recibe ninguno
- **Correo en el sujeto**: un emailAddress válido se añade también al SAN como nombre de correo, para todos los tipos de certificado
- **Uso de clave**: una solicitud sin uso de clave recibe el de su tipo, como en el formulario de emisión (cliente, firma de código y correo incluidos)
- Una CA padre con pathLen 0, o un nombre fuera de las restricciones de nombres de la CA, se rechaza indicando ese motivo; el CN con puntos de un certificado de correo se comprueba como nombre DNS solo cuando el certificado lleva también Server Auth

### Firma con una CA de Microsoft

Si hay conexiones a una CA de Microsoft configuradas, aparece una pestaña **Microsoft CA** en el diálogo de firma:

1. Seleccione una CSR pendiente y pulse **Firmar**
2. Cambie a la pestaña **Microsoft CA**
3. Seleccione la **conexión a la CA de Microsoft**
4. Seleccione la **plantilla de certificado** (se carga automáticamente desde la CA)
5. Pulse **Firmar**

Si la plantilla exige la aprobación de un responsable, la solicitud permanece Pendiente en UCM. Ábrala en **Pendiente** y pulse **Verificar estado** en su menú **⋯** para obtener el certificado una vez que la CA lo haya emitido (requiere también el permiso para firmar CSR), o apruébela desde el panel de control de la CA de la conexión.

### Inscripción en nombre de (EOBO)

Al firmar mediante una CA de Microsoft, se puede inscribir en nombre de otro usuario:

1. Seleccione la conexión a la CA de Microsoft y la plantilla
2. Marque **Inscripción en nombre de (EOBO)**
3. Los campos **DN del inscrito** y **UPN del inscrito** se rellenan solos con el sujeto de la CSR y el correo del SAN
4. Ajuste los valores si hace falta y pulse **Firmar**

> ⚠️ EOBO requiere un certificado de agente de inscripción configurado en el servidor AD CS, y la plantilla debe permitir la inscripción en nombre de otros usuarios.

### Firma con una CA externa

Para un certificado de una CA pública o de terceros, conserve la clave en UCM y envíe solo la solicitud:

1. **Genere la CSR** en UCM, luego **Descargue la CSR** y envíela a la CA externa
2. Cuando vuelva el certificado, impórtelo en la página Certificados (**Importar**, archivo o PEM pegado) o mediante **Operaciones → Smart Importar**
3. UCM reconoce el certificado por su clave pública, completa la CSR pendiente y conserva su clave privada: el certificado se exporta entonces con la clave (PEM, PKCS#12, JKS) como cualquier otro

La CSR pasa de **Pendiente** a **Historial**. Si el certificado debe instalarse en otro lugar, **Descargar Clave Privada** en la CSR pendiente proporciona la clave (requiere el permiso read:private_keys, como toda exportación directa de claves).

> 💡 La coincidencia se hace por el par de claves, por lo que sigue funcionando cuando la CA reescribe el sujeto (muchas CA públicas conservan solo el CN).

## Firmar una solicitud de nuevo

Un dispositivo que conserva su clave, como una tarjeta inteligente, a menudo no puede producir dos veces la misma solicitud. En **Historial**, **Firmar de nuevo** devuelve la solicitud almacenada a **Pendiente**, con la misma clave pública, para firmarla otra vez con otros EKU, nombres o validez. El certificado ya emitido se deja como está: revóquelo si ya no debe usarse.

> 💡 La renovación sigue rechazándose para un certificado cuya clave privada UCM no conserva, porque revocaría el número de serie que el dispositivo aún presenta.

## Añadir una clave privada

Antes de firmar, **Subir Clave** (en el menú **⋯** de la solicitud) adjunta la clave privada a una CSR pendiente, de modo que el certificado firmado pueda exportarse como PKCS#12. Una solicitud firmada ya no ofrece esta acción.

> 💡 Es útil cuando el solicitante envía de forma segura tanto la CSR como la clave.

## Eliminar CSR

Eliminar quita de UCM una CSR pendiente. Una solicitud firmada es su certificado: se elimina desde la página Certificados, no desde aquí.
`
  }
}
