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
          { label: 'Revocar', text: 'Revoca una CA intermedia desde su CA padre: se publica en la CRL y el OCSP del padre, y la CA ya no puede firmar (permanente)' },
          { label: 'Reparar cadena', text: 'Corrige automáticamente las relaciones padre-hijo rotas' },
          { label: 'Importar clave privada', text: 'Adjuntar la clave privada de una CA que solo tiene su certificado (firmado a partir de una solicitud externa) para que pueda firmar' },
        ]
      },
      {
        title: 'CAs firmadas externamente (modo CSR, v2.214)',
        content: 'El tipo de creación «Firmada por CA externa (CSR)» cubre el patrón de raíz sin conexión: el par de claves vive en UCM, el certificado se firma en otro lugar. La clave privada nunca sale de UCM.',
        items: [
          { label: 'Crear', text: 'UCM genera el par de claves (local o HSM) y un CSR de tipo CA — el CSR se descarga automáticamente' },
          { label: 'En espera de certificado', text: 'La CA pendiente no puede firmar, exportarse, ser padre ni ponerse sin conexión hasta que se instale su certificado' },
          { label: 'Subir certificado', text: 'Pegue o suba el certificado firmado externamente (PEM/DER). Su clave pública debe coincidir con la clave privada almacenada; se verifican las restricciones de CA' },
          { label: 'Cadena', text: 'Se vincula automáticamente cuando el emisor es conocido por UCM — importe la raíz externa (solo el certificado) para una cadena completa' },
          { label: 'Renovar vía CSR', text: 'Reemite un CSR desde la misma clave (SKI estable); fírmelo externamente y suba el nuevo certificado' },
          { label: 'Después de la renovación', text: 'El certificado sustituido sigue siendo válido hasta su notAfter — UCM muestra su número de serie tras la subida; revóquelo en la raíz externa si ya no debe ser de confianza' },
        ]
      },
      {
        title: 'CAs respaldadas por HSM',
        items: [
          { label: 'Almacenamiento de clave', text: 'Elija Local (cifrado en BD) o HSM al crear la CA' },
          { label: 'Generar clave nueva', text: 'Crea una clave de firma nueva en el proveedor HSM seleccionado' },
          { label: 'Usar clave existente', text: 'Vincula la CA a una clave de firma no utilizada ya presente en el HSM' },
          { label: 'Sin exportación de clave privada', text: 'Las claves respaldadas por HSM nunca salen del HSM — PKCS#12, JKS y exportación de clave están deshabilitados' },
          { label: 'Requisito previo', text: 'Configure y conecte un proveedor HSM en Gestión HSM primero' },
        ]
      },
      {
        title: 'Modo sin conexión',
        items: [
          { label: 'Propósito', text: 'Proteger la clave privada de una CA (típicamente una raíz) del uso en tiempo de ejecución manteniendo disponibles el certificado, la cadena, la CRL y OCSP' },
          { label: 'Protegida con contraseña', text: 'La clave se cifra con una contraseña proporcionada por el usuario (PKCS#8) y permanece en la base de datos. Restauración introduciendo la contraseña.' },
          { label: 'Exportada a archivo', text: 'La clave se exporta como un PEM cifrado descargable una vez y se elimina de la base de datos. Restauración volviendo a subir el archivo con la contraseña.' },
          { label: 'Política de contraseña', text: 'La contraseña sigue las reglas de complejidad de UCM (longitud y clases de caracteres). Si se pierde, la clave es irrecuperable.' },
          { label: 'Efecto en la firma', text: 'La firma de CSR, la emisión de certificados y la renovación de la CA están bloqueadas sin conexión. CRL y OCSP siguen funcionando con firmas en caché.' },
          { label: 'Sub-CAs', text: 'Tanto las CAs raíces como las intermedias pueden ponerse sin conexión de forma independiente' },
        ]
      },
      {
        title: 'CRLs externas para CAs sin clave (v2.215)',
        content: 'Una CA cuya clave UCM no puede usar (CA sin conexión, importación solo del certificado) no puede firmar su propia CRL — suba en su lugar una generada junto a la clave sin conexión.',
        items: [
          { label: 'Dónde', text: 'Panel de detalles de la CA › Lista de revocación (CRL): muestra el número de la CRL servida, la cantidad de entradas, thisUpdate/nextUpdate y una advertencia una vez pasado nextUpdate' },
          { label: 'Subida', text: 'Solo CRLs completas (no delta), en PEM o DER. La firma debe verificarse contra el certificado de la CA y el emisor debe coincidir con su sujeto' },
          { label: 'Monotonía', text: 'Una subida más antigua que la CRL servida actualmente (número de CRL o thisUpdate) se rechaza — emítala con un número de CRL más alto' },
          { label: 'Publicación', text: 'La CRL subida se sirve en la ruta CDP existente de la CA, y OCSP responde «revocado» para los números de serie que lista' },
          { label: 'Flujo de trabajo', text: 'Revoque en la raíz sin conexión, genere la CRL de la raíz en el entorno air-gap y súbala aquí — la clave de la raíz nunca pasa a estar en línea' },
        ]
      },
    ],
    tips: [
      'Las CAs con un icono de llave (🔑) tienen clave privada y pueden firmar certificados',
      'Ponga la CA raíz sin conexión tan pronto como sus intermedias estén operativas',
      'Use «Exportada a archivo» para el mayor aislamiento air-gap; «Protegida con contraseña» para una restauración rápida in situ',
      'La exportación PKCS#12 incluye la cadena completa y es ideal para respaldo',
    ],
    warnings: [
      'Eliminar una CA NO revocará los certificados que haya emitido — revócalos primero',
      'Las claves privadas se almacenan cifradas; perder la base de datos significa perder las claves',
      'Las contraseñas del modo sin conexión NO son recuperables — guárdelas en su gestor de contraseñas / vault antes de confirmar',
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

### Crear una CA firmada externamente (modo CSR, v2.214)
Para el patrón de raíz sin conexión — la clave de la CA emisora vive en UCM, su certificado se firma en otro lugar:
1. Haz clic en **Crear** → tipo **Firmada por CA externa (CSR)**
2. Completa el Sujeto y la configuración de clave (local o HSM) — la validez la decide el firmante externo
3. Envía: UCM genera el par de claves y un CSR de tipo CA (se descarga automáticamente)
4. Haz firmar el CSR por tu CA raíz externa/sin conexión
5. De vuelta en la CA (insignia **En espera de certificado**), haz clic en **Subir certificado** y proporciona el certificado firmado (PEM o DER)

UCM solo activa la CA si la clave pública del certificado coincide con la clave privada almacenada y se cumplen las restricciones de CA. La cadena se vincula automáticamente cuando el emisor es conocido por UCM — importa la raíz externa (solo el certificado) para una cadena completa. Hasta la activación, la CA pendiente no puede firmar, exportarse, ser CA padre ni ponerse sin conexión.

Para renovar, usa **Renovar vía CSR**: se emite un nuevo CSR **desde la misma clave** (el SKI permanece estable), se firma externamente y se sube mediante el mismo flujo.

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

## Revocar una CA intermedia

Una CA intermedia cuya clave está comprometida o que se retira del servicio se revoca desde su CA padre, como un certificado:

1. Selecciona la CA intermedia y haz clic en **Revocar CA**
2. Elige el motivo RFC 5280 (compromiso de clave, compromiso de CA, cese de operación, ...)
3. Confirma: la revocación es permanente

Qué ocurre a continuación:
- El número de serie de la CA se publica en la **CRL de la CA padre** (regenerada inmediatamente) y el **respondedor OCSP** del padre responde \`revoked\` con el motivo
- La CA revocada **ya no puede firmar** nada: certificados, CSRs, renovaciones, sub-CAs, y tampoco pueden hacerlo las CAs situadas por debajo
- Los certificados que emitió dejan de ser de confianza para los clientes que validan la cadena; su propia CRL y OCSP se siguen sirviendo hasta que se elimine la CA
- Eliminar la CA revocada conserva su entrada en la CRL del padre hasta la expiración original del certificado

> ⚠ Una CA raíz no puede revocarse desde UCM (autofirmada: las partes que confían en ella la retiran de sus almacenes de confianza), y una intermedia firmada por una raíz externa se revoca en esa raíz. Su CRL puede entonces servirse desde UCM (ver Modo sin conexión).

## Eliminar una CA

> ⚠ Eliminar una CA la remueve de UCM pero NO revoca los certificados que haya emitido. Revoca los certificados primero si es necesario.

La eliminación se bloquea si la CA tiene CAs hijas. Elimina o reasigna las hijas primero.

## CAs respaldadas por HSM

UCM puede almacenar la clave de firma de una CA en un módulo de seguridad de hardware (HSM) externo en lugar de la base de datos cifrada local. Es la opción recomendada para CAs raíz e intermedias en producción.

### Cuándo usar
- Requisitos de cumplimiento (FIPS 140-2/3, eIDAS, Common Criteria)
- Defensa en profundidad: las claves no pueden exfiltrarse aunque se comprometa el host UCM
- Custodia centralizada de claves entre varias herramientas PKI

### Requisitos previos
1. Abra **Gestión HSM** y configure un proveedor (PKCS#11 / OpenBao / etc.)
2. Verifique que el proveedor esté **Activo** y **Conectado**

### Paso a paso
1. Abra **Crear CA**
2. Rellene el sujeto y la validez como de costumbre
3. En **Almacenamiento de clave**, cambie de *Local* a **HSM**
4. Elija el proveedor HSM
5. Elija un modo de clave:
   - **Generar clave nueva** — proporcione una etiqueta (letras/dígitos/_/-) y elija el algoritmo (RSA-2048/3072/4096 o EC-P256/P384/P521)
   - **Usar clave existente** — elija una clave de firma no utilizada ya presente en el HSM
6. Envíe. UCM crea el certificado de CA y lo vincula a la clave HSM.

### Limitaciones
- Las claves privadas respaldadas por HSM **no se pueden exportar**. Las opciones PKCS#12, JKS y solo-clave se ocultan para las CAs HSM. Solo el certificado (PEM/DER/P7B) puede exportarse.
- **No hay migración in situ** entre Local y HSM. Para «mover» una CA local existente a un HSM, cree una nueva CA en el HSM y vuelva a emitir los certificados.
- Las claves existentes ofrecidas en *Usar clave existente* se filtran a claves asimétricas con capacidad de firma aún no vinculadas a otra CA.

## Modo sin conexión

Saca la clave de firma de una CA del uso en tiempo de ejecución sin eliminar la CA. El certificado, la cadena, la CRL y OCSP siguen funcionando — solo se bloquean las operaciones de firma (firmar CSR, emitir certificado, renovar CA).

Esta es la forma estándar de proteger una CA raíz entre ceremonias poco frecuentes, manteniendo en línea su ancla de confianza y su infraestructura de revocación.

### Dos modos

**Protegida con contraseña** — la clave privada permanece en la base de datos UCM, envuelta (PKCS#8) bajo una contraseña que usted elige. Para volver a poner la CA en línea, haga clic en **Restaurar** y vuelva a introducir la contraseña. Rápido y conveniente; la seguridad depende de la fuerza de la contraseña y de que UCM no esté comprometido.

**Exportada a archivo** — la clave privada se exporta como un archivo PEM cifrado con contraseña que se descarga una vez. Luego la clave se **elimina de la base de datos**. Para volver a poner la CA en línea, haga clic en **Restaurar**, suba el archivo e introduzca la contraseña. Es la opción más fuerte (auténtico air-gap) pero usted es plenamente responsable del archivo: si lo pierde, la clave es irrecuperable.

### Reglas de contraseña
La contraseña sigue la política de complejidad estándar de UCM: longitud mínima, mezcla de clases de caracteres, sin secuencias triviales. Las mismas reglas que para las contraseñas de usuario.

### Paso a paso — Poner sin conexión
1. Abra el panel de detalles de la CA
2. Haga clic en **Poner sin conexión**
3. Lea la explicación, haga clic en **Continuar**
4. Elija un modo (*Protegida con contraseña* o *Exportada a archivo*)
5. Introduzca la contraseña dos veces
6. Confirme. Para *Exportada a archivo*, la clave cifrada se descarga inmediatamente — guárdela de forma segura.

### Paso a paso — Restaurar
1. Abra el panel de detalles de la CA sin conexión
2. Haga clic en **Restaurar**
3. Introduzca la contraseña
4. Para *Exportada a archivo*: seleccione además el archivo de clave previamente descargado
5. Confirme. Las operaciones de firma se reanudan inmediatamente.

### Efecto en las operaciones
| Operación | En línea | Sin conexión |
|---|---|---|
| Emitir certificado | Permitido | **Bloqueado** |
| Firmar CSR | Permitido | **Bloqueado** |
| Renovar CA | Permitido | **Bloqueado** |
| Renovar certificado emitido | Permitido | **Bloqueado** |
| Servir CRL / OCSP | Permitido | Permitido (firma en caché) |
| Exportar certificado / cadena | Permitido | Permitido |
| Eliminar CA | Permitido | Permitido |

> ⚠ Las contraseñas del modo sin conexión **no son recuperables**. Guárdelas en su gestor de contraseñas / vault antes de confirmar. Contraseña perdida = CA inutilizable = reemisión completa de la jerarquía subordinada.
`
  }
}