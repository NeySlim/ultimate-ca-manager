export default {
  helpContent: {
    title: 'Autoridades de certificación',
    subtitle: 'Gestiona tu jerarquía PKI',
    overview: 'Crea y gestiona Autoridades de certificación raíz e intermedias. Construye una cadena de confianza completa para tu organización. Las CAs con clave privada pueden firmar certificados directamente.',
    sections: [
      {
        title: 'Vistas',
        items: [
          { label: 'Vista de árbol', text: 'Visualización jerárquica de las relaciones padre-hijo entre CAs' },
          { label: 'Vista de lista', text: 'Vista de tabla plana con ordenación y filtrado' },
          { label: 'Vista de organización', text: 'Agrupada por organización para configuraciones multi-tenant' },
        ]
      },
      {
        title: 'Acciones',
        items: [
          { label: 'Crear CA raíz', text: 'Autoridad de nivel superior autofirmada' },
          { label: 'Crear intermedia', text: 'CA firmada por una CA padre en la cadena' },
          { label: 'Importar CA', text: 'Importa un certificado CA existente (con o sin clave privada)' },
          { label: 'Exportar', text: 'PEM, DER o PKCS#12 (P12/PFX) con protección por contraseña' },
          { label: 'Renovar CA', text: 'Reemite el certificado CA con un nuevo período de validez' },
          { label: 'Reparar cadena', text: 'Corrige automáticamente las relaciones padre-hijo rotas' },
        ]
      },
    ],
    tips: [
      'Las CAs con un icono de llave (🔑) tienen clave privada y pueden firmar certificados',
      'Usa CAs intermedias para la firma diaria, mantén la CA raíz fuera de línea cuando sea posible',
      'La exportación PKCS#12 incluye la cadena completa y es ideal para respaldo',
    ],
    warnings: [
      'Eliminar una CA NO revocará los certificados que haya emitido — revócalos primero',
      'Las claves privadas se almacenan cifradas; perder la base de datos significa perder las claves',
    ],
  },
  helpGuides: {
    title: 'Autoridades de certificación',
    content: `
## Descripción general

Las Autoridades de certificación (CAs) forman la base de tu PKI. UCM soporta jerarquías de CA multinivel con CAs raíz, CAs intermedias y sub-CAs.

## Tipos de CA

### CA raíz
Un certificado autofirmado que sirve como ancla de confianza. Las CAs raíz deberían idealmente mantenerse fuera de línea en entornos de producción. En UCM, una CA raíz no tiene padre.

### CA intermedia
Firmada por una CA raíz u otra CA intermedia. Utilizada para la firma diaria de certificados. Las CAs intermedias limitan el radio de impacto en caso de compromiso.

### Sub-CA
Cualquier CA firmada por una CA intermedia, creando niveles de jerarquía más profundos.

## Vistas

### Vista de árbol
Muestra la jerarquía completa de CAs como un árbol desplegable. Las relaciones padre-hijo se visualizan con indentación y líneas de conexión.

### Vista de lista
Tabla plana con columnas ordenables: Nombre, Tipo, Estado, Certificados emitidos, Fecha de expiración.

### Vista de organización
Agrupa las CAs por su campo Organización (O). Útil para configuraciones multi-tenant donde diferentes departamentos gestionan árboles de CA separados.

## Crear una CA

### Crear CA raíz
1. Haz clic en **Crear** → **CA raíz**
2. Completa los campos del Sujeto (CN, O, OU, C, ST, L)
3. Selecciona el algoritmo de clave (RSA 2048/4096, ECDSA P-256/P-384)
4. Establece el período de validez (típicamente 10-20 años para CAs raíz)
5. Opcionalmente selecciona una plantilla de certificado
6. Haz clic en **Crear**

### Crear CA intermedia
1. Haz clic en **Crear** → **CA intermedia**
2. Selecciona la **CA padre** (debe tener clave privada)
3. Completa los campos del Sujeto
4. Establece el período de validez (típicamente 5-10 años)
5. Haz clic en **Crear**

> ⚠ La validez de la CA intermedia no puede exceder la de su CA padre.

## Importar una CA

Importa certificados CA existentes mediante:
- **Archivo PEM** — Certificado en formato PEM
- **Archivo DER** — Formato binario DER
- **PKCS#12** — Paquete de certificado + clave privada (requiere contraseña)

Al importar sin clave privada, la CA puede verificar certificados pero no puede firmar nuevos.

## Exportar una CA

Formatos de exportación:
- **PEM** — Certificado codificado en Base64
- **DER** — Formato binario
- **PKCS#12 (P12/PFX)** — Certificado + clave privada + cadena, protegido con contraseña

> 💡 La exportación PKCS#12 incluye la cadena completa de certificados y es ideal para respaldo.

## Claves privadas

Las CAs con un **icono de llave** (🔑) tienen una clave privada almacenada en UCM y pueden firmar certificados. Las CAs sin clave son solo de confianza — validan cadenas pero no pueden emitir.

### Almacenamiento de claves
Las claves privadas están cifradas en reposo en la base de datos de UCM. Para mayor seguridad, considera usar un proveedor HSM (ver la página HSM).

## Reparar cadena

Si las relaciones padre-hijo están rotas (p. ej., después de una importación), usa **Reparar cadena** para reconstruir automáticamente la jerarquía basándose en la coincidencia Emisor/Sujeto.

## Renovar una CA

La renovación reemite el certificado CA con:
- Mismo sujeto y clave
- Nuevo período de validez
- Nuevo número de serie

Los certificados existentes firmados por la CA permanecen válidos.

## Eliminar una CA

> ⚠ Eliminar una CA la remueve de UCM pero NO revoca los certificados que haya emitido. Revoca los certificados primero si es necesario.

La eliminación se bloquea si la CA tiene CAs hijas. Elimina o reasigna las hijas primero.
`
  }
}
