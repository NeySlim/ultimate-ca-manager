export default {
  helpContent: {
    title: 'Solicitudes de aprobación',
    subtitle: 'Gestión del flujo de aprobación de certificados',
    overview: 'Revisar y gestionar las solicitudes de aprobación de certificados. Cuando una política exige aprobación, la emisión del certificado queda en pausa hasta que el número requerido de aprobadores haya revisado y aprobado la solicitud.',
    sections: [
      {
        title: 'Ciclo de vida de una solicitud',
        items: [
          { label: 'Pendiente', text: 'A la espera de revisión, el certificado aún no puede emitirse' },
          { label: 'Aprobada', text: 'Se recibieron todas las aprobaciones requeridas, el certificado puede emitirse' },
          { label: 'Rechazada', text: 'Cualquier rechazo detiene la solicitud de inmediato' },
          { label: 'Expirada', text: 'Sin decisión en siete días; se cierra como expirada y nunca se cuenta como pendiente' },
          { label: 'Cancelada', text: 'Su solicitante realizó la acción directamente o aprobó un duplicado: nadie aprueba su propia solicitud' },
        ]
      },
      {
        title: 'De dónde vienen las solicitudes',
        items: [
          { label: 'Formulario de emisión', text: 'Una solicitud de certificado que coincide con una política que exige aprobación' },
          { label: 'Firma de CSR y firma masiva', text: 'Firmar una solicitud almacenada, sola o desde Operaciones, se pone en cola de la misma manera; la aprobación realiza la firma' },
          { label: 'Renovación', text: 'Renovar un certificado, solo o en masa, también se pone en cola; una renovación que no puede atenderse (revocada, clave no custodiada por el servidor) se rechaza de inmediato' },
          { label: 'Revocación', text: 'Revocar un certificado (solo, en masa, desde los certificados de usuario) o una CA intermedia bajo una política de revocación se pone en cola; la aprobación revoca con el motivo solicitado' },
          { label: 'Planificador', text: 'Bajo una política de renovación, el planificador pone la renovación en cola; la aprobación vuelve a firmar la clave que el servidor custodia, como lo habría hecho el planificador' },
          { label: 'Protocolos de inscripción', text: 'Una finalización ACME, una inscripción EST, una reinscripción o la generación de clave en el servidor, una solicitud SCEP (incluso en un perfil de aprobación automática) o una inscripción o renovación WSTEP bajo una política que exige aprobación queda retenida: se informa al cliente de que la solicitud está pendiente y consulta periódicamente; la aprobación emite el certificado a través de ese protocolo, y un rechazo o una expiración se comunican al cliente como una denegación' },
          { label: 'Administradores', text: 'Saltan la cola en todas las vías, como en el formulario de emisión' },
        ]
      },
      {
        title: 'Solicitudes cerradas automáticamente',
        items: [
          { label: 'Firmada o renovada directamente', text: 'Una solicitud en cola cuyo objetivo un administrador firmó o renovó entretanto se cierra como aprobada por esa acción y se vincula al certificado' },
          { label: 'Eliminada o revocada', text: 'Una solicitud cuyo objetivo fue eliminado o revocado se cierra como rechazada; una suspensión de certificado mantiene la solicitud de renovación en espera hasta que se levante' },
          { label: 'Ya satisfecha', text: 'Aprobar una solicitud ya cumplida la cierra sobre el certificado existente; aprobar una de varias solicitudes para el mismo objetivo cierra las demás como aprobadas por el aprobador' },
          { label: 'Objetivo desaparecido', text: 'Aprobar una solicitud cuya solicitud almacenada, certificado o CA ya no existe la cierra como rechazada' },
          { label: 'Revocado o renovado entretanto', text: 'Una revocación en cola cuyo certificado fue revocado directamente se cierra como aprobada; aquella cuyo certificado se renovó desde entonces se cierra como rechazada al aprobarla' },
          { label: 'Plazo', text: 'Una solicitud espera siete días; pasado ese plazo se cierra como expirada, nunca se cuenta como pendiente, y el planificador de renovaciones se reanuda para su certificado' },
        ]
      },
    ],
    tips: [
      'Un solo rechazo detiene de inmediato la aprobación: es intencionado por seguridad. Un rechazo pide un motivo de al menos cinco caracteres.',
      'Mientras una renovación espera aprobación, el planificador deja el certificado a esa decisión, siempre que pueda llegar antes de que el certificado caduque; bajo una política de renovación nunca renueva sin ella.',
      'Cada decisión y su comentario se conservan en la cronología de aprobación de la solicitud; el registro de auditoría anota las aprobaciones, no el comentario, ni una solicitud en cola ni un rechazo.',
    ],
  },
  helpGuides: {
    title: 'Solicitudes de aprobación',
    content: `
## Visión general

La página Aprobaciones muestra todas las solicitudes de certificado que requieren aprobación manual antes de la emisión. Los flujos de aprobación se configuran en **Políticas**: cuando una política tiene activada la opción de exigir aprobación, cualquier solicitud de certificado que coincida crea aquí una solicitud de aprobación.

## Ciclo de vida de una solicitud

### Pendiente
La solicitud espera revisión. El certificado no puede emitirse hasta que el número requerido de aprobadores la haya aprobado. Las solicitudes pendientes aparecen primero por defecto.

### Aprobada
Se recibieron todas las aprobaciones requeridas. El certificado se emitirá automáticamente una vez aprobada.

### Rechazada
Un solo rechazo detiene la solicitud de inmediato. El certificado no se emitirá. Se requiere un comentario de rechazo que explique el motivo.

### Expirada
La solicitud no se decidió en siete días. Las solicitudes expiradas deben volver a presentarse.

### Cancelada
Su solicitante realizó la acción directamente, o aprobó otra solicitud para el mismo objetivo: nadie aprueba su propia solicitud, por lo que se cierra sin voto.

## De dónde vienen las solicitudes
Además del formulario de emisión, una política que exige aprobación también pone en cola:
- La **firma de CSR** y la **firma masiva** desde Operaciones: la aprobación realiza la firma
- **Renovar** y **renovar en masa**: la aprobación realiza la renovación; una renovación que no puede atenderse (certificado revocado, clave no custodiada por el servidor) se rechaza de inmediato en lugar de ponerse en cola
- **Revocar** (un certificado, en masa, un certificado de usuario, una CA intermedia) bajo una política de revocación: la aprobación revoca con el motivo y la fecha de invalidez solicitados, tras una nueva comprobación (un certificado renovado desde la solicitud no se revoca)
- El **planificador de renovaciones**, bajo una política de renovación: pone la renovación en cola una vez, y la aprobación la realiza como lo habría hecho el planificador

Los administradores saltan la cola en todas las vías.

## Solicitudes cerradas automáticamente
- Una solicitud en cola cuyo objetivo un administrador **firmó o renovó directamente** entretanto se cierra como aprobada por esa acción y se vincula al certificado
- Una solicitud cuyo objetivo fue **eliminado o revocado** se cierra como rechazada; una suspensión de certificado mantiene la solicitud de renovación en espera hasta que se levante
- Aprobar una solicitud **ya satisfecha** la cierra sobre el certificado existente; aprobar una de varias solicitudes para el mismo objetivo cierra las demás como aprobadas por el aprobador
- Aprobar una solicitud cuya solicitud almacenada, certificado o CA **ya no existe** la cierra como rechazada
- Una revocación en cola cuyo certificado fue **revocado directamente** se cierra como aprobada (cancelada cuando su solicitante la revocó); aquella cuyo certificado se **renovó** desde entonces se cierra como rechazada al aprobarla; aprobada durante una suspensión de certificado, hace definitiva la suspensión con su motivo

Un cierre como rechazada notifica a los webhooks igual que un rechazo; un cierre como aprobada no envía ningún webhook.

## Plazo
Una solicitud espera **siete días** una decisión. Pasado ese plazo se cierra como expirada, nunca se cuenta como pendiente, y el planificador de renovaciones se reanuda para su certificado. Mientras una renovación espera aprobación, el planificador deja el certificado a esa decisión, siempre que pueda llegar antes de que el certificado caduque; bajo una política de renovación nunca renueva sin ella.

## La cola

Las solicitudes abiertas se agrupan por su plazo: **A tramitar en 48 h** y **Más adelante**, cada una con su número. Una solicitud que pasó su plazo está expirada: pasa a **Tramitadas recientemente** y ya no puede decidirse. Una fila indica lo que pide la solicitud y su sujeto, una etiqueta con su origen (CSR, certificado, renovación, revocación, CA, ACME, EST, SCEP, WSTEP), quién la pidió y cuándo, la política, la autoridad y el plazo en forma abreviada sobre su fecha exacta. Un sujeto abre la solicitud en el inspector, con sus secciones **Solicitud** y **Registro**.

## Aprobar una solicitud

1. Hacer clic en **Aprobar…** en su fila, o en el inspector
2. Opcionalmente, indicar un motivo: se anota con la decisión
3. Confirmar: lo que la aprobación emitió se abre en su página, un certificado en el inspector de la página Certificados, una CA en la página Autoridades

## Rechazar una solicitud

1. Hacer clic en **Rechazar…** en su fila, o en el inspector
2. Introducir un **motivo** de al menos cinco caracteres (obligatorio): se conserva en la cronología de la solicitud; un rechazo no escribe ninguna entrada en el registro de auditoría
3. Confirmar: la solicitud se detiene de inmediato

> ⚠ Un solo rechazo detiene toda la solicitud. Es intencionado: si algún revisor identifica un problema, la emisión no debe continuar.

## Decidir varias solicitudes

Marcar varias filas, o un grupo entero desde su cabecera, y después **Aprobar…** o **Rechazar…** en la barra que sustituye a la indicación. No existe una vía masiva: cada solicitud se decide por turno. Cuando todas se han tramitado, un mensaje lo indica; en caso contrario, el resultado enumera las que se tramitaron y por qué las demás no (ya votada, expirada, emisión fallida).

## Historial de aprobación

Cada solicitud mantiene una cronología de aprobación completa que muestra:
- Quién aprobó o rechazó (nombre de usuario)
- Cuándo se realizó la acción (marca de tiempo)
- El comentario aportado (si lo hay)

Este historial se guarda con la solicitud, no en el registro de auditoría.

## Tramitadas recientemente

Las solicitudes decididas (aprobadas, rechazadas, expiradas, canceladas) se pliegan al final de la página bajo **Tramitadas recientemente**, la más reciente primero, con quién decidió, cuándo y por qué.

## Permisos

- **read:approvals**: ver las solicitudes de aprobación
- **write:approvals**: aprobar o rechazar solicitudes

> 💡 Configurar las notificaciones por correo en las políticas para que los aprobadores reciban un aviso cuando lleguen solicitudes nuevas.
`
  },
}
