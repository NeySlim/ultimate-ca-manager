export default {
  helpContent: {
    title: 'Resumen',
    subtitle: 'Lo que requiere acción y el estado de la PKI',
    overview: 'Seis tarjetas independientes sobre los datos en vivo de su PKI. Cada tarjeta se carga por sí sola y muestra su propio estado de carga, vacío, error o falta de permiso. Cada contador que tiene una lista abre la lista de certificados filtrada exactamente a los certificados que cuenta.',
    sections: [
      {
        title: 'Tarjetas',
        items: [
          { label: 'Por tramitar', text: 'Los seis elementos más urgentes, los críticos primero, cada uno con un enlace a su registro; un nivel plegado da el total por tipo, y los cuatro tipos de renovación abren la lista de certificados' },
          { label: 'Estado de la automatización', text: 'Por protocolo (ACME, SCEP, EST), los éxitos y fallos diarios, y el estado del planificador' },
          { label: 'Jerarquía', text: 'Las autoridades como un árbol bajo su padre, con el estado de CRL y OCSP, una marca de sin conexión o con firma cruzada, y los certificados que cada una emitió en 7 días; cada autoridad abre su página' },
          { label: 'Horizonte de expiración', text: 'Los contadores de por expirar y expirados, cada uno abre su lista, y los cinco certificados que expiran a continuación' },
          { label: 'Cumplimiento', text: 'Certificados activos por algoritmo de clave y debilidad (RSA por debajo de 3072 bits, hash de firma débil, certificados de servidor de más de 398 días, cadena incompleta, sin clave privada); cada contador abre la lista correspondiente' },
          { label: 'Últimas operaciones', text: 'Las cinco operaciones más recientes; con el permiso de auditoría, un enlace abre el registro completo' },
        ]
      },
    ],
    tips: [
      'Elija el preajuste Operador, Responsable o Todas las tarjetas en el encabezado para decidir qué tarjetas se muestran',
      'El diseño se guarda con su cuenta y le sigue en todos los navegadores',
      'En la lista de certificados, los filtros procedentes del resumen aparecen como chips; quite uno con su x',
    ],
  },
  helpGuides: {
    title: 'Panel de control',
    content: `
## Descripción general

El panel de control es su centro de supervisión principal. Muestra métricas en tiempo real, gráficos y alertas sobre toda su infraestructura PKI a través de widgets personalizables.

## Widgets

### Tarjeta de estadísticas
Muestra estos contadores:
- **Certificados**: todos los certificados, expirados y revocados incluidos
- **CA**: Autoridades de certificación raíz e intermedias
- **CSR**: Solicitudes de firma de certificado en espera de firma
- **ACME**: cuentas ACME registradas
- **Certificados SSH**: se muestra cuando existe una CA SSH

### Actividad de certificados
Un gráfico de áreas de los certificados emitidos, revocados y expirados por día durante el período elegido. Pase el cursor sobre los puntos de datos para ver los conteos exactos.

### Distribución de estados
Gráfico circular que muestra el desglose de los estados de los certificados:
- **Válido**: Dentro del período de validez y no revocado
- **Por expirar**: Expira dentro de 30 días
- **Expirado**: Posterior a la fecha «Not After»
- **Revocado**: Revocado explícitamente

### Próxima expiración
Lista los seis certificados válidos que expiran antes, sea cual sea su fecha. Haga clic en cualquier certificado para ir a sus detalles.

### Estado del sistema
Muestra el estado de los servicios de UCM:
- Servidor ACME (activado/desactivado)
- Servidor SCEP
- Protocolo EST (activado/desactivado, CA asignada)
- Auto-regeneración de CRL con recuento de CDP
- Respondedor OCSP
- TSA, SMTP y webhooks
- Estado de la renovación automática

El panel de estado del sistema muestra también la conexión WebSocket, la base de datos, la API y la hora de la última actualización.

### Actividad reciente
Un flujo en directo de las últimas operaciones: emisión de certificados, revocaciones, importaciones, inicios de sesión de usuarios. Se actualiza en tiempo real mediante WebSocket. El flujo completo requiere **read:audit**, como la página de registros de auditoría; sin él, solo ve sus propios eventos.

### Autoridades de certificación
Vista rápida de las últimas CA, cada una marcada como Root o Sub.

### Expiración del almacén de confianza
Certificados de confianza que expiran antes.

### Cuentas ACME
Lista las cuentas de clientes ACME registradas y su número de pedidos.

## Personalización

### Reorganizar widgets
Haga clic en **Editar diseño** en el encabezado de la página y arrastre cualquier widget por su encabezado para reposicionarlo. El diseño utiliza una cuadrícula adaptable que se ajusta al tamaño de su pantalla.

### Mostrar/ocultar widgets
Haga clic en **Personalizar** (icono de controles deslizantes) en el encabezado de la página y luego en el ojo junto a un widget para alternar su visibilidad. Los widgets ocultos se recuerdan entre sesiones.

### Persistencia del diseño
Su diseño se guarda en el navegador, no en su cuenta: todas las cuentas que inician sesión desde el mismo perfil de navegador lo comparten, y otro navegador parte del diseño predeterminado.

## Actualizaciones en tiempo real
El panel de control recibe actualizaciones en directo mediante WebSocket. No es necesario actualizar manualmente: los nuevos certificados, cambios de estado y entradas de actividad aparecen automáticamente.

> 💡 El punto verde de la barra lateral indica una conexión WebSocket activa y desaparece si se corta. Los datos se actualizarán al reconectarse.
`
  }
}
