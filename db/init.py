"""
Inicialización de la base de datos PostgreSQL.

init_db() es idempotente: puede llamarse múltiples veces sin efecto adverso.
Crea las tablas si no existen y siembra los datos iniciales del tenant.

Soporta dos modos:
- **Modo legacy** (default): aplica PUBLIC_DDL + get_tenant_ddl con CREATE
  TABLE IF NOT EXISTS. Funciona en cualquier BD vacía.
- **Modo Alembic-aware**: si la tabla `public.alembic_version` existe (BD ya
  migrada con `alembic upgrade head`), salta el DDL y solo siembra los datos
  de referencia. Esto evita duplicar trabajo en producción donde Alembic es
  la fuente de verdad.
"""

import os
import logging
from sqlalchemy import text

from db.connection import get_engine, get_connection, validate_schema_name
from db.schema import PUBLIC_DDL, get_tenant_ddl

log = logging.getLogger(__name__)


def _alembic_applied() -> bool:
    """Detecta si Alembic ya aplicó migraciones (existe `alembic_version`)."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name   = 'alembic_version'
                )
            """)).scalar()
        return bool(row)
    except Exception:
        return False


def init_db():
    """
    1. Si Alembic NO ha migrado, aplica DDL público + tenant (modo legacy).
    2. Si Alembic SÍ ha migrado, salta el DDL (ya existe).
    3. Crea el schema del tenant y sus tablas (si aplica).
    4. Inserta datos de referencia iniciales (idempotente).
    """
    tenant = validate_schema_name(os.environ.get("TENANT_DEFAULT", "istpet"))
    engine = get_engine()
    alembic_done = _alembic_applied()

    with engine.connect() as conn:
        if alembic_done:
            log.info(
                "Alembic ya aplicó migraciones (alembic_version existe). "
                "Saltando DDL legacy."
            )
        else:
            # Schema público
            conn.execute(text(PUBLIC_DDL))
            conn.commit()

            # Schema del tenant por default
            conn.execute(text(get_tenant_ddl(tenant)))
            conn.commit()

            # Obtener todos los tenants activos para aplicar migraciones a cada uno
            tenant_slugs = [r[0] for r in conn.execute(
                text("SELECT slug FROM public.tenants WHERE activo = true")
            ).fetchall()] or [tenant]

            for slug in tenant_slugs:
                validate_schema_name(slug)
                conn.execute(text(f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = '{slug}' AND table_name = 'dispositivos'
                              AND column_name = 'prioridad'
                        ) THEN
                            ALTER TABLE {slug}.dispositivos ADD COLUMN prioridad INTEGER NOT NULL DEFAULT 5;
                        END IF;

                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = '{slug}' AND table_name = 'dispositivos'
                              AND column_name = 'capacidad_max'
                        ) THEN
                            ALTER TABLE {slug}.dispositivos ADD COLUMN capacidad_max INTEGER NOT NULL DEFAULT 100000;
                        END IF;

                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = '{slug}' AND table_name = 'justificaciones'
                              AND column_name = 'hora_recuperacion_fin'
                        ) THEN
                            ALTER TABLE {slug}.justificaciones ADD COLUMN hora_recuperacion_fin TIME;
                        END IF;

                        -- 2026-07-28: renombrar 'categorias' a 'grupos_funcionales'
                        -- y columna 'categoria_id' a 'grupo_funcional_id' en 'personas'.
                        -- Compatible con produccion (idempotente) y con tests
                        -- que usan pgserver (donde Alembic no corre).
                        IF EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema = '{slug}' AND table_name = 'categorias'
                        ) AND NOT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema = '{slug}' AND table_name = 'grupos_funcionales'
                        ) THEN
                            ALTER TABLE {slug}.categorias RENAME TO grupos_funcionales;
                        END IF;

                        IF EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = '{slug}' AND table_name = 'personas'
                              AND column_name = 'categoria_id'
                        ) AND NOT EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = '{slug}' AND table_name = 'personas'
                              AND column_name = 'grupo_funcional_id'
                        ) THEN
                            ALTER TABLE {slug}.personas
                                RENAME COLUMN categoria_id TO grupo_funcional_id;
                        END IF;
                    END $$;
                """))
            conn.commit()

    # Datos de referencia (siempre, incluso si Alembic ya migró)
    _seed_datos_iniciales(tenant)
    log.info("init_db completado para tenant=%s (alembic=%s)", tenant, alembic_done)


def _seed_datos_iniciales(tenant: str):
    """Inserta datos de referencia mínimos si no existen (idempotente)."""
    nombre_inst = os.environ.get("NOMBRE_INSTITUCION", "ISTPET")
    zk_ip = os.environ.get("ZK_IP", "192.168.7.129")
    zk_port = int(os.environ.get("ZK_PORT", "4370"))
    zk_pwd = os.environ.get("ZK_PASSWORD", "")
    zk_proto = "udp" if os.environ.get("ZK_UDP", "false").lower() == "true" else "tcp"
    zk_timeout = int(os.environ.get("ZK_TIMEOUT", "120"))

    # Tenant en public.tenants
    with get_engine().connect() as conn:
        conn.execute(
            text("""
                INSERT INTO public.tenants (slug, nombre, nombre_corto, zona_horaria)
                VALUES (:slug, :nombre, :nombre_corto, 'America/Guayaquil')
                ON CONFLICT (slug) DO NOTHING
            """),
            {"slug": tenant, "nombre": nombre_inst, "nombre_corto": nombre_inst[:20]},
        )
        conn.commit()

        # SUPERADMIN INICIAL desde .env
        sa_email = os.environ.get("INITIAL_SUPERADMIN_EMAIL")
        sa_pass = os.environ.get("INITIAL_SUPERADMIN_PASSWORD")
        if sa_email and sa_pass:
            from auth import hash_password
            import json
            # Verificar si ya existe un usuario
            count = conn.execute(text("SELECT count(*) FROM public.usuarios")).scalar()
            if count == 0:
                 # Obtener id del tenant para vincularlo
                 t_id = conn.execute(text("SELECT id FROM public.tenants WHERE slug = :slug"), {"slug": tenant}).scalar()
                 log.info(f"Creando Superadmin inicial ({sa_email})...")
                 conn.execute(
                     text("""
                         INSERT INTO public.usuarios (tenant_id, email, password_hash, nombre, roles, configuracion)
                         VALUES (:t_id, :email, :pass_hash, :nombre, '{superadmin,admin}', '{}')
                     """),
                     {
                         "t_id": t_id,
                         "email": sa_email.strip().lower(),
                         "pass_hash": hash_password(sa_pass),
                         "nombre": "Administrador Inicial"
                     }
                 )
                 conn.commit()

    # Datos dentro del schema del tenant
    with get_connection(tenant) as conn:
        # Sede principal
        conn.execute(
            text("""
                INSERT INTO sedes (nombre)
                SELECT :nombre
                WHERE NOT EXISTS (SELECT 1 FROM sedes LIMIT 1)
            """),
            {"nombre": f"Sede Principal - {nombre_inst}"},
        )

        # Dispositivo ZK principal
        conn.execute(
            text("""
                INSERT INTO dispositivos (nombre, ip, puerto, protocolo, tipo_driver, timeout_seg)
                SELECT :nombre, :ip, :puerto, :protocolo, 'zk', :timeout
                WHERE NOT EXISTS (SELECT 1 FROM dispositivos LIMIT 1)
            """),
            {
                "nombre": f"ZK - {zk_ip}",
                "ip": zk_ip,
                "puerto": zk_port,
                "protocolo": zk_proto,
                "timeout": zk_timeout,
            },
        )

        # Tipos de persona iniciales
        conn.execute(
            text("""
                INSERT INTO tipos_persona (nombre, descripcion, color)
                SELECT nombre, descripcion, color FROM (VALUES
                    ('Empleado',    'Personal con contrato laboral',     '#2E75B6'),
                    ('Practicante', 'Alumno en período de prácticas',    '#70AD47')
                ) AS v(nombre, descripcion, color)
                WHERE NOT EXISTS (SELECT 1 FROM tipos_persona LIMIT 1)
            """)
        )

        # Feriados nacionales Ecuador 2025
        _insertar_feriados_ecuador(conn)


def _insertar_feriados_ecuador(conn):
    """Inserta feriados nacionales de Ecuador 2025 y 2026 si no hay feriados cargados."""
    existe = conn.execute(text("SELECT COUNT(*) FROM feriados")).fetchone()[0]
    if existe > 0:
        return

    feriados = [
        # 2025
        ("2025-01-01", "Año Nuevo", "nacional"),
        ("2025-02-28", "Carnaval", "nacional"),
        ("2025-03-03", "Carnaval", "nacional"),
        ("2025-04-18", "Viernes Santo", "nacional"),
        ("2025-05-01", "Día del Trabajo", "nacional"),
        ("2025-05-24", "Batalla de Pichincha", "nacional"),
        ("2025-08-10", "Primer Grito de Independencia", "nacional"),
        ("2025-10-09", "Independencia de Guayaquil", "nacional"),
        ("2025-11-02", "Día de los Difuntos", "nacional"),
        ("2025-11-03", "Independencia de Cuenca", "nacional"),
        ("2025-12-25", "Navidad", "nacional"),
        # 2026
        ("2026-01-01", "Año Nuevo", "nacional"),
        ("2026-02-16", "Carnaval", "nacional"),
        ("2026-02-17", "Carnaval", "nacional"),
        ("2026-04-03", "Viernes Santo", "nacional"),
        ("2026-05-01", "Día del Trabajo", "nacional"),
        ("2026-05-24", "Batalla de Pichincha", "nacional"),
        ("2026-08-10", "Primer Grito de Independencia", "nacional"),
        ("2026-10-09", "Independencia de Guayaquil", "nacional"),
        ("2026-11-02", "Día de los Difuntos", "nacional"),
        ("2026-11-03", "Independencia de Cuenca", "nacional"),
        ("2026-12-25", "Navidad", "nacional"),
    ]

    for fecha, desc, tipo in feriados:
        conn.execute(
            text("""
                INSERT INTO feriados (fecha, descripcion, tipo)
                VALUES (CAST(:fecha AS date), :desc, :tipo)
                ON CONFLICT (fecha) DO NOTHING
            """),
            {"fecha": fecha, "desc": desc, "tipo": tipo},
        )
