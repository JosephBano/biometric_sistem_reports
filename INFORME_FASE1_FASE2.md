# Informe Técnico — Fase 1 y Fase 2
**Sistema de Informes Biométricos RRHH — ISTPET**
**Fecha:** 2026-03-17

---

## Índice

1. [Estado anterior al trabajo](#1-estado-anterior-al-trabajo)
2. [Fase 1 — Migración a PostgreSQL](#2-fase-1--migración-a-postgresql)
3. [Fase 2 — Autenticación y Roles](#3-fase-2--autenticación-y-roles)
4. [Variables de entorno nuevas](#4-variables-de-entorno-nuevas)
5. [Cómo poner en marcha desde cero](#5-cómo-poner-en-marcha-desde-cero)
6. [Diagrama de archivos del proyecto](#6-diagrama-de-archivos-del-proyecto)

---

## 1. Estado anterior al trabajo

Antes de estas fases el sistema funcionaba así:

- **Base de datos:** SQLite en un archivo local (`data/asistencias.db` dentro del contenedor Docker). No soportaba acceso concurrente real ni backups automatizados.
- **Modelos de datos:** Tablas planas separadas por tipo de persona (`empleados`, `alumnos`, `departamentos`, `horarios_personal`, etc.).
- **Autenticación:** Una sola contraseña compartida por toda la aplicación, almacenada como hash werkzeug en la variable de entorno `APP_PASSWORD_HASH`. No había usuarios, roles ni auditoría.
- **Escalabilidad:** Una sola instancia, sin posibilidad de multitenancy ni múltiples roles de acceso.

---

## 2. Fase 1 — Migración a PostgreSQL

### 2.1 ¿Qué se cambió?

La Fase 1 reemplazó completamente la base de datos SQLite por **PostgreSQL 16**, manteniendo **cero cambios** en `app.py`, `script.py`, `sync.py` y `horarios.py`. Todo el trabajo fue interno a la capa de datos.

### 2.2 Infraestructura Docker

**`docker-compose.yml`** ahora levanta dos servicios:

```
web  →  aplicación Flask (gunicorn)
db   →  PostgreSQL 16 con volumen persistente
```

El servicio `web` espera a que `db` esté saludable antes de arrancar (`healthcheck` + `depends_on`).

### 2.3 Arquitectura de la base de datos

Se implementó una estrategia de **schema-por-tenant** en PostgreSQL:

| Schema | Contenido |
|---|---|
| `public` | Tablas globales: `tenants`, `usuarios` (app), `audit_log`, `login_intentos` |
| `istpet` | Tablas del tenant: personas, asistencias, horarios, dispositivos, etc. |

Cuando en el futuro se agregue otra institución, se crea un nuevo schema (ej: `otra_inst`) con las mismas tablas, completamente aislado.

### 2.4 Modelo de datos horizontal (17 tablas)

El modelo anterior tenía tablas separadas por tipo de persona. Ahora hay **una sola tabla `personas`** con un campo `tipo_persona_id` que apunta a la tabla `tipos_persona`. Esto significa que empleados, practicantes, contratistas o cualquier tipo futuro son la misma entidad en la BD.

**Tablas del schema de tenant (`istpet`):**

```
BLOQUE 1 — INFRAESTRUCTURA
  sedes              Sedes físicas de la institución
  dispositivos       Dispositivos ZK (IP, puerto, contraseña cifrada)
  sync_log           Historial de sincronizaciones

BLOQUE 2 — CONFIGURACIÓN
  tipos_persona      Tipos: "Empleado", "Practicante", etc.
  grupos             Jerarquía organizacional (departamentos, bloques, carreras)
  categorias         Categorías dentro de un tipo (cargo, nivel, especialidad)

BLOQUE 3 — PERSONAS
  usuarios_zk        Usuarios descargados del dispositivo ZK
  personas           Tabla única de personas (reemplaza empleados + alumnos)
  personas_dispositivos  Vinculación N:M persona ↔ dispositivo

BLOQUE 4 — VIGENCIA
  periodos_vigencia  Períodos con fecha inicio/fin (contratos, prácticas)

BLOQUE 5 — HORARIOS
  config_ciclo_horario    Configuración de ciclos de horario rotativo
  plantillas_horario      Horarios tipo (lunes-viernes 08:00-17:00, etc.)
  asignaciones_horario    Qué plantilla aplica a qué persona y cuándo

BLOQUE 6 — ASISTENCIAS
  asistencias             Marcaciones del biométrico (Entrada/Salida)
  justificaciones         Justificaciones de ausencias/tardanzas
  breaks_categorizados    Salidas categorializadas (almuerzo, permiso, etc.)
  feriados                Feriados nacionales/locales
```

**Tablas del schema `public`:**

```
tenants             Instituciones registradas en el sistema
usuarios            Usuarios de la aplicación web (con roles y contraseñas)
audit_log           Registro de todas las acciones importantes
login_intentos      Registro de intentos de login (para rate limiting)
```

### 2.5 Capa de compatibilidad (`db/`)

El antiguo `db.py` (SQLite, ~832 líneas) se reemplazó por el paquete `db/`. La interfaz pública es **100% compatible** — las mismas funciones con las mismas firmas:

```
db/
├── __init__.py          Re-exporta todas las funciones públicas
├── connection.py        Motor SQLAlchemy, gestión de conexiones, search_path por tenant
├── init.py              init_db() — crea tablas + siembra datos iniciales
├── schema.py            DDL completo (CREATE TABLE IF NOT EXISTS)
├── migrations/
│   ├── env.py           Configuración Alembic
│   └── versions/
│       └── 0001_initial_schema.py   Migración inicial (idempotente)
└── queries/
    ├── personas.py      upsert_usuarios, get_ids_usuarios_zk
    ├── asistencias.py   insertar_asistencias, consultar_asistencias, get_personas
    ├── horarios.py      upsert_horarios, get_horarios, upsert_horario, delete_horario
    ├── justificaciones.py   insertar_justificacion, get_justificaciones, etc.
    ├── breaks.py        insertar_break_categorizado, get_breaks_categorizados_dict
    ├── feriados.py      insertar_feriado, get_feriados, importar_feriados_csv
    └── sync_log.py      registrar_sync
```

**Internamente** las queries trabajan con `persona_id` (UUID) pero las funciones públicas siguen recibiendo y devolviendo `id_usuario` (TEXT) como antes, para no romper el resto del sistema.

### 2.6 Migraciones con Alembic

Se configuró Alembic para controlar la evolución del schema. La migración `0001` aplica todo el DDL inicial de forma idempotente (`CREATE TABLE IF NOT EXISTS`).

Para aplicar migraciones:
```bash
alembic upgrade head
```

### 2.7 Inicialización automática (`init_db`)

Al arrancar la aplicación, `init_db()` ejecuta automáticamente:
1. Crea todas las tablas si no existen
2. Inserta el tenant `istpet` en `public.tenants`
3. Inserta la sede principal
4. Inserta el dispositivo ZK (con IP/puerto del `.env`)
5. Inserta los tipos de persona iniciales: "Empleado" y "Practicante"
6. Inserta feriados nacionales de Ecuador 2025 y 2026

### 2.8 Gestión de contraseña del dispositivo ZK

La contraseña del ZK que antes estaba solo en `ZK_PASSWORD` del `.env` ahora también puede guardarse cifrada en la columna `dispositivos.password_enc` (AES-256-GCM). En la Fase 2 esto se completó con las funciones de cifrado.

---

## 3. Fase 2 — Autenticación y Roles

### 3.1 ¿Qué se cambió?

La Fase 2 reemplazó el sistema de "una contraseña para todos" por **autenticación real con usuarios individuales, roles y auditoría completa**.

### 3.2 Nuevos archivos

#### `auth.py` — Módulo de autenticación

Contiene todas las funciones relacionadas con autenticación:

| Función | ¿Qué hace? |
|---|---|
| `hash_password(plain)` | Genera hash bcrypt (coste 12) de una contraseña |
| `verificar_password(plain, hash)` | Compara contraseña con hash bcrypt |
| `encrypt_device_password(plain)` | Cifra la contraseña del ZK con AES-256-GCM |
| `decrypt_device_password(enc)` | Descifra la contraseña del ZK |
| `verificar_login(email, password)` | Verifica credenciales y retorna dict del usuario |
| `get_usuario_by_id(id)` | Busca un usuario por su UUID |
| `crear_usuario(...)` | Crea un nuevo usuario con hash bcrypt |
| `actualizar_roles(usuario_id, roles, config)` | Actualiza roles y scopes de supervisores |
| `desactivar_usuario(usuario_id)` | Desactiva un usuario sin borrarlo |
| `activar_usuario(usuario_id)` | Reactiva un usuario desactivado |

**Cifrado de contraseña del dispositivo ZK:**

```
Algoritmo: AES-256-GCM (autenticado, sin posibilidad de manipulación)
Formato almacenado: base64(nonce[12 bytes] + ciphertext + tag[16 bytes])
Clave: DB_ENCRYPTION_KEY en .env (32 bytes en base64)
```

**Por qué bcrypt y no werkzeug PBKDF2:**
bcrypt tiene mayor resistencia a ataques de GPU y es el estándar para contraseñas de usuario reales. PBKDF2 es adecuado para claves de cifrado, no para contraseñas de usuario.

---

#### `decorators.py` — Decoradores de ruta

Dos decoradores que se aplican sobre las rutas de Flask:

**`@require_role(*roles)`**

```python
@app.route('/api/sincronizar', methods=['POST'])
@require_role('admin', 'superadmin')
def sincronizar():
    ...
```

- Si el usuario no tiene sesión → redirige a login (HTML) o devuelve JSON 401 (API)
- Si el usuario tiene sesión pero no tiene ninguno de los roles indicados → 403
- Las rutas API (path `/api/`) siempre devuelven JSON, nunca redirigen

**`@require_tipo_persona(nombre)`**

```python
@app.route('/periodos/nuevo')
@require_role('gestor', 'admin')
@require_tipo_persona('Practicante')
def nuevo_periodo():
    ...
```

- Verifica que el tenant tenga configurado ese tipo de persona (case-insensitive)
- Si no existe → 403 con mensaje "Esta funcionalidad no está disponible para tu institución"
- Lee `g.tenant_tipos` que el middleware carga en cada request

---

#### `crear_superadmin.py` — Script CLI

Script para crear el primer usuario del sistema. Se usa una sola vez al instalar:

```bash
python crear_superadmin.py --email admin@istpet.edu.ec --nombre "Administrador"
# (pedirá la contraseña de forma interactiva, sin eco)
```

También acepta `--password` y `--tenant` como argumentos opcionales.

---

#### `db/queries/auth.py` — Queries de autenticación

Módulo de queries SQL para todas las tablas relacionadas con auth:

| Función | Tabla | ¿Qué hace? |
|---|---|---|
| `get_usuario_por_email(email)` | `public.usuarios` | Busca usuario activo por email (incluye password_hash para verificación) |
| `get_usuario_por_id(id)` | `public.usuarios` | Busca usuario por UUID (sin password_hash) |
| `get_usuarios_tenant(tenant_id)` | `public.usuarios` | Lista todos los usuarios del tenant |
| `crear_usuario_db(...)` | `public.usuarios` | Inserta nuevo usuario |
| `actualizar_roles_db(...)` | `public.usuarios` | Actualiza roles y configuración |
| `desactivar_usuario_db(id)` | `public.usuarios` | activo=false |
| `activar_usuario_db(id)` | `public.usuarios` | activo=true |
| `actualizar_ultimo_acceso(id)` | `public.usuarios` | Actualiza timestamp de último login |
| `registrar_audit(...)` | `public.audit_log` | Registra una acción |
| `registrar_login_intento(...)` | `public.login_intentos` | Registra intento de login |
| `contar_intentos_fallidos(ip)` | `public.login_intentos` | Cuenta intentos fallidos en ventana de 15 min |
| `get_tipos_persona()` | `<tenant>.tipos_persona` | Lista tipos activos (para `@require_tipo_persona`) |
| `get_device_password_enc()` | `<tenant>.dispositivos` | Lee contraseña cifrada del dispositivo |
| `set_device_password_enc(enc)` | `<tenant>.dispositivos` | Guarda contraseña cifrada |

---

#### `db/migrations/versions/0002_auth_indices.py`

Migración Alembic que agrega:
- Columna `configuracion JSONB NOT NULL DEFAULT '{}'` en `public.usuarios` (para scopes de supervisores)
- Índice en `public.usuarios(email)` — acelera el login
- Índice en `public.usuarios(tenant_id)` — acelera listado de usuarios por tenant
- Índice en `public.login_intentos(ip, creado_en DESC)` — acelera conteo de intentos fallidos
- Índice en `public.audit_log(tenant_id, creado_en DESC)` — acelera consultas de auditoría

---

#### `templates/admin/usuarios.html` — Panel de gestión de usuarios

Interfaz web (Bootstrap 5) para que admin y superadmin gestionen los usuarios:

- **Lista de usuarios**: nombre, email, roles (badges de colores), último acceso, estado activo/inactivo
- **Crear usuario**: nombre, email, contraseña temporal, roles (checkboxes), scopes de supervisor
- **Editar usuario**: cambiar roles, asignar scopes, activar/desactivar
- **Scopes dinámicos**: al marcar `supervisor_grupo` aparece un dropdown de grupos; al marcar `supervisor_periodo` aparece un dropdown de períodos activos

---

### 3.3 Cambios en `app.py`

#### Sistema de autenticación nuevo

| Antes | Después |
|---|---|
| `APP_PASSWORD_HASH` en env | Usuarios en `public.usuarios` con bcrypt |
| Una contraseña para todos | Cada persona tiene su email + contraseña |
| `session["autenticado"] = True` | `session["usuario_id"]`, `session["roles"]`, `session["tenant_schema"]`, `session["nombre"]` |
| Sin auditoría | Login, logout y acciones clave se registran en `public.audit_log` |
| Sin rate limiting | `flask-limiter`: máximo 5 intentos fallidos por IP en 15 minutos |

#### Middleware `before_request`

En cada request autenticado el middleware carga en `g` (contexto de Flask):

```python
g.usuario_id    = session["usuario_id"]     # UUID del usuario
g.tenant_schema = session["tenant_schema"]  # slug del schema PostgreSQL
g.roles         = session["roles"]          # lista de roles
g.nombre        = session["nombre"]         # nombre completo
g.tenant_id     = session["tenant_id"]      # UUID del tenant
g.tenant_tipos  = db.get_tipos_persona()    # tipos activos (para @require_tipo_persona)
```

#### Protección CSRF

Todos los formularios HTML POST incluyen un token CSRF:
- Se genera automáticamente en la sesión con `secrets.token_hex(32)`
- El template lo incluye con `{{ csrf_token() }}`
- El middleware lo valida en cada POST no-API
- Las rutas `/api/` están exentas (usan JSON, no formularios)

#### Headers de seguridad HTTP

`after_request` agrega en todas las respuestas:

```
X-Content-Type-Options: nosniff
X-Frame-Options: SAMEORIGIN
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; ...
```

#### Rutas nuevas en `app.py`

| Ruta | Método | Roles | Descripción |
|---|---|---|---|
| `/login` | GET/POST | — | Login con email + contraseña |
| `/logout` | POST | Cualquier autenticado | Cierra sesión |
| `/admin/usuarios` | GET | admin, superadmin | Lista de usuarios |
| `/admin/usuarios` | POST | admin, superadmin | Crear usuario nuevo |
| `/admin/usuarios/<id>` | POST | admin, superadmin | Editar usuario (roles, estado) |

#### `@require_role` aplicado en rutas existentes

| Ruta | Roles permitidos |
|---|---|
| `POST /api/sincronizar` | admin, superadmin |
| `POST /api/generar-desde-db` | superadmin, admin, gestor |
| `POST /api/reportes/enviar-email` | superadmin, admin, gestor |
| `POST /api/limpiar-dispositivo` | superadmin, admin |
| `GET /api/backup/descargar` | superadmin, admin |
| `GET /api/backup/csv` | superadmin, admin, gestor |
| `POST /api/historicos/importar` | superadmin, admin |
| `POST /api/horarios/importar` | superadmin, admin, gestor |
| `GET /api/horarios/exportar` | superadmin, admin, gestor |
| `POST /api/horarios` | superadmin, admin, gestor |
| `PUT /api/horarios/<id>` | superadmin, admin, gestor |
| `DELETE /api/horarios/<id>` | superadmin, admin |
| `POST /api/justificaciones` | superadmin, admin, gestor |
| `DELETE /api/justificaciones/<id>` | superadmin, admin |
| `POST /api/feriados` | superadmin, admin |
| `DELETE /api/feriados/<fecha>` | superadmin, admin |
| `POST /api/feriados/importar` | superadmin, admin |
| `POST /api/categorizar-break` | superadmin, admin, gestor |

Las rutas de solo lectura (`GET`) son accesibles por cualquier usuario autenticado.

---

### 3.4 Cambios en `sync.py`

La contraseña del dispositivo ZK ahora se lee con prioridad desde la BD:

```python
def _get_zk_password() -> int:
    # 1. Intenta leer password_enc de la BD y descifrarlo
    enc = db.get_device_password_enc()
    if enc:
        return int(auth.decrypt_device_password(enc))
    # 2. Fallback: ZK_PASSWORD en .env (deprecada)
    return int(os.getenv("ZK_PASSWORD", "0"))
```

`ZK_PASSWORD` en `.env` sigue funcionando como fallback hasta que la contraseña se migre a la BD.

---

### 3.5 Sistema de roles

| Rol | Descripción | ¿Puede asignar? |
|---|---|---|
| `superadmin` | Acceso total. Gestiona tenants y usuarios globales. | Todos |
| `admin` | Gestiona dispositivos, horarios, personas y usuarios del tenant. | Todos excepto `superadmin` |
| `gestor` | Ve y genera reportes, aprueba justificaciones, gestiona horarios. | No |
| `supervisor_grupo` | Ve reportes del grupo al que está asignado. | No |
| `supervisor_periodo` | Ve reportes del período de vigencia al que está asignado. | No |
| `readonly` | Solo descarga reportes pre-generados. | No |

**Scopes de supervisor:**

Los supervisores tienen un "scope" que limita qué datos pueden ver. Se almacena en `public.usuarios.configuracion` (JSONB):

```json
{
  "supervisor_grupo_id": "uuid-del-grupo",
  "supervisor_periodo_id": "uuid-del-periodo"
}
```

---

### 3.6 Auditoría

Las siguientes acciones quedan registradas en `public.audit_log` con timestamp, IP y usuario:

- `login` — inicio de sesión exitoso
- `logout` — cierre de sesión
- `generar_pdf` — generación de reporte PDF
- `limpiar_dispositivo` — limpieza del log ZK
- `crear_usuario` — creación de nuevo usuario
- `editar_usuario` — cambio de roles o estado
- `desactivar_usuario` — desactivación de cuenta

---

## 4. Variables de entorno nuevas

### Fase 1

| Variable | Descripción | Ejemplo |
|---|---|---|
| `DATABASE_URL` | URL de conexión PostgreSQL | `postgresql://user:pass@db:5432/asistencias_db` |
| `POSTGRES_USER` | Usuario de PostgreSQL (Docker) | `asistencias_user` |
| `POSTGRES_PASSWORD` | Contraseña de PostgreSQL (Docker) | `clave_segura` |
| `POSTGRES_DB` | Nombre de la base de datos | `asistencias_db` |
| `TENANT_DEFAULT` | Slug del tenant (schema en PostgreSQL) | `istpet` |
| `DB_ENCRYPTION_KEY` | Clave AES-256 en base64 para cifrar contraseñas de dispositivos | ver abajo |

Para generar `DB_ENCRYPTION_KEY`:
```bash
python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

### Fase 2

| Variable | Descripción | Default |
|---|---|---|
| `FLASK_SECRET_KEY` | Clave para firmar las cookies de sesión | *(cambiar en producción)* |
| `SESSION_LIFETIME_HOURS` | Duración de la sesión en horas | `8` |

### Deprecadas (Fase 2)

| Variable | Estado |
|---|---|
| `APP_PASSWORD_HASH` | **Eliminada.** La autenticación ahora usa `public.usuarios` con bcrypt. |
| `APP_MAINTENANCE_PASSWORD_HASH` | **Eliminada.** Reemplazada por `@require_role('admin', 'superadmin')`. |
| `ZK_PASSWORD` | **Deprecada.** Sigue funcionando como fallback. La contraseña ahora debe almacenarse cifrada en `dispositivos.password_enc` via la BD. |

---

## 5. Cómo poner en marcha desde cero

### Primera instalación

```bash
# 1. Copiar y rellenar el .env
cp .env.example .env
# → Editar DATABASE_URL, FLASK_SECRET_KEY, DB_ENCRYPTION_KEY, ZK_IP, etc.

# 2. Generar DB_ENCRYPTION_KEY y agregarla al .env
python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"

# 3. Levantar contenedores
docker compose up -d

# 4. Aplicar migraciones
docker compose exec web alembic upgrade head

# 5. Crear el primer superadmin
docker compose exec web python crear_superadmin.py \
    --email admin@istpet.edu.ec \
    --nombre "Administrador"
# (pedirá la contraseña)

# 6. Abrir el navegador en http://localhost:5000
```

### Instalación con BD ya existente (upgrade desde Fase 1)

```bash
# 1. Actualizar dependencias
pip install bcrypt flask-limiter

# 2. Aplicar solo la migración 0002
alembic upgrade head

# 3. Crear superadmin (aún no existe ningún usuario en public.usuarios)
python crear_superadmin.py --email admin@istpet.edu.ec --nombre "Administrador"
```

---

## 6. Diagrama de archivos del proyecto

```
script_informe_asistencia/
│
├── app.py                      Servidor Flask (auth + todas las rutas)
├── script.py                   Motor de análisis y generación de PDF [NO MODIFICAR]
├── sync.py                     Conector ZK (pyzk), scheduler
├── horarios.py                 Parser de archivos .obd/.ods/.csv
│
├── auth.py                     ★ NUEVO — bcrypt, AES-256-GCM, CRUD usuarios
├── decorators.py               ★ NUEVO — @require_role, @require_tipo_persona
├── crear_superadmin.py         ★ NUEVO — CLI para crear primer superadmin
│
├── db/
│   ├── __init__.py             Wrapper: re-exporta todas las funciones públicas
│   ├── connection.py           Motor SQLAlchemy, get_connection(), get_tenant_schema()
│   ├── init.py                 init_db() — crea tablas + seeds
│   ├── schema.py               DDL completo (CREATE TABLE IF NOT EXISTS)
│   ├── migrations/
│   │   ├── env.py              Config Alembic
│   │   └── versions/
│   │       ├── 0001_initial_schema.py   Schema completo Fase 1
│   │       └── 0002_auth_indices.py    ★ NUEVO — configuracion JSONB + índices
│   └── queries/
│       ├── personas.py         Queries de personas/usuarios ZK
│       ├── asistencias.py      Queries de asistencias
│       ├── horarios.py         Queries de horarios personalizados
│       ├── justificaciones.py  Queries de justificaciones
│       ├── breaks.py           Queries de breaks categorizados
│       ├── feriados.py         Queries de feriados
│       ├── sync_log.py         Queries de log de sincronización
│       └── auth.py             ★ NUEVO — Queries de auth, audit_log, login_intentos
│
├── templates/
│   ├── base.html               Layout base (sidebar con usuario/roles)
│   ├── login.html              ★ ACTUALIZADO — email + contraseña
│   ├── dashboard.html          Panel principal
│   ├── configuracion.html      Página de configuración
│   ├── justificaciones.html    Página de justificaciones
│   ├── reportes.html           Página de reportes
│   └── admin/
│       └── usuarios.html       ★ NUEVO — Panel de gestión de usuarios
│
├── static/
│   └── style.css               Estilos Bootstrap 5 + custom
│
├── Dockerfile                  Imagen Docker (gunicorn)
├── docker-compose.yml          web + db (PostgreSQL 16)
├── alembic.ini                 Configuración de Alembic
├── requirements.txt            Dependencias Python
└── .env.example                Plantilla de variables de entorno
```

---

*Informe generado el 2026-03-17. Para dudas técnicas sobre la implementación, consultar los archivos de plan: `PLAN_FASE1_POSTGRESQL_v2.md` y `PLAN_FASE2_AUTH_ROLES_v2.md`.*
