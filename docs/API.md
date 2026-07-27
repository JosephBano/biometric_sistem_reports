---
title: Referencia de la API HTTP
tags: [api, rest, flask, endpoints, json]
status: active
created: 2026-07-01
updated: 2026-07-01
authors: [documenter]
related: ["[[ARQUITECTURA]]", "[[AUTENTICACION]]", "[[ER]]", "[[ADR-0001-modularizacion-monolito-flask]]"]
---

# Referencia de la API HTTP

## Resumen

Esta es la referencia completa de los **81 endpoints HTTP** registrados en `app.py` (2 512 líneas).
Incluye vistas HTML (Jinja2 renderizado server-side) y endpoints JSON para integraciones internas.

Convenciones:

- **REST + HTML**: la mayoría de las mutaciones son `POST` (no `PUT/DELETE`) para que funcionen con
  formularios HTML estándar (sin `_method`). Varios recursos exponen endpoints "estilo REST" para CRUD
  AJAX: `/api/horarios`, `/api/justificaciones`, `/api/feriados`.
- **CSRF**: requerida en todos los `POST` de rutas HTML (no `/api/*`). El token se lee de `csrf_token` en
  el form o del header `X-CSRF-Token`.
- **Errores**: `{"error": "<mensaje>", ...}` en JSON. Las rutas HTML devuelven flash + `302` o `4xx` con
  plantilla.
- **Content-Type**: `application/json` para respuestas `/api/*`, `text/csv` para descargas, `text/html`
  para vistas.
- **Content negotiation**: los decoradores detectan APIs por `request.path.startswith("/api/")` o
  `Accept: application/json` y devuelven JSON en lugar de `redirect`/`render_template`.
- **Autenticación**: sesión Flask (cookie `session`) — todas las rutas excepto `/login` (GET) y
  `/biometrico/static/*` requieren sesión activa.

> **Importante**: la API no tiene versionado explícito. Las URLs raíz son estables; las migraciones de
> contrato se hacen en `/api/v2/*` cuando se decida (ver backlog P2).

---

## Versionado y mount

Todas las rutas se montan bajo el prefijo `/biometrico` vía `DispatcherMiddleware`
(`app.py:51-53`):

```python
app.wsgi_app = DispatcherMiddleware(NotFound(), {
    '/biometrico': app.wsgi_app,
})
```

Por lo tanto, una ruta registrada como `/login` en Flask se accede en producción como
`https://host/biometrico/login`. La documentación muestra la **ruta interna** (sin prefijo). Para
probar en local:

```bash
# local (sin prefijo)
curl http://localhost:5000/login

# detrás del DispatcherMiddleware
curl http://localhost:5000/biometrico/login
```

Las IPs del cliente se extraen con `ProxyFix` (`app.py:49`) leyendo `X-Forwarded-For`, `X-Forwarded-Proto`,
`X-Forwarded-Host` y `X-Forwarded-Prefix`.

---

## Tabla maestra de endpoints

Las 81 filas siguientes son la fuente directa extraída con `grep -n "^@app.route" app.py`. La columna
"Auth requerida" indica que el endpoint exige sesión Flask activa (validada por `before_request`); la
columna "Decoradores RBAC" muestra los `@require_role`/`@require_tipo_persona` explícitos. Donde no se ve
decorador (rutas accesibles a cualquier usuario autenticado), se marca "?".

