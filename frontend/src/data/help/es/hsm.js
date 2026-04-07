export default {
  helpContent: {
    title: 'Módulos de Seguridad de Hardware',
    subtitle: 'Almacenamiento externo de claves',
    overview: 'Integre con Módulos de Seguridad de Hardware para el almacenamiento seguro de claves privadas. Soporte para PKCS#11, AWS CloudHSM, Azure Key Vault y Google Cloud KMS.',
    sections: [
      {
        title: 'Proveedores compatibles',
        definitions: [
          { term: 'PKCS#11', description: 'Interfaz HSM estándar de la industria (Thales, Entrust, SoftHSM)' },
          { term: 'AWS CloudHSM', description: 'HSM basado en la nube de Amazon Web Services' },
          { term: 'Azure Key Vault', description: 'Almacenamiento de claves gestionado de Microsoft Azure' },
          { term: 'Google KMS', description: 'Servicio de gestión de claves de Google Cloud' },
        ]
      },
      {
        title: 'Acciones',
        items: [
          { label: 'Agregar proveedor', text: 'Configurar la conexión a un HSM (ruta de biblioteca, credenciales, slot)' },
          { label: 'Probar conexión', text: 'Verificar que el HSM es accesible y las credenciales son válidas' },
          { label: 'Generar clave', text: 'Crear un nuevo par de claves directamente en el HSM' },
          { label: 'Estado', text: 'Monitorear el estado de conexión del proveedor' },
        ]
      },
    ],
    tips: [
      'Use SoftHSM para pruebas antes de implementar con un HSM físico',
      'Las claves generadas en un HSM nunca salen del hardware — no se pueden exportar',
      'Pruebe la conexión antes de usar un proveedor HSM para la firma de CA',
    ],
    warnings: [
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

> 💡 **Docker**: SoftHSM viene preinstalado en la imagen Docker. Al primer inicio, se inicializa automáticamente un token predeterminado y se registra como el proveedor \`SoftHSM-Default\` — listo para usar de inmediato.

Configuración:
- **Ruta de biblioteca** — Ruta a la biblioteca compartida PKCS#11 (.so/.dll)
- **Slot** — Número de slot del HSM
- **PIN** — PIN de usuario para autenticación

### AWS CloudHSM
HSM basado en la nube de Amazon Web Services:
- **ID de clúster** — Identificador del clúster CloudHSM
- **Región** — Región de AWS
- **Credenciales** — Clave de acceso y secreto de AWS

### Azure Key Vault
Almacenamiento de claves gestionado de Microsoft Azure:
- **URL del Vault** — Endpoint de Azure Key Vault
- **ID de tenant** — Tenant de Azure AD
- **ID/Secreto de cliente** — Credenciales del principal de servicio

### Google Cloud KMS
Servicio de gestión de claves de Google Cloud:
- **Proyecto** — ID del proyecto de GCP
- **Ubicación** — Ubicación del anillo de claves KMS
- **Anillo de claves** — Nombre del anillo de claves
- **Credenciales** — Clave JSON de la cuenta de servicio

## Gestión de proveedores

### Agregar un proveedor
1. Haga clic en **Agregar proveedor**
2. Seleccione el **tipo de proveedor**
3. Ingrese los detalles de conexión
4. Haga clic en **Probar conexión** para verificar
5. Haga clic en **Guardar**

### Probar conexión
Siempre pruebe la conexión después de crear o modificar un proveedor. UCM verifica que puede comunicarse con el HSM y autenticarse.

### Estado del proveedor
Cada proveedor muestra un indicador de estado de conexión:
- **Conectado** — El HSM es accesible y está autenticado
- **Desconectado** — No se puede alcanzar el HSM
- **Error** — Problema de autenticación o configuración

## Gestión de claves

### Generar claves
1. Seleccione un proveedor conectado
2. Haga clic en **Generar clave**
3. Elija el algoritmo (RSA 2048/4096, ECDSA P-256/P-384)
4. Ingrese una etiqueta/alias para la clave
5. Haga clic en **Generar**

La clave se crea directamente en el HSM. UCM almacena solo una referencia.

### Uso de claves HSM
Al crear una CA, seleccione un proveedor HSM y una clave en lugar de generar una clave por software. Las operaciones de firma de la CA se realizan en el HSM.

> ⚠ Las claves generadas en un HSM no se pueden exportar. Si pierde el acceso al HSM, pierde las claves.

> 💡 Use SoftHSM para desarrollo y pruebas antes de implementar con HSMs físicos.
`
  }
}
