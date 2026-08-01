"""
Migra asignaciones_horario 1:1 a propuesta de defaults de grupo funcional.

NO escribe en BD. Solo emite un CSV propuesto para revisión del admin.
El CSV contiene columnas:

  - persona_id
  - nombre
  - plantilla_id
  - plantilla_nombre
  - tipo_persona_id
  - grupo_id        (operativo)
  - sede_id

Uso:
    python scripts/migrar_asignaciones_a_defaults.py --tenant istpet \\
        --out /tmp/propuesta_migracion_horarios.csv

Reglas (ADR-0003 Fase 5):
  - Solo se incluyen asignaciones con `ciclo_semanas = 1` (legacy 1:1).
  - Solo vigentes (`fecha_fin IS NULL`).
  - El admin decide manualmente qué aplicar y cómo agrupar por gf.
"""
import argparse
import csv
import os

from sqlalchemy import text

# Permitir imports desde raíz.
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_connection, validate_schema_name  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Propone migración de asignaciones_horario 1:1 a defaults "
            "de grupo funcional (ADR-0003, plan Tarea 7.1)."
        ),
    )
    parser.add_argument(
        "--tenant",
        default=os.environ.get("TENANT_DEFAULT", "istpet"),
        help="Schema del tenant (default: TENANT_DEFAULT env var).",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Ruta del CSV propuesto para revisión.",
    )
    args = parser.parse_args()

    schema = validate_schema_name(args.tenant)

    # Query el reporte de asignaciones 1:1 vigentes.
    with get_connection(schema) as conn:
        rows = conn.execute(
            text("""
                SELECT p.id::text AS persona_id,
                       p.nombre,
                       ah.plantilla_id::text,
                       ph.nombre AS plantilla_nombre,
                       p.tipo_persona_id::text AS tipo_persona_id,
                       p.grupo_id::text AS grupo_id,
                       p.sede_id::text AS sede_id
                FROM asignaciones_horario ah
                JOIN plantillas_horario ph
                  ON ph.id = ah.plantilla_id
                JOIN personas p
                  ON p.id = ah.persona_id
                WHERE ah.ciclo_semanas = 1
                  AND ah.fecha_fin IS NULL
                ORDER BY p.nombre
            """)
        ).fetchall()

    columnas = [
        "persona_id",
        "nombre",
        "plantilla_id",
        "plantilla_nombre",
        "tipo_persona_id",
        "grupo_id",
        "sede_id",
    ]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(columnas)
        for row in rows:
            w.writerow([
                str(c) if c is not None else "" for c in row
            ])

    print(
        f"Propuesta escrita en {args.out}: {len(rows)} filas. "
        "Revisar manualmente y aplicar con la asignación masiva "
        "/api/asignacion-masiva/grupo-funcional."
    )


if __name__ == "__main__":
    main()