| # | Método | Ruta (interna) | Blueprint objetivo | Decoradores RBAC | Auth requerida | CSRF | Descripción |
|---|---|---|---|---|---|---|---|
| 1 | GET, POST | `/login` | `auth_bp` | — (autentica) | No (público) | Sí (POST) | Formulario de login. POST verifica credenciales e inicia sesión. Rate limit 5/15min por IP. |
| 2 | POST | `/logout` | `auth_bp` | — (autentica) | Sí | Sí | Cierra la sesión, registra audit `logout`, redirige a `/login`. |
| 3 | POST | `/admin/switch-tenant` | `auth_bp` | `@require_role('superadmin')` | Sí | Sí | Cambia `session["tenant_schema"]` para impersonar un tenant. |
| 4 | GET | `/` | `dashboard_bp` | ? | Sí | N/A | Renderiza `dashboard.html` (panel principal con KPIs y estado de sync). |
| 5 | GET | `/configuracion` | `dashboard_bp` | ? | Sí | N/A | Renderiza `configuracion.html` (vista de configuración del tenant). |
| 6 | GET | `/justificaciones-vista` | `dashboard_bp` | ? | Sí | N/A | Renderiza `justificaciones.html` (vista de justificaciones). |
| 7 | GET | `/reportes` | `dashboard_bp` | ? | Sí | N/A | Renderiza `reportes.html` (vista de generación de reportes). |
| 8 | GET | `/descargar/&lt;filename&gt;` | `dashboard_bp` | ? | Sí | N/A | Descarga un archivo previamente generado de `REPORTS_FOLDER`. 404 si expirado. |
| 9 | GET | `/api/estado-sync` | `devices_bp` | ? | Sí | N/A | Estado global de sync: dispositivos activos, capacidad, días para llenado. |
| 10 | GET | `/api/dispositivos` | `devices_bp` | `@require_role('admin', 'superadmin')` | Sí | N/A | Lista todos los dispositivos con su estado (sync, capacidad, registros). |
| 11 | POST | `/api/dispositivos` | `devices_bp` | `@require_role('admin', 'superadmin')` | Sí | Exento | Crea o reemplaza un dispositivo (cifra `password_enc` con AES-256-GCM). |
| 12 | PUT | `/api/dispositivos/&lt;id&gt;` | `devices_bp` | `@require_role('admin', 'superadmin')` | Sí | Exento | Edita un dispositivo existente. |
| 13 | DELETE | `/api/dispositivos/&lt;id&gt;` | `devices_bp` | `@require_role('superadmin')` | Sí | Exento | Elimina (soft-delete) un dispositivo. |
| 14 | GET | `/api/dispositivos/&lt;id&gt;/test` | `devices_bp` | `@require_role('admin', 'superadmin')` | Sí | N/A | Ping al dispositivo ZK/Hikvision. Retorna `{"ok": true|false}`. |
| 15 | POST | `/api/dispositivos/&lt;id&gt;/sync` | `devices_bp` | `@require_role('admin', 'superadmin')` | Sí | Exento | Lanza sync en background para el dispositivo. Retorna `{"status": "procesando"}`. |
| 16 | GET | `/api/usuarios-zk` | `devices_bp` | `@require_role('admin', 'superadmin')` | Sí | N/A | Lista usuarios del biométrico con estado de vinculación a personas. |
| 17 | POST | `/api/usuarios-zk/&lt;id_usuario&gt;/vincular` | `devices_bp` | `@require_role('admin', 'superadmin')` | Sí | Exento | Vincula un `id_usuario_zk` con una persona del catálogo. |
| 18 | GET | `/api/personas-lista` | `devices_bp` | `@require_role('admin', 'superadmin')` | Sí | N/A | Lista simplificada de personas para selectores. |
| 19 | GET | `/api/sync/estado` | `devices_bp` | `@require_role('admin', 'superadmin')` | Sí | N/A | Estado de sync granular por dispositivo (para polling). |
| 20 | POST | `/api/sincronizar` | `devices_bp` | `@require_role('admin', 'superadmin')` | Sí | Exento | Inicia sync con rango de fechas opcional. Retorna `job_id` para polling. |
| 21 | GET | `/api/sync-status/&lt;job_id&gt;` | `devices_bp` | ? | Sí | N/A | Estado de un job de sync en curso. |
| 22 | GET | `/api/personas-db` | `periods_bp` | ? | Sí | N/A | Lista personas con horario cargado (para selector de reportes). |
| 23 | GET | `/api/alertas/tardanzas-severas` | `analytics_bp` | ? | Sí | N/A | Personas con ≥ 3 tardanzas severas en el rango (default: mes en curso). |
| 24 | GET | `/presencia` | `dashboard_bp` | ? | Sí | N/A | Vista cruda de marcaciones. Soporta `?export=csv`. |
| 25 | POST | `/api/generar-desde-db` | `reports_bp` | `@require_role('superadmin', 'admin', 'gestor')` | Sí | Exento | Genera reporte PDF/DOCX desde la BD (`modo: general|persona|varias`). |
| 26 | POST | `/api/reportes/enviar-email` | `reports_bp` | `@require_role('superadmin', 'admin', 'gestor')` | Sí | Exento | Genera reporte de una persona y lo envía por email. |
| 27 | POST | `/api/limpiar-dispositivo` | `devices_bp` | `@require_role('superadmin', 'admin')` | Sí | Exento | Borra los registros de marcación de un dispositivo (requiere `confirmar: true`). |
| 28 | GET | `/api/backup/descargar` | `reports_bp` | `@require_role('superadmin', 'admin')` | Sí | N/A | **(Fase 2)** Descarga dump completo de la BD en formato `pg_dump -Fc` (`backup_completo_YYYYMMDD_HHMM.dump`). Registra en `audit_log`. |
| 29 | GET | `/api/backup/csv` | `reports_bp` | `@require_role('superadmin', 'admin', 'gestor')` | Sí | N/A | Descarga CSV con todas las marcaciones (`asistencias_backup_YYYYMMDD.csv`). |
| 30 | POST | `/api/historicos/importar` | `system_bp` | `@require_role('superadmin', 'admin')` | Sí | Exento | Importa histórico desde `.csv` o `.xlsx` con columnas `id_usuario`, `nombre`, `fecha_hora`. |
| 30b | GET | `/api/scheduler/estado` | `system_bp` | `@require_role('superadmin', 'admin')` | Sí | N/A | **(Fase 1)** Estado del scheduler (activo/inactivo, hora, próxima corrida) + últimas 10 corridas de `public.scheduler_runs`. |
| 31 | POST | `/api/horarios/importar` | `schedule_bp` | `@require_role('superadmin', 'admin', 'gestor')` | Sí | Exento | Importa horarios desde archivo `.csv`, `.obd` o `.ods`. |
| 32 | GET | `/api/horarios/estado` | `schedule_bp` | ? | Sí | N/A | Estado actual de los horarios cargados (totales, fuente, fecha). |
| 33 | GET | `/api/horarios` | `schedule_bp` | ? | Sí | N/A | Lista todos los horarios por persona. |
| 34 | GET | `/api/horarios/exportar` | `schedule_bp` | `@require_role('superadmin', 'admin', 'gestor')` | Sí | N/A | Descarga CSV con todos los horarios. |
| 35 | POST | `/api/horarios` | `schedule_bp` | `@require_role('superadmin', 'admin', 'gestor')` | Sí | Exento | Crea un horario nuevo. 409 si el `id_usuario` ya existe. |
| 36 | PUT | `/api/horarios/&lt;id_usuario&gt;` | `schedule_bp` | `@require_role('superadmin', 'admin', 'gestor')` | Sí | Exento | Actualiza un horario existente. 404 si no existe. |
| 37 | DELETE | `/api/horarios/&lt;id_usuario&gt;` | `schedule_bp` | `@require_role('superadmin', 'admin')` | Sí | Exento | Elimina un horario. |
| 38 | GET | `/api/justificaciones` | `attendance_bp` | ? | Sí | N/A | Lista justificaciones en un rango de fechas. |
| 39 | POST | `/api/justificaciones` | `attendance_bp` | `@require_role('superadmin', 'admin', 'gestor')` | Sí | Exento | Crea una justificación (tipos: ausencia, tardanza, almuerzo, incompleto, salida_anticipada, permiso). |
| 40 | PATCH | `/api/justificaciones/&lt;int:jid&gt;` | `attendance_bp` | ? | Sí | Exento | Cambia el estado de una justificación (`aprobada`/`rechazada`/`pendiente`). |
| 41 | GET | `/api/justificaciones/&lt;int:jid&gt;` | `attendance_bp` | ? | Sí | N/A | Obtiene una justificación por ID. |
| 42 | PUT | `/api/justificaciones/&lt;int:jid&gt;` | `attendance_bp` | ? | Sí | Exento | Actualiza todos los campos editables de una justificación. |
| 43 | DELETE | `/api/justificaciones/&lt;int:jid&gt;` | `attendance_bp` | `@require_role('superadmin', 'admin')` | Sí | Exento | Elimina una justificación. |
| 44 | GET | `/api/feriados` | `attendance_bp` | ? | Sí | N/A | Lista feriados (opcional: `?anio=YYYY`). |
| 45 | POST | `/api/feriados` | `attendance_bp` | `@require_role('superadmin', 'admin')` | Sí | Exento | Crea un feriado (`fecha`, `descripcion`, `tipo`). |
| 46 | DELETE | `/api/feriados/&lt;fecha&gt;` | `attendance_bp` | `@require_role('superadmin', 'admin')` | Sí | Exento | Elimina el feriado de una fecha. |
| 47 | POST | `/api/feriados/importar` | `attendance_bp` | `@require_role('superadmin', 'admin')` | Sí | Exento | Importa feriados desde CSV. |
| 48 | GET | `/api/feriados/exportar` | `attendance_bp` | ? | Sí | N/A | Descarga CSV con todos los feriados. |
| 49 | POST | `/api/categorizar-break` | `breaks_bp` | `@require_role('superadmin', 'admin', 'gestor')` | Sí | Exento | Categoriza un break (`almuerzo`/`permiso`/`injustificado`). |
| 50 | GET | `/admin/tenants` | `admin_bp` | `@require_role('superadmin')` | Sí | N/A | Renderiza `admin/tenants.html` (lista de tenants). |
| 51 | POST | `/admin/tenants` | `admin_bp` | `@require_role('superadmin')` | Sí | Sí | Crea un tenant nuevo y provisiona su schema PostgreSQL. |
| 52 | POST | `/admin/tenants/&lt;tenant_id&gt;` | `admin_bp` | `@require_role('superadmin')` | Sí | Sí | Activa/desactiva un tenant (HTML form usa POST por compatibilidad). |
| 53 | GET | `/admin/dispositivos` | `admin_bp` | `@require_role('superadmin', 'admin')` | Sí | N/A | Renderiza `admin/dispositivos.html` (UI de gestión de dispositivos). |
| 54 | GET | `/admin/usuarios` | `admin_bp` | `@require_role('superadmin', 'admin')` | Sí | N/A | Renderiza `admin/usuarios.html` (lista de usuarios del tenant). |
| 55 | POST | `/admin/usuarios` | `admin_bp` | `@require_role('superadmin', 'admin')` | Sí | Sí | Crea un usuario nuevo en el tenant activo. |
| 56 | POST | `/admin/usuarios/&lt;usuario_id&gt;` | `admin_bp` | `@require_role('superadmin', 'admin')` | Sí | Sí | Edita roles, scopes y estado activo de un usuario. |
| 57 | GET | `/admin/superadmin/usuarios` | `admin_bp` | `@require_role('superadmin')` | Sí | N/A | Panel global cross-tenant: todos los usuarios de todos los tenants. |
| 58 | DELETE | `/api/superadmin/usuarios/&lt;usuario_id&gt;` | `admin_bp` | `@require_role('superadmin')` | Sí | Exento | Soft-delete de un usuario de cualquier tenant. |
| 59 | POST | `/api/superadmin/usuarios` | `admin_bp` | `@require_role('superadmin')` | Sí | Exento | Crea un usuario en un tenant específico (asignado por `tenant_id`). |
| 60 | POST | `/api/superadmin/usuarios/mover` | `admin_bp` | `@require_role('superadmin')` | Sí | Exento | Mueve un usuario de un tenant a otro (soft-delete en origen + crea en destino). |
| 61 | GET | `/periodos` | `periods_bp` | `@require_role('admin', 'superadmin', 'gestor')` | Sí | N/A | Renderiza `periodos/lista.html` (periodos activos e historial). |
| 62 | POST | `/periodos/crear` | `periods_bp` | `@require_role('admin', 'superadmin')` | Sí | Sí | Crea un nuevo periodo de prácticas. |
| 63 | GET | `/periodos/&lt;id&gt;` | `periods_bp` | `@require_role('admin', 'superadmin', 'gestor')` | Sí | N/A | Renderiza detalle del periodo con asistencia calculada por persona. |
| 64 | POST | `/periodos/&lt;id&gt;/importar-personas` | `periods_bp` | `@require_role('admin', 'superadmin')` | Sí | Sí | Importa personas de un periodo desde CSV. |
| 65 | POST | `/periodos/&lt;id&gt;/cerrar` | `periods_bp` | `@require_role('admin', 'superadmin')` | Sí | Sí | Cierra un periodo (cambia estado a `cerrado`). |
| 66 | POST | `/periodos/&lt;id&gt;/archivar` | `periods_bp` | `@require_role('admin', 'superadmin')` | Sí | Sí | Archiva un periodo cerrado. |
| 67 | POST | `/periodos/&lt;id&gt;/eliminar` | `periods_bp` | `@require_role('superadmin')` | Sí | Sí | Elimina un periodo permanentemente (solo superadmin). |
| 68 | GET | `/personas` | `people_bp` | `@require_role('admin', 'superadmin', 'gestor')` | Sí | N/A | Renderiza `personas/lista.html` con filtros por tipo/grupo/búsqueda. |
| 69 | POST | `/personas/crear` | `people_bp` | `@require_role('admin', 'superadmin')` | Sí | Sí | Crea una persona nueva en el catálogo del tenant. |
| 70 | POST | `/personas/&lt;id&gt;` | `people_bp` | `@require_role('admin', 'superadmin')` | Sí | Sí | Edita los datos de una persona. |
| 71 | GET | `/personas/historico` | `people_bp` | `@require_role('admin', 'superadmin', 'gestor')` | Sí | N/A | Renderiza `personas/historico.html` (histórico por número de identificación). |
| 72 | GET | `/admin/grupos` | `groups_bp` | `@require_role('admin', 'superadmin')` | Sí | N/A | Renderiza `admin/grupos.html` (lista de grupos). |
| 73 | POST | `/admin/grupos` | `groups_bp` | `@require_role('admin', 'superadmin')` | Sí | Sí | Crea un grupo nuevo. |
| 74 | POST | `/admin/grupos/&lt;id&gt;` | `groups_bp` | `@require_role('admin', 'superadmin')` | Sí | Sí | Edita nombre, tipo y estado activo de un grupo. |
| 75 | GET | `/admin/categorias` | `groups_bp` | `@require_role('admin', 'superadmin')` | Sí | N/A | Renderiza `admin/categorias.html`. |
| 76 | POST | `/admin/categorias` | `groups_bp` | `@require_role('admin', 'superadmin')` | Sí | Sí | Crea una categoría (vinculada opcionalmente a un tipo de persona). |
| 77 | POST | `/admin/categorias/&lt;id&gt;` | `groups_bp` | `@require_role('admin', 'superadmin')` | Sí | Sí | Edita una categoría (nombre, estado activo). |
| 78 | GET | `/analytics` | `analytics_bp` | `@require_role('admin', 'superadmin', 'gestor')` | Sí | N/A | Renderiza `analytics.html` (últimos 30 días por defecto). |
| 79 | GET | `/analytics/periodo/&lt;periodo_id&gt;` | `analytics_bp` | `@require_role('admin', 'superadmin', 'gestor')` | Sí | N/A | Analytics detallado de un periodo con narrativo IA. |
| 80 | POST | `/api/analytics/narrativo` | `analytics_bp` | `@require_role('admin', 'superadmin', 'gestor')` | Sí | Exento | Genera narrativo IA on-demand a partir de hallazgos (DeepSeek + fallback). |
| 81 | GET | `/api/analytics` | `analytics_bp` | `@require_role('admin', 'superadmin', 'gestor')` | Sí | N/A | Hallazgos completos + narrativo para un rango de fechas. |

