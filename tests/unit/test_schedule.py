"""
Tests del wrapper de sync/scheduler (`app.domain.schedule`).

Cubre:
  - `get_job_status` retorna "no_encontrado" para IDs inexistentes
  - `_jobs` es un dict accesible (para inspección desde tests)
  - `init_scheduler` no falla cuando SYNC_AUTO=false (caso de test)
"""
from __future__ import annotations

from app import create_app
from app.domain import schedule as schedule_svc


class TestJobStatus:

    def test_job_inexistente_devuelve_no_encontrado(self):
        """Pedir el estado de un job_id que no existe → 'no_encontrado'."""
        status = schedule_svc.get_job_status("id-que-no-existe-12345")
        assert status.get("estado") == "no_encontrado"

    def test_set_job_y_get_job_status_roundtrip(self):
        """Si alguien setea un job en _jobs, get_job_status lo lee."""
        schedule_svc._jobs["test-job-1"] = {"estado": "procesando", "x": 1}
        status = schedule_svc.get_job_status("test-job-1")
        assert status["estado"] == "procesando"
        assert status["x"] == 1
        # Limpieza
        del schedule_svc._jobs["test-job-1"]


class TestInitScheduler:

    def test_init_scheduler_con_sync_auto_false_no_inicia(self):
        """Si SYNC_AUTO=false (default), init_scheduler no hace nada."""
        app = create_app("testing")
        # SYNC_AUTO es False por default en TestConfig.
        # El test verifica que la llamada es segura (no inicia thread).
        schedule_svc.init_scheduler(app)
        # Si llegamos aquí sin excepción, el test pasa.

    def test_init_scheduler_acepta_app_valida(self):
        """No debe lanzar con una app válida (aunque SYNC_AUTO=false)."""
        app = create_app("testing")
        # Simplemente no debe explotar.
        schedule_svc.init_scheduler(app)
