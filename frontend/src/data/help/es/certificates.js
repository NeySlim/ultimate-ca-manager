export default {
  helpContent: {
    title: 'Certificados',
    subtitle: 'Emitir, gestionar y supervisar certificados',
    overview: 'Gestión centralizada de todos los certificados X.509. Emita nuevos certificados desde sus CA, importe certificados existentes, controle las fechas de expiración y gestione las renovaciones y revocaciones.',
    sections: [
      {
        title: 'Estado del certificado',
        definitions: [
          { term: 'Válido', description: 'Dentro del período de validez y no revocado' },
          { term: 'Por expirar', description: 'Expirará dentro de 30 días' },
          { term: 'Expirado', description: 'Posterior a la fecha «Not After»' },
          { term: 'Revocado', description: 'Revocado explícitamente (publicado en la CRL)' },
          { term: 'Huérfano', description: 'La CA emisora ya no existe en el sistema' },
        ]
      },
      {
        title: 'Acciones',
        items: [
          { label: 'Emitir', text: 'Crear un nuevo certificado firmado por una de sus CA' },
          { label: 'Importar', text: 'Importar un certificado existente (PEM, DER o PKCS#12)' },
          { label: 'Renovar', text: 'Reemitir con el mismo sujeto y un nuevo período de validez' },
          { label: 'Revocar', text: 'Marcar como revocado con un motivo — aparecerá en la CRL' },
          { label: 'Levantar suspensión', text: 'Quitar la suspensión de un certificado revocado con el motivo «Suspensión de certificado» — lo restaura al estado válido' },
          { label: 'Revocar y reemplazar', text: 'Revocar y emitir inmediatamente un reemplazo' },
          { label: 'Exportar', text: 'Descargar en formato PEM, DER o PKCS#12' },
          { label: 'Comparar', text: 'Comparación lado a lado de dos certificados' },
        ]
      },
    ],
    tips: [
      'Marque con estrella ⭐ los certificados importantes para añadirlos a su lista de favoritos',
      'Utilice los filtros para encontrar rápidamente certificados por estado, CA o texto de búsqueda',
      'La renovación conserva el mismo sujeto pero genera un nuevo par de claves',
    ],
    warnings: [
      'La revocación es generalmente permanente — excepto para «Suspensión de certificado» que puede levantarse',
      'Eliminar un certificado lo quita de UCM pero no lo revoca',
    ],
  },
  helpGuides: {
    title: 'Certificados',
    content: `
## Descripción general

Gestión centralizada de todos los certificados X.509. Emita nuevos certificados, importe certificados existentes, controle las fechas de expiración, gestione las renovaciones y revocaciones.

## Estado del certificado

- **Válido** — Dentro del período de validez y no revocado
- **Por expirar** — Expirará dentro de 30 días (configurable)
- **Expirado** — Posterior a la fecha «Not After»
- **Revocado** — Revocado explícitamente, publicado en la CRL
- **Huérfano** — La CA emisora ya no existe en UCM

## Emitir un certificado

1. Haga clic en **Emitir certificado**
2. Seleccione la **CA de firma** (debe poseer una clave privada)
3. Complete el sujeto (CN es obligatorio, los demás campos son opcionales)
4. Añada nombres alternativos del sujeto (SAN): nombres DNS, IP, correos electrónicos
5. Elija el tipo y tamaño de la clave
6. Establezca el período de validez
7. Opcionalmente aplique una **plantilla** para prerellenar la configuración
8. Haga clic en **Emitir**

### Uso de plantillas
Las plantillas prerellenan el uso de la clave, el uso extendido de la clave, los valores predeterminados del sujeto y la validez. Seleccione una plantilla antes de rellenar el formulario para ahorrar tiempo.

## Importar certificados

Formatos admitidos:
- **PEM** — Certificados individuales o agrupados
- **DER** — Formato binario
- **PKCS#12 (P12/PFX)** — Certificado + clave + cadena (se requiere contraseña)
- **PKCS#7 (P7B)** — Cadena de certificados sin claves

## Renovar un certificado

La renovación crea un nuevo certificado con:
- Mismo sujeto y SAN
- Nuevo par de claves (generado automáticamente)
- Nuevo período de validez
- Nuevo número de serie

El certificado original permanece válido hasta que expire o sea revocado.

## Revocar un certificado

1. Seleccione el certificado → **Revocar**
2. Elija un motivo de revocación (Compromiso de clave, Compromiso de CA, Cambio de afiliación, Reemplazo, Cese de operación, Suspensión de certificado, etc.)
3. Confirme la revocación

Los certificados revocados se publican en la CRL en la próxima regeneración.

> ⚠ La revocación es generalmente permanente — excepto para la **Suspensión de certificado** que puede levantarse.

### Levantar suspensión

Si un certificado fue revocado con el motivo **Suspensión de certificado**, puede restaurarse al estado válido:

1. Abra los detalles del certificado revocado
2. El botón **Levantar suspensión** aparece en la barra de acciones (solo para revocaciones de tipo Suspensión de certificado)
3. Haga clic en **Levantar suspensión** para restaurar el certificado
4. El certificado vuelve al estado válido, la CRL se regenera y la caché OCSP se actualiza

> 💡 La suspensión de certificado es útil para suspensiones temporales (por ejemplo, dispositivo perdido, investigación en curso).

### Revocar y reemplazar
Combina la revocación con una reemisión inmediata. El nuevo certificado hereda el mismo sujeto y SAN.

## Exportar certificados

Formatos de exportación:
- **PEM** — Solo el certificado
- **PEM + Cadena** — Certificado con la cadena completa del emisor
- **DER** — Formato binario
- **PKCS#12** — Certificado + clave + cadena, protegido con contraseña

## Favoritos

Marque con estrella ⭐ los certificados importantes para guardarlos en favoritos. Los favoritos aparecen primero en las vistas filtradas y son accesibles desde el filtro de favoritos.

## Comparar certificados

Seleccione dos certificados y haga clic en **Comparar** para ver una comparación lado a lado de su sujeto, SAN, uso de la clave, validez y extensiones.

## Filtrado y búsqueda

- **Filtro por estado** — Válido, Por expirar, Expirado, Revocado, Huérfano
- **Filtro por CA** — Mostrar certificados de una CA específica
- **Búsqueda de texto** — Buscar por CN, número de serie o SAN
- **Ordenación** — Por nombre, fecha de expiración, fecha de creación, estado
`
  }
}
