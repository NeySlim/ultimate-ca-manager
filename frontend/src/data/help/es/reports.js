export default {
  helpContent: {
    title: 'Informes',
    subtitle: 'Informes de cumplimiento e inventario de la PKI',
    overview: 'Generar, descargar y programar informes para la auditoría de cumplimiento. Los informes cubren el inventario de certificados, los certificados por expirar, la jerarquía de CA, la actividad de auditoría y el estado de cumplimiento de las políticas. Descargar un informe ejecutivo en PDF para la revisión de la dirección.',
    sections: [
      {
        title: 'Tipos de informe',
        items: [
          { label: 'Inventario de certificados', text: 'Lista completa de todos los certificados con su estado' },
          { label: 'Certificados por expirar', text: 'Certificados que expiran dentro de una ventana de tiempo especificada' },
          { label: 'Jerarquía de CA', text: 'Estructura y estadísticas de las autoridades de certificación' },
          { label: 'Resumen de auditoría', text: 'Las acciones más frecuentes y los usuarios más activos durante el período' },
          { label: 'Estado de cumplimiento', text: 'Tres comprobaciones: certificados activos, CA expiradas y certificados que expiran en 30 días; las políticas de certificados no se leen' },
          { label: 'Certificados revocados', text: 'Certificados revocados durante el período, con fecha y motivo' },
        ]
      },
      {
        title: 'Informe ejecutivo en PDF',
        items: [
          { label: 'Descargar', text: 'Cada plantilla PDF es un informe de la página: Descargar lo genera; Crear un PDF… compone uno a partir de las secciones elegidas' },
          { label: 'Contenido', text: 'Resumen ejecutivo, evaluación de riesgos, inventario de certificados, puntuaciones de cumplimiento, infraestructura de CA, actividad de auditoría y recomendaciones' },
          { label: 'Gráficos y elementos visuales', text: 'Incluye un indicador de riesgo, la distribución por estado, la línea temporal de vencimientos y el desglose de cumplimiento' },
        ]
      },
      {
        title: 'Programación',
        items: [
          { label: 'Programar un informe', text: 'Elegir cualquier informe de datos o plantilla PDF, y después su frecuencia (diaria, semanal o mensual), la hora (introducida y mostrada en la zona horaria propia; una ejecución semanal o mensual que cayera en otro día para el usuario conserva su hora UTC, y se indica), el formato y los destinatarios; los informes programados se agrupan por próxima ejecución' },
          { label: 'Adjunto', text: 'El informe se adjunta al correo en su formato: CSV o JSON para los informes de datos, PDF para las plantillas PDF' },
        ]
      },
    ],
    tips: [
      'Usar el informe ejecutivo en PDF para las revisiones de la dirección y las auditorías de cumplimiento.',
      'Descargar los informes como CSV para analizarlos en una hoja de cálculo o como JSON para la automatización.',
      'Usar la función de envío de prueba para verificar la entrega del correo antes de activar las programaciones.',
    ],
  },
  helpGuides: {
    title: 'Informes',
    content: `
## Visión general

Generar, descargar y programar informes de cumplimiento de la PKI. Los informes dan visibilidad sobre la infraestructura de certificados para la auditoría, el cumplimiento y la planificación operativa.

## Tipos de informe

### Inventario de certificados
Lista completa de todos los certificados gestionados por UCM. Incluye sujeto, emisor, número de serie, fechas de validez, tipo de clave y estado actual. Usarlo para auditorías de cumplimiento y documentación de la infraestructura.

### Certificados por expirar
Certificados que expiran dentro de una ventana de tiempo especificada (por defecto: 30 días). Esencial para evitar interrupciones: revisar este informe con regularidad o programar su envío diario.

### Jerarquía de CA
Estructura de las autoridades de certificación con las relaciones padre-hijo y el número de certificados por CA. Útil para comprender la topología de la PKI.

### Resumen de auditoría
Las diez acciones más frecuentes y los diez usuarios más activos durante el período.

### Estado de cumplimiento
Tres comprobaciones con un recuento y una gravedad: certificados activos, CA expiradas y certificados que expiran en 30 días. No lee las políticas de certificados.

### Certificados revocados
Certificados revocados durante el período elegido (por defecto: 30 días), con fecha y motivo de revocación. Revisarlo para seguir las revocaciones y sus causas.

## Informe ejecutivo en PDF

La plantilla **Resumen ejecutivo** es uno de los informes de la página: su botón **Descargar** genera el PDF, adecuado para revisiones de la dirección, presentaciones al consejo y auditorías de cumplimiento. **Crear un PDF…** en la cabecera de la página (bajo la cola en un teléfono) compone uno a partir de las secciones elegidas.

### Contenido
El informe PDF incluye 9 secciones:
1. **Portada**: métricas clave, indicador de riesgo y principales hallazgos de un vistazo
2. **Índice**: navegación rápida
3. **Resumen ejecutivo**: estado general de la PKI, distribución de certificados y nivel de riesgo
4. **Evaluación de riesgos**: hallazgos críticos, certificados por expirar, algoritmos débiles
5. **Inventario de certificados**: desglose por estado, tipo de clave y CA emisora
6. **Análisis de cumplimiento**: distribución de puntuaciones, desglose por calificación, puntuaciones por categoría
7. **Ciclo de vida de los certificados**: línea temporal de vencimientos y tasa de automatización
8. **Infraestructura de CA**: detalles de las CA raíz e intermedias, jerarquía
9. **Recomendaciones**: acciones concretas según el estado actual de la PKI

### Gráficos y elementos visuales
El informe incluye elementos visuales: barra indicadora de riesgo, distribución por estado, desglose por calificación de cumplimiento y línea temporal de vencimientos, pensados para interlocutores no técnicos.

> 💡 El informe PDF se genera a partir de datos en vivo. Descargarlo antes de las reuniones para obtener la instantánea más actual.

## La cola

Los informes programados se agrupan por su próxima ejecución: **Próxima ejecución en 24 h**, y después **Programados**. Una fila indica el informe, su frecuencia y hora en una etiqueta (en la zona horaria propia; una ejecución semanal o mensual que cayera en otro día para el usuario conserva su hora UTC, y se indica), la cifra actual cuando los contadores de certificados la tienen (Certificados por expirar) o si no su formato, sus destinatarios, y la próxima ejecución en forma abreviada sobre su fecha exacta. Los informes sin programación se pliegan bajo **Sin programar**, cada uno con **Descargar** y **Programar…**.

## Ver un informe

El nombre de un informe lo abre en el inspector:
- **Informe**: su programación y la cifra actual: para Certificados por expirar, la cifra de los contadores (la ventana de 30 días de la vista general, sin los certificados revocados); para los demás informes de datos, **Calcular**; los informes de inventario, de expiración y de revocados ofrecen **Ver estos certificados**
- **Ejecuciones**: el servidor no sirve ningún historial de ejecuciones; la programación y la próxima ejecución es lo que se conoce
- **Vista previa**: **Generar** construye el informe ahora y muestra sus filas (las 200 primeras; la descarga las contiene todas)

## Descargar informes

**Descargar** en una fila, o en el inspector, genera el informe ahora en el formato de su programación: CSV por defecto, JSON cuando se elige, PDF para una plantilla. Marcar varias filas las descarga una tras otra: un mensaje cuando todas se han tramitado, y si no el resultado indica cuáles fallaron.

> 💡 Los informes CSV son más fáciles para los interlocutores no técnicos. JSON es mejor para scripts e integraciones con la API.

## Programar informes

### Qué puede programarse
Cada informe de datos y cada plantilla PDF puede programarse, cada uno con su propia frecuencia, hora y destinatarios. Programar **Certificados por expirar** a diario para detectar los certificados que expiran antes de que causen interrupciones.

### Frecuencia
**Diario**, **Semanal** (elegir el día de la semana) o **Mensual** (elegir el día del mes). El planificador funciona en UTC: la hora se introduce en la zona horaria propia, como la muestra la cola, y se convierte al guardar; una ejecución semanal o mensual cuyo día cambiaría con la conversión se introduce en UTC, como indica el diálogo.

### Configuración
1. Hacer clic en **Programar un informe**, o en **Programar…** en un informe plegado bajo **Sin programar**
2. Elegir el contenido, la frecuencia y su día, la hora de envío (en la zona horaria propia) y, para un informe de datos, el formato (CSV o JSON)
3. Indicar uno o varios destinatarios, separados por comas: sin destinatario no se envía nada
4. Hacer clic en **Programar**

Cada informe programado se adjunta al correo en su formato: CSV o JSON para los informes de datos, PDF para las plantillas PDF. **Cambiar la programación…** y **Suspender la programación** están en el menú « ⋯ » del inspector; marcar varias filas las suspende juntas, en una sola actualización.

### Envío de prueba
Antes de confiar en una programación, usar **Enviar una prueba…** en el menú « ⋯ » del inspector de un informe para enviarlo a una dirección de correo. Esto verifica que SMTP está bien configurado y que el formato del informe satisface las necesidades.

> ⚠ Los informes programados requieren que SMTP esté configurado en **Configuración → Correo**. El envío de prueba fallará si SMTP no está configurado.

## Permisos

- **read:audit**: generar y ver informes; la descarga también necesita **export:audit**
- **read:audit + export:audit**: descargar el informe ejecutivo en PDF
- **write:settings**: configurar las programaciones de informes

> 💡 Programar primero el informe de Certificados por expirar: es el más valioso operativamente y ayuda a evitar interrupciones relacionadas con certificados.
`
  },
}
