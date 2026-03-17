# Plan de Implementación — Fase 1: PostgreSQL + Modelo de Datos Horizontal
**Versión:** 2.0 — Arquitectura horizontal (revisión completa)
**Fecha:** 2026-03-17
**Estado:** Listo para implementar
**Reemplaza a:** PLAN_FASE1_POSTGRESQL.md (v1)

---

## Índice

1. [Contexto y decisiones de diseño](#1-contexto-y-decisiones-de-diseño)
2. [Qué cambia respecto a la v1](#2-qué-cambia-respecto-a-la-v1)
3. [Alcance de la Fase 1](#3-alcance-de-la-fase-1)
4. [Nuevas dependencias](#4-nuevas-dependencias)
5. [Cambios de infraestructura](#5-cambios-de-infraestructura)
6. [Arquitectura de la base de datos](#6-arquitectura-de-la-base-de-datos)
7. [Esquema completo de tablas](#7-esquema-completo-de-tablas)
8. [Capa de abstracción SQLAlchemy](#8-capa-de-abstracción-sqlalchemy)
9. [Gestión de migraciones con Alembic](#9-gestión-de-migraciones-con-alembic)
10. [Pasos de implementación](#10-pasos-de-implementación)
11. [Reimportación de horarios](#11-reimportación-de-horarios)
12. [Criterio de finalización](#12-criterio-de-finalización)
13. [Apéndice A: Diferencias SQLite → PostgreSQL](#apéndice-a-diferencias-sqlite--postgresql)
14. [Apéndice B: Resolución de horario activo](#apéndice-b-resolución-de-horario-activo)

---

## 1. Contexto y decisiones de diseño

### 1.1 Decisiones técnicas base (sin cambio respecto a v1)

| Decisión | Valor |
|---|---|
| Datos SQLite actuales | Se descartan. Migración limpia. |
| Horarios existentes | Reimportar desde CSV ya exportado. |
| Motor de base de datos | PostgreSQL 16 |
| Abstracción de BD | SQLAlchemy Core (no ORM completo) |
| Migraciones de esquema | Alembic |
| Estrategia multitenancy | Schema por tenant en PostgreSQL |
| Framework web | Flask (sin cambios) |
| Generador de PDFs | ReportLab (sin cambios) |

### 1.2 Decisiones de arquitectura nuevas en v2

Estas decisiones redefinen el modelo de datos respecto a la v1:

| Decisión | Valor | Motivo |
|---|---|---|
| Modelo de personas | Tabla única `personas` con `tipo_persona_id` | Empleados, alumnos, contratistas y cualquier tipo futuro son la misma entidad |
| Módulos del tenant | Eliminados (`modulo_rrhh`, `modulo_alumnos` no existen) | Los módulos se expresan a través de los tipos de persona configurados |
| Vinculación biométrica | Tabla `personas_dispositivos` (N:M) | Una persona puede tener IDs distintos en distintos dispositivos |
| Grupos organizacionales | Tabla `grupos` jerárquica (auto-referenciada) | Reemplaza `departamentos`, `oficinas`, `bloques`, `carreras` |
| Categorías | Tabla `categorias` genérica | Reemplaza `cargos`, `niveles`, `especialidades` |
| Horarios | Plantillas reutilizables + asignaciones con ciclos | Soporta horarios fijos, cambios en el tiempo y rotaciones complejas |
| Vigencia | Tabla `periodos_vigencia` con `fecha_fin` nullable | Empleados indefinidos y contratos con fecha son el mismo modelo |
| Asistencias | Tabla única para todos los tipos de persona | Una sola tabla `asistencias` con `persona_id` |

### 1.3 Lo que NO cambia en esta fase

- `script.py` — motor de análisis y generación de PDFs. No se toca.
- `horarios.py` — parser de archivos .obd/.ods/.csv. No se toca.
- La lógica de negocio (tardanzas, almuerzos, justificaciones, feriados).
- ReportLab como generador de PDFs.
- Flask como framework web.
- Las firmas públicas de `db.py` que consume el resto del sistema.

---

## 2. Qué cambia respecto a la v1

### Tablas que desaparecen

| Tabla v1 | Motivo |
|---|---|
| `empleados` | Absorbida por `personas` |
| `alumnos` | Absorbida por `personas` con tipo distinto |
| `departamentos` | Absorbida por `grupos` |
| `oficinas` | Absorbida por `grupos` (nodo hijo) |
| `bloques` | Absorbida por `grupos` |
| `cargos` | Absorbida por `categorias` |
| `carreras` | Absorbida por `categorias` o `grupos` según el tenant |
| `periodos_practicas` | Absorbida por `periodos_vigencia` |
| `matriculas_periodo` | Absorbida por `periodos_vigencia` (por persona) |
| `asistencias_alumnos` | Absorbida por `asistencias` |
| `horarios_personal` | Absorbida por `plantillas_horario` + `asignaciones_horario` |

### Tablas que se agregan

| Tabla nueva | Reemplaza / Función |
|---|---|
| `tipos_persona` | Nuevo concepto. Define qué tipos existen en el tenant |
| `personas` | Reemplaza `empleados` + `alumnos` |
| `personas_dispositivos` | Nuevo. Vinculación N:M persona ↔ dispositivo |
| `grupos` | Reemplaza `departamentos` + `oficinas` + `bloques` |
| `categorias` | Reemplaza `cargos` + `niveles` + `carreras` |
| `periodos_vigencia` | Reemplaza `periodos_practicas` + `matriculas_periodo` |
| `plantillas_horario` | Reemplaza `horarios_personal` (parte de estructura) |
| `asignaciones_horario` | Nuevo. Vincula plantilla ↔ persona con ciclos y vigencia |
| `config_ciclo_horario` | Nuevo. Ancla temporal para rotaciones complejas |

### Tablas que se mantienen sin cambio conceptual

`sedes`, `dispositivos`, `sync_log`, `feriados`, `public.tenants`, `public.usuarios`, `public.audit_log`, `public.login_intentos`

### Tablas que cambian solo el tipo de la clave foránea

`justificaciones` y `breaks_categorizados`: el campo `id_usuario TEXT` se reemplaza por `persona_id UUID FK personas(id)`.

---

## 3. Alcance de la Fase 1

**Qué incluye esta fase:**
- Levantar PostgreSQL 16 como servicio Docker
- Diseñar e implementar el schema completo horizontal en PostgreSQL
- Reemplazar `db.py` con capa SQLAlchemy Core compatible con schema-por-tenant
- Configurar Alembic para gestión de migraciones futuras
- Reimportar el CSV de horarios existentes al nuevo modelo
- Verificar que el flujo actual (sync ZK → generar PDF) funciona sobre la nueva BD

**Qué NO incluye esta fase:**
- Auth y roles (Fase 2)
- UI de gestión de personas, grupos, tipos (Fases posteriores)
- Multi-dispositivo completo con Tailscale (Fase 6)
- Analytics e IA (Fase 5)

Durante esta fase, el sistema corre con un único tenant predefinido (`istpet`) creado manualmente, sin UI de gestión de tenants. La autenticación sigue siendo la contraseña simple existente hasta la Fase 2.

---

## 4. Nuevas dependencias

```
# Base de datos
sqlalchemy>=2.0
psycopg2-binary>=2.9

# Migraciones
alembic>=1.13

# Cifrado (para contraseñas de dispositivos ZK en BD)
cryptography>=42.0
```

**Por qué SQLAlchemy Core y no ORM:**
El ORM completo requeriría reescribir toda la lógica de consultas como objetos Python. Core mantiene SQL explícito pero permite cambiar el driver con un cambio de connection string. El riesgo de regresión es mínimo.

**Por qué psycopg2-binary y no psycopg3:**
Mayor madurez, mejor soporte en entornos Docker, compatibilidad garantizada con SQLAlchemy 2.x.

---

## 5. Cambios de infraestructura

### 5.1 docker-compose.yml

Se agrega el servicio `db` (PostgreSQL 16) con volumen persistente. La app Flask depende de que la BD esté lista.

Configuración relevante:
- Puerto `5432` expuesto solo en localhost
- Volumen nombrado `postgres_data` en `/var/lib/postgresql/data`
- Healthcheck para que Flask espere a PostgreSQL listo
- La app Flask mantiene `network_mode: host` (necesario para conectar al ZK)

### 5.2 Variables de entorno (.env)

**Variables que se reemplazan:**

| Variable antigua | Variable nueva | Nota |
|---|---|---|
| `DB_PATH` | `DATABASE_URL` | `postgresql://user:pass@localhost:5432/asistencias_db` |

**Variables que se agregan:**

| Variable | Descripción | Ejemplo |
|---|---|---|
| `POSTGRES_USER` | Usuario de PostgreSQL | `asistencias_user` |
| `POSTGRES_PASSWORD` | Contraseña de PostgreSQL | `cambiar_esto` |
| `POSTGRES_DB` | Nombre de la base de datos | `asistencias_db` |
| `TENANT_DEFAULT` | Slug del tenant activo en dev | `istpet` |
| `DB_ENCRYPTION_KEY` | Clave AES-256 para cifrar passwords de dispositivos ZK | `clave_aleatoria_32_bytes` |

**Variables que se mantienen sin cambio:**
Todas las variables de ZK, SMTP, Flask y autenticación simple siguen igual.

### 5.3 Estructura de archivos

```
proyecto/
├── db.py              → REEMPLAZADO por wrapper que re-exporta db/
├── db/
│   ├── __init__.py    → Re-exporta funciones públicas (compatibilidad total)
│   ├── connection.py  → Engine, session factory, schema switching
│   ├── models.py      → Definición de tablas con SQLAlchemy Core (metadata)
│   ├── queries/
│   │   ├── asistencias.py
│   │   ├── horarios.py       ← lógica de resolución de plantilla activa
│   │   ├── personas.py       ← lookup id_en_dispositivo → persona_id
│   │   ├── dispositivos.py
│   │   ├── sync_log.py
│   │   ├── justificaciones.py
│   │   ├── breaks.py
│   │   ├── feriados.py
│   │   └── tenants.py
│   └── migrations/
│       ├── env.py
│       ├── alembic.ini
│       └── versions/
│           └── 0001_initial_schema.py
```

**Compatibilidad hacia atrás:** El archivo `db.py` en la raíz re-exporta todas las funciones de `db/` con la misma firma exacta. `app.py`, `script.py` y `sync.py` no requieren ningún cambio.

---

## 6. Arquitectura de la base de datos

### 6.1 Estrategia schema-por-tenant

```
PostgreSQL: asistencias_db
│
├── Schema: public
│   ├── tenants              (registro de instituciones)
│   ├── usuarios             (usuarios de la app)
│   ├── audit_log            (log de acciones)
│   └── login_intentos       (rate limiting)
│
├── Schema: istpet
│   ├── Infraestructura:     sedes, dispositivos, sync_log, feriados
│   ├── Configuración:       tipos_persona, grupos, categorias
│   ├── Personas:            personas, personas_dispositivos, usuarios_zk
│   ├── Vigencia:            periodos_vigencia
│   ├── Horarios:            config_ciclo_horario, plantillas_horario,
│   │                        asignaciones_horario
│   └── Asistencia:          asistencias, justificaciones,
│                            breaks_categorizados
│
└── Schema: otra_institucion
    └── (mismas tablas, datos completamente aislados)
```

### 6.2 Schema switching en Flask

```
Request entrante
  → Middleware de tenant (lee tenant del usuario en sesión)
  → SET search_path TO {tenant_slug}, public
  → Todas las queries del request usan ese schema automáticamente
  → Al final del request, conexión devuelta al pool
```

Durante la Fase 1, el tenant se determina desde `TENANT_DEFAULT`.

### 6.3 Flujo de sync ZK con el nuevo modelo

El cambio más importante respecto al sistema anterior es cómo se procesa un registro del dispositivo:

```
ZK reporta: { id_usuario: "00042", nombre: "JUAN PEREZ", fecha_hora: "...", tipo: "entrada" }
  ↓
1. Busca en personas_dispositivos:
   WHERE id_en_dispositivo = '00042' AND dispositivo_id = <id_dispositivo_activo>
  ↓
2a. Encontrado → obtiene persona_id (UUID)
2b. No encontrado → crea entrada en usuarios_zk y personas (como "sin perfil"),
    crea personas_dispositivos
  ↓
3. Inserta en asistencias con persona_id (UUID)
  ↓
4. La capa de compatibilidad retorna el registro con id_usuario y nombre
   para que script.py no note ningún cambio
```

---

## 7. Esquema completo de tablas

---

### Schema: public

---

#### `public.tenants`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK DEFAULT gen_random_uuid() | |
| `slug` | TEXT UNIQUE NOT NULL | Nombre del schema. Solo `[a-z0-9_]`. |
| `nombre` | TEXT NOT NULL | Nombre completo |
| `nombre_corto` | TEXT | Para reportes |
| `zona_horaria` | TEXT DEFAULT `'America/Guayaquil'` | |
| `activo` | BOOLEAN DEFAULT true | |
| `configuracion` | JSONB DEFAULT `'{}'` | Config flexible: logo, colores, umbrales, fecha_referencia_ciclos |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |

**Nota:** Los campos `modulo_rrhh` y `modulo_alumnos` de la v1 **no existen** en este schema. La funcionalidad disponible en un tenant se determina por los `tipos_persona` que tenga configurados, no por flags globales.

---

#### `public.usuarios`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK DEFAULT gen_random_uuid() | |
| `tenant_id` | UUID FK `tenants(id)` NULLABLE | NULL = superadmin global |
| `email` | TEXT UNIQUE NOT NULL | Login principal |
| `password_hash` | TEXT NOT NULL | bcrypt |
| `nombre` | TEXT NOT NULL | |
| `roles` | TEXT[] NOT NULL DEFAULT `'{}'` | |
| `activo` | BOOLEAN DEFAULT true | |
| `ultimo_acceso` | TIMESTAMPTZ | |
| `creado_por` | UUID FK `usuarios(id)` NULLABLE | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |

---

#### `public.audit_log`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `tenant_id` | UUID FK `tenants(id)` NULLABLE | |
| `usuario_id` | UUID FK `usuarios(id)` NULLABLE | NULL = acción del sistema |
| `accion` | TEXT NOT NULL | `login`, `generar_pdf`, `sync_manual`, etc. |
| `entidad` | TEXT | `persona`, `dispositivo`, `periodo_vigencia` |
| `entidad_id` | TEXT | |
| `detalle` | JSONB | |
| `ip` | TEXT | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |

---

#### `public.login_intentos`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `ip` | TEXT NOT NULL | |
| `email` | TEXT | |
| `exitoso` | BOOLEAN NOT NULL | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |

---

### Schema: {tenant_slug}

Todas las tablas siguientes existen en el schema del tenant. El `search_path` activo determina cuál schema se usa sin prefijo en las queries.

---

### Bloque 1: Infraestructura

---

#### `sedes`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK DEFAULT gen_random_uuid() | |
| `nombre` | TEXT NOT NULL | "Sede Central", "Sede Norte" |
| `direccion` | TEXT | |
| `activa` | BOOLEAN DEFAULT true | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |

---

#### `dispositivos`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK DEFAULT gen_random_uuid() | |
| `nombre` | TEXT NOT NULL | "Portería Principal", "Lab Prácticas 1" |
| `ip` | TEXT NOT NULL | IP en red local o Tailscale |
| `puerto` | INTEGER DEFAULT 4370 | |
| `password_enc` | TEXT | Contraseña cifrada AES-256 |
| `tipo_driver` | TEXT DEFAULT `'zk'` | `'zk'`, `'hikvision'`, `'suprema'`, `'dahua'` |
| `protocolo` | TEXT DEFAULT `'tcp'` | `'tcp'` o `'udp'` |
| `sede_id` | UUID FK `sedes(id)` NULLABLE | |
| `activo` | BOOLEAN DEFAULT true | |
| `timeout_seg` | INTEGER DEFAULT 120 | |
| `watermark_ultimo_id` | TEXT | Base de sync incremental (Fase 7). NULL en Fase 1. |
| `watermark_ultima_fecha` | TIMESTAMPTZ | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |

---

#### `sync_log`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `dispositivo_id` | UUID FK `dispositivos(id)` NULLABLE | NULL = sync del sistema anterior |
| `fecha_sync` | TIMESTAMPTZ DEFAULT NOW() | |
| `fecha_inicio_rango` | DATE | |
| `fecha_fin_rango` | DATE | |
| `registros_obtenidos` | INTEGER DEFAULT 0 | |
| `registros_nuevos` | INTEGER DEFAULT 0 | |
| `registros_en_dispositivo` | INTEGER DEFAULT 0 | |
| `exito` | BOOLEAN NOT NULL | |
| `error_detalle` | TEXT | |

---

#### `feriados`

| Columna | Tipo | Descripción |
|---|---|---|
| `fecha` | DATE PK | |
| `descripcion` | TEXT NOT NULL | |
| `tipo` | TEXT DEFAULT `'nacional'` | `'nacional'` o `'institucional'` |

---

### Bloque 2: Configuración del tenant

Estas tablas definen la estructura organizacional del tenant. Son completamente configurables: cada tenant decide qué tipos de persona tiene, cómo se llaman sus grupos y qué categorías usa.

---

#### `tipos_persona`

Define los tipos de persona que existen en el tenant. Reemplaza los flags `modulo_rrhh` y `modulo_alumnos`.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK DEFAULT gen_random_uuid() | |
| `nombre` | TEXT NOT NULL | "Empleado", "Practicante", "Contratista", "Voluntario" |
| `descripcion` | TEXT | |
| `color` | TEXT | Hex color para UI. Ej: `'#2E75B6'` |
| `icono` | TEXT | Nombre de icono para UI |
| `activo` | BOOLEAN DEFAULT true | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |

**Datos iniciales para ISTPET:**
```sql
INSERT INTO tipos_persona (nombre, descripcion) VALUES
  ('Empleado',    'Personal con contrato laboral'),
  ('Practicante', 'Alumno en período de prácticas');
```

---

#### `grupos`

Estructura organizacional jerárquica. Reemplaza `departamentos`, `oficinas`, `bloques` y `carreras`.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK DEFAULT gen_random_uuid() | |
| `nombre` | TEXT NOT NULL | "Docencia", "Secretaría General", "Bloque A" |
| `tipo_grupo` | TEXT | Etiqueta libre: `'departamento'`, `'area'`, `'bloque'`. Solo para UI. |
| `padre_id` | UUID FK `grupos(id)` NULLABLE | Self-reference para jerarquía |
| `sede_id` | UUID FK `sedes(id)` NULLABLE | |
| `activo` | BOOLEAN DEFAULT true | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |

**Ejemplo para ISTPET:**
```
Docencia (tipo_grupo='departamento')
└── Ciencias Básicas (tipo_grupo='area', padre_id=Docencia.id)
└── Tecnología (tipo_grupo='area', padre_id=Docencia.id)
Administrativo (tipo_grupo='departamento')
└── Secretaría General (tipo_grupo='area', padre_id=Administrativo.id)
```

**Nota de diseño:** El campo `tipo_grupo` es solo una etiqueta descriptiva para la UI. La jerarquía real se expresa con `padre_id`. No hay límite de niveles de profundidad.

---

#### `categorias`

Reemplaza `cargos`, `niveles` y cualquier clasificación adicional de personas.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK DEFAULT gen_random_uuid() | |
| `nombre` | TEXT NOT NULL | "Docente", "Secretaria", "Director Académico", "Primer Nivel" |
| `tipo_persona_id` | UUID FK `tipos_persona(id)` NULLABLE | Si es NULL aplica a todos los tipos |
| `activo` | BOOLEAN DEFAULT true | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |

---

### Bloque 3: Personas y vinculación biométrica

---

#### `usuarios_zk`

Espejo de los registros en el dispositivo. Se actualiza en cada sync. Permanece como tabla de referencia del hardware.

| Columna | Tipo | Descripción |
|---|---|---|
| `id_usuario` | TEXT PK | ID interno del dispositivo ZK |
| `nombre` | TEXT NOT NULL | Nombre como está en el ZK |
| `privilegio` | INTEGER | |
| `actualizado_en` | TIMESTAMPTZ DEFAULT NOW() | |

---

#### `personas`

Tabla central del sistema. Una fila por persona física, independientemente de su tipo.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK DEFAULT gen_random_uuid() | |
| `nombre` | TEXT NOT NULL | Nombre canónico (puede diferir del nombre en el ZK) |
| `identificacion` | TEXT UNIQUE NULLABLE | Cédula, pasaporte u otro documento |
| `tipo_persona_id` | UUID FK `tipos_persona(id)` NOT NULL | |
| `grupo_id` | UUID FK `grupos(id)` NULLABLE | Departamento, área, bloque, etc. |
| `categoria_id` | UUID FK `categorias(id)` NULLABLE | Cargo, nivel, especialidad, etc. |
| `sede_id` | UUID FK `sedes(id)` NULLABLE | |
| `email` | TEXT NULLABLE | |
| `telefono` | TEXT NULLABLE | |
| `activo` | BOOLEAN DEFAULT true | |
| `notas` | TEXT | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |

**Reglas de negocio:**
- Una persona no se elimina nunca. Se desactiva con `activo = false`.
- La `identificacion` es permanente y es la clave para consultas históricas y reclamos.
- Durante la Fase 1, esta tabla puede estar vacía o con datos mínimos. El sistema sigue funcionando con `usuarios_zk` + `personas_dispositivos`.

---

#### `personas_dispositivos`

Vinculación N:M entre personas y dispositivos. Permite que una persona tenga IDs distintos en dispositivos distintos.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK DEFAULT gen_random_uuid() | |
| `persona_id` | UUID FK `personas(id)` NOT NULL | |
| `dispositivo_id` | UUID FK `dispositivos(id)` NOT NULL | |
| `id_en_dispositivo` | TEXT NOT NULL | ID interno del ZK (mismo valor que `usuarios_zk.id_usuario` para ese dispositivo) |
| `es_principal` | BOOLEAN DEFAULT true | El dispositivo principal de esta persona |
| `activo` | BOOLEAN DEFAULT true | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |
| UNIQUE | `(dispositivo_id, id_en_dispositivo)` | Un ID por dispositivo es único |

**Cómo funciona el lookup en sync:**
```sql
SELECT p.id, p.nombre
FROM personas p
JOIN personas_dispositivos pd ON pd.persona_id = p.id
WHERE pd.id_en_dispositivo = :id_usuario_del_zk
  AND pd.dispositivo_id = :id_dispositivo_activo
  AND pd.activo = true
LIMIT 1
```

**Compatibilidad hacia atrás:** La capa `db/queries/personas.py` expone una función `resolver_persona(id_usuario, dispositivo_id)` que hace este lookup y retorna `{persona_id, nombre}`. Las funciones de compatibilidad usan este resolver internamente.

---

### Bloque 4: Vigencia

---

#### `periodos_vigencia`

Reemplaza `periodos_practicas` y el concepto de contrato de empleado. Cualquier persona puede tener uno o más períodos.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK DEFAULT gen_random_uuid() | |
| `persona_id` | UUID FK `personas(id)` NOT NULL | |
| `nombre` | TEXT NOT NULL | "Contrato 2024", "Prácticas Enero A 2026", "Guardia Verano" |
| `fecha_inicio` | DATE NOT NULL | |
| `fecha_fin` | DATE NULLABLE | NULL = indefinido (empleado de planta) |
| `estado` | TEXT DEFAULT `'activo'` | `'activo'`, `'cerrado'`, `'archivado'` |
| `descripcion` | TEXT | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |

**Reglas de negocio:**
- Un empleado indefinido tiene `fecha_fin = NULL` y `estado = 'activo'`.
- Un practicante tiene ambas fechas. Al vencer `fecha_fin`, el sistema puede cerrar el período automáticamente.
- Un período `cerrado` es de solo lectura. Sus asistencias no se modifican.
- Para saber si un período está activo en una fecha: `fecha_inicio <= :fecha AND (fecha_fin IS NULL OR fecha_fin >= :fecha) AND estado = 'activo'`.

---

### Bloque 5: Horarios

El modelo de horarios es el más complejo del sistema. Soporta tres casos de uso:

1. **Horario fijo permanente** — Un empleado con el mismo horario indefinidamente.
2. **Cambio de horario** — Le cambiaron la entrada de 7:00 a 8:00 a partir del 1 de marzo.
3. **Rotación cíclica** — Semana A trabaja L-V normal, semana B trabaja L-J + sábado.

---

#### `plantillas_horario`

Define la estructura de un horario. Reutilizable por N personas.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK DEFAULT gen_random_uuid() | |
| `nombre` | TEXT NOT NULL | "Normal L-V 7-16", "Turno A Rotativo", "Médico Guardia" |
| `descripcion` | TEXT | |
| `lunes` | TIME NULLABLE | Hora de entrada. NULL = no trabaja ese día. |
| `martes` | TIME NULLABLE | |
| `miercoles` | TIME NULLABLE | |
| `jueves` | TIME NULLABLE | |
| `viernes` | TIME NULLABLE | |
| `sabado` | TIME NULLABLE | |
| `domingo` | TIME NULLABLE | |
| `lunes_salida` | TIME NULLABLE | |
| `martes_salida` | TIME NULLABLE | |
| `miercoles_salida` | TIME NULLABLE | |
| `jueves_salida` | TIME NULLABLE | |
| `viernes_salida` | TIME NULLABLE | |
| `sabado_salida` | TIME NULLABLE | |
| `domingo_salida` | TIME NULLABLE | |
| `almuerzo_min` | INTEGER DEFAULT 0 | Tiempo de almuerzo general en minutos |
| `lunes_almuerzo_min` | INTEGER NULLABLE | Almuerzo específico por día |
| `martes_almuerzo_min` | INTEGER NULLABLE | |
| `miercoles_almuerzo_min` | INTEGER NULLABLE | |
| `jueves_almuerzo_min` | INTEGER NULLABLE | |
| `viernes_almuerzo_min` | INTEGER NULLABLE | |
| `sabado_almuerzo_min` | INTEGER NULLABLE | |
| `domingo_almuerzo_min` | INTEGER NULLABLE | |
| `horas_semana` | NUMERIC(5,2) NULLABLE | Horas contrato por semana |
| `horas_mes` | NUMERIC(5,2) NULLABLE | Horas contrato por mes |
| `activo` | BOOLEAN DEFAULT true | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |

**Ventaja de reutilización:** Si 30 empleados tienen el horario "Normal L-V 7-16" y cambia a "Normal L-V 8-17", se actualiza una sola plantilla y todas las asignaciones vigentes reflejan el cambio automáticamente. Si el cambio es solo para algunos, se crea una nueva plantilla y se reasigna.

---

#### `config_ciclo_horario`

Ancla temporal para rotaciones cíclicas. Define a partir de qué fecha empieza el ciclo.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK DEFAULT gen_random_uuid() | |
| `nombre` | TEXT NOT NULL | "Ciclo Rotativo Personal Salud 2026" |
| `fecha_referencia` | DATE NOT NULL | La fecha que corresponde a la semana 1, posición 1 del ciclo |
| `ciclo_semanas` | INTEGER NOT NULL | Cuántas semanas dura el ciclo completo |
| `descripcion` | TEXT | |
| `activo` | BOOLEAN DEFAULT true | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |

---

#### `asignaciones_horario`

Vincula una plantilla a una persona con vigencia y patrón de ciclo. Es la tabla que responde "¿qué horario tiene esta persona hoy?".

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | UUID PK DEFAULT gen_random_uuid() | |
| `persona_id` | UUID FK `personas(id)` NOT NULL | |
| `plantilla_id` | UUID FK `plantillas_horario(id)` NOT NULL | |
| `fecha_inicio` | DATE NOT NULL | Desde cuándo aplica esta asignación |
| `fecha_fin` | DATE NULLABLE | Hasta cuándo. NULL = vigente indefinidamente |
| `ciclo_semanas` | INTEGER DEFAULT 1 | 1 = siempre aplica. 2+ = rotación |
| `posicion_ciclo` | INTEGER DEFAULT 1 | Qué semana del ciclo ocupa esta plantilla (1 a ciclo_semanas) |
| `config_ciclo_id` | UUID FK `config_ciclo_horario(id)` NULLABLE | NULL si ciclo_semanas = 1 |
| `notas` | TEXT | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |
| UNIQUE | `(persona_id, plantilla_id, fecha_inicio, posicion_ciclo)` | |

**Ejemplos de uso:**

*Caso 1 — Horario fijo permanente (empleado normal):*
```
asignaciones_horario:
  persona_id = María García
  plantilla_id = "Normal L-V 7-16"
  fecha_inicio = 2024-01-01
  fecha_fin = NULL
  ciclo_semanas = 1
  posicion_ciclo = 1
```

*Caso 2 — Cambio de horario en una fecha:*
```
-- Cierra la asignación anterior
UPDATE asignaciones_horario SET fecha_fin = '2026-02-28'
WHERE persona_id = María AND plantilla_id = "Normal L-V 7-16"

-- Crea la nueva asignación
INSERT: fecha_inicio = '2026-03-01', plantilla = "Normal L-V 8-17"
```

*Caso 3 — Rotación de 3 semanas (enfermera):*
```
asignaciones_horario (3 filas para la misma persona):
  row 1: plantilla="Turno Mañana", ciclo=3, posicion=1, config_ciclo_id=X
  row 2: plantilla="Turno Tarde",  ciclo=3, posicion=2, config_ciclo_id=X
  row 3: plantilla="Guardia Fin",  ciclo=3, posicion=3, config_ciclo_id=X
```

Ver **Apéndice B** para el algoritmo completo de resolución de horario activo.

---

### Bloque 6: Asistencias y seguimiento

---

#### `asistencias`

Registros de marcación. Una sola tabla para todos los tipos de persona. **Nunca se eliminan registros.**

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `persona_id` | UUID FK `personas(id)` NOT NULL | |
| `periodo_vigencia_id` | UUID FK `periodos_vigencia(id)` NULLABLE | NULL si la persona marcó fuera de cualquier período activo |
| `fecha_hora` | TIMESTAMPTZ NOT NULL | Momento exacto de la marcación |
| `punch_raw` | INTEGER | Valor crudo del dispositivo (0=entrada, 1=salida) |
| `tipo` | TEXT NOT NULL | `'entrada'` o `'salida'` |
| `fuente` | TEXT DEFAULT `'zk'` | `'zk'`, `'manual'`, `'csv'` |
| `dispositivo_id` | UUID FK `dispositivos(id)` NULLABLE | NULL = registros migrados del sistema anterior |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |
| UNIQUE | `(persona_id, fecha_hora)` | Evita duplicados |

**Índices recomendados:**
```sql
CREATE INDEX ON asistencias (persona_id, fecha_hora);
CREATE INDEX ON asistencias (periodo_vigencia_id) WHERE periodo_vigencia_id IS NOT NULL;
```

---

#### `justificaciones`

Sin cambios funcionales respecto al sistema actual. Solo cambia `id_usuario TEXT` → `persona_id UUID`.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `persona_id` | UUID FK `personas(id)` NOT NULL | ← antes era `id_usuario TEXT` |
| `fecha` | DATE NOT NULL | |
| `tipo` | TEXT NOT NULL | `'tardanza'`, `'ausencia'`, `'almuerzo'`, `'incompleto'`, `'salida_anticipada'`, `'permiso'` |
| `motivo` | TEXT | |
| `aprobado_por` | TEXT | |
| `hora_permitida` | TIME NULLABLE | |
| `hora_retorno_permiso` | TIME NULLABLE | |
| `estado` | TEXT DEFAULT `'aprobada'` | `'aprobada'`, `'rechazada'`, `'pendiente'` |
| `duracion_permitida_min` | INTEGER NULLABLE | |
| `incluye_almuerzo` | BOOLEAN DEFAULT false | |
| `recuperable` | BOOLEAN DEFAULT false | |
| `fecha_recuperacion` | DATE NULLABLE | |
| `hora_recuperacion` | TIME NULLABLE | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |
| UNIQUE | `(persona_id, fecha, tipo)` | |

---

#### `breaks_categorizados`

Sin cambios funcionales. Solo cambia `id_usuario TEXT` → `persona_id UUID`.

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `persona_id` | UUID FK `personas(id)` NOT NULL | ← antes era `id_usuario TEXT` |
| `fecha` | DATE NOT NULL | |
| `hora_inicio` | TIME NOT NULL | |
| `hora_fin` | TIME NOT NULL | |
| `duracion_min` | INTEGER | |
| `categoria` | TEXT NOT NULL CHECK(categoria IN ('almuerzo','permiso','injustificado')) | |
| `motivo` | TEXT | |
| `aprobado_por` | TEXT | |
| `creado_en` | TIMESTAMPTZ DEFAULT NOW() | |
| UNIQUE | `(persona_id, fecha, hora_inicio)` | |

---

## 8. Capa de abstracción SQLAlchemy

### 8.1 Principio de diseño

El contrato con el resto del sistema es simple: las funciones públicas de `db.py` mantienen exactamente la misma firma de entrada y salida que tienen hoy. La diferencia es interna.

**Funciones que deben mantener compatibilidad exacta:**

```python
# Asistencias
insertar_asistencias(registros)           # registros tiene id_usuario + nombre
consultar_asistencias(fecha_inicio, fecha_fin)  # retorna id_usuario, nombre, datetime, fecha, hora, tipo
get_personas(fecha_inicio, fecha_fin)     # retorna lista de nombres
get_personas_con_id(fecha_inicio, fin)    # retorna [{id_usuario, nombre}]
get_estado()                              # retorna {total_registros, personas_en_db, ultima_sync}

# Usuarios ZK
upsert_usuarios(usuarios)
get_ids_usuarios_zk()

# Horarios
upsert_horarios(horarios, fuente)
upsert_horario(horario, fuente)
get_horarios()                            # retorna {by_id: {...}, by_nombre: {...}}
get_horario(id_usuario)
delete_horario(id_usuario)
get_estado_horarios()

# Sync
registrar_sync(fecha_inicio, fecha_fin, obtenidos, nuevos, exito, error, en_dispositivo)

# Justificaciones (todas las funciones existentes)
insertar_justificacion(...)
get_justificaciones(fecha_inicio, fecha_fin)
get_justificaciones_dict(fecha_inicio, fecha_fin)
get_justificaciones_pendientes()
actualizar_estado_justificacion(id, estado)
eliminar_justificacion(id)
get_justificacion_by_id(id)
actualizar_justificacion_completa(id, **campos)

# Breaks
get_breaks_categorizados_dict(fecha_inicio, fecha_fin)
insertar_break_categorizado(id_usuario, fecha, hora_inicio, hora_fin, categoria, motivo, aprobado_por)

# Feriados (todas las funciones existentes)
insertar_feriado(fecha, descripcion, tipo)
get_feriados(fecha_inicio, fecha_fin)
get_feriados_set(fecha_inicio, fecha_fin)
eliminar_feriado(fecha)
importar_feriados_csv(filepath)
```

### 8.2 La traducción interna clave

Las funciones que reciben o retornan `id_usuario` hacen el lookup a través de `personas_dispositivos`:

```python
# En db/queries/personas.py

def resolver_persona_id(conn, id_usuario: str, dispositivo_id: str = None) -> tuple[str, str]:
    """
    Dado un id_usuario del ZK, retorna (persona_id UUID, nombre).
    Si la persona no existe aún, la crea automáticamente.
    """
    row = conn.execute("""
        SELECT p.id, p.nombre
        FROM personas p
        JOIN personas_dispositivos pd ON pd.persona_id = p.id
        WHERE pd.id_en_dispositivo = :id_usuario
          AND (:dispositivo_id IS NULL OR pd.dispositivo_id = :dispositivo_id::uuid)
          AND pd.activo = true
        LIMIT 1
    """, {"id_usuario": id_usuario, "dispositivo_id": dispositivo_id}).fetchone()

    if row:
        return str(row["id"]), row["nombre"]

    # Auto-crear si no existe
    return _crear_persona_desde_zk(conn, id_usuario)


def id_usuario_from_persona(conn, persona_id: str, dispositivo_id: str = None) -> str:
    """
    Dado un persona_id UUID, retorna el id_usuario TEXT del ZK.
    Necesario para mantener compatibilidad en las funciones que retornan id_usuario.
    """
    row = conn.execute("""
        SELECT id_en_dispositivo FROM personas_dispositivos
        WHERE persona_id = :persona_id::uuid
          AND (:dispositivo_id IS NULL OR dispositivo_id = :dispositivo_id::uuid)
          AND es_principal = true
        LIMIT 1
    """, {"persona_id": persona_id, "dispositivo_id": dispositivo_id}).fetchone()
    return row["id_en_dispositivo"] if row else persona_id
```

### 8.3 Schema switching

```python
# db/connection.py

from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import os

_engine = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            os.environ["DATABASE_URL"],
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=2,
            pool_timeout=30,
            pool_pre_ping=True,
        )
    return _engine

def get_tenant_schema() -> str:
    """
    Fase 1: retorna siempre TENANT_DEFAULT.
    Fase 2+: leerá g.tenant_schema del contexto Flask.
    """
    try:
        from flask import g
        return getattr(g, "tenant_schema", os.environ.get("TENANT_DEFAULT", "public"))
    except RuntimeError:
        return os.environ.get("TENANT_DEFAULT", "public")

@contextmanager
def get_connection(schema: str = None):
    schema = schema or get_tenant_schema()
    with get_engine().connect() as conn:
        conn.execute(text(f"SET search_path TO {schema}, public"))
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
```

---

## 9. Gestión de migraciones con Alembic

### 9.1 Por qué reemplaza `_migrar_columna()`

El `db.py` actual tiene 15 llamadas a `_migrar_columna()` hardcodeadas en `init_db()`. Esto funcionó para columnas simples pero no puede manejar:
- Cambiar tipos de datos
- Renombrar columnas o tablas
- Crear o eliminar índices
- Revertir cambios
- Historial auditable de qué cambió cuándo

Alembic resuelve todo esto con archivos versionados y operaciones `upgrade()` / `downgrade()`.

### 9.2 Migraciones por schema de tenant

`db/migrations/env.py` se configura para iterar sobre todos los tenants activos y aplicar cada migración en cada schema. Al agregar un nuevo tenant, `alembic upgrade head` sincroniza su schema automáticamente.

### 9.3 Estructura de versiones

```
0001_initial_schema.py     ← Todo el schema de la Fase 1
0002_auth_usuarios.py      ← Fase 2: campos de auth
0003_grupos_v2.py          ← Futura: si se necesita cambio en grupos
```

---

## 10. Pasos de implementación

---

### Paso 1 — Preparar entorno Docker con PostgreSQL

**Qué se hace:**
- Actualizar `docker-compose.yml` con el servicio `db` (postgres:16) y su volumen persistente
- Agregar healthcheck para que Flask espere a PostgreSQL
- Actualizar `.env.example` con las nuevas variables
- Actualizar `.env` local con los valores reales

**Criterio de verificación:**
- `docker-compose up -d db` levanta sin errores
- `docker exec -it <container_db> psql -U asistencias_user -d asistencias_db -c "SELECT version();"` retorna la versión de PostgreSQL
- El volumen `postgres_data` persiste al reiniciar

---

### Paso 2 — Instalar dependencias Python

**Qué se hace:**
- Agregar `sqlalchemy`, `psycopg2-binary`, `alembic`, `cryptography` al `requirements.txt`
- Verificar instalación en el entorno virtual

**Criterio de verificación:**
- `python -c "import sqlalchemy, alembic, psycopg2, cryptography; print('OK')"` sin errores

---

### Paso 3 — Inicializar Alembic y crear migración inicial

**Qué se hace:**
- `alembic init db/migrations`
- Configurar `env.py` para usar `DATABASE_URL` y soportar schema-por-tenant
- Crear `0001_initial_schema.py` con todas las tablas del schema `public` y del schema `istpet`

**Criterio de verificación:**
- `alembic upgrade head` ejecuta sin errores
- `\dt public.*` muestra: `tenants`, `usuarios`, `audit_log`, `login_intentos`
- `\dt istpet.*` muestra todas las tablas del Bloque 1 al 6
- `alembic current` muestra `0001_initial_schema (head)`

---

### Paso 4 — Crear `db/connection.py`

**Qué se hace:**
- Implementar el engine SQLAlchemy con pool de conexiones
- Implementar `get_connection(schema)` con `search_path`
- Implementar `get_tenant_schema()` que en Fase 1 retorna `TENANT_DEFAULT`

**Criterio de verificación:**
- `from db.connection import get_connection` no lanza errores
- Una query `SELECT 1` con `get_connection('istpet')` retorna resultado

---

### Paso 5 — Implementar `db/queries/personas.py`

Este módulo es el núcleo del cambio. Implementa la traducción `id_usuario ↔ persona_id`.

**Qué se hace:**
- Implementar `resolver_persona_id(conn, id_usuario, dispositivo_id)`
- Implementar `id_usuario_from_persona(conn, persona_id)`
- Implementar `_crear_persona_desde_zk(conn, id_usuario, nombre)` para auto-crear personas desconocidas
- Implementar `upsert_usuarios(usuarios)` que además de `usuarios_zk` actualiza `personas_dispositivos`

**Criterio de verificación:**
- Dado un `id_usuario` conocido, `resolver_persona_id` retorna el UUID correcto
- Dado un `id_usuario` desconocido, crea la persona y retorna su nuevo UUID
- `upsert_usuarios([{"id_usuario": "42", "nombre": "TEST"}])` crea entradas en `usuarios_zk` y `personas_dispositivos`

---

### Paso 6 — Implementar `db/queries/asistencias.py`

**Qué se hace:**
- `insertar_asistencias(registros)`: usa `resolver_persona_id` internamente, inserta con `persona_id`
- `consultar_asistencias(inicio, fin)`: retorna con `id_usuario` y `nombre` (compatibilidad)
- `get_personas(inicio, fin)`: igual que hoy
- `get_personas_con_id(inicio, fin)`: retorna `id_usuario` del ZK (via `personas_dispositivos`)
- `get_estado()`: igual que hoy

**Criterio de verificación por función:**

| Función | Verificación |
|---|---|
| `insertar_asistencias()` | Inserta con persona_id. Respeta UNIQUE. Retorna conteo correcto. |
| `consultar_asistencias()` | Retorna registros con los 6 campos que espera `script.py`. |
| `get_personas()` | Retorna lista de nombres únicos del rango. |
| `get_personas_con_id()` | Retorna `[{id_usuario, nombre}]` con el id del ZK. |
| `get_estado()` | Retorna dict con `total_registros`, `personas_en_db`, `ultima_sync`. |

---

### Paso 7 — Implementar `db/queries/horarios.py`

Este módulo es el más complejo de la capa de compatibilidad. Debe construir el dict `{by_id, by_nombre}` resolviendo la plantilla activa para cada persona.

**Qué se hace:**
- `upsert_horarios(horarios, fuente)`: crea/actualiza `plantillas_horario` y `asignaciones_horario`
- `get_horarios()`: resuelve plantilla activa por persona y retorna `{by_id, by_nombre}` idéntico al sistema actual
- `get_horario(id_usuario)`: igual para una persona
- `delete_horario(id_usuario)`: cierra la asignación activa (no borra la plantilla)
- `get_estado_horarios()`: igual que hoy

**Lógica de `upsert_horarios` en Fase 1:**
Durante la Fase 1, cada horario del CSV se trata como `ciclo_semanas=1, posicion_ciclo=1` (sin rotación). Se crea o actualiza la plantilla y se crea/mantiene la asignación activa. El soporte de rotaciones se configura manualmente desde la UI en fases posteriores.

**Criterio de verificación:**
- `get_horarios()` retorna exactamente `{by_id: {...}, by_nombre: {...}}`
- Los valores en `by_id[id_usuario]` tienen las mismas claves que retorna el sistema SQLite actual
- `get_horario('42')` retorna el mismo formato que hoy

---

### Paso 8 — Implementar el resto de módulos de queries

**Qué se hace:**
- `db/queries/justificaciones.py`: todas las funciones de justificaciones, usando `persona_id` internamente y traduciendo `id_usuario` en la interfaz
- `db/queries/breaks.py`: ídem para breaks
- `db/queries/feriados.py`: igual que hoy, sin cambios conceptuales
- `db/queries/sync_log.py`: `registrar_sync()` con el nuevo campo `dispositivo_id`

**Criterio de verificación:**
- `insertar_justificacion(id_usuario='42', ...)` resuelve a `persona_id` y guarda correctamente
- `get_justificaciones_dict()` retorna indexado por `(id_usuario, fecha, tipo)` como hoy
- `get_breaks_categorizados_dict()` retorna la misma estructura anidada que hoy

---

### Paso 9 — Crear `db/__init__.py` y wrapper `db.py`

**Qué se hace:**
- `db/__init__.py` importa y re-exporta todas las funciones públicas de los módulos de queries
- `db.py` en la raíz pasa a ser: `from db import *`

**Criterio de verificación:**
- `from db import insertar_asistencias, get_horarios, insertar_justificacion` funciona sin errores
- `import db; db.get_estado()` retorna el dict correcto

---

### Paso 10 — Verificar flujo completo end-to-end

**Qué se hace:**
- Levantar la app completa con `docker-compose up`
- Ejecutar una sincronización manual con el dispositivo ZK
- Generar un PDF de informe para el rango de fechas sincronizado

**Criterio de verificación:**
- La sync completa sin errores
- `sync_log` registra el resultado con `dispositivo_id` correcto
- El PDF generado es idéntico en contenido al del sistema SQLite (mismas personas, mismos días, mismas tardanzas)
- No hay errores en los logs de Flask

---

### Paso 11 — Cargar datos de referencia iniciales

**Qué se hace:**
- Crear tenant `istpet` en `public.tenants`
- Crear sede principal en `istpet.sedes`
- Crear tipos de persona iniciales: `empleado`, `practicante`
- Cargar feriados nacionales de Ecuador para 2025 y 2026
- Crear grupos base de ISTPET (departamentos y áreas)
- Crear categorías base (cargos)

**Criterio de verificación:**
- `SELECT * FROM public.tenants;` muestra el registro de ISTPET
- `SELECT * FROM istpet.tipos_persona;` muestra al menos `empleado` y `practicante`
- `SELECT count(*) FROM istpet.feriados;` muestra los feriados cargados

---

### Paso 12 — Reimportar horarios desde CSV

**Qué se hace:**
- Usar `upsert_horarios()` para cargar el CSV exportado del sistema SQLite
- Verificar que todos los horarios quedaron cargados en `plantillas_horario` y `asignaciones_horario`

**Criterio de verificación:**
- `get_horarios()` retorna los mismos horarios que estaban en el sistema SQLite
- Generar un PDF con horarios activos produce resultados idénticos al sistema anterior

---

## 11. Reimportación de horarios

El CSV del sistema SQLite tiene los horarios en el formato que produce `horarios.py`. La reimportación usa `upsert_horarios()` directamente o la ruta `POST /cargar-horarios`.

**Mapeo del CSV al nuevo modelo:**

Cada fila del CSV genera:
1. Una `plantillas_horario` con todos los campos de horario (o actualiza si el nombre ya existe)
2. Una `asignaciones_horario` con `fecha_inicio = 2024-01-01` (o la fecha más antigua conocida), `fecha_fin = NULL`, `ciclo_semanas = 1`
3. Una entrada en `personas_dispositivos` si `id_usuario` no tiene persona vinculada

**Antes de reimportar, verificar:**
- Que todos los `id_usuario` del CSV coinciden con los IDs que el ZK reportará en la próxima sync
- Que los nombres coinciden con los del ZK (para el fallback `by_nombre`)

---

## 12. Criterio de finalización

La Fase 1 está completa cuando:

- [ ] PostgreSQL corre como servicio Docker con volumen persistente
- [ ] `alembic upgrade head` aplica el schema completo sin errores
- [ ] `\dt istpet.*` muestra las 18 tablas del schema horizontal
- [ ] Todas las funciones públicas de `db.py` funcionan con la misma firma que el sistema SQLite
- [ ] El flujo completo funciona: sync ZK → registros en PostgreSQL → PDF generado correctamente
- [ ] Los horarios están reimportados y los PDFs producen resultados idénticos al sistema anterior
- [ ] Los datos de referencia iniciales están cargados (tenant, sede, tipos de persona, feriados)
- [ ] El sistema puede reiniciarse completamente (`docker-compose down + up`) sin pérdida de datos
- [ ] `alembic current` muestra `(head)` — sin migraciones pendientes
- [ ] No hay ninguna referencia a `modulo_rrhh` ni `modulo_alumnos` en ninguna tabla

**Una vez completados estos criterios, el sistema está listo para la Fase 2 (Autenticación y Roles).**

---

## Apéndice A: Diferencias SQLite → PostgreSQL

| Concepto | SQLite (actual) | PostgreSQL (nuevo) |
|---|---|---|
| Placeholder | `?` | `%s` (psycopg2) o `:param` (SQLAlchemy) |
| PK autoincremental | `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL PRIMARY KEY` |
| PK UUID | No nativo (TEXT) | `UUID DEFAULT gen_random_uuid()` |
| Fecha/hora | `TEXT` en formato ISO | `TIMESTAMPTZ` |
| Hora | `TEXT` en formato HH:MM | `TIME` nativo |
| Fecha actual | `datetime('now')` | `NOW()` |
| Booleano | `INTEGER` (0/1) | `BOOLEAN` nativo |
| Insertar ignorando duplicado | `INSERT OR IGNORE` | `INSERT ... ON CONFLICT DO NOTHING` |
| Upsert | `INSERT OR REPLACE` | `INSERT ... ON CONFLICT DO UPDATE SET ...` |
| Formato de fecha | `strftime('%Y-%m-%d', col)` | `TO_CHAR(col, 'YYYY-MM-DD')` |
| Array | No nativo | `TEXT[]`, `UUID[]` |
| JSON flexible | No nativo | `JSONB` (indexable) |
| Semanas transcurridas | Cálculo manual | `EXTRACT(WEEK FROM date)` |

---

## Apéndice B: Resolución de horario activo

Este algoritmo responde la pregunta central del motor de análisis: **¿qué horario tiene esta persona en esta fecha?**

### Caso simple (sin rotación)

```sql
SELECT ph.*
FROM plantillas_horario ph
JOIN asignaciones_horario ah ON ah.plantilla_id = ph.id
WHERE ah.persona_id = :persona_id::uuid
  AND ah.ciclo_semanas = 1
  AND ah.fecha_inicio <= :fecha
  AND (ah.fecha_fin IS NULL OR ah.fecha_fin >= :fecha)
ORDER BY ah.fecha_inicio DESC
LIMIT 1
```

### Caso con rotación cíclica

```sql
-- Paso 1: obtener la configuración del ciclo
SELECT cch.fecha_referencia, ah.ciclo_semanas
FROM asignaciones_horario ah
JOIN config_ciclo_horario cch ON cch.id = ah.config_ciclo_id
WHERE ah.persona_id = :persona_id::uuid
  AND ah.ciclo_semanas > 1
  AND ah.fecha_inicio <= :fecha
  AND (ah.fecha_fin IS NULL OR ah.fecha_fin >= :fecha)
LIMIT 1;

-- Paso 2: calcular la posición actual en el ciclo
-- semanas_desde_referencia = FLOOR((:fecha - fecha_referencia) / 7)
-- posicion_actual = (semanas_desde_referencia % ciclo_semanas) + 1

-- Paso 3: obtener la plantilla para esa posición
SELECT ph.*
FROM plantillas_horario ph
JOIN asignaciones_horario ah ON ah.plantilla_id = ph.id
WHERE ah.persona_id = :persona_id::uuid
  AND ah.posicion_ciclo = :posicion_actual
  AND ah.fecha_inicio <= :fecha
  AND (ah.fecha_fin IS NULL OR ah.fecha_fin >= :fecha)
LIMIT 1;
```

### Implementación Python en `db/queries/horarios.py`

```python
def get_horario_en_fecha(conn, persona_id: str, fecha: date) -> dict | None:
    """
    Retorna el horario activo de una persona en una fecha específica.
    Maneja tanto horarios fijos como rotaciones cíclicas.
    """
    # Primero intenta horario fijo (ciclo_semanas = 1)
    row = conn.execute("""
        SELECT ph.*
        FROM plantillas_horario ph
        JOIN asignaciones_horario ah ON ah.plantilla_id = ph.id
        WHERE ah.persona_id = :persona_id::uuid
          AND ah.ciclo_semanas = 1
          AND ah.fecha_inicio <= :fecha
          AND (ah.fecha_fin IS NULL OR ah.fecha_fin >= :fecha)
        ORDER BY ah.fecha_inicio DESC
        LIMIT 1
    """, {"persona_id": persona_id, "fecha": fecha}).fetchone()

    if row:
        return dict(row)

    # Si no tiene fijo, busca rotación
    ciclo_row = conn.execute("""
        SELECT cch.fecha_referencia, ah.ciclo_semanas
        FROM asignaciones_horario ah
        JOIN config_ciclo_horario cch ON cch.id = ah.config_ciclo_id
        WHERE ah.persona_id = :persona_id::uuid
          AND ah.ciclo_semanas > 1
          AND ah.fecha_inicio <= :fecha
          AND (ah.fecha_fin IS NULL OR ah.fecha_fin >= :fecha)
        LIMIT 1
    """, {"persona_id": persona_id, "fecha": fecha}).fetchone()

    if not ciclo_row:
        return None

    from datetime import date as _date
    ref = ciclo_row["fecha_referencia"]
    semanas = (fecha - ref).days // 7
    posicion = (semanas % ciclo_row["ciclo_semanas"]) + 1

    row = conn.execute("""
        SELECT ph.*
        FROM plantillas_horario ph
        JOIN asignaciones_horario ah ON ah.plantilla_id = ph.id
        WHERE ah.persona_id = :persona_id::uuid
          AND ah.posicion_ciclo = :posicion
          AND ah.fecha_inicio <= :fecha
          AND (ah.fecha_fin IS NULL OR ah.fecha_fin >= :fecha)
        LIMIT 1
    """, {"persona_id": persona_id, "posicion": posicion, "fecha": fecha}).fetchone()

    return dict(row) if row else None
```

### Formato de retorno (compatible con `script.py`)

La función `get_horarios()` construye el dict `{by_id, by_nombre}` llamando a `get_horario_en_fecha()` para cada persona con la fecha actual. El dict retornado tiene exactamente las mismas claves que el sistema SQLite:

```python
{
    "by_id": {
        "00042": {
            "id_usuario": "00042",
            "nombre": "JUAN PEREZ",
            "lunes": "07:00", "lunes_salida": "16:00",
            "martes": "07:00", "martes_salida": "16:00",
            # ... resto de días
            "almuerzo_min": 60,
            "horas_semana": 40.0,
            "horas_mes": None,
            # ... etc
        }
    },
    "by_nombre": {
        "JUAN PEREZ": { ... }  # mismo objeto
    }
}
```

`script.py` nunca sabe que por debajo existen plantillas, asignaciones ni ciclos.
