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
    title: 'Resumen',
    content: `
## Descripción general

El Resumen es la página de inicio: seis tarjetas independientes sobre los datos en vivo de su PKI. Cada tarjeta se carga por sí sola y muestra su propio estado de carga, vacío, error o falta de permiso.

## Tarjetas

### Por tramitar
Los seis elementos más urgentes, los críticos primero, cada uno con un enlace a su registro. Un nivel plegado da el total por tipo; los cuatro tipos de renovación abren la lista de certificados.

### Estado de la automatización
Por protocolo (ACME, SCEP, EST), los éxitos y fallos diarios y la última operación, además del estado del planificador.

### Jerarquía
Las autoridades como un árbol bajo su padre, con el estado de CRL y OCSP, una marca de sin conexión o con firma cruzada, y los certificados que cada una emitió en 7 días. Cada autoridad abre su página.

### Horizonte de expiración
Los contadores de por expirar y expirados, cada uno abre su lista, y los cinco certificados que expiran a continuación.

### Cumplimiento
Certificados activos por algoritmo de clave y debilidad: RSA por debajo de 3072 bits, hash de firma débil, certificados de servidor de más de 398 días, cadena incompleta, sin clave privada. Cada contador abre la lista correspondiente.

### Últimas operaciones
Las cinco operaciones más recientes. Sin **read:audit** solo ve sus propios eventos; con él, un enlace abre el registro completo en la página de registros de auditoría.

## Abrir una lista filtrada
Cada contador que tiene una lista abre la página de certificados filtrada exactamente a los certificados que cuenta. El filtro aparece como un chip sobre la tabla; quítelo con su x.

## Elegir las tarjetas
Elija el preajuste **Operador**, **Responsable** o **Todas las tarjetas** en el encabezado de la página para decidir qué tarjetas se muestran. El diseño se guarda con su cuenta y le sigue en todos los navegadores.

## Actualización
Las tarjetas se cargan al abrir la página; una tarjeta con error ofrece **Reintentar**. El icono de conexión de la barra superior muestra el estado del enlace en directo, y la barra de estado inferior muestra la versión y si el servicio responde.
`
  }
}
