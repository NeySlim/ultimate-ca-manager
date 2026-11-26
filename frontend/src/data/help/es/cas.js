export default {
  helpContent: {
    title: "Autoridades de certificación",
    subtitle: "Gestione su jerarquía PKI",
    overview: "Cree y gestione CA raíz e intermedias. Construya una cadena de confianza completa para su organización. Las CA con clave privada pueden firmar certificados directamente.",
    sections: [
      {
        title: "Vistas",
        items: [
          { label: "Pestañas", text: "Todas, Raíz, Intermedias y Expiradas, cada una con su recuento, y luego Fuera de línea, Revocadas y A la espera de certificado cuando las hay. La pestaña forma parte de la dirección" },
          { label: "Vista de árbol", text: "La jerarquía de confianza, abierta por defecto junto al panel de la autoridad seleccionada: cada raíz con sus subautoridades a la derecha, plegadas a partir del primer nivel. Un nodo muestra su estado, sus certificados y sus subautoridades; una línea de puntos une una CA con la que la certificó de forma cruzada. Las raíces sin subautoridad ocupan una línea cada una, y las que no tienen certificado se pliegan en un solo grupo cuando son muchas" },
          { label: "Teclado", text: "En el árbol, las flechas se desplazan, derecha e izquierda despliegan y pliegan, y Intro o un clic selecciona la CA y la muestra en el panel lateral; la CA seleccionada forma parte de la dirección" },
          { label: "Buscar", text: "Filtra el árbol y la lista por el nombre, el nombre común y el sujeto; el árbol conserva la rama que lleva a cada coincidencia" },
          { label: "Panel lateral", text: "Junto al árbol (debajo en un teléfono): identidad, clave, emisión y revocación de la CA seleccionada, su emisor, sus subautoridades y sus certificados cruzados como enlaces, su CRL (número, publicación, próxima actualización, un aviso con un día de antelación) y si su respondedor OCSP está activo. Ver certificados, Emitir con esta CA (desactivado, con el motivo, cuando la CA no puede firmar), Descargar la cadena y luego Otras acciones (exportar, CSR, revocar, desconectar, restaurar, fijación de plantillas, eliminar). Los demás detalles (restricciones, extensiones, huellas, PEM, metadatos) están plegados debajo. Una CA abierta desde otra página (una cadena de certificados, la paleta de comandos, una aprobación) se abre aquí" },
          { label: "Vista de lista", text: "Tabla plana ordenable junto al panel lateral, 25 autoridades por página (10, 50 o 100 a elección): una acción por fila (descargar el certificado) y un chevrón que muestra la CA en el panel; en un teléfono cada CA es una tarjeta, que se abre con un toque en cualquier punto" },
        ]
      },
      {
        title: "Acciones",
        items: [
          { label: "Crear CA", text: "Un solo botón; el diálogo permite elegir una raíz autofirmada, una intermedia firmada por una CA padre o una CA firmada por una CA externa (CSR)" },
          { label: "Importar CA", text: "Importa un certificado de CA existente (con o sin clave privada)" },
          { label: "Exportar", text: "PEM, DER o PKCS#12 (P12/PFX) con protección por contraseña" },
          { label: "Revocar", text: "Revoca una CA intermedia desde su CA padre: se publica en la CRL y el OCSP del padre, y la CA ya no puede firmar (permanente)" },
          { label: "Reparación de cadena", text: "Corrige automáticamente las relaciones padre-hijo rotas. Su franja aparece sola cuando una CA queda huérfana, un registro espera su reparación o hay una reparación en curso; si no, el botón Reparación de cadena de la cabecera de la página la abre" },
          { label: "Importar clave privada", text: "Adjunta la clave privada de una CA que solo tiene su certificado, para que pueda firmar" },
          { label: "Usar una clave del HSM", text: "Para una CA importada sin su clave, que quedó en un HSM: elija el proveedor y luego una de sus claves cuya clave pública sea la del certificado. UCM comprueba que la clave firma para el certificado antes de que la CA la use; una clave que ya tiene otra CA se muestra, pero no se puede elegir" },
          { label: "Clave y validez", text: "RSA-3072 por defecto, local o HSM. Validez de 1, 2, 3, 5, 10, 15 o 20 años, o Personalizada (días) hasta 50 años. Se señala una CA RSA-2048 que sobreviviría a 2030: la ANSSI acepta RSA-2048 hasta finales de 2030, ETSI TS 119 312 hasta finales de 2026" },
          { label: "Poscuántica (ML-DSA)", text: "ML-DSA-44, ML-DSA-65 o ML-DSA-87 (FIPS 204, niveles NIST 2, 3 y 5), generada en software o en un proveedor HSM que admita ML-DSA; en modo FIPS solo una clave de software, que se ofrece cuando el módulo FIPS aprueba ML-DSA (la imagen Docker -fips lo hace). Una clave ML-DSA firma sin un hash aparte, así que la CA, sus CRL y sus respuestas OCSP no tienen hash que elegir. Una CA ML-DSA puede firmar certificados RSA o EC, y una CA RSA o EC puede firmar una intermedia ML-DSA" },
          { label: "EdDSA (Ed25519, Ed448)", text: "Claves Ed25519 o Ed448 para una CA raíz, intermedia o externa, solo en software (ningún proveedor HSM firma EdDSA) y ocultas en modo FIPS salvo que el módulo FIPS apruebe EdDSA (la imagen Docker -fips lo hace). Como ML-DSA, una clave EdDSA firma sin hash, y la jerarquía puede mezclarse con RSA, EC o ML-DSA. Los navegadores, Windows (CryptoAPI/CNG) y los clientes SCEP no aceptan lo que firma una CA EdDSA, sea cual sea la clave de la hoja: resérvela para consumidores OpenSSL, Go o Java 15+. SCEP y XCEP rechazan una CA así" },
          { label: "Importación EdDSA (v2.251)", text: "Una clave de CA Ed25519 o Ed448 se puede importar con su certificado, o después con Importar clave privada" },
          { label: "Hash predeterminado (v2.251)", text: "Bajo una CA P-384 o P-521, lo que se firma sin un hash elegido (EST, SCEP, WSTEP, Firmar CSR, el formulario de emisión, órdenes ACME sin hash, CRL) usa SHA-384 o SHA-512; las políticas acotan los certificados, no las CRL. Las CRL ya emitidas no cambian: la siguiente sigue la regla" },
          { label: "Sin clave privada (v2.247)", text: "Una CA conservada sin su clave privada se marca como Sin clave privada, con una acción Importar clave privada. Los selectores de CA indican cuántas CA dejan fuera por no poder firmar" },
          { label: "Restricciones de nombre", text: "Restricciones avanzadas (RFC 5280): los subárboles permitidos y excluidos (DNS, rango de IP, correo) limitan los nombres que la CA puede certificar. En una CA firmada externamente, las fija la CA firmante" },
          { label: "Esquema de firma RSA", text: "PKCS#1 v1.5 por defecto, o RSA-PSS (sal tan larga como el hash) para una CA RSA con una clave local, PKCS#11 o OpenBao. Se aplica a los certificados, las CRL, las respuestas OCSP y las respuestas SCEP que firma la CA; las marcas de tiempo siguen en PKCS#1 v1.5, el esquema que comprueba openssl ts -verify. «Firmar con RSA-PSS» en los detalles de la CA cambia una CA existente en uno u otro sentido: los certificados ya emitidos conservan su firma" },
          { label: "Perfil de cumplimiento", text: "ANSSI, BSI o EU ACM: reglas alineadas con un texto de referencia acotan lo que emite la CA (tipos de clave, hashes, esquema RSA, horizontes de fechas y, para EU ACM, una clave de CA en un HSM). Elija uno al crearla (a una CA intermedia se le propone el perfil de su padre; si no, el predeterminado de Ajustes, Acerca de). En una CA existente, el campo de los detalles lo asocia, lo cambia o lo quita: la comprobación del perfil se ejecuta primero sobre esa CA, se listan sus hallazgos y usted confirma que las reglas se aplican solo a las emisiones futuras, sin volver a firmar nada de lo ya emitido. Requiere write:cas, y admin:system para asociarlo o cambiarlo" },
          { label: "Listas de emisión", text: "Ocultar de la emisión, en los detalles de la CA, deja una CA (típicamente una raíz) fuera de las listas de CA de Emitir certificado, Firmar CSR, la firma masiva de CSR, los certificados mTLS de usuario (Mi cuenta, Usuarios y grupos) y el certificado de firma de TSA. Un enlace bajo esas listas, Mostrar CA ocultas, la recupera cuando hace falta, y una CA ya elegida sigue en la lista. Los ajustes de protocolo (ACME, EST, SCEP, XCEP/WSTEP), el padre de una CA nueva y la firma cruzada la siguen listando. Requiere write:cas" },
          { label: "Sujeto único", text: "Aplicar, en los detalles de la CA, hace que la CA rechace un certificado cuyo sujeto (RFC 5280 §4.1.2.6) ya lleve bajo ella un certificado de otra entidad, válido, caducado, revocado o sustituido por igual: un nombre una vez certificado queda ligado a su entidad. La misma entidad se reconoce por la misma clave pública, por una renovación de uno de sus certificados (renovar, renovación automática, EST simplereenroll, SCEP RenewalReq, renovación WSTEP), por la misma cuenta ACME o por el mismo SID de Windows. No se comprueban un sujeto vacío, los certificados de CA ni los servicios que UCM certifica para sí mismo. Emitir certificado y Firmar CSR nombran entonces el certificado que tiene el sujeto y ofrecen Emitir a la misma entidad: el operador atestigua que el nuevo certificado es para la entidad que ya lleva el sujeto, el certificado se une a esa entidad (el antiguo y el nuevo se renuevan entonces como de costumbre, renovación automática incluida) y el registro de auditoría anota la atestación; los protocolos no tienen excepción. Un sujeto que varias entidades ya llevan (compartido antes de activar la opción, o importado) sigue compartido: nada indica a qué entidad se refiere, así que sus renovaciones se rechazan tal cual y su renovación automática falla; solo pasan Emitir certificado y Firmar CSR, con esa confirmación. Activar la opción se permite con sujetos ya compartidos: se muestran su número y el primero de ellos. Desactivada por defecto. Requiere write:cas" },
          { label: "CA padre no verificable", text: "Una CA cuyo padre no puede comprobar UCM por su clave (SLH-DSA, GOST) se importa sin padre. Sus detalles nombran el padre probable (mismo sujeto que su emisor, mismo identificador de clave cuando ambos lo llevan) y el algoritmo; Vincular a esta CA padre pide una confirmación explícita, lo comprueba todo de nuevo y registra quién lo confirmó y cuándo. La reparación de cadena conserva el vínculo, una reimportación también mientras esa CA siga siendo el padre probable, y Retirar el vínculo lo quita. Una firma que no se verifica nunca se vincula. Requiere write:cas" },
        ]
      },
      {
        title: "CA firmadas externamente (modo CSR, v2.214)",
        content: "El tipo de creación «Firmada por CA externa (CSR)» cubre el patrón de raíz sin conexión: el par de claves vive en UCM, el certificado se firma en otro lugar. La clave privada nunca sale de UCM.",
        items: [
          { label: "Crear", text: "UCM genera el par de claves (local o HSM) y un CSR de tipo CA; el CSR se descarga automáticamente" },
          { label: "Esperando certificado", text: "La CA pendiente no puede firmar, exportarse, ser padre ni desconectarse hasta que se instale su certificado" },
          { label: "Subir certificado", text: "Pegue o suba el certificado firmado externamente (PEM/DER). Su clave pública debe coincidir con la clave privada almacenada; se aplican las restricciones de CA" },
          { label: "Cadena", text: "Se vincula automáticamente cuando UCM conoce al emisor; importe la raíz externa (solo el certificado) para una cadena completa" },
          { label: "Renovar mediante CSR", text: "Reemite un CSR desde la misma clave (SKI estable); fírmelo externamente y suba el nuevo certificado" },
          { label: "Tras la renovación", text: "El certificado reemplazado sigue siendo válido hasta su notAfter, UCM muestra su número de serie tras la subida; revóquelo en la raíz externa si ya no debe ser de confianza" },
        ]
      },
      {
        title: "Certificados cruzados",
        content: "Un certificado cruzado lleva el sujeto y la clave de una CA bajo otro emisor, de modo que los clientes que solo confían en esa otra raíz pueden construir una ruta. Se coloca junto al certificado propio de la CA y nunca lo reemplaza.",
        items: [
          { label: "Dónde", text: "Panel lateral de la CA › Certificados cruzados; una CA que lleva uno muestra una insignia Firmada de forma cruzada" },
          { label: "Adjuntar", text: "Pegue o elija un certificado (PEM o DER) emitido por otra CA para la clave de esta CA; se informa de las restricciones de nombre o de política que lleve" },
          { label: "Firmar de forma cruzada", text: "Firma la clave de esta CA con otra CA presente en UCM, con una validez y una longitud de ruta" },
          { label: "Servir", text: "Como máximo uno por CA se sirve en la cadena predeterminada (TLS, PKCS#12, ACME, WSTEP, TSA, despliegues, AIA .cer y .pem). Uno revocado, caducado o aún no válido nunca se sirve" },
          { label: "Cadena a presentar", text: "Las exportaciones y los enlaces de despliegue pueden fijar la cadena predeterminada, la raíz autofirmada o un certificado cruzado. ACME ofrece las demás cadenas como alternativas (certbot --preferred-chain)" },
          { label: "Importación", text: "Un certificado sobre la clave de una CA presente se adjunta a una raíz autofirmada; en una intermedia, el 409 ofrece Adjuntar como certificado cruzado o Reemplazar. Smart Importar lo adjunta junto a una raíz presente o lo indica como omitido" },
          { label: "Aún encadenadas", text: "Panel lateral de la CA › Aún encadenadas a esta CA lista los certificados, las subCA activas, los enlaces de despliegue y los envíos de CRL que aún dependen de la CA, directamente o mediante un certificado cruzado, para saber cuándo se puede retirar una raíz antigua; un cliente que guardó una cadena en caché no se cuenta" },
          { label: "Reparación", text: "La barra bajo las estadísticas lista los registros que dañó una importación anterior: Convertir en certificado cruzado (requiere delete:cas) y Restaurar como principal. Nada se ejecuta solo" },
        ]
      },
      {
        title: "CA respaldadas por HSM",
        items: [
          { label: "Almacenamiento de clave", text: "Elija Local (en la base de datos, cifrada bajo la clave maestra) o HSM al crear la CA" },
          { label: "Generar clave nueva", text: "Crea una clave de firma nueva en el proveedor HSM seleccionado" },
          { label: "Usar clave existente", text: "Vincula la CA a una clave de firma no utilizada ya presente en el HSM" },
          { label: "Sin exportación de clave privada", text: "Las claves respaldadas por HSM nunca salen del HSM; las exportaciones PKCS#12, JKS y solo clave están desactivadas" },
          { label: "Requisito previo", text: "Configure y conecte primero un proveedor HSM en Gestión HSM" },
          { label: "Una autoridad por clave", text: "La lista de claves existentes ofrece solo claves no utilizadas: una clave HSM respalda una sola autoridad, X.509 o SSH. Una clave que ya tiene una CA se rechaza (409) con el nombre de esa CA" },
          { label: "Permiso", text: "Crear una CA en una clave HSM requiere read:hsm además de write:cas; la opción HSM está desactivada sin él" },
        ]
      },
      {
        title: "Modo desconectado",
        items: [
          { label: "Finalidad", text: "Proteger la clave privada de una CA (típicamente una raíz) del uso en tiempo de ejecución, manteniendo disponibles su certificado, su cadena y su última CRL" },
          { label: "Protegido por contraseña", text: "La clave se envuelve con una contraseña aportada por el usuario (PKCS#8) y permanece en la base de datos. Se restaura introduciendo la contraseña." },
          { label: "Archivo de clave exportado", text: "La clave se exporta como una descarga PEM protegida con contraseña y se elimina de la base de datos. Se restaura volviendo a subir el archivo con la contraseña." },
          { label: "Política de contraseña", text: "La contraseña sigue las reglas de complejidad de contraseñas de UCM (longitud y clases de caracteres). Si se pierde, la clave es irrecuperable." },
          { label: "Efecto en la firma", text: "La firma de CSR, la emisión de certificados y la renovación quedan bloqueadas mientras la CA está desconectada. La última CRL se sigue sirviendo hasta que suba una nueva firmada junto a la clave; OCSP responde mediante un respondedor delegado y, si no, solo con respuestas ya en caché, hasta su nextUpdate." },
          { label: "Subordinadas", text: "Tanto las CA raíz como las intermedias pueden desconectarse de forma independiente" },
        ]
      },
      {
        title: "CRL externas para CA sin clave (v2.215)",
        content: "Una CA cuya clave no puede usar UCM (CA desconectada, importación solo del certificado) no puede firmar su propia CRL: suba en su lugar una generada junto a la clave desconectada.",
        items: [
          { label: "Dónde", text: "Vista de detalles de la CA › Lista de revocación (CRL): muestra el número de la CRL servida, el recuento de entradas, la fecha de esta actualización y de la siguiente, y un aviso una vez pasado el nextUpdate" },
          { label: "Subir", text: "PEM o DER, solo CRL completas (no delta). La firma debe verificarse con el certificado de la CA y el emisor debe coincidir con su sujeto" },
          { label: "Monotonía", text: "Se rechaza una subida más antigua que la CRL servida actualmente (número de CRL o thisUpdate): emítala con un número de CRL mayor" },
          { label: "Publicación", text: "La CRL subida se sirve en la ruta CDP existente de la CA, y OCSP responde revocado para los números de serie que lista" },
          { label: "Flujo de trabajo", text: "Revoque en la raíz desconectada, genere la CRL de la raíz en el entorno aislado (air-gap), súbala aquí: la clave de la raíz nunca se conecta" },
        ]
      },
    ],
    tips: [
      "Las CA con un icono de llave (🔑) tienen una clave privada y pueden firmar certificados",
      "Desconecte la CA raíz en cuanto sus intermedias estén operativas",
      "Use «Archivo de clave exportado» para el aislamiento air-gap más fuerte; «Protegido por contraseña» para una restauración rápida en el sitio",
      "La exportación PKCS#12 incluye la cadena completa y es ideal para copias de seguridad",
    ],
    warnings: [
      "Una CA ML-DSA aún no se puede exportar como PKCS#12 ni JKS: exporte el certificado y la clave privada como PEM. Los clientes sin soporte de ML-DSA (OpenSSL anterior a 3.5, la mayoría de los navegadores actuales) no pueden verificar lo que firma",
      "Una CA no se puede eliminar mientras tenga CA intermedias o certificados emitidos: revóquelos y elimínelos primero",
      "Las claves privadas se almacenan cifradas bajo la clave maestra; perder la base de datos, o la clave maestra sin una copia de seguridad de UCM, supone perder las claves",
      "Las contraseñas del modo desconectado NO son recuperables: guárdelas en su gestor de contraseñas o bóveda antes de confirmar",
      "Un certificado cruzado nunca reemplaza el certificado propio de una CA: una intermedia que se recertificara bajo otro emisor se rechaza (409) salvo que la adjunte como certificado cruzado o reemplace la actual; un cambio de raíz bajo el mismo nombre de emisor la reemplaza",
      "Una raíz autofirmada sobrescrita o eliminada no se recupera con Convertir en certificado cruzado: restáurela desde una copia de seguridad, o entregue su certificado a Restaurar como principal",
    ],
  },
  helpGuides: {
    title: "Autoridades de certificación",
    content: `
## Descripción general

Las autoridades de certificación (CA) forman la base de su PKI. UCM admite jerarquías de CA multinivel con CA raíz, CA intermedias y subCA.

## Tipos de CA

### CA raíz
Un certificado autofirmado que sirve como ancla de confianza. Las CA raíz deberían mantenerse idealmente desconectadas en entornos de producción. En UCM, una CA raíz no tiene padre.

### CA intermedia
Firmada por una CA raíz u otra CA intermedia. Se usa para la firma diaria de certificados. Las CA intermedias limitan el alcance del daño en caso de compromiso.

### SubCA
Cualquier CA firmada por una CA intermedia, que crea niveles de jerarquía más profundos.

## Vistas

Las pestañas bajo el título cuentan las CA (Todas, Raíz, Intermedias, Expiradas, y luego Fuera de línea, Revocadas y A la espera de certificado cuando las hay) y filtran la página; la pestaña forma parte de la dirección. El campo de búsqueda filtra por el nombre, el nombre común y el sujeto. Jerarquía y Lista, a su lado, alternan entre las dos vistas; la autoridad mostrada en el panel lateral forma parte de la dirección.

### Vista de árbol
La vista por defecto. Cada raíz que encabeza una jerarquía se dibuja con sus subautoridades a la derecha, plegadas a partir del primer nivel; un nodo indica su estado, el número de sus certificados y de sus subautoridades, y una línea de puntos une una CA con la que la certificó de forma cruzada. Una raíz sin subautoridad ocupa una sola línea, y las raíces que no tienen certificado se pliegan en un solo grupo cuando son muchas. Las flechas se desplazan por el árbol, derecha e izquierda despliegan y pliegan, e Intro o un clic selecciona la CA.

### Panel lateral
Junto al árbol (debajo en un teléfono), la CA seleccionada muestra su identidad, su clave, lo que emitió y su revocación: el emisor, las subautoridades y los certificados cruzados son enlaces que los seleccionan, la CRL indica su número, su publicación y su próxima actualización (con un aviso con un día de antelación), y el respondedor OCSP figura como activo o inactivo. **Ver certificados** abre la lista de certificados filtrada por esta CA, **Emitir con esta CA** abre el formulario de emisión sobre ella (desactivado, con el motivo, cuando la CA no puede firmar), **Descargar la cadena** descarga su cadena PEM, y **Otras acciones** reúne exportar, CSR, revocación, desconexión, restauración, fijación de plantillas y eliminación. Los demás detalles (restricciones, extensiones, huellas, PEM, metadatos) están plegados debajo. Una CA abierta desde otra página se abre aquí.

### Vista de lista
Tabla plana con columnas ordenables, junto al panel lateral, 25 autoridades por página (10, 50 o 100 a elección). Una fila lleva una acción (descargar el certificado) y un chevrón que muestra la CA en el panel. En un teléfono cada CA es una tarjeta con los mismos datos y su chevrón; un toque en cualquier punto muestra la CA.

## Crear una CA

### Crear una CA raíz
1. Haga clic en **Crear CA** y elija el tipo raíz en el diálogo
2. Complete los campos del sujeto (CN, O, OU, C, ST, L)
3. Seleccione el algoritmo de clave (RSA 2048/3072/4096, ECDSA P-256/P-384/P-521, ML-DSA 44/65/87, EdDSA Ed25519/Ed448): RSA-3072 por defecto
4. Establezca el período de validez: 1, 2, 3, 5, 10, 15 o 20 años, o **Personalizada (días)** hasta 50 años (típicamente 10-20 años para las CA raíz)
5. Haga clic en **Crear**

### Crear una CA intermedia
1. Haga clic en **Crear CA** y elija el tipo intermedia en el diálogo
2. Seleccione la **CA padre** (debe tener clave privada)
3. Complete los campos del sujeto
4. Establezca el período de validez (típicamente 5-10 años)
5. Haga clic en **Crear**

> ⚠ La validez de la CA intermedia no puede exceder la de su CA padre.

El formulario señala una CA RSA-2048 que sobreviviría a 2030: la ANSSI acepta RSA-2048 hasta finales de 2030, ETSI TS 119 312 hasta finales de 2026. Elija RSA-3072 o superior. En **Restricciones avanzadas (RFC 5280)**, los subárboles permitidos y excluidos (DNS, rango de IP, correo) limitan los nombres que la CA puede certificar.

### CA poscuánticas (ML-DSA)
**ML-DSA-44**, **ML-DSA-65** y **ML-DSA-87** (FIPS 204) aparecen con su nivel de seguridad NIST (2, 3 y 5). La clave se genera en software, o en un proveedor HSM que admita ML-DSA (véase CA respaldadas por HSM); en modo FIPS solo se ofrece una clave de software, cuando el módulo FIPS aprueba ML-DSA (la imagen Docker \`-fips\` lo hace, RHEL 9 y Ubuntu 24.04 no).

- Una clave ML-DSA firma sin un hash aparte: el campo de hash desaparece, y un hash enviado por la API se ignora con un aviso. Las CRL y las respuestas OCSP de la CA siguen la misma regla.
- Las jerarquías pueden mezclarse: una raíz ML-DSA puede firmar una intermedia RSA o EC, y una CA RSA o EC puede firmar una intermedia ML-DSA, que entonces usa el hash de su padre.
- Una CA ML-DSA se exporta como PEM o DER, no como PKCS#12 ni JKS. Los clientes sin soporte de ML-DSA (OpenSSL anterior a 3.5, la mayoría de los navegadores actuales) no pueden verificar lo que firma.

### CA EdDSA (Ed25519, Ed448)
Se pueden generar claves **Ed25519** y **Ed448** para una CA raíz, intermedia o externa, o importarlas con el certificado de la CA o después. La clave es de software (ningún proveedor HSM firma EdDSA), y en modo FIPS el algoritmo solo se ofrece cuando el módulo FIPS lo aprueba (la imagen Docker \`-fips\` lo hace, RHEL 9 y Ubuntu 24.04 no).

- Una clave EdDSA firma sin hash, como ML-DSA: el campo de hash desaparece y las CRL y las respuestas OCSP siguen la misma regla.
- Las jerarquías pueden mezclarse: una CA EdDSA puede firmar intermedias y hojas RSA, EC o ML-DSA, y a la inversa.
- Los navegadores, Windows (CryptoAPI/CNG) y los clientes SCEP no aceptan certificados firmados por una CA EdDSA, sea cual sea la clave de la hoja. SCEP y XCEP/WSTEP rechazan una CA así. Úsela donde los consumidores sean OpenSSL, Go o Java 15+.

### Crear una CA firmada externamente (modo CSR, v2.214)
Para el patrón de raíz sin conexión: la clave de la CA emisora vive en UCM, su certificado se firma en otro lugar:
1. Haga clic en **Crear** → tipo **Firmada por CA externa (CSR)**
2. Complete el sujeto y la configuración de clave (local o HSM): la validez la decide el firmante externo
3. Envíe: UCM genera el par de claves y un CSR de tipo CA (se descarga automáticamente)
4. Haga firmar el CSR por su CA raíz externa o desconectada
5. De vuelta en la CA (insignia **Esperando certificado**), haga clic en **Subir certificado** y proporcione el certificado firmado (PEM o DER)

UCM solo activa la CA si la clave pública del certificado coincide con la clave privada almacenada y se cumplen las restricciones de CA. La cadena se vincula automáticamente cuando UCM conoce al emisor: importe la raíz externa (solo el certificado) para una cadena completa. Hasta la activación, la CA pendiente no puede firmar, exportarse, ser CA padre ni desconectarse.

Para renovar, use **Renovar mediante CSR**: se emite un nuevo CSR **desde la misma clave** (el SKI permanece estable), se firma externamente y se sube mediante el mismo flujo.

## Importar una CA

Importe certificados de CA existentes mediante:
- **Archivo PEM**: certificado en formato PEM
- **Archivo DER**: formato binario DER
- **PKCS#12**: paquete de certificado y clave privada (requiere contraseña)

Al importar sin clave privada, la CA puede verificar certificados pero no puede firmar otros nuevos.

Un certificado que lleva el sujeto y la clave de una CA ya presente en UCM, bajo otro emisor, es un certificado cruzado y nunca reemplaza el certificado propio de la CA. En una raíz autofirmada se adjunta como certificado cruzado. En una intermedia, y al subirlo tras **Renovar mediante CSR**, la importación se rechaza (409) y ofrece **Adjuntar como certificado cruzado** o **Reemplazar**; un cambio de raíz (mismo nombre de emisor, clave nueva) reemplaza el certificado como lo hace una renovación. Smart Importar adjunta el que encuentra junto a una raíz presente y lo indica en el resultado; el que no puede adjuntar se omite y se informa como omitido.

## Exportar una CA

Formatos de exportación:
- **PEM**: certificado codificado en Base64
- **DER**: formato binario
- **PKCS#12 (P12/PFX)**: certificado, clave privada y cadena, protegido con contraseña

Cuando un certificado cruzado ofrece otra ruta, el diálogo de exportación muestra **Cadena a presentar**: la cadena predeterminada que sirve UCM, la raíz autofirmada o un certificado cruzado.

> 💡 La exportación PKCS#12 incluye la cadena completa de certificados y es ideal para copias de seguridad.

## Certificados cruzados

Un certificado cruzado lleva el sujeto y la clave de una CA bajo la firma de otra CA. Los clientes que solo confían en la otra raíz construyen a través de él una ruta hasta su CA, y así se renueva o migra una raíz sin romperlos. Se coloca junto al certificado propio de la CA, que nunca se reemplaza. Una CA que lleva uno muestra una insignia **Firmada de forma cruzada**.

En los detalles de la CA, **Certificados cruzados** los lista:
- **Adjuntar**: pegue o elija un certificado emitido por otra CA para la clave de esta CA (PEM o DER). Se informa de las restricciones de nombre o de política que lleve.
- **Firmar de forma cruzada**: firme la clave de esta CA con otra CA presente en UCM; elija la validez y la longitud de ruta.
- **Servir / Dejar de servir**: como máximo uno por CA se sirve, en la cadena predeterminada de TLS, PKCS#12, ACME, WSTEP, TSA y despliegues, y en las URL AIA \`.cer\` y \`.pem\`. Uno revocado, caducado o aún no válido se conserva y se puede exportar, pero nunca se sirve.
- **Exportar** y **Desvincular**.

Las exportaciones y los enlaces de despliegue pueden fijar otra cadena (**Cadena a presentar** / **Variante de cadena**). El servidor ACME ofrece las demás cadenas como alternativas, que el cliente elige con \`--preferred-chain\`. Los cambios llegan a los clientes tras la siguiente emisión o despliegue, y tras la caché de 24 horas de las URL AIA.

### Reparar registros dañados

Una barra bajo las estadísticas de la CA lista los registros que dejó una importación anterior: un registro duplicado que contiene el certificado cruzado de una raíz que también está presente (**Convertir en certificado cruzado** traslada sus CA hijas y sus certificados a la raíz y elimina el duplicado), o una clave compartida por certificados distintos sin registro autofirmado (**Restaurar como principal** toma el certificado autofirmado). No se cambia nada sin un clic. Una raíz autofirmada sobrescrita o eliminada solo se recupera desde una copia de seguridad o mediante **Restaurar como principal**.

## Claves privadas

Las CA con un **icono de llave** (🔑) tienen una clave privada almacenada en UCM y pueden firmar certificados. Las CA sin clave son solo de confianza: validan cadenas pero no pueden emitir.

### Almacenamiento de claves
Las claves privadas se almacenan en la base de datos de UCM, cifradas bajo la clave maestra que UCM crea en su primer arranque (véase Ajustes › Seguridad). Para mayor seguridad, considere usar un proveedor HSM (véase la página HSM).

## Reparación de cadena

Si las relaciones padre-hijo están rotas (p. ej., tras una importación), use **Reparación de cadena** para reconstruir automáticamente la jerarquía a partir de la coincidencia Emisor/Sujeto. Su franja aparece sola mientras una CA está huérfana, un registro espera su reparación o hay una reparación en curso; si no, el botón **Reparación de cadena** de la cabecera de la página la abre.

## Renovar una CA

UCM no reemite el certificado de una CA que él firmó: para reemplazar una CA próxima a expirar, cree una CA nueva y emita bajo ella. Una CA firmada por una CA externa se renueva con **Renovar mediante CSR**, que reemite un CSR desde la misma clave para que la CA externa lo firme (véase CA firmadas externamente).

## Revocar una CA intermedia

Una CA intermedia cuya clave está comprometida o que se retira del servicio se revoca desde su CA padre, como un certificado:

1. Seleccione la CA intermedia y haga clic en **Revocar CA**
2. Elija el motivo RFC 5280 (compromiso de clave, compromiso de CA, cese de operación, ...)
3. Confirme: la revocación es permanente

Qué ocurre a continuación:
- El número de serie de la CA se publica en la **CRL de la CA padre** (regenerada de inmediato) y el **respondedor OCSP** del padre responde \`revoked\` con el motivo
- La CA revocada **ya no puede firmar** nada: certificados, CSR, renovaciones, subCA, y tampoco pueden hacerlo las CA situadas por debajo
- Los certificados que emitió dejan de ser de confianza para los clientes que validan la cadena; su propia CRL y su OCSP se siguen sirviendo hasta que se elimine la CA
- Eliminar la CA revocada conserva su entrada en la CRL del padre hasta la expiración original del certificado

> ⚠ Una CA raíz no puede revocarse desde UCM (autofirmada: las partes que confían en ella la retiran de sus almacenes de confianza), y una intermedia firmada por una raíz externa se revoca en esa raíz. Su CRL puede entonces servirse desde UCM (véase Modo desconectado).

## Eliminar una CA

La eliminación se rechaza (409) mientras la CA tenga CA intermedias, haya emitido certificados o esté vinculada a un perfil SCEP u otro servicio. Revoque y elimine primero sus certificados, y elimine sus CA hijas.

## CA respaldadas por HSM

UCM puede almacenar la clave de firma de una CA en un módulo de seguridad de hardware (HSM) externo en lugar de la base de datos cifrada local. Es la opción recomendada para las CA raíz e intermedias en producción.

### Cuándo usarlas
- Requisitos de cumplimiento (FIPS 140-2/3, eIDAS, Common Criteria)
- Defensa en profundidad: las claves no se pueden exfiltrar aunque se comprometa el host de UCM
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
   - **Generar clave nueva**: indique una etiqueta (letras/dígitos/_/-) y elija el algoritmo (RSA-2048/3072/4096 o EC-P256/P384/P521, RSA-3072 por defecto; Brainpool en PKCS#11, ML-DSA en los proveedores indicados en Gestión HSM)
   - **Usar clave existente**: elija una clave de firma no utilizada ya presente en el HSM
6. Envíe. UCM crea el certificado de la CA y lo vincula a la clave HSM.

### Limitaciones
- Las claves privadas respaldadas por HSM **no se pueden exportar**. Las opciones de exportación PKCS#12, JKS y solo clave se ocultan para las CA HSM. Solo se puede exportar el certificado (PEM/DER/P7B).
- **No hay migración in situ** entre Local y HSM. Para «mover» una CA local existente a un HSM, cree una CA nueva en el HSM y vuelva a emitir los certificados.
- Las claves existentes que se ofrecen en *Usar clave existente* se filtran a claves asimétricas con capacidad de firma que aún no están vinculadas a una autoridad, X.509 o SSH: una clave HSM respalda una sola autoridad.
- Crear una CA en una clave HSM requiere el permiso \`read:hsm\` además de \`write:cas\`; sin él, la opción **HSM** está desactivada.

## Modo desconectado

Saque la clave de firma de una CA del uso en tiempo de ejecución sin eliminar la CA. El certificado, la cadena y la última CRL se siguen sirviendo; las operaciones de firma (firmar CSR, emitir certificados, renovar, nuevas CRL) quedan bloqueadas. OCSP responde mediante un respondedor delegado y, si no, solo con respuestas ya en caché, hasta su nextUpdate.

Es la forma estándar de proteger una CA raíz entre ceremonias poco frecuentes, manteniendo en línea su ancla de confianza y su infraestructura de revocación.

### Dos modos

**Protegido por contraseña**: la clave privada permanece en la base de datos de UCM, envuelta (PKCS#8) bajo una contraseña que usted elige. Para volver a poner la CA en línea, haga clic en **Restaurar CA** y vuelva a introducir la contraseña. Rápido y cómodo; la seguridad depende de la fortaleza de la contraseña y de que UCM no esté comprometido.

**Archivo de clave exportado**: la clave privada se exporta como un archivo PEM cifrado con contraseña que se descarga una sola vez. La clave se **elimina entonces de la base de datos**. Para volver a poner la CA en línea, haga clic en **Restaurar CA**, suba el archivo e introduzca la contraseña. Es la opción más fuerte (auténtico air-gap), pero usted es plenamente responsable del archivo: si lo pierde, la clave es irrecuperable.

### Reglas de contraseña
La contraseña sigue la política estándar de complejidad de contraseñas de UCM: longitud mínima, mezcla de clases de caracteres, sin secuencias triviales. Las mismas reglas que para las contraseñas de usuario.

### Paso a paso. Desconectar
1. Abra la CA en el inspector
2. Haga clic en **Desconectar**
3. Lea la explicación y haga clic en **Continuar**
4. Elija un modo (*Protegido por contraseña* o *Archivo de clave exportado*)
5. Introduzca la contraseña dos veces
6. Confirme. Con *Archivo de clave exportado*, la clave cifrada se descarga de inmediato: guárdela en un lugar seguro.

### Paso a paso. Restaurar
1. Abra la CA desconectada en el inspector
2. Haga clic en **Restaurar CA**
3. Introduzca la contraseña
4. Con *Archivo de clave exportado*: seleccione además el archivo de clave descargado antes
5. Confirme. Las operaciones de firma se reanudan de inmediato.

### Efecto en las operaciones
| Operación | En línea | Desconectada |
|---|---|---|
| Emitir un certificado | Permitido | **Bloqueado** |
| Firmar un CSR | Permitido | **Bloqueado** |
| Renovar un certificado emitido | Permitido | **Bloqueado** |
| Servir la última CRL | Permitido | Permitido (suba una nueva firmada junto a la clave) |
| OCSP | Permitido | Respondedor delegado, o respuestas en caché hasta nextUpdate |
| Exportar certificado / cadena | Permitido | Permitido |
| Eliminar la CA | Permitido | Permitido |

> ⚠ Las contraseñas del modo desconectado **no son recuperables**. Guárdelas en su gestor de contraseñas o bóveda antes de confirmar. Contraseña perdida = CA inutilizable = reemisión completa de la jerarquía subordinada.
`
  }
}
