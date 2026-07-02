"""
Tests del módulo `backup.py` (Fase 2 — Backups portables).

Mockeamos subprocess y filesystem para no ejecutar pg_dump real.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import backup as backup_module


class TestPurgarBackupsViejos:

    def test_purgar_borra_archivos_mas_viejos_que_dias(self, tmp_path):
        """Crea 3 archivos (1 viejo + 2 frescos); debe borrar solo el viejo."""
        viejo = tmp_path / "backup_20260501_0200.dump"
        viejo.write_bytes(b"x" * 100)
        # Forzar mtime viejo (100 días atrás)
        viejo_mtime = time.time() - 100 * 86400
        os.utime(viejo, (viejo_mtime, viejo_mtime))

        fresco1 = tmp_path / "backup_20260701_0200.dump"
        fresco1.write_bytes(b"x" * 100)
        fresco2 = tmp_path / "backup_20260702_0200.dump"
        fresco2.write_bytes(b"x" * 100)

        borrados = backup_module.purgar_backups_viejos(tmp_path, dias=30)

        assert borrados == 1
        assert not viejo.exists()
        assert fresco1.exists()
        assert fresco2.exists()

    def test_purgar_directorio_inexistente_devuelve_cero(self, tmp_path):
        """Si el directorio no existe, retorna 0 sin lanzar."""
        inxistente = tmp_path / "no_existe"
        borrados = backup_module.purgar_backups_viejos(inxistente, dias=30)
        assert borrados == 0

    def test_purgar_no_borra_archivos_no_dump(self, tmp_path):
        """Solo borra archivos .dump (no .log, .tmp, etc.)."""
        viejo_log = tmp_path / "viejo.log"
        viejo_log.write_text("log")
        viejo_mtime = time.time() - 100 * 86400
        os.utime(viejo_log, (viejo_mtime, viejo_mtime))

        # .dump con mtime viejo (debe borrarse)
        viejo_dump = tmp_path / "viejo.dump"
        viejo_dump.write_bytes(b"x")
        os.utime(viejo_dump, (viejo_mtime, viejo_mtime))

        borrados = backup_module.purgar_backups_viejos(tmp_path, dias=30)

        assert borrados == 1
        assert not viejo_dump.exists()
        assert viejo_log.exists()  # no se toca


class TestGenerarDump:

    def test_generar_dump_armando_comando_correcto(self, tmp_path):
        """Verifica que pg_dump se invoca con -Fc y destino correcto."""
        destino = tmp_path / "test.dump"

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("backup.subprocess.run", return_value=mock_result) as mock_run:
            # Crear el archivo destino para que el size() funcione
            destino.write_bytes(b"x" * 1024)

            ruta = backup_module.generar_dump(destino)

        assert ruta == destino
        # Verificar comando
        args = mock_run.call_args.args[0]
        assert args[0] == "pg_dump"
        assert "-Fc" in args
        assert str(destino) in args

    def test_generar_dump_con_database_url_armada_correctamente(self, tmp_path):
        """DATABASE_URL se parsea y se pasa por env PGPASSWORD (no argv)."""
        destino = tmp_path / "test.dump"

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:secret@dbhost:5432/mydb"},
            clear=False,
        ):
            with patch("backup.subprocess.run", return_value=mock_result) as mock_run:
                destino.write_bytes(b"x" * 1024)
                backup_module.generar_dump(destino)

        # Verificar que el comando tiene host, port, user, dbname correctos
        args = mock_run.call_args.args[0]
        assert "-h" in args
        idx = args.index("-h")
        assert args[idx + 1] == "dbhost"
        assert "-p" in args
        assert args[args.index("-p") + 1] == "5432"
        assert "-U" in args
        assert args[args.index("-U") + 1] == "user"
        assert "mydb" in args

        # Y que PGPASSWORD está en env (no en argv)
        env = mock_run.call_args.kwargs.get("env", {})
        assert env.get("PGPASSWORD") == "secret"
        # Y NO está en argv
        assert "secret" not in " ".join(args), "Password NO debe aparecer en argv"

    def test_generar_dump_falla_si_returncode_no_cero(self, tmp_path):
        """pg_dump con error → debe lanzar RuntimeError con mensaje claro."""
        destino = tmp_path / "test.dump"

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "pg_dump: error: connection failed"

        with patch("backup.subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError) as exc_info:
                backup_module.generar_dump(destino)

        assert "pg_dump" in str(exc_info.value)
        assert "connection failed" in str(exc_info.value)

    def test_generar_dump_sin_database_url_lanza_error(self, tmp_path):
        """Sin DATABASE_URL → RuntimeError antes de tocar subprocess."""
        destino = tmp_path / "test.dump"

        # Limpiar todas las env vars que podrían tener DATABASE_URL
        env_sin_db = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        with patch.dict(os.environ, env_sin_db, clear=True):
            with pytest.raises(RuntimeError) as exc_info:
                backup_module.generar_dump(destino)

        assert "DATABASE_URL" in str(exc_info.value)

    def test_generar_dump_registra_tamano_archivo(self, tmp_path):
        """Retorna un objeto con size() > 0 (vía Path.stat().st_size)."""
        destino = tmp_path / "test.dump"
        destino.write_bytes(b"x" * 4096)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("backup.subprocess.run", return_value=mock_result):
            ruta = backup_module.generar_dump(destino)

        assert ruta.stat().st_size == 4096

    def test_generar_dump_si_archivo_vacio_lanza_error(self, tmp_path):
        """Si pg_dump retorna OK pero el archivo está vacío → error."""
        destino = tmp_path / "test.dump"
        # No escribimos nada (archivo vacío)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("backup.subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError) as exc_info:
                backup_module.generar_dump(destino)

        assert "vacío" in str(exc_info.value) or "ausente" in str(exc_info.value)

    def test_generar_dump_si_pg_dump_no_instalado_lanza_error(self, tmp_path):
        """Si pg_dump no existe en PATH → FileNotFoundError → RuntimeError claro."""
        destino = tmp_path / "test.dump"

        with patch("backup.subprocess.run", side_effect=FileNotFoundError("pg_dump no encontrado")):
            with pytest.raises(RuntimeError) as exc_info:
                backup_module.generar_dump(destino)

        assert "pg_dump" in str(exc_info.value)
        assert "reconstruir" in str(exc_info.value).lower() or "instalado" in str(exc_info.value).lower()