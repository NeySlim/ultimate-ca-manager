export default {
  helpContent: {
    title: 'Módulos de Seguridad de Hardware',
    subtitle: 'Almacenamiento externo de claves',
    overview: 'Integre con Módulos de Seguridad de Hardware para el almacenamiento seguro de claves privadas. Soporte para PKCS#11, AWS CloudHSM, Azure Key Vault, Google Cloud KMS y OpenBao/Vault Transit.',
    sections: [
      {
        title: 'Proveedores compatibles',
        definitions: [
          { term: 'PKCS#11', description: 'Interfaz HSM estándar de la industria (Thales, Entrust, SoftHSM)' },
          { term: 'AWS CloudHSM', description: 'HSM basado en la nube de Amazon Web Services' },
          { term: 'Azure Key Vault', description: 'Almacenamiento de claves gestionado de Microsoft Azure' },
          { term: 'Google KMS', description: 'Servicio de gestión de claves de Google Cloud' },
          { term: 'OpenBao / Vault Transit', description: 'Motor de secretos Transit de OpenBao o Vault para gestión de claves como servicio' },
        ]
      },
      {
        title: 'Acciones',
        items: [
          { label: 'Agregar proveedor', text: 'Configurar la conexión a un HSM (ruta de biblioteca, credenciales, slot)' },
          { label: 'Probar conexión', text: 'Verificar que el HSM es accesible y las credenciales son válidas; para un módulo PKCS#11, registra también lo que el módulo declara (biblioteca, fabricante, versiones de la biblioteca y del firmware), visible en la página del proveedor' },
          { label: 'Generar clave', text: 'Crear un nuevo par de claves directamente en el HSM' },
          { label: 'Estado', text: 'Monitorear el estado de conexión del proveedor' },
          { label: 'Certificación', text: 'Declarar la certificación del HSM: Common Criteria EAL 4+, EUCC high, FIPS 140-3 nivel 3, FIPS 140-2 nivel 3 u otra. Si se deja vacía, no se declara. El perfil de cumplimiento eu-acm solo acepta Common Criteria EAL 4+, EUCC high y FIPS 140-3 nivel 3 (hasta el 31 de diciembre de 2030) para una CA respaldada por HSM' },
          { label: 'Nombre ya en uso (v2.249)', text: 'Se rechaza (409) generar una clave con un nombre que OpenBao o Azure Key Vault ya tienen: traiga una clave existente con una sincronización de claves (POST /api/v2/hsm/providers/<id>/sync)' },
          { label: 'Una generación a la vez (v2.249)', text: 'Las generaciones de claves se turnan en cada proveedor, y una que sigue esperando tras 60 segundos recibe un 409. Una clave cuyo registro no pudo guardarse se elimina del HSM' },
          { label: 'PIN en las copias (v2.249)', text: 'Una copia contiene el PIN o el token del proveedor en claro dentro del archivo, protegido por su contraseña, de modo que se restaura en otra instalación. Un valor que solo abre la clave de otra instalación se descarta al restaurar, con una entrada de registro que pide introducirlo de nuevo' },
          { label: 'SoftHSM en modo FIPS (v2.247)', text: 'El modo FIPS rechaza un nuevo proveedor SoftHSM, al no ser SoftHSM un módulo validado; UCM_FIPS_ALLOW_SOFTHSM=1 permite uno para pruebas' },
        ]
      },
      {
        title: 'CA respaldadas por HSM (v2.130+)',
        content: 'Una vez configurado un proveedor, puede fijar la clave privada de una CA a ese HSM en el momento de creación:',
        items: [
          { label: 'Conmutador Key Storage', text: 'En el formulario de creación de CA, elegir Local (cifrado en DB) o HSM. Seleccionar proveedor + etiqueta de clave' },
          { label: 'Ruta de firma', text: 'Cada emisión, firma de CRL y firma OCSP de esa CA pasa por el HSM, la clave nunca sale' },
          { label: 'Restricciones de exportación', text: 'PKCS#12, JKS y exportaciones de solo clave están deshabilitadas para CA HSM (solo el certificado público / cadena pueden exportarse)' },
          { label: 'CRL y OCSP', text: 'Ambos funcionan de forma transparente con CA HSM (firmados vía HSM)' },
          { label: 'Migración', text: 'Las CA locales existentes no pueden moverse a un HSM tras la creación, elegir en la creación' },
        ]
      },
      {
        title: 'Claves ML-DSA',
        content: 'Las claves ML-DSA-44, ML-DSA-65 y ML-DSA-87 (FIPS 204) se ofrecen solo en los proveedores que firman con ellas. Firman los datos directamente, por lo que no se elige un resumen.',
        items: [
          { label: 'PKCS#11', text: 'Un token que implemente PKCS#11 3.2 con los mecanismos ML-DSA' },
          { label: 'OpenBao / Vault Transit', text: 'Tipos de clave Transit mldsa-44, mldsa-65 y mldsa-87' },
          { label: 'Google Cloud KMS', text: 'Versiones de clave PQ_SIGN_ML_DSA, mapeadas desde la API de KMS pero aún no probadas con el servicio. KMS firma como máximo 64 KiB de datos, por lo que una CRL mayor no puede firmarse' },
          { label: 'No disponible', text: 'Los proveedores Azure Key Vault y AWS CloudHSM no contienen ninguna clave ML-DSA, y el modo FIPS rechaza ML-DSA en todos los proveedores' },
        ]
      },

    ],
    tips: [
      'Use SoftHSM para pruebas antes de implementar con un HSM físico',
      'Las claves generadas en un HSM nunca salen del hardware, no se pueden exportar',
      'Pruebe la conexión antes de usar un proveedor HSM para la firma de CA',
      'Para CA raíz de larga duración en producción, prefiera el almacenamiento de clave respaldado por HSM',
    ],
    warnings: [
      'La certificación declarada es la afirmación del operador sobre el HSM: UCM no verifica el hardware. Los perfiles alineados con eIDAS la leen para comprobar la protección de la clave de la CA',
      'Una configuración incorrecta del proveedor HSM puede impedir la firma de certificados',
      'Perder el acceso al HSM significa perder el acceso a las claves almacenadas en él',
    ],
  },
  helpGuides: {
    title: 'Módulos de Seguridad de Hardware',
    content: `
## Descripción general

Los Módulos de Seguridad de Hardware (HSM) proporcionan almacenamiento resistente a manipulaciones para claves criptográficas. Las claves privadas almacenadas en un HSM nunca salen del hardware, proporcionando el nivel más alto de protección de claves.

## Proveedores compatibles

### PKCS#11
La interfaz HSM estándar de la industria. Dispositivos compatibles:
- **Thales Luna** / **SafeNet**
- **Entrust nShield**
- **SoftHSM** (basado en software, para pruebas)
- Cualquier dispositivo compatible con PKCS#11

> 💡 **Docker**: SoftHSM viene preinstalado en la imagen Docker. Al primer inicio, se inicializa automáticamente un token predeterminado y se registra como el proveedor \`SoftHSM-Default\`: listo para usar de inmediato. En modo FIPS, SoftHSM no es un módulo validado: el proveedor predeterminado no se crea y se rechaza un proveedor SoftHSM, salvo que \`UCM_FIPS_ALLOW_SOFTHSM=1\` permita uno para pruebas.

Configuración:
- **Ruta de biblioteca**: Ruta a la biblioteca compartida PKCS#11 (.so/.dll)
- **Slot**: Número de slot del HSM
- **PIN**: PIN de usuario para autenticación

### AWS CloudHSM
HSM basado en la nube de Amazon Web Services:
- **ID de clúster**: Identificador del clúster CloudHSM
- **Etiqueta del token**: etiqueta del token PKCS#11 de CloudHSM
- **Crypto Usuario / Crypto Contraseña**: el usuario criptográfico (CU) con el que UCM inicia sesión; no se necesita ninguna clave de acceso de AWS

### Azure Key Vault
Almacenamiento de claves gestionado de Microsoft Azure:
- **URL del Vault**: Endpoint de Azure Key Vault
- **ID de tenant**: Tenant de Azure AD
- **ID/Secreto de cliente**: Credenciales del principal de servicio

### Google Cloud KMS
Servicio de gestión de claves de Google Cloud:
- **Proyecto**: ID del proyecto de GCP
- **Ubicación**: Ubicación del anillo de claves KMS
- **Anillo de claves**: Nombre del anillo de claves
- **Credenciales**: Clave JSON de la cuenta de servicio

### OpenBao / Vault Transit
Motor de secretos Transit de OpenBao o HashiCorp Vault. Las claves se gestionan remotamente a través de la API Transit, no se requiere biblioteca PKCS#11.

Configuración:
- **URL**: Dirección del servidor (ej. \`https://openbao.example.com:8200\`)
- **Token**: Token de autenticación
- **Ruta de montaje**: Punto de montaje del motor Transit (predeterminado: \`transit\`)
- **Espacio de nombres**: Espacio de nombres opcional para configuraciones multi-inquilino
- **Omitir verificación TLS**: Omitir verificación de certificado TLS (para certificados autofirmados)

Tipos de claves soportados:
- RSA 2048, 3072, 4096
- ECDSA P-256, P-384, P-521
- ML-DSA-44, ML-DSA-65, ML-DSA-87 (claves Transit \`mldsa-*\`, en una versión de OpenBao que las incluya)
- AES-256-GCM (simétrico)

> 💡 OpenBao es un fork comunitario de HashiCorp Vault. UCM funciona con ambos.

## Gestión de proveedores

### Agregar un proveedor
1. Haga clic en **Agregar proveedor**
2. Seleccione el **tipo de proveedor**
3. Ingrese los detalles de conexión
4. Haga clic en **Probar conexión** para verificar
5. Haga clic en **Guardar**

### Probar conexión
Siempre pruebe la conexión después de crear o modificar un proveedor. UCM verifica que puede comunicarse con el HSM y autenticarse. Para un módulo PKCS#11, la prueba registra también lo que el módulo declara (biblioteca, fabricante, versiones de la biblioteca y del firmware), visible en la página del proveedor.

### Estado del proveedor
Cada proveedor muestra un indicador de estado de conexión:
- **Conectado**: El HSM es accesible y está autenticado
- **Desconectado**: No se puede alcanzar el HSM
- **Error**: Problema de autenticación o configuración

## Gestión de claves

### Generar claves
1. Seleccione un proveedor conectado
2. Haga clic en **Generar clave**
3. Elija el algoritmo (RSA 2048/4096, ECDSA P-256/P-384)
4. Ingrese una etiqueta/alias para la clave
5. Haga clic en **Generar**

La clave se crea directamente en el HSM. UCM almacena solo una referencia.

### Claves ML-DSA
Las claves ML-DSA-44, ML-DSA-65 y ML-DSA-87 (FIPS 204) se ofrecen solo en los proveedores que firman con ellas:
- **PKCS#11**: un token que implemente PKCS#11 3.2 con los mecanismos ML-DSA
- **OpenBao / Vault Transit**: tipos de clave \`mldsa-44\`, \`mldsa-65\` y \`mldsa-87\`
- **Google Cloud KMS**: versiones de clave \`PQ_SIGN_ML_DSA_*\`, mapeadas desde la API de KMS pero aún no probadas con el servicio. KMS firma como máximo 64 KiB de datos, por lo que una CRL mayor no puede firmarse

Los proveedores Azure Key Vault y AWS CloudHSM no contienen ninguna clave ML-DSA, y el modo FIPS rechaza ML-DSA en todos los proveedores. Una clave ML-DSA firma los datos directamente, por lo que no se elige un resumen.

### Uso de claves HSM
Al crear una CA, seleccione un proveedor HSM y una clave en lugar de generar una clave por software. Las operaciones de firma de la CA se realizan en el HSM.

> ⚠ Las claves generadas en un HSM no se pueden exportar. Si pierde el acceso al HSM, pierde las claves.

> 💡 Use SoftHSM para desarrollo y pruebas antes de implementar con HSMs físicos.
`
  }
}
