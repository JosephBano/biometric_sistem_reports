#!/usr/bin/env python3
"""
Genera docs/ER.md a partir de db/schema.py de forma automática.

Uso:
    python docs/generate_er.py           # genera ER.md
    python docs/generate_er.py --verify # solo verifica sintaxis del DDL
"""

import re
import sys
import textwrap
from pathlib import Path

SCHEMA_FILE = Path(__file__).parent.parent / "db" / "schema.py"
OUTPUT_FILE = Path(__file__).parent / "ER.md"


def parse_table_block(block: str) -> dict:
    name = re.search(r"CREATE TABLE IF NOT EXISTS (\S+)\s*\(", block)
    columns = []
    constraints = []
    for line in block.split("\n"):
        line = line.rstrip()
        if not line or line.startswith("--") or line.startswith("CREATE"):
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent < 4:
            constraints.append(stripped)
        else:
            col_match = re.match(r"(\w+)\s+(.+?),?\s*$", stripped)
            if col_match:
                col_name = col_match.group(1)
                col_def = col_match.group(2).rstrip(",")
                is_pk = "PRIMARY KEY" in col_def.upper()
                is_fk = "REFERENCES" in col_def.upper()
                is_unique = "UNIQUE" in col_def.upper()
                col_type = re.sub(r"(NOT NULL|NULL|DEFAULT.*|CHECK.*|REFERENCES.*)", "", col_def).strip()
                col_type = re.sub(r"\s+", " ", col_type)
                fk_match = re.search(r"REFERENCES\s+\w+(?:\([^)]+\))?\.\w+\.(\w+).*ON DELETE (\w+)", col_def, re.IGNORECASE)
                fk_ref = f"→ `{fk_match.group(4)}`" if fk_match else None
                on_delete = fk_match.group(5) if fk_match else None
                default_match = re.search(r"DEFAULT\s+('[^']*'|\"[^\"]*\"|\S+)", col_def)
                default_val = default_match.group(1) if default_match else None
                columns.append({
                    "name": col_name,
                    "type": col_type,
                    "pk": is_pk,
                    "fk": is_fk,
                    "fk_ref": fk_ref,
                    "on_delete": on_delete,
                    "unique": is_unique,
                    "default": default_val,
                    "nullable": "NOT NULL" not in col_def.upper(),
                })
    return {
        "name": name.group(1) if name else "unknown",
        "columns": columns,
        "constraints": [c for c in constraints if c.strip()],
    }


def parse_schema_py() -> list:
    content = SCHEMA_FILE.read_text()
    blocks = re.findall(
        r"CREATE TABLE IF NOT EXISTS \w+[^;]+;",
        content,
        re.DOTALL | re.MULTILINE
    )
    tables = []
    current_schema = "public"
    for block in blocks:
        if block.startswith("CREATE SCHEMA"):
            m = re.search(r"CREATE SCHEMA IF NOT EXISTS (\w+)", block)
            if m:
                current_schema = m.group(1)
        elif "CREATE TABLE" in block:
            t = parse_table_block(block)
            t["schema"] = current_schema
            tables.append(t)
    return tables


def table_md(t: dict) -> str:
    full_name = f"{t['schema']}.{t['name']}" if t["schema"] != "public" else t["name"]
    lines = [f"#### `{full_name}`", ""]
    if t.get("description"):
        lines.append(t["description"])
    lines.append("| Columna | Tipo | Constraints | Descripción |")
    lines.append("|---------|------|-------------|-------------|")
    for col in t["columns"]:
        constraints = []
        if col["pk"]:
            constraints.append("PK")
        if col["fk"]:
            constraints.append(f"FK {col['fk_ref']} ON DELETE {col['on_delete']}")
        if col["unique"]:
            constraints.append("UNIQUE")
        if not col["nullable"]:
            constraints.append("NOT NULL")
        if col["default"]:
            constraints.append(f"DEFAULT {col['default']}")
        const_str = ", ".join(constraints) if constraints else "—"
        desc = "—" if not constraints else ""
        lines.append(f"| `{col['name']}` | {col['type']} | {const_str} | {desc} |")
    return "\n".join(lines)