**Total endpoints inventariados: 81** (verificado con `grep -c "^@app.route" app.py` → 61 líneas con
`@require_role`, 81 con `@app.route`). Si difiere de los 81 reportados en [[ARQUITECTURA]], prevalece
este inventario por ser fuente directa del código.

> **Nota sobre `middleware.py`**: NO se incluye aquí. Es un servidor FastAPI/uvicorn huérfano que vive en la
> raíz del repo y expone `/asistencias`, `/usuarios` y `/asistencias-con-nombre` en otro proceso (puerto
> 8000). Ver [[ARQUITECTURA]] (sección "Backlog P2") para su destino final (eliminar o extraer a
> `services/biometric_proxy/`).

---

## Endpoints HTML vs JSON

**25 endpoints HTML** (renderizan Jinja, esperan form-POST con CSRF):

| # | Ruta | Blueprint |
|---|---|---|
| 4–8 | `/`, `/configuracion`, `/justificaciones-vista`, `/reportes`, `/descargar/...` | `dashboard_bp` |
| 24 | `/presencia` | `dashboard_bp` |
| 50 | `/admin/tenants` | `admin_bp` |
| 53 | `/admin/dispositivos` | `admin_bp` |
| 54 | `/admin/usuarios` | `admin_bp` |
| 57 | `/admin/superadmin/usuarios` | `admin_bp` |
| 61 | `/periodos` | `periods_bp` |
| 63 | `/periodos/&lt;id&gt;` | `periods_bp` |
| 68 | `/personas` | `people_bp` |
| 71 | `/personas/historico` | `people_bp` |
| 72 | `/admin/grupos` | `groups_bp` |
| 75 | `/admin/categorias` | `groups_bp` |
| 78 | `/analytics` | `analytics_bp` |
| 79 | `/analytics/periodo/&lt;id&gt;` | `analytics_bp` |

