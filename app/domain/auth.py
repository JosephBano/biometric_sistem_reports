"""
Servicio de autenticación (`app/domain/auth.py`).

Responsabilidades:
  - Hash y verificación de contraseñas (bcrypt)
  - Cifrado/descifrado de contraseñas de dispositivos ZK (AES-256-GCM)
  - Login: verificación de credenciales contra `public.usuarios`
  - CRUD de usuarios (wrapper sobre `db.queries.auth`)

Migrado desde `auth.py` (raíz). Diferencias:
  - **Imports top-level** a `db.queries.auth` — sin anti-patrón de imports locales.
  - El módulo es PURO (sin Flask): se puede instanciar desde REPL/tests sin app context.
  - Se completa la firma pública documentada en `docs/ARQUITECTURA.md`.
"""
from __future__ import annotations

import base64
import os
import secrets
from typing import Any

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Imports top-level (rompe el anti-patrón de auth.py original líneas 94, 116,
# 131, 147, 153, 159 que tenían imports locales para evitar ciclos).
# El módulo de queries no importa nada de `app/`, así que no hay ciclo.
from db.queries.auth import (
    activar_usuario_db,
    actualizar_roles_db,
    actualizar_ultimo_acceso,
    contar_intentos_fallidos,
    crear_usuario_db,
    desactivar_usuario_db,
    get_usuario_por_email,
    get_usuario_por_id,
    registrar_audit,
    registrar_login_intento,
)
from db.queries.tenants import get_tenant_by_slug

# ══════════════════════════════════════════════════════════════════════════
# CONTRASEÑAS DE USUARIOS (bcrypt)
# ══════════════════════════════════════════════════════════════════════════


def hash_password(plain: str) -> str:
    """Genera hash bcrypt (coste 12) de la contraseña en texto plano."""
    return bcrypt.hashpw(
        plain.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")


def verificar_password(plain: str, hashed: str) -> bool:
    """Verifica si el texto plano coincide con el hash bcrypt."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return False


def generar_temporary_password(longitud: int = 12) -> str:
    """Genera una contraseña temporal segura (token URL-safe)."""
    return secrets.token_urlsafe(longitud)


# ══════════════════════════════════════════════════════════════════════════
# CONTRASEÑAS DE DISPOSITIVOS ZK (AES-256-GCM)
# ══════════════════════════════════════════════════════════════════════════


def _get_encryption_key() -> bytes:
    key_b64 = os.environ.get("DB_ENCRYPTION_KEY", "").strip()
    if not key_b64:
        raise RuntimeError(
            "DB_ENCRYPTION_KEY no configurada. Genera una con:\n"
            "  python -c \"import secrets,base64; "
            "print(base64.b64encode(secrets.token_bytes(32)).decode())\""
        )
    key = base64.urlsafe_b64decode(key_b64 + "==")
    if len(key) != 32:
        raise ValueError(
            "DB_ENCRYPTION_KEY debe ser de exactamente 32 bytes (256 bits) en base64."
        )
    return key


def encrypt_device_password(plain: str) -> str:
    """
    Cifra la contraseña de dispositivo con AES-256-GCM.
    Formato del resultado: base64(nonce[12] + ciphertext + tag[16]).
    """
    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, plain.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_device_password(enc: str) -> str:
    """Descifra la contraseña de dispositivo. Retorna texto plano."""
    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(enc)
    nonce, ciphertext = raw[:12], raw[12:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


# ══════════════════════════════════════════════════════════════════════════
# AUTENTICACIÓN
# ══════════════════════════════════════════════════════════════════════════


def verificar_login(email: str, password: str) -> dict[str, Any] | None:
    """
    Verifica email + password contra `public.usuarios`.

    Retorna dict del usuario (sin password_hash) o None si falla.
    El llamador debe registrar el intento en `login_intentos`.
    """
    usuario = get_usuario_por_email(email)
    if not usuario:
        return None
    if not verificar_password(password, usuario["password_hash"]):
        return None

    return {
        "id":            usuario["id"],
        "email":         usuario["email"],
        "nombre":        usuario["nombre"],
        "roles":         usuario["roles"],
        "tenant_id":     usuario["tenant_id"],
        "tenant_schema": usuario.get("tenant_schema") or os.environ.get("TENANT_DEFAULT", "istpet"),
        "configuracion": usuario.get("configuracion", {}),
    }


def get_usuario_by_id(usuario_id: str) -> dict[str, Any] | None:
    """Retorna datos del usuario por ID (sin password_hash)."""
    return get_usuario_por_id(usuario_id)


# ══════════════════════════════════════════════════════════════════════════
# CRUD DE USUARIOS
# ══════════════════════════════════════════════════════════════════════════


def crear_usuario(
    tenant_id: str,
    email: str,
    password: str,
    nombre: str,
    roles: list[str],
    configuracion: dict | None = None,
) -> dict[str, Any]:
    """
    Crea un nuevo usuario en `public.usuarios`.

    Retorna el usuario creado (sin password_hash).
    Lanza `ValueError` si el email ya existe.
    """
    try:
        return crear_usuario_db(
            tenant_id,
            email,
            hash_password(password),
            nombre,
            roles,
            configuracion or {},
        )
    except Exception as e:  # noqa: BLE001
        msg = str(e).lower()
        if "unique" in msg or "duplicate" in msg:
            raise ValueError(f"El email '{email}' ya está registrado.") from e
        raise


def actualizar_roles(
    usuario_id: str,
    roles: list[str],
    configuracion: dict | None = None,
) -> bool:
    """Actualiza los roles y opcionalmente la configuración de scopes."""
    return actualizar_roles_db(usuario_id, roles, configuracion)


def desactivar_usuario(usuario_id: str) -> bool:
    """Desactiva un usuario (activo=false)."""
    return desactivar_usuario_db(usuario_id)


def activar_usuario(usuario_id: str) -> bool:
    """Reactiva un usuario (activo=true)."""
    return activar_usuario_db(usuario_id)

# Re-exports de `db` (capa de datos), añadidos para cumplir la regla de
# capas del ADR-0001 (antes: `app/web/auth_bp.py` importaba `db` directo).
