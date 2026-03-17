"""
Lógica de Provisioning para nuevos tenants (Fase 3: Multitenancy).

Crea el schema, corre DDL y siembra datos iniciales.
"""

import logging
from sqlalchemy import text

from db.connection import get_engine, get_connection
from db.schema import get_tenant_ddl
from db.queries.tenants import insertar_tipo_persona, eliminar_tenant_de_public
from db.init import _insertar_feriados_ecuador

log = logging.getLogger(__name__)


def provisionar_schema(slug: str, tipos_persona: list[str]) -> bool:
    """
    Crea el schema de base de datos para un nuevo tenant, corre su DDL y
    siembra datos iniciales (tipos de persona y feriados).
    """
    # Validar slug (prevenir inyección SQL)
    if not all(c.isalnum() or c == "_" for c in slug):
        raise ValueError(f"Nombre de schema inválido: '{slug}'")

    engine = get_engine()
    created_schema = False

    try:
        with engine.connect() as conn:
            # 1. Crear schema y tablas usando DDL
            log.info(f"Creando schema '{slug}'...")
            conn.execute(text(get_tenant_ddl(slug)))
            conn.commit()
            created_schema = True

        # 2. Datos de referencia iniciales en el nuevo schema
        with get_connection(slug) as conn:
            # Sede por defecto
            conn.execute(
                text("INSERT INTO sedes (nombre) VALUES (:nombre)"),
                {"nombre": f"Sede Principal"}
            )

            # Tipos de persona iniciales
            log.info(f"Cargando tipos de persona para '{slug}'...")
            for tipo in tipos_persona:
                 # Evitar duplicar
                 conn.execute(
                     text("INSERT INTO tipos_persona (nombre) VALUES (:nombre)"),
                     {"nombre": tipo}
                 )

            # Cargar feriados nacionales de Ecuador
            log.info(f"Cargando feriados nacionales para '{slug}'...")
            _insertar_feriados_ecuador(conn)

        log.info(f"Provisioning completado exitosamente para '{slug}'.")
        return True

    except Exception as e:
        log.error(f"Error durante el provisioning del tenant '{slug}': {e}")
        # Rollback explícito de Provisioning
        if created_schema:
            try:
                log.warning(f"Ejecutando rollback (DROP SCHEMA) de '{slug}'...")
                with engine.connect() as conn:
                    # DROP SCHEMA CASCADE para remover tablas asociadas
                    conn.execute(text(f"DROP SCHEMA IF EXISTS {slug} CASCADE"))
                    conn.commit()
            except Exception as rollback_err:
                 log.error(f"Error en rollback de schema para '{slug}': {rollback_err}")

        # Remover de public.tenants para que no quede huérfano
        eliminar_tenant_de_public(slug)

        raise e
