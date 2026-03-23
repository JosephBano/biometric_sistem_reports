"""
Módulo de autenticación — Fase 2.

Responsabilidades:
- Hash y verificación de contraseñas (bcrypt)
- Cifrado/descifrado de contraseñas de dispositivos ZK (AES-256-GCM)
- Login / logout con registro en audit_log
- CRUD de usuarios en public.usuarios
"""

import os
import base64
import secrets

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


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
    except Exception:
        return False


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
    key = base64.b64decode(key_b64)
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

def verificar_login(email: str, password: str) -> dict | None:
    """
    Verifica email + password contra public.usuarios.
    Retorna dict del usuario (sin password_hash) o None si las credenciales fallan.
    El llamador debe registrar el intento en login_intentos.
    """
    from db.queries.auth import get_usuario_por_email

    usuario = get_usuario_por_email(email)
    if not usuario:
        return None
    if not verificar_password(password, usuario["password_hash"]):
        return None

    # Retornar sin exponer el hash
    return {
        "id":             usuario["id"],
        "email":          usuario["email"],
        "nombre":         usuario["nombre"],
        "roles":          usuario["roles"],
        "tenant_id":      usuario["tenant_id"],
        "tenant_schema":  usuario.get("tenant_schema") or os.environ.get("TENANT_DEFAULT", "istpet"),
        "configuracion":  usuario.get("configuracion", {}),
    }


def get_usuario_by_id(usuario_id: str) -> dict | None:
    """Retorna datos del usuario por ID (sin password_hash)."""
    from db.queries.auth import get_usuario_por_id
    return get_usuario_por_id(usuario_id)


# ══════════════════════════════════════════════════════════════════════════
# CRUD DE USUARIOS
# ══════════════════════════════════════════════════════════════════════════

def crear_usuario(tenant_id: str, email: str, password: str, nombre: str,
                  roles: list, configuracion: dict = None) -> dict:
    """
    Crea un nuevo usuario en public.usuarios.
    Retorna el usuario creado (sin password_hash).
    Lanza ValueError si el email ya existe.
    """
    from db.queries.auth import crear_usuario_db
    try:
        return crear_usuario_db(
            tenant_id, email, hash_password(password),
            nombre, roles, configuracion or {}
        )
    except Exception as e:
        msg = str(e).lower()
        if "unique" in msg or "duplicate" in msg:
            raise ValueError(f"El email '{email}' ya está registrado.")
        raise


def actualizar_roles(usuario_id: str, roles: list,
                     configuracion: dict = None) -> bool:
    """Actualiza los roles y configuración de scopes de un usuario."""
    from db.queries.auth import actualizar_roles_db
    return actualizar_roles_db(usuario_id, roles, configuracion)


def desactivar_usuario(usuario_id: str) -> bool:
    """Desactiva un usuario (activo=false)."""
    from db.queries.auth import desactivar_usuario_db
    return desactivar_usuario_db(usuario_id)


def activar_usuario(usuario_id: str) -> bool:
    """Reactiva un usuario (activo=true)."""
    from db.queries.auth import activar_usuario_db
    return activar_usuario_db(usuario_id)
