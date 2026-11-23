export default {
  helpContent: {
    title: 'TSA',
    subtitle: 'Autoridad de sellado de tiempo',
    overview: 'TSA (RFC 3161) proporciona marcas de tiempo de confianza que prueban que un documento o un hash existía en un momento preciso. Se utiliza para la firma de código, el cumplimiento legal y las pistas de auditoría.',
    sections: [
      {
        title: 'Pestañas',
        items: [
          { label: 'Servicios', text: 'El servicio de sellado de tiempo con su Autoridad, su Hash (los resúmenes que puede llevar una solicitud), su Política y su Estado. Su detalle indica el firmante, la URL /tsa, los totales de solicitudes y el uso de OpenSSL' },
          { label: 'Configuración', text: 'Habilitar servidor TSA, CA de firma, OID de política, certificado de firma y modo estricto, en un formulario con su barra de guardado; Generar un certificado de firma permanece en su sección' },
        ]
      },
      {
        title: 'Configuración',
        items: [
          { label: 'CA de firma', text: 'La CA que emite el certificado de firma dedicado. Su propio certificado firma los tokens de sellado de tiempo solo si no hay un firmante dedicado definido y Requerir un certificado TSA dedicado está desactivado. Una CA fuera de su período de validez no firma: /tsa responde 503. Los verificadores estrictos (openssl ts -verify, jarsigner) rechazan los tokens firmados por un certificado de CA, y la página avisa mientras la CA firma' },
          { label: 'OID de política', text: 'Identificador de objeto de la política TSA, incluido en cada respuesta de sellado de tiempo. El valor por defecto 1.2.3.4.1 es el OID de ejemplo de OpenSSL, un marcador de posición del que la página avisa: usar un OID del arco de la organización' },
          { label: 'Habilitar/Deshabilitar', text: 'Activar o desactivar el punto de acceso TSA sin perder la configuración' },
          { label: 'Requerir un certificado dedicado', text: 'Activado por defecto: rechazar firmar marcas de tiempo con el propio certificado de la CA, de modo que /tsa responde 503 mientras no se defina un certificado de firma de entidad final dedicado con una EKU timeStamping crítica (RFC 3161). Desactivarlo no cumple la RFC 3161; una instalación actualizada desde la 2.x cuya TSA firmaba con su CA lo mantiene desactivado, y la vista general muestra una advertencia' },
          { label: 'Certificado de firma (v2.217)', text: 'Firmar los tokens con un certificado de entidad final dedicado elegido entre los certificados emitidos (EKU timeStamping, clave RSA, ECDSA o ML-DSA en poder de UCM; no se ofrecen los certificados Ed25519 y Ed448, ni ML-DSA en modo FIPS cuando el módulo FIPS no lo aprueba). Las renovaciones se siguen automáticamente; un firmante caducado o revocado hace fallar las solicitudes con 503 y nunca recurre al certificado de la CA' },
          { label: 'Generar un certificado de firma (v2.218)', text: 'Emisión con un clic de un firmante RFC 3161 hecho a propósito: CA:FALSE, KeyUsage solo digitalSignature y una EKU timeStamping crítica y exclusiva, la forma que exigen los verificadores estrictos (openssl ts -verify). Se emite desde la CA TSA configurada y se selecciona automáticamente cuando no hay un firmante utilizable. El certificado tiene el origen "manual": añadir "manual" a los orígenes de renovación automática o renovarlo uno mismo antes de que caduque' },
        ]
      },
      {
        title: 'Uso',
        items: [
          { label: 'Crear una solicitud', text: 'openssl ts -query -data file.txt -sha256 -cert -out request.tsq (-cert pide el certificado del firmante en la respuesta, que openssl ts -verify necesita)' },
          { label: 'Enviar a la TSA', text: 'curl -H "Content-Type: application/timestamp-query" --data-binary @request.tsq https://your-server/tsa -o response.tsr' },
          { label: 'Verificar', text: 'openssl ts -verify -data file.txt -in response.tsr -CAfile ca-chain.pem (firmante dedicado RSA o ECDSA; un token firmado por el certificado de la CA falla con "unsuitable certificate purpose"). Un token ML-DSA falla en openssl ts -verify: comprobar su firma con openssl cms -verify (OpenSSL 3.5 o posterior), y comparar después la huella del mensaje con el hash del archivo' },
        ]
      },
    ],
    tips: [
      'Las marcas de tiempo TSA se utilizan en la firma de código para que las firmas sigan siendo válidas después de que el certificado caduque',
      'El punto de acceso TSA acepta HTTP POST con Content-Type: application/timestamp-query (o application/octet-stream)',
      'Una solicitud con cualquier extensión se rechaza con unacceptedExtension, y una mal formada con badDataFormat (RFC 3161 §2.4.1)',
      'Los tokens llevan genTime en segundos enteros con una precisión declarada de 1 segundo, y la huella del mensaje de la solicitud copiada tal como se envió',
      'Utilizar SHA-256 o algoritmos de hash más fuertes al crear las solicitudes de sellado de tiempo',
      'No se requiere autenticación: el punto de acceso TSA es de acceso público, como CRL/OCSP',
    ],
    warnings: [
      'Debe definirse un certificado de firma dedicado antes de que /tsa firme: generar uno en la configuración',
      'openssl ts -verify y jarsigner rechazan los tokens firmados por el certificado de la CA: la RFC 3161 exige un firmante dedicado con una EKU timeStamping crítica y exclusiva. Generar uno en la configuración',
      'El punto de acceso TSA es un punto de acceso de protocolo público: no incluir datos sensibles en las solicitudes de sellado de tiempo',
    ],
  },
  helpGuides: {
    title: 'Protocolo TSA',
    content: `
## Visión general

La autoridad de sellado de tiempo (TSA) implementa la **RFC 3161** para proporcionar marcas de tiempo de confianza que prueban criptográficamente que un documento, un hash o una firma digital existía en un momento preciso. TSA se utiliza ampliamente en la firma de código, el cumplimiento legal, el archivado a largo plazo y las pistas de auditoría.

## Cómo funciona

1. **El cliente crea una solicitud de sellado de tiempo**: calcula el hash de un archivo con SHA-256/SHA-512 y crea un \`TimeStampReq\` (codificado en ASN.1 DER)
2. **El cliente envía la solicitud a la TSA**: HTTP POST al punto de acceso \`/tsa\` con \`Content-Type: application/timestamp-query\`
3. **UCM firma la marca de tiempo**: el certificado de firma dedicado firma el hash y la hora actual en un \`TimeStampResp\`. El certificado propio de la CA configurada solo firma cuando **Requerir un certificado TSA dedicado** está desactivado
4. **El cliente recibe y guarda la respuesta**: el archivo \`.tsr\` puede probar después que el documento existía en ese momento

## Configuración

### Configuración

1. **Habilitar servidor TSA**: activar o desactivar el servidor TSA
2. **CA de firma**: seleccionar qué autoridad de certificación firma los tokens de sellado de tiempo
3. **OID de política**: identificador de objeto de la política TSA, incluido en cada respuesta de sellado de tiempo
4. **Requerir un certificado TSA dedicado**: activado por defecto: rechazar firmar marcas de tiempo con el propio certificado de la CA, de modo que \`/tsa\` responde 503 mientras no se defina un certificado de firma de entidad final dedicado con una **EKU timeStamping crítica** (RFC 3161). **Generar un certificado de firma** emite uno desde la CA de firma y lo selecciona. Desactivar la opción permite que firme el certificado de la CA, lo que no cumple la RFC 3161; una instalación actualizada desde la 2.x cuya TSA firmaba con su CA la mantiene desactivada, y la vista general muestra una advertencia

### Elegir una CA de firma

La clave privada de la CA de firma se usa para firmar cada token de sellado de tiempo. Buenas prácticas:

- Usar una **sub-CA dedicada** para el sellado de tiempo en lugar de la CA raíz
- La RFC 3161 §2.3 exige un firmante cuya única EKU, crítica, sea **id-kp-timeStamping** (OID 1.3.6.1.5.5.7.3.8), algo que un certificado de CA no puede llevar sin perder sus demás usos. Los tokens firmados por el certificado de la CA son rechazados por los verificadores estrictos: \`openssl ts -verify\` falla con "unsuitable certificate purpose" y jarsigner con "Certificate is not valid for timestamping". La configuración avisa mientras firma el certificado de la CA: **generar un certificado de firma dedicado** allí para estos clientes
- Asegurar que el certificado de la CA tenga **validez suficiente**: las marcas de tiempo deben seguir siendo verificables durante años. Una CA fuera de su período de validez no firma: \`/tsa\` responde 503
- Mantener activado **Requerir un certificado TSA dedicado** para imponerlo en el momento de la firma

### OID de política

El OID de política identifica la política TSA bajo la cual se emiten las marcas de tiempo. Se incluye en cada \`TimeStampResp\`.

- Por defecto: \`1.2.3.4.1\` (marcador de posición: el OID de ejemplo de OpenSSL, asignado a nadie; la configuración avisa mientras se usa)
- En producción, registrar un OID bajo el arco de la organización o usar uno de su CP/CPS

## Punto de acceso

El detalle del servicio muestra:

- **URL del punto de acceso TSA**: URL lista para copiar y pegar en la configuración del cliente
- **Ejemplos de uso**: comandos OpenSSL para crear solicitudes, enviarlas y verificar las respuestas
- **Estadísticas**: total de solicitudes de sellado de tiempo procesadas (correctas y fallidas); cada solicitud rechazada se audita como \`tsa.timestamp_rejected\` con su código de fallo

## Ejemplos de uso

### Crear una solicitud de sellado de tiempo

\`\`\`bash
# Calcular el hash de un archivo y crear una solicitud de marca de tiempo (-cert: incluir el certificado del firmante)
openssl ts -query -data file.txt -sha256 -cert -out request.tsq
\`\`\`

### Enviar la solicitud a la TSA

\`\`\`bash
# Enviar la solicitud y recibir una respuesta de marca de tiempo
curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @request.tsq \\
  https://your-server:8443/tsa -o response.tsr
\`\`\`

### Verificar una marca de tiempo

\`\`\`bash
# Verificar la respuesta de marca de tiempo con el archivo original
openssl ts -verify -data file.txt -in response.tsr \\
  -CAfile ca-chain.pem
\`\`\`

\`openssl ts -verify\` necesita un certificado de firma dedicado (un token firmado por el certificado de la CA falla) y solo comprueba tokens RSA y ECDSA. Un token ML-DSA se verifica con \`openssl cms -verify\` (OpenSSL 3.5 o posterior); después, comparar su huella del mensaje con el hash del archivo.

### Firma de código con marcas de tiempo

Al firmar código, añadir la URL de la TSA para que las firmas sigan siendo válidas después de que el certificado caduque. Configurar antes un certificado de firma dedicado: jarsigner rechaza un token firmado por el certificado de la CA ("Certificate is not valid for timestamping").

\`\`\`bash
# Firmar con marca de tiempo (osslsigncode)
osslsigncode sign -certs cert.pem -key key.pem \\
  -ts https://your-server:8443/tsa \\
  -in app.exe -out app-signed.exe

# Firmar con marca de tiempo (signtool.exe en Windows)
signtool sign /fd SHA256 /tr https://your-server:8443/tsa \\
  /td SHA256 /f cert.pfx app.exe
\`\`\`

### Marcas de tiempo de documentos PDF

\`\`\`bash
# Crear una marca de tiempo separada para un PDF
openssl ts -query -data document.pdf -sha256 -cert \\
  -out document.tsq

curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @document.tsq \\
  https://your-server:8443/tsa -o document.tsr
\`\`\`

## Detalles del protocolo

| Propiedad | Valor |
|----------|-------|
| RFC | 3161 (Internet X.509 PKI TSP) |
| Punto de acceso | \`/tsa\` (POST) |
| Content-Type | \`application/timestamp-query\` |
| Tipo de respuesta | \`application/timestamp-reply\` |
| Algoritmos de hash | SHA-256, SHA-384, SHA-512 (SHA-1 y MD5 rechazados con badAlg) |
| Extensiones de la solicitud | Ninguna aceptada: cualquier extensión, crítica o no, se rechaza con unacceptedExtension |
| Solicitud mal formada | badDataFormat (incluidos los bytes sobrantes) |
| genTime / precisión | Segundos enteros, precisión de 1 segundo |
| Huella del mensaje | Copiada de la solicitud tal como se envió |
| Autenticación | Ninguna (punto de acceso público) |
| Transporte | HTTP o HTTPS |

## Consideraciones de seguridad

- El punto de acceso TSA es **público**: no se requiere autenticación (igual que CRL/OCSP)
- Cada respuesta de sellado de tiempo está **firmada** por el firmante dedicado o la clave de la CA: los clientes verifican la firma para asegurar la autenticidad
- Usar algoritmos de hash **SHA-256 o más fuertes** al crear las solicitudes (SHA-1 se rechaza)
- La TSA **no** ve el documento original: solo se transmite el hash
- Considerar una **limitación de tasa** si el punto de acceso TSA está expuesto a internet

> 💡 Las marcas de tiempo son esenciales para la firma de código: garantizan que el software firmado siga siendo de confianza incluso después de que caduque el certificado de firma.
`
  }
}
