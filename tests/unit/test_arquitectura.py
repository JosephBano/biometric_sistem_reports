"""
Tests que hacen cumplir las reglas de capas del ADR-0001 (`app/__init__.py`):

  - `app/web/*` solo importa de `app/domain/*` (nunca de `db`, `db.queries`
    ni de los módulos legacy top-level como `script`, `analytics`, `horarios`).
  - `app/domain/*` nunca importa de `app/web/*`.
  - `db/queries/*` nunca importa de `app/*` ni de Flask.

Antes de este test la regla solo vivía en docstrings; una violación pasaba
desapercibida en review (ver revisión ADR-0001 del 2026-07-02).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Módulos legacy top-level que `app/domain/*` puede envolver (Fase 4e
# pendiente: migrarlos físicamente y retirar esta lista).
LEGACY_TOP_LEVEL = {
    "script", "analytics", "horarios", "ia_report", "script_docx",
    "sync", "backup", "db",
}


def _imported_names(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(), filename=str(py_file))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
    return names


def _web_files():
    return sorted((ROOT / "app" / "web").glob("*.py"))


def _domain_files():
    return sorted((ROOT / "app" / "domain").glob("*.py"))


def _db_query_files():
    return sorted((ROOT / "db" / "queries").glob("*.py"))


@pytest.mark.parametrize("py_file", _web_files(), ids=lambda p: p.name)
def test_web_no_importa_db_directamente(py_file: Path):
    """`app/web/*` no debe importar `db` ni los módulos legacy top-level."""
    imported = _imported_names(py_file)
    violaciones = imported & LEGACY_TOP_LEVEL
    assert not violaciones, (
        f"{py_file.relative_to(ROOT)} importa {violaciones} directamente; "
        f"debe pasar por app.domain.* (ver ADR-0001)."
    )


@pytest.mark.parametrize("py_file", _domain_files(), ids=lambda p: p.name)
def test_domain_no_importa_web(py_file: Path):
    """`app/domain/*` nunca debe importar de `app/web/*` (evita ciclos)."""
    tree = ast.parse(py_file.read_text(), filename=str(py_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("app.web"), (
                f"{py_file.relative_to(ROOT)} importa de app.web ({node.module})."
            )


@pytest.mark.parametrize("py_file", _db_query_files(), ids=lambda p: p.name)
def test_db_queries_no_importa_app_ni_flask(py_file: Path):
    """`db/queries/*` es capa de datos pura: sin Flask, sin `app.*`."""
    imported = _imported_names(py_file)
    assert "flask" not in imported, f"{py_file.relative_to(ROOT)} importa flask."
    assert "app" not in imported, f"{py_file.relative_to(ROOT)} importa app."


def test_no_quedan_imports_locales_de_db_en_blueprints():
    """
    Los blueprints no deben re-importar `db`/módulos legacy dentro de funciones
    (anti-patrón que el ADR-0001 identificó y pidió eliminar).
    """
    for py_file in _web_files():
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.ImportFrom) and sub.module:
                        top = sub.module.split(".")[0]
                        assert top not in LEGACY_TOP_LEVEL, (
                            f"{py_file.relative_to(ROOT)}::{node.name} importa "
                            f"'{sub.module}' localmente; debe estar a nivel de módulo "
                            f"e ir por app.domain.*."
                        )
