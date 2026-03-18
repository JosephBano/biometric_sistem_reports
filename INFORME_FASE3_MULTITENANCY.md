# Informe de Implementación — Fase 3: Multitenancy
**Versión:** 1.0
**Fecha:** 2026-03-17
**Estado:** Completada y validada

---

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Qué cambió respecto a Fase 2](#2-qué-cambió-respecto-a-fase-2)
3. [Arquitectura implementada](#3-arquitectura-implementada)
4. [Componentes implementados](#4-componentes-implementados)
5. [Cómo usar el sistema multitenant](#5-cómo-usar-el-sistema-multitenant)
6. [Referencia de rutas API](#6-referencia-de-rutas-api)
7. [Referencia de decoradores](#7-referencia-de-decoradores)
8. [Referencia de funciones de base de datos](#8-referencia-de-funciones-de-base-de-datos)
9. [Migraciones Alembic multi-tenant](#9-migraciones-alembic-multi-tenant)
10. [Operaciones de administración](#10-operaciones-de-administración)
11. [Consideraciones de seguridad](#11-consideraciones-de-seguridad)
12. [Archivos modificados y creados](#12-archivos-modificados-y-creados)

---

## 1. Resumen ejecutivo

La Fase 3 convierte el sistema de gestión biométrica de RRHH en una plataforma **multi-institución**. Cada institución (tenant) opera en completo aislamiento: su propio schema PostgreSQL, sus propios usuarios, sus propios dispositivos ZK y sus propias configuraciones.

El concepto central de la Fase 3 es que **las capacidades del tenant emergen de su configuración**, no de flags booleanos. Si una institución tiene configurado el tipo de persona `"Practicante"`, verá la sección de períodos de prácticas. Si no lo tiene, esa sección simplemente no existe.

**Resultado:** El sistema puede servir a N instituciones desde una única instalación Docker, con aislamiento estricto de datos entre ellas.

---

## 2. Qué cambió respecto a Fase 2

### 2.1 Lo que desaparece

| Concepto Fase 1/2 | Reemplazado por |
|---|---|
| `modulo_rrhh = true/false` en tenants | Tenant con tipo `"Empleado"` configurado |
| `modulo_alumnos = true/false` | Tenant con tipo `"Practicante"` configurado |
| Un único tenant (`istpet`) hardcodeado | N tenants registrados en `public.tenants` |
| Sin panel de gestión de instituciones | Panel `/admin/tenants` (solo superadmin) |
| Sin provisioning automático | `provisionar_schema()` crea schema + datos iniciales |

No existe ninguna referencia a `modulo_rrhh` o `modulo_alumnos` en el código.

### 2.2 Lo que no cambia

- Schema-por-tenant en PostgreSQL (establecido en Fase 1)
- Sistema de roles (`superadmin`, `admin`, `gestor`, etc.) de Fase 2
- `@require_role(...)` en todas las rutas sensibles
- Mecanismo de login con bcrypt + audit log
- Conector ZK, generación de PDF, análisis de asistencia

---

## 3. Arquitectura implementada

### 3.1 Separación de schemas

```
PostgreSQL
│
├── public (schema global)
│   ├── tenants          — Registro de instituciones
│   ├── usuarios         — Usuarios de todas las instituciones
│   ├── audit_log        — Log global de acciones
│   └── login_intentos   — Rate limiting por IP
│
├── istpet (schema institución ISTPET)
│   ├── sedes, dispositivos, sync_log, feriados
│   ├── tipos_persona, grupos, categorias
│   ├── personas, personas_dispositivos
│   ├── config_ciclo_horario, plantillas_horario, asignaciones_horario
│   └── asistencias, justificaciones, breaks_categorizados
│
└── {otro_slug} (schema de otra institución)
    └── ... (misma estructura, datos completamente separados)
```

### 3.2 Regla de aislamiento estricto

Ninguna query de negocio cruza schemas de tenant. Solo acceden a `public.*`:
- El proceso de login
- El middleware `before_request` (validación de tenant)
- El panel del superadmin
- El audit log global

### 3.3 Flujo de una petición autenticada

```
Request HTTP
    │
    ▼
before_request (autenticar_request)
    ├── ¿Endpoint público (login/static)? → pasar
    ├── ¿Sin sesión? → 401/redirect login
    ├── ¿POST sin CSRF? → 403
    ├── Cargar g.usuario_id, g.tenant_schema, g.roles
    ├── Validar que tenant existe en public.tenants
    ├── Validar que tenant.activo = true
    ├── Asignar g.tenant (objeto completo del tenant)
    └── Cargar g.tenant_tipos (tipos de persona activos)
         │
         ▼
    Vista/Ruta
    ├── @require_role(...) → verifica g.roles
    ├── @require_tipo_persona(...) → verifica g.tenant_tipos
    └── lógica de negocio con get_connection(g.tenant_schema)
```

---

## 4. Componentes implementados

### 4.1 Middleware de tenant (`app.py:145-197`)

El hook `@app.before_request` carga el contexto del tenant en cada petición:

```python
# Resultado en g (Flask context) después de cada request:
g.usuario_id    = "uuid del usuario"
g.tenant_schema = "istpet"           # slug del schema PostgreSQL
g.roles         = ["admin"]
g.nombre        = "Juan Pérez"
g.tenant_id     = "uuid del tenant"
g.tenant        = {                  # objeto completo del tenant
    "id": "...",
    "nombre": "ISTPET",
    "nombre_corto": "ISTPET",
    "slug": "istpet",
    "zona_horaria": "America/Guayaquil",
    "activo": True,
    "creado_en": datetime(...)
}
g.tenant_tipos  = [                  # tipos de persona activos
    {"id": "...", "nombre": "Empleado",     "descripcion": "", "activo": True},
    {"id": "...", "nombre": "Practicante",  "descripcion": "", "activo": True},
]
```

**Comportamiento cuando el tenant está inactivo:**
- Limpia la sesión automáticamente
- HTML: renderiza `login.html` con mensaje "Acceso suspendido. Contacte a soporte."
- API JSON: retorna `{"error": "Cuenta de institución suspendida"}` con HTTP 403

### 4.2 Helper `tenant_tiene_tipo()` (`app.py:201-204`)

Función disponible tanto en Python como en templates Jinja2:

```python
# En Python (vistas, helpers):
if tenant_tiene_tipo("Practicante"):
    mostrar_seccion_periodos()

# En templates Jinja2 (inyectado via context_processor):
{% if tenant_tiene_tipo('Practicante') %}
  <a href="/periodos">Períodos de Prácticas</a>
{% endif %}
```

La comparación es **case-insensitive**: `"practicante"`, `"Practicante"` y `"PRACTICANTE"` son equivalentes.

### 4.3 Context processor (`app.py:207-216`)

Inyecta automáticamente en todos los templates:

| Variable | Tipo | Descripción |
|---|---|---|
| `current_user_nombre` | `str` | Nombre del usuario logueado |
| `current_user_roles` | `list` | Lista de roles del usuario |
| `tenant` | `dict\|None` | Objeto completo del tenant activo |
| `tenant_tipos` | `list` | Tipos de persona configurados |
| `tenant_tiene_tipo` | `function` | Helper para verificar capacidades |

### 4.4 Decorador `@require_tipo_persona` (`decorators.py:78-114`)

Protege rutas que requieren un tipo de persona específico:

```python
@app.route('/periodos/nuevo')
@require_role('gestor', 'admin', 'superadmin')
@require_tipo_persona('Practicante')          # ← Fase 3
def nuevo_periodo():
    ...
```

- Si el tenant NO tiene el tipo configurado → HTTP 403
- Funciona correctamente tanto para rutas HTML como API JSON
- Se combina con `@require_role` (primero verificar rol, luego tipo)

### 4.5 Provisioning de tenants (`db/tenant_provisioner.py`)

La función `provisionar_schema(slug, tipos_persona)` ejecuta en secuencia:

```
1. Validar slug (solo [a-z0-9_], previene SQL injection)
2. CREATE SCHEMA {slug} + DDL completo (todas las tablas)
3. INSERT sede "Sede Principal" por defecto
4. INSERT tipos_persona (los que se pasan como parámetro)
5. INSERT feriados nacionales de Ecuador (2025-2026)
6. Sincronizar tabla alembic_version al head actual
```

**Rollback automático si falla cualquier paso:**
```
si falla paso 3, 4, 5 o 6:
    DROP SCHEMA {slug} CASCADE
    DELETE FROM public.tenants WHERE slug = {slug}
    raise la excepción original
```

**Feriados nacionales cargados automáticamente:**
```
01-enero    Año Nuevo
Viernes Santo (variable)
Sábado Santo (variable)
01-mayo     Día del Trabajo
24-mayo     Batalla de Pichincha
10-agosto   Primer Grito de Independencia
09-octubre  Independencia de Guayaquil
02-noviembre Día de los Difuntos
03-noviembre Independencia de Cuenca
25-diciembre Navidad
```

---

## 5. Cómo usar el sistema multitenant

### 5.1 Crear una nueva institución

**Desde la UI (recomendado):**

1. Iniciar sesión como `superadmin`
2. Ir a **`/admin/tenants`**
3. Hacer clic en **"Nueva Institución"**
4. Completar el formulario:
   - **Nombre completo:** nombre oficial de la institución
   - **Nombre corto:** abreviatura (ej: ISTPET)
   - **Slug:** identificador técnico, solo minúsculas y guiones bajos (ej: `istpet_quito`)
   - **Zona horaria:** `America/Guayaquil` para Ecuador
5. El sistema crea automáticamente:
   - Schema PostgreSQL con todas las tablas
   - Tipos de persona: `Empleado` y `Practicante`
   - Feriados nacionales de Ecuador
   - Sede principal por defecto

**Desde Python (para scripts de seed):**
```python
import db as db_module

# 1. Registrar en public.tenants
tenant = db_module.crear_tenant(
    nombre="Instituto Ejemplo",
    nombre_corto="IEJE",
    slug="instituto_ejemplo",
    zona_horaria="America/Guayaquil"
)

# 2. Provisionar schema completo
db_module.provisionar_schema(
    slug="instituto_ejemplo",
    tipos_persona=["Empleado", "Contratista"]
)
```

### 5.2 Activar / desactivar una institución

**Desde la UI:**
1. Ir a `/admin/tenants`
2. En la fila del tenant, hacer clic en **"Desactivar"** / **"Activar"**

**Efecto inmediato:** todos los usuarios de esa institución son bloqueados en su próximo request. Sus datos NO se eliminan.

**Desde Python:**
```python
db_module.actualizar_tenant(tenant_id, {"activo": False})
```

### 5.3 Impersonar un tenant (superadmin)

El superadmin puede operar dentro del contexto de cualquier tenant:

```http
POST /admin/switch-tenant
Content-Type: application/x-www-form-urlencoded

tenant_slug=istpet
```

Después de esto, el superadmin ve la UI exactamente como la vería un admin de esa institución. Para volver al contexto global:

```http
POST /admin/switch-tenant
tenant_slug=public
```

### 5.4 Verificar tipos de persona desde código

```python
# En una vista Flask:
from flask import g

if tenant_tiene_tipo("Practicante"):
    periodos = db_module.listar_periodos()
```

```html
<!-- En un template Jinja2: -->
{% if tenant_tiene_tipo('Empleado') %}
  <section id="asistencia-empleados">...</section>
{% endif %}

{% if tenant_tiene_tipo('Practicante') %}
  <section id="periodos-practicas">...</section>
{% endif %}
```

### 5.5 Agregar un tipo de persona a un tenant existente

```python
db_module.insertar_tipo_persona(
    schema="istpet",
    nombre="Contratista",
    descripcion="Personal contratado por servicios"
)
```

Inmediatamente después, `tenant_tiene_tipo("Contratista")` retorna `True` para las sesiones activas del tenant `istpet` (en el próximo request, porque `g.tenant_tipos` se recarga en cada petición).

---

## 6. Referencia de rutas API

### Gestión de tenants (solo `superadmin`)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/admin/tenants` | Lista todas las instituciones |
| `POST` | `/admin/tenants` | Crea institución + provisiona schema |
| `POST` | `/admin/tenants/<tenant_id>` | Activa o desactiva una institución |
| `POST` | `/admin/switch-tenant` | Impersona un tenant (cambia contexto de sesión) |

### Parámetros de `POST /admin/tenants`

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `nombre` | string | Sí | Nombre completo |
| `nombre_corto` | string | No | Abreviatura |
| `slug` | string | Sí | Identificador único, patrón `[a-z][a-z0-9_]{2,29}` |
| `zona_horaria` | string | No | Default: `America/Guayaquil` |

### Respuestas

**Éxito en creación:**
```
HTTP 302 → /admin/tenants?msg=Tenant+creado+con+éxito
```

**Error de validación:**
```
HTTP 400 — "Nombre y Slug son requeridos"
HTTP 400 — "Slug debe contener solo letras, números y guiones bajos"
```

**Error de provisioning:**
```
HTTP 500 — "Error al crear tenant: <detalle>"
(el rollback se ejecuta automáticamente)
```

---

## 7. Referencia de decoradores

### `@require_role(*roles)`

```python
from decorators import require_role

@app.route('/admin/reportes')
@require_role('admin', 'superadmin')        # requiere UNO de estos roles
def admin_reportes():
    ...
```

**Roles disponibles:** `superadmin`, `admin`, `gestor`, `supervisor_grupo`, `supervisor_periodo`, `readonly`

**Respuesta si falla:**
- HTML: `403 — Acceso denegado`
- API: `{"error": "Acceso denegado. Rol insuficiente.", "roles_requeridos": [...]}`

---

### `@require_tipo_persona(nombre)`

```python
from decorators import require_tipo_persona

@app.route('/periodos')
@require_role('gestor', 'admin')
@require_tipo_persona('Practicante')        # requiere este tipo en el tenant
def periodos():
    ...
```

**Respuesta si el tenant no tiene el tipo:**
- HTML: `403 — Funcionalidad no disponible para tu institución`
- API: `{"error": "Esta funcionalidad no está disponible para tu institución."}`

**Orden correcto:** siempre `@require_role` antes de `@require_tipo_persona`. El rol se verifica primero.

---

## 8. Referencia de funciones de base de datos

Todas accesibles vía `import db as db_module` o `from db import *`.

### Gestión de tenants

```python
# Buscar tenant por slug
tenant = db_module.get_tenant_by_slug("istpet")
# → {"id": "...", "nombre": "ISTPET", "slug": "istpet", "activo": True, ...}
# → None si no existe

# Listar todos los tenants
tenants = db_module.listar_tenants()
# → [{"id": ..., "nombre": ..., "slug": ..., "activo": ...}, ...]

# Crear registro de tenant
tenant = db_module.crear_tenant(
    nombre="Nombre Completo",
    nombre_corto="NC",
    slug="nombre_corto",
    zona_horaria="America/Guayaquil"
)

# Actualizar tenant
db_module.actualizar_tenant(tenant_id, {"activo": False})
db_module.actualizar_tenant(tenant_id, {"nombre": "Nuevo Nombre"})

# Provisionar schema completo
db_module.provisionar_schema("nuevo_slug", tipos_persona=["Empleado"])
```

### Tipos de persona

```python
# Obtener tipos activos de un tenant
tipos = db_module.get_tipos_persona("istpet")
# → [{"id": "...", "nombre": "Empleado", "descripcion": "", "activo": True}, ...]

# Insertar nuevo tipo
db_module.insertar_tipo_persona("istpet", "Contratista", "Personal por servicios")
```

### Conexiones por tenant

```python
from db.connection import get_connection

# Conexión con search_path automático al schema del tenant
with get_connection("istpet") as conn:
    rows = conn.execute(text("SELECT * FROM asistencias LIMIT 10")).fetchall()
    # auto-commit al salir; rollback si hay excepción
```

---

## 9. Migraciones Alembic multi-tenant

### Comportamiento de `alembic upgrade head`

Desde Fase 3, `alembic upgrade head` aplica las migraciones en **dos pasadas**:

```
Pasada 1: schema public
    → Aplica a public.tenants, public.usuarios, etc.
    → alembic_version guardada en public

Pasada 2: para cada tenant activo en public.tenants
    → SET search_path TO {slug}, public
    → Aplica el mismo script de migración al schema del tenant
    → alembic_version guardada en {slug}.alembic_version
```

**Resultado:** una sola ejecución de `alembic upgrade head` migra todos los tenants activos.

### Convención de nombres de migraciones

```
db/migrations/versions/
├── 0001_initial_schema.py      ← Fase 1: schema completo (DDL base)
├── 0002_auth_indices.py        ← Fase 2: JSONB en usuarios + índices
└── 0003_multitenancy_ajustes.py← Fase 3: placeholder (sin cambios DDL)
```

La migración `0003` está vacía intencionalmente — los cambios de Fase 3 son de comportamiento de la aplicación, no de schema.

### Agregar una migración nueva

```bash
# Crear el archivo de migración
alembic revision -m "descripcion_del_cambio"
# → crea db/migrations/versions/0004_descripcion.py

# Editar la migración para agregar los cambios DDL
# ...

# Aplicar a todos los tenants activos
alembic upgrade head
```

### Rollback de una migración

```bash
alembic downgrade -1     # retrocede un step en todos los tenants
alembic downgrade 0002   # retrocede hasta la revisión 0002
```

---

## 10. Operaciones de administración

### Ver el estado de todos los tenants

```sql
SELECT slug, nombre, activo, creado_en
FROM public.tenants
ORDER BY nombre;
```

### Verificar que un tenant tiene sus tablas

```sql
-- Listar schemas existentes
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name NOT IN ('public', 'information_schema', 'pg_catalog')
ORDER BY schema_name;

-- Verificar tablas de un tenant específico
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'istpet'
ORDER BY table_name;
```

### Verificar tipos de persona de un tenant

```sql
SET search_path TO istpet;
SELECT nombre, descripcion, activo FROM tipos_persona ORDER BY nombre;
```

### Verificar feriados cargados en un tenant

```sql
SET search_path TO istpet;
SELECT fecha, descripcion, tipo FROM feriados ORDER BY fecha;
```

### Verificar versión de Alembic por tenant

```sql
-- Schema público
SELECT version_num FROM public.alembic_version;

-- Schema de tenant
SELECT version_num FROM istpet.alembic_version;
```

### Desactivar un tenant manualmente (emergencia)

```sql
UPDATE public.tenants SET activo = false WHERE slug = 'nombre_del_tenant';
-- Efecto inmediato en el próximo request de cualquier usuario de ese tenant
```

---

## 11. Consideraciones de seguridad

### Prevención de SQL injection en slugs

Todos los puntos donde se usa el slug como nombre de schema aplican la misma validación:

```python
if not all(c.isalnum() or c == "_" for c in slug):
    raise ValueError(f"Schema name inválido: {schema!r}")
```

Esto ocurre en:
- `provisionar_schema()` antes de crear el schema
- `get_connection()` antes de ejecutar `SET search_path`
- `env.py` de Alembic antes de iterar tenants
- La ruta `POST /admin/tenants` antes de llamar a provisioning

### Aislamiento de sesiones

Cada sesión de usuario tiene `tenant_schema` grabado. El middleware valida en **cada request** que:
1. El tenant existe en `public.tenants`
2. El tenant tiene `activo = true`

Si cualquiera de las dos condiciones falla, la sesión se destruye inmediatamente.

### Superadmin y switch-tenant

La impersonación via `/admin/switch-tenant` solo cambia `session["tenant_schema"]`. No se crea ningún usuario nuevo ni se escalan privilegios fuera del rol `superadmin`.

---

## 12. Archivos modificados y creados

### Archivos nuevos (Fase 3)

| Archivo | Descripción |
|---|---|
| `db/tenant_provisioner.py` | Lógica de creación de schema + datos iniciales + rollback |
| `db/queries/tenants.py` | CRUD de `public.tenants` y `tipos_persona` |
| `db/migrations/versions/0003_multitenancy_ajustes.py` | Migración placeholder para Fase 3 |
| `templates/admin/tenants.html` | UI de gestión de instituciones (superadmin) |

### Archivos modificados (Fase 3)

| Archivo | Qué se agregó |
|---|---|
| `app.py` | Middleware de validación de tenant activo + carga de `g.tenant_tipos` + `tenant_tiene_tipo()` + context processor + rutas `/admin/tenants` + `/admin/switch-tenant` |
| `decorators.py` | Decorador `@require_tipo_persona(nombre)` |
| `db/__init__.py` | Exports de `provisionar_schema`, `listar_tenants`, `crear_tenant`, `actualizar_tenant`, `insertar_tipo_persona`, `eliminar_tenant_de_public` |
| `db/migrations/env.py` | Lógica multi-schema: itera `public.tenants` y aplica migraciones a cada tenant |

### Archivos sin cambios en Fase 3

`script.py`, `sync.py`, `horarios.py`, `auth.py`, `db/connection.py`, `db/schema.py`, `db/queries/auth.py`, `db/queries/asistencias.py`, `templates/index.html`, `docker-compose.yml`

---

*Siguiente fase: Fase 4 — Períodos y Personas (gestión de personas, vigencias, grupos)*
