#!/usr/bin/env python3
"""
Script CLI para crear el primer superadmin del sistema.

Uso:
    python crear_superadmin.py --email admin@istpet.edu.ec --nombre "Administrador"

Si omite --password se le pedirá de forma interactiva (sin eco).

Requiere que DATABASE_URL esté configurado (en .env o en el entorno).
"""

import argparse
import getpass
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    if os.path.exists(".env"):
        with open(".env", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if (v.startswith('"') and v.endswith('"')) or \
                       (v.startswith("'") and v.endswith("'")):
                        v = v[1:-1]
                    os.environ.setdefault(k, v)


def main():
    parser = argparse.ArgumentParser(
        description="Crea el primer superadmin del sistema de asistencia biométrica."
    )
    parser.add_argument("--email",    required=True,  help="Email del superadmin")
    parser.add_argument("--nombre",   required=True,  help="Nombre completo")
    parser.add_argument("--password", default=None,   help="Contraseña (se pedirá si no se indica)")
    parser.add_argument("--tenant",   default=None,
                        help="Slug del tenant (por defecto: TENANT_DEFAULT del .env)")
    args = parser.parse_args()

    # Obtener contraseña de forma segura
    if args.password:
        password = args.password
    else:
        password = getpass.getpass(f"Contraseña para {args.email}: ")
        confirm  = getpass.getpass("Confirmar contraseña: ")
        if password != confirm:
            print("ERROR: Las contraseñas no coinciden.", file=sys.stderr)
            sys.exit(1)

    if len(password) < 8:
        print("ERROR: La contraseña debe tener al menos 8 caracteres.", file=sys.stderr)
        sys.exit(1)

    tenant_slug = args.tenant or os.environ.get("TENANT_DEFAULT", "istpet")

    # Importar módulos de DB (después de configurar el entorno)
    try:
        from db.connection import get_engine
        from sqlalchemy import text
        import auth as auth_module
    except ImportError as e:
        print(f"ERROR: No se pudieron importar los módulos necesarios: {e}", file=sys.stderr)
        print("Asegúrese de ejecutar desde el directorio raíz del proyecto.", file=sys.stderr)
        sys.exit(1)

    # Verificar conexión
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"✓ Conexión a la base de datos OK")
    except Exception as e:
        print(f"ERROR: No se pudo conectar a la base de datos: {e}", file=sys.stderr)
        sys.exit(1)

    # Obtener tenant_id
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id::text FROM public.tenants WHERE slug = :slug"),
                {"slug": tenant_slug},
            ).fetchone()
        if not row:
            print(f"ERROR: No existe el tenant '{tenant_slug}'. "
                  "Ejecute la aplicación al menos una vez para inicializar la BD.",
                  file=sys.stderr)
            sys.exit(1)
        tenant_id = row[0]
        print(f"✓ Tenant '{tenant_slug}' encontrado (id={tenant_id})")
    except Exception as e:
        print(f"ERROR obteniendo tenant: {e}", file=sys.stderr)
        sys.exit(1)

    # Verificar que el email no exista
    try:
        from db.queries.auth import get_usuario_por_email
        if get_usuario_por_email(args.email):
            print(f"AVISO: Ya existe un usuario con el email '{args.email}'.")
            resp = input("¿Desea continuar y crear otro? (s/N): ").strip().lower()
            if resp != "s":
                print("Operación cancelada.")
                sys.exit(0)
    except Exception as e:
        print(f"AVISO: No se pudo verificar email existente: {e}")

    # Crear el superadmin
    try:
        usuario = auth_module.crear_usuario(
            tenant_id=tenant_id,
            email=args.email,
            password=password,
            nombre=args.nombre,
            roles=["superadmin"],
        )
        print(f"\n✓ Superadmin creado exitosamente:")
        print(f"  ID:     {usuario['id']}")
        print(f"  Email:  {usuario['email']}")
        print(f"  Nombre: {usuario['nombre']}")
        print(f"  Roles:  {usuario['roles']}")
        print(f"\nPuede iniciar sesión en la aplicación con estas credenciales.")
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR creando usuario: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
