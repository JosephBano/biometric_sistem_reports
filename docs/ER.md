# Modelo Entidad-Relación — Base de Datos Biométrico RRHH

> **Fuente:** `db/schema.py` — Generado automáticamente por `docs/generate_er.py`


## Esquema Público (`public`)

Estas tablas viven en el schema `public` y son compartidas por todos los tenants.

#### `public.tenants`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `slug` | TEXT UNIQUE | UNIQUE, NOT NULL |  |
| `nombre` | TEXT | NOT NULL |  |
| `nombre_corto` | TEXT | — | — |
| `zona_horaria` | TEXT | NOT NULL, DEFAULT 'America/Guayaquil' |  |
| `activo` | BOOLEAN | NOT NULL, DEFAULT true |  |
| `configuracion` | JSONB | NOT NULL, DEFAULT '{}' |  |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `public.usuarios`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `tenant_id` | UUID | FK None ON DELETE None |  |
| `email` | TEXT UNIQUE | UNIQUE, NOT NULL |  |
| `password_hash` | TEXT | NOT NULL |  |
| `nombre` | TEXT | NOT NULL |  |
| `roles` | TEXT[] | NOT NULL, DEFAULT '{}' |  |
| `activo` | BOOLEAN | NOT NULL, DEFAULT true |  |
| `ultimo_acceso` | TIMESTAMPTZ | — | — |
| `configuracion` | JSONB | NOT NULL, DEFAULT '{}' |  |
| `creado_por` | UUID | FK None ON DELETE None |  |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `public.audit_log`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | BIGSERIAL PRIMARY KEY | PK |  |
| `tenant_id` | UUID | FK None ON DELETE None |  |
| `usuario_id` | UUID | FK None ON DELETE None |  |
| `accion` | TEXT | NOT NULL |  |
| `entidad` | TEXT | — | — |
| `entidad_id` | TEXT | — | — |
| `detalle` | JSONB | — | — |
| `ip` | TEXT | — | — |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `public.login_intentos`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | BIGSERIAL PRIMARY KEY | PK |  |
| `ip` | TEXT | NOT NULL |  |
| `email` | TEXT | — | — |
| `exitoso` | BOOLEAN | NOT NULL |  |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `sedes`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `nombre` | TEXT | NOT NULL |  |
| `direccion` | TEXT | — | — |
| `activa` | BOOLEAN | NOT NULL, DEFAULT true |  |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `dispositivos`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `nombre` | TEXT | NOT NULL |  |
| `ip` | TEXT | NOT NULL |  |
| `puerto` | INTEGER | NOT NULL, DEFAULT 4370 |  |
| `password_enc` | TEXT | — | — |
| `tipo_driver` | TEXT | NOT NULL, DEFAULT 'zk' |  |
| `protocolo` | TEXT | NOT NULL, DEFAULT 'tcp' |  |
| `sede_id` | UUID | FK None ON DELETE None |  |
| `activo` | BOOLEAN | NOT NULL, DEFAULT true |  |
| `timeout_seg` | INTEGER | NOT NULL, DEFAULT 120 |  |
| `prioridad` | INTEGER | NOT NULL, DEFAULT 5 |  |
| `watermark_ultimo_id` | TEXT | — | — |
| `watermark_ultima_fecha` | TIMESTAMPTZ | — | — |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `sync_estado`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `dispositivo_id` | UUID PRIMARY KEY | PK, FK None ON DELETE None |  |
| `estado` | TEXT | NOT NULL, DEFAULT 'idle' |  |
| `progreso_pct` | INTEGER | NOT NULL, DEFAULT 0 |  |
| `registros_proc` | INTEGER | NOT NULL, DEFAULT 0 |  |
| `mensaje` | TEXT | — | — |
| `actualizado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `sync_log`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | BIGSERIAL PRIMARY KEY | PK |  |
| `dispositivo_id` | UUID | FK None ON DELETE None |  |
| `fecha_sync` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |
| `fecha_inicio_rango` | DATE | — | — |
| `fecha_fin_rango` | DATE | — | — |
| `registros_obtenidos` | INTEGER | NOT NULL, DEFAULT 0 |  |
| `registros_nuevos` | INTEGER | NOT NULL, DEFAULT 0 |  |
| `registros_en_dispositivo` | INTEGER | NOT NULL, DEFAULT 0 |  |
| `exito` | BOOLEAN | NOT NULL |  |
| `error_detalle` | TEXT | — | — |

#### `feriados`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `fecha` | DATE PRIMARY KEY | PK |  |
| `descripcion` | TEXT | NOT NULL |  |
| `tipo` | TEXT | NOT NULL, DEFAULT 'nacional' |  |

#### `tipos_persona`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `nombre` | TEXT | NOT NULL |  |
| `descripcion` | TEXT | — | — |
| `color` | TEXT | — | — |
| `icono` | TEXT | — | — |
| `activo` | BOOLEAN | NOT NULL, DEFAULT true |  |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `grupos`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `nombre` | TEXT | NOT NULL |  |
| `tipo_grupo` | TEXT | — | — |
| `padre_id` | UUID | FK None ON DELETE None |  |
| `sede_id` | UUID | FK None ON DELETE None |  |
| `activo` | BOOLEAN | NOT NULL, DEFAULT true |  |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `categorias`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `nombre` | TEXT | NOT NULL |  |
| `tipo_persona_id` | UUID | FK None ON DELETE None |  |
| `activo` | BOOLEAN | NOT NULL, DEFAULT true |  |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `usuarios_zk`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id_usuario` | TEXT PRIMARY KEY | PK |  |
| `nombre` | TEXT | NOT NULL |  |
| `privilegio` | INTEGER | — | — |
| `actualizado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `personas`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `nombre` | TEXT | NOT NULL |  |
| `identificacion` | TEXT UNIQUE | UNIQUE |  |
| `tipo_persona_id` | UUID | FK None ON DELETE None |  |
| `grupo_id` | UUID | FK None ON DELETE None |  |
| `categoria_id` | UUID | FK None ON DELETE None |  |
| `sede_id` | UUID | FK None ON DELETE None |  |
| `email` | TEXT | — | — |
| `telefono` | TEXT | — | — |
| `activo` | BOOLEAN | NOT NULL, DEFAULT true |  |
| `notas` | TEXT | — | — |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `personas_dispositivos`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `persona_id` | UUID | FK None ON DELETE None, NOT NULL |  |
| `dispositivo_id` | UUID | FK None ON DELETE None, NOT NULL |  |
| `id_en_dispositivo` | TEXT | NOT NULL |  |
| `es_principal` | BOOLEAN | NOT NULL, DEFAULT true |  |
| `activo` | BOOLEAN | NOT NULL, DEFAULT true |  |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |
| `UNIQUE` | (dispositivo_id, id_en_dispositivo) | — | — |

#### `grupos_periodo`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `nombre` | TEXT | NOT NULL |  |
| `fecha_inicio` | DATE | NOT NULL |  |
| `fecha_fin` | DATE | — | — |
| `descripcion` | TEXT | — | — |
| `estado` | TEXT | NOT NULL, DEFAULT 'activo' |  |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `periodos_vigencia`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `persona_id` | UUID | FK None ON DELETE None, NOT NULL |  |
| `nombre` | TEXT | NOT NULL |  |
| `fecha_inicio` | DATE | NOT NULL |  |
| `fecha_fin` | DATE | — | — |
| `estado` | TEXT | NOT NULL, DEFAULT 'activo' |  |
| `descripcion` | TEXT | — | — |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `config_ciclo_horario`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `nombre` | TEXT | NOT NULL |  |
| `fecha_referencia` | DATE | NOT NULL |  |
| `ciclo_semanas` | INTEGER | NOT NULL |  |
| `descripcion` | TEXT | — | — |
| `activo` | BOOLEAN | NOT NULL, DEFAULT true |  |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `plantillas_horario`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `nombre` | TEXT | NOT NULL |  |
| `descripcion` | TEXT | — | — |
| `lunes` | TIME | — | — |
| `martes` | TIME | — | — |
| `miercoles` | TIME | — | — |
| `jueves` | TIME | — | — |
| `viernes` | TIME | — | — |
| `sabado` | TIME | — | — |
| `domingo` | TIME | — | — |
| `lunes_salida` | TIME | — | — |
| `martes_salida` | TIME | — | — |
| `miercoles_salida` | TIME | — | — |
| `jueves_salida` | TIME | — | — |
| `viernes_salida` | TIME | — | — |
| `sabado_salida` | TIME | — | — |
| `domingo_salida` | TIME | — | — |
| `almuerzo_min` | INTEGER | NOT NULL, DEFAULT 0 |  |
| `lunes_almuerzo_min` | INTEGER | — | — |
| `martes_almuerzo_min` | INTEGER | — | — |
| `miercoles_almuerzo_min` | INTEGER | — | — |
| `jueves_almuerzo_min` | INTEGER | — | — |
| `viernes_almuerzo_min` | INTEGER | — | — |
| `sabado_almuerzo_min` | INTEGER | — | — |
| `domingo_almuerzo_min` | INTEGER | — | — |
| `horas_semana` | NUMERIC(5,2) | — | — |
| `horas_mes` | NUMERIC(5,2) | — | — |
| `activo` | BOOLEAN | NOT NULL, DEFAULT true |  |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |

#### `asignaciones_horario`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | UUID PRIMARY KEY | PK, DEFAULT gen_random_uuid() |  |
| `persona_id` | UUID | FK None ON DELETE None, NOT NULL |  |
| `plantilla_id` | UUID | FK None ON DELETE None, NOT NULL |  |
| `fecha_inicio` | DATE | NOT NULL |  |
| `fecha_fin` | DATE | — | — |
| `ciclo_semanas` | INTEGER | NOT NULL, DEFAULT 1 |  |
| `posicion_ciclo` | INTEGER | NOT NULL, DEFAULT 1 |  |
| `config_ciclo_id` | UUID | FK None ON DELETE None |  |
| `notas` | TEXT | — | — |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |
| `UNIQUE` | (persona_id, plantilla_id, fecha_inicio, posicion_ciclo) | — | — |

#### `asistencias`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | BIGSERIAL PRIMARY KEY | PK |  |
| `persona_id` | UUID | FK None ON DELETE None, NOT NULL |  |
| `periodo_vigencia_id` | UUID | FK None ON DELETE None |  |
| `fecha_hora` | TIMESTAMPTZ | NOT NULL |  |
| `punch_raw` | INTEGER | — | — |
| `tipo` | TEXT | NOT NULL |  |
| `fuente` | TEXT | NOT NULL, DEFAULT 'zk' |  |
| `dispositivo_id` | UUID | FK None ON DELETE None |  |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |
| `UNIQUE` | (persona_id, fecha_hora) | — | — |

#### `justificaciones`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | BIGSERIAL PRIMARY KEY | PK |  |
| `persona_id` | UUID | FK None ON DELETE None, NOT NULL |  |
| `fecha` | DATE | NOT NULL |  |
| `tipo` | TEXT | NOT NULL |  |
| `motivo` | TEXT | — | — |
| `aprobado_por` | TEXT | — | — |
| `hora_permitida` | TIME | — | — |
| `hora_retorno_permiso` | TIME | — | — |
| `estado` | TEXT | NOT NULL, DEFAULT 'aprobada' |  |
| `duracion_permitida_min` | INTEGER | — | — |
| `incluye_almuerzo` | BOOLEAN | NOT NULL, DEFAULT false |  |
| `recuperable` | BOOLEAN | NOT NULL, DEFAULT false |  |
| `fecha_recuperacion` | DATE | — | — |
| `hora_recuperacion` | TIME | — | — |
| `hora_recuperacion_fin` | TIME | — | — |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |
| `UNIQUE` | (persona_id, fecha, tipo) | — | — |

#### `breaks_categorizados`

| Columna | Tipo | Constraints | Descripción |
|---------|------|-------------|-------------|
| `id` | BIGSERIAL PRIMARY KEY | PK |  |
| `persona_id` | UUID | FK None ON DELETE None, NOT NULL |  |
| `fecha` | DATE | NOT NULL |  |
| `hora_inicio` | TIME | NOT NULL |  |
| `hora_fin` | TIME | NOT NULL |  |
| `duracion_min` | INTEGER | — | — |
| `categoria` | TEXT | NOT NULL |  |
| `motivo` | TEXT | — | — |
| `aprobado_por` | TEXT | — | — |
| `creado_en` | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() |  |
| `UNIQUE` | (persona_id, fecha, hora_inicio) | — | — |