**55 endpoints JSON o file-download** (intercambian JSON o CSV; el POST no exige CSRF si está bajo
`/api/`, pero sí si es HTML):

- 1 `/login` (combinado HTML + API según content-negotiation).
- 3 `/admin/switch-tenant` (HTML form que recibe en sesión).
- 2 `/logout` (HTML form, hace redirect).
- 51 + 2 = 53 restantes.

---

## Códigos de error comunes

| Código | Significado en este sistema | Cuándo se devuelve |
|---|---|---|
| **400** | Petición malformada (body JSON inválido, fechas con formato incorrecto, campos requeridos faltantes). | Endpoints de creación/edición cuando faltan validaciones de tipo/valor. |
| **401** | No autenticado. La sesión no tiene `usuario_id`. | Cualquier endpoint protegido si no hay cookie `session` válida. En API devuelve `{"error": "No autenticado"}`; en HTML redirige a `/login`. |
| **403** | (a) Token CSRF inválido en POST HTML, o (b) rol insuficiente (`@require_role` no satisfecho), o (c) tipo de persona ausente (`@require_tipo_persona`), o (d) tenant inactivo (suspendido). | Detección API vs HTML: JSON o HTML según `Accept` o path. |
| **404** | Recurso no encontrado. | Endpoints con `<id>` cuando el ID no existe; `/api/backup/descargar` siempre (501, ver fila 28). `/periodos/<id>`, `/api/justificaciones/<jid>`, etc. |
| **409** | Conflicto (recurso duplicado). | `POST /api/horarios` cuando el `id_usuario` ya existe. `POST /api/superadmin/usuarios` cuando `email` ya registrado. |
| **429** | Rate limit excedido. | `POST /login` (5 por IP en 15 min, configurable). También `Flask-Limiter` en otros endpoints si se les añade `@limiter.limit(...)`. |
| **500** | Error interno (BD caída, excepción no capturada, dispositivo inalcanzable en sync). | Casi todos los endpoints tienen `except Exception → return jsonify({"error": str(e)}), 500`. |
| **501** | No implementado. | Reservado para stubs legacy. `/api/backup/descargar` ahora devuelve dump real (`pg_dump -Fc`). |

