"""
Tests de la Application Factory (`app`).

Cubre:
  - create_app() con cada config_name válido
  - create_app() rechaza config_name desconocido
  - TestingConfig salvaguarda: rechaza DATABASE_URL sin 'test'
  - La factory registra todos los Blueprints (13)
  - La factory aplica headers de seguridad
"""
from __future__ import annotations

import os

import pytest

from app import create_app


class TestFactoryEnSi:

    def test_create_app_devuelve_instancia_flask(self):
        app = create_app("testing")
        try:
            from flask import Flask
            assert isinstance(app, Flask)
        finally:
            # Limpieza: cerrar el engine de SQLAlchemy si se creó
            pass

    def test_create_app_rechaza_config_desconocida(self):
        with pytest.raises(KeyError):
            create_app("config_inexistente")

    def test_create_app_acepta_aliases(self):
        # Los aliases de config_map deben funcionar.
        for name in ("dev", "prod", "test"):
            app = create_app(name)
            assert app is not None


class TestTestingConfigSafeguard:

    def test_database_url_sin_test_es_rechazada(self, monkeypatch):
        """TestConfig debe rechazar DATABASE_URL que no parezca de test."""
        # Quitamos el valor por defecto del conftest.py y ponemos uno real.
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/production_db")

        with pytest.raises(RuntimeError, match="TestingConfig"):
            create_app("testing")

    def test_database_url_con_test_pasa(self):
        """TestConfig acepta DATABASE_URL que contiene 'test'."""
        # El conftest.py ya setea una URL con 'test_db'. Si esto no cambia,
        # la app debe construirse sin error.
        os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/test_db"
        app = create_app("testing")
        assert app is not None


class TestBlueprintsRegistrados:

    def test_contamos_los_blueprints_esperados(self):
        """Debe haber exactamente 14 blueprints (incluido horarios_gf)."""
        from app.web import all_blueprints
        assert len(all_blueprints) == 14, (
            f"Esperado 14 blueprints, encontrados {len(all_blueprints)}: "
            f"{[bp.name for bp in all_blueprints]}"
        )

    def test_nombres_de_blueprints_esperados(self):
        from app.web import all_blueprints
        nombres = {bp.name for bp in all_blueprints}
        expected = {
            "auth", "dashboard", "devices", "schedule", "attendance",
            "breaks", "reports", "periods", "people", "groups",
            "horarios_gf", "admin", "analytics", "system",
        }
        assert nombres == expected, f"Faltan o sobran: {nombres ^ expected}"


class TestSecurityHeaders:

    def test_respuesta_lleva_headers_de_seguridad(self):
        app = create_app("testing")
        client = app.test_client()
        # Usar una ruta que no requiera template (404 es válido,
        # los after_request se ejecutan en cualquier respuesta)
        resp = client.get("/__ruta_inexistente__")
        # Flask devuelve 404 HTML por default; los headers deben estar
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


class TestConteoDeRutas:

    def test_total_de_rutas_registradas(self):
        """Las 81 rutas del monolito deben estar todas en blueprints."""
        app = create_app("testing")
        rules = [r.rule for r in app.url_map.iter_rules() if not r.rule.startswith("/static")]
        # Filtrar la ruta "static" de Flask
        routes = [r for r in rules if r != "/static/<path:filename>"]
        assert len(routes) >= 80, (
            f"Esperado ≥80 rutas (post-refactor), encontradas {len(routes)}"
        )


class TestArquitectura:

    def test_app_web_no_importa_db_queries(self):
        """Regla: `app/web/*` no debe importar `db.queries.*` directamente."""
        import pathlib

        web_dir = pathlib.Path("app/web")
        offenders = []
        for py_file in web_dir.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            if "from db.queries" in source or "import db.queries" in source:
                offenders.append(py_file.name)

        # NOTA: hay una excepción legítima en `_get_grupos_periodos()` de admin_bp
        # que usa `db.connection.get_connection()` (no `db.queries.*`).
        # Esta regla debe cumplirse: ningún blueprint importa queries.
        assert offenders == [], (
            f"Las blueprints importan db.queries directamente: {offenders}"
        )

    def test_app_domain_no_importa_app_web(self):
        """Regla: `app/domain/*` no debe importar `app/web/*`."""
        import pathlib

        domain_dir = pathlib.Path("app/domain")
        offenders = []
        for py_file in domain_dir.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            if "from app.web" in source or "import app.web" in source:
                offenders.append(py_file.name)
        assert offenders == [], (
            f"Servicios de dominio importan web (ciclo!): {offenders}"
        )
