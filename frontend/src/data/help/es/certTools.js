export default {
  helpContent: {
    title: 'Herramientas de certificados',
    subtitle: 'Decodificar, convertir y verificar certificados',
    overview: 'Un conjunto de herramientas para trabajar con certificados, CSR y claves. Decodifique certificados para inspeccionar su contenido, convierta entre formatos, verifique puntos de conexión SSL remotos y compruebe la correspondencia de claves.',
    sections: [
      {
        title: 'Disposición de la página',
        content: 'El índice de la izquierda lista las cinco herramientas; la herramienta elegida se muestra en su marco. Su botón la ejecuta en la línea situada bajo los campos, que indica entonces el resultado; el detalle sigue debajo. Un archivo se lee con Elegir un archivo… bajo cada campo PEM.',
        items: [
          { label: 'Cambiar de herramienta', text: 'Elegir otra herramienta borra el resultado de la anterior' },
          { label: 'Enlaces', text: 'Un enlace a /tools?tab=<herramienta> (ssl-checker, csr-decoder, cert-decoder, key-matcher, converter) abre esa herramienta' },
        ],
      },
      {
        title: 'Herramientas disponibles',
        items: [
          { label: 'Verificador SSL', text: 'Conectar a un host remoto e inspeccionar el certificado que presenta (solo el certificado final, no la cadena)' },
          { label: 'Decodificador CSR', text: 'Pegar una CSR en formato PEM para ver su sujeto, SAN e información de clave' },
          { label: 'Decodificador', text: 'Pegar un certificado en formato PEM para inspeccionar su sujeto, emisor, validez, clave, SAN, usos de clave y huellas; CDP, AIA y políticas no se muestran' },
          { label: 'Comparador de claves', text: 'Verificar que un certificado, una CSR y una clave privada se corresponden' },
          { label: 'Convertidor', text: 'Convertir entre los formatos PEM, DER, PKCS#12 y PKCS#7' },
        ]
      },
      {
        title: 'Detalles del convertidor',
        items: [
          'Conversión PEM ↔ DER',
          'PEM → PKCS#12 con contraseña y cadena completa',
          'PKCS#12 → extracción PEM',
          'PEM → PKCS#7 (P7B) agrupación de la cadena',
        ]
      },
    ],
    tips: [
      'El Verificador SSL admite puertos personalizados: úselo para comprobar cualquier servicio TLS',
      'El Comparador de claves compara las claves públicas, ML-DSA incluida: una clave privada ML-DSA debe incluir su semilla, y un archivo de clave que solo contiene la forma expandida se rechaza',
      'El Convertidor conserva la cadena completa de certificados al crear un PKCS#12',
      'Los decodificadores nombran una clave poscuántica con su nivel de seguridad NIST, p. ej. ML-DSA-65 (nivel 3), sin tamaño en bits',
      'UCM aún no puede escribir una clave ML-DSA en un PKCS#12 ni en un JKS: expórtela en PEM con la clave privada',
    ],
  },
  helpGuides: {
    title: 'Herramientas de certificados',
    content: `
## Descripción general

Un conjunto de herramientas para inspeccionar, convertir y verificar certificados sin salir de UCM.

## Verificador SSL

Inspeccionar el certificado SSL/TLS de un servidor remoto:

1. Introduzca el **nombre de host** (por ejemplo, \`google.com\`)
2. Opcionalmente cambie el **puerto** (por defecto: 443)
3. Haga clic en **Verificar SSL**

Los resultados incluyen:
- Sujeto y emisor del certificado
- Fechas de validez
- SAN (nombres alternativos del sujeto)
- Tipo y tamaño de clave
- Versión del protocolo TLS

Solo se lee el certificado que presenta el servidor, no el resto de su cadena.

## Decodificador CSR

Analizar y mostrar el contenido de una CSR:

1. Pegue una CSR en formato PEM
2. Haga clic en **Decodificar**

Muestra: sujeto, SAN, algoritmo de clave, tamaño de clave, algoritmo de firma.

## Decodificador de certificados

Analizar y mostrar los detalles de un certificado:

1. Pegue un certificado en formato PEM
2. Haga clic en **Decodificar**

Muestra: sujeto, emisor, SAN, validez, número de serie, uso de clave, extensiones, huellas digitales.

## Comparador de claves

Verificar que un certificado, una CSR y una clave privada se corresponden:

1. Pegue el PEM del **certificado**
2. Pegue el PEM de la **clave privada** (opcionalmente cifrada: indique la contraseña)
3. Opcionalmente pegue el PEM de la **CSR**
4. Haga clic en **Comparar claves**

UCM compara las claves públicas (RSA, EC, EdDSA, ML-DSA). Una coincidencia confirma que forman un par válido. Una clave privada ML-DSA debe incluir su semilla: un archivo de clave que solo contiene la forma expandida se rechaza.

## Claves poscuánticas

Los decodificadores y el Verificador SSL nombran una clave **ML-DSA** o **SLH-DSA** con su nivel de seguridad NIST, p. ej. *ML-DSA-65 (nivel 3)*. Estas claves no tienen tamaño en bits. UCM aún no puede escribir una clave ML-DSA en un PKCS#12 ni en un JKS, por lo que el diálogo de exportación las desactiva: exporte en PEM con la clave privada.

## Convertidor

Convertir entre formatos de certificados y claves:

### PEM → DER
Convierte un PEM codificado en Base64 a formato binario DER.

### PEM → PKCS#12
Crea un archivo P12/PFX protegido con contraseña a partir de:
- PEM del certificado
- PEM de la clave privada
- Certificados de cadena opcionales
- Contraseña para el archivo P12

### PKCS#12 → PEM
Extrae el certificado, la clave y la cadena de un archivo P12:
- Suba el archivo P12
- Introduzca la contraseña
- Descargue los componentes PEM extraídos

### PEM → PKCS#7
Agrupa varios certificados en un solo archivo P7B (sin claves).

> 💡 El convertidor conserva la cadena completa de certificados al crear archivos PKCS#12.
`
  }
}
