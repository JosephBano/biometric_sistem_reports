"""
Tests del servicio de email (`app.domain.emailer`).

Cubre:
  - Sin configuración SMTP → devuelve False sin lanzar excepción.
  - Con configuración incompleta → devuelve False.
  - Función pura: no requiere Flask ni contexto de app.
"""
from __future__ import annotations

from app.domain.emailer import enviar_correo


class TestSinConfiguracionSMTP:

    def test_sin_variables_de_entorno_devuelve_false(self, monkeypatch):
        """Si faltan vars SMTP_* → False sin lanzar."""
        for var in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
                    "SMTP_FROM", "SMTP_USE_TLS"):
            monkeypatch.delenv(var, raising=False)

        resultado = enviar_correo(
            destinatario="user@example.com",
            asunto="Test",
            cuerpo="<p>Hola</p>",
        )
        assert resultado is False

    def test_con_solo_algunas_variables_devuelve_false(self, monkeypatch):
        """Con variables parciales → False (no intentar enviar)."""
        monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
        # Falta SMTP_PORT, SMTP_USER, SMTP_PASSWORD
        monkeypatch.delenv("SMTP_PORT", raising=False)
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)

        resultado = enviar_correo(
            destinatario="user@example.com",
            asunto="Test",
            cuerpo="<p>Hola</p>",
        )
        assert resultado is False


class TestPurezaDelModulo:

    def test_no_importa_flask(self):
        """`app.domain.emailer` debe ser usable sin Flask context."""
        import inspect

        from app.domain import emailer
        source = inspect.getsource(emailer)
        assert "from flask" not in source
        assert "import flask" not in source

    def test_no_importa_app_web(self):
        """Regla arquitectónica: domain/* no importa web/*."""
        import inspect

        from app.domain import emailer
        source = inspect.getsource(emailer)
        assert "from app.web" not in source
        assert "from web" not in source
