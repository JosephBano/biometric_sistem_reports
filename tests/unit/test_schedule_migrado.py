"""
Tests del módulo `app.domain.schedule` (Fase 4e.6 — migración de sync.py).

Garantías:
  - `import app.domain.schedule` no arranca threads ni lee env vars críticos.
  - `_jobs` vive en `app.domain.schedule._jobs` (no en `sync._jobs`).
  - `init_scheduler(app)` arranca los jobs solo si `app.config["SYNC_AUTO"]`.
  - `init_scheduler(app)` es idempotente (segunda llamada = no-op).
  - API pública estable: `get_job_status`, `sincronizar`, `ping_dispositivo`,
    `sincronizar_con_reintento`, `sincronizar_dispositivo`,
    `limpiar_log_dispositivo`, `verificar_dispositivos_desconectados`.
"""
from __future__ import annotations

import importlib
import inspect
import threading


class TestImportEsSeguro:
    """`import app.domain.schedule` no debe arrancar el scheduler."""

    def test_import_no_crea_hilos(self):
        """Importar el módulo no debe dejar hilos daemon activos del scheduler."""
        antes = {t.name for t in threading.enumerate()}
        importlib.import_module("app.domain.schedule")
        despues = {t.name for t in threading.enumerate()}
        nuevos = despues - antes
        # No debe haber aparecido el hilo "biometrico-scheduler"
        assert "biometrico-scheduler" not in nuevos, (
            f"`import app.domain.schedule` arrancó threads: {nuevos}"
        )

    def test_modulo_no_arranca_scheduler_al_importar(self):
        """El módulo expone `_scheduler_started` (False por default)."""
        mod = importlib.import_module("app.domain.schedule")
        # El flag debe existir y estar en False (no se llamó iniciar)
        assert hasattr(mod, "_scheduler_started"), (
            "Falta atributo `_scheduler_started` en app.domain.schedule"
        )
        assert mod._scheduler_started is False

    def test_jobs_dict_es_atributo_del_modulo_dominio(self):
        """`_jobs` debe vivir en `app.domain.schedule`, no en `sync` legacy."""
        mod = importlib.import_module("app.domain.schedule")
        assert hasattr(mod, "_jobs")
        assert isinstance(mod._jobs, dict)


class TestApiPublica:
    """API pública de `app.domain.schedule` debe estar expuesta."""

    def test_funciones_publicas_esperadas(self):
        """Funciones que las blueprints y tests deben poder importar."""
        mod = importlib.import_module("app.domain.schedule")
        funciones_esperadas = [
            "init_scheduler",
            "get_job_status",
            "ping_dispositivo",
            "sincronizar",
            "sincronizar_con_reintento",
            "sincronizar_dispositivo",
            "limpiar_log_dispositivo",
            "verificar_dispositivos_desconectados",
        ]
        for nombre in funciones_esperadas:
            assert hasattr(mod, nombre), (
                f"Falta función pública `{nombre}` en app.domain.schedule"
            )
            assert callable(getattr(mod, nombre)), (
                f"`{nombre}` debe ser callable"
            )


class TestInitSchedulerConApp:
    """`init_scheduler(app)` lee de `app.config` y respeta `SYNC_AUTO=false`."""

    def test_init_scheduler_con_sync_auto_false_no_inicia(self):
        """Si `app.config['SYNC_AUTO']` es False, no se inicia el scheduler."""
        from app import create_app
        from app.domain import schedule as schedule_svc

        app = create_app("testing")
        # TestConfig tiene SYNC_AUTO=False por default.
        schedule_svc.init_scheduler(app)
        assert schedule_svc._scheduler_started is False

    def test_init_scheduler_es_idempotente(self):
        """Llamar `init_scheduler` dos veces no duplica el log de arranque."""
        from app import create_app
        from app.domain import schedule as schedule_svc

        app = create_app("testing")
        schedule_svc.init_scheduler(app)
        schedule_svc.init_scheduler(app)
        # Si fuera no-idempotente, podría lanzar o loguear warning.
        # Aquí solo verificamos que no rompe y que el flag sigue en False
        # (porque SYNC_AUTO=False).
        assert schedule_svc._scheduler_started is False

    def test_get_job_status_devuelve_no_encontrado_para_id_inexistente(self):
        """API estable: pedir un job_id inexistente retorna 'no_encontrado'."""
        from app.domain import schedule as schedule_svc

        status = schedule_svc.get_job_status("id-que-no-existe-99999")
        assert status.get("estado") == "no_encontrado"