### Middleware 403 con tenant inactivo

`before_request` en `app.py:191-196`:

```python
if tenant_info and not tenant_info.get("activo", True):
    session.clear()
    if request.path.startswith("/api/"):
        return jsonify({"error": "Cuenta de institución suspendida"}), 403
    return render_template("login.html", error="Acceso suspendido. Contacte a soporte."), 403
```

---

## Formato de request/response (ejemplos)

### Login (POST `/login`)

Request HTML:

```bash
curl -c cookies.txt -L \
  -X POST http://localhost:5000/biometrico/login \
  -d "email=admin@istpet.edu.ec" \
  -d "password=miclave123" \
  -d "csrf_token=$(grep csrf_token cookies.txt | cut -f7)"
```

Si los datos vienen como JSON (soportado por content-negotiation):

```bash
curl -c cookies.txt \
  -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"email":"admin@istpet.edu.ec","password":"miclave123"}'
```

Respuesta típica: `302 → /biometrico/` y cookie `session=...` en headers. 401 si credenciales inválidas.
429 si se excedió el rate limit.

### Generar reporte PDF (POST `/api/generar-desde-db`)

```bash
curl -b cookies.txt \
  -X POST http://localhost:5000/biometrico/api/generar-desde-db \
  -H "Content-Type: application/json" \
  -d '{
    "fecha_inicio": "2026-06-01",
    "fecha_fin":    "2026-06-30",
    "modo":         "general",
    "persona":      "",
    "formato":      "pdf",
    "filtros": {
      "mostrar_ausencias": true,
      "mostrar_tardanza_severa": true,
      "reporte_todos_usuarios": false
    },
    "duplicado_min": 60,
    "excluidos": [""]
  }'
```

Respuesta típica:

```json
{
  "success": true,
  "download_url": "/biometrico/descargar/reporte_8a3f9c1d.pdf",
  "filename": "Reporte_Biometrico_General_DB.pdf"
}
```

Errores:

- `400` si faltan fechas o no hay registros en el rango.
- `500` si falla reportlab o la BD.

### Sincronizar dispositivo (POST `/api/sincronizar`)

```bash
curl -b cookies.txt \
  -X POST http://localhost:5000/biometrico/api/sincronizar \
  -H "Content-Type: application/json" \
  -d '{
    "fecha_inicio": "2026-06-01",
    "fecha_fin":    "2026-06-30"
  }'
```

Respuesta (sincrónico, retorna inmediatamente al lanzar el thread):

```json
{ "job_id": "a3f9c1d8b2e5", "estado": "en_progreso" }
```

Para hacer polling:

```bash
curl -b cookies.txt http://localhost:5000/biometrico/api/sync-status/a3f9c1d8b2e5
```

```json
{
  "job_id": "a3f9c1d8b2e5",
  "estado": "completado",
  "registros_descargados": 1247,
  "errores": 0
}
```

### Crear justificación (POST `/api/justificaciones`)

```bash
curl -b cookies.txt \
  -X POST http://localhost:5000/biometrico/api/justificaciones \
  -H "Content-Type: application/json" \
  -d '{
    "id_usuario":      "42",
    "nombre":          "Juan Pérez",
    "fecha":           "2026-06-15",
    "tipo":            "permiso",
    "motivo":          "Cita médica",
    "aprobado_por":    "admin@istpet.edu.ec",
    "hora_permitida":  "10:00",
    "hora_retorno_permiso": "12:00",
    "estado":          "aprobada",
    "recuperable":     false
  }'
```

Respuesta (`201 Created`):

```json
{
  "success": true,
  "justificacion": {
    "id": 17,
    "id_usuario": "42",
    "nombre": "Juan Pérez",
    "fecha": "2026-06-15",
    "tipo": "permiso",
    "estado": "aprobada",
    "created_at": "2026-07-01T16:13:55Z"
  }
}
```

### Generar narrativo IA (POST `/api/analytics/narrativo`)

```bash
curl -b cookies.txt \
  -X POST http://localhost:5000/biometrico/api/analytics/narrativo \
  -H "Content-Type: application/json" \
  -d '{
    "exito": true,
    "resumen_general": {
      "asistencia_promedio": 91.4,
      "tardanzas_totales": 12,
      "ausencias_justificadas": 3,
      "ausencias_injustificadas": 1
    },
    "hallazgos_por_persona": [ ... ]
  }'
```

Respuesta:

```json
{ "narrativo": "Durante los últimos 30 días, la asistencia promedio fue de 91.4%, ..." }
```

Si `DEEPSEEK_API_KEY` no está seteado, el generador cae al fallback basado en reglas (todavía útil).

