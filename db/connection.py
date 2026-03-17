"""
Motor SQLAlchemy con soporte de schema-por-tenant.
Fase 1: el tenant se determina desde la variable TENANT_DEFAULT.
Fase 2+: leerá g.tenant_schema del contexto Flask.
"""

import os
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError(
                "DATABASE_URL no está configurado. "
                "Agrega DATABASE_URL=postgresql://user:pass@host:5432/db al .env"
            )
        _engine = create_engine(
            url,
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
        schema = getattr(g, "tenant_schema", None)
        if schema:
            return schema
    except RuntimeError:
        pass
    return os.environ.get("TENANT_DEFAULT", "istpet")


@contextmanager
def get_connection(schema: str = None):
    """
    Context manager que entrega una conexión con el search_path correcto.
    Hace commit automático al salir sin excepción; rollback en error.
    """
    schema = schema or get_tenant_schema()
    # Validar que el slug solo tiene caracteres seguros (previene SQL injection)
    if not all(c.isalnum() or c == "_" for c in schema):
        raise ValueError(f"Schema name inválido: {schema!r}")
    with get_engine().connect() as conn:
        conn.execute(text(f"SET search_path TO {schema}, public"))
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
