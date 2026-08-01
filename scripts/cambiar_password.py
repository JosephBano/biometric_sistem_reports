"""
Cambia la contraseña de un usuario de `public.usuarios` (bcrypt).

Uso (dentro del contenedor de la app, que ya tiene DATABASE_URL)::

    docker compose exec -it biometrico-app python scripts/cambiar_password.py

Todo se pide por prompt: la contraseña nunca pasa por la shell ni queda en el
historial, y el hash no se copia a mano. Ambos fueron origen de errores reales
(expansión de `$` en bash, comillas de PowerShell, hash truncado al copiar).

Al terminar valida la clave nueva con `verificar_login`, el mismo código que
usa el formulario de login.
"""
from __future__ import annotations

import getpass
import os
import sys

# Ejecutado como `python scripts/cambiar_password.py`, sys.path[0] es
# `scripts/`, no la raíz del repo: sin esto `import app` falla.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.domain.auth import hash_password, verificar_login  # noqa: E402
from db.connection import get_engine  # noqa: E402

LARGO_MINIMO = 8


def main() -> int:
    email = input("Email del usuario: ").strip().lower()
    if not email:
        print("ERROR: email vacío.")
        return 1

    with get_engine().connect() as conn:
        fila = conn.execute(
            text("SELECT nombre, roles, activo FROM public.usuarios WHERE email = :e"),
            {"e": email},
        ).fetchone()

    if fila is None:
        print(f"ERROR: no existe ningún usuario con email {email!r}.")
        print("Listá los existentes con: SELECT email FROM public.usuarios;")
        return 1

    print(f"Usuario: {fila.nombre} | roles: {fila.roles} | activo: {fila.activo}")

    nueva = getpass.getpass("Nueva contraseña: ")
    if len(nueva) < LARGO_MINIMO:
        print(f"ERROR: mínimo {LARGO_MINIMO} caracteres.")
        return 1
    if nueva != getpass.getpass("Repetir contraseña: "):
        print("ERROR: las contraseñas no coinciden.")
        return 1

    with get_engine().connect() as conn:
        resultado = conn.execute(
            text("UPDATE public.usuarios SET password_hash = :h WHERE email = :e"),
            {"h": hash_password(nueva), "e": email},
        )
        conn.commit()

    if resultado.rowcount != 1:
        print(f"ERROR: se actualizaron {resultado.rowcount} filas, se esperaba 1.")
        return 1

    # Validación contra el mismo camino que usa el login del navegador.
    if verificar_login(email, nueva) is None:
        print("ERROR: la contraseña se guardó pero verificar_login la rechaza.")
        return 1

    print(f"OK: contraseña de {email} actualizada y verificada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
