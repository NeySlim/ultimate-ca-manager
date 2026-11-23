export default {
  helpContent: {
    title: 'Módulos de seguridad de hardware',
    subtitle: 'Almacenamiento externo de claves',
    overview: 'Integre módulos de seguridad de hardware para el almacenamiento seguro de claves privadas. Compatible con PKCS#11, AWS CloudHSM, Azure Key Vault, Google Cloud KMS y OpenBao/Vault Transit.',
    sections: [
      {
        title: 'Proveedores compatibles',
        definitions: [
          { term: 'PKCS#11', description: 'Interfaz HSM estándar de la industria (Thales, Entrust, SoftHSM)' },
          { term: 'AWS CloudHSM', description: 'HSM en la nube de Amazon Web Services' },
          { term: 'Azure Key Vault', description: 'Almacenamiento de claves gestionado de Microsoft Azure' },
          { term: 'Google KMS', description: 'Servicio de gestión de claves de Google Cloud' },
          { term: 'OpenBao / Vault Transit', description: 'Motor de secretos Transit de OpenBao o HashiCorp Vault para la gestión de claves como servicio de cifrado' },
        ]
      },
      {
        title: 'Acciones',
        items: [
          { label: 'Nuevo proveedor', text: 'Configurar la conexión a un HSM (ruta de la biblioteca, credenciales, slot)' },
          { label: 'Probar conexión', text: 'Verificar que el HSM es accesible y que las credenciales son válidas; para un módulo PKCS#11, registra además lo que este informa (biblioteca, fabricante, versiones de la biblioteca y del firmware), que se muestra en la página del proveedor' },
          { label: 'Generar', text: 'Crear un nuevo par de claves directamente en el HSM' },
          { label: 'Sincronizar claves', text: 'Vuelve a leer las claves del proveedor desde el token: se añaden las claves nuevas y se eliminan las que ya no están en el token, salvo las que usa una CA, que se conservan. Si falla el listado del token, no se elimina nada. El mensaje indica los recuentos, las claves conservadas y las claves ilegibles; el botón permanece deshabilitado mientras se ejecuta la sincronización' },
          { label: 'Estado', text: 'La lista muestra de cada proveedor el tipo, las claves, la última comprobación (su última prueba de conexión) y el estado: Conectado, Error, Desconectado o No probado. El detalle de un proveedor tiene su resumen, sus claves y su configuración' },
          { label: 'Certificación', text: 'Declarar la certificación del HSM: Common Criteria EAL 4+, EUCC (garantía alta), FIPS 140-3 nivel 3, FIPS 140-2 nivel 3 u otra. Si se deja vacía, no se declara. El perfil de cumplimiento eu-acm solo acepta Common Criteria EAL 4+, EUCC (garantía alta) y FIPS 140-3 nivel 3 (hasta el 31 de diciembre de 2030) para una CA respaldada por HSM' },
          { label: 'Nombre ya existente (v2.249)', text: 'Generar una clave con un nombre que OpenBao o Azure Key Vault ya tienen se rechaza (409): incorpore una clave existente con una sincronización de claves (POST /api/v2/hsm/providers/<id>/sync)' },
          { label: 'Una generación a la vez (v2.249)', text: 'Las generaciones de claves se turnan en cada proveedor, y una que siga esperando tras 60 segundos recibe un 409. Una clave cuyo registro no pudo almacenarse se elimina del HSM' },
          { label: 'PIN en las copias de seguridad (v2.249)', text: 'Una copia de seguridad contiene el PIN o el token del proveedor en claro dentro del archivo, protegido por su contraseña, de modo que se restaura en otra instalación. Un valor que solo abre la clave de otra instalación se descarta al restaurar, con una entrada de registro que pide volver a introducirlo' },
          { label: 'SoftHSM en modo FIPS (v2.247)', text: 'El modo FIPS rechaza un nuevo proveedor SoftHSM, ya que SoftHSM no es un módulo validado; UCM_FIPS_ALLOW_SOFTHSM=1 permite uno para pruebas' },
        ]
      },
      {
        title: 'CA respaldadas por HSM (v2.130+)',
        content: 'Una vez configurado un proveedor, se puede fijar la clave privada de una CA a ese HSM en el momento de crearla:',
        items: [
          { label: 'Selector Almacenamiento de clave', text: 'En el formulario de creación de la CA, elija Local (cifrada en la base de datos) o HSM. Seleccione el proveedor y la etiqueta de la clave' },
          { label: 'Ruta de firma', text: 'Toda emisión, firma de CRL y firma OCSP de esa CA usa el HSM; la clave nunca sale' },
          { label: 'Restricciones de exportación', text: 'Las exportaciones PKCS#12, JKS y solo de clave están deshabilitadas para las CA respaldadas por HSM (solo puede exportarse el certificado público o la cadena)' },
          { label: 'CRL y OCSP', text: 'Ambos funcionan con las CA respaldadas por HSM de forma transparente (firmados mediante el HSM)' },
          { label: 'Migración', text: 'Las CA locales existentes no pueden pasarse a un HSM tras su creación: elija en el momento de crearlas' },
          { label: 'Una autoridad por clave', text: 'Una clave de HSM respalda una sola autoridad, X.509 o SSH. Las listas de claves existentes ofrecen las claves sin usar, una segunda CA sobre una clave se rechaza (409) con el nombre de la CA que la tiene, y no se puede eliminar una clave ni su proveedor mientras una CA la tenga' },
          { label: 'Permisos', text: 'Crear una CA sobre una clave de HSM, X.509 o SSH, requiere read:hsm además de write:cas o write:ssh_cas; la opción HSM no está disponible sin él' },
          { label: 'CA SSH', text: 'Una CA SSH de usuario o de host puede usar una clave de firma RSA o ECDSA P-256/P-384/P-521 (véase CA SSH). En modo HA, una clave en SoftHSM o en un lector local de tarjetas inteligentes se rechaza, porque existe en un solo nodo' },
        ]
      },
      {
        title: 'Claves ML-DSA',
        content: 'Las claves ML-DSA-44, ML-DSA-65 y ML-DSA-87 (FIPS 204) solo se ofrecen en los proveedores que firman con ellas. Firman los datos mismos, por lo que no se elige ningún resumen.',
        items: [
          { label: 'PKCS#11', text: 'Un token que implemente PKCS#11 3.2 con los mecanismos ML-DSA' },
          { label: 'OpenBao / Vault Transit', text: 'Tipos de clave Transit mldsa-44, mldsa-65 y mldsa-87' },
          { label: 'Google Cloud KMS', text: 'Versiones de clave PQ_SIGN_ML_DSA, asignadas a partir de la API de KMS pero aún no probadas con el servicio. KMS firma como máximo 64 KiB de datos, por lo que una CRL mayor no puede firmarse' },
          { label: 'No disponible', text: 'Los proveedores Azure Key Vault y AWS CloudHSM no tienen ninguna clave ML-DSA, y el modo FIPS rechaza ML-DSA en todos los proveedores' },
        ]
      },
    ],
    tips: [
      'Use SoftHSM para probar antes de desplegar con un HSM físico',
      'Las claves generadas en un HSM nunca salen del hardware: no pueden exportarse',
      'Pruebe la conexión antes de usar un proveedor HSM para firmar con una CA',
      'Para CA raíz de larga duración en producción, prefiera el almacenamiento de claves respaldado por HSM',
    ],
    warnings: [
      'La certificación declarada es la afirmación del operador sobre el HSM: UCM no verifica el hardware. Los perfiles alineados con eIDAS la leen para comprobar la protección de la clave de la CA',
      'Una mala configuración del proveedor HSM puede impedir la firma de certificados',
      'Perder el acceso al HSM significa perder el acceso a las claves almacenadas en él',
    ],
  },
  helpGuides: {
    title: 'Módulos de seguridad de hardware',
    content: `
## Descripción general

Los módulos de seguridad de hardware (HSM) proporcionan un almacenamiento a prueba de manipulación para las claves criptográficas. Las claves privadas almacenadas en un HSM nunca salen del hardware, lo que ofrece el máximo nivel de protección de claves.

## Proveedores compatibles

### PKCS#11
La interfaz HSM estándar de la industria. Dispositivos compatibles:
- **Thales Luna** / **SafeNet**
- **Entrust nShield**
- **SoftHSM** (basado en software, para pruebas)
- Cualquier dispositivo compatible con PKCS#11

> 💡 **Docker**: SoftHSM viene preinstalado en la imagen de Docker. En el primer arranque se inicializa automáticamente un token por defecto y se registra como el proveedor \`SoftHSM-Default\`, listo para usar de inmediato. En modo FIPS, SoftHSM no es un módulo validado: el proveedor por defecto no se crea y un proveedor SoftHSM se rechaza, salvo que \`UCM_FIPS_ALLOW_SOFTHSM=1\` permita uno para pruebas.

Configuración:
- **Ruta de la biblioteca PKCS#11**: ruta de la biblioteca compartida PKCS#11 (.so/.dll)
- **Etiqueta del token**: etiqueta del token que se usará (obligatoria)
- **Slot ID**: número de slot del HSM (opcional)
- **PIN**: PIN de usuario para la autenticación

### AWS CloudHSM
HSM en la nube de Amazon Web Services:
- **ID del clúster**: identificador del clúster de CloudHSM
- **Etiqueta del token**: etiqueta del token PKCS#11 de CloudHSM
- **Crypto Usuario / Crypto Contraseña**: el usuario criptográfico (CU) con el que UCM inicia sesión; no hace falta ninguna clave de acceso de AWS

### Azure Key Vault
Almacenamiento de claves gestionado de Microsoft Azure:
- **URL de la bóveda**: endpoint de Azure Key Vault
- **ID de inquilino**: inquilino de Azure AD
- **ID de cliente/Secreto de cliente**: credenciales de la entidad de servicio

### Google Cloud KMS
Servicio de gestión de claves de Google Cloud:
- **ID del proyecto**: ID del proyecto de GCP
- **Ubicación**: ubicación del llavero de KMS
- **Clave Ring**: nombre del llavero de claves
- **Clave JSON de la cuenta de servicio**: credenciales de la cuenta de servicio

### OpenBao / Vault Transit
Motor de secretos Transit de OpenBao o HashiCorp Vault. Las claves se gestionan de forma remota mediante la API Transit, sin necesidad de una biblioteca PKCS#11.

Configuración:
- **URL del servidor**: dirección del servidor (p. ej., \`https://openbao.example.com:8200\`)
- **Token de autenticación**: token de autenticación
- **Ruta de montaje Transit**: punto de montaje del motor Transit (por defecto: \`transit\`)
- **Espacio de nombres**: espacio de nombres opcional para configuraciones multiinquilino
- **Omitir verificación TLS**: omitir la verificación del certificado TLS (para certificados autofirmados)

Tipos de clave compatibles:
- RSA 2048, 3072, 4096
- ECDSA P-256, P-384, P-521
- ML-DSA-44, ML-DSA-65, ML-DSA-87 (claves Transit \`mldsa-*\`, en una versión de OpenBao que las incluya)
- AES-256-GCM (simétrica)

> 💡 OpenBao es una bifurcación de HashiCorp Vault mantenida por la comunidad. UCM funciona con OpenBao y con Vault.

> 💡 Para desarrollo, ejecute OpenBao en modo dev: \`docker run -d -p 8200:8200 -e BAO_DEV_ROOT_TOKEN_ID=test-token quay.io/openbao/openbao:latest server -dev\`

## Gestión de proveedores

### Añadir un proveedor
1. Pulse **Nuevo proveedor**
2. Seleccione el **tipo de proveedor**
3. Introduzca los datos de conexión
4. Pulse **Crear**
5. Pulse **Probar** en el nuevo proveedor para verificar la conexión

### Probar la conexión
Pruebe siempre la conexión tras crear o modificar un proveedor. UCM verifica que puede comunicarse con el HSM y autenticarse. Para un módulo PKCS#11, la prueba registra además lo que el módulo informa (biblioteca, fabricante, versiones de la biblioteca y del firmware), que se muestra en la página del proveedor.

### Estado del proveedor
Cada proveedor muestra un indicador del estado de la conexión:
- **Conectado**: el HSM es accesible y la autenticación es correcta
- **Desconectado**: no se puede alcanzar el HSM
- **Error**: problema de autenticación o de configuración

## Gestión de claves

### Generar claves
1. Seleccione un proveedor conectado
2. Pulse **Generar**
3. Elija el algoritmo (RSA 2048/4096, ECDSA P-256/P-384)
4. Introduzca una etiqueta o alias para la clave
5. Pulse **Generar**

La clave se crea directamente en el HSM. UCM solo almacena una referencia.

### Claves ML-DSA
ML-DSA-44, ML-DSA-65 y ML-DSA-87 (FIPS 204) solo se ofrecen en los proveedores que firman con ellas:
- **PKCS#11**: un token que implemente PKCS#11 3.2 con los mecanismos ML-DSA
- **OpenBao / Vault Transit**: tipos de clave \`mldsa-44\`, \`mldsa-65\` y \`mldsa-87\`
- **Google Cloud KMS**: versiones de clave \`PQ_SIGN_ML_DSA_*\`, asignadas a partir de la API de KMS pero aún no probadas con el servicio. KMS firma como máximo 64 KiB de datos, por lo que una CRL mayor no puede firmarse

Los proveedores Azure Key Vault y AWS CloudHSM no tienen ninguna clave ML-DSA, y el modo FIPS rechaza ML-DSA en todos los proveedores. Una clave ML-DSA firma los datos mismos, por lo que no se elige ningún resumen.

### Sincronizar claves
Pulse **Sincronizar claves** en los detalles del proveedor para volver a leer las claves del token.
- Se añaden las claves nuevas.
- Se eliminan las claves que ya no están en el token, salvo las que usa una CA: se conservan.
- Si falla el listado del token, no se elimina nada.

El mensaje indica los recuentos, el número de claves conservadas porque una CA las usa, el número de claves ilegibles y el número de claves usadas por una CA cuyo material cambió en el token. El botón permanece deshabilitado mientras se ejecuta la sincronización.

### Usar claves de HSM
Al crear una CA, seleccione un proveedor HSM y una clave en lugar de generar una clave en software. Las operaciones de firma de la CA se realizan en el HSM.

Una clave de HSM respalda una sola autoridad, X.509 o SSH. Crear una CA sobre una clave de HSM requiere el permiso \`read:hsm\` además de \`write:cas\` (\`write:ssh_cas\` para una CA SSH), y no se puede eliminar una clave que tiene una CA.

> ⚠ Las claves generadas en un HSM no pueden exportarse. Si pierde el acceso al HSM, pierde las claves.

> 💡 Use SoftHSM para desarrollo y pruebas antes de desplegar con HSM físicos.
`
  }
}
