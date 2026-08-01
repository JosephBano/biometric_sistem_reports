"""
Tests de `SESSION_COOKIE_SECURE` en ProductionConfig.

Contexto (bug prod 29-jul-2026): con `SESSION_COOKIE_SECURE = True` fijo y el
despliegue sirviendo HTTP plano (http://IP:5000), el navegador descarta la
cookie de sesión → la sesión llega vacía al POST → 403 "Token CSRF inválido".
El flag debe poder desactivarse por entorno, manteniendo True como defecto.
"""
from __future__ import annotations

import importlib

import pytest

import app.config as config_mod


@pytest.fixture()
def reload_config():
    """Recarga `app.config` con el entorno actual y restaura al terminar."""
    def _reload():
        return importlib.reload(config_mod)

    yield _reload
    importlib.reload(config_mod)


class TestSessionCookieSecure:

    def test_default_es_true(self, monkeypatch, reload_config):
        monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
        cfg = reload_config()
        assert cfg.ProductionConfig.SESSION_COOKIE_SECURE is True

    def test_env_false_desactiva_secure(self, monkeypatch, reload_config):
        monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
        cfg = reload_config()
        assert cfg.ProductionConfig.SESSION_COOKIE_SECURE is False

    def test_env_true_explicito(self, monkeypatch, reload_config):
        monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
        cfg = reload_config()
        assert cfg.ProductionConfig.SESSION_COOKIE_SECURE is True
