# Ultimate Certificate Manager

[English](README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · [Português (Brasil)](README.pt.md) · [Русский](README.ru.md) · [Українська](README.uk.md) · [日本語](README.ja.md) · [中文](README.zh.md)

![Version](https://img.shields.io/github/v/release/NeySlim/ultimate-ca-manager?label=version&color=brightgreen)
![License](https://img.shields.io/badge/license-AGPL--3.0--only-blue.svg)
![Docker Hub](https://img.shields.io/docker/v/neyslim/ultimate-ca-manager?label=docker%20hub&color=blue)
![GHCR](https://img.shields.io/badge/ghcr.io-available-blue)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20UCM-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/neyslim)

**Ultimate Certificate Manager (UCM)** es una plataforma web de gestión de autoridades de certificación con soporte de protocolos PKI (ACME, SCEP, EST, OCSP, CRL/CDP), integración con Microsoft ADCS, autenticación multifactor y gestión del ciclo de vida de los certificados.

> **UCM es un proyecto joven y en pleno desarrollo.** Los comentarios, informes de errores y solicitudes de funciones son muy bienvenidos. No dudes en [abrir una incidencia](https://github.com/NeySlim/ultimate-ca-manager/issues): cada informe ayuda a mejorar UCM.

> Consulta las [notas de la última versión](https://github.com/NeySlim/ultimate-ca-manager/releases/latest) y el [CHANGELOG](CHANGELOG.md) completo para ver las novedades.

![Dashboard](docs/screenshots/dashboard-dark.png)

---

## Funciones

### Núcleo PKI
- **Gestión de CA** -- CA raíz e intermedias, vista de jerarquía, importación y exportación, **revocación de CA intermedias** (CRL y OCSP de la CA superior, estado de revocada en origen por debajo), **CA solo de certificado** (una CA firmada a partir de una solicitud externa, con su clave privada importada más tarde), **claves de firma respaldadas por HSM** (la clave privada nunca sale del HSM), **perfil RFC 5280 configurable** (resumen de la firma, Key Usage, EKU), posibilidad de **ocultar una CA de los formularios de emisión** (una raíz que solo firma intermedias) con valores por defecto al estilo de Let's Encrypt y un esquema de firma **RSA-PSS** opcional, **perfiles de conformidad** alineados con ANSSI, BSI y los mecanismos acordados de la UE, **CA firmadas externamente** (UCM genera el par de claves y una CSR de tipo CA, una raíz externa o fuera de línea la firma: la clave privada nunca sale de UCM, con renovación de la CSR con la misma clave), **certificados de CA con firma cruzada** (adjuntar o firmar de forma cruzada uno junto al certificado propio de la CA, servirlo en la cadena por defecto durante un cambio de raíz, elegir la cadena por exportación o despliegue, ver qué sigue encadenándose a la raíz antigua), **restricciones de nombre RFC 5280** definidas en la creación (subárboles permitidos y excluidos de DNS, rangos IP y e-mail, aplicadas en todas las vías de emisión), validez desde 1 año o cualquier número de días hasta 50 años, y una regla opcional de **sujeto único** (se rechaza en todas las vías de emisión un certificado cuyo sujeto ya lleva otra entidad bajo esa CA, RFC 5280 §4.1.2.6)
- **Ciclo de vida de los certificados** -- Emitir, firmar, revocar (con el motivo RFC 5280, desde cada cuadro de diálogo de revocación y de forma masiva), renovar (**in situ**: identificadores estables entre renovaciones, los números de serie reemplazados permanecen en CRL/OCSP hasta su caducidad original, con una validez elegida que sigue limitada por la política), renombrar (nombre visible editable, incluye certificados sin CN), exportar (PEM, DER, PKCS#12 con un modo de compatibilidad 3DES/SHA-1 para Android 15 y anteriores, macOS 14 y anteriores, Windows y Java antiguos, JKS; la cadena omite por defecto la raíz autofirmada, con una opción **Incluir CA raíz** cuando el destino de empaquetado o importación la necesita), operaciones masivas, filtro por estado / emisor / origen (ACME, SCEP, EST, AD CS, importación…), incluidos los registros **archivados** por una renovación o una reinscripción y conservados como historial
- **Análisis de conformidad** -- comprobaciones por certificado frente a RFC 5280, los Baseline Requirements del CA/Browser Forum y ETSI EN 319 412 mediante pkilint (y zlint cuando está disponible), solo informativas
- **Gestión de CSR** -- Crear, importar y firmar solicitudes de firma de certificado con **OID de EKU adicionales personalizados** (RFC 5280 §4.2.1.12), **validación tipada de SAN** (DNS / IP / Email / URI / UPN), curvas NIST P-256 / P-384 / P-521 y Brainpool P256r1 / P384r1 / P512r1, y una **vía de retorno de CA externa**: un certificado emitido en otro lugar para una CSR generada en UCM completa esa CSR al importarse y conserva su clave privada; **nombres añadidos al firmar** (la dirección de e-mail de una solicitud S/MIME de una tarjeta inteligente que solo lleva un CN, bajo las mismas restricciones de nombre, políticas y aprobación) y **firmar de nuevo** desde el historial, para dispositivos que no pueden producir su solicitud dos veces
- **Plantillas de certificado** -- Perfiles predefinidos para servidor, cliente, firma de código, e-mail e inicio de sesión con tarjeta inteligente de Windows; tipos de clave RSA-2048/3072/4096, EC P-256/P-384/P-521, Brainpool y **poscuánticas ML-DSA-44/65/87** (Ed25519/Ed448 para CA), **extensiones X.509 personalizadas por OID**, **qcStatements (ETSI EN 319 412-5) y OID de políticas de certificado**, y valores de sujeto por defecto (e-mail incluido) rellenados en el formulario de emisión; exportación e importación JSON que conservan todos los ajustes, una plantilla o varias por archivo
- **Descubrimiento de certificados** -- Escaneo de red, perfiles de escaneo, escaneos programados, importación de certificados
- **Almacén de confianza** -- Gestión de certificados de CA raíz de confianza con alertas de caducidad y eliminación masiva
- **Reparación de cadenas** -- Validación de cadenas basada en AKI/SKI con planificador de reparación automática
- **Certificados SSH** -- Gestión de autoridades de certificación SSH, firma de certificados de host y de usuario, importación de CA y certificados, scripts de configuración aptos para curl; identificadores de clave asignados por la CA (`principals@nombre de la CA`) o dejados al solicitante

### Protocolos
- **ACME** -- RFC 8555, inscripción y renovación automáticas, desafíos DNS-01/HTTP-01/TLS-ALPN-01, compatibilidad con comodines, **identificadores IP (RFC 8738)**, **comprobación CAA con vinculación a cuenta y método (RFC 8657/8659)**, **External Account Binding (EAB, RFC 8555 §7.3.4)**, **Renewal Information (ARI, RFC 9773)**, **archivos de desafío HTTP-01 servidos por UCM** (reenviar `/.well-known/acme-challenge/` desde el puerto 80, comprobados antes del envío, renovados automáticamente), **elección del resolvedor DNS-01** (automático, solo el del sistema o solo los resolvedores indicados, para redes sin acceso a resolvedores públicos) para split-horizon, ACME sobre IP internas o privadas (incluido el upstream de loopback opcional para una CA en el mismo equipo), **gestión de varias CA** (selección de CA por solicitud, fijada en el pedido para que las renovaciones reutilicen la misma CA: Let's Encrypt, Actalis, ZeroSSL, Google Trust Services, HARICA…), **CSR externa y reutilización de la clave en la renovación**, **ensayo previo en staging**, **proxy multi-CA** (los dominios upstream ya validados pasan directamente, endpoints por CA en `/acme/proxy/<slug>/directory`, incluida la revocación upstream), **cadena de certificados preferida** (alternativas de RFC 8555 §7.4.2, por cuenta de CA), **perfiles de certificado** (draft-ietf-acme-profiles: políticas de emisión con nombre anunciadas en el directorio y seleccionables por pedido, cada una vinculable a una plantilla de certificado cuyo uso de clave y EKU rigen entonces el certificado emitido, más un **perfil por defecto** y un resumen de firma por defecto para los pedidos que no nombran ninguno), **gestión de pedidos del servidor local** (vista de pedidos con limpieza y purga programada de los pedidos caducados); el proxy también publica los valores TXT de dns-01 del lado del cliente para que las comprobaciones de propagación de los clientes (lego, Traefik, Caddy) pasen tal cual, reutiliza el pedido aún pendiente de una cuenta en los reintentos, y un **servicio de escucha DNS UPDATE (RFC 2136)** opcional permite que solucionadores rfc2136 estándar, como el de cert-manager, respondan a DNS-01 a través del proxy con claves TSIG por cuenta
- **SCEP** -- inscripción automática de dispositivos RFC 8894 con flujos de aprobación, GetCert/GetCRL, GetNextCACert firmado, opcionalmente en el puerto HTTP simple para clientes como sscep (fuera del modo FIPS, que solo admite transporte de clave RSA-OAEP), renovaciones autenticadas con el certificado del dispositivo, cifrado AES-128 con alternativa basada en contraseña (PBKDF2) para clientes no RSA; una solicitud aprobada a mano se emite con la plantilla del perfil por el que llegó, igual que la aprobación automática; los perfiles con nombre validan los desafíos de **Microsoft Intune** contra la API de Intune del inquilino, y los dispositivos Windows (transporte de clave RSAES-OAEP) y Apple se inscriben a través de ellos, véase [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md)
- **EST** -- RFC 7030 Enrollment over Secure Transport, incluida la generación de claves en el servidor (CMS §4.4) y **etiquetas de CA** (§3.2.2: servir varias CA desde un mismo endpoint)
- **OCSP** -- estado de certificados en tiempo real según RFC 6960, solicitudes de varios certificados, compatibilidad con nonce, validación de respondedor delegado con renovación automática del certificado del respondedor, validez de respuesta configurable
- **TSA (RFC 3161)** -- autoridad de sellado de tiempo con OID de política configurable; firma con un **certificado de firma de entidad final dedicado** (RFC 3161, exigido por defecto y por verificadores estrictos como `openssl ts -verify` y jarsigner), elegido entre los certificados emitidos o generado con un clic (EKU timeStamping crítico y exclusivo); renovaciones seguidas automáticamente, cadena del emisor incluida en los tokens, modo estricto de firmante dedicado, estado y caducidad del firmante visibles en el panel
- **CRL/CDP** -- distribución de listas de revocación con soporte de Delta CRL (RFC 5280 §5.2.4), calendario por CA (validez desvinculada de la cadencia de publicación) y resumen de firma configurable, URL con nombre opcionales (slug del nombre de la CA en las rutas CDP/AIA, activable en CA existentes), **carga de CRL firmadas externamente para CA sin conexión o sin clave** (validadas contra el certificado de la CA con monotonía del número de CRL, servidas en el endpoint CDP existente y consultadas por OCSP)
- **AIA CA Issuers** -- descarga del certificado de la CA mediante Authority Information Access (RFC 5280 §4.2.2.1)

### Integraciones
- **Microsoft ADCS** -- Ciclo de vida completo sobre AD CS: firma de CSR, descubrimiento de plantillas, EOBO (Enroll On Behalf Of), renovación y revocación a través del conector, y un canal de administración WinRM opcional para la sincronización de revocaciones de CRL, la importación del inventario de CA y la aprobación o denegación de solicitudes pendientes con un panel de estado de la CA
- **Inscripción automática de Windows y conector de Active Directory** -- política e inscripción MS-XCEP/WSTEP para equipos y usuarios unidos al dominio con la plantilla que nombra la solicitud; con el enlace Kerberos, las plantillas de equipo y las derivadas de AD toman el sujeto de Active Directory (el nombre de host DNS del equipo, o el DN y el UPN del usuario), a través de varios controladores de dominio con conmutación por error y una comprobación de estado programada por controlador, nunca con un enlace anónimo; la inscripción se configura en **perfiles por realm** (`/api/v2/windows-profiles`), cada uno con su propia CA, plantillas, keytab de Kerberos, grupo de AD y conector, y una solicitud Kerberos la atiende el perfil habilitado del realm de su principal (el enlace UsernamePassword, el perfil por defecto cuando está habilitado; una renovación vinculada a certificado, el perfil registrado en el certificado presentado), a través de **varios conectores de Active Directory** (uno por bosque o dominio)
- **Microsoft Intune** -- validación de desafíos SCEP para dispositivos gestionados por Intune, registros de aplicación de Entra definidos una sola vez en SCEP › Registros de aplicación de Intune y elegidos por perfil, con una guía paso a paso en `docs/integrations/intune-scep.md`
- **HSM** -- SoftHSM incluido, PKCS#11, Azure Key Vault, Google Cloud KMS, OpenBao/Vault Transit; **CA respaldadas por HSM** con claves de firma no exportables, RSA-PSS y Brainpool en PKCS#11, y una certificación de dispositivo declarada (Common Criteria, EUCC, FIPS 140-3) comprobada por el perfil de conformidad de la UE; una prueba de conexión muestra lo que informa un módulo PKCS#11 (biblioteca, fabricante, firmware)
- **Kubernetes / cert-manager** -- Manifiestos de referencia para ClusterIssuer (HTTP-01 + DNS-01 con EAB), Certificate de ejemplo y plantilla de Secret en `examples/kubernetes/cert-manager/`
- **Proveedores DNS** -- Cloudflare, Route53, Azure DNS, Plesk y más para los desafíos ACME DNS-01
- **Webhooks** -- Notificaciones basadas en eventos del ciclo de vida de los certificados (más de 15 tipos de evento), **historial de entregas por endpoint con reintento manual**, cola de entrega asíncrona duradera con retroceso exponencial y una ventana de retención del historial para que no crezca sin límite

### Seguridad y acceso
- **Autenticación** -- Contraseña, WebAuthn/FIDO2 (también como segundo factor, junto a TOTP o en su lugar), 2FA con TOTP, mTLS, claves de API (`X-API-Key` o `Authorization: Bearer`)
- **SSO** -- LDAP (LDAPS o StartTLS), OAuth2 (Azure/Google/GitHub), SAML con Single Logout, asignación de roles a roles integrados y **roles personalizados** (grupos SAML leídos de la aserción, con las notificaciones de Entra ID y AD FS) y un formato de NameID configurable; **seguimiento de `auth_source` por usuario** y sincronización de roles opcional al iniciar sesión
- **RBAC** -- 4 roles integrados (Admin, Operator, Auditor, Viewer) más roles personalizados con permisos granulares; los **grupos conceden permisos adicionales** sobre el rol del usuario (nunca de administrador)
- **Políticas y aprobaciones** -- Políticas de emisión de certificados con flujos de aprobación y reglas obligatorias (tipos de clave y hashes de firma permitidos, límite de SAN DNS, límite de validez, con alcance por CA, plantilla o patrón DNS), que vinculan **todas las vías del operador** (el formulario de emisión, la firma de una solicitud almacenada de forma individual o masiva, y la renovación) y, para tipos de clave y hashes, también ACME, SCEP, EST, WSTEP y la creación de CA; una política que exige aprobación retiene en la cola de aprobación las **solicitudes ACME, EST, SCEP y WSTEP**, y cada cliente lo recibe en los términos de su protocolo (ACME `processing`, EST 202 con Retry-After, SCEP PENDING, WSTEP pending); una política también puede someter a aprobación las **revocaciones y renovaciones**; una solicitud en cola se cierra sola cuando su objetivo se firma, renueva, elimina o revoca mientras tanto
- **Valores por defecto de clave y hash** -- Una solicitud que no indica clave ni hash sigue un único valor por defecto en todas las vías de emisión (RSA-2048 con SHA-256 salvo que un perfil o una política lo rechace, y entonces el primer tipo aceptado), el hash sigue a la clave de firma, y una CA intermedia nueva nunca toma un hash inferior al de su superior
- **Registros de auditoría** -- Registro de acciones con verificación de integridad, reenvío remoto por syslog y un período de retención opcional
- **Cifrado de claves privadas** -- AES-128 (Fernet, HMAC-SHA256) en reposo con una clave maestra creada en el primer arranque (en un contenedor, cuando `/etc/ucm` es un volumen) o indicada como `KEY_ENCRYPTION_KEY`, que abarca las claves de CA y de certificados, las claves de CA SSH y de destinos de despliegue, las claves de cuenta ACME y EAB, los desafíos SCEP y las contraseñas de enlace LDAP, con **Cifrar las claves restantes** para los secretos almacenados antes de activarlo; con el cifrado activado no se conserva ningún archivo de clave en texto claro en disco (las copias existentes se eliminan al activarlo y al arrancar, los archivos de certificados públicos permanecen), y los archivos de clave se recrean al desactivarlo
- **Alta disponibilidad** -- Ejecuta dos o más nodos sobre una misma base de datos PostgreSQL con `UCM_HA=1` (Docker, Docker Compose, DEB/RPM o `ha.enabled` del chart de Helm): un nodo elegido ejecuta las tareas programadas, los ajustes, el cifrado, las copias de seguridad y las actualizaciones progresivas llegan a todos los nodos, y las sesiones son compartidas, de modo que solo los endpoints de inscripción Kerberos necesitan afinidad por dirección de origen (véase [docs/HA.md](docs/HA.md))
- **Modo FIPS** -- la imagen Docker `-fips` ejecuta la criptografía de UCM en el OpenSSL FIPS Provider 3.5.9 (certificado CMVP #5586), que aprueba ML-DSA, Ed25519 y Ed448, de modo que las firmas poscuánticas y EdDSA están disponibles en modo FIPS con la imagen; los paquetes DEB y RPM construidos con `UCM_FIPS_BUILD=1` se ejecutan sobre el módulo FIPS de RHEL 9 (#5573) o Ubuntu 24.04 Pro (#5115), que no las ofrecen. Con `UCM_FIPS=1`, UCM solo arranca sobre un módulo activo y autoverificado, genera las claves a través de él, permite un algoritmo solo cuando el módulo cargado lo aprueba y rechaza el resto (MD5, 3DES, scrypt, Argon2id, PKCS#12 heredado, NTLM), y una comprobación de disponibilidad enumera de antemano lo que perdería una instancia. UCM en sí no es un módulo validado, y Debian 13 y arm64 no figuran entre las configuraciones probadas del certificado #5586
- **Perfiles de conformidad** -- políticas por CA alineadas con ANSSI PG-083, BSI TR-02102-1 y los mecanismos criptográficos acordados del ECCG (tipos de clave, hashes, esquemas de firma, horizontes de validez, claves de CA en HSM, firmante de sellos de tiempo EC), con rechazos donde el texto impone y avisos donde recomienda, y una comprobación previa de solo lectura antes de asociar un perfil a una CA existente; UCM no está certificado ni cualificado por ninguno de estos organismos
- **SBOM** -- un SBOM CycloneDX para cada paquete y plataforma de imagen de cada versión, vinculado al hash del archivo o al digest de la imagen, que enumera lo que incluye con sus versiones y licencias declaradas y lo que un paquete resuelve en la instalación ([docs/SBOM.md](docs/SBOM.md))
- **Refuerzo** -- HSTS configurable por el operador (Ajustes → Seguridad o variable de entorno), control de proxies de confianza para las cabeceras de certificado de cliente, permisos de las claves de API limitados a los del propio creador; los proxies de confianza pueden indicarse como redes CIDR y, una vez activado el soporte de proxy, las cabeceras `X-Forwarded-*` solo se aceptan de ellos, de modo que un cliente que llegue directamente al backend no pueda falsificar su dirección; la interfaz web y la API de gestión pueden **restringirse a direcciones IP y redes indicadas** mientras los endpoints de los protocolos PKI siguen accesibles

### Operaciones y supervisión
- **Resumen** -- Cuatro cifras principales, pasos de configuración inicial y nueve tarjetas independientes (cola de trabajo con acciones de renovar, reintentar y publicar, estado de la automatización, emisiones por origen, horizonte de caducidad, conformidad, cobertura de revocación, jerarquía, últimas operaciones, autoridades y HSM), que se muestran, ocultan y reordenan con preajustes de disposición guardados por usuario y se recargan solas cuando cambian los datos
- **Informes** -- Informes PDF programados, resúmenes ejecutivos, certificados revocados, plantillas personalizadas
- **Herramientas de certificados** -- Comprobador SSL, decodificador de CSR y certificados, comparador de claves, conversor de formatos
- **Notificaciones por e-mail** -- SMTP con STARTTLS o TLS implícito (puerto 465), **OAuth2 (XOAUTH2)** para Gmail, Outlook.com y Microsoft 365, plantillas HTML/texto personalizables, alertas de caducidad de certificados con varios umbrales de días (un e-mail por umbral y período de validez, al estilo escalonado 30/14/7/1), con la posibilidad de excluir los certificados que los clientes ACME renuevan por sí mismos
- **Ganchos de despliegue** -- Envío de los certificados emitidos y renovados, y de las CRL regeneradas (DER o un paquete PEM con las CRL superiores), a hosts remotos por SSH/SFTP, con rutas de destino y un comando de recarga opcional por vinculación: autenticación por clave (ed25519 generada o clave importada, cifrada en reposo), fijación de la clave de host en la primera conexión, rutas de destino por vinculación (certificado / clave / cadena completa, la cadena sin la raíz autofirmada salvo que la vinculación la pida, escrita de forma atómica), cola de entrega duradera con reintentos e historial por entrega, un **preajuste para el mismo host** para servicios que se ejecutan junto a UCM, y **destinos de API HTTP** que envían un certificado a un cortafuegos, equilibrador de carga o API en la nube en una sola solicitud construida a partir de una plantilla de cuerpo (URL, método, cabeceras cifradas, variables del tipo `{{cert_pem|json}}`, clave privada solo con una aceptación explícita sobre HTTPS verificado)
- **Copia de seguridad y restauración** -- Copias de seguridad cifradas manuales y programadas con políticas de retención y un límite opcional del espacio que ocupan los archivos almacenados; los archivos son flujos de bloques autenticados de forma independiente, así que crearlos y comprobarlos antes de una restauración no exige tenerlos enteros en memoria; los archivos incluyen pedidos de cliente ACME y solicitudes pendientes, se restauran en modo de fusión o de reemplazo, hacen coincidir filas por nombre entre instalaciones y reejecutan las migraciones de reparación
- **Paquete de registros de diagnóstico** -- Descarga con un clic (Ajustes → Acerca de → Diagnóstico) de los registros de la aplicación, el registro de errores, el diario de systemd y un diagnóstico del sistema sin secretos en un ZIP, con los tokens sensibles ocultados
- **Visor de registros del sistema** -- Explora desde la interfaz los registros de la aplicación, de acceso, de errores y el diario de systemd, filtrados por nivel, ventana de tiempo y texto, con los secretos ocultados
- **Métricas de Prometheus** -- endpoint `/metrics` opcional, protegido con bearer, que expone contadores de certificados, CA, planificador, webhooks y ACME
- **Planificador** -- vista de administración de las tareas en segundo plano (comprobaciones de caducidad, actualización de CRL, entrega de webhooks, copias de seguridad, renovación automática) con estado y ejecución inmediata, ejecutadas en un proceso propio bajo gunicorn
- **HTTPS propio** -- aplica cualquier certificado emitido a la interfaz web; la vinculación sigue las renovaciones automáticamente (archivos regenerados, servicio reiniciado)
- **Valores de red seguros por defecto** -- escucha en doble pila (`HOST=::` sirve IPv6 e IPv4 en un mismo socket) y salvaguardas de la URL base de administración (comprobación de accesibilidad antes de aplicar, la redirección canónica se desactiva cuando el host deja de resolverse, interruptor de recuperación `UCM_DISABLE_CANONICAL_REDIRECT=1`)
- **Actualizaciones de software** -- Comprobador de actualizaciones integrado con instalación con un clic, comprobación diaria programada en el canal estable o de versiones candidatas, e instalación desatendida opcional (DEB/RPM) con verificación SHA256 obligatoria y eventos de resultado veraces (instalado solo después de verificar la versión tras la instalación real), más una ventana opcional, una sola vez por usuario, con las notas de versión tras una actualización
- **Búsqueda global** -- Búsqueda entre recursos y paleta de comandos (Ctrl+K)

### Plataforma
- **Temas** -- Atelier y Aurore, cada uno oscuro o claro, o según el sistema; **preferencias por usuario guardadas en el servidor** (idioma, tema, modo)
- **i18n** -- 10 idiomas (EN, FR, DE, ES, IT, PT, UK, RU, ZH, JA)
- **Estado de la interfaz persistente** -- Las selecciones de filtros se conservan entre recargas en las principales páginas de listas (certificados, CA, plantillas, políticas, registros de auditoría, almacén de confianza, usuarios, SSH)
- **Base de datos** -- SQLite (por defecto) o **backend nativo de PostgreSQL** con interfaz de migración bidireccional
- **Interfaz adaptable** -- React 18 + Radix UI, apta para móviles
- **Tiempo real** -- Actualizaciones en vivo por WebSocket: un cambio hecho por otro operador actualiza las listas que lo muestran, y una reconexión tras una interrupción las recarga en lugar de dejar filas obsoletas en pantalla
- **Multiplataforma** -- Docker, Debian/Ubuntu (.deb), RHEL/Rocky/Fedora (.rpm); los paquetes instalan la rotación de registros para los registros de acceso y de errores
- **Listo para proxy inverso** -- Puertos públicos independientes de los de escucha (un `:80` o `:443` explícito en las URL base se anuncia tal cual se escribe), proxies de confianza por IP o red CIDR, y valores `proxy.*` del chart de Helm para un Ingress delante de UCM

---

## Inicio rápido

### Docker

```bash
docker run -d --restart=unless-stopped \
  --name ucm \
  -p 8443:8443 \
  -p 8080:8080 \
  -v ucm-data:/opt/ucm/data \
  -v ucm-config:/etc/ucm \
  neyslim/ultimate-ca-manager:latest
```

También disponible en GitHub Container Registry: `ghcr.io/neyslim/ultimate-ca-manager`. La variante FIPS lleva la etiqueta `<version>-fips` (se ejecuta con `UCM_FIPS=1`).

### Debian/Ubuntu

Descarga el paquete `.deb` de la [última versión](https://github.com/NeySlim/ultimate-ca-manager/releases/latest):

```bash
sudo dpkg -i ucm_<version>_all.deb
sudo systemctl enable --now ucm
```

### RHEL/Rocky/Fedora

Descarga el paquete `.rpm` de la [última versión](https://github.com/NeySlim/ultimate-ca-manager/releases/latest): `ucm-VERSION-1.fc43.noarch.rpm` para Fedora, `ucm-el9-VERSION-1.el9.noarch.rpm` para RHEL, Rocky Linux y AlmaLinux 9, `ucm-el10-VERSION-1.el10.noarch.rpm` para las mismas distribuciones en la versión 10.

```bash
sudo dnf install ./ucm-VERSION-1.fc43.noarch.rpm
sudo systemctl enable --now ucm
```

**Acceso:** `https://localhost:8443` o `https://your-server-fqdn:8443`
**Primer inicio de sesión:** `admin`, con la contraseña generada en el primer arranque: `sudo cat /opt/ucm/data/initial-admin-password` (Docker: `docker exec <container> cat /opt/ucm/data/initial-admin-password`). Debe cambiarse en el primer inicio de sesión. Consulta [First access](docs/installation/README.md#first-access) para indicar la tuya.

Consulta la [Guía de instalación](docs/installation/README.md) para todos los métodos, incluidos Docker Compose y la instalación desde el código fuente.

---

## Documentación

| Recurso | Enlace |
|----------|------|
| Wiki (documentación completa) | [github.com/NeySlim/ultimate-ca-manager/wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki) |
| Instalación | [docs/installation/](docs/installation/README.md) |
| Guía de usuario | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| Guía de administración | [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md) |
| Microsoft Intune SCEP | [docs/integrations/intune-scep.md](docs/integrations/intune-scep.md) |
| Clientes del proxy ACME | [docs/integrations/acme-proxy-clients.md](docs/integrations/acme-proxy-clients.md) |
| Referencia de la API | [docs/API_REFERENCE.md](docs/API_REFERENCE.md) |
| Seguridad | [docs/SECURITY.md](docs/SECURITY.md) |
| Guía de actualización | [UPGRADE.md](UPGRADE.md) |
| Registro de cambios | [CHANGELOG.md](CHANGELOG.md) |

---

## Pila tecnológica

| Componente | Tecnología |
|-----------|------------|
| Frontend | React 18, Vite, Radix UI, Recharts |
| Backend | Python 3.11+, Flask, SQLAlchemy |
| Base de datos | SQLite o PostgreSQL |
| Servidor | Gunicorn + gevent WebSocket |
| Criptografía | pyOpenSSL, cryptography |
| Autenticación | Cookies de sesión, WebAuthn/FIDO2, TOTP, mTLS |

---

## Ubicación de los archivos

| Elemento | Ruta |
|------|------|
| Aplicación | `/opt/ucm/` |
| Datos y base de datos | `/opt/ucm/data/` |
| Configuración (DEB/RPM) | `/etc/ucm/ucm.env` |
| Registros (DEB/RPM) | `/var/log/ucm/` |
| Servicio | `systemctl status ucm` |

Docker: datos en `/opt/ucm/data/` (montar como volumen), configuración mediante variables de entorno, registros a stdout.

---

## Contribuir

Las pull requests se dirigen a `dev`, y la primera te pide firmar una vez el
[CLA](CLA.md). Consulta [CONTRIBUTING.md](CONTRIBUTING.md) para el resto: cómo
informar de un error de forma útil, qué aspecto tiene una pull request revisable,
y las reglas sobre pruebas, traducciones y migraciones.

---

## Licencia

UCM es software libre bajo la [GNU AGPL v3.0 only](LICENSE). Ejecutarlo, a cualquier escala y con fines comerciales, no cuesta nada; hay disponible una [licencia comercial](COMMERCIAL-LICENSE.md) para quienes lo modifican y no pueden publicar sus cambios.

Las versiones anteriores a la 2.243 siguen bajo su licencia original, BSD 3-Clause con la Commons Clause.

---

## Soporte

- [GitHub Issues](https://github.com/NeySlim/ultimate-ca-manager/issues)
- [GitHub Wiki](https://github.com/NeySlim/ultimate-ca-manager/wiki)

Si UCM te resulta útil, considera apoyar su desarrollo:

<a href="https://ko-fi.com/neyslim"><img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Support on Ko-fi" /></a>
