export default {
  helpContent: {
    title: 'TSA',
    subtitle: 'Time Stamp Authority',
    overview: 'TSA (RFC 3161) proporciona marcas de tiempo confiables que demuestran que un documento o hash existía en un momento específico. Se utiliza para firma de código, cumplimiento legal y trazabilidad de auditoría.',
    sections: [
      {
        title: 'Pestañas',
        items: [
          { label: 'Configuración', text: 'Activar TSA, seleccionar la CA firmante y configurar el OID de política TSA' },
          { label: 'Información', text: 'URL del endpoint TSA, ejemplos de uso con OpenSSL y estadísticas de solicitudes' },
        ]
      },
      {
        title: 'Configuración',
        items: [
          { label: 'CA firmante', text: 'La CA cuya clave privada firma los tokens de marca de tiempo — debe ser una CA válida y no expirada' },
          { label: 'OID de política', text: 'Identificador de objeto para la política TSA (ej., 1.2.3.4.1) — incluido en cada respuesta de marca de tiempo' },
          { label: 'Activar/Desactivar', text: 'Alternar el endpoint TSA sin perder la configuración' },
        ]
      },
      {
        title: 'Uso',
        items: [
          { label: 'Crear solicitud', text: 'openssl ts -query -data file.txt -sha256 -no_nonce -out request.tsq' },
          { label: 'Enviar a TSA', text: 'curl -H "Content-Type: application/timestamp-query" --data-binary @request.tsq https://your-server/tsa -o response.tsr' },
          { label: 'Verificar', text: 'openssl ts -verify -data file.txt -in response.tsr -CAfile ca-chain.pem' },
        ]
      },
    ],
    tips: [
      'Las marcas de tiempo TSA se usan en la firma de código para asegurar que las firmas sigan siendo válidas después de la expiración del certificado',
      'El endpoint TSA acepta HTTP POST con Content-Type: application/timestamp-query',
      'Use SHA-256 o algoritmos de hash más fuertes al crear solicitudes de marca de tiempo',
      'No se requiere autenticación — el endpoint TSA es de acceso público como CRL/OCSP',
    ],
    warnings: [
      'Se debe configurar una CA firmante válida antes de activar TSA',
      'El endpoint TSA es un endpoint de protocolo público — no incluya datos sensibles en las solicitudes de marca de tiempo',
    ],
  },
  helpGuides: {
    title: 'Protocolo TSA',
    content: `
## Descripción general

Time Stamp Authority (TSA) implementa **RFC 3161** para proporcionar marcas de tiempo confiables que demuestran criptográficamente que un documento, hash o firma digital existía en un momento específico. TSA se usa ampliamente para firma de código, cumplimiento legal, archivado a largo plazo y trazabilidad de auditoría.

## Cómo funciona

1. **El cliente crea una solicitud de marca de tiempo** — genera un hash del archivo con SHA-256/SHA-512 y crea un \`TimeStampReq\` (codificado en ASN.1 DER)
2. **El cliente envía la solicitud a TSA** — HTTP POST al endpoint \`/tsa\` con \`Content-Type: application/timestamp-query\`
3. **UCM firma la marca de tiempo** — la CA configurada firma el hash + la hora actual en un \`TimeStampResp\`
4. **El cliente recibe y almacena la respuesta** — el archivo \`.tsr\` puede demostrar más tarde que el documento existía en ese momento

## Configuración

### Pestaña de configuración

1. **Activar TSA** — Alternar el servidor TSA
2. **CA firmante** — Seleccionar qué Autoridad de Certificación firma los tokens de marca de tiempo
3. **OID de política** — Identificador de objeto para la política TSA (ej., \`1.2.3.4.1\`), incluido en cada respuesta de marca de tiempo

### Elegir una CA firmante

La clave privada de la CA firmante se usa para firmar cada token de marca de tiempo. Mejores prácticas:

- Use una **sub-CA dedicada** para marcas de tiempo en lugar de su CA raíz
- El certificado de la CA debe incluir el uso extendido de clave **id-kp-timeStamping** (OID 1.3.6.1.5.5.7.3.8)
- Asegúrese de que el certificado de la CA tenga **validez suficiente** — las marcas de tiempo deben permanecer verificables durante años

### OID de política

El OID de política identifica la política TSA bajo la cual se emiten las marcas de tiempo. Se incluye en cada \`TimeStampResp\`.

- Predeterminado: \`1.2.3.4.1\` (marcador de posición)
- Para producción, registre un OID bajo el arco de su organización o use uno de su CP/CPS

## Pestaña de información

La pestaña de información muestra:

- **URL del endpoint TSA** — URL lista para copiar y pegar para la configuración del cliente
- **Ejemplos de uso** — Comandos OpenSSL para crear solicitudes, enviarlas y verificar respuestas
- **Estadísticas** — Total de solicitudes de marca de tiempo procesadas (exitosas y fallidas)

## Ejemplos de uso

### Crear una solicitud de marca de tiempo

\`\`\`bash
# Generar hash de un archivo y crear una solicitud de marca de tiempo
openssl ts -query -data file.txt -sha256 -no_nonce -out request.tsq
\`\`\`

### Enviar solicitud a TSA

\`\`\`bash
# Enviar la solicitud y recibir una respuesta de marca de tiempo
curl -s -H "Content-Type: application/timestamp-query" \\
  --data-binary @request.tsq \\
  https://your-server:8443/tsa -o response.tsr
\`\`\`

### Verificar una marca de tiempo

\`\`\`bash
# Verificar la respuesta de marca de tiempo contra el archivo original
openssl ts -verify -data file.txt -in response.tsr \\
  -CAfile ca-chain.pem
\`\`\`

### Firma de código con marcas de tiempo

Al firmar código, agregue la URL de TSA para asegurar que las firmas sigan siendo válidas después de la expiración del certificado:

\`\`\`bash
# Firmar con marca de tiempo (osslsigncode)
osslsigncode sign -certs cert.pem -key key.pem \\
  -ts https://your-server:8443/tsa \\
  -in app.exe -out app-signed.exe

# Firmar con marca de tiempo (signtool.exe en Windows)
signtool sign /fd SHA256 /tr https://your-server:8443/tsa \\
  /td SHA256 /f cert.pfx app.exe
\`\`\`

### Marcas de tiempo para documentos PDF

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
|-----------|-------|
| RFC | 3161 (Internet X.509 PKI TSP) |
| Endpoint | \`/tsa\` (POST) |
| Content-Type | \`application/timestamp-query\` |
| Tipo de respuesta | \`application/timestamp-reply\` |
| Algoritmos de hash | SHA-256, SHA-384, SHA-512, SHA-1 (legado) |
| Autenticación | Ninguna (endpoint público) |
| Transporte | HTTP o HTTPS |

## Consideraciones de seguridad

- El endpoint TSA es **público** — no se requiere autenticación (igual que CRL/OCSP)
- Cada respuesta de marca de tiempo está **firmada** por la clave de la CA — los clientes verifican la firma para asegurar la autenticidad
- Use **SHA-256 o más fuerte** al crear solicitudes (SHA-1 se acepta pero no se recomienda)
- TSA **no** ve el documento original — solo se transmite el hash
- Considere **limitar la velocidad** si el endpoint TSA está expuesto a Internet

> 💡 Las marcas de tiempo son esenciales para la firma de código: aseguran que su software firmado siga siendo confiable incluso después de que expire el certificado de firma.
`
  }
}
