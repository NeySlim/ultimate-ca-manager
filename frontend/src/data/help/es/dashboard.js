export default {
  helpContent: {
    title: 'Overview',
    subtitle: 'What needs action, and the state of the PKI',
    overview: 'Six independent cards over the live data of your PKI. Each card loads on its own and shows its own loading, empty, error or missing-permission state. Every counter that has a list opens the certificate list filtered to exactly the certificates it counts.',
    sections: [
      {
        title: 'Cards',
        items: [
          { label: 'To handle', text: 'The six most urgent items, critical first, each linking to its record; a folded tier gives the total per kind, and the four renewal kinds open the certificate list' },
          { label: 'Automation health', text: 'Per protocol (ACME, SCEP, EST) the daily successes and failures, and the scheduler state' },
          { label: 'Hierarchy', text: 'The authorities as a tree under their parent, with CRL and OCSP state and the certificates each issued over 7 days; each authority opens its page' },
          { label: 'Expiry horizon', text: 'The expiring and expired counters, each opening its list, and the five certificates that expire next' },
          { label: 'Compliance', text: 'Live certificates by key algorithm and weakness (RSA below 3072 bits, weak signature hash, server certificates over 398 days, incomplete chain, no private key); each counter opens the matching list' },
          { label: 'Latest operations', text: 'The five most recent operations; with the audit permission, a link opens the whole trail' },
        ]
      },
    ],
    tips: [
      'Pick the Operator, Manager or All cards preset in the header to choose which cards are shown',
      'The layout is saved with your account and follows you across browsers',
      'On the certificate list, filters coming from the overview appear as chips; remove one with its x',
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
