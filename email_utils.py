"""
Utilidades de correo electrónico.
Módulo independiente para evitar imports circulares entre app.py y sync.py.
"""

import os
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication


def enviar_correo(destinatario: str, asunto: str, cuerpo: str, adjunto_path: str = None) -> bool:
    """
    Envia un correo usando SMTP configurado en el entorno.
    """
    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    user = os.getenv("SMTP_USER")
    pwd  = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
    sender = os.getenv("SMTP_FROM", user)

    if not all([host, port, user, pwd]):
         return False

    try:
         msg = MIMEMultipart()
         msg['From'] = sender
         msg['To'] = destinatario
         msg['Subject'] = asunto
         msg.attach(MIMEText(cuerpo, 'html'))

         if adjunto_path and os.path.exists(adjunto_path):
              filename = os.path.basename(adjunto_path)
              with open(adjunto_path, "rb") as f:
                   part = MIMEApplication(f.read(), Name=filename)
                   part['Content-Disposition'] = f'attachment; filename="{filename}"'
                   msg.attach(part)

         server = smtplib.SMTP(host, int(port), timeout=10)
         if use_tls:
              server.starttls()
         server.login(user, pwd)
         server.send_message(msg)
         server.quit()
         return True
    except Exception as e:
         print(f"Error enviando correo: {e}", file=sys.stderr)
         return False