---

## Autenticación y CSRF en la API

### Sesión

- **Cookie**: `session` (Flask default). `HttpOnly`, `SameSite=Lax`. Signed con `FLASK_SECRET_KEY`.
- **Obtención**: tras `POST /login` exitoso.
- **Reutilización**: enviar la cookie en cada request con `-b cookies.txt` (curl) o el equivalente en
  cliente.

### CSRF

**Para endpoints HTML** (`POST /login`, `POST /admin/*`, etc.):

```bash
# 1) GET del form (típicamente /admin/usuarios)
curl -c cookies.txt http://localhost:5000/biometrico/admin/usuarios

# 2) Extraer csrf_token de la cookie de sesión
# (en la práctica: scrapear de la respuesta HTML o leer de session["csrf_token"])
TOKEN=$(awk '/csrf_token/ {print $7}' cookies.txt)

# 3) POST con el token
curl -b cookies.txt \
  -X POST http://localhost:5000/biometrico/admin/usuarios \
  -d "csrf_token=$TOKEN" \
  -d "nombre=Juan" \
  -d "email=juan@inst.edu.ec" \
  ...
```

**Para endpoints `/api/*`**: el CSRF está **exento** por convención (ver `validate_csrf` en
`app.py:138-143`). Si una integración externa necesita CSRF en una API (caso raro), enviar el token
en header `X-CSRF-Token`:

```bash
curl -b cookies.txt \
  -H "X-CSRF-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:5000/biometrico/api/some-protected-endpoint
```

### Ejemplo completo (3 endpoints representativos)

```bash
# 1. Login (almacena cookie en cookies.txt)
curl -c cookies.txt -b cookies.txt \
  -X POST http://localhost:5000/biometrico/login \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"email":"admin@istpet.edu.ec","password":"miclave123"}'

# 2. Lanzar sync incremental (POST /api/sincronizar)
curl -b cookies.txt \
  -X POST http://localhost:5000/biometrico/api/sincronizar \
  -H "Content-Type: application/json" \
  -d '{}'

# 3. Listar justificaciones del mes
curl -b cookies.txt \
  "http://localhost:5000/biometrico/api/justificaciones?fecha_inicio=2026-06-01&fecha_fin=2026-06-30"
```

---

## Agrupación por Blueprint objetivo

Cada Blueprint es la unidad de ownership post-refactor (ver [[ADR-0001-modularizacion-monolito-flask]] y
[[ARQUITECTURA]]). En la tabla maestra, la columna "Blueprint objetivo" indica a qué módulo
`app/web/*_bp.py` se moverá el endpoint durante la Fase 3 del refactor.

### `auth_bp` — Autenticación (3 rutas)

| # | Método | Ruta | Decorador RBAC | Descripción corta |
|---|---|---|---|---|
| 1 | GET, POST | `/login` | — | Login (rate limit 5/15min) |
| 2 | POST | `/logout` | — | Cierre de sesión |
| 3 | POST | `/admin/switch-tenant` | superadmin | Impersonar tenant |

### `dashboard_bp` — Vistas HTML principales (6 rutas)

| # | Método | Ruta | Decorador RBAC | Descripción corta |
|---|---|---|---|---|
| 4 | GET | `/` | ? | Dashboard |
| 5 | GET | `/configuracion` | ? | Configuración del tenant |
| 6 | GET | `/justificaciones-vista` | ? | Vista de justificaciones |
| 7 | GET | `/reportes` | ? | Vista de reportes |
| 8 | GET | `/descargar/&lt;filename&gt;` | ? | Descargar reporte generado |
| 24 | GET | `/presencia` | ? | Vista cruda de marcaciones |

### `devices_bp` — Dispositivos biométricos y sync (14 rutas)

| # | Método | Ruta | Decorador RBAC | Descripción corta |
|---|---|---|---|---|
| 9 | GET | `/api/estado-sync` | ? | Estado global |
| 10 | GET | `/api/dispositivos` | admin, superadmin | Listar dispositivos |
| 11 | POST | `/api/dispositivos` | admin, superadmin | Crear/reemplazar |
| 12 | PUT | `/api/dispositivos/&lt;id&gt;` | admin, superadmin | Editar |
| 13 | DELETE | `/api/dispositivos/&lt;id&gt;` | superadmin | Soft-delete |
| 14 | GET | `/api/dispositivos/&lt;id&gt;/test` | admin, superadmin | Ping |
| 15 | POST | `/api/dispositivos/&lt;id&gt;/sync` | admin, superadmin | Lanzar sync |
| 16 | GET | `/api/usuarios-zk` | admin, superadmin | Listar usuarios del biométrico |
| 17 | POST | `/api/usuarios-zk/&lt;id_usuario&gt;/vincular` | admin, superadmin | Vincular con persona |
| 18 | GET | `/api/personas-lista` | admin, superadmin | Selector personas |
| 19 | GET | `/api/sync/estado` | admin, superadmin | Estado por dispositivo |
| 20 | POST | `/api/sincronizar` | admin, superadmin | Sync con rango |
| 21 | GET | `/api/sync-status/&lt;job_id&gt;` | ? | Estado de job |
| 27 | POST | `/api/limpiar-dispositivo` | superadmin, admin | Borrar log dispositivo |

### `schedule_bp` — Horarios personalizados (7 rutas)

| # | Método | Ruta | Decorador RBAC | Descripción corta |
|---|---|---|---|---|
| 31 | POST | `/api/horarios/importar` | sup, admin, gestor | Importar `.csv`/`.obd`/`.ods` |
| 32 | GET | `/api/horarios/estado` | ? | Estado actual |
| 33 | GET | `/api/horarios` | ? | Listar todos |
| 34 | GET | `/api/horarios/exportar` | sup, admin, gestor | Descargar CSV |
| 35 | POST | `/api/horarios` | sup, admin, gestor | Crear |
| 36 | PUT | `/api/horarios/&lt;id_usuario&gt;` | sup, admin, gestor | Actualizar |
| 37 | DELETE | `/api/horarios/&lt;id_usuario&gt;` | sup, admin | Eliminar |

