"""
Motor SQLAlchemy con soporte de schema-por-tenant.
Fase 1: el tenant se determina desde la variable TENANT_DEFAULT.
Fase 2+: leerá g.tenant_schema del contexto Flask.
"""

import os
import threading
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

_engine = None
_thread_local = threading.local()


def set_thread_tenant(schema: str):
    """Establece el tenant schema para el hilo actual (uso en background threads)."""
    _thread_local.tenant_schema = schema


def clear_thread_tenant():
    """Limpia el tenant schema del hilo actual."""
    _thread_local.tenant_schema = None


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
    Prioridad:
    1. Thread-local (background threads que capturaron el schema antes de lanzarse)
    2. Flask g.tenant_schema (requests HTTP normales)
    3. TENANT_DEFAULT env var (fallback)
    """
    schema = getattr(_thread_local, "tenant_schema", None)
    if schema:
        return schema
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
