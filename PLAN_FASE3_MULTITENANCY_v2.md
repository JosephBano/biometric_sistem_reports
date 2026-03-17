# Plan de Implementación — Fase 3: Multitenancy
**Versión:** 2.0 — Sin módulos, configuración por tipos de persona
**Fecha:** 2026-03-17
**Prerequisito:** Fases 1 y 2 v2 completadas y verificadas

---

## Índice

1. [Contexto y cambios respecto a v1](#1-contexto-y-cambios-respecto-a-v1)
2. [Alcance](#2-alcance)
3. [Arquitectura de schemas](#3-arquitectura-de-schemas)
4. [Middleware de tenant refinado](#4-middleware-de-tenant-refinado)
5. [Provisioning de nuevos tenants](#5-provisioning-de-nuevos-tenants)
6. [Capacidades del tenant según tipos configurados](#6-capacidades-del-tenant-según-tipos-configurados)
7. [Feriados: nacionales vs institucionales](#7-feriados-nacionales-vs-institucionales)
8. [Migraciones Alembic multi-tenant](#8-migraciones-alembic-multi-tenant)
9. [Pasos de implementación](#9-pasos-de-implementación)
10. [Criterio de finalización](#10-criterio-de-finalización)

---

## 1. Contexto y cambios respecto a v1

### 1.1 El cambio conceptual central

La v1 giraba en torno a `modulo_rrhh` y `modulo_alumnos` como flags booleanos en `tenants`. El provisioning, la UI, el middleware y los decoradores asumían que el sistema tiene exactamente dos módulos.

En v2 esto desaparece completamente:

| Concepto v1 | Concepto v2 |
|---|---|
| `modulo_rrhh = true/false` | El tenant tiene configurado el tipo `"Empleado"` |
| `modulo_alumnos = true/false` | El tenant tiene configurado el tipo `"Practicante"` |
| `@require_module('rrhh')` | `@require_tipo_persona('Empleado')` |
| "App mínima para tenants sin módulos" | Vista básica de presencia para tenants sin tipos configurados |
| Formulario de provisioning con checkboxes de módulos | Formulario de provisioning que pregunta qué tipos de persona tendrá |

Las capacidades del tenant son una consecuencia de su configuración, no un flag binario.

### 1.2 Lo que no cambia

- Schema-por-tenant en PostgreSQL
- Regla de aislamiento estricto entre schemas
- Mecanismo de impersonación para superadmin
- Gestión de feriados
- `alembic upgrade head` multi-schema

---

## 2. Alcance

**Qué incluye:**
- Panel de gestión de tenants (solo `superadmin`)
- Provisioning: crear schema + migraciones + tipos de persona iniciales + feriados
- Middleware de tenant: cargar `g.tenant_tipos` con los tipos configurados
- Adaptación de la UI según tipos de persona disponibles en el tenant
- Decorador `@require_tipo_persona` aplicado a rutas relevantes
- Gestión de feriados desde la UI (admin del tenant)
- Migraciones Alembic en entorno multi-tenant

**Qué NO incluye:**
- Drivers para otras marcas de dispositivos (Fase 6)
- La otra institución vía Tailscale (Fase 6)

---

## 3. Arquitectura de schemas

### 3.1 Separación de responsabilidades (sin cambios en estructura)

```
public schema:
├── tenants          → Registro de instituciones (sin flags de módulos)
├── usuarios         → Usuarios de la app con roles y scopes
├── audit_log        → Log global
└── login_intentos   → Rate limiting

{tenant_slug} schema:
├── Infraestructura  → sedes, dispositivos, sync_log, feriados
├── Configuración    → tipos_persona, grupos, categorias
├── Personas         → personas, personas_dispositivos, usuarios_zk
├── Vigencia         → periodos_vigencia
├── Horarios         → config_ciclo_horario, plantillas_horario,
│                      asignaciones_horario
└── Asistencia       → asistencias, justificaciones, breaks_categorizados
```

### 3.2 Todas las tablas existen en todos los tenants

Alembic aplica el mismo schema completo a todos los tenants. Un tenant sin `tipos_persona` configurados tiene todas las tablas vacías. Esto simplifica las migraciones: no hay schemas de segunda clase.

### 3.3 Regla de aislamiento estricto

Ninguna query de negocio cruza schemas de tenant. Solo pueden tocar `public.*`:
- El login
- El middleware de tenant
- El audit log
- El panel de superadmin

---

## 4. Middleware de tenant refinado

### 4.1 `before_request` versión Fase 3

```
before_request:
  1. Si endpoint en excepciones (login, static): skip
  2. Leer session['usuario_id'] → No existe: redirect login
  3. Leer session['tenant_schema'] → Asignar a g.tenant_schema
  4. Si g.tenant_schema != 'public':
     a. Cargar tenant desde public.tenants WHERE slug = g.tenant_schema
     b. Si no existe o activo=false: cerrar sesión, redirect con mensaje
     c. Asignar g.tenant = objeto tenant completo
     d. Cargar g.tenant_tipos = lista de tipos_persona del tenant
        (desde {tenant_schema}.tipos_persona WHERE activo=true)
  5. Asignar g.roles desde session['roles']
  6. Configurar search_path para el tenant
```

### 4.2 `g.tenant_tipos` — el reemplazo de `g.tenant.modulo_*`

```python
# Antes (v1):
if g.tenant.modulo_alumnos:
    mostrar_seccion_practicas()

# Ahora (v2):
if any(t['nombre'] == 'Practicante' for t in g.tenant_tipos):
    mostrar_seccion_periodos()
```

Este patrón se encapsula en un helper:

```python
def tenant_tiene_tipo(nombre: str) -> bool:
    """Verifica si el tenant activo tiene configurado un tipo de persona."""
    return any(
        t['nombre'].lower() == nombre.lower()
        for t in g.get('tenant_tipos', [])
    )
```

### 4.3 Context processor para templates Jinja2

```python
@app.context_processor
def inject_tenant_context():
    return dict(
        tenant=g.get('tenant'),
        tenant_tipos=g.get('tenant_tipos', []),
        tenant_tiene_tipo=tenant_tiene_tipo,  # función disponible en templates
    )
```

Uso en templates:
```html
{% if tenant_tiene_tipo('Practicante') %}
  <a href="/periodos">Períodos de Prácticas</a>
{% endif %}
```

### 4.4 Impersonación de tenant para superadmin

```
POST /admin/switch-tenant
Body: { "tenant_slug": "istpet" }
→ Actualiza session['tenant_schema'] = 'istpet'
→ Recarga g.tenant_tipos del nuevo tenant
→ Redirect al dashboard
→ Banner en UI: "Operando como: ISTPET [salir]"
```

---

## 5. Provisioning de nuevos tenants

### 5.1 Flujo de creación

```
1. Superadmin completa el formulario:
   - Nombre completo
   - Nombre corto
   - Slug (validado: [a-z][a-z0-9_]{2,29})
   - Zona horaria
   - Tipos de persona iniciales (inputs de texto dinámicos, mínimo 1)
     Ejemplos: "Empleado", "Practicante", "Contratista"
   - Email del primer admin

2. Sistema ejecuta el provisioning:
   a. Insertar en public.tenants
   b. CREATE SCHEMA {slug}
   c. alembic upgrade head para el nuevo schema
   d. Insertar tipos_persona configurados en {slug}.tipos_persona
   e. Cargar feriados nacionales de Ecuador en {slug}.feriados
   f. Crear usuario admin en public.usuarios
      (contraseña temporal, email si SMTP configurado)

3. Retornar confirmación con credenciales del admin
```

### 5.2 Validaciones antes del provisioning

- `slug` debe coincidir con `^[a-z][a-z0-9_]{2,29}$`
- `slug` no puede ser nombre reservado: `public`, `pg_catalog`, `information_schema`, ni schemas del sistema
- `slug` no puede duplicar un tenant existente
- Al menos un tipo de persona debe configurarse
- Email del admin debe ser único en `public.usuarios`

### 5.3 Rollback de provisioning fallido

Si el provisioning falla a mitad:
1. `DROP SCHEMA {slug} CASCADE`
2. Eliminar registro de `public.tenants` si se creó
3. Eliminar usuario admin si se creó
4. Retornar error detallado

`CREATE SCHEMA` no es transaccional en PostgreSQL — el rollback del schema se maneja explícitamente.

### 5.4 Desactivar un tenant

`PUT /admin/tenants/<id>` con `{ "activo": false }`:
- Schema con datos intactos
- Usuarios del tenant no pueden hacer login
- Reactivable en cualquier momento
- No existe flujo de eliminación permanente en la UI

---

## 6. Capacidades del tenant según tipos configurados

### 6.1 Concepto de "capacidad"

Una capacidad es una funcionalidad que solo tiene sentido si el tenant tiene ciertos tipos de persona configurados. Las capacidades no son flags; emergen de la configuración.

| Capacidad | Condición |
|---|---|
| Generación de reportes de asistencia detallados | Al menos un tipo de persona activo |
| Gestión de justificaciones y breaks | Al menos un tipo de persona activo |
| Períodos de vigencia con fecha fin | Cualquier tipo de persona |
| Vista de períodos cerrados/archivados | Al menos un período cerrado |
| Alertas de riesgo por período | Al menos un período activo con fecha fin próxima |

### 6.2 Tenant sin tipos configurados ("app mínima")

Un tenant que acaba de ser provisionado sin tipos de persona configurados (o uno que solo quiere sync básica) tiene acceso a:

- Dashboard de presencia cruda: tabla con `id_usuario`, `nombre`, `fecha_hora`, filtrable por rango de fechas
- Exportación CSV de registros crudos
- Sync de dispositivos

Esto es equivalente a la "app mínima" de la v1, pero sin necesidad de un flag especial. Simplemente es lo que ve un tenant vacío.

### 6.3 Configuración de tipos de persona desde la UI

El `admin` puede:
- Ver los tipos de persona configurados
- Agregar nuevos tipos
- Desactivar tipos (no borrar — hay personas asociadas)
- Editar nombre, descripción, color, icono

Ruta: `GET/POST /admin/configuracion/tipos-persona`

---

## 7. Feriados: nacionales vs institucionales

### 7.1 Carga automática al provisionar

Al crear un tenant, se cargan automáticamente los feriados nacionales de Ecuador:

```
1 enero — Año Nuevo
Viernes Santo (variable)
Sábado Santo (variable)
1 mayo — Día del Trabajo
24 mayo — Batalla de Pichincha
10 agosto — Primer Grito de Independencia
9 octubre — Independencia de Guayaquil
2 noviembre — Día de los Difuntos
3 noviembre — Independencia de Cuenca
25 diciembre — Navidad
```

Los feriados de traslado se cargan manualmente ya que dependen del decreto ejecutivo de cada año.

### 7.2 Gestión desde la UI

Usuarios con rol `admin` pueden:
- Ver todos los feriados (nacionales e institucionales)
- Agregar feriados institucionales
- Editar descripción de cualquier feriado
- Eliminar solo feriados institucionales (nunca los nacionales)

`script.py` no distingue entre tipos — cualquier fecha en `feriados` se trata como no hábil.

---

## 8. Migraciones Alembic multi-tenant

### 8.1 El problema

Por defecto Alembic opera sobre un único schema. Cuando se agrega una migración nueva, debe aplicarse a todos los schemas de tenants activos.

### 8.2 Solución: `env.py` multi-schema

`db/migrations/env.py` itera sobre todos los tenants activos y aplica cada migración en su schema:

```python
# En env.py
def run_migrations_online():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        tenants = conn.execute(
            text("SELECT slug FROM public.tenants WHERE activo = true")
        ).fetchall()
        for tenant in tenants:
            conn.execute(text(f"SET search_path TO {tenant.slug}, public"))
            context.configure(connection=conn, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
```

`alembic upgrade head` es idempotente y multi-tenant automáticamente.

### 8.3 Provisioning de nuevo tenant

Al crear un tenant, se usa un runner específico que aplica solo el schema de ese tenant:

```python
# db/migrations/runner.py
def migrate_tenant(slug: str):
    """Aplica todas las migraciones al schema de un tenant específico."""
    ...
```

### 8.4 Convención de nombres de migraciones

```
0001_initial_schema.py              ← Fase 1: schema completo
0002_auth_indices.py                ← Fase 2: índices de auth
0003_multitenancy_ajustes.py        ← Fase 3: ajustes menores si necesario
0004_...                            ← Fases posteriores
```

---

## 9. Pasos de implementación

### Paso 1 — Migración Alembic `0003` y `env.py` multi-schema

- Crear `0003_multitenancy_ajustes.py` (puede ser vacía si no hay cambios de schema)
- Configurar `env.py` para iterar sobre todos los tenants activos

**Verificación:**
- `alembic upgrade head` aplica en `istpet`
- Crear schema de prueba `test_tenant` manualmente → `alembic upgrade head` aplica en ambos

---

### Paso 2 — Implementar `db/queries/tenants.py`

- `get_tenant_by_slug(slug)` → dict | None
- `listar_tenants()` → list
- `crear_tenant(datos)` → dict
- `actualizar_tenant(id, datos)` → dict
- `provisionar_schema(slug, tipos_persona)` → crea schema y corre migraciones
- `get_tipos_persona_del_tenant()` → list (para cargar `g.tenant_tipos`)

**Verificación:**
- `get_tenant_by_slug('istpet')` retorna el registro correcto
- `provisionar_schema('test_tenant', ['Empleado'])` crea el schema con todas las tablas y el tipo configurado

---

### Paso 3 — Refinar middleware de tenant

- Agregar carga de `g.tenant_tipos` desde `tipos_persona`
- Agregar validación de `tenant.activo`
- Agregar `tenant_tiene_tipo()` helper y context_processor

**Verificación:**
- `g.tenant_tipos` contiene los tipos del tenant en cada request
- `tenant_tiene_tipo('Practicante')` retorna `True` para ISTPET
- Desactivar `istpet` en BD → login falla con mensaje apropiado

---

### Paso 4 — Adaptar `@require_tipo_persona` en rutas

- Aplicar el decorador en rutas que requieren tipos específicos
- Adaptar `index.html` para ocultar secciones según tipos disponibles
- Adaptar la barra de navegación

**Verificación:**
- Tenant sin tipo `Practicante` → sección Períodos no aparece en navegación
- ISTPET con ambos tipos → navegación completa visible

---

### Paso 5 — Panel de gestión de tenants

- Plantilla `admin/tenants.html`
- Rutas `GET/POST /admin/tenants`
- Formulario de creación con campos de tipos de persona dinámicos
- Estado de cada tenant: activo/inactivo, tipos configurados, último acceso de sus usuarios

**Verificación:**
- Superadmin crea `test_tenant` con tipo "Empleado" desde la UI
- Schema `test_tenant` existe en PostgreSQL con `tipos_persona` cargado
- Admin del nuevo tenant puede hacer login y ve la UI correspondiente

---

### Paso 6 — Vista de presencia cruda para tenants sin configuración completa

- Ruta `GET /presencia` disponible para todos los tenants
- Tabla filtrable con `id_usuario`, `nombre`, `fecha_hora`, `tipo`
- Exportación CSV del rango seleccionado

**Verificación:**
- Tenant recién creado (sin horarios ni grupos) puede ver esta vista
- La exportación CSV produce archivo correcto

---

### Paso 7 — Gestión de feriados desde UI

- Función de carga automática al provisionar
- Rutas `GET/POST /admin/feriados`
- Admin puede agregar feriados institucionales y editar descripciones

**Verificación:**
- Al crear `test_tenant`, `SELECT count(*) FROM test_tenant.feriados;` muestra feriados nacionales
- Admin agrega feriado institucional → aparece en los reportes como día no hábil

---

### Paso 8 — Gestión de tipos de persona desde UI

- Ruta `GET/POST /admin/configuracion/tipos-persona`
- CRUD de tipos de persona del tenant
- Validación: no se puede borrar un tipo con personas asociadas

**Verificación:**
- Admin agrega tipo "Voluntario" al tenant → `tenant_tiene_tipo('Voluntario')` retorna True
- Intentar borrar un tipo con personas asociadas → error descriptivo

---

## 10. Criterio de finalización

- [ ] `alembic upgrade head` aplica migraciones en todos los schemas de tenants activos
- [ ] Superadmin crea un nuevo tenant desde la UI con tipos de persona configurados
- [ ] Provisioning incluye: schema, tipos_persona, feriados nacionales, usuario admin inicial
- [ ] Middleware carga `g.tenant_tipos` en cada request
- [ ] `tenant_tiene_tipo()` disponible en código Python y en templates Jinja2
- [ ] Desactivar un tenant bloquea el acceso sin eliminar datos
- [ ] `@require_tipo_persona` funciona en rutas que lo usan
- [ ] La UI oculta secciones según tipos de persona configurados en el tenant
- [ ] Superadmin puede hacer switch entre tenants con el mecanismo de impersonación
- [ ] Feriados nacionales cargados automáticamente al crear nuevo tenant
- [ ] Admin puede gestionar feriados institucionales y tipos de persona desde la UI
- [ ] No existe ninguna referencia a `modulo_rrhh` o `modulo_alumnos` en el código

**Una vez completados estos criterios, el sistema está listo para la Fase 4 (Períodos y Personas).**
