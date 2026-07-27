"""
Configuración por entorno (`app/config.py`).

Patrón: una clase por entorno. La factory selecciona una vía
`config_map[config_name]`. Cada subclase puede sobreescribir atributos
de Flask y métodos de inicialización.

Salvaguardas de TestConfig:
  - Rechaza arrancar si `DATABASE_URL` no apunta a una BD de test.
  - NO ejecuta `init_db()` ni el scheduler por defecto.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


class BaseConfig:
    """Configuración común a todos los entornos."""

    # ── Seguridad ─────────────────────────────────────────────────────
    # Generar con: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-production")

    # ── Sesión ────────────────────────────────────────────────────────
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("SESSION_LIFETIME_HOURS", "8")) * 3600
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # ── Archivos ──────────────────────────────────────────────────────
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "data/uploads")
    REPORTS_FOLDER = os.environ.get("REPORTS_FOLDER", "data/reports")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

    # ── Sistema ───────────────────────────────────────────────────────
    NOMBRE_SISTEMA = os.environ.get("NOMBRE_SISTEMA", "Informes Biométricos")
    NOMBRE_INSTITUCION = os.environ.get("NOMBRE_INSTITUCION", "ISTPET")

    # ── Mount path (DispatcherMiddleware en factory) ──────────────────
    APPLICATION_ROOT = "/biometrico"

    # ── Sync ──────────────────────────────────────────────────────────
    SYNC_AUTO = os.environ.get("SYNC_AUTO", "false").lower() == "true"
    SYNC_HORA_NOCTURNA = os.environ.get("SYNC_HORA_NOCTURNA", "02:00")
    SYNC_INTERVALO_HORAS = int(os.environ.get("SYNC_INTERVALO_HORAS", "2"))

    # ── Backup (Fase 2 — Backups portables) ───────────────────────────
    # Si BACKUP_AUTO está vacío, hereda el valor de SYNC_AUTO.
    _backup_auto_env = os.environ.get("BACKUP_AUTO", "")
    BACKUP_AUTO = (
        _backup_auto_env.lower() == "true"
        if _backup_auto_env != ""
        else SYNC_AUTO
    )
    BACKUP_HORA = os.environ.get("BACKUP_HORA", "03:00")
    BACKUP_DIR = os.environ.get("BACKUP_DIR", "/data/backups")
    BACKUP_RETENCION_DIAS = int(os.environ.get("BACKUP_RETENCION_DIAS", "30"))

    # ── Tenant ────────────────────────────────────────────────────────
    TENANT_DEFAULT = os.environ.get("TENANT_DEFAULT", "istpet")

    def init_app(self, app: Flask) -> None:
        """Hook para subclases; crea directorios y aplica defaults."""
        for folder in (app.config["UPLOAD_FOLDER"], app.config["REPORTS_FOLDER"]):
            try:
                os.makedirs(folder, exist_ok=True)
            except PermissionError:
                # Fallback al directorio local data/
                app.config["UPLOAD_FOLDER"] = "data/uploads"
                app.config["REPORTS_FOLDER"] = "data/reports"
                os.makedirs("data/uploads", exist_ok=True)
                os.makedirs("data/reports", exist_ok=True)

        # BACKUP_DIR puede no estar disponible (permisos); fallback a local
        backup_dir = app.config.get("BACKUP_DIR")
        if backup_dir:
            try:
                os.makedirs(backup_dir, exist_ok=True)
            except PermissionError:
                app.config["BACKUP_DIR"] = "data/backups"
                os.makedirs("data/backups", exist_ok=True)


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # permite HTTP en dev


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # sólo por HTTPS


class TestingConfig(BaseConfig):
    """
    Config para pytest.

    Salvaguardas (ver ADR-0001 Fase 2):
      - Rechaza `DATABASE_URL` que no parezca apuntar a una BD de test.
        Evita que un pytest cargado con `.env` de producción toque la BD real.
      - NO ejecuta `init_db()` automáticamente (eso se hace explícitamente en fixtures).
      - Desactiva el scheduler.
    """

    TESTING = True
    DEBUG = False
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False

    SYNC_AUTO = False  # nunca arrancar el scheduler en tests

    # Nombre de la BD de test: forzar a que contenga "test"
    TEST_DB_NAME_HINT = "test"

    def init_app(self, app: Flask) -> None:
        # Salvaguarda #1: DATABASE_URL parece apuntar a BD de test
        db_url = os.environ.get("DATABASE_URL", "")
        if self.TEST_DB_NAME_HINT not in db_url.lower():
            raise RuntimeError(
                f"TestingConfig requiere que DATABASE_URL contenga "
                f"'{self.TEST_DB_NAME_HINT}' para evitar tocar una BD real.\n"
                f"Actual: {db_url!r}\n"
                f"Exporta DATABASE_URL=postgresql://...test_db antes de pytest."
            )
        super().init_app(app)


# Mapa para `create_app(config_name)`.
config_map: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "dev": DevelopmentConfig,
    "production": ProductionConfig,
    "prod": ProductionConfig,
    "testing": TestingConfig,
    "test": TestingConfig,
}
