"""
Servicio de backups portables (`app.domain.backup`).

Estrategia: `pg_dump -Fc` (formato custom comprimido) ejecutado vía subprocess
con credenciales pasadas por env (`PGPASSWORD`), NUNCA por argv. Esto evita
exponer secretos en `ps aux`.

Restauración: `pg_restore -d <db> backup.dump` en cualquier PostgreSQL >= 16.

Migrado desde `backup.py` (raíz) en Fase 4e.7 del ADR-0001.

API pública:
  - `generar_dump(destino) -> Path`
  - `purgar_backups_viejos(directorio, dias=30) -> int`
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse


def _parse_database_url(url: str) -> dict:
    """Parsea DATABASE_URL estilo postgresql://user:pass@host:port/db."""
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise ValueError(f"DATABASE_URL con esquema no soportado: {parsed.scheme}")
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "",
        "password": parsed.password or "",
        "dbname": (parsed.path or "/").lstrip("/"),
    }


def generar_dump(destino: Path) -> Path:
    """
    Ejecuta `pg_dump -Fc` sobre la BD configurada por DATABASE_URL y escribe el
    resultado en `destino`.

    Args:
        destino: ruta absoluta del archivo .dump a crear.

    Returns:
        La misma ruta `destino`, con el dump ya escrito.

    Raises:
        RuntimeError: si DATABASE_URL no está, si pg_dump no está instalado,
            o si returncode != 0 o el archivo resultante está vacío.
    """
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL no configurado. No se puede ejecutar pg_dump."
        )

    cfg = _parse_database_url(db_url)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    # Credenciales por env (NUNCA en argv).
    env = os.environ.copy()
    env["PGPASSWORD"] = cfg["password"]

    cmd = [
        "pg_dump",
        "-Fc",  # formato custom comprimido
        "-h", cfg["host"],
        "-p", cfg["port"],
        "-U", cfg["user"],
        "-d", cfg["dbname"],
        "-f", str(destino),
    ]

    try:
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=1800,
            check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "pg_dump no está instalado en el contenedor. "
            "Reconstruir la imagen con postgresql-client incluido."
        ) from e

    if result.returncode != 0:
        raise RuntimeError(
            f"pg_dump falló (returncode={result.returncode}): {result.stderr}"
        )

    if not destino.exists() or destino.stat().st_size == 0:
        raise RuntimeError(
            f"pg_dump terminó OK pero el archivo {destino} está vacío o ausente."
        )

    return destino


def purgar_backups_viejos(directorio: Path, dias: int = 30) -> int:
    """
    Borra archivos `.dump` con mtime > `dias` días.

    Args:
        directorio: carpeta donde están los backups.
        dias: retención; los más viejos que esto se eliminan.

    Returns:
        Cantidad de archivos borrados.
    """
    directorio = Path(directorio)
    if not directorio.is_dir():
        return 0

    cutoff = time.time() - dias * 86400
    borrados = 0
    for archivo in directorio.glob("*.dump"):
        try:
            if archivo.stat().st_mtime < cutoff:
                archivo.unlink()
                borrados += 1
        except OSError:
            # Archivo puede haber sido borrado por otro proceso; ignorar.
            continue
    return borrados


__all__ = ["generar_dump", "purgar_backups_viejos"]
