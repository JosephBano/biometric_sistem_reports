"""
Servicio de correo electrónico (`app/domain/emailer.py`).

Migrado desde `email_utils.py` (raíz). Sin cambios funcionales.

API:
  - `enviar_correo(destinatario, asunto, cuerpo, adjunto_path=None) -> bool`

No importa Flask: se puede llamar desde un hilo de background.
"""
from __future__ import annotations

import os
import smtplib
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def enviar_correo(
    destinatario: str,
    asunto: str,
    cuerpo: str,
    adjunto_path: str | None = None,
) -> bool:
    """
    Envía un correo usando SMTP configurado en el entorno.

    Variables de entorno requeridas: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
    `SMTP_PASSWORD`. `SMTP_USE_TLS=true` activa STARTTLS.
    `SMTP_FROM` (opcional) define el emisor; por defecto usa `SMTP_USER`.

    Args:
        destinatario: dirección del receptor.
        asunto: línea de Subject.
        cuerpo: contenido HTML del mensaje.
        adjunto_path: ruta absoluta a un archivo para adjuntar (opcional).

    Returns:
        True si el envío fue exitoso, False en cualquier fallo (incluido
        configuración SMTP incompleta).
    """
    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
    sender = os.getenv("SMTP_FROM", user)

    if not all([host, port, user, pwd]):
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = destinatario
        msg["Subject"] = asunto
        msg.attach(MIMEText(cuerpo, "html"))

        if adjunto_path and os.path.exists(adjunto_path):
            filename = os.path.basename(adjunto_path)
            with open(adjunto_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=filename)
                part["Content-Disposition"] = f'attachment; filename="{filename}"'
                msg.attach(part)

        server = smtplib.SMTP(host, int(port), timeout=10)
        if use_tls:
            server.starttls()
        server.login(user, pwd)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"Error enviando correo: {e}", file=sys.stderr)
        return False