### `attendance_bp` — Justificaciones y feriados (11 rutas)

| # | Método | Ruta | Decorador RBAC | Descripción corta |
|---|---|---|---|---|
| 38 | GET | `/api/justificaciones` | ? | Listar por rango |
| 39 | POST | `/api/justificaciones` | sup, admin, gestor | Crear |
| 40 | PATCH | `/api/justificaciones/&lt;int:jid&gt;` | ? | Cambiar estado |
| 41 | GET | `/api/justificaciones/&lt;int:jid&gt;` | ? | Obtener una |
| 42 | PUT | `/api/justificaciones/&lt;int:jid&gt;` | ? | Actualizar |
| 43 | DELETE | `/api/justificaciones/&lt;int:jid&gt;` | sup, admin | Eliminar |
| 44 | GET | `/api/feriados` | ? | Listar |
| 45 | POST | `/api/feriados` | sup, admin | Crear |
| 46 | DELETE | `/api/feriados/&lt;fecha&gt;` | sup, admin | Eliminar uno |
| 47 | POST | `/api/feriados/importar` | sup, admin | Importar CSV |
| 48 | GET | `/api/feriados/exportar` | ? | Exportar CSV |

### `breaks_bp` — Categorización de breaks (1 ruta)

| # | Método | Ruta | Decorador RBAC | Descripción corta |
|---|---|---|---|---|
| 49 | POST | `/api/categorizar-break` | sup, admin, gestor | Categorizar break |

### `reports_bp` — Generación de reportes y backups (4 rutas)

| # | Método | Ruta | Decorador RBAC | Descripción corta |
|---|---|---|---|---|
| 25 | POST | `/api/generar-desde-db` | sup, admin, gestor | Generar PDF/DOCX |
| 26 | POST | `/api/reportes/enviar-email` | sup, admin, gestor | Enviar por email |
| 28 | GET | `/api/backup/descargar` | sup, admin | **(Fase 2)** Dump `pg_dump -Fc` descargable |
| 29 | GET | `/api/backup/csv` | sup, admin, gestor | CSV completo |

### `periods_bp` — Periodos de prácticas (8 rutas)

| # | Método | Ruta | Decorador RBAC | Descripción corta |
|---|---|---|---|---|
| 22 | GET | `/api/personas-db` | ? | Personas con horario |
| 61 | GET | `/periodos` | admin, sup, gestor | Lista periodos |
| 62 | POST | `/periodos/crear` | admin, sup | Crear periodo |
| 63 | GET | `/periodos/&lt;id&gt;` | admin, sup, gestor | Detalle periodo |
| 64 | POST | `/periodos/&lt;id&gt;/importar-personas` | admin, sup | Importar CSV |
| 65 | POST | `/periodos/&lt;id&gt;/cerrar` | admin, sup | Cerrar periodo |
| 66 | POST | `/periodos/&lt;id&gt;/archivar` | admin, sup | Archivar periodo |
| 67 | POST | `/periodos/&lt;id&gt;/eliminar` | superadmin | Eliminar |

### `people_bp` — Personas (4 rutas)

| # | Método | Ruta | Decorador RBAC | Descripción corta |
|---|---|---|---|---|
| 68 | GET | `/personas` | admin, sup, gestor | Listar con filtros |
| 69 | POST | `/personas/crear` | admin, sup | Crear persona |
| 70 | POST | `/personas/&lt;id&gt;` | admin, sup | Editar persona |
| 71 | GET | `/personas/historico` | admin, sup, gestor | Histórico |

### `groups_bp` — Grupos y categorías (6 rutas)

| # | Método | Ruta | Decorador RBAC | Descripción corta |
|---|---|---|---|---|
| 72 | GET | `/admin/grupos` | admin, sup | Listar grupos |
| 73 | POST | `/admin/grupos` | admin, sup | Crear grupo |
| 74 | POST | `/admin/grupos/&lt;id&gt;` | admin, sup | Editar grupo |
| 75 | GET | `/admin/categorias` | admin, sup | Listar categorías |
| 76 | POST | `/admin/categorias` | admin, sup | Crear categoría |
| 77 | POST | `/admin/categorias/&lt;id&gt;` | admin, sup | Editar categoría |

### `admin_bp` — Administración cross-tenant (11 rutas)

| # | Método | Ruta | Decorador RBAC | Descripción corta |
|---|---|---|---|---|
| 3 | POST | `/admin/switch-tenant` | superadmin | (también en auth_bp) |
| 50 | GET | `/admin/tenants` | superadmin | Lista tenants |
| 51 | POST | `/admin/tenants` | superadmin | Crear tenant |
| 52 | POST | `/admin/tenants/&lt;tenant_id&gt;` | superadmin | Activar/desactivar |
| 53 | GET | `/admin/dispositivos` | sup, admin | UI dispositivos |
| 54 | GET | `/admin/usuarios` | sup, admin | UI usuarios del tenant |
| 55 | POST | `/admin/usuarios` | sup, admin | Crear usuario tenant |
| 56 | POST | `/admin/usuarios/&lt;usuario_id&gt;` | sup, admin | Editar usuario |
| 57 | GET | `/admin/superadmin/usuarios` | superadmin | UI global usuarios |
| 58 | DELETE | `/api/superadmin/usuarios/&lt;usuario_id&gt;` | superadmin | Soft-delete |
| 59 | POST | `/api/superadmin/usuarios` | superadmin | Crear en tenant |
| 60 | POST | `/api/superadmin/usuarios/mover` | superadmin | Mover entre tenants |

