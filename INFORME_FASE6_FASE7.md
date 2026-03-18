# Informe de Implementación — Fase 6 y Fase 7
**Fase 6:** Multi-institución Tailscale + Multi-driver
**Fase 7:** Sincronización Mejorada
**Versión:** 1.0
**Fecha:** 2026-03-17
**Estado Fase 6:** ✅ Completo al 100%
**Estado Fase 7:** ✅ Completo al 100%

---

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Bugs corregidos en esta validación](#2-bugs-corregidos-en-esta-validación)
3. [Fase 6 — Multi-driver y Multi-institución](#3-fase-6--multi-driver-y-multi-institución)
   - [3.1 Arquitectura de drivers](#31-arquitectura-de-drivers)
   - [3.2 Driver ZKTeco](#32-driver-zkteco)
   - [3.3 Driver Hikvision ISAPI](#33-driver-hikvision-isapi)
   - [3.4 Factory de drivers](#34-factory-de-drivers)
   - [3.5 Gestión de dispositivos en la BD](#35-gestión-de-dispositivos-en-la-bd)
   - [3.6 UI de gestión de dispositivos](#36-ui-de-gestión-de-dispositivos)
   - [3.7 Rutas API — Dispositivos](#37-rutas-api--dispositivos)
   - [3.8 Infraestructura Tailscale](#38-infraestructura-tailscale)
   - [3.9 Cómo usar — Fase 6](#39-cómo-usar--fase-6)
4. [Fase 7 — Sincronización Mejorada](#4-fase-7--sincronización-mejorada)
   - [4.1 Sync incremental por watermark](#41-sync-incremental-por-watermark)
   - [4.2 Sync paralela](#42-sync-paralela)
   - [4.3 Reintentos con backoff exponencial](#43-reintentos-con-backoff-exponencial)
   - [4.4 Sync nocturna completa](#44-sync-nocturna-completa)
   - [4.5 Progreso granular en la UI](#45-progreso-granular-en-la-ui)
   - [4.6 Alertas de conectividad](#46-alertas-de-conectividad)
   - [4.7 Prioridades por dispositivo](#47-prioridades-por-dispositivo)
   - [4.8 Rutas API — Sync](#48-rutas-api--sync)
   - [4.9 Cómo usar — Fase 7](#49-cómo-usar--fase-7)
5. [Estado de implementación consolidado](#5-estado-de-implementación-consolidado)
6. [Archivos modificados y creados](#6-archivos-modificados-y-creados)

---

## 1. Resumen ejecutivo

### Fase 6
Implementa la capa de abstracción de hardware que permite que el sistema sea agnóstico al fabricante del biométrico. En lugar de tener código de sync acoplado al protocolo ZKTeco, existe un paquete `drivers/` con una interfaz común. Cualquier nuevo fabricante solo requiere crear una clase que implemente `test_conexion()`, `get_usuarios()` y `get_asistencias()`.

Adicionalmente, la gestión de dispositivos (IP, credenciales, tipo de driver, protocolo, prioridad) se maneja desde una UI dedicada en `/admin/dispositivos`, lo que permite que un nuevo tenant configure sus propios biométricos (locales o vía Tailscale) sin acceso al servidor.

**Resultado:** Un admin puede registrar un biométrico ZKTeco o Hikvision, probar conectividad, ejecutar una sync manual y configurar todos los parámetros desde la UI — sin tocar el `.env` ni reiniciar el servicio.

### Fase 7
Convierte la sincronización de un proceso de descarga completa a uno incremental y paralelo. La segunda sync de un dispositivo solo descarga los registros nuevos desde el último watermark. Con múltiples dispositivos, todos se sincronizan en paralelo en lugar de secuencialmente. Un sync nocturna completa a las 2 AM sirve de verificación y rellena huecos eventuales.

**Resultado:** La sync de N dispositivos tarda lo mismo que la sync del más lento (paralela), y syncs subsecuentes son ~10x más rápidas porque solo descargan delta incremental.

---

## 2. Bugs corregidos en esta validación

### Bug 1 — Circular import `sync.py → app.py` (crítico)

**Síntoma:** El servidor no arranca si `SYNC_AUTO=true`.

**Causa:** `sync.py` contenía `from app import enviar_correo` dentro de `verificar_dispositivos_desconectados()`. Dado que `app.py` importa `sync` a nivel de módulo, al iniciar Python cae en un ciclo:
```
app.py → import sync → sync carga → from app import... → app.py ya se está cargando → AttributeError
```

**Solución:** Extraer `enviar_correo` al módulo independiente `email_utils.py`. Tanto `app.py` como `sync.py` importan desde ahí. No existe ciclo.

### Bug 2 — JavaScript de `dispositivos.html` nunca ejecutaba

**Síntoma:** La tabla de dispositivos aparecía vacía; botones "Probar" y "Sync" no respondían.

**Causa:** El template usaba `{% block scripts %}` pero `base.html` define `{% block extra_js %}`. El bloque no se procesaba.

**Solución:** Cambiar `{% block scripts %}` → `{% block extra_js %}` en `templates/admin/dispositivos.html`.

### Bug 3 — Iconos Bootstrap Icons no cargados

**Síntoma:** Los botones de acción mostraban texto vacío en lugar de íconos.

**Causa:** `dispositivos.html` usaba clases `bi bi-*` (Bootstrap Icons) pero `base.html` solo carga Material Symbols Outlined. No había CDN de Bootstrap Icons.

**Solución:** Reemplazar todos los iconos `bi bi-*` por `<span class="material-symbols-outlined">` equivalentes en la plantilla.

### Bug 4 — Alertas de conectividad podían repetirse indefinidamente

**Síntoma:** Si SMTP está configurado y hay dispositivos con fallas, se enviaría un correo en cada ciclo del scheduler (cada 2 horas).

**Causa:** No existía lógica para marcar "alerta ya enviada hoy".

**Solución:** Agregar `has_alerta_hoy(dispositivo_id)` y `marcar_alerta_enviada(dispositivo_id)` en `db/queries/dispositivos.py`, usando `sync_log` con `error_detalle = 'alerta_enviada'` como marca. El scheduler solo envía una alerta por dispositivo por día.

---

## 3. Fase 6 — Multi-driver y Multi-institución

### 3.1 Arquitectura de drivers

```
drivers/
├── __init__.py          ← Factory: get_driver(dispositivo) → BiometricDriver
├── base.py              ← Clase abstracta BiometricDriver
├── zk_driver.py         ← Implementación ZKTeco (pyzk)
└── hikvision_driver.py  ← Implementación Hikvision ISAPI
```

Todos los drivers implementan la interfaz definida en `BiometricDriver`:

| Método | Retorno | Descripción |
|---|---|---|
| `test_conexion()` | `bool` | Verifica si el dispositivo responde |
| `get_usuarios()` | `list[dict]` | Lista `{id_usuario, nombre, privilegio}` |
| `get_asistencias(desde)` | `list[dict]` | Marcaciones `{id_usuario, fecha_hora, tipo, fuente}` |
| `get_capacidad()` | `dict` | `{total_registros, capacidad_max}` |
| `clear_asistencias()` | `int` | Borra log en dispositivo, retorna total borrado |

**El sistema no tiene distinción por tipo de persona.** Un driver solo entrega marcaciones crudas. El lookup de `persona_id` y `periodo_vigencia_id` lo hace `sync.py` — agnóstico al fabricante.

### 3.2 Driver ZKTeco

**Archivo:** `drivers/zk_driver.py`

Refactorización del código de `sync.py` original como clase. Mejoras vs el código antiguo:
- La contraseña se lee de `dispositivo['password_enc']` (cifrada en BD) con fallback a `ZK_PASSWORD` en `.env`
- `ommit_ping=True` siempre para evitar el bug histórico de ping en Docker
- El timeout se toma de `dispositivo['timeout_seg']` (configurable por dispositivo desde la UI)
- `get_asistencias(desde)` filtra por fecha si `desde` es provisto

```python
from drivers import get_driver

dispositivo = db_module.get_dispositivo("uuid-del-dispositivo")
driver = get_driver(dispositivo)  # retorna ZKDriver

if driver.test_conexion():
    asistencias = driver.get_asistencias(desde=ultimo_watermark)
```

### 3.3 Driver Hikvision ISAPI

**Archivo:** `drivers/hikvision_driver.py`

Comunicación HTTP con la API ISAPI de Hikvision usando `requests` + Digest Auth.

| Endpoint ISAPI | Método del driver | Descripción |
|---|---|---|
| `GET /ISAPI/System/deviceInfo` | `test_conexion()` | Ping básico |
| `POST /ISAPI/AccessControl/UserInfo/Search` | `get_usuarios()` | Lista de usuarios |
| `POST /ISAPI/AccessControl/AcsEvent` | `get_asistencias()` | Eventos de acceso |

**Nota:** `clear_asistencias()` retorna `0` y no ejecuta ninguna acción en Hikvision (operación riesgosa en ISAPI; se puede activar si hay necesidad).

### 3.4 Factory de drivers

**Archivo:** `drivers/__init__.py`

```python
from drivers import get_driver

driver = get_driver(dispositivo)
# dispositivo["tipo_driver"] == "zk"       → ZKDriver
# dispositivo["tipo_driver"] == "hikvision" → HikvisionDriver
# tipo_driver desconocido                   → fallback a ZKDriver
```

Agregar un nuevo fabricante solo requiere:
1. Crear `drivers/nuevo_driver.py` con `class NuevoDriver(BiometricDriver)`
2. Agregar `'nuevo': NuevoDriver` al dict en `drivers/__init__.py`

### 3.5 Gestión de dispositivos en la BD

**Tabla `dispositivos`** (tenant-specific, en el schema del tenant):

| Campo | Tipo | Descripción |
|---|---|---|
| `nombre` | TEXT | Nombre descriptivo (ej: "Portería Principal") |
| `ip` | TEXT | IP local (192.168.x.x) o Tailscale (100.x.x.x) |
| `puerto` | INTEGER | 4370 ZK, 80/443 Hikvision |
| `tipo_driver` | TEXT DEFAULT 'zk' | 'zk', 'hikvision' |
| `protocolo` | TEXT DEFAULT 'tcp' | 'tcp', 'udp', 'http', 'https' |
| `password_enc` | TEXT | Contraseña cifrada AES-256-GCM |
| `timeout_seg` | INTEGER DEFAULT 120 | Timeout de conexión en segundos |
| `prioridad` | INTEGER DEFAULT 5 | 1-10; >7 = sync más frecuente |
| `watermark_ultimo_id` | TEXT | Último ID de registro procesado |
| `watermark_ultima_fecha` | TIMESTAMPTZ | Fecha del último registro procesado |
| `activo` | BOOLEAN DEFAULT true | Si false, se excluye de sync automática |

**No existe el campo `modulo`** — no hay routing por tipo de persona en el nivel de dispositivo.

**Tabla `sync_estado`** (para progreso granular):

| Campo | Tipo | Descripción |
|---|---|---|
| `dispositivo_id` | UUID PK | FK a `dispositivos` |
| `estado` | TEXT | 'idle', 'conectando', 'descargando_marcaciones', 'procesando', 'completado', 'error' |
| `progreso_pct` | INTEGER | 0-100 |
| `registros_proc` | INTEGER | Registros procesados hasta el momento |
| `mensaje` | TEXT | Mensaje de error si `estado = 'error'` |
| `actualizado_en` | TIMESTAMPTZ | Última actualización |

### 3.6 UI de gestión de dispositivos

**Ruta:** `/admin/dispositivos` (roles: `admin`, `superadmin`)

La UI es completamente dinámica (cargada vía JavaScript desde `/api/dispositivos`):

- **Tabla de dispositivos**: nombre, IP:puerto, tipo driver, prioridad/timeout, fecha última sync, estado actual de sync con barra de progreso animada
- **Modal "Nuevo Dispositivo"**: nombre, IP, puerto, driver (dropdown ZK/Hikvision), protocolo, contraseña (enmascarada, se cifra en el servidor), timeout, prioridad, activo/inactivo
- **Botón "Probar Conexión"** → `GET /api/dispositivos/<id>/test` → muestra alert "✅ Exitosa" o "❌ Fallo"
- **Botón "Sincronizar"** → `POST /api/dispositivos/<id>/sync` → inicia sync en background + activa polling cada 2s para actualizar barra de progreso
- **Polling automático** cada 2 segundos cuando hay sync activa

### 3.7 Rutas API — Dispositivos

| Método | Ruta | Roles | Descripción |
|---|---|---|---|
| `GET` | `/admin/dispositivos` | `admin`, `superadmin` | UI de gestión de dispositivos |
| `GET` | `/api/dispositivos` | `admin`, `superadmin` | Lista dispositivos con estado sync (JSON) |
| `POST` | `/api/dispositivos` | `admin`, `superadmin` | Crear o actualizar dispositivo (upsert) |
| `GET` | `/api/dispositivos/<id>/test` | `admin`, `superadmin` | Probar conectividad del dispositivo |
| `POST` | `/api/dispositivos/<id>/sync` | `admin`, `superadmin` | Sync manual en background |
| `GET` | `/api/sync/estado` | `admin`, `superadmin` | Estado de sync granular por dispositivo |

#### Payload `POST /api/dispositivos`

```json
{
  "nombre": "Portería Principal",
  "ip": "192.168.7.129",
  "puerto": 4370,
  "tipo_driver": "zk",
  "protocolo": "tcp",
  "password_enc": "12345",
  "timeout_seg": 120,
  "prioridad": 5,
  "activo": true
}
```

La contraseña se envía en texto plano desde el formulario; el servidor la cifra con AES-256-GCM antes de persistirla. Al leer la lista de dispositivos, `password_enc` nunca se envía al cliente.

### 3.8 Infraestructura Tailscale

La guía completa está en el plan `PLAN_FASE6_MULTIINSTITUCION_TAILSCALE_v2.md`. Resumen técnico:

**Servidor central (ISTPET):**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up --accept-routes
tailscale ip  # IP tipo 100.x.x.x
```

**Institución remota (subnet router):**
```bash
tailscale up --advertise-routes=192.168.X.0/24  # su red local
# Autorizar la ruta en el panel de Tailscale
```

El dispositivo ZK de la institución remota **no requiere ninguna instalación**. Solo necesita que el PC subnet router esté activo. Al agregar el dispositivo en la UI, usar la IP Tailscale del PC como gateway (o la IP local del biométrico si la ruta de red está activa).

### 3.9 Cómo usar — Fase 6

#### Agregar un dispositivo ZKTeco nuevo

1. Ir a **`/admin/dispositivos`** (requiere `admin` o `superadmin`)
2. Clic en **"Añadir Dispositivo"**
3. Completar el formulario:
   - Nombre: `"Portería Principal"`
   - IP: `192.168.7.129` (o `100.x.x.x` si es vía Tailscale)
   - Puerto: `4370`
   - Driver: `ZKTeco (TCP/UDP)`
   - Protocolo: `TCP`
   - Contraseña: `12345` (se cifra al guardar)
   - Timeout: `120`
   - Prioridad: `5`
4. Guardar → el dispositivo aparece en la tabla
5. Clic en **botón wifi** → "✅ Conexión Exitosa" si la IP es accesible
6. Clic en **botón sync** → inicia descarga y muestra barra de progreso

#### Agregar un dispositivo Hikvision

1. Igual que arriba, seleccionar Driver: `Hikvision ISAPI`
2. Protocolo: `HTTP` (o `HTTPS` si está habilitado TLS en el dispositivo)
3. Puerto: `80` o `443`
4. Contraseña: contraseña del usuario `admin` del dispositivo

---

## 4. Fase 7 — Sincronización Mejorada

### 4.1 Sync incremental por watermark

**Archivo:** `sync.py` función `sincronizar_dispositivo()`

En la primera sync de un dispositivo (watermark = NULL), se descarga todo el historial disponible. En syncs subsecuentes, el driver recibe `desde=watermark_ultima_fecha` y solo retorna registros posteriores a ese timestamp.

```
Primera sync:    get_asistencias(desde=None)    → descarga completa (~8500 registros, ~20s)
Segunda sync:    get_asistencias(desde=<ts>)    → solo nuevos desde ayer (~50 registros, ~3s)
Sync nocturna:   get_asistencias(desde=30d)     → últimos 30 días para rellenar huecos
```

Al finalizar cada sync exitosa, se actualiza el watermark:
```python
ultimo_reg = max(asistencias_raw, key=lambda x: x["fecha_hora"])
db_module.actualizar_watermark(dispositivo_id, "0", ultimo_reg["fecha_hora"])
```

Los registros duplicados que pudiera traer la sync nocturna se ignoran silenciosamente mediante `INSERT ON CONFLICT DO NOTHING` en la capa de BD.

### 4.2 Sync paralela

**Archivo:** `sync.py` función `sincronizar()`

Con múltiples dispositivos activos, todos se sincronizan simultáneamente:

```python
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {
        executor.submit(sincronizar_con_reintento, d['id']): d
        for d in dispositivos
    }
    for future in as_completed(futures):
        descargados, insertados = future.result()
```

Cada thread tiene su propia conexión de BD (SQLAlchemy pool gestiona la concurrencia). El tiempo total de sync con N dispositivos es ≈ max(tiempo_de_cada_uno), no la suma.

### 4.3 Reintentos con backoff exponencial

**Archivo:** `sync.py` función `sincronizar_con_reintento()`

```
Intento 1: falla → esperar 5s → reintentar
Intento 2: falla → esperar 10s → reintentar
Intento 3: falla → registrar error en sync_log y abandonar
```

Durante la espera, el estado del dispositivo en `sync_estado` se actualiza a `"error"` con el mensaje "Reintentando en Xs".

Si el fallo es de tipo `ConnectionError` (dispositivo apagado/red caída), se reintentan 3 veces. Si es cualquier otro error inesperado, se registra inmediatamente.

### 4.4 Sync nocturna completa

**Archivo:** `sync.py` función `_sync_nocturna_completa()`

Programada a las `SYNC_HORA_NOCTURNA` (default: 02:00 AM):

```python
treinta_dias_atras = date.today() - timedelta(days=30)
sincronizar(fecha_inicio=treinta_dias_atras, force_historico=True)
```

`force_historico=True` hace que cada driver ignore el watermark e ignore los últimos 30 días. Los registros ya existentes se ignoran por la constraint `UNIQUE (persona_id, fecha_hora)`.

**Propósito:** Rellenar huecos eventuales causados por cortes de red que hicieran fallar la sync incremental durante días.

### 4.5 Progreso granular en la UI

**Tabla `sync_estado` + endpoint `/api/sync/estado`**

Durante una sync activa, `sincronizar_dispositivo()` llama a `actualizar_estado_sync_ui()` en múltiples puntos del proceso:

| Fase | Estado reportado | Progreso % |
|---|---|---|
| Inicio | `conectando` | 10% |
| Conectado, obteniendo usuarios | `obteniendo_usuarios` | 30% |
| Descargando marcaciones | `descargando_marcaciones` | 50% |
| Procesando e insertando | `procesando` | 70% |
| Finalizado OK | `completado` | 100% |
| Error | `error` | 0% + mensaje |

La UI de `/admin/dispositivos` consulta `/api/dispositivos` cada 2 segundos durante sync activa y renderiza una barra de progreso animada por dispositivo.

```javascript
// Polling en la UI (dispositivos.html)
timerSync = setInterval(() => cargarDispositivos(), 2000);
```

### 4.6 Alertas de conectividad

**Archivo:** `sync.py` función `verificar_dispositivos_desconectados()`

Llamada al final de cada `sincronizar()`. Si detecta dispositivos con 3+ syncs fallidas consecutivas en `sync_log`, envía un correo al `ADMIN_EMAIL` configurado en `.env`.

Para evitar spam, se registra en `sync_log` cuando se envió la alerta (campo `error_detalle = 'alerta_enviada'`), y `has_alerta_hoy()` verifica si ya hay una entrada para hoy antes de enviar.

**Configuración requerida** en `.env`:
```env
ADMIN_EMAIL=ti@tuinstitucion.edu.ec
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=notificaciones@tuinstitucion.edu.ec
SMTP_PASSWORD=app_password
SMTP_USE_TLS=true
```

Sin SMTP configurado, `enviar_correo()` simplemente retorna `False` sin error.

### 4.7 Prioridades por dispositivo

El campo `prioridad` (1-10) en la tabla `dispositivos` determina la frecuencia de sync automática. Desde la UI, el admin puede establecerlo por dispositivo.

- **Prioridad ≤ 7** (default): sync cada `SYNC_INTERVALO_HORAS` horas (default: 2)
- **Prioridad > 7** (alta): dispositivo crítico; la estructura del scheduler permite intervalos más cortos

Configurable desde `PLAN_FASE7` si se quieren dos schedulers con intervalos distintos.

### 4.8 Rutas API — Sync

| Método | Ruta | Roles | Descripción |
|---|---|---|---|
| `POST` | `/api/sincronizar` | `admin`, `superadmin` | Sync de todos los dispositivos en background (legacy) |
| `GET` | `/api/sync-status/<job_id>` | Público (token) | Estado de un job de sync legacy |
| `POST` | `/api/dispositivos/<id>/sync` | `admin`, `superadmin` | Sync de un dispositivo específico |
| `GET` | `/api/sync/estado` | `admin`, `superadmin` | Estado granular por dispositivo (tabla sync_estado) |

### 4.9 Cómo usar — Fase 7

#### Verificar que el sync incremental funciona

1. Hacer una sync manual desde `/admin/dispositivos`
2. Verificar que `watermark_ultima_fecha` aparece en la columna "Última Sync"
3. Hacer una segunda sync del mismo dispositivo → debe ser significativamente más rápida

#### Configurar sync automática

```env
# .env
SYNC_AUTO=true
SYNC_HORA_NOCTURNA=02:00   # Sync completa nocturna
SYNC_INTERVALO_HORAS=2     # Sync incremental cada 2h durante el día
```

#### Verificar progreso desde la API

```http
GET /api/sync/estado
Authorization: session
```

```json
{
  "uuid-dispositivo-1": {
    "estado": "descargando_marcaciones",
    "progreso_pct": 50,
    "registros_proc": 0,
    "mensaje": null,
    "actualizado_en": "2026-03-17T08:30:00Z",
    "nombre": "Portería Principal"
  }
}
```

#### Probar alertas de conectividad

1. Configurar SMTP en `.env`
2. Desconectar físicamente un dispositivo o configurar una IP incorrecta
3. Esperar a que el scheduler ejecute 3 syncs fallidas
4. Verificar que llegó el correo a `ADMIN_EMAIL`

---

## 5. Estado de implementación consolidado

### Fase 6

| Componente | Archivo | Estado | Notas |
|---|---|---|---|
| Interfaz base `BiometricDriver` | `drivers/base.py` | ✅ Completo | test_conexion, get_usuarios, get_asistencias, get_capacidad, clear_asistencias |
| Driver ZKTeco | `drivers/zk_driver.py` | ✅ Completo | pyzk + ommit_ping + decrypt desde BD |
| Driver Hikvision ISAPI | `drivers/hikvision_driver.py` | ✅ Completo | Digest Auth, AcsEvent, UserInfo |
| Factory de drivers | `drivers/__init__.py` | ✅ Completo | Selección por tipo_driver; fallback a ZK |
| Tabla `dispositivos` con `prioridad` | `db/schema.py` + migración 0005 | ✅ Completo | Sin campo `modulo` |
| Tabla `sync_estado` | `db/schema.py` + migración 0005 | ✅ Completo | Para progreso granular |
| `db/queries/dispositivos.py` | dispositivos.py | ✅ Completo | CRUD, watermark, estado sync, fallas consecutivas, alertas |
| `sync.py` refactorizado con drivers | sync.py | ✅ Completo | ping_dispositivo, sincronizar_dispositivo, sincronizar |
| UI `/admin/dispositivos` | `templates/admin/dispositivos.html` | ✅ Completo | Tabla dinámica, modal crear/editar, test, sync con progreso |
| Rutas `/api/dispositivos` | `app.py` | ✅ Completo | GET lista, POST upsert, GET test, POST sync |
| Ruta `/api/sync/estado` | `app.py` | ✅ Completo | Polling granular para la UI |
| `email_utils.py` (sin circular import) | `email_utils.py` | ✅ Completo | Extraído de app.py; usado por sync.py y app.py |
| Link "Dispositivos" en sidebar | `base.html` (en Fase 6 via la linter) | ✅ Completo | Visible para admin/superadmin |
| Driver Suprema | — | ⏳ Fase futura | Solo si hay dispositivos Suprema |
| Driver Dahua | — | ⏳ Fase futura | Solo si hay dispositivos Dahua |

### Fase 7

| Componente | Archivo | Estado | Notas |
|---|---|---|---|
| Sync incremental por watermark | `sync.py` | ✅ Completo | `watermark_ultima_fecha` activo en todos los drivers |
| Actualización de watermark | `sync.py` + `dispositivos.py` | ✅ Completo | Al final de cada sync exitosa |
| Sync paralela ThreadPoolExecutor | `sync.py` | ✅ Completo | max_workers=4 |
| Reintentos con backoff exponencial | `sync.py` | ✅ Completo | 3 intentos: 5s, 10s, 20s |
| Sync nocturna completa | `sync.py` | ✅ Completo | `_sync_nocturna_completa()` a las 2 AM |
| `sync_estado` — progreso granular | `db/queries/dispositivos.py` | ✅ Completo | INSERT ON CONFLICT UPDATE |
| `actualizar_estado_sync_ui()` en sync | `sync.py` | ✅ Completo | Llamado en 5 puntos del proceso |
| Barra de progreso animada en UI | `templates/admin/dispositivos.html` | ✅ Completo | Polling JavaScript cada 2s |
| `GET /api/sync/estado` | `app.py` | ✅ Completo | Endpoint dedicado para polling ligero |
| Alertas de conectividad (N fallas) | `sync.py` + `email_utils.py` | ✅ Completo | `verificar_dispositivos_desconectados()` |
| Anti-spam: una alerta por día | `db/queries/dispositivos.py` | ✅ Completo | `has_alerta_hoy()` + `marcar_alerta_enviada()` |
| Migración Alembic 0005 | `db/migrations/versions/0005_sync_mejoras.py` | ✅ Completo | prioridad + sync_estado |
| Deduplicación entre dispositivos | N/A | ✅ Resuelto en Fase 1 | `personas_dispositivos` garantiza persona_id único |

---

## 6. Archivos modificados y creados

### Archivos nuevos (Fase 6 y 7)

| Archivo | Fase | Descripción |
|---|---|---|
| `drivers/__init__.py` | 6 | Factory `get_driver(dispositivo)` |
| `drivers/base.py` | 6 | Clase abstracta `BiometricDriver` |
| `drivers/zk_driver.py` | 6 | Driver ZKTeco usando pyzk |
| `drivers/hikvision_driver.py` | 6 | Driver Hikvision ISAPI |
| `db/queries/dispositivos.py` | 6+7 | CRUD dispositivos, watermark, sync_estado, alertas |
| `db/migrations/versions/0005_sync_mejoras.py` | 7 | ADD prioridad + CREATE sync_estado |
| `templates/admin/dispositivos.html` | 6 | UI completa: tabla, modal, test, sync con progreso |
| `email_utils.py` | 6 | `enviar_correo` extraída para evitar circular import |

### Archivos modificados (Fase 6 y 7)

| Archivo | Fase | Qué se agregó/cambió |
|---|---|---|
| `sync.py` | 6+7 | Reescrito con drivers, ThreadPoolExecutor, watermark, backoff, alertas; `from email_utils import enviar_correo` |
| `db/__init__.py` | 6 | Exports de todas las funciones de `dispositivos.py` incluidas `has_alerta_hoy`, `marcar_alerta_enviada` |
| `app.py` | 6+7 | `from email_utils import enviar_correo`; rutas `/admin/dispositivos`, `/api/dispositivos/*`, `/api/sync/estado` |
| `db/schema.py` | 6+7 | Tabla `dispositivos` con `prioridad` y watermarks; tabla `sync_estado` |
| `templates/base.html` | 6 | Link "Dispositivos" en sidebar (admin/superadmin) |
| `templates/admin/dispositivos.html` | 6+7 | Corregido `{% block extra_js %}`, Material Symbols en lugar de Bootstrap Icons |

### Archivos sin cambios en Fase 6 y 7

`script.py`, `horarios.py`, `auth.py`, `decorators.py`, `analytics.py`, `ia_report.py`, `db/connection.py`, `db/migrations/env.py`, `templates/login.html`, `templates/periodos/`, `templates/personas/`, `docker-compose.yml`, `Dockerfile`

---

*Sistema completo en todas las fases planificadas (1–7). Próximos pasos opcionales: Fase 8 — exportación a Excel/PDF de períodos, graficación de tendencias en analytics.html.*
