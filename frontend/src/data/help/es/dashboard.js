export default {
  helpContent: {
    title: 'Panel de control',
    subtitle: 'Vista general del sistema y supervisión',
    overview: 'Vista general en tiempo real de su infraestructura PKI. Los widgets muestran el estado de los certificados, las alertas de expiración, el estado del sistema y la actividad reciente. El diseño es totalmente personalizable con arrastrar y soltar.',
    sections: [
      {
        title: 'Widgets',
        items: [
          { label: 'Estadísticas', text: 'Total de CA, certificados activos, CSR pendientes y cantidad próximos a expirar' },
          { label: 'Tendencia de certificados', text: 'Gráfico del historial de emisión a lo largo del tiempo' },
          { label: 'Distribución de estados', text: 'Gráfico circular: válido / por expirar / expirado / revocado' },
          { label: 'Próxima expiración', text: 'Certificados que expiran dentro de 30 días' },
          { label: 'Estado del sistema', text: 'Estado de los servicios: ACME, SCEP, EST, OCSP, CRL/CDP, estado de renovación automática' },
          { label: 'Actividad reciente', text: 'Últimas operaciones en todo el sistema' },
          { label: 'Certificados recientes', text: 'Certificados emitidos o importados recientemente' },
          { label: 'Autoridades de certificación', text: 'Lista de CA con información de la cadena' },
          { label: 'Cuentas ACME', text: 'Cuentas de clientes ACME registradas' },
        ]
      },
    ],
    tips: [
      'Arrastre los widgets para reorganizar el diseño de su panel de control',
      'Haga clic en el icono del ojo en el encabezado para mostrar/ocultar widgets específicos',
      'El panel de control se actualiza en tiempo real mediante WebSocket — no es necesario actualizar manualmente',
      'El diseño se guarda por usuario y persiste entre sesiones',
    ],
  },
  helpGuides: {
    title: 'Panel de control',
    content: `
## Descripción general

El panel de control es su centro de supervisión principal. Muestra métricas en tiempo real, gráficos y alertas sobre toda su infraestructura PKI a través de widgets personalizables.

## Widgets

### Tarjeta de estadísticas
Muestra cuatro contadores clave:
- **Total de CA** — Autoridades de certificación raíz e intermedias
- **Certificados activos** — Certificados válidos y no revocados
- **CSR pendientes** — Solicitudes de firma de certificado en espera de aprobación
- **Próximos a expirar** — Certificados que expiran dentro de 30 días

### Tendencia de certificados
Un gráfico de líneas que muestra la emisión de certificados a lo largo del tiempo. Pase el cursor sobre los puntos de datos para ver los conteos exactos.

### Distribución de estados
Gráfico circular que muestra el desglose de los estados de los certificados:
- **Válido** — Dentro del período de validez y no revocado
- **Por expirar** — Expira dentro de 30 días
- **Expirado** — Posterior a la fecha «Not After»
- **Revocado** — Revocado explícitamente

### Próxima expiración
Lista los certificados que expiran más pronto. Haga clic en cualquier certificado para ir a sus detalles. Configure el umbral en **Configuración → General**.

### Estado del sistema
Muestra el estado de los servicios de UCM:
- Servidor ACME (activado/desactivado)
- Servidor SCEP
- Protocolo EST (activado/desactivado, CA asignada)
- Auto-regeneración de CRL con recuento de CDP
- Respondedor OCSP
- Estado de la renovación automática
- Tiempo de actividad del servicio

### Actividad reciente
Un flujo en directo de las últimas operaciones: emisión de certificados, revocaciones, importaciones, inicios de sesión de usuarios. Se actualiza en tiempo real mediante WebSocket.

### Autoridades de certificación
Vista rápida de todas las CA con su tipo (raíz/intermedia) y recuento de certificados.

### Cuentas ACME
Lista las cuentas de clientes ACME registradas y su número de pedidos.

## Personalización

### Reorganizar widgets
Arrastre cualquier widget por su encabezado para reposicionarlo. El diseño utiliza una cuadrícula adaptable que se ajusta al tamaño de su pantalla.

### Mostrar/ocultar widgets
Haga clic en el **icono del ojo** en el encabezado de la página para alternar la visibilidad de cada widget. Los widgets ocultos se recuerdan entre sesiones.

### Persistencia del diseño
Su configuración de diseño se guarda por usuario en el navegador. Persiste entre sesiones y dispositivos que comparten el mismo perfil de navegador.

## Actualizaciones en tiempo real
El panel de control recibe actualizaciones en directo mediante WebSocket. No es necesario actualizar manualmente — los nuevos certificados, cambios de estado y entradas de actividad aparecen automáticamente.

> 💡 Si el WebSocket se desconecta, aparece un indicador amarillo en la barra lateral. Los datos se actualizarán al reconectarse.
`
  }
}
