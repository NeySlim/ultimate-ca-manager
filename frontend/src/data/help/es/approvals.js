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
          { label: 'Expirada', text: 'No decidida en siete días; cerrada como expirada y nunca contada como pendiente' },
        ]
      },
      {
        title: 'De dónde vienen las solicitudes',
        items: [
          { label: 'Formulario de emisión', text: 'Una solicitud de certificado que coincide con una política que requiere aprobación' },
          { label: 'Firmar CSR y firma masiva', text: 'Firmar una solicitud almacenada, sola o desde Operaciones, se encola del mismo modo; la aprobación realiza la firma' },
          { label: 'Renovación', text: 'Renovar un certificado, solo o de forma masiva, también se encola; una renovación que no podría atenderse (revocado, clave no en poder del servidor) se rechaza de inmediato' },
          { label: 'Administradores', text: 'Omiten la cola en todas las rutas, como en el formulario de emisión' },
        ]
      },
      {
        title: 'Solicitudes cerradas en tu lugar',
        items: [
          { label: 'Firmada o renovada directamente', text: 'Una solicitud en cola cuyo objetivo un administrador firmó o renovó entretanto se cierra como aprobada por esa acción y se vincula al certificado' },
          { label: 'Eliminado o revocado', text: 'Una solicitud cuyo objetivo fue eliminado o revocado se cierra como rechazada; una suspensión de certificado mantiene la solicitud de renovación en espera hasta que se levante la suspensión' },
          { label: 'Ya satisfecha', text: 'Aprobar una solicitud ya atendida la cierra sobre el certificado existente; aprobar una de varias solicitudes para el mismo objetivo cierra las demás como aprobadas por ti' },
          { label: 'Objetivo desaparecido', text: 'Aprobar una solicitud cuya solicitud almacenada, certificado o CA ya no existe la cierra como rechazada' },
          { label: 'Fecha límite', text: 'Una solicitud espera siete días; pasado ese plazo se cierra como expirada, nunca se cuenta como pendiente y el planificador de renovaciones se reanuda para su certificado' },
        ]
      },
    ],
    tips: [
      'Cualquier rechazo individual detiene inmediatamente la aprobación — esto es intencional por seguridad.',
      'Mientras una renovación espera aprobación, el planificador deja el certificado a esa decisión, siempre que pueda llegar antes de que expire el certificado.',
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
La solicitud no fue decidida en siete días. Las solicitudes expiradas deben ser reenviadas.

## De dónde vienen las solicitudes
Más allá del formulario de emisión, una política que requiere aprobación también encola:
- **Firmar CSR** y **firma masiva** desde Operaciones: la aprobación realiza la firma
- **Renovar** y **renovación masiva**: la aprobación realiza la renovación; una renovación que no podría atenderse (certificado revocado, clave no en poder del servidor) se rechaza de inmediato en lugar de encolarse

Los administradores omiten la cola en todas las rutas.

## Solicitudes cerradas en tu lugar
- Una solicitud en cola cuyo objetivo un administrador **firmó o renovó directamente** entretanto se cierra como aprobada por esa acción y se vincula al certificado
- Una solicitud cuyo objetivo fue **eliminado o revocado** se cierra como rechazada; una suspensión de certificado mantiene la solicitud de renovación en espera hasta que se levante la suspensión
- Aprobar una solicitud **ya satisfecha** la cierra sobre el certificado existente; aprobar una de varias solicitudes para el mismo objetivo cierra las demás como aprobadas por ti
- Aprobar una solicitud cuya solicitud almacenada, certificado o CA **ya no existe** la cierra como rechazada

Los webhooks reciben aviso de estos cierres igual que de un rechazo.

## Fecha límite
Una solicitud espera **siete días** una decisión. Pasado ese plazo se cierra como expirada, nunca se cuenta como pendiente y el planificador de renovaciones se reanuda para su certificado. Mientras una renovación espera aprobación, el planificador deja el certificado a esa decisión, siempre que pueda llegar antes de que expire el certificado.

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
