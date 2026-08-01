"""
Impide URLs absolutas que ignoren el prefijo de montaje de la app.

Motivación (incidente de producción 2026-07-28): "no puedo desactivar a
las personas". El modal de edición hacía

    document.getElementById('formEditarPersona').action = '/personas/' + id;

La app se monta bajo `/biometrico` vía `DispatcherMiddleware` (ver
`wsgi.py`), así que el POST salía a `/personas/<id>` y devolvía 404. El
mismo patrón estaba repetido en 5 templates: personas, usuarios, tenants,
grupos y grupos funcionales — o sea que editar/desactivar estaba roto en
todas esas pantallas.

En desarrollo local (sin prefijo) estas URLs funcionan, por eso el bug
solo se manifestaba en producción y ningún test lo veía.

Convención del proyecto:
  - Templates Jinja → `{{ url_for('blueprint.endpoint') }}`
  - JavaScript      → `window.APP_BASE` (definido en `base.html` a partir
                       de `request.script_root`) o pasar una ruta relativa
                       a `apiCall`/`API.*`, que ya anteponen la base.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]

# Asignaciones de URL absoluta a atributos de navegación/envío.
# Ej: `form.action = '/personas/' + id`  |  `href="/admin/grupos"`
_ASIGNACION_ABSOLUTA = re.compile(
    r"""(?:\.action|\.href|href=|\.src)\s*=?\s*['"]/(?!/)[a-zA-Z]"""
)

# Rutas que sí pueden ser absolutas: estáticos servidos por el propio
# prefijo se resuelven con url_for, y las anclas internas no navegan.
_PERMITIDAS = ("#", "//")


def _archivos_a_revisar():
    templates = sorted((ROOT / "templates").rglob("*.html"))
    scripts = sorted((ROOT / "static" / "js").rglob("*.js"))
    return templates + scripts


def _lineas_sospechosas(path: Path) -> list[tuple[int, str]]:
    hallazgos = []
    for n, linea in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not _ASIGNACION_ABSOLUTA.search(linea):
            continue
        # Exentas: ya usan la base o el helper de Jinja.
        if "APP_BASE" in linea or "url_for" in linea:
            continue
        if any(p in linea for p in _PERMITIDAS):
            continue
        hallazgos.append((n, linea.strip()))
    return hallazgos


@pytest.mark.parametrize(
    "archivo", _archivos_a_revisar(), ids=lambda p: str(p.relative_to(ROOT)),
)
def test_sin_urls_absolutas_que_ignoren_el_prefijo(archivo: Path):
    """Ninguna URL de navegación puede saltarse `APP_BASE`/`url_for`.

    La app vive bajo `/biometrico`; una ruta absoluta escrita a mano
    produce un 404 en producción aunque funcione en local.
    """
    hallazgos = _lineas_sospechosas(archivo)
    assert not hallazgos, (
        f"{archivo.relative_to(ROOT)} tiene URL(s) absolutas que ignoran el "
        f"prefijo de montaje:\n"
        + "\n".join(f"  L{n}: {txt}" for n, txt in hallazgos)
        + "\n\nUsa `{{ url_for('bp.endpoint') }}` en Jinja o "
          "`(window.APP_BASE || '') + '/ruta'` en JS."
    )