> El endpoint `POST /admin/switch-tenant` (fila 3) se lista dos veces: una por `auth_bp` (autentica) y
> otra por `admin_bp` (operación de admin). En el árbol final del refactor, vivirá **una sola vez**
> en `admin_bp` (admin) y `auth_bp` solo conservará `/login` y `/logout`.

### `analytics_bp` — Analytics e IA (5 rutas)

| # | Método | Ruta | Decorador RBAC | Descripción corta |
|---|---|---|---|---|
| 23 | GET | `/api/alertas/tardanzas-severas` | ? | Alertas de tardanzas |
| 78 | GET | `/analytics` | admin, sup, gestor | Vista 30 días |
| 79 | GET | `/analytics/periodo/&lt;periodo_id&gt;` | admin, sup, gestor | Analytics periodo |
| 80 | POST | `/api/analytics/narrativo` | admin, sup, gestor | Narrativo IA |
| 81 | GET | `/api/analytics` | admin, sup, gestor | Hallazgos completos |

### `system_bp` — Ingesta histórica + estado scheduler (2 rutas)

- `POST /api/historicos/importar` — Importa CSV/XLSX histórico.
- `GET /api/scheduler/estado` **(Fase 1)** — Estado del scheduler + últimas 10 corridas.

#### `GET /api/scheduler/estado`

Estado actual del scheduler y últimas 10 corridas registradas en `public.scheduler_runs`.

- **Auth**: rol `superadmin` o `admin`.
- **Response 200**:
  ```json
  {
    "sync_activo": true,
    "sync_hora_nocturna": "02:00",
    "sync_intervalo_horas": 2,
    "proxima_corrida": "2026-07-03T02:00:00-05:00",
    "ultimas_corridas": [
      {
        "id": 42,
        "job": "sync_incremental",
        "tenant_slug": "istpet",
        "inicio": "2026-07-02T10:00:00-05:00",
        "fin": "2026-07-02T10:05:00-05:00",
        "ok": true,
        "descargados": 124,
        "insertados": 98,
        "detalle": null
      }
    ]
  }
  ```
- **Errores**: `401` sin sesión, `403` sin rol suficiente.
- **Uso**: alimenta la card "Sincronización automática" en `/configuracion`.

#### `GET /api/backup/descargar` **(Fase 2)**

Descarga un dump completo de la BD en formato `pg_dump -Fc` (custom comprimido).

- **Auth**: rol `superadmin` o `admin`.
- **Response 200**: archivo binario `application/octet-stream`,
  filename `backup_completo_YYYYMMDD_HHMM.dump`. Registrado en `audit_log` con
  `accion=backup_db_descargar`, `detalle={filename, size_bytes}`.
- **Errores**:
  - `401` sin sesión.
  - `403` sin rol.
  - `500` si `pg_dump` falla (mensaje claro + log).
- **Restauración**: `pg_restore -d <db> backup_completo_*.dump` en cualquier PostgreSQL ≥ 16.
- **Notas**: el archivo se guarda temporalmente en `REPORTS_FOLDER` y el cleanup thread
  (15 min) lo purga automáticamente. Las credenciales de BD se pasan por env (`PGPASSWORD`),
  nunca por argv (no aparecen en `ps aux`).

| # | Método | Ruta | Decorador RBAC | Descripción corta |
|---|---|---|---|---|
| 30 | POST | `/api/historicos/importar` | sup, admin | Importar `.csv`/`.xlsx` |

---

## Headers de seguridad (post-procesamiento)

Aplicados a **todas** las respuestas en `app.py:2486-2499`:

| Header | Valor |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `SAMEORIGIN` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; …` (CSP con whitelist de CDN de Bootstrap, Google Fonts y jsDelivr) |

---

## Backlog

### P2 (importante, no urgente)

- **Versionado explícito**: hoy no existe `/api/v1/*`, `/api/v2/*`. Cuando un cambio sea incompatible,
  mover el contrato viejo a `/api/v1/` y exponer el nuevo en `/api/v2/`. Estrategia concreta:
  1. Definir `API_VERSION = "v1"` en `app/config.py`.
  2. Montar ambos prefijos desde `create_app()`.
  3. Marcar `/api/*` como deprecated y agregar header `Sunset:`.
- **OpenAPI / Swagger**: generar spec automáticamente desde decoradores. Opciones:
  - `flask-pydantic` (schemas tipados en handlers).
  - `apispec` + `apispec-webframeworks` + `marshmallow`.
  - `flask-smorest` (combina Marshmallow + OpenAPI + Swagger UI).
- **Paginación**: los endpoints que listas grandes (`/api/justificaciones`, `/api/horarios`) no paginan.
  Estandarizar `?limit=&offset=` y devolver `{"total": N, "items": [...]}`.

### P3 (futuro)

- **JSON Merge Patch (RFC 7396)** para `PUT /api/justificaciones/<jid>` en lugar de reemplazo total.
- **Filtros declarativos** vía query string estilo `?filter[estado]=aprobada`.
- **Idempotency-Key header** para POST destructivos.
- **Webhooks salientes** para eventos clave (sync finalizado, alerta de dispositivo caído).

---

## Relacionado

- [[ARQUITECTURA]] — Mapa de Blueprints y árbol de carpetas destino.
- [[AUTENTICACION]] — Detalle del sistema de auth, decoradores RBAC y CSRF (cómo se relacionan con esta API).
- [[ER]] — Modelo de datos: cada recurso de esta API corresponde a una tabla o conjunto de tablas.
- [[ADR-0001-modularizacion-monolito-flask]] — El refactor que moverá estas 81 rutas a 13 Blueprints.
