"""
DDL completo para el schema de PostgreSQL.
Aplicado por init_db() con CREATE TABLE IF NOT EXISTS (idempotente).

Schema público (global):
  tenants, usuarios, audit_log, login_intentos

Schema tenant (istpet por defecto):
  Infraestructura: sedes, dispositivos, sync_log, feriados
  Config:          tipos_persona, grupos, categorias
  Personas:        usuarios_zk, personas, personas_dispositivos
  Vigencia:        periodos_vigencia
  Horarios:        config_ciclo_horario, plantillas_horario, asignaciones_horario
  Asistencias:     asistencias, justificaciones, breaks_categorizados
"""

PUBLIC_DDL = """
-- Extensión para gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── Tenants ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.tenants (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    slug          TEXT        UNIQUE NOT NULL,
    nombre        TEXT        NOT NULL,
    nombre_corto  TEXT,
    zona_horaria  TEXT        NOT NULL DEFAULT 'America/Guayaquil',
    activo        BOOLEAN     NOT NULL DEFAULT true,
    configuracion JSONB       NOT NULL DEFAULT '{}',
    creado_en     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Usuarios de la app ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.usuarios (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID        REFERENCES public.tenants(id) ON DELETE SET NULL,
    email         TEXT        UNIQUE NOT NULL,
    password_hash TEXT        NOT NULL,
    nombre        TEXT        NOT NULL,
    roles         TEXT[]      NOT NULL DEFAULT '{}',
    activo        BOOLEAN     NOT NULL DEFAULT true,
    ultimo_acceso TIMESTAMPTZ,
    creado_por    UUID        REFERENCES public.usuarios(id) ON DELETE SET NULL,
    creado_en     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Audit log ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.audit_log (
    id          BIGSERIAL   PRIMARY KEY,
    tenant_id   UUID        REFERENCES public.tenants(id) ON DELETE SET NULL,
    usuario_id  UUID        REFERENCES public.usuarios(id) ON DELETE SET NULL,
    accion      TEXT        NOT NULL,
    entidad     TEXT,
    entidad_id  TEXT,
    detalle     JSONB,
    ip          TEXT,
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Rate limiting de login ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.login_intentos (
    id         BIGSERIAL   PRIMARY KEY,
    ip         TEXT        NOT NULL,
    email      TEXT,
    exitoso    BOOLEAN     NOT NULL,
    creado_en  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def get_tenant_ddl(schema: str) -> str:
    """Retorna el DDL completo para un schema de tenant dado."""
    # Usar format con doble {{ }} para las llaves literales de PostgreSQL
    return f"""
-- ── Schema del tenant ─────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS {schema};
SET search_path TO {schema}, public;

-- ╔══════════════════════════════════════════════════╗
-- ║  BLOQUE 1: INFRAESTRUCTURA                       ║
-- ╚══════════════════════════════════════════════════╝

