export default {
  helpContent: {
    title: 'Solicitudes de aprobación',
    subtitle: 'Gestión del flujo de aprobación de certificados',
    overview: 'Revisa y gestiona las solicitudes de aprobación de certificados. Cuando una política requiere aprobación, la emisión del certificado se pausa hasta que el número requerido de aprobadores hayan revisado y aprobado la solicitud.',
    sections: [
      {
        title: 'Ciclo de vida de la solicitud',
        items: [
          { label: 'Pendiente', text: 'En espera de revisión — el certificado aún no puede ser emitido' },
          { label: 'Aprobada', text: 'Todas las aprobaciones requeridas recibidas — el certificado puede ser emitido' },
          { label: 'Rechazada', text: 'Cualquier rechazo detiene inmediatamente la solicitud' },
          { label: 'Expirada', text: 'La solicitud no fue revisada antes de la fecha límite' },
        ]
      },
    ],
    tips: [
      'Cualquier rechazo individual detiene inmediatamente la aprobación — esto es intencional por seguridad.',
      'Los comentarios de aprobación se registran en la pista de auditoría para cumplimiento normativo.',
    ],
  },
  helpGuides: {
    title: 'Solicitudes de aprobación',
    content: `
## Descripción general

La página de Aprobaciones muestra todas las solicitudes de certificados que requieren aprobación manual antes de su emisión. Los flujos de aprobación se configuran en **Políticas** — cuando una política tiene "Requerir aprobación" activado, cualquier solicitud de certificado que coincida crea una solicitud de aprobación aquí.

## Ciclo de vida de la solicitud

### Pendiente
La solicitud está en espera de revisión. El certificado no puede ser emitido hasta que el número requerido de aprobadores lo hayan aprobado. Las solicitudes pendientes aparecen primero por defecto.

### Aprobada
Todas las aprobaciones requeridas han sido recibidas. El certificado se emitirá automáticamente una vez aprobado.

### Rechazada
Cualquier rechazo individual detiene inmediatamente la solicitud. El certificado no será emitido. Se requiere un comentario de rechazo para explicar el motivo.

### Expirada
La solicitud no fue revisada antes de la fecha límite. Las solicitudes expiradas deben ser reenviadas.

## Aprobar una solicitud

1. Haz clic en una solicitud pendiente para ver sus detalles
2. Revisa los detalles del certificado, el solicitante y la política asociada
3. Haz clic en **Aprobar** y opcionalmente añade un comentario
4. La aprobación se registra con tu nombre de usuario y marca de tiempo

## Rechazar una solicitud

1. Haz clic en una solicitud pendiente para ver sus detalles
2. Haz clic en **Rechazar**
3. Introduce un **motivo de rechazo** (obligatorio) — esto se registra para cumplimiento de auditoría
4. La solicitud se detiene inmediatamente

> ⚠ Cualquier rechazo individual detiene toda la solicitud. Esto es intencional — si algún revisor identifica un problema, la emisión no debe proceder.

## Historial de aprobaciones

Cada solicitud mantiene una línea de tiempo completa de aprobaciones que muestra:
- Quién aprobó o rechazó (nombre de usuario)
- Cuándo se realizó la acción (marca de tiempo)
- Comentario proporcionado (si lo hay)

Este historial es inmutable y forma parte de la pista de auditoría.

## Filtrado

Usa la barra de filtro por estado en la parte superior para mostrar:
- **Pendiente** — Solicitudes que esperan tu revisión
- **Aprobada** — Solicitudes aprobadas recientemente
- **Rechazada** — Solicitudes rechazadas con motivos
- **Total** — Todas las solicitudes sin importar el estado

## Permisos

- **read:approvals** — Ver solicitudes de aprobación
- **write:approvals** — Aprobar o rechazar solicitudes

> 💡 Configura notificaciones por email en las políticas para que los aprobadores sean alertados cuando lleguen nuevas solicitudes.
`
  }
}
