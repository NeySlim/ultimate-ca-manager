export default {
  helpContent: {
    title: 'Descubrimiento de certificados',
    subtitle: 'Encontrar certificados TLS en la red',
    overview: 'Escanear la red para encontrar los certificados TLS desplegados en servidores y puntos finales, y contrastarlos con el inventario de la PKI gestionada. Localizar certificados sin seguimiento, detectar cambios y vigilar los certificados que expiran fuera del control de UCM.',
    sections: [
      {
        title: 'Vistas',
        items: [
          { label: 'Análisis', text: 'La página se abre en los análisis, uno por perfil de escaneo: su rango, lo que encontró su última ejecución y cuándo, y el estado de esa ejecución (Completado, Fallido, En curso, Programado, Nunca ejecutado). Un nombre lo abre en el panel, con Analizar ahora, Editar… y Eliminar…' },
          { label: 'Certificados encontrados', text: 'Todos los certificados que se toparon los escaneos, con host, emisor, expiración y estado; la búsqueda, los chips de estado y el filtro de análisis los aplica el servidor' },
          { label: 'Historial de ejecuciones', text: 'Todas las ejecuciones, de un análisis o de un escaneo rápido, la más reciente primero, con lo que encontró, los objetivos escaneados y su duración' },
        ]
      },
      {
        title: 'Escaneo',
        items: [
          { label: 'Escaneo rápido', text: 'Escaneo puntual sin guardar un perfil: introducir objetivos y puertos, los resultados llegan en directo' },
          { label: 'Objetivos', text: 'Uno por línea, o separados por comas: nombre de host, IP, rango IPv4 (192.0.2.0/24) o host:puerto (mail.example.com:465). Un comodín DNS (*.example.com), un rango IPv6 y un rango IPv4 de más de 65 536 hosts se rechazan en el formulario: el escáner no alcanza ningún host en los dos primeros y rechaza el tercero' },
          { label: 'Puertos', text: 'Puertos TCP separados por comas (por ejemplo 443, 8443, 636), o el preajuste de puertos habituales' },
          { label: 'Opciones avanzadas', text: 'Resolución DNS inversa (registros PTR), tiempo de espera y concurrencia' },
          { label: 'Programación', text: 'Los perfiles se ejecutan manualmente o de forma automática cada 1h / 6h / 12h / 24h / 7d' },
          { label: 'Notificaciones', text: 'Alertas por correo ante certificados nuevos, cambios de certificado o expiraciones próximas. Un certificado encontrado mediante SNI en un objetivo IP se cuenta como nuevo en cada escaneo' },
        ]
      },
      {
        title: 'Estados de los resultados',
        items: [
          { label: 'En UCM', text: 'La huella SHA-256 del certificado coincide con un certificado del inventario de UCM' },
          { label: 'Desconocido para UCM', text: 'Encontrado en la red pero no en el inventario, un candidato para pasar a la gestión' },
          { label: 'Con error', text: 'El punto final respondió pero falló su negociación TLS o su certificado (SNI rechazado, certificado ilegible). Una conexión rechazada, un tiempo de espera agotado o un fallo de DNS o de red no dejan ninguna fila. Reintentar una fila, o Reintentar errores en la página actual' },
          { label: 'Cambiado', text: 'Un punto final que presenta un certificado distinto del escaneo anterior se marca con una marca de tiempo de Último cambio' },
        ]
      },
    ],
    tips: [
      'Filtrar los certificados encontrados con los chips de estado: Todos, En UCM, Desconocido para UCM, Con error',
      'Exportar descarga, como CSV, los certificados encontrados que muestran los filtros de búsqueda, estado y análisis',
      'Programar un escaneo diario de las subredes de servidores con la notificación de certificados nuevos activada',
    ],
    warnings: [
      'Ejecutar escaneos y gestionar perfiles requiere permisos de administrador; la subred de un perfil está limitada a 1024 direcciones (/22), un CIDR introducido como objetivo a 65 536 hosts',
    ],
  },
  helpGuides: {
    title: 'Descubrimiento de certificados',
    content: `
## Visión general

El descubrimiento de certificados escanea la red para encontrar los certificados TLS desplegados en servidores y puntos finales, y los contrasta con el inventario de la PKI gestionada. Usarlo para localizar certificados sin seguimiento, detectar cambios y vigilar los certificados que expiran fuera del control de UCM.

## Vistas

### Análisis
La página se abre en los análisis, uno por perfil de escaneo: su rango, lo que encontró su última ejecución y cuándo, y el estado de esa ejecución (**Completado**, **Fallido**, **En curso**, **Programado**, **Nunca ejecutado**). Un nombre abre el análisis en el panel: **Vista general** da sus propiedades y su descripción, **Ejecuciones** sus ejecuciones; **Analizar ahora**, **Editar…** y **Eliminar…** requieren admin:system. **Nuevo análisis…** crea uno.

### Certificados encontrados
Todos los certificados que se toparon los escaneos, con host, emisor, expiración y estado. Un nombre abre el certificado en el panel: su sujeto, emisor, validez, extensiones y huellas y, para uno con error, el error y una pista sobre su causa.

### Historial de ejecuciones
Todas las ejecuciones, de un análisis o de un escaneo rápido, la más reciente primero, con lo que encontró, los objetivos escaneados y su duración.

## Escaneo rápido

Ejecutar un escaneo puntual sin guardar un perfil:

1. Hacer clic en **Análisis rápido…**
2. Introducir el **rango**, un objetivo por línea o separados por comas: nombre de host, IP, rango IPv4 (\`192.0.2.0/24\`), o \`host:puerto\` (\`mail.example.com:465\`). Un comodín DNS, un rango IPv6 y un rango IPv4 de más de 65 536 hosts se rechazan en el formulario
3. Introducir los **puertos**: puertos TCP separados por comas (por ejemplo \`443, 8443, 636\`), o elegir el preajuste de puertos habituales
4. Opcionalmente, ajustar las **opciones avanzadas**: resolución DNS inversa (registros PTR), tiempo de espera, concurrencia
5. Hacer clic en **Iniciar escaneo**: el progreso se actualiza en directo mediante WebSocket

## Perfiles de escaneo

Los perfiles guardan una configuración de objetivos para usarla repetidamente:

- **Objetivos y puertos**: los mismos formatos que en el escaneo rápido
- **Programación**: manual, o automática cada 1h / 6h / 12h / 24h / 7d
- **Notificaciones**: alertas por correo cuando se descubren certificados nuevos, cuando cambia un certificado en un punto final, o cuando los certificados descubiertos están por expirar. Un certificado encontrado mediante SNI en un objetivo IP se cuenta como nuevo en cada escaneo

Ejecutar un análisis a demanda con **Analizar ahora** en su panel, o dejar que el planificador lo ejecute en el intervalo configurado.

## Estados de los resultados

- **En UCM**: la huella SHA-256 del certificado coincide con un certificado del inventario de UCM
- **Desconocido para UCM**: encontrado en la red pero no en el inventario: un candidato para pasar a la gestión
- **Con error**: el punto final respondió pero falló su negociación TLS o su certificado (SNI rechazado, certificado ilegible). Una conexión rechazada, un tiempo de espera agotado o un fallo de DNS o de red no se registran

### Detección de cambios
Cuando un punto final presenta un certificado distinto del escaneo anterior, el cambio se registra (se conserva la huella anterior, con la marca de tiempo de **Último cambio**) y puede desencadenar una notificación.

## Filtrado y exportación

- **Chips de estado**: Todos, En UCM, Desconocido para UCM, Con error
- **Filtro de perfil**: limitar los resultados a un perfil de escaneo
- **Exportar**: descargar, como CSV, los certificados encontrados que muestran los filtros de búsqueda, estado y análisis
- **Reintentar**: volver a escanear objetivos con error concretos, o **Reintentar errores** mostrados en la página actual
- **Resolver DNS**: resolución DNS inversa en bloque de las IP descubiertas

## Límites y seguridad

- La subred de un perfil está limitada a 1024 direcciones (el equivalente de un /22 IPv4), un CIDR introducido como objetivo a 65 536 hosts; hasta 1000 objetivos por escaneo de perfil
- Los rangos privados RFC1918 y el loopback se pueden escanear: es el modelo de despliegue local de UCM; los rangos de enlace local, multidifusión y reservados están bloqueados
- Los escaneos iniciados a mano y los cambios de perfil se registran en la auditoría; las ejecuciones programadas no

## Permisos

- **read:certificates**: ver los certificados descubiertos, los perfiles y el historial
- **admin:system**: crear o editar perfiles y ejecutar escaneos
- **delete:certificates**: eliminar los resultados descubiertos

> 💡 Programar un escaneo diario de las subredes de servidores y activar la notificación de certificados nuevos: detecta los certificados desplegados al margen del proceso de la PKI.
`
  },
}
