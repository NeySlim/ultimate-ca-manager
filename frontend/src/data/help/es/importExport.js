export default {
  helpContent: {
    title: 'Importar y Exportar',
    subtitle: 'Migración de datos y copias de seguridad',
    overview: 'Importe certificados de fuentes externas y exporte sus datos PKI. La importación inteligente detecta automáticamente los tipos de archivo. La integración con OPNsense permite la sincronización directa con su firewall.',
    sections: [
      {
        title: 'Importar',
        items: [
          { label: 'Importación inteligente', text: 'Suba cualquier archivo de certificado — UCM detecta automáticamente el formato (PEM, DER, P12, P7B)' },
          { label: 'Sincronización OPNsense', text: 'Conéctese al firewall OPNsense e importe sus certificados y CAs' },
        ]
      },
      {
        title: 'Exportar',
        items: [
          { label: 'Exportar certificados', text: 'Descarga masiva de certificados como paquete PEM o PKCS#7' },
          { label: 'Exportar CAs', text: 'Descarga masiva de certificados de CA y cadenas' },
        ]
      },
      {
        title: 'Integración OPNsense',
        items: [
          { label: 'Conexión', text: 'Proporcione la URL de OPNsense, clave API y secreto API' },
          { label: 'Probar conexión', text: 'Verificar la conectividad antes de importar' },
          { label: 'Seleccionar elementos', text: 'Elegir qué certificados y CAs importar' },
        ]
      },
    ],
    tips: [
      'La importación inteligente maneja paquetes PEM con múltiples certificados en un solo archivo',
      'Pruebe la conexión de OPNsense antes de ejecutar una importación completa',
      'Los archivos PKCS#12 requieren la contraseña correcta para importar claves privadas',
    ],
  },
  helpGuides: {
    title: 'Importar y Exportar',
    content: `
## Descripción general

Importe certificados de fuentes externas y exporte sus datos PKI para copias de seguridad o migración.

## Importación inteligente

El asistente de importación inteligente detecta automáticamente los tipos de archivo y los procesa:

### Formatos compatibles
- **PEM** — Certificados individuales o en paquete, CAs y claves
- **DER** — Certificado o clave en formato binario
- **PKCS#12 (P12/PFX)** — Certificado + clave + cadena (requiere contraseña)
- **PKCS#7 (P7B)** — Cadena de certificados sin claves

### Cómo funciona
1. Haga clic en **Importar** o arrastre archivos a la zona de carga
2. UCM analiza cada archivo e identifica su contenido
3. Revise los elementos detectados (CAs, certificados, claves)
4. Haga clic en **Importar** para agregarlos a UCM

> 💡 La importación inteligente maneja paquetes PEM con múltiples certificados en un solo archivo. Distingue automáticamente las CAs de los certificados de entidad final.

## Integración OPNsense

Sincronice certificados y CAs desde un firewall OPNsense:

### Configuración
1. En OPNsense, cree una clave API (Sistema → Acceso → Usuarios → Claves API)
2. En UCM, ingrese la URL de OPNsense, la clave API y el secreto API
3. Haga clic en **Probar conexión** para verificar

### Importar
1. Haga clic en **Conectar** para obtener los certificados y CAs disponibles
2. Seleccione los elementos que desea importar
3. Haga clic en **Importar seleccionados**

UCM importa los certificados con sus claves privadas (si están disponibles) y preserva la jerarquía de CAs.

## Exportar certificados

Exportación masiva de todos los certificados:
- **PEM** — Archivos PEM individuales
- **Paquete P7B** — Todos los certificados en un solo archivo PKCS#7
- **ZIP** — Todos los certificados como archivos PEM individuales en un archivo ZIP

## Exportar CAs

Exportación masiva de todas las Autoridades de Certificación:
- **PEM** — Cadena de certificados en formato PEM
- **Cadena completa** — Raíz → Intermedia → Sub-CA

## Migración entre instancias UCM

Para migrar de una instancia UCM a otra:
1. Cree una **copia de seguridad** en el origen (Configuración → Copia de seguridad)
2. Instale UCM en el destino
3. **Restaure** la copia de seguridad en el destino

Esto preserva todos los datos: certificados, CAs, claves, usuarios, configuración y registros de auditoría.
`
  }
}
