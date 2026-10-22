"""PostgreSQL advisory locks for the dedicated scheduler process and jobs."""
from __future__ import annotations

from sqlalchemy import text

from db.connection import get_engine

_LOCK_NAMESPACE = 0x42494F4D  # ASCII "BIOM", signed int32.
SCHEDULER_LEADER_LOCK = 0
_JOB_LOCKS = {
    "sync_nocturna": 1,
    "sync_incremental": 2,
    "backup_diario": 3,
}


def job_lock_id(job: str) -> int:
    """Return the stable advisory-lock key for a known scheduler job."""
    try:
        return _JOB_LOCKS[job]
    except KeyError as exc:
        raise ValueError(f"Job sin lock configurado: {job}") from exc


def try_acquire(lock_id: int):
    """Acquire a session lock and return its connection, or None if busy.

    The caller must release a returned connection with :func:`release`.
    """
    conn = get_engine().connect()
    try:
        acquired = bool(conn.execute(
            text("SELECT pg_try_advisory_lock(:namespace, :lock_id)"),
            {"namespace": _LOCK_NAMESPACE, "lock_id": lock_id},
        ).scalar())
        conn.commit()
    except Exception:
        conn.close()
        raise

    if not acquired:
        conn.close()
        return None
    return conn


def release(conn, lock_id: int) -> None:
    """Release an advisory lock and return its connection to the pool."""
    try:
        conn.execute(
            text("SELECT pg_advisory_unlock(:namespace, :lock_id)"),
            {"namespace": _LOCK_NAMESPACE, "lock_id": lock_id},
        )
        conn.commit()
    finally:
        conn.close()


def scheduler_is_active() -> bool:
    """Check whether another process currently holds the scheduler leader lock."""
    conn = try_acquire(SCHEDULER_LEADER_LOCK)
    if conn is None:
        return True
    release(conn, SCHEDULER_LEADER_LOCK)
    return False
