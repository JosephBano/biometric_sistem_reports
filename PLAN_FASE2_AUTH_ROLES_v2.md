# Plan de Implementación — Fase 2: Autenticación y Roles
**Versión:** 2.0 — Roles desacoplados de módulos
**Fecha:** 2026-03-17
**Prerequisito:** Fase 1 v2 completada y verificada

---

## Índice

1. [Contexto y cambios respecto a v1](#1-contexto-y-cambios-respecto-a-v1)
2. [Alcance](#2-alcance)
3. [Nuevas dependencias](#3-nuevas-dependencias)
4. [Modelo de autenticación](#4-modelo-de-autenticación)
5. [Sistema de roles rediseñado](#5-sistema-de-roles-rediseñado)
6. [Componentes a implementar](#6-componentes-a-implementar)
7. [Cambios en rutas existentes](#7-cambios-en-rutas-existentes)
8. [Interfaz de gestión de usuarios](#8-interfaz-de-gestión-de-usuarios)
9. [Seguridad adicional](#9-seguridad-adicional)
10. [Pasos de implementación](#10-pasos-de-implementación)
11. [Criterio de finalización](#11-criterio-de-finalización)

---

## 1. Contexto y cambios respecto a v1

### 1.1 Qué cambia

La v1 de este plan definía roles atados a módulos (`rrhh` al "módulo RRHH", `coordinador_alumnos` al "módulo Alumnos"). Con el modelo horizontal de la Fase 1 v2, **los módulos no existen como concepto**. Lo que existe son tipos de persona configurados por tenant.

Esto requiere rediseñar el sistema de roles desde el concepto, no solo renombrar:

| Rol v1 | Problema | Rol v2 |
|---|---|---|
| `rrhh` | Atado a "módulo RRHH" | `gestor` — gestiona cualquier tipo de persona |
| `coordinador_alumnos` | Atado a "módulo Alumnos" | Absorbido por `gestor` con filtro de tipo |
| `supervisor_dpto` | Atado a departamentos | `supervisor_grupo` — scoped a un `grupo_id` |
| `supervisor` | Atado a `periodos_practicas` | `supervisor_periodo` — scoped a un `periodo_vigencia_id` |
| `readonly` | Sin cambio conceptual | `readonly` |
| `admin`, `superadmin` | Sin cambio conceptual | `admin`, `superadmin` |

El decorador `@require_module` de la v1 **desaparece**. Se reemplaza por `@require_tipo_persona` que verifica si el tenant tiene configurado el tipo de persona relevante.

### 1.2 Lo que no cambia

- Login/logout con sesiones Flask
- Rate limiting en `/login`
- Middleware de tenant con `g.tenant_schema`
- Auditoría en `public.audit_log`
- Contraseñas cifradas con bcrypt
- Script `crear_superadmin.py`

---

## 2. Alcance

**Qué incluye:**
- Login y logout con sesiones Flask
- Rate limiting en el endpoint de login
- Decoradores `@require_role` y `@require_tipo_persona`
- Middleware que identifica usuario, tenant y roles en cada request
- Panel de gestión de usuarios (crear, editar, desactivar)
- Auditoría en `public.audit_log`
- Creación del primer superadmin por CLI

**Qué NO incluye:**
- 2FA (previsto pero no implementado)
- Recuperación de contraseña por email
- JWT
- SSO / OAuth

---

## 3. Nuevas dependencias

```
bcrypt>=4.1
flask-limiter>=3.5
```

**Por qué bcrypt:** Mayor resistencia a ataques de GPU que PBKDF2 de werkzeug. Para contraseñas reales de usuarios es la elección estándar.

**Por qué flask-limiter:** Rate limiting declarativo con soporte de múltiples backends. En esta fase se usa memoria; migrable a Redis en el futuro sin cambios en la lógica de negocio.

---

## 4. Modelo de autenticación

### 4.1 Flujo de login

```
1. Usuario envía email + password al POST /login
2. Rate limiter: ¿más de 5 intentos fallidos desde esta IP en 15 min?
   → Sí: HTTP 429 con Retry-After
   → No: continúa
3. Busca usuario por email en public.usuarios (activo=true)
   → No encontrado: intento fallido, error genérico
4. bcrypt.checkpw(password, usuario.password_hash)
   → No coincide: intento fallido, error genérico
5. Registrar intento exitoso en public.login_intentos
6. Actualizar usuarios.ultimo_acceso = NOW()
7. Crear sesión Flask:
   session['usuario_id']    = str(usuario.id)
   session['tenant_schema'] = tenant.slug
   session['roles']         = lista de roles
   session['nombre']        = usuario.nombre
8. Registrar en audit_log: accion='login'
9. Redirect al dashboard
```

**Mensaje de error unificado:** Tanto "usuario no encontrado" como "contraseña incorrecta" devuelven el mismo mensaje genérico.

### 4.2 Flujo de logout

```
1. POST /logout (nunca GET — evita logout por CSRF)
2. Registrar en audit_log: accion='logout'
3. session.clear()
4. Redirect al login
```

### 4.3 Sesiones Flask

```python
session = {
    'usuario_id':    UUID,
    'tenant_schema': str,   # slug del schema PostgreSQL del tenant
    'roles':         list,  # ['gestor', 'supervisor_grupo']
    'nombre':        str,
}
```

Cookie firmada con `FLASK_SECRET_KEY`. `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE='Lax'`. Expiración configurable via `PERMANENT_SESSION_LIFETIME` (default: 8 horas).

---

## 5. Sistema de roles rediseñado

### 5.1 Definición de roles

| Rol | Descripción | Puede asignar |
|---|---|---|
| `superadmin` | Acceso total. Gestiona tenants y usuarios globales. | Todos |
| `admin` | Gestiona dispositivos, horarios, personas y usuarios de su tenant. | Todos excepto `superadmin` |
| `gestor` | Ve y genera reportes de personas. Aprueba justificaciones. Gestiona horarios. | No |
| `supervisor_grupo` | Ve reportes del grupo al que está asignado (`grupo_id` en su perfil de usuario). | No |
| `supervisor_periodo` | Ve reportes del período de vigencia al que está asignado (`periodo_vigencia_id` en su perfil). | No |
| `readonly` | Solo descarga reportes pre-generados. | No |

### 5.2 Alcance de `supervisor_grupo` y `supervisor_periodo`

Estos roles tienen **scope** — su visibilidad está limitada a una entidad específica. Este scope se almacena en `public.usuarios` en el campo `configuracion` JSONB:

```json
{
  "supervisor_grupo_id": "uuid-del-grupo",
  "supervisor_periodo_id": "uuid-del-periodo-vigencia"
}
```

Un usuario puede tener ambos roles simultáneamente con diferentes scopes:
```json
{
  "supervisor_grupo_id": "uuid-docencia",
  "supervisor_periodo_id": "uuid-practicas-ene-a"
}
```

### 5.3 Reemplazo del decorador `@require_module`

La v1 usaba `@require_module('rrhh')` y `@require_module('alumnos')` para verificar si el tenant tenía el módulo activo.

En v2 ese decorador se reemplaza por `@require_tipo_persona(nombre)`:

```python
@app.route('/periodos/nuevo')
@require_role('gestor', 'admin', 'superadmin')
@require_tipo_persona('Practicante')  # Solo si el tenant tiene este tipo configurado
def nuevo_periodo():
    ...
```

`@require_tipo_persona` verifica que `g.tenant_tipos` (cargado por el middleware) contenga al menos un tipo de persona con ese nombre. Si el tenant no tiene el tipo, retorna 403 con mensaje "Esta funcionalidad no está disponible para tu institución."

Esto es equivalente al antiguo `@require_module` pero totalmente configurable — no requiere cambios de código para nuevos tipos de persona.

### 5.4 Tabla de permisos por ruta

| Ruta | Roles permitidos |
|---|---|
| `GET /` (dashboard) | Todos los autenticados |
| `POST /generar`, `POST /generar-desde-db` | `superadmin`, `admin`, `gestor` |
| `POST /sincronizar` | `superadmin`, `admin` |
| `POST /limpiar-dispositivo` | `superadmin`, `admin` |
| `POST /cargar-horarios` | `superadmin`, `admin`, `gestor` |
| `POST /api/justificaciones` | `superadmin`, `admin`, `gestor` |
| `GET /admin/usuarios` | `superadmin`, `admin` |
| `GET /admin/tenants` | `superadmin` |
| `GET /periodos` | `superadmin`, `admin`, `gestor`, `supervisor_periodo` |
| `POST /periodos` | `superadmin`, `admin`, `gestor` |
| `GET /periodos/<id>/reporte` | `superadmin`, `admin`, `gestor`, `supervisor_periodo` (solo su período) |
| `GET /grupos/<id>/reporte` | `superadmin`, `admin`, `gestor`, `supervisor_grupo` (solo su grupo) |
| `GET /descargar/<filename>` | Cualquier rol autenticado |

---

## 6. Componentes a implementar

### 6.1 `auth.py`

```python
verificar_login(email, password) → usuario_dict | None
hash_password(plain) → str
verificar_password(plain, hash) → bool
encrypt_device_password(plain) → str   # AES-256-GCM
decrypt_device_password(enc) → str
get_usuario_by_id(usuario_id) → dict | None
crear_usuario(tenant_id, email, password, nombre, roles) → dict
actualizar_roles(usuario_id, roles) → bool
desactivar_usuario(usuario_id) → bool
```

### 6.2 `decorators.py` — Decoradores de ruta

```python
@require_role(*roles)
# El usuario debe tener AL MENOS UNO de los roles.
# Falla → redirect login (HTML) o JSON 401/403 (API)

@require_tipo_persona(nombre_tipo)
# El tenant debe tener un tipo_persona con ese nombre (case-insensitive).
# Lee g.tenant_tipos cargado por el middleware.
# Falla → 403 con mensaje "Funcionalidad no disponible"
```

### 6.3 Adición a `public.usuarios` — campo `configuracion`

La tabla `public.usuarios` en la Fase 1 ya tiene el campo `configuracion JSONB`. En esta fase se usa para almacenar los scopes de supervisor:

```sql
-- Al crear usuario supervisor_grupo:
UPDATE public.usuarios
SET configuracion = configuracion || '{"supervisor_grupo_id": "uuid-aqui"}'::jsonb
WHERE id = :usuario_id;
```

### 6.4 Middleware `before_request` (versión Fase 2)

```python
@app.before_request
def autenticar_request():
    # 1. Rutas públicas (login, static): skip
    if request.endpoint in ('login', 'static'):
        return

    # 2. Verificar sesión
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    # 3. Cargar usuario y tenant
    g.usuario_id    = session['usuario_id']
    g.tenant_schema = session['tenant_schema']
    g.roles         = session['roles']
    g.nombre        = session['nombre']

    # 4. Cargar tipos de persona del tenant (para @require_tipo_persona)
    g.tenant_tipos = db.get_tipos_persona()  # lista de {id, nombre}

    # 5. Configurar search_path para el tenant
    # (ya implementado en db/connection.py desde Fase 1)
```

---

## 7. Cambios en rutas existentes

### 7.1 Rutas que se modifican

- `GET/POST /login`: implementar flujo completo con bcrypt
- `POST /logout`: implementar con audit_log
- Todas las rutas existentes: agregar `@require_role` correspondiente
- `POST /sincronizar`: agregar `@require_role('admin', 'superadmin')`
- `POST /cargar-horarios`: agregar `@require_role('admin', 'superadmin', 'gestor')`

### 7.2 Rutas que se agregan

```
GET  /admin/usuarios         → Lista de usuarios del tenant
POST /admin/usuarios         → Crear usuario nuevo
PUT  /admin/usuarios/<id>    → Editar roles / desactivar
POST /login
POST /logout
```

---

## 8. Interfaz de gestión de usuarios

### 8.1 Vista de lista de usuarios (`admin/usuarios.html`)

Muestra: nombre, email, roles, último acceso, estado activo/inactivo.
Acciones: crear nuevo, editar roles, desactivar.

### 8.2 Formulario de creación de usuario

Campos: nombre, email, contraseña temporal, roles (checkboxes).

Al seleccionar `supervisor_grupo`: aparece dropdown de grupos disponibles → guarda en `configuracion.supervisor_grupo_id`.
Al seleccionar `supervisor_periodo`: aparece dropdown de períodos activos → guarda en `configuracion.supervisor_periodo_id`.

### 8.3 Indicadores en la UI por rol

- `supervisor_periodo`: solo ve los períodos donde está asignado
- `supervisor_grupo`: solo ve el grupo donde está asignado
- `gestor`: ve todas las personas y puede generar reportes
- `admin`: ve todo + sección Administración
- Botones que requieren permisos elevados se ocultan si el rol no los permite

---

## 9. Seguridad adicional

### 9.1 Rate limiting

- `POST /login`: máximo 5 intentos por IP en ventana de 15 minutos
- HTTP 429 con header `Retry-After` al superar el límite
- Ventana reiniciada con login exitoso

### 9.2 Contraseñas de dispositivos ZK

Las contraseñas de dispositivos pasan de `.env` a `dispositivos.password_enc` cifradas con AES-256-GCM usando `DB_ENCRYPTION_KEY`. La variable `ZK_PASSWORD` en `.env` queda deprecada.

`sync.py` lee la contraseña desde la BD (descifrada en memoria) en lugar del entorno.

### 9.3 Headers de seguridad HTTP

`after_request` agrega en todas las respuestas:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Content-Security-Policy: default-src 'self'`
- `Referrer-Policy: strict-origin-when-cross-origin`

### 9.4 CSRF básico

Token CSRF en sesión para todos los formularios POST que modifican datos.

---

## 10. Pasos de implementación

### Paso 1 — Agregar dependencias y migración Alembic

- Agregar `bcrypt` y `flask-limiter` a `requirements.txt`
- Migración `0002_auth_indices.py`: índices en `public.usuarios` y `public.login_intentos`

**Verificación:** `alembic upgrade head` sin errores.

---

### Paso 2 — Crear `auth.py`

- Implementar todas las funciones de la sección 6.1
- Test unitario: login con contraseña correcta, incorrecta, usuario inactivo

**Verificación:** Crear usuario de prueba manualmente con hash bcrypt → `auth.verificar_login()` retorna usuario o None según corresponda.

---

### Paso 3 — Crear `decorators.py`

- Implementar `@require_role(*roles)`
- Implementar `@require_tipo_persona(nombre)`

**Verificación:**
- Ruta con `@require_role('admin')` redirige al login sin sesión
- Ruta con `@require_tipo_persona('Practicante')` retorna 403 en tenant sin ese tipo configurado

---

### Paso 4 — Crear `crear_superadmin.py`

Script CLI interactivo para crear el primer superadmin.

```bash
python crear_superadmin.py --email admin@istpet.edu.ec --nombre "Administrador"
```

**Verificación:** `SELECT * FROM public.usuarios;` muestra el registro con `roles = ['superadmin']`.

---

### Paso 5 — Crear el primer superadmin de ISTPET

Ejecutar el script con las credenciales reales. Verificar login.

**Verificación:** `public.audit_log` registra el primer login.

---

### Paso 6 — Reemplazar `before_request` en `app.py`

- Reemplazar middleware actual por el descrito en sección 6.4
- Remover `APP_PASSWORD_HASH` y `APP_MAINTENANCE_PASSWORD_HASH` del código

**Verificación:**
- Sin sesión: cualquier ruta protegida redirige al login
- Con sesión de superadmin: todas las rutas accesibles
- `g.tenant_schema` y `g.tenant_tipos` disponibles en cada request

---

### Paso 7 — Aplicar `@require_role` en rutas existentes

Revisar cada ruta de `app.py` y aplicar el decorador según la tabla de la sección 5.4.

**Verificación:**
- Usuario `gestor` puede generar PDFs pero no iniciar sync
- Usuario `readonly` puede descargar PDFs pero no generar nuevos
- HTTP 403 (API) o redirect (navegador) al intentar acceder sin el rol correcto

---

### Paso 8 — Cifrar contraseñas de dispositivos ZK

- Implementar `encrypt_device_password` / `decrypt_device_password` en `auth.py`
- Actualizar `sync.py` para leer contraseña desde BD
- `ZK_PASSWORD` en `.env` queda deprecada

**Verificación:**
- Sync funciona con contraseña cifrada en BD
- `SELECT password_enc FROM dispositivos;` muestra texto cifrado, no plaintext

---

### Paso 9 — Panel de gestión de usuarios

- Plantilla `admin/usuarios.html`
- Rutas `GET/POST /admin/usuarios` y `PUT /admin/usuarios/<id>`
- Formulario con scope de grupo/período para roles de supervisor

**Verificación:**
- Admin crea usuario `gestor` → puede hacer login y generar reportes
- Admin crea usuario `supervisor_periodo` con período asignado → solo ve ese período
- `audit_log` registra `crear_usuario` y `desactivar_usuario`

---

### Paso 10 — Headers de seguridad

- `after_request` con los 4 headers de seguridad
- Ajustar CSP si se usa CDN para Bootstrap

**Verificación:** DevTools → Network → los 4 headers presentes en respuestas HTML.

---

## 11. Criterio de finalización

- [ ] Login con email/password bcrypt. `APP_PASSWORD_HASH` ya no se usa.
- [ ] Rate limiting: 6to intento desde misma IP → HTTP 429
- [ ] `@require_role` aplicado en todas las rutas según la tabla de permisos
- [ ] `@require_tipo_persona` implementado y funcional
- [ ] `before_request` carga usuario, tenant, roles y `g.tenant_tipos`
- [ ] `g.tenant_schema` disponible en todos los requests protegidos
- [ ] Contraseñas de dispositivos ZK cifradas en BD. `ZK_PASSWORD` deprecada.
- [ ] Panel de gestión de usuarios funcional: crear, editar roles, desactivar
- [ ] Scopes de supervisor almacenados en `public.usuarios.configuracion`
- [ ] `audit_log` registra: login, logout, generar_pdf, sync_manual, crear_usuario
- [ ] Headers de seguridad HTTP presentes en todas las respuestas
- [ ] `crear_superadmin.py` funcional y documentado
- [ ] No existe ninguna referencia a `modulo_rrhh` o `modulo_alumnos` en el código

**Una vez completados estos criterios, el sistema está listo para la Fase 3 (Multitenancy).**
