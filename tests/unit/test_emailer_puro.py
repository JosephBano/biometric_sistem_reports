"""
Tests unitarios de `app.domain.emailer` (Fase 7.4).

Funciones puras (no Flask) y mocks de SMTP.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.domain import emailer


class TestEnviarCorreo:

    def test_enviar_correo_sin_smtp_config_retorna_false(self, monkeypatch):
        """Si SMTP no está configurado, no envía y retorna False."""
        monkeypatch.delenv("SMTP_HOST", raising=False)
        monkeypatch.delenv("SMTP_PORT", raising=False)
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)

        result = emailer.enviar_correo(
            "test@x.com",
            "Asunto",
            "Cuerpo del mensaje",
        )
        assert result is False

    def test_enviar_correo_usa_smtp_externo(self, monkeypatch):
        """Mockeando smtplib, verificar que se invoca SMTP().send_message()."""
        monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setenv("SMTP_USER", "user")
        monkeypatch.setenv("SMTP_PASSWORD", "pass")
        monkeypatch.setenv("SMTP_USE_TLS", "true")

        with patch("smtplib.SMTP") as mock_smtp:
            mock_instance = mock_smtp.return_value
            result = emailer.enviar_correo(
                "to@test.com",
                "Subject",
                "<p>Body</p>",
            )

        assert result is True
        mock_instance.send_message.assert_called_once()
        mock_instance.starttls.assert_called_once()
        mock_instance.login.assert_called_once_with("user", "pass")

    def test_enviar_correo_con_adjunto_existente(self, monkeypatch, tmp_path):
        """Si el adjunto existe, se adjunta al mensaje."""
        monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setenv("SMTP_USER", "user")
        monkeypatch.setenv("SMTP_PASSWORD", "pass")

        # Crear archivo temporal
        adjunto = tmp_path / "reporte.pdf"
        adjunto.write_bytes(b"%PDF-1.4 fake")

        with patch("smtplib.SMTP") as mock_smtp:
            mock_instance = mock_smtp.return_value
            result = emailer.enviar_correo(
                "to@test.com",
                "Subject",
                "<p>Body</p>",
                adjunto_path=str(adjunto),
            )

        assert result is True
        mock_instance.send_message.assert_called_once()

    def test_enviar_correo_con_adjunto_inexistente_no_falla(self, monkeypatch):
        """Si el adjunto no existe, el envío continúa sin él."""
        monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setenv("SMTP_USER", "user")
        monkeypatch.setenv("SMTP_PASSWORD", "pass")

        with patch("smtplib.SMTP") as mock_smtp:
            mock_instance = mock_smtp.return_value
            result = emailer.enviar_correo(
                "to@test.com",
                "Subject",
                "<p>Body</p>",
                adjunto_path="/tmp/no-existe.pdf",
            )

        # El envío debe seguir funcionando a pesar del adjunto faltante
        assert result is True

    def test_enviar_correo_cuando_smtp_falla_retorna_false(self, monkeypatch):
        """Si smtplib.SMTP lanza excepción, retorna False."""
        monkeypatch.setenv("SMTP_HOST", "smtp.test.com")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setenv("SMTP_USER", "user")
        monkeypatch.setenv("SMTP_PASSWORD", "pass")

        with patch("smtplib.SMTP", side_effect=ConnectionError("SMTP unreachable")):
            result = emailer.enviar_correo(
                "to@test.com",
                "Subject",
                "<p>Body</p>",
            )
        assert result is False