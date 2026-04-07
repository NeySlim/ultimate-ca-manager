export default {
  helpContent: {
    title: 'Informes',
    subtitle: 'Informes de cumplimiento e inventario PKI',
    overview: 'Genere, descargue y programe informes para auditorías de cumplimiento. Los informes cubren inventario de certificados, certificados por expirar, jerarquía de CA, actividad de auditoría y estado de cumplimiento de políticas. Descargue un informe ejecutivo en PDF para revisión de la dirección.',
    sections: [
      {
        title: 'Tipos de informes',
        items: [
          { label: 'Inventario de certificados', text: 'Lista completa de todos los certificados con su estado' },
          { label: 'Certificados por expirar', text: 'Certificados que expiran dentro de un período de tiempo especificado' },
          { label: 'Jerarquía de CA', text: 'Estructura y estadísticas de las autoridades de certificación' },
          { label: 'Resumen de auditoría', text: 'Resumen de eventos de seguridad y actividad de usuarios' },
          { label: 'Estado de cumplimiento', text: 'Resumen de cumplimiento de políticas e infracciones' },
        ]
      },
      {
        title: 'Informe ejecutivo PDF',
        items: [
          { label: 'Descargar PDF', text: 'Informe profesional en PDF con un clic para la dirección y auditores' },
          { label: 'Contenido', text: 'Resumen ejecutivo, evaluación de riesgos, inventario de certificados, puntuaciones de cumplimiento, infraestructura de CA, actividad de auditoría y recomendaciones' },
          { label: 'Gráficos y visualizaciones', text: 'Incluye medidor de riesgo, distribución de estados, línea de tiempo de expiración y desglose de cumplimiento' },
        ]
      },
      {
        title: 'Programación',
        items: [
          { label: 'Informe de expiración', text: 'Correo electrónico diario con certificados que expiran pronto' },
          { label: 'Informe de cumplimiento', text: 'Correo electrónico semanal con el estado de cumplimiento de políticas' },
        ]
      },
    ],
    tips: [
      'Use el informe ejecutivo en PDF para revisiones de la dirección y auditorías de cumplimiento.',
      'Descargue informes en CSV para análisis en hojas de cálculo o en JSON para automatización.',
      'Use la función de envío de prueba para verificar la entrega de correo antes de activar los programas.',
    ],
  },
  helpGuides: {
    title: 'Informes',
    content: `
## Descripción general

Genere, descargue y programe informes de cumplimiento PKI. Los informes proporcionan visibilidad sobre su infraestructura de certificados para auditorías, cumplimiento y planificación operativa.

## Tipos de informes

### Inventario de certificados
Lista completa de todos los certificados gestionados por UCM. Incluye asunto, emisor, número de serie, fechas de validez, tipo de clave y estado actual. Úselo para auditorías de cumplimiento y documentación de infraestructura.

### Certificados por expirar
Certificados que expiran dentro de un período de tiempo especificado (por defecto: 30 días). Crítico para evitar interrupciones — revise este informe regularmente o prográmelo para entrega diaria.

### Jerarquía de CA
Estructura de las autoridades de certificación que muestra las relaciones padre-hijo, el recuento de certificados por CA y el estado de la CA. Útil para comprender la topología de su PKI.

### Resumen de auditoría
Resumen de eventos de seguridad y actividad de usuarios. Incluye intentos de inicio de sesión, operaciones con certificados, infracciones de políticas y cambios de configuración. Esencial para auditorías de seguridad.

### Estado de cumplimiento
Resumen de cumplimiento de políticas e infracciones. Muestra qué certificados cumplen con sus políticas y cuáles las infringen. Necesario para el cumplimiento normativo.

## Informe ejecutivo PDF

Haga clic en **Descargar PDF** en la esquina superior derecha para generar un informe ejecutivo profesional adecuado para revisiones de la dirección, presentaciones ante la junta directiva y auditorías de cumplimiento.

### Contenido
El informe PDF incluye 9 secciones:
1. **Portada** — Métricas clave, medidor de riesgo y hallazgos principales de un vistazo
2. **Tabla de contenidos** — Navegación rápida
3. **Resumen ejecutivo** — Salud general de la PKI, distribución de certificados y nivel de riesgo
4. **Evaluación de riesgos** — Hallazgos críticos, certificados por expirar, algoritmos débiles
5. **Inventario de certificados** — Desglose por estado, tipo de clave y CA emisora
6. **Análisis de cumplimiento** — Distribución de puntuaciones, desglose de calificaciones, puntuaciones por categoría
7. **Ciclo de vida de certificados** — Línea de tiempo de expiración y tasa de automatización
8. **Infraestructura de CA** — Detalles de CA raíz e intermedias, jerarquía
9. **Recomendaciones** — Elementos accionables basados en el estado actual de la PKI

### Gráficos y visualizaciones
El informe incluye elementos visuales: barra de medidor de riesgo, distribución de estados, desglose de calificaciones de cumplimiento y línea de tiempo de expiración — diseñados para partes interesadas no técnicas.

> 💡 El informe PDF se genera a partir de datos en tiempo real. Descárguelo antes de las reuniones para obtener la instantánea más actual.

## Generación de informes

1. Encuentre el informe que desea en la lista
2. Haga clic en **▶ Generar** para crear una vista previa
3. La vista previa aparece debajo como una tabla formateada
4. Haga clic en **Cerrar** para descartarla

## Descarga de informes

Cada fila de informe tiene botones de descarga:
- **CSV** — Formato de hoja de cálculo para Excel, Google Sheets o LibreOffice
- **JSON** — Datos estructurados para automatización e integración

> 💡 Los informes CSV son más fáciles para partes interesadas no técnicas. JSON es mejor para scripts e integraciones API.

## Programación de informes

### Informe de expiración (Diario)
Envía automáticamente un informe de expiración de certificados todos los días a los destinatarios configurados. Active esto para detectar certificados que expiran antes de que causen interrupciones.

### Informe de cumplimiento (Semanal)
Envía un resumen de cumplimiento de políticas cada semana. Útil para el monitoreo continuo de cumplimiento sin esfuerzo manual.

### Configuración
1. Haga clic en **Programar informes** en la esquina superior derecha
2. Active los informes que desea programar
3. Agregue direcciones de correo electrónico de los destinatarios (presione Enter o haga clic en Agregar)
4. Haga clic en Guardar

### Envío de prueba
Antes de activar los programas, use el botón ✈️ en cualquier fila de informe para enviar un informe de prueba a una dirección de correo específica. Esto verifica que SMTP esté configurado correctamente y que el formato del informe cumple con sus necesidades.

> ⚠ Los informes programados requieren que SMTP esté configurado en **Configuración → Correo electrónico**. El envío de prueba fallará si SMTP no está configurado.

## Permisos

- **read:reports** — Generar y descargar informes
- **read:audit + export:audit** — Descargar informe ejecutivo PDF
- **write:settings** — Configurar programas de informes

> 💡 Programe el informe de expiración primero — es el más valioso operativamente y ayuda a prevenir interrupciones relacionadas con certificados.
`
  }
}
