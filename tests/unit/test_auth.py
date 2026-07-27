"""
Tests del servicio de auth (`app.domain.auth`).

Cubre:
  - hash/verify bcrypt (round-trip)
  - encrypt/decrypt AES-256-GCM (round-trip)
  - Sin DB_ENCRYPTION_KEY → RuntimeError
  - generar_temporary_password: token URL-safe
"""
from __future__ import annotations

import base64
import os
import secrets

import pytest

# Forzar DB_ENCRYPTION_KEY antes de importar auth.
_TEST_KEY = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
os.environ.setdefault("DB_ENCRYPTION_KEY", _TEST_KEY)


from app.domain.auth import (  # noqa: E402
    decrypt_device_password,
    encrypt_device_password,
    generar_temporary_password,
    hash_password,
    verificar_password,
)


class TestBcrypt:

    def test_hash_y_verify_roundtrip(self):
        plain = "MiPasswordSegura123"
        hashed = hash_password(plain)
        assert hashed != plain
        assert verificar_password(plain, hashed) is True

    def test_verify_password_distinta_que_el_hash(self):
        hashed = hash_password("correcto")
        assert verificar_password("incorrecto", hashed) is False

    def test_verify_password_con_hash_invalido_devuelve_false(self):
        """Un hash malformado no debe lanzar excepción."""
        assert verificar_password("cualquiera", "hash-no-valido") is False

    def test_hash_produce_sal_diferente(self):
        """bcrypt genera salts aleatorias → dos hashes del mismo password difieren."""
        h1 = hash_password("test")
        h2 = hash_password("test")
        assert h1 != h2
        assert verificar_password("test", h1)
        assert verificar_password("test", h2)


class TestAESGCM:

    def test_encrypt_y_decrypt_roundtrip(self):
        plain = "zk_password_42"
        enc = encrypt_device_password(plain)
        assert enc != plain
        assert decrypt_device_password(enc) == plain

    def test_encrypt_produce_sal_diferente(self):
        """AES-GCM usa nonce aleatorio → dos cifrados del mismo plain difieren."""
        a = encrypt_device_password("password")
        b = encrypt_device_password("password")
        assert a != b
        assert decrypt_device_password(a) == "password"
        assert decrypt_device_password(b) == "password"

    def test_sin_db_encryption_key_lanza_error(self, monkeypatch):
        monkeypatch.delenv("DB_ENCRYPTION_KEY", raising=False)
        with pytest.raises(RuntimeError, match="DB_ENCRYPTION_KEY"):
            encrypt_device_password("x")

    def test_db_encryption_key_invalida_lanza_valueerror(self, monkeypatch):
        # 32 bytes hex → demasiado corto
        monkeypatch.setenv("DB_ENCRYPTION_KEY", "Y2lubyBjb3JyZWN0bw==")
        with pytest.raises(ValueError, match="32 bytes"):
            encrypt_device_password("x")


class TestTemporaryPassword:

    def test_genera_password_por_defecto(self):
        p = generar_temporary_password()
        assert isinstance(p, str)
        assert len(p) >= 12

    def test_genera_password_personalizado(self):
        p = generar_temporary_password(longitud=24)
        assert len(p) >= 24

    def test_dos_passwords_son_distintas(self):
        p1 = generar_temporary_password()
        p2 = generar_temporary_password()
        assert p1 != p2
