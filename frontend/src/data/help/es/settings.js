export default {
  helpContent: {
    title: 'Configuración',
    subtitle: 'Configuración del sistema',
    overview: 'Configure todos los aspectos del sistema UCM. La configuración está organizada por categorías: general, apariencia, correo electrónico, seguridad, SSO, respaldo, auditoría, base de datos, HTTPS, actualizaciones y webhooks.',
    sections: [
      {
        title: 'Categorías',
        items: [
          { label: 'General', text: 'Nombre de instancia, nombre de host y valores predeterminados del sistema' },
          { label: 'Apariencia', text: 'Selección de tema (claro/oscuro/sistema), color de acento, modo escritorio' },
          { label: 'Correo electrónico (SMTP)', text: 'Servidor SMTP, credenciales, editor de plantillas de correo y notificaciones de alerta de expiración' },
          { label: 'Seguridad', text: 'Políticas de contraseña, tiempo de espera de sesión, limitación de velocidad, restricciones de IP' },
          { label: 'SSO', text: 'Integración de inicio de sesión único con SAML 2.0, OAuth2/OIDC y LDAP' },
          { label: 'Respaldo', text: 'Copias de seguridad manuales y programadas de la base de datos' },
          { label: 'Auditoría', text: 'Retención de registros, reenvío a syslog, verificación de integridad' },
          { label: 'Base de datos', text: 'Backend activo (SQLite o PostgreSQL), tamaño, número de tablas, probar/cambiar/migrar entre backends' },
          { label: 'HTTPS', text: 'Certificado TLS para la interfaz web de UCM' },
          { label: 'Actualizaciones', text: 'Buscar nuevas versiones, ver registro de cambios, actualización automática (DEB/RPM)' },
          { label: 'Webhooks', text: 'Webhooks HTTP para eventos de certificados (emisión, revocación, expiración)' },
        ]
      },
    ],
    tips: [
      'Use el widget de Estado del Sistema en la parte superior para verificar rápidamente la salud de los servicios',
      'Pruebe la configuración SMTP antes de depender de las notificaciones por correo electrónico',
      'Personalice la plantilla de correo electrónico con su marca usando el editor HTML/texto integrado',
      'Programe copias de seguridad automáticas para entornos de producción',
    ],
    warnings: [
      'Cambiar el certificado HTTPS requiere un reinicio del servicio',
      'Modificar la configuración de seguridad puede bloquear a los usuarios — verifique el acceso antes de guardar',
    ],
  },
  helpGuides: {
    title: 'Configuración',
    content: `
## Descripción general

Configuración de todo el sistema organizada en pestañas. Los cambios surten efecto inmediatamente a menos que se indique lo contrario.

## General

- **Nombre de instancia** — Se muestra en el título del navegador y en los correos electrónicos
- **Nombre de host** — El nombre de dominio completamente cualificado del servidor
- **Validez predeterminada** — Período de validez predeterminado del certificado en días
- **Umbral de advertencia de expiración** — Días antes de la expiración para activar advertencias

## Apariencia

- **Tema** — Claro, Oscuro o Sistema (sigue la preferencia del SO)
- **Color de acento** — Color principal usado para botones, enlaces y resaltados
- **Forzar modo escritorio** — Desactivar el diseño responsivo para móviles
- **Comportamiento de la barra lateral** — Colapsada o expandida por defecto

## Correo electrónico (SMTP)

Configure SMTP para notificaciones por correo (alertas de expiración, invitaciones de usuario):
- **Host SMTP** y **Puerto**
- **Nombre de usuario** y **Contraseña**
- **Cifrado** — Ninguno, STARTTLS o SSL/TLS
- **Dirección de remitente** — Dirección de correo del remitente
- **Tipo de contenido** — HTML, texto plano o ambos
- **Destinatarios de alertas** — Agregue múltiples destinatarios usando la entrada de etiquetas

Haga clic en **Probar** para enviar un correo de prueba y verificar la configuración.

### Editor de plantillas de correo

Haga clic en **Editar plantilla** para abrir el editor de plantillas de panel dividido en una ventana flotante:
- **Pestaña HTML** — Edite la plantilla HTML del correo con vista previa en tiempo real a la derecha
- **Pestaña Texto plano** — Edite la versión de texto plano para clientes de correo que no soportan HTML
- Variables disponibles: \`{{title}}\`, \`{{content}}\`, \`{{datetime}}\`, \`{{instance_url}}\`, \`{{logo}}\`, \`{{title_color}}\`
- Haga clic en **Restablecer a predeterminado** para restaurar la plantilla con marca UCM incorporada
- La ventana es redimensionable y arrastrable para una edición cómoda

### Alertas de expiración

Cuando SMTP está configurado, active alertas automáticas de expiración de certificados:
- Active/desactive las alertas
- Seleccione umbrales de advertencia (90d, 60d, 30d, 14d, 7d, 3d, 1d)
- Ejecute **Verificar ahora** para activar un escaneo inmediato

## Seguridad

### Política de contraseñas
- Longitud mínima (8-32 caracteres)
- Requerir mayúsculas, minúsculas, números, caracteres especiales
- Expiración de contraseña (días)
- Historial de contraseñas (prevenir reutilización)

### Gestión de sesiones
- Tiempo de espera de sesión (minutos de inactividad)
- Máximo de sesiones concurrentes por usuario

### Limitación de velocidad
- Límite de intentos de inicio de sesión por IP
- Duración del bloqueo después de exceder el límite

### Restricciones de IP
Permitir o denegar acceso desde direcciones IP o rangos CIDR específicos.

### Aplicación de 2FA
Requerir que todos los usuarios activen la autenticación de dos factores.

> ⚠ Pruebe las restricciones de IP cuidadosamente antes de aplicarlas. Las reglas incorrectas pueden bloquear a todos los usuarios.

## SSO (Single Sign-On)

### SAML 2.0
- Proporcione a su IDP la **URL de metadatos SP**: \`/api/v2/sso/saml/metadata\`
- O configure manualmente: cargue/enlace el XML de metadatos del IDP, configure Entity ID y URL ACS
- Mapee atributos del IDP a campos de usuario de UCM (nombre de usuario, correo, rol)

### OAuth2 / OIDC
- URL de autorización y URL de token
- Client ID y Client Secret
- URL de información del usuario (para obtener atributos)
- Scopes (openid, profile, email)
- Crear usuarios automáticamente en el primer inicio de sesión SSO

### LDAP
- Nombre de host del servidor, puerto (389/636), opción SSL
- Bind DN y contraseña (cuenta de servicio)
- Base DN y filtro de usuario
- Mapeo de atributos (nombre de usuario, correo, nombre completo)

> 💡 Siempre mantenga una cuenta de administrador local como respaldo en caso de que SSO falle.

## Respaldo

### Respaldo manual
Haga clic en **Crear respaldo** para generar una instantánea de la base de datos. Los respaldos incluyen todos los certificados, CAs, claves, configuración y registros de auditoría.

### Respaldo programado
Configure copias de seguridad automáticas:
- Frecuencia (diaria, semanal, mensual)
- Cantidad de retención (número de respaldos a conservar)

### Restaurar
Suba un archivo de respaldo para restaurar UCM a un estado anterior.

> ⚠ Restaurar un respaldo reemplaza TODOS los datos actuales.

## Auditoría

- **Retención de registros** — Limpieza automática de registros antiguos después de N días
- **Reenvío a syslog** — Enviar eventos a un servidor syslog remoto (UDP/TCP/TLS)
- **Verificación de integridad** — Activar encadenamiento de hash para detección de manipulación

## Base de datos

UCM admite dos backends de base de datos:

- **SQLite** (predeterminado) — basado en archivo, sin configuración, ideal para nodo único
- **PostgreSQL 13+** — recomendado para alta disponibilidad, multi-instancia o si ya opera un clúster PG gestionado

El backend activo se selecciona mediante la variable de entorno \`DATABASE_URL\`. Si no se establece, UCM usa SQLite en \`UCM_DATA_DIR/ucm.db\`.

### Panel de estado
- Backend activo (sqlite / postgresql) y controlador
- Tamaño de la base de datos y número de tablas
- Versión de migración

### Probar la conexión
Valide una \`DATABASE_URL\` (p. ej. \`postgresql://user:pass@host:5432/ucm\`) antes de cambiar. La prueba abre una conexión real e informa cualquier error. Los servidores PostgreSQL anteriores a la versión 13 son rechazados — UCM requiere PostgreSQL 13 o más reciente.

### Cambiar de backend
Persiste \`DATABASE_URL\` en \`/etc/ucm/ucm.env\` (DEB/RPM) y reinicia UCM. **No se copia ningún dato** — use **Migrar** primero si desea conservar sus datos existentes.

### Migrar datos
Copia todas las filas del backend actual al backend destino. Funciona en ambas direcciones (SQLite ↔ PostgreSQL):

1. La base de datos de origen se respalda en \`/opt/ucm/data/backups/db_migration/\`
2. El esquema se crea en el destino mediante SQLAlchemy
3. Las restricciones FK se desactivan durante la carga masiva
4. Las columnas origen/destino se intersectan (las columnas heredadas se omiten con una advertencia)
5. Las secuencias de PostgreSQL se restablecen después de la carga
6. El servicio se reinicia automáticamente (DEB/RPM) — en Docker, establezca \`DATABASE_URL\` en su archivo compose y reinicie el contenedor manualmente

**Comprobaciones de seguridad (fallo rápido, origen intacto):**
- El destino debe estar vacío. Si \`users\`, \`cas\` o \`certificates\` ya contienen filas, la migración se rechaza con HTTP 409 y una sugerencia de limpieza:
  - PostgreSQL: \`psql ... -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'\`
  - SQLite: elimine el archivo \`.db\` de destino
- Si la migración falla a mitad de camino, el origen permanece intacto y el mensaje de error apunta a la copia de seguridad del origen. Restablezca el destino antes de reintentar.

> ⚠ Realice siempre una copia de seguridad completa de UCM (Configuración → Copia de seguridad) antes de migrar entre backends.

## HTTPS

Administre el certificado TLS usado por la interfaz web de UCM:
- Ver los detalles del certificado actual
- Importar un nuevo certificado (PEM o PKCS#12)
- Generar un certificado autofirmado

> ⚠ Cambiar el certificado HTTPS requiere un reinicio del servicio.

## Actualizaciones

- Buscar nuevas versiones de UCM desde las publicaciones de GitHub
- Ver el registro de cambios de las actualizaciones disponibles
- Versión actual e información de compilación
- **Actualización automática**: en instalaciones compatibles (DEB/RPM), haga clic en **Actualizar ahora** para descargar e instalar la última versión automáticamente
- **Incluir prelanzamientos**: active para verificar también los candidatos de lanzamiento (rc)

## Webhooks

Configure webhooks HTTP para notificar a sistemas externos sobre eventos:

### Eventos soportados
- Certificado emitido, revocado, expirado, renovado
- CA creada, eliminada
- Inicio de sesión del usuario, cierre de sesión
- Respaldo creado

### Crear un webhook
1. Haga clic en **Agregar webhook**
2. Ingrese la **URL** (debe ser HTTPS)
3. Seleccione los **eventos** a los que suscribirse
4. Opcionalmente establezca un **secreto** para verificación de firma HMAC
5. Haga clic en **Crear**

### Pruebas
Haga clic en **Probar** para enviar un evento de ejemplo a la URL del webhook y verificar que sea accesible.
`
  }
}
