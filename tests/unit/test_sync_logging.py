"""
Tests del logger y registro de corridas en `app.domain.schedule`.

Migrado desde `tests/unit/test_sync_logging.py` (Fase 4e.6 — ADR-0001).
Mockeamos el engine y los helpers para no tocar BD ni dispositivos reales.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import patch


class TestLoggerSchedule:

    def test_modulo_tiene_logger_named_app_domain_schedule(self, caplog):
        """`app.domain.schedule` debe exponer un logger con nombre coherente."""
        from app.domain import schedule as schedule_svc

        assert hasattr(schedule_svc, "log")
        assert isinstance(schedule_svc.log, logging.Logger)
        assert schedule_svc.log.name == "app.domain.schedule"

    def test_init_scheduler_con_sync_auto_false_loggea_inactivo(self, caplog):
        """Si `app.config['SYNC_AUTO']` es False, loguear 'Scheduler INACTIVO'."""
        from app.domain import schedule as schedule_svc
        from app import create_app

        app = create_app("testing")
        # TestingConfig tiene SYNC_AUTO=False por default.
        with caplog.at_level(logging.INFO, logger="app.domain.schedule"):
            schedule_svc.init_scheduler(app)

        mensajes = [r.getMessage() for r in caplog.records]
        assert any("INACTIVO" in m for m in mensajes), (
            f"Esperaba log conteniendo 'INACTIVO'; recibí: {mensajes}"
        )


class TestRegistrarCorridaSync:

    def test_registrar_corrida_llama_db_registrar_run(self):
        """`_registrar_corrida_sync` debe invocar `db.queries.scheduler_runs.registrar_run`."""
        from app.domain import schedule as schedule_svc

        with patch("db.queries.scheduler_runs.registrar_run") as mock_reg:
            schedule_svc._registrar_corrida_sync(
                job="sync_incremental",
                tenant_slug="istpet",
                inicio=datetime(2026, 7, 2, 10, 0, tzinfo=UTC),
                fin=datetime(2026, 7, 2, 10, 5, tzinfo=UTC),
                ok=True,
                descargados=10,
                insertados=8,
                detalle=None,
            )

        mock_reg.assert_called_once()
        kwargs = mock_reg.call_args.kwargs
        assert kwargs["job"] == "sync_incremental"
        assert kwargs["ok"] is True
        assert kwargs["tenant_slug"] == "istpet"

    def test_registrar_corrida_no_propaga_excepciones(self):
        """Si `db.queries.scheduler_runs` falla, NO debe matar el scheduler."""
        from app.domain import schedule as schedule_svc

        with patch(
            "db.queries.scheduler_runs.registrar_run",
            side_effect=RuntimeError("BD caída"),
        ):
            # No debe lanzar
            schedule_svc._registrar_corrida_sync(
                job="sync_incremental",
                tenant_slug="istpet",
                inicio=datetime(2026, 7, 2, 10, 0, tzinfo=UTC),
                fin=datetime(2026, 7, 2, 10, 5, tzinfo=UTC),
                ok=True,
                descargados=10,
                insertados=8,
                detalle=None,
            )
        # OK si llegamos aquí sin excepción


class TestSyncAutomaticaNoFallaEnSilencio:

    def test_sync_automatico_registra_error_pero_no_lanza(self):
        """`_sync_automatico` debe capturar excepciones por tenant, registrar y continuar.

        Si `sincronizar()` lanza en el tenant A, debe seguir con el tenant B.
        """
        from app.domain import schedule as schedule_svc

        # _get_tenant_slugs mockeado para devolver 2 slugs
        with patch.object(
            schedule_svc, "_get_tenant_slugs", return_value=["tenant_a", "tenant_b"]
        ):
            # sincronizar falla en A pero ok en B
            def fake_sincronizar(*args, **kwargs):
                if schedule_svc._get_tenant_slugs.call_count == 0:
                    return (5, 3)
                # Primera llamada (tenant_a): falla
                if (
                    schedule_svc.db_module.set_thread_tenant.call_args[0][0]
                    == "tenant_a"
                ):
                    raise ConnectionError("dispositivo no disponible")
                return (10, 8)

            with patch.object(
                schedule_svc, "sincronizar", side_effect=fake_sincronizar
            ), patch.object(
                schedule_svc, "_registrar_corrida_sync"
            ) as mock_reg, patch(
                "db.queries.periodos.cerrar_periodos_vencidos"
            ), patch.object(
                schedule_svc.db_module, "set_thread_tenant"
            ), patch.object(
                schedule_svc.db_module, "clear_thread_tenant"
            ):

                schedule_svc._sync_automatico()

            # Debe haber llamado a _registrar_corrida_sync DOS veces
            # (una por tenant, ambas con ok=True/False)
            assert mock_reg.call_count == 2
            # El primer llamado fue para tenant_a (falló)
            primera = mock_reg.call_args_list[0]
            assert primera.kwargs["tenant_slug"] == "tenant_a"
            assert primera.kwargs["ok"] is False
            assert "dispositivo" in primera.kwargs["detalle"]
            # El segundo llamado fue para tenant_b (ok)
            segunda = mock_reg.call_args_list[1]
            assert segunda.kwargs["tenant_slug"] == "tenant_b"
            assert segunda.kwargs["ok"] is True
            assert segunda.kwargs["descargados"] == 10
            assert segunda.kwargs["insertados"] == 8


class TestRunLoopInkillable:

    def test_run_loop_pattern_es_inkillable_por_estructura(self):
        """El loop `while-True` tiene try/except para no morir.

        Verificación estática: el código fuente contiene el patrón correcto.
        El comportamiento real se valida en staging (loop debe sobrevivir 24h).
        """
        import inspect

        from app.domain import schedule as schedule_svc

        fuente = inspect.getsource(schedule_svc.init_scheduler)
        # El loop `_run()` debe tener try/except envolviendo run_pending
        assert "while True" in fuente, "Debe existir loop while True"
        assert "run_pending" in fuente, "Debe invocar schedule.run_pending()"
        assert "log.exception" in fuente, "Debe loguear excepción"
        assert "time_module.sleep" in fuente, "Debe dormir entre pasadas"
        # Y debe estar dentro de un try/except (al menos 2: uno para
        # run_pending, otro para _registrar_corrida_sync).
        assert fuente.count("try:") >= 2, (
            "Debe haber al menos 2 try/except (loop + registrar_corrida_sync)"
        )

    def test_init_scheduler_no_duplica_hilos_con_singleton_guard(self):
        """Llamar `init_scheduler(app)` dos veces con SYNC_AUTO=True no crea 2 hilos."""
        from app import create_app
        from app.domain import schedule as schedule_svc

        app = create_app("testing")
        app.config["SYNC_AUTO"] = True

        # Resetear el flag singleton para que intente iniciar.
        schedule_svc._scheduler_started = False

        try:
            # Mockear el Thread para contar cuántas veces se crea.
            with patch("app.domain.schedule.threading.Thread") as mock_thread:
                schedule_svc.init_scheduler(app)
                # Segunda y tercera llamada deben ser ignoradas por el guard.
                schedule_svc.init_scheduler(app)
                schedule_svc.init_scheduler(app)

            # Solo se creó 1 thread (no 3).
            assert mock_thread.call_count == 1, (
                f"Esperaba 1 thread; se crearon {mock_thread.call_count}"
            )
        finally:
            # Restaurar estado para no contaminar otros tests.
            schedule_svc._scheduler_started = False