def generate_er_markdown(tables: list) -> str:
    blocks = {
        "public": [],
        "Bloque 1": [],
        "Bloque 2": [],
        "Bloque 3": [],
        "Bloque 3B": [],
        "Bloque 4": [],
        "Bloque 5": [],
        "Bloque 6": [],
    }
    current_block = None
    for t in tables:
        if t["schema"] == "public":
            blocks["public"].append(t)
        elif any(x in t["name"] for x in ["sedes","dispositivos","sync_estado","sync_log","feriados"]):
            blocks["Bloque 1"].append(t)
        elif any(x in t["name"] for x in ["tipos_persona","grupos","categorias"]):
            blocks["Bloque 2"].append(t)
        elif any(x in t["name"] for x in ["usuarios_zk","personas","personas_dispositivos"]):
            blocks["Bloque 3"].append(t)
        elif "grupos_periodo" in t["name"]:
            blocks["Bloque 3B"].append(t)
        elif "periodos_vigencia" in t["name"]:
            blocks["Bloque 4"].append(t)
        elif any(x in t["name"] for x in ["config_ciclo","plantillas_horario","asignaciones_horario"]):
            blocks["Bloque 5"].append(t)
        else:
            blocks["Bloque 6"].append(t)

    sections = [
        ("## Esquema Público (`public`)", blocks["public"], "Estas tablas viven en el schema `public` y son compartidas por todos los tenants."),
        ("## Esquema Tenant (`{slug}`)", [], None),
        ("### BLOQUE 1 — Infraestructura", blocks["Bloque 1"], None),
        ("### BLOQUE 2 — Configuración del Tenant", blocks["Bloque 2"], None),
        ("### BLOQUE 3 — Personas y Vinculación Biométrica", blocks["Bloque 3"], None),
        ("### BLOQUE 3B — Períodos Grupales", blocks["Bloque 3B"], None),
        ("### BLOQUE 4 — Vigencia", blocks["Bloque 4"], None),
        ("### BLOQUE 5 — Horarios", blocks["Bloque 5"], None),
        ("### BLOQUE 6 — Asistencia y Seguimiento", blocks["Bloque 6"], None),
    ]

    out = []
    out.append("# Modelo Entidad-Relación — Base de Datos Biométrico RRHH")
    out.append("")
    out.append("> **Fuente:** `db/schema.py` — Generado automáticamente por `docs/generate_er.py`")
    out.append("")
    for section in sections:
        title, tbls, desc = section
        if tbls is None:
            out.append("")
            out.append(title)
            continue
        if not tbls:
            continue
        out.append("")
        out.append(title)
        if desc:
            out.append("")
            out.append(desc)
        out.append("")
        for t in tbls:
            out.append(table_md(t))
            out.append("")

    return "\n".join(out)


def main():
    verify_only = "--verify" in sys.argv or "--verify-only" in sys.argv

    if not SCHEMA_FILE.exists():
        print(f"ERROR: {SCHEMA_FILE} no encontrado", file=sys.stderr)
        sys.exit(1)

    if verify_only:
        print("Verificando sintaxis de db/schema.py...")
        try:
            compile(SCHEMA_FILE.read_text(), str(SCHEMA_FILE), "exec")
            print("OK: db/schema.py sintaxis válida")
        except SyntaxError as e:
            print(f"ERROR de sintaxis: {e}", file=sys.stderr)
            sys.exit(1)
        return

    print(f"Leyendo {SCHEMA_FILE}...")
    tables = parse_schema_py()
    print(f"  {len(tables)} tablas encontradas")

    er_md = generate_er_markdown(tables)

    OUTPUT_FILE.write_text(er_md)
    print(f"Generado: {OUTPUT_FILE}")
    print(f"  {OUTPUT_FILE.stat().st_size} bytes")


if __name__ == "__main__":
    main()
