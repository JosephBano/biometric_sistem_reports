"""
Inicialización de la base de datos PostgreSQL.

init_db() es idempotente: puede llamarse múltiples veces sin efecto adverso.
Crea las tablas si no existen y siembra los datos iniciales del tenant.
"""

import os
import logging
from sqlalchemy import text

from db.connection import get_engine, get_connection
from db.schema import PUBLIC_DDL, get_tenant_ddl

log = logging.getLogger(__name__)


def init_db():
    """
    1. Aplica DDL público (tenants, usuarios, audit_log, login_intentos).
    2. Crea el schema del tenant y sus tablas.
    3. Inserta datos de referencia iniciales (idempotente).
    """
    tenant = os.environ.get("TENANT_DEFAULT", "istpet")
    engine = get_engine()

    with engine.connect() as conn:
        # Schema público
        conn.execute(text(PUBLIC_DDL))
        conn.commit()

        # Schema del tenant
        conn.execute(text(get_tenant_ddl(tenant)))
        conn.commit()

    # Datos de referencia
    _seed_datos_iniciales(tenant)
    log.info("init_db completado para tenant=%s", tenant)


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
