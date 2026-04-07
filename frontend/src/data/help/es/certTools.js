export default {
  helpContent: {
    title: 'Herramientas de certificados',
    subtitle: 'Decodificar, convertir y verificar certificados',
    overview: 'Un conjunto de herramientas para trabajar con certificados, CSR y claves. Decodifique certificados para inspeccionar su contenido, convierta entre formatos, verifique puntos de conexión SSL remotos y compruebe la correspondencia de claves.',
    sections: [
      {
        title: 'Herramientas disponibles',
        items: [
          { label: 'SSL Checker', text: 'Conectar a un host remoto e inspeccionar su cadena de certificados SSL/TLS' },
          { label: 'CSR Decoder', text: 'Pegar un CSR en formato PEM para ver su sujeto, SAN e información de clave' },
          { label: 'Certificate Decoder', text: 'Pegar un certificado en formato PEM para inspeccionar todos los campos' },
          { label: 'Key Matcher', text: 'Verificar que un certificado, CSR y clave privada pertenecen al mismo conjunto' },
          { label: 'Converter', text: 'Convertir entre formatos PEM, DER, PKCS#12 y PKCS#7' },
        ]
      },
      {
        title: 'Detalles del convertidor',
        items: [
          'Conversión PEM ↔ DER',
          'PEM → PKCS#12 con contraseña y cadena completa',
          'PKCS#12 → extracción PEM',
          'PEM → PKCS#7 (P7B) agrupación de cadena',
        ]
      },
    ],
    tips: [
      'SSL Checker admite puertos personalizados — úselo para verificar cualquier servicio TLS',
      'Key Matcher compara hashes de módulo para verificar pares coincidentes',
      'Converter conserva la cadena completa de certificados al crear PKCS#12',
    ],
  },
  helpGuides: {
    title: 'Herramientas de certificados',
    content: `
## Descripción general

Un conjunto de herramientas para inspeccionar, convertir y verificar certificados sin salir de UCM.

## SSL Checker

Inspeccionar el certificado SSL/TLS de un servidor remoto:

1. Introduzca el **nombre del host** (por ejemplo, \`google.com\`)
2. Opcionalmente cambie el **puerto** (por defecto: 443)
3. Haga clic en **Verificar**

Los resultados incluyen:
- Sujeto y emisor del certificado
- Fechas de validez
- SAN (nombres alternativos del sujeto)
- Tipo y tamaño de clave
- Cadena completa de certificados
- Versión del protocolo TLS

## CSR Decoder

Analizar y mostrar el contenido de un CSR:

1. Pegue un CSR en formato PEM
2. Haga clic en **Decodificar**

Muestra: sujeto, SAN, algoritmo de clave, tamaño de clave, algoritmo de firma.

## Certificate Decoder

Analizar y mostrar los detalles de un certificado:

1. Pegue un certificado en formato PEM
2. Haga clic en **Decodificar**

Muestra: sujeto, emisor, SAN, validez, número de serie, uso de clave, extensiones, huellas digitales.

## Key Matcher

Verificar que un certificado, CSR y clave privada pertenecen al mismo conjunto:

1. Pegue el **certificado** PEM
2. Pegue la **clave privada** PEM (opcionalmente cifrada — proporcione la contraseña)
3. Opcionalmente pegue un **CSR** PEM
4. Haga clic en **Verificar correspondencia**

UCM compara los hashes del módulo (RSA) o la clave pública (EC). Una coincidencia confirma que forman un par válido.

## Converter

Convertir entre formatos de certificados y claves:

### PEM → DER
Convierte un PEM codificado en Base64 a formato binario DER.

### PEM → PKCS#12
Crea un archivo P12/PFX protegido con contraseña a partir de:
- Certificado PEM
- Clave privada PEM
- Certificados de cadena opcionales
- Contraseña para el archivo P12

### PKCS#12 → PEM
Extrae certificado, clave y cadena de un archivo P12:
- Suba el archivo P12
- Introduzca la contraseña
- Descargue los componentes PEM extraídos

### PEM → PKCS#7
Agrupa múltiples certificados en un solo archivo P7B (sin claves).

> 💡 El convertidor conserva la cadena completa de certificados al crear archivos PKCS#12.
`
  }
}