CREATE TABLE IF NOT EXISTS sedes (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre     TEXT        NOT NULL,
    direccion  TEXT,
    activa     BOOLEAN     NOT NULL DEFAULT true,
    creado_en  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dispositivos (
    id                       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre                   TEXT        NOT NULL,
    ip                       TEXT        NOT NULL,
    puerto                   INTEGER     NOT NULL DEFAULT 4370,
    password_enc             TEXT,
    tipo_driver              TEXT        NOT NULL DEFAULT 'zk',
    protocolo                TEXT        NOT NULL DEFAULT 'tcp',
    sede_id                  UUID        REFERENCES sedes(id) ON DELETE SET NULL,
    activo                   BOOLEAN     NOT NULL DEFAULT true,
    timeout_seg              INTEGER     NOT NULL DEFAULT 120,
    watermark_ultimo_id      TEXT,
    watermark_ultima_fecha   TIMESTAMPTZ,
    creado_en                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sync_log (
    id                        BIGSERIAL   PRIMARY KEY,
    dispositivo_id            UUID        REFERENCES dispositivos(id) ON DELETE SET NULL,
    fecha_sync                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fecha_inicio_rango        DATE,
    fecha_fin_rango           DATE,
    registros_obtenidos       INTEGER     NOT NULL DEFAULT 0,
    registros_nuevos          INTEGER     NOT NULL DEFAULT 0,
    registros_en_dispositivo  INTEGER     NOT NULL DEFAULT 0,
    exito                     BOOLEAN     NOT NULL,
    error_detalle             TEXT
);

CREATE TABLE IF NOT EXISTS feriados (
    fecha        DATE        PRIMARY KEY,
    descripcion  TEXT        NOT NULL,
    tipo         TEXT        NOT NULL DEFAULT 'nacional'
);

-- ╔══════════════════════════════════════════════════╗
-- ║  BLOQUE 2: CONFIGURACIÓN DEL TENANT              ║
-- ╚══════════════════════════════════════════════════╝

CREATE TABLE IF NOT EXISTS tipos_persona (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre      TEXT        NOT NULL,
    descripcion TEXT,
    color       TEXT,
    icono       TEXT,
    activo      BOOLEAN     NOT NULL DEFAULT true,
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS grupos (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre      TEXT        NOT NULL,
    tipo_grupo  TEXT,
    padre_id    UUID        REFERENCES grupos(id) ON DELETE SET NULL,
    sede_id     UUID        REFERENCES sedes(id) ON DELETE SET NULL,
    activo      BOOLEAN     NOT NULL DEFAULT true,
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS categorias (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre           TEXT        NOT NULL,
    tipo_persona_id  UUID        REFERENCES tipos_persona(id) ON DELETE SET NULL,
    activo           BOOLEAN     NOT NULL DEFAULT true,
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ╔══════════════════════════════════════════════════╗
-- ║  BLOQUE 3: PERSONAS Y VINCULACIÓN BIOMÉTRICA     ║
-- ╚══════════════════════════════════════════════════╝

CREATE TABLE IF NOT EXISTS usuarios_zk (
    id_usuario     TEXT        PRIMARY KEY,
    nombre         TEXT        NOT NULL,
    privilegio     INTEGER,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS personas (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre           TEXT        NOT NULL,
    identificacion   TEXT        UNIQUE,
    tipo_persona_id  UUID        REFERENCES tipos_persona(id) ON DELETE RESTRICT,
    grupo_id         UUID        REFERENCES grupos(id) ON DELETE SET NULL,
    categoria_id     UUID        REFERENCES categorias(id) ON DELETE SET NULL,
    sede_id          UUID        REFERENCES sedes(id) ON DELETE SET NULL,
    email            TEXT,
    telefono         TEXT,
    activo           BOOLEAN     NOT NULL DEFAULT true,
    notas            TEXT,
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS personas_dispositivos (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_id        UUID        NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    dispositivo_id    UUID        NOT NULL REFERENCES dispositivos(id) ON DELETE CASCADE,
    id_en_dispositivo TEXT        NOT NULL,
    es_principal      BOOLEAN     NOT NULL DEFAULT true,
    activo            BOOLEAN     NOT NULL DEFAULT true,
    creado_en         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (dispositivo_id, id_en_dispositivo)
);

-- ╔══════════════════════════════════════════════════╗
-- ║  BLOQUE 4: VIGENCIA                              ║
-- ╚══════════════════════════════════════════════════╝

CREATE TABLE IF NOT EXISTS periodos_vigencia (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_id   UUID        NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    nombre       TEXT        NOT NULL,
    fecha_inicio DATE        NOT NULL,
    fecha_fin    DATE,
    estado       TEXT        NOT NULL DEFAULT 'activo',
    descripcion  TEXT,
    creado_en    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ╔══════════════════════════════════════════════════╗
-- ║  BLOQUE 5: HORARIOS                              ║
-- ╚══════════════════════════════════════════════════╝

CREATE TABLE IF NOT EXISTS config_ciclo_horario (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre           TEXT        NOT NULL,
    fecha_referencia DATE        NOT NULL,
    ciclo_semanas    INTEGER     NOT NULL,
    descripcion      TEXT,
    activo           BOOLEAN     NOT NULL DEFAULT true,
    creado_en        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS plantillas_horario (
    id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre                 TEXT        NOT NULL,
    descripcion            TEXT,
    lunes                  TIME,
    martes                 TIME,
    miercoles              TIME,
    jueves                 TIME,
    viernes                TIME,
    sabado                 TIME,
    domingo                TIME,
    lunes_salida           TIME,
    martes_salida          TIME,
    miercoles_salida       TIME,
    jueves_salida          TIME,
    viernes_salida         TIME,
    sabado_salida          TIME,
    domingo_salida         TIME,
    almuerzo_min           INTEGER     NOT NULL DEFAULT 0,
    lunes_almuerzo_min     INTEGER,
    martes_almuerzo_min    INTEGER,
    miercoles_almuerzo_min INTEGER,
    jueves_almuerzo_min    INTEGER,
    viernes_almuerzo_min   INTEGER,
    sabado_almuerzo_min    INTEGER,
    domingo_almuerzo_min   INTEGER,
    horas_semana           NUMERIC(5,2),
    horas_mes              NUMERIC(5,2),
    activo                 BOOLEAN     NOT NULL DEFAULT true,
    creado_en              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asignaciones_horario (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_id      UUID        NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    plantilla_id    UUID        NOT NULL REFERENCES plantillas_horario(id) ON DELETE RESTRICT,
    fecha_inicio    DATE        NOT NULL,
    fecha_fin       DATE,
    ciclo_semanas   INTEGER     NOT NULL DEFAULT 1,
    posicion_ciclo  INTEGER     NOT NULL DEFAULT 1,
    config_ciclo_id UUID        REFERENCES config_ciclo_horario(id) ON DELETE SET NULL,
    notas           TEXT,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (persona_id, plantilla_id, fecha_inicio, posicion_ciclo)
);

-- ╔══════════════════════════════════════════════════╗
-- ║  BLOQUE 6: ASISTENCIAS Y SEGUIMIENTO             ║
-- ╚══════════════════════════════════════════════════╝

CREATE TABLE IF NOT EXISTS asistencias (
    id                   BIGSERIAL   PRIMARY KEY,
    persona_id           UUID        NOT NULL REFERENCES personas(id) ON DELETE RESTRICT,
    periodo_vigencia_id  UUID        REFERENCES periodos_vigencia(id) ON DELETE SET NULL,
    fecha_hora           TIMESTAMPTZ NOT NULL,
    punch_raw            INTEGER,
    tipo                 TEXT        NOT NULL,
    fuente               TEXT        NOT NULL DEFAULT 'zk',
    dispositivo_id       UUID        REFERENCES dispositivos(id) ON DELETE SET NULL,
    creado_en            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (persona_id, fecha_hora)
);

CREATE INDEX IF NOT EXISTS idx_asistencias_persona_fecha
    ON asistencias (persona_id, fecha_hora);

CREATE INDEX IF NOT EXISTS idx_asistencias_periodo
    ON asistencias (periodo_vigencia_id)
    WHERE periodo_vigencia_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS justificaciones (
    id                     BIGSERIAL   PRIMARY KEY,
    persona_id             UUID        NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    fecha                  DATE        NOT NULL,
    tipo                   TEXT        NOT NULL,
    motivo                 TEXT,
    aprobado_por           TEXT,
    hora_permitida         TIME,
    hora_retorno_permiso   TIME,
    estado                 TEXT        NOT NULL DEFAULT 'aprobada',
    duracion_permitida_min INTEGER,
    incluye_almuerzo       BOOLEAN     NOT NULL DEFAULT false,
    recuperable            BOOLEAN     NOT NULL DEFAULT false,
    fecha_recuperacion     DATE,
    hora_recuperacion      TIME,
    creado_en              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (persona_id, fecha, tipo)
);

CREATE TABLE IF NOT EXISTS breaks_categorizados (
    id           BIGSERIAL   PRIMARY KEY,
    persona_id   UUID        NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    fecha        DATE        NOT NULL,
    hora_inicio  TIME        NOT NULL,
    hora_fin     TIME        NOT NULL,
    duracion_min INTEGER,
    categoria    TEXT        NOT NULL CHECK(categoria IN ('almuerzo','permiso','injustificado')),
    motivo       TEXT,
    aprobado_por TEXT,
    creado_en    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (persona_id, fecha, hora_inicio)
);
"""
