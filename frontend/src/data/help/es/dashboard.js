export default {
  helpContent: {
    title: 'Panel de control',
    subtitle: 'Vista general del sistema y supervisión',
    overview: 'Vista general en tiempo real de su infraestructura PKI. Los widgets muestran el estado de los certificados, las alertas de expiración, el estado del sistema y la actividad reciente. El diseño es totalmente personalizable con arrastrar y soltar.',
    sections: [
      {
        title: 'Widgets',
        items: [
          { label: 'Estadísticas', text: 'Total de certificados (expirados y revocados incluidos), CA, CSR pendientes y cuentas ACME, más los certificados SSH cuando existe una CA SSH' },
          { label: 'Actividad de certificados', text: 'Certificados emitidos, revocados y expirados por día durante el período elegido' },
          { label: 'Distribución de estados', text: 'Gráfico circular: válido / por expirar / expirado / revocado' },
          { label: 'Próxima expiración', text: 'Los seis certificados válidos que expiran antes, sea cual sea su fecha; el firmante TSA dedicado configurado se identifica con un chip "TSA signer" (v2.218)' },
          { label: 'Estado del sistema', text: 'Estado de los servicios: ACME, SCEP, EST, OCSP, CRL/CDP, TSA (v2.218), renovación automática, SMTP y webhooks. Las insignias muestran un estado de advertencia ámbar diferenciado (firmante TSA próximo a expirar, SMTP configurado pero desactivado) y su mensaje de estado al pasar el cursor' },
          { label: 'Actividad reciente', text: 'Últimas operaciones en todo el sistema con read:audit; sin él, solo sus propios eventos' },
          { label: 'Certificados recientes', text: 'Certificados emitidos o importados recientemente' },
          { label: 'Autoridades de certificación', text: 'Últimas CA, cada una marcada como Root o Sub' },
          { label: 'Cuentas ACME', text: 'Cuentas de clientes ACME registradas' },
          { label: 'Expiración del almacén de confianza', text: 'Certificados de confianza que expiran antes' },
        ]
      },
    ],
    tips: [
      'Haga clic en Editar diseño en el encabezado y arrastre los widgets para reorganizarlos',
      'Haga clic en el botón Personalizar (icono de controles deslizantes) en el encabezado y luego en el ojo junto a un widget para mostrarlo u ocultarlo',
      'El panel de control se actualiza en tiempo real mediante WebSocket, no es necesario actualizar manualmente',
      'El diseño se guarda en este navegador, para todas las cuentas que inician sesión desde él',
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
