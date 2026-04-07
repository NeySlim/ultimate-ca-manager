export default {
  helpContent: {
    title: 'Solicitudes de firma de certificado',
    subtitle: 'Gestionar el flujo de trabajo de CSR',
    overview: 'Cargue, revise y firme solicitudes de firma de certificado. Los CSR permiten a los sistemas externos solicitar certificados de sus CA sin exponer las claves privadas.',
    sections: [
      {
        title: 'Flujo de trabajo',
        items: [
          { label: 'Generar CSR', text: 'Crear un nuevo CSR con par de claves directamente en UCM' },
          { label: 'Cargar CSR', text: 'Aceptar archivos CSR codificados en PEM o pegar texto PEM' },
          { label: 'Revisar', text: 'Inspeccionar el sujeto, SAN, tipo de clave y firma antes de firmar' },
          { label: 'Firmar', text: 'Seleccionar una CA, tipo de certificado, establecer el período de validez y emitir el certificado' },
          { label: 'Descargar', text: 'Descargar el CSR original en formato PEM' },
        ]
      },
      {
        title: 'Pestañas',
        items: [
          { label: 'Pendientes', text: 'CSR en espera de revisión y firma' },
          { label: 'Historial', text: 'CSR previamente firmados o rechazados' },
        ]
      },
    ],
    tips: [
      'Los CSR preservan la clave privada del solicitante — nunca sale de su sistema',
      'Puede añadir una clave privada a un CSR después de firmarlo si es necesario para la exportación PKCS#12',
      'Utilice el modo Microsoft CA para firmar CSR a través de AD CS cuando esté conectado a una PKI Windows',
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
CSR previamente firmados o rechazados, con enlaces a los certificados resultantes.

## Generar un CSR

UCM puede generar un CSR y un par de claves directamente:

1. Haga clic en **Generar CSR**
2. Complete los campos del sujeto (CN obligatorio)
3. Añada nombres alternativos del sujeto si es necesario
4. Seleccione el tipo y tamaño de clave (RSA 2048/4096, ECDSA P-256/P-384)
5. Haga clic en **Generar**

El CSR y la clave privada se crean y almacenan en UCM. El CSR aparece en la pestaña Pendientes listo para firmar.

> 💡 Esto es conveniente cuando desea que UCM gestione todo el ciclo de vida — CSR, firma y almacenamiento de claves.

## Cargar un CSR

1. Haga clic en **Cargar CSR**
2. Pegue texto PEM o suba un archivo PEM/DER
3. UCM valida la firma del CSR y muestra los detalles
4. El CSR aparece en la pestaña Pendientes

## Revisar un CSR

Haga clic en un CSR para ver:
- **Sujeto** — CN, O, OU, C, etc.
- **SAN** — Nombres DNS, direcciones IP, correos electrónicos
- **Información de clave** — Algoritmo, tamaño, huella digital de la clave pública
- **Firma** — Algoritmo y validez

## Firmar un CSR

### Firma con CA local

1. Seleccione un CSR pendiente
2. Haga clic en **Firmar**
3. Elija la **CA de firma** (debe poseer una clave privada)
4. Seleccione el **tipo de certificado** (servidor, cliente, firma de código, correo electrónico)
5. Establezca el **período de validez** en días
5. Opcionalmente aplique una plantilla para el uso de clave y extensiones
6. Haga clic en **Firmar**

El certificado resultante aparece en la página de Certificados.

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

## Añadir una clave privada

Después de firmar, puede adjuntar una clave privada al certificado para la exportación PKCS#12. Haga clic en **Añadir clave** en el certificado firmado.

> 💡 Esto es útil cuando el solicitante envía tanto el CSR como la clave de forma segura.

## Eliminar CSR

Eliminar quita el CSR de UCM. Si el CSR ya fue firmado, el certificado resultante no se ve afectado.
`
  }
}
