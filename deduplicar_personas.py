"""
Script de deduplicación de personas.

Por cada grupo de personas con el mismo nombre:
  - Si todos los id_en_dispositivo son iguales → fusión automática (segura).
  - Si hay id_en_dispositivo distintos → se omite y se reporta para revisión manual.

La persona canónica es la de menor creado_en (la más antigua del grupo).
Las demás se eliminan después de reasignar asistencias y vínculos de dispositivo.

Uso:
    python deduplicar_personas.py          # dry-run (solo muestra lo que haría)
    python deduplicar_personas.py --apply  # ejecuta los cambios
"""

import sys
from dotenv import load_dotenv
load_dotenv()

from db.connection import get_connection
from sqlalchemy import text


def obtener_grupos_duplicados(conn):
    """
    Retorna dos listas:
      - fusionables: grupos donde todos los id_en_dispositivo son iguales → merge seguro
      - conflictivos: grupos con id_en_dispositivo distintos → revisión manual
    """
    rows = conn.execute(text("""
        SELECT
            p.nombre,
            p.id                    AS persona_id,
            p.creado_en,
            pd.id_en_dispositivo,
            pd.dispositivo_id
        FROM istpet.personas p
        LEFT JOIN istpet.personas_dispositivos pd ON pd.persona_id = p.id AND pd.activo = true
        WHERE p.nombre IN (
            SELECT nombre FROM istpet.personas
            GROUP BY nombre HAVING COUNT(*) > 1
        )
        ORDER BY p.nombre, p.creado_en ASC
    """)).mappings().all()

    grupos = {}
    for r in rows:
        nombre = r["nombre"]
        if nombre not in grupos:
            grupos[nombre] = []
        grupos[nombre].append(dict(r))

    fusionables = {}
    conflictivos = {}

    for nombre, miembros in grupos.items():
        ids_zk = {m["id_en_dispositivo"] for m in miembros if m["id_en_dispositivo"]}
        if len(ids_zk) <= 1:
            fusionables[nombre] = miembros
        else:
            conflictivos[nombre] = miembros

    return fusionables, conflictivos


def fusionar_grupo(conn, nombre, miembros, dry_run=True):
    """
    Fusiona un grupo de personas duplicadas hacia la persona más antigua (canónica).
    Retorna (asistencias_reasignadas, duplicados_eliminados).
    """
    # Ordenar por creado_en para elegir la canónica
    ordenados = sorted(
        [m for m in miembros if m["persona_id"] is not None],
        key=lambda m: m["creado_en"] or ""
    )
    # Desduplicar por persona_id (puede haber múltiples filas por persona si tiene varios dispositivos)
    vistas = set()
    unicas = []
    for m in ordenados:
        if m["persona_id"] not in vistas:
            vistas.add(m["persona_id"])
            unicas.append(m)

    if len(unicas) < 2:
        return 0, 0

    canonical_id = unicas[0]["persona_id"]
    duplicados = [m["persona_id"] for m in unicas[1:]]

    total_asistencias = 0
    total_eliminados = 0

    for dup_id in duplicados:
        # 1. Contar asistencias del duplicado
        n_asis = conn.execute(text(
            "SELECT COUNT(*) FROM istpet.asistencias WHERE persona_id = CAST(:id AS uuid)"
        ), {"id": dup_id}).scalar()

        if not dry_run:
            # 1a. Eliminar asistencias que ya existen en la canónica (misma fecha_hora)
            conn.execute(text("""
                DELETE FROM istpet.asistencias a
                WHERE a.persona_id = CAST(:dup_id AS uuid)
                  AND EXISTS (
                      SELECT 1 FROM istpet.asistencias b
                      WHERE b.persona_id = CAST(:canonical_id AS uuid)
                        AND b.fecha_hora = a.fecha_hora
                  )
            """), {"dup_id": dup_id, "canonical_id": canonical_id})

            # 1b. Reasignar el resto
            conn.execute(text("""
                UPDATE istpet.asistencias
                SET persona_id = CAST(:canonical_id AS uuid)
                WHERE persona_id = CAST(:dup_id AS uuid)
            """), {"dup_id": dup_id, "canonical_id": canonical_id})

            # 2. Reasignar vínculos de dispositivo al canónico
            conn.execute(text("""
                UPDATE istpet.personas_dispositivos
                SET persona_id = CAST(:canonical_id AS uuid), es_principal = false
                WHERE persona_id = CAST(:dup_id AS uuid)
                ON CONFLICT (dispositivo_id, id_en_dispositivo) DO NOTHING
            """), {"dup_id": dup_id, "canonical_id": canonical_id})

            # 3. Eliminar persona duplicada
            conn.execute(text("""
                DELETE FROM istpet.personas WHERE id = CAST(:id AS uuid)
            """), {"id": dup_id})

        total_asistencias += n_asis
        total_eliminados += 1

    return total_asistencias, total_eliminados


def main():
    dry_run = "--apply" not in sys.argv

    if dry_run:
        print("=" * 60)
        print("MODO DRY-RUN — no se modifica nada.")
        print("Ejecuta con --apply para aplicar los cambios.")
        print("=" * 60)
    else:
        print("=" * 60)
        print("MODO APPLY — los cambios serán permanentes.")
        print("=" * 60)

    with get_connection() as conn:
        fusionables, conflictivos = obtener_grupos_duplicados(conn)

        total_grupos = len(fusionables)
        total_duplicados = sum(
            len({m["persona_id"] for m in miembros}) - 1
            for miembros in fusionables.values()
        )
        total_asistencias_afectadas = 0

        print(f"\nGrupos a fusionar automáticamente : {total_grupos}")
        print(f"Personas duplicadas a eliminar    : {total_duplicados}")
        print(f"Casos conflictivos (omitidos)      : {len(conflictivos)}")

        if conflictivos:
            print("\n── Casos conflictivos (revisión manual) ──────────────────")
            for nombre, miembros in conflictivos.items():
                ids_zk = [(m["id_en_dispositivo"], m["dispositivo_id"]) for m in miembros]
                print(f"  {nombre}")
                for id_zk, dev_id in ids_zk:
                    print(f"    · id_en_dispositivo={id_zk}  dispositivo={dev_id}")

        if dry_run:
            print("\nEjemplos de fusiones que se harían (primeros 10):")
            for i, (nombre, miembros) in enumerate(list(fusionables.items())[:10]):
                ids = list({m["persona_id"] for m in miembros})
                ordenados = sorted(
                    [m for m in miembros if m["persona_id"] in ids],
                    key=lambda m: m["creado_en"] or ""
                )
                vistas = set()
                unicas = []
                for m in ordenados:
                    if m["persona_id"] not in vistas:
                        vistas.add(m["persona_id"])
                        unicas.append(m)
                canonical = unicas[0]["persona_id"]
                dups = [m["persona_id"] for m in unicas[1:]]
                print(f"  {nombre}")
                print(f"    Canónica : {canonical}")
                for d in dups:
                    print(f"    Eliminar : {d}")
        else:
            print("\nAplicando fusiones...")
            for nombre, miembros in fusionables.items():
                asis, elim = fusionar_grupo(conn, nombre, miembros, dry_run=False)
                total_asistencias_afectadas += asis

            conn.commit()
            print(f"\n✓ Fusiones aplicadas.")
            print(f"  Personas eliminadas          : {total_duplicados}")
            print(f"  Asistencias reasignadas/elim : {total_asistencias_afectadas}")

        print("\nListo.")


if __name__ == "__main__":
    main()
