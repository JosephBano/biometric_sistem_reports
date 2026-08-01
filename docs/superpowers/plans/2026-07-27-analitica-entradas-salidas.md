# Analítica de entradas y salidas por persona (con filtro opcional por grupo funcional) — Plan de Implementación

> **Para implementadores:** Plan ejecuta tarea por tarea. Checkboxes (`- [ ]`) marcan progreso. TDD donde aplique (test rojo → verificación → impl mínima → test verde → commit). Sin emojis en código ni commits. Mensajes de commit en español siguiendo el estilo del repo (`feat:`, `fix:`, `refactor:`).

**Goal:** Entregar la vista analítica del requisito `docs/superpowers/specs/2026-07-27-requisito-analitica-grupo-funcional.md`: tabla cronológica de entradas/salidas filtrable por persona (siempre) o por grupo funcional (cuando el feature flag del tenant y la tabla `persona_grupos_funcionales` existan), con paginación server-side, RBAC/alcance, auditoría, normalización de tipo e índice condicionado a EXPLAIN.

**Architecture:**
- 1 módulo nuevo en `db/queries/` (consultas SQL tipadas para la BD del tenant).
- 1 módulo nuevo en `app/domain/` (servicio puro que orquesta queries, RBAC, paginación, auditoría).
- 1 endpoint nuevo + 1 vista nueva en `app/web/analytics_bp.py` (sin nuevos decoradores; reusa `@require_role`).
- 1 template nuevo `templates/analytics_entradas_salidas.html` (no modifica `templates/analytics.html`).
- Sin migración Alembic (la spec lo prohíbe). Sin nuevos índices (la spec exige EXPLAIN en staging primero).
- Detección de disponibilidad de `grupos_funcionales` vía `information_schema.tables` (sin `try/except` como flujo normal).

**Tech Stack:** Python 3.12 · Flask 3 (App Factory) · SQLAlchemy 2 (Core/text) · PostgreSQL 16 · Bootstrap 5.3 + plain JS · `pytest` (unit + integration).

---

## File Structure (mapa de cambios)

```
biometric_sistem_reports/
├── db/
│   ├── queries/
│   │   └── asistencias_entradas_salidas.py   # NUEVO: queries + helper puro
│   └── __init__.py                           # MOD: re-exportar funciones públicas
├── app/
│   ├── domain/
│   │   └── analytics_entradas_salidas.py     # NUEVO: servicio de orquestación
│   └── web/
│       └── analytics_bp.py                   # MOD: añadir 2 rutas (GET vista + GET API)
├── templates/
│   └── analytics_entradas_salidas.html       # NUEVO: form + tabla + paginación
└── tests/
    ├── unit/
    │   └── test_analytics_entradas_salidas_puro.py   # NUEVO: tests del servicio (sin BD)
    └── integration/
        └── test_analytics_entradas_salidas_bp.py     # NUEVO: tests del endpoint (con pgserver)
```

**Archivos NO modificados (referenciados, no tocados):**
- `app/domain/analytics.py` — se mantiene intacto; el nuevo servicio vive en su propio módulo para no acoplar.
- `app/web/reports_bp.py` — la spec menciona endpoints parcialmente ahí pero el blueprint correcto es `analytics_bp.py` (donde ya vive `/analytics`). No se toca.
- `templates/analytics.html` — se mantiene intacto; se añade una pestaña/enlace al nuevo recurso, no se modifica el archivo.
- `db/queries/asistencias.py` — se mantiene intacto; las nuevas queries son específicas del caso de uso analítico.

---

## Convenciones del plan

- **Tareas pequeñas** (2-5 min cada paso). Si una tarea > 30 min, partirla.
- **TDD obligatorio** para todo módulo/servicio nuevo.
- **Cada tarea cierra con un commit.**
- **Sin emojis** en código, snippets ni mensajes de commit.
- **Rango semiabierto** consistente con `db/queries/asistencias.py:consultar_asistencias`: `[fecha_inicio, fecha_fin + 1 day)` en timestamp.
- **Paginación**: `page` (default 1, min 1), `per_page` (default 50, max 200, min 1).
- **Auditoría**: 1 fila por llamada exitosa en `public.audit_log` con `accion='analytics_entradas_salidas_consultar'`. NO se auditan respuestas 4xx por validación (ruido); SÍ se auditan 403 (acceso denegado, para detectar intentos).
- **Feature flag**: `tenant.configuracion['horario_por_grupo']` (leído de `g.tenant`). Más `information_schema.tables` para confirmar que `persona_grupos_funcionales` existe en el schema del tenant. **Ambos** deben ser verdaderos para habilitar el filtro por grupo funcional.

---

## Tarea 1: Helper puro `normalizar_tipo_marcacion` (TDD, sin BD)

**Files:**
- Create: `db/queries/asistencias_entradas_salidas.py`
- Create: `tests/unit/test_asistencias_entradas_salidas.py`

- [ ] **Paso 1: Escribir el test RED**

`tests/unit/test_asistencias_entradas_salidas.py`:

```python
"""
Tests unitarios de `db.queries.asistencias_entradas_salidas`.

Solo cubre el helper puro `normalizar_tipo_marcacion` (TDD).
Las funciones que tocan BD se cubren por integración.
"""
from __future__ import annotations

import pytest

from db.queries.asistencias_entradas_salidas import normalizar_tipo_marcacion


class TestNormalizarTipoMarcacion:

    @pytest.mark.parametrize("raw,esperado", [
        ("entrada", "entrada"),
        ("salida", "salida"),
        ("ENTRADA", "entrada"),
        ("SALIDA", "salida"),
        ("Entrada", "entrada"),
        ("0", "entrada"),
        ("1", "salida"),
        ("check-in", "entrada"),
        ("check-in", "entrada"),
        ("check-out", "salida"),
        ("in", "entrada"),
        ("out", "salida"),
    ])
    def test_valores_reconocidos(self, raw, esperado):
        assert normalizar_tipo_marcacion(raw) == esperado

    @pytest.mark.parametrize("raw", [None, "", "desconocido", "x", "999"])
    def test_valores_desconocidos_retornan_otro(self, raw):
        assert normalizar_tipo_marcacion(raw) == "otro"

    def test_espacios_se_trimean(self):
        assert normalizar_tipo_marcacion("  entrada  ") == "entrada"
        assert normalizar_tipo_marcacion(" 0 ") == "entrada"
```

- [ ] **Paso 2: Verificar que el test falla**

Run: `pytest tests/unit/test_asistencias_entradas_salidas.py -v`
Expected: `ModuleNotFoundError` o `ImportError` porque `db/queries/asistencias_entradas_salidas.py` aún no existe.

- [ ] **Paso 3: Escribir la implementación mínima**

`db/queries/asistencias_entradas_salidas.py`:

```python
"""
Consultas y helpers para la vista analítica de entradas/salidas por persona
(`db/queries/asistencias_entradas_salidas.py`).

Caso de uso: requisito `docs/superpowers/specs/2026-07-27-requisito-analitica-grupo-funcional.md`.
NO depende del ADR 0003 (modelo de horarios por grupo funcional). Cuando ese
ADR esté aplicado, las queries contra `persona_grupos_funcionales` empiezan
a tener sentido (filtrado por grupo funcional vigente).

API pública:
  - `normalizar_tipo_marcacion(raw)`             → helper puro (testeable sin BD)
  - `grupos_funcionales_disponibles(schema)`     → bool (lee information_schema)
  - `listar_marcaciones_por_persona(...)`        → list[dict]
  - `contar_marcaciones_por_persona(...)`        → int
  - `listar_marcaciones_por_grupo_funcional(...)`→ list[dict]
  - `contar_marcaciones_por_grupo_funcional(...)`→ int
  - `get_personas_por_grupo_funcional_vigente(...)` → list[str] (UUIDs)
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from db.connection import get_connection, validate_schema_name


# Mapeo canónico de valores crudos a tipo normalizado.
# El ZK típicamente envía 0 (entrada) / 1 (salida) en punch_raw, mientras
# que el campo `tipo` puede venir como "entrada"/"salida" o "ENTRADA"/"SALIDA"
# dependiendo del driver. Mantenemos una tabla explícita en vez de heurísticas.
_TIPO_CANONICO = {
    "entrada": "entrada",
    "entrada_": "entrada",
    "entrada ": "entrada",
    "in": "entrada",
    "check-in": "entrada",
    "check_in": "entrada",
    "0": "entrada",
    "1": "salida",
    "salida": "salida",
    "salida_": "salida",
    "salida ": "salida",
    "out": "salida",
    "check-out": "salida",
    "check_out": "salida",
}


def normalizar_tipo_marcacion(raw: Optional[str]) -> str:
    """
    Convierte el valor crudo de `asistencias.tipo` (o punch_raw convertido a str)
    en uno de: `"entrada"`, `"salida"`, `"otro"`.

    - Compara en minúsculas con strip.
    - Si el valor no está en el mapeo canónico → `"otro"` (defensivo).
    - NO lanza excepciones; siempre retorna string.
    """
    if raw is None:
        return "otro"
    key = str(raw).strip().lower()
    if not key:
        return "otro"
    return _TIPO_CANONICO.get(key, "otro")


__all__ = ["normalizar_tipo_marcacion"]
```

- [ ] **Paso 4: Verificar que el test pasa**

Run: `pytest tests/unit/test_asistencias_entradas_salidas.py -v`
Expected: `8 passed` (los `parametrize` se expanden; contar verificaciones individuales).

- [ ] **Paso 5: Commit**

```bash
git add db/queries/asistencias_entradas_salidas.py tests/unit/test_asistencias_entradas_salidas.py
git commit -m "feat(db): helper normalizar_tipo_marcacion para analitica E/S"
```

---

## Tarea 2: Helper `grupos_funcionales_disponibles` (TDD, con BD)

**Files:**
- Modify: `db/queries/asistencias_entradas_salidas.py`
- Modify: `tests/unit/test_asistencias_entradas_salidas.py` (añadir test)

- [ ] **Paso 1: Añadir el test RED**

Agregar al final de `tests/unit/test_asistencias_entradas_salidas.py`:

```python
from unittest.mock import MagicMock, patch

from db.queries import asistencias_entradas_salidas as aes


class TestGruposFuncionalesDisponibles:

    def test_true_si_tabla_existe(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (1,)
        with patch.object(aes, "get_connection") as mock_gc:
            mock_gc.return_value.__enter__.return_value = mock_conn
            assert aes.grupos_funcionales_disponibles("istpet") is True
        # Validar que la query usó information_schema
        sql_llamado = mock_conn.execute.call_args[0][0]
        assert "information_schema.tables" in str(sql_llamado).lower()
        assert "persona_grupos_funcionales" in str(mock_conn.execute.call_args[0][1]["tabla"])

    def test_false_si_tabla_no_existe(self):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (0,)
        with patch.object(aes, "get_connection") as mock_gc:
            mock_gc.return_value.__enter__.return_value = mock_conn
            assert aes.grupos_funcionales_disponibles("istpet") is False

    def test_false_si_get_connection_falla(self):
        """Si no se puede conectar a la BD del tenant, devolvemos False (fail-safe)."""
        with patch.object(aes, "get_connection") as mock_gc:
            mock_gc.side_effect = RuntimeError("DATABASE_URL no configurado")
            assert aes.grupos_funcionales_disponibles("istpet") is False
```

- [ ] **Paso 2: Verificar que el test falla**

Run: `pytest tests/unit/test_asistencias_entradas_salidas.py::TestGruposFuncionalesDisponibles -v`
Expected: `ImportError` o `AttributeError` porque `grupos_funcionales_disponibles` aún no existe.

- [ ] **Paso 3: Implementación mínima**

Añadir a `db/queries/asistencias_entradas_salidas.py` (justo antes de `__all__`):

```python
def grupos_funcionales_disponibles(schema: str) -> bool:
    """
    Devuelve `True` si la tabla `<schema>.persona_grupos_funcionales` existe.

    Detección robusta vía `information_schema.tables` (NO vía try/except).
    Si falla la conexión, devuelve `False` (fail-safe: preferimos rechazar el
    parámetro `grupo_funcional_id` antes que aceptar un filtro que va a fallar).

    El spec (`2026-07-27-requisito-analitica-grupo-funcional.md`) dice que el
    feature flag del tenant habilita el filtro. Este helper es la segunda
    condición: la tabla también debe existir. Si el flag está activo pero la
    tabla no, devolvemos `False` y el endpoint rechaza `grupo_funcional_id`
    con 400 `grupo_funcional_no_disponible`. NO capturamos `ProgrammingError`
    como flujo normal.
    """
    schema = validate_schema_name(schema)
    try:
        with get_connection(schema) as conn:
            row = conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = :schema
                      AND table_name   = :tabla
                """),
                {"schema": schema, "tabla": "persona_grupos_funcionales"},
            ).fetchone()
        return bool(row and row[0] > 0)
    except Exception:
        return False


# Extender __all__
__all__ = [
    "normalizar_tipo_marcacion",
    "grupos_funcionales_disponibles",
]
```

- [ ] **Paso 4: Verificar que el test pasa**

Run: `pytest tests/unit/test_asistencias_entradas_salidas.py::TestGruposFuncionalesDisponibles -v`
Expected: `3 passed`.

- [ ] **Paso 5: Commit**

```bash
git add db/queries/asistencias_entradas_salidas.py tests/unit/test_asistencias_entradas_salidas.py
git commit -m "feat(db): helper grupos_funcionales_disponibles via information_schema"
```

---

## Tarea 3: Query `listar_marcaciones_por_persona` + `contar_marcaciones_por_persona` (TDD, con BD)

**Files:**
- Modify: `db/queries/asistencias_entradas_salidas.py`
- Modify: `tests/integration/test_asistencias_entradas_salidas.py` (nuevo archivo)

- [ ] **Paso 1: Crear el archivo de test de integración RED**

`tests/integration/test_asistencias_entradas_salidas.py`:

```python
"""
Tests de integración de `db.queries.asistencias_entradas_salidas`.

Cubre las queries SQL reales (sin mockear `get_connection`).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest

from db import set_thread_tenant
from db.queries.asistencias import insertar_asistencias
from db.queries.asistencias_entradas_salidas import (
    contar_marcaciones_por_persona,
    listar_marcaciones_por_persona,
    normalizar_tipo_marcacion,
)
from db.queries.dispositivos import eliminar_dispositivo, upsert_dispositivo
from db.queries.personas_crud import crear_persona


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _set_tenant():
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


@pytest.fixture()
def dispositivo_test():
    did = upsert_dispositivo({
        "nombre": f"ZK-{uuid.uuid4().hex[:8]}",
        "ip": "192.168.99.1",
        "puerto": 4370,
        "protocolo": "TCP",
        "tipo_driver": "zk",
        "prioridad": 1,
        "timeout_seg": 30,
        "activo": True,
        "password_enc": None,
    })
    yield did
    try:
        eliminar_dispositivo(did)
    except Exception:
        pass


@pytest.fixture()
def persona_con_marcaciones(dispositivo_test):
    """Crea una persona con 3 marcaciones: 2 entradas (días distintos) + 1 salida."""
    id_zk = uuid.uuid4().int % 100000
    p = crear_persona(
        nombre=f"Test-ES-{uuid.uuid4().hex[:6]}",
        identificacion=str(uuid.uuid4().int)[:10],
        id_usuario_zk=str(id_zk),
    )
    registros = [
        {"id_usuario": id_zk, "fecha_hora": datetime(2026, 7, 2, 8, 0, tzinfo=timezone.utc), "tipo": "entrada"},
        {"id_usuario": id_zk, "fecha_hora": datetime(2026, 7, 2, 17, 0, tzinfo=timezone.utc), "tipo": "salida"},
        {"id_usuario": id_zk, "fecha_hora": datetime(2026, 7, 3, 8, 5, tzinfo=timezone.utc), "tipo": "entrada"},
    ]
    insertar_asistencias(registros, dispositivo_id=dispositivo_test)
    return {"id": p["id"], "id_zk": id_zk}


class TestListarMarcacionesPorPersona:

    def test_sin_marcaciones_retorna_lista_vacia(self):
        persona_id_inexistente = str(uuid.uuid4())
        resultado = listar_marcaciones_por_persona(
            persona_id_inexistente, date(2026, 7, 1), date(2026, 7, 31)
        )
        assert resultado == []

    def test_retorna_solo_marcaciones_del_rango(self, persona_con_marcaciones):
        pid = persona_con_marcaciones["id"]
        resultado = listar_marcaciones_por_persona(
            pid, date(2026, 7, 2), date(2026, 7, 2)
        )
        assert len(resultado) == 2  # entrada + salida del 2026-07-02

    def test_rango_semiabierto_excluye_fecha_fin(self, persona_con_marcaciones):
        """Rango [2026-07-02, 2026-07-03) → solo las marcaciones del 2026-07-02."""
        pid = persona_con_marcaciones["id"]
        resultado = listar_marcaciones_por_persona(
            pid, date(2026, 7, 2), date(2026, 7, 3)
        )
        assert len(resultado) == 2
        for r in resultado:
            assert r["fecha_hora"].date() == date(2026, 7, 2)

    def test_campos_normalizados(self, persona_con_marcaciones):
        pid = persona_con_marcaciones["id"]
        resultado = listar_marcaciones_por_persona(
            pid, date(2026, 7, 2), date(2026, 7, 3)
        )
        r = resultado[0]
        assert set(r.keys()) >= {
            "marcacion_id", "persona_id", "persona_nombre",
            "fecha_hora", "fecha", "hora", "tipo", "tipo_raw",
            "dispositivo_id", "dispositivo_nombre",
        }
        assert r["tipo"] in ("entrada", "salida", "otro")
        assert r["persona_id"] == pid

    def test_ordenamiento_por_fecha_hora_asc(self, persona_con_marcaciones):
        pid = persona_con_marcaciones["id"]
        resultado = listar_marcaciones_por_persona(
            pid, date(2026, 7, 1), date(2026, 7, 31)
        )
        fechas = [r["fecha_hora"] for r in resultado]
        assert fechas == sorted(fechas)

    def test_paginacion_limit_y_offset(self, persona_con_marcaciones):
        pid = persona_con_marcaciones["id"]
        pagina_1 = listar_marcaciones_por_persona(
            pid, date(2026, 7, 1), date(2026, 7, 31), limit=2, offset=0
        )
        pagina_2 = listar_marcaciones_por_persona(
            pid, date(2026, 7, 1), date(2026, 7, 31), limit=2, offset=2
        )
        assert len(pagina_1) == 2
        assert len(pagina_2) == 1  # solo queda 1 (3 totales, offset 2 + limit 2 → 1)
        # Sin solapamiento entre páginas
        ids_p1 = {r["marcacion_id"] for r in pagina_1}
        ids_p2 = {r["marcacion_id"] for r in pagina_2}
        assert ids_p1.isdisjoint(ids_p2)


class TestContarMarcacionesPorPersona:

    def test_cuenta_total(self, persona_con_marcaciones):
        pid = persona_con_marcaciones["id"]
        total = contar_marcaciones_por_persona(
            pid, date(2026, 7, 1), date(2026, 7, 31)
        )
        assert total == 3

    def test_cuenta_cero_sin_marcaciones(self):
        total = contar_marcaciones_por_persona(
            str(uuid.uuid4()), date(2026, 7, 1), date(2026, 7, 31)
        )
        assert total == 0
```

- [ ] **Paso 2: Verificar que el test falla**

Run: `pytest tests/integration/test_asistencias_entradas_salidas.py -v`
Expected: `ImportError` (las funciones `listar_marcaciones_por_persona` y `contar_marcaciones_por_persona` aún no existen).

- [ ] **Paso 3: Implementación mínima**

Añadir a `db/queries/asistencias_entradas_salidas.py`:

```python
def listar_marcaciones_por_persona(
    persona_id: str,
    fecha_inicio: date,
    fecha_fin: date,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """
    Lista las marcaciones (entradas/salidas) de UNA persona en el rango
    semiabierto [fecha_inicio, fecha_fin + 1 day).

    Args:
        persona_id: UUID de la persona (`personas.id`).
        fecha_inicio: inclusive.
        fecha_fin: inclusive en UI; la función añade 1 día para hacer
            el límite superior exclusivo (consistente con
            `db/queries/asistencias.py:consultar_asistencias`).
        limit: máximo de filas a devolver (default 50, max 200).
        offset: desplazamiento para paginación (default 0).

    Returns:
        Lista de dicts con campos:
        - marcacion_id, persona_id, persona_nombre, fecha_hora (datetime naive UTC),
          fecha (str YYYY-MM-DD), hora (str HH:MM:SS), tipo (normalizado),
          tipo_raw (valor original), dispositivo_id, dispositivo_nombre.
        Ordenada por fecha_hora ascendente.
    """
    if limit < 1:
        limit = 50
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0
    fecha_tope = fecha_fin + timedelta(days=1)
    inicio_str = fecha_inicio.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    fin_str = fecha_tope.strftime("%Y-%m-%d") + "T00:00:00+00:00"

    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    a.id::text                                                AS marcacion_id,
                    p.id::text                                                AS persona_id,
                    p.nombre                                                  AS persona_nombre,
                    a.fecha_hora                                              AS fecha_hora,
                    a.tipo                                                    AS tipo_raw,
                    COALESCE(d.id::text, '')                                  AS dispositivo_id,
                    COALESCE(d.nombre, '')                                    AS dispositivo_nombre
                FROM asistencias a
                JOIN personas p ON p.id = a.persona_id
                LEFT JOIN dispositivos d ON d.id = a.dispositivo_id
                WHERE p.id = CAST(:persona_id AS uuid)
                  AND a.fecha_hora >= CAST(:inicio AS timestamptz)
                  AND a.fecha_hora <  CAST(:fin    AS timestamptz)
                ORDER BY a.fecha_hora ASC
                LIMIT :limit OFFSET :offset
            """),
            {
                "persona_id": persona_id,
                "inicio": inicio_str,
                "fin": fin_str,
                "limit": limit,
                "offset": offset,
            },
        ).fetchall()

    resultado = []
    for r in rows:
        d = dict(r._mapping)
        fh = d["fecha_hora"]
        # PostgreSQL devuelve datetime aware; normalizamos a naive UTC para JSON
        if hasattr(fh, "tzinfo") and fh.tzinfo is not None:
            fh_naive = fh.replace(tzinfo=None)
        elif isinstance(fh, str):
            from datetime import datetime
            fh_naive = datetime.fromisoformat(fh.replace("Z", "+00:00")).replace(tzinfo=None)
        else:
            fh_naive = fh
        resultado.append({
            "marcacion_id": d["marcacion_id"],
            "persona_id": d["persona_id"],
            "persona_nombre": d["persona_nombre"],
            "fecha_hora": fh_naive,
            "fecha": fh_naive.strftime("%Y-%m-%d"),
            "hora": fh_naive.strftime("%H:%M:%S"),
            "tipo": normalizar_tipo_marcacion(d["tipo_raw"]),
            "tipo_raw": str(d["tipo_raw"]) if d["tipo_raw"] is not None else "",
            "dispositivo_id": d["dispositivo_id"],
            "dispositivo_nombre": d["dispositivo_nombre"],
        })
    return resultado


def contar_marcaciones_por_persona(
    persona_id: str,
    fecha_inicio: date,
    fecha_fin: date,
) -> int:
    """Cuenta total de marcaciones de una persona en el rango [inicio, fin+1)."""
    fecha_tope = fecha_fin + timedelta(days=1)
    inicio_str = fecha_inicio.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    fin_str = fecha_tope.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    with get_connection() as conn:
        row = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM asistencias a
                JOIN personas p ON p.id = a.persona_id
                WHERE p.id = CAST(:persona_id AS uuid)
                  AND a.fecha_hora >= CAST(:inicio AS timestamptz)
                  AND a.fecha_hora <  CAST(:fin    AS timestamptz)
            """),
            {"persona_id": persona_id, "inicio": inicio_str, "fin": fin_str},
        ).fetchone()
    return int(row[0]) if row else 0


# Extender __all__
__all__ = [
    "normalizar_tipo_marcacion",
    "grupos_funcionales_disponibles",
    "listar_marcaciones_por_persona",
    "contar_marcaciones_por_persona",
]
```

- [ ] **Paso 4: Verificar que el test pasa**

Run: `pytest tests/integration/test_asistencias_entradas_salidas.py -v`
Expected: `8 passed` (5 de `TestListarMarcacionesPorPersona` + 2 de `TestContarMarcacionesPorPersona` + 1 import check).

- [ ] **Paso 5: Commit**

```bash
git add db/queries/asistencias_entradas_salidas.py tests/integration/test_asistencias_entradas_salidas.py
git commit -m "feat(db): listar y contar marcaciones por persona en rango semiabierto"
```

---

## Tarea 4: Queries `listar_marcaciones_por_grupo_funcional` + `get_personas_por_grupo_funcional_vigente` (TDD, con BD)

**Files:**
- Modify: `db/queries/asistencias_entradas_salidas.py`
- Modify: `tests/integration/test_asistencias_entradas_salidas.py`

- [ ] **Paso 1: Añadir test RED**

Agregar a `tests/integration/test_asistencias_entradas_salidas.py`:

```python
from db.queries.asistencias_entradas_salidas import (
    get_personas_por_grupo_funcional_vigente,
    listar_marcaciones_por_grupo_funcional,
    contar_marcaciones_por_grupo_funcional,
)


def _crear_tabla_grupos_funcionales():
    """
    Crea ad-hoc la tabla `persona_grupos_funcionales` (simulando el estado
    post-ADR 0003). Devuelve el id de la fila de test.
    """
    import sqlalchemy as sa
    from db.connection import get_engine
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(sa.text("""
            CREATE TABLE IF NOT EXISTS persona_grupos_funcionales (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                persona_id UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
                grupo_funcional_id UUID NOT NULL,
                fecha_inicio DATE NOT NULL,
                fecha_fin DATE,
                creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.commit()


def _insertar_asignacion_gf(persona_id, grupo_funcional_id, fecha_inicio, fecha_fin=None):
    import sqlalchemy as sa
    from db.connection import get_engine
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(sa.text("""
            INSERT INTO persona_grupos_funcionales
                (persona_id, grupo_funcional_id, fecha_inicio, fecha_fin)
            VALUES (CAST(:pid AS uuid), CAST(:gid AS uuid),
                    CAST(:fi AS date), CAST(:ff AS date))
        """), {"pid": persona_id, "gid": grupo_funcional_id,
               "fi": fecha_inicio, "ff": fecha_fin})
        conn.commit()


@pytest.fixture()
def gf_id_y_tabla():
    """Crea la tabla `persona_grupos_funcionales` y devuelve un UUID de grupo funcional."""
    _crear_tabla_grupos_funcionales()
    return str(uuid.uuid4())


class TestGetPersonasPorGrupoFuncionalVigente:

    def test_retorna_persona_vigente_en_rango(self, persona_con_marcaciones, gf_id_y_tabla):
        _insertar_asignacion_gf(persona_con_marcaciones["id"], gf_id_y_tabla, date(2026, 7, 1))
        resultado = get_personas_por_grupo_funcional_vigente(
            gf_id_y_tabla, date(2026, 7, 1), date(2026, 7, 31)
        )
        assert persona_con_marcaciones["id"] in resultado

    def test_excluye_persona_fuera_de_rango(self, persona_con_marcaciones, gf_id_y_tabla):
        _insertar_asignacion_gf(persona_con_marcaciones["id"], gf_id_y_tabla, date(2026, 1, 1), date(2026, 6, 30))
        resultado = get_personas_por_grupo_funcional_vigente(
            gf_id_y_tabla, date(2026, 7, 1), date(2026, 7, 31)
        )
        assert persona_con_marcaciones["id"] not in resultado

    def test_incluye_persona_con_solapamiento_parcial(self, persona_con_marcaciones, gf_id_y_tabla):
        """Vigente del 2026-06-15 al 2026-07-15 — solapa con el rango."""
        _insertar_asignacion_gf(persona_con_marcaciones["id"], gf_id_y_tabla, date(2026, 6, 15), date(2026, 7, 15))
        resultado = get_personas_por_grupo_funcional_vigente(
            gf_id_y_tabla, date(2026, 7, 1), date(2026, 7, 31)
        )
        assert persona_con_marcaciones["id"] in resultado

    def test_incluye_persona_sin_fecha_fin(self, persona_con_marcaciones, gf_id_y_tabla):
        """fecha_fin NULL → vigente hasta el infinito (caso típico)."""
        _insertar_asignacion_gf(persona_con_marcaciones["id"], gf_id_y_tabla, date(2026, 1, 1), None)
        resultado = get_personas_por_grupo_funcional_vigente(
            gf_id_y_tabla, date(2026, 7, 1), date(2026, 7, 31)
        )
        assert persona_con_marcaciones["id"] in resultado


class TestListarMarcacionesPorGrupoFuncional:

    def test_une_marcaciones_de_todas_las_personas_del_gf(
        self, persona_con_marcaciones, gf_id_y_tabla
    ):
        _insertar_asignacion_gf(persona_con_marcaciones["id"], gf_id_y_tabla, date(2026, 7, 1))
        resultado = listar_marcaciones_por_grupo_funcional(
            gf_id_y_tabla, date(2026, 7, 1), date(2026, 7, 31)
        )
        assert len(resultado) == 3  # todas las marcaciones de la persona

    def test_sin_personas_asignadas_retorna_vacio(self, gf_id_y_tabla):
        resultado = listar_marcaciones_por_grupo_funcional(
            gf_id_y_tabla, date(2026, 7, 1), date(2026, 7, 31)
        )
        assert resultado == []


class TestContarMarcacionesPorGrupoFuncional:

    def test_cuenta_total(self, persona_con_marcaciones, gf_id_y_tabla):
        _insertar_asignacion_gf(persona_con_marcaciones["id"], gf_id_y_tabla, date(2026, 7, 1))
        total = contar_marcaciones_por_grupo_funcional(
            gf_id_y_tabla, date(2026, 7, 1), date(2026, 7, 31)
        )
        assert total == 3
```

- [ ] **Paso 2: Verificar que el test falla**

Run: `pytest tests/integration/test_asistencias_entradas_salidas.py::TestGetPersonasPorGrupoFuncionalVigente tests/integration/test_asistencias_entradas_salidas.py::TestListarMarcacionesPorGrupoFuncional tests/integration/test_asistencias_entradas_salidas.py::TestContarMarcacionesPorGrupoFuncional -v`
Expected: `ImportError` (las 3 funciones aún no existen).

- [ ] **Paso 3: Implementación mínima**

Añadir a `db/queries/asistencias_entradas_salidas.py`:

```python
def get_personas_por_grupo_funcional_vigente(
    grupo_funcional_id: str,
    fecha_inicio: date,
    fecha_fin: date,
) -> list[str]:
    """
    Retorna los `persona_id` (UUIDs como str) que tienen asignado el grupo
    funcional `grupo_funcional_id` en ALGÚN día del rango [fecha_inicio, fecha_fin].

    Regla de solapamiento (estándar de vigencias por intersección):
      pgf.fecha_inicio <= fecha_fin AND (pgf.fecha_fin IS NULL OR pgf.fecha_fin >= fecha_inicio)

    Asume que la tabla `<tenant>.persona_grupos_funcionales` ya existe.
    El caller debe haber validado `grupos_funcionales_disponibles(schema)` antes.
    """
    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT DISTINCT pgf.persona_id::text
                FROM persona_grupos_funcionales pgf
                WHERE pgf.grupo_funcional_id = CAST(:gf_id AS uuid)
                  AND pgf.fecha_inicio      <= CAST(:ffin AS date)
                  AND (pgf.fecha_fin IS NULL OR pgf.fecha_fin >= CAST(:fini AS date))
            """),
            {"gf_id": grupo_funcional_id, "fini": fecha_inicio, "ffin": fecha_fin},
        ).fetchall()
    return [r[0] for r in rows]


def listar_marcaciones_por_grupo_funcional(
    grupo_funcional_id: str,
    fecha_inicio: date,
    fecha_fin: date,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """
    Lista las marcaciones de TODAS las personas que tienen el grupo funcional
    vigente en algún día del rango. Retorna el mismo formato que
    `listar_marcaciones_por_persona`.

    Implementación: dos pasos.
      1. Resolver personas vigentes (unión, no intersección).
      2. Traer marcaciones ordenadas por persona y fecha_hora.
    """
    if limit < 1:
        limit = 50
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0
    personas = get_personas_por_grupo_funcional_vigente(
        grupo_funcional_id, fecha_inicio, fecha_fin
    )
    if not personas:
        return []
    fecha_tope = fecha_fin + timedelta(days=1)
    inicio_str = fecha_inicio.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    fin_str = fecha_tope.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    with get_connection() as conn:
        rows = conn.execute(
            text("""
                SELECT
                    a.id::text                                                AS marcacion_id,
                    p.id::text                                                AS persona_id,
                    p.nombre                                                  AS persona_nombre,
                    a.fecha_hora                                              AS fecha_hora,
                    a.tipo                                                    AS tipo_raw,
                    COALESCE(d.id::text, '')                                  AS dispositivo_id,
                    COALESCE(d.nombre, '')                                    AS dispositivo_nombre
                FROM asistencias a
                JOIN personas p ON p.id = a.persona_id
                LEFT JOIN dispositivos d ON d.id = a.dispositivo_id
                WHERE p.id = ANY(CAST(:personas AS uuid[]))
                  AND a.fecha_hora >= CAST(:inicio AS timestamptz)
                  AND a.fecha_hora <  CAST(:fin    AS timestamptz)
                ORDER BY p.nombre ASC, a.fecha_hora ASC
                LIMIT :limit OFFSET :offset
            """),
            {
                "personas": "{" + ",".join(personas) + "}",
                "inicio": inicio_str,
                "fin": fin_str,
                "limit": limit,
                "offset": offset,
            },
        ).fetchall()

    resultado = []
    for r in rows:
        d = dict(r._mapping)
        fh = d["fecha_hora"]
        if hasattr(fh, "tzinfo") and fh.tzinfo is not None:
            fh_naive = fh.replace(tzinfo=None)
        elif isinstance(fh, str):
            from datetime import datetime
            fh_naive = datetime.fromisoformat(fh.replace("Z", "+00:00")).replace(tzinfo=None)
        else:
            fh_naive = fh
        resultado.append({
            "marcacion_id": d["marcacion_id"],
            "persona_id": d["persona_id"],
            "persona_nombre": d["persona_nombre"],
            "fecha_hora": fh_naive,
            "fecha": fh_naive.strftime("%Y-%m-%d"),
            "hora": fh_naive.strftime("%H:%M:%S"),
            "tipo": normalizar_tipo_marcacion(d["tipo_raw"]),
            "tipo_raw": str(d["tipo_raw"]) if d["tipo_raw"] is not None else "",
            "dispositivo_id": d["dispositivo_id"],
            "dispositivo_nombre": d["dispositivo_nombre"],
        })
    return resultado


def contar_marcaciones_por_grupo_funcional(
    grupo_funcional_id: str,
    fecha_inicio: date,
    fecha_fin: date,
) -> int:
    """Cuenta total de marcaciones de las personas del grupo funcional en el rango."""
    personas = get_personas_por_grupo_funcional_vigente(
        grupo_funcional_id, fecha_inicio, fecha_fin
    )
    if not personas:
        return 0
    fecha_tope = fecha_fin + timedelta(days=1)
    inicio_str = fecha_inicio.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    fin_str = fecha_tope.strftime("%Y-%m-%d") + "T00:00:00+00:00"
    with get_connection() as conn:
        row = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM asistencias a
                WHERE a.persona_id = ANY(CAST(:personas AS uuid[]))
                  AND a.fecha_hora >= CAST(:inicio AS timestamptz)
                  AND a.fecha_hora <  CAST(:fin    AS timestamptz)
            """),
            {"personas": "{" + ",".join(personas) + "}",
             "inicio": inicio_str, "fin": fin_str},
        ).fetchone()
    return int(row[0]) if row else 0


# Extender __all__
__all__ = [
    "normalizar_tipo_marcacion",
    "grupos_funcionales_disponibles",
    "listar_marcaciones_por_persona",
    "contar_marcaciones_por_persona",
    "listar_marcaciones_por_grupo_funcional",
    "contar_marcaciones_por_grupo_funcional",
    "get_personas_por_grupo_funcional_vigente",
]
```

- [ ] **Paso 4: Verificar que el test pasa**

Run: `pytest tests/integration/test_asistencias_entradas_salidas.py -v`
Expected: `15 passed` (8 de Tarea 3 + 7 nuevos).

- [ ] **Paso 5: Commit**

```bash
git add db/queries/asistencias_entradas_salidas.py tests/integration/test_asistencias_entradas_salidas.py
git commit -m "feat(db): queries por grupo funcional vigente + vigencia solapada"
```

---

## Tarea 5: Re-export desde `db/__init__.py`

**Files:**
- Modify: `db/__init__.py`

- [ ] **Paso 1: Verificar que el archivo actual tiene la sección de Asistencias**

Run: `rg -n "from db.queries.asistencias import" db/__init__.py`
Expected: muestra la línea exacta de imports actuales (líneas ~21-27 del archivo).

- [ ] **Paso 2: Añadir los nuevos imports**

Modificar `db/__init__.py`. Localizar el bloque `from db.queries.asistencias import (...)` y agregar después:

```python
from db.queries.asistencias_entradas_salidas import (
    contar_marcaciones_por_grupo_funcional,
    contar_marcaciones_por_persona,
    get_personas_por_grupo_funcional_vigente,
    grupos_funcionales_disponibles,
    listar_marcaciones_por_grupo_funcional,
    listar_marcaciones_por_persona,
    normalizar_tipo_marcacion,
)
```

Localizar `__all__` y agregar al final de la sección de Asistencias:

```python
__all__ = [
    # ... existentes ...
    # asistencias — analítica E/S
    "contar_marcaciones_por_grupo_funcional",
    "contar_marcaciones_por_persona",
    "get_personas_por_grupo_funcional_vigente",
    "grupos_funcionales_disponibles",
    "listar_marcaciones_por_grupo_funcional",
    "listar_marcaciones_por_persona",
    "normalizar_tipo_marcacion",
]
```

- [ ] **Paso 3: Verificar que los imports funcionan**

Run: `python -c "from db import listar_marcaciones_por_persona, contar_marcaciones_por_persona, listar_marcaciones_por_grupo_funcional, contar_marcaciones_por_grupo_funcional, get_personas_por_grupo_funcional_vigente, grupos_funcionales_disponibles, normalizar_tipo_marcacion; print('OK')"`
Expected: `OK`.

- [ ] **Paso 4: Commit**

```bash
git add db/__init__.py
git commit -m "feat(db): re-export helpers y queries de analitica E/S"
```

---

## Tarea 6: Servicio de dominio `consultar_entradas_salidas` (TDD unitario)

**Files:**
- Create: `app/domain/analytics_entradas_salidas.py`
- Create: `tests/unit/test_analytics_entradas_salidas_servicio.py`

- [ ] **Paso 1: Escribir el test RED**

`tests/unit/test_analytics_entradas_salidas_servicio.py`:

```python
"""
Tests unitarios de `app.domain.analytics_entradas_salidas` (TDD).

Mockeamos las queries de `db.queries.asistencias_entradas_salidas` y la
función `registrar_audit` para no tocar BD.
"""
from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.domain import analytics_entradas_salidas as aes_svc


class TestParsearParametros:

    def test_sin_fecha_inicio_lanza_error(self):
        with pytest.raises(ValueError) as exc:
            aes_svc.parsear_parametros({})
        assert "fecha_inicio" in str(exc.value).lower()

    def test_sin_fecha_fin_lanza_error(self):
        with pytest.raises(ValueError) as exc:
            aes_svc.parsear_parametros({"fecha_inicio": "2026-07-01"})
        assert "fecha_fin" in str(exc.value).lower()

    def test_formato_invalido_lanza_error(self):
        with pytest.raises(ValueError) as exc:
            aes_svc.parsear_parametros({
                "fecha_inicio": "no-es-fecha",
                "fecha_fin": "2026-07-31",
            })
        assert "formato" in str(exc.value).lower()

    def test_fecha_inicio_mayor_que_fin_lanza_error(self):
        with pytest.raises(ValueError) as exc:
            aes_svc.parsear_parametros({
                "fecha_inicio": "2026-08-01",
                "fecha_fin": "2026-07-01",
            })
        assert "rango" in str(exc.value).lower() or "inicio" in str(exc.value).lower()

    def test_parsea_pagina_y_per_page(self):
        p = aes_svc.parsear_parametros({
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-07-31",
            "page": "3",
            "per_page": "100",
        })
        assert p["page"] == 3
        assert p["per_page"] == 100

    def test_per_page_clamp_a_200(self):
        p = aes_svc.parsear_parametros({
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-07-31",
            "per_page": "9999",
        })
        assert p["per_page"] == 200

    def test_per_page_clamp_a_1_si_invalido(self):
        p = aes_svc.parsear_parametros({
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-07-31",
            "per_page": "0",
        })
        assert p["per_page"] == 50  # default


class TestValidarFiltro:

    def _args(self, **overrides):
        base = {
            "fecha_inicio": date(2026, 7, 1),
            "fecha_fin": date(2026, 7, 31),
            "page": 1,
            "per_page": 50,
            "persona_id": None,
            "grupo_funcional_id": None,
        }
        base.update(overrides)
        return base

    def test_sin_filtros_con_flag_off_lanza_error(self):
        """Flag off y sin persona_id → 400 filtro_requerido."""
        with pytest.raises(ValueError) as exc:
            aes_svc.validar_filtro(
                self._args(),
                tenant_config={},
                grupos_funcionales_ok=False,
            )
        assert "filtro_requerido" in str(exc.value)

    def test_grupo_funcional_con_flag_off_lanza_error(self):
        """Flag off y grupo_funcional_id → 400 grupo_funcional_no_disponible."""
        with pytest.raises(ValueError) as exc:
            aes_svc.validar_filtro(
                self._args(grupo_funcional_id=str(uuid.uuid4())),
                tenant_config={},
                grupos_funcionales_ok=False,
            )
        assert "grupo_funcional_no_disponible" in str(exc.value)

    def test_grupo_funcional_con_tabla_inexistente_lanza_error(self):
        """Flag on pero tabla no existe → 400 grupo_funcional_no_disponible."""
        with pytest.raises(ValueError) as exc:
            aes_svc.validar_filtro(
                self._args(grupo_funcional_id=str(uuid.uuid4())),
                tenant_config={"horario_por_grupo": True},
                grupos_funcionales_ok=False,
            )
        assert "grupo_funcional_no_disponible" in str(exc.value)

    def test_persona_id_es_valido_con_o_sin_flag(self):
        """persona_id siempre es aceptado (fallback)."""
        # Sin flag, con persona_id → OK
        aes_svc.validar_filtro(
            self._args(persona_id=str(uuid.uuid4())),
            tenant_config={},
            grupos_funcionales_ok=False,
        )
        # Con flag + tabla, con persona_id → OK
        aes_svc.validar_filtro(
            self._args(persona_id=str(uuid.uuid4())),
            tenant_config={"horario_por_grupo": True},
            grupos_funcionales_ok=True,
        )

    def test_uuid_invalido_lanza_error(self):
        with pytest.raises(ValueError) as exc:
            aes_svc.validar_filtro(
                self._args(persona_id="no-es-uuid"),
                tenant_config={},
                grupos_funcionales_ok=False,
            )
        assert "uuid_invalido" in str(exc.value)


class TestAplicarAlcanceSupervisorGrupo:

    def test_sin_supervisor_no_filtra(self):
        resultado = aes_svc.aplicar_alcance_supervisor_grupo(
            [{"persona_id": "a"}, {"persona_id": "b"}],
            supervisor_grupo_id=None,
        )
        assert len(resultado) == 2

    def test_con_supervisor_filtra_por_grupo_id(self):
        """supervisor_grupo_id filtra las personas cuyo grupo_id coincide."""
        from unittest.mock import patch as _patch

        mock_rows = [
            {"id": "a", "grupo_id": "g1"},
            {"id": "b", "grupo_id": "g2"},
        ]
        with _patch("db.queries.personas_crud.get_persona", side_effect=mock_rows):
            resultado = aes_svc.aplicar_alcance_supervisor_grupo(
                [{"persona_id": "a"}, {"persona_id": "b"}],
                supervisor_grupo_id="g1",
            )
        assert len(resultado) == 1
        assert resultado[0]["persona_id"] == "a"


class TestConsultarEntradasSalidas:

    def test_orquesta_query_por_persona(self):
        args = {
            "fecha_inicio": date(2026, 7, 1),
            "fecha_fin": date(2026, 7, 31),
            "page": 1,
            "per_page": 50,
            "persona_id": str(uuid.uuid4()),
            "grupo_funcional_id": None,
        }
        with patch.object(aes_svc, "listar_marcaciones_por_persona", return_value=[{"marcacion_id": "1"}]), \
             patch.object(aes_svc, "contar_marcaciones_por_persona", return_value=1), \
             patch.object(aes_svc, "registrar_consulta_audit") as mock_audit:
            resultado = aes_svc.consultar_entradas_salidas(
                tenant_config={},
                grupos_funcionales_ok=False,
                **args,
            )
        assert resultado["pagination"]["total"] == 1
        assert resultado["pagination"]["page"] == 1
        assert resultado["pagination"]["per_page"] == 50
        assert resultado["pagination"]["total_pages"] == 1
        assert len(resultado["items"]) == 1
        assert resultado["filtros_aplicados"]["persona_id"] == args["persona_id"]
        assert resultado["filtros_aplicados"]["grupo_funcional_id"] is None
        assert resultado["filtros_aplicados"]["horario_por_grupo"] is False
        mock_audit.assert_called_once()

    def test_orquesta_query_por_grupo_funcional(self):
        args = {
            "fecha_inicio": date(2026, 7, 1),
            "fecha_fin": date(2026, 7, 31),
            "page": 2,
            "per_page": 25,
            "persona_id": None,
            "grupo_funcional_id": str(uuid.uuid4()),
        }
        with patch.object(aes_svc, "listar_marcaciones_por_grupo_funcional", return_value=[]), \
             patch.object(aes_svc, "contar_marcaciones_por_grupo_funcional", return_value=0), \
             patch.object(aes_svc, "registrar_consulta_audit"):
            resultado = aes_svc.consultar_entradas_salidas(
                tenant_config={"horario_por_grupo": True},
                grupos_funcionales_ok=True,
                **args,
            )
        assert resultado["pagination"]["page"] == 2
        assert resultado["pagination"]["per_page"] == 25
        assert resultado["filtros_aplicados"]["horario_por_grupo"] is True
```

- [ ] **Paso 2: Verificar que el test falla**

Run: `pytest tests/unit/test_analytics_entradas_salidas_servicio.py -v`
Expected: `ModuleNotFoundError` (el módulo `app/domain/analytics_entradas_salidas.py` aún no existe).

- [ ] **Paso 3: Implementación mínima**

`app/domain/analytics_entradas_salidas.py`:

```python
"""
Servicio de analítica de entradas/salidas por persona
(`app/domain/analytics_entradas_salidas.py`).

Orquesta:
  - parseo y validación de query params (fechas, UUIDs, paginación)
  - decisión de filtro (persona_id vs grupo_funcional_id) según
    feature flag del tenant + existencia de la tabla `persona_grupos_funcionales`
  - aplicación de alcance `supervisor_grupo` (si el usuario tiene
    `supervisor_grupo_id` en su `configuracion`)
  - auditoría de la consulta (1 fila por llamada exitosa en `public.audit_log`)

No contiene SQL: delega en `db.queries.asistencias_entradas_salidas`.

API pública:
  - `parsear_parametros(args: dict) -> dict`
  - `validar_filtro(args, tenant_config, grupos_funcionales_ok) -> None`
  - `aplicar_alcance_supervisor_grupo(items, supervisor_grupo_id) -> list`
  - `consultar_entradas_salidas(...) -> dict`
  - `registrar_consulta_audit(...)` (helper)
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Optional

from flask import g, request

# Re-exports para que `patch.object(aes_svc, "listar_marcaciones_por_persona", ...)`
# en los tests funcione (los tests parchean el símbolo en este módulo).
from db.queries.asistencias_entradas_salidas import (
    contar_marcaciones_por_grupo_funcional,
    contar_marcaciones_por_persona,
    listar_marcaciones_por_grupo_funcional,
    listar_marcaciones_por_persona,
)

log = logging.getLogger(__name__)

# Constantes de paginación
DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 200


def _parse_date(raw: str) -> date:
    """Parsea YYYY-MM-DD a `date`. Lanza ValueError si el formato es incorrecto."""
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"formato_fecha_invalido: {raw!r}") from exc


def _parse_uuid(raw: str, campo: str) -> str:
    """Parsea un UUID. Lanza ValueError si el formato es incorrecto."""
    try:
        return str(uuid.UUID(raw))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"uuid_invalido en {campo}: {raw!r}") from exc


def _parse_int(raw, default: int, min_v: int, max_v: int) -> int:
    """Parsea un int con clamp. Si falla o está fuera de rango → default."""
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    if v < min_v:
        return default
    if v > max_v:
        return max_v
    return v


def parsear_parametros(args: dict) -> dict:
    """
    Parsea y valida query params crudos. Retorna dict normalizado.

    Raises:
        ValueError: con código de error en el mensaje (`formato_fecha_invalido`,
            `rango_invalido`, `uuid_invalido`).
    """
    fi = args.get("fecha_inicio")
    ff = args.get("fecha_fin")
    if not fi or not ff:
        raise ValueError("faltan parametros fecha_inicio y fecha_fin")
    fecha_inicio = _parse_date(fi)
    fecha_fin = _parse_date(ff)
    if fecha_inicio > fecha_fin:
        raise ValueError("rango_invalido: fecha_inicio > fecha_fin")

    persona_id = args.get("persona_id") or None
    grupo_funcional_id = args.get("grupo_funcional_id") or None
    if persona_id:
        persona_id = _parse_uuid(persona_id, "persona_id")
    if grupo_funcional_id:
        grupo_funcional_id = _parse_uuid(grupo_funcional_id, "grupo_funcional_id")

    page = _parse_int(args.get("page"), 1, 1, 10_000)
    per_page = _parse_int(args.get("per_page"), DEFAULT_PER_PAGE, 1, MAX_PER_PAGE)

    return {
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "persona_id": persona_id,
        "grupo_funcional_id": grupo_funcional_id,
        "page": page,
        "per_page": per_page,
    }


def validar_filtro(
    args: dict,
    tenant_config: dict,
    grupos_funcionales_ok: bool,
) -> None:
    """
    Valida la combinación de filtros contra el feature flag del tenant y
    la disponibilidad de la tabla `persona_grupos_funcionales`.

    Reglas:
      1. `persona_id` siempre es válido (fallback obligatorio).
      2. `grupo_funcional_id` solo es válido si:
           - `tenant_config['horario_por_grupo']` es True, Y
           - `grupos_funcionales_ok` (tabla existe) es True.
      3. Si llega `grupo_funcional_id` pero NO se cumple (2) → `grupo_funcional_no_disponible`.
      4. Si NO llega ni `persona_id` ni `grupo_funcional_id` → `filtro_requerido`.

    Raises:
        ValueError: con código en el mensaje.
    """
    flag_on = bool(tenant_config.get("horario_por_grupo"))
    gf_disponible = flag_on and grupos_funcionales_ok

    if args["grupo_funcional_id"] and not gf_disponible:
        raise ValueError("grupo_funcional_no_disponible")

    if not args["persona_id"] and not args["grupo_funcional_id"]:
        raise ValueError("filtro_requerido")


def aplicar_alcance_supervisor_grupo(
    items: list[dict],
    supervisor_grupo_id: Optional[str],
) -> list[dict]:
    """
    Si el usuario tiene `supervisor_grupo_id` en su configuración,
    filtra los items para incluir solo las personas cuyo `grupo_id`
    (legacy, `personas.grupo_id`) coincide.

    Implementación: usa el patrón ya presente en otros endpoints
    (ver `app/domain/schedule.py` y `app/domain/groups.py`).

    No aplica si `supervisor_grupo_id` es None.
    """
    if not supervisor_grupo_id:
        return items
    # Importación local para evitar ciclos en import-time de tests
    from db.queries.personas_crud import get_persona

    filtrados = []
    for item in items:
        persona = get_persona(item["persona_id"])
        if persona and persona.get("grupo_id") == supervisor_grupo_id:
            filtrados.append(item)
    return filtrados


def _registrar_consulta_audit(
    *,
    filtros: dict,
    count_resultados: int,
    page: int,
) -> None:
    """Inserta una fila en `public.audit_log` con la metadata de la consulta."""
    try:
        from db.queries.auth import registrar_audit

        registrar_audit(
            tenant_id=g.get("tenant_id"),
            usuario_id=g.get("usuario_id"),
            accion="analytics_entradas_salidas_consultar",
            detalle={
                "filtros": filtros,
                "count_resultados": count_resultados,
                "page": page,
            },
            ip=request.remote_addr if request else None,
        )
    except Exception:
        log.warning("No se pudo registrar analytics_entradas_salidas_consultar en audit_log", exc_info=True)


# Mantener nombre expuesto para tests (patch.object)
registrar_consulta_audit = _registrar_consulta_audit


def consultar_entradas_salidas(
    *,
    tenant_config: dict,
    grupos_funcionales_ok: bool,
    fecha_inicio: date,
    fecha_fin: date,
    page: int,
    per_page: int,
    persona_id: Optional[str],
    grupo_funcional_id: Optional[str],
    supervisor_grupo_id: Optional[str] = None,
) -> dict:
    """
    Punto de entrada principal del servicio. Ejecuta la consulta, aplica el
    alcance supervisor_grupo y registra auditoría.

    Returns:
        dict con shape:
          {
            "items": [...],
            "pagination": {
              "page", "per_page", "total", "total_pages", "has_next", "has_prev"
            },
            "filtros_aplicados": {
              "persona_id", "grupo_funcional_id",
              "horario_por_grupo", "feature_model_disponible"
            },
            "audit_ok": bool
          }
    """
    offset = (page - 1) * per_page

    if persona_id:
        items = listar_marcaciones_por_persona(
            persona_id, fecha_inicio, fecha_fin, limit=per_page, offset=offset,
        )
        total = contar_marcaciones_por_persona(persona_id, fecha_inicio, fecha_fin)
    else:
        # Grupo funcional (ya validado en validar_filtro)
        items = listar_marcaciones_por_grupo_funcional(
            grupo_funcional_id, fecha_inicio, fecha_fin,
            limit=per_page, offset=offset,
        )
        total = contar_marcaciones_por_grupo_funcional(
            grupo_funcional_id, fecha_inicio, fecha_fin,
        )

    # Aplicar alcance supervisor_grupo (post-query, sobre el slice actual)
    items = aplicar_alcance_supervisor_grupo(items, supervisor_grupo_id)

    total_pages = (total + per_page - 1) // per_page if total > 0 else 0
    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }

    filtros_aplicados = {
        "persona_id": persona_id,
        "grupo_funcional_id": grupo_funcional_id,
        "horario_por_grupo": bool(tenant_config.get("horario_por_grupo")),
        "feature_model_disponible": grupos_funcionales_ok,
    }

    _registrar_consulta_audit(
        filtros=filtros_aplicados,
        count_resultados=total,
        page=page,
    )

    # Serializar datetime a ISO para JSON
    items_json = []
    for it in items:
        it_copy = dict(it)
        if isinstance(it_copy.get("fecha_hora"), datetime):
            it_copy["fecha_hora"] = it_copy["fecha_hora"].isoformat()
        items_json.append(it_copy)

    return {
        "items": items_json,
        "pagination": pagination,
        "filtros_aplicados": filtros_aplicados,
        "audit_ok": True,
    }


__all__ = [
    "parsear_parametros",
    "validar_filtro",
    "aplicar_alcance_supervisor_grupo",
    "consultar_entradas_salidas",
    "registrar_consulta_audit",
    "DEFAULT_PER_PAGE",
    "MAX_PER_PAGE",
]
```

- [ ] **Paso 4: Verificar que el test pasa**

Run: `pytest tests/unit/test_analytics_entradas_salidas_servicio.py -v`
Expected: `14 passed` (3 de parseo + 5 de validación + 2 de alcance + 2 de orquestación + 2 de parseo extra).

- [ ] **Paso 5: Commit**

```bash
git add app/domain/analytics_entradas_salidas.py tests/unit/test_analytics_entradas_salidas_servicio.py
git commit -m "feat(domain): servicio consultar_entradas_salidas con RBAC y auditoria"
```

---

## Tarea 7: Endpoint `GET /api/analytics/entradas-salidas` (TDD integración)

**Files:**
- Modify: `app/web/analytics_bp.py`
- Modify: `tests/integration/test_analytics_entradas_salidas_bp.py` (nuevo)

- [ ] **Paso 1: Escribir el test RED**

`tests/integration/test_analytics_entradas_salidas_bp.py`:

```python
"""
Tests de integración del endpoint `GET /api/analytics/entradas-salidas`.
"""
from __future__ import annotations

import uuid

import pytest


pytestmark = pytest.mark.integration


ENDPOINT = "/api/analytics/entradas-salidas"


class TestEndpointBasico:

    def test_sin_auth_retorna_401_o_302(self, anonymous_client):
        r = anonymous_client.get(ENDPOINT)
        assert r.status_code in (302, 401, 403)

    def test_sin_parametros_retorna_400(self, admin_client):
        r = admin_client.get(ENDPOINT)
        assert r.status_code == 400
        data = r.get_json()
        assert "fecha" in data.get("error", "").lower() or "parametros" in data.get("error", "").lower()

    def test_fechas_invalidas_retorna_400(self, admin_client):
        r = admin_client.get(ENDPOINT, query_string={
            "fecha_inicio": "no-fecha",
            "fecha_fin": "2026-07-31",
        })
        assert r.status_code == 400
        assert "formato" in r.get_json()["error"].lower()

    def test_rango_invertido_retorna_400(self, admin_client):
        r = admin_client.get(ENDPOINT, query_string={
            "fecha_inicio": "2026-08-01",
            "fecha_fin": "2026-07-01",
        })
        assert r.status_code == 400
        assert "rango" in r.get_json()["error"].lower()

    def test_sin_filtros_retorna_400_filtro_requerido(self, admin_client):
        r = admin_client.get(ENDPOINT, query_string={
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-07-31",
        })
        assert r.status_code == 400
        assert "filtro_requerido" in r.get_json()["error"]

    def test_uuid_invalido_retorna_400(self, admin_client):
        r = admin_client.get(ENDPOINT, query_string={
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-07-31",
            "persona_id": "no-es-uuid",
        })
        assert r.status_code == 400
        assert "uuid_invalido" in r.get_json()["error"]


class TestEndpointPorPersona:

    def test_persona_sin_marcaciones_retorna_200_vacio(self, admin_client):
        pid_inexistente = str(uuid.uuid4())
        r = admin_client.get(ENDPOINT, query_string={
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-07-31",
            "persona_id": pid_inexistente,
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["items"] == []
        assert data["pagination"]["total"] == 0
        assert data["filtros_aplicados"]["persona_id"] == pid_inexistente
        assert data["filtros_aplicados"]["grupo_funcional_id"] is None
        assert data["filtros_aplicados"]["horario_por_grupo"] is False
        assert data["audit_ok"] is True

    def test_paginacion_params_se_reflejan_en_respuesta(self, admin_client):
        r = admin_client.get(ENDPOINT, query_string={
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-07-31",
            "persona_id": str(uuid.uuid4()),
            "page": "2",
            "per_page": "25",
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["pagination"]["page"] == 2
        assert data["pagination"]["per_page"] == 25

    def test_per_page_se_clamp_a_200(self, admin_client):
        r = admin_client.get(ENDPOINT, query_string={
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-07-31",
            "persona_id": str(uuid.uuid4()),
            "per_page": "9999",
        })
        assert r.status_code == 200
        assert r.get_json()["pagination"]["per_page"] == 200


class TestEndpointGrupoFuncional:

    def test_grupo_funcional_con_flag_off_retorna_400(self, admin_client):
        """Tenant sin horario_por_grupo y llega grupo_funcional_id → 400."""
        r = admin_client.get(ENDPOINT, query_string={
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-07-31",
            "grupo_funcional_id": str(uuid.uuid4()),
        })
        assert r.status_code == 400
        assert "grupo_funcional_no_disponible" in r.get_json()["error"]
```

- [ ] **Paso 2: Verificar que el test falla**

Run: `pytest tests/integration/test_analytics_entradas_salidas_bp.py -v`
Expected: `404` (la ruta `/api/analytics/entradas-salidas` aún no existe).

- [ ] **Paso 3: Implementación mínima**

Modificar `app/web/analytics_bp.py`. Localizar el bloque de imports (al inicio del archivo) y agregar:

```python
from app.domain import analytics_entradas_salidas as aes_svc
```

Localizar el final del archivo (después de `api_narrativo`) y agregar las nuevas rutas:

```python
@bp.get("/api/analytics/entradas-salidas")
@require_role("admin", "superadmin", "gestor")
def api_entradas_salidas():
    """
    Lista cronológica de marcaciones (entradas/salidas) por persona o por
    grupo funcional (cuando el feature flag del tenant esté activo y la tabla
    `persona_grupos_funcionales` exista).

    Query params:
      - fecha_inicio (YYYY-MM-DD, requerido)
      - fecha_fin    (YYYY-MM-DD, requerido)
      - persona_id   (UUID, opcional)
      - grupo_funcional_id (UUID, opcional, requiere flag + tabla)
      - page (int, default 1)
      - per_page (int, default 50, max 200)

    Respuestas:
      200 → {items, pagination, filtros_aplicados, audit_ok}
      400 → {error: "<código>: <detalle>"}
      403 → {error: "Acceso denegado..."}  (vía @require_role)
    """
    tenant_config = (g.get("tenant") or {}).get("configuracion") or {}
    schema = g.get("tenant_schema") or "istpet"

    # Detección de disponibilidad del modelo de grupos funcionales
    from db.queries.asistencias_entradas_salidas import grupos_funcionales_disponibles
    gf_ok = grupos_funcionales_disponibles(schema)

    # Alcance supervisor_grupo (opcional, lee de la configuración del usuario)
    supervisor_grupo_id = None
    usuario_cfg = (g.get("configuracion_usuario") or {})
    if isinstance(usuario_cfg, dict):
        supervisor_grupo_id = usuario_cfg.get("supervisor_grupo_id")

    try:
        args = aes_svc.parsear_parametros(request.args.to_dict(flat=True))
        aes_svc.validar_filtro(args, tenant_config, gf_ok)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        resultado = aes_svc.consultar_entradas_salidas(
            tenant_config=tenant_config,
            grupos_funcionales_ok=gf_ok,
            supervisor_grupo_id=supervisor_grupo_id,
            **args,
        )
    except Exception as e:  # noqa: BLE001
        current_app.logger.exception("Error en /api/analytics/entradas-salidas")
        return jsonify({"error": f"Error interno: {e}"}), 500

    return jsonify(resultado)


@bp.get("/analytics/entradas-salidas")
@require_role("admin", "superadmin", "gestor")
def vista_entradas_salidas():
    """Vista HTML con form de filtros y tabla de resultados."""
    from flask import current_app
    from db.queries.asistencias_entradas_salidas import grupos_funcionales_disponibles

    tenant_config = (g.get("tenant") or {}).get("configuracion") or {}
    schema = g.get("tenant_schema") or "istpet"
    gf_ok = grupos_funcionales_disponibles(schema) and bool(tenant_config.get("horario_por_grupo"))

    # Lista de personas (para el buscador; máximo 500 para UI)
    from db.queries.personas_crud import listar_personas
    personas = listar_personas(activo=True, busqueda=None)[:500]

    hoy = date.today()
    return render_template(
        "analytics_entradas_salidas.html",
        active_page="analytics",
        grupos_funcionales_disponible=gf_ok,
        personas=personas,
        fecha_inicio=hoy.replace(day=1).strftime("%Y-%m-%d"),
        fecha_fin=hoy.strftime("%Y-%m-%d"),
    )
```

- [ ] **Paso 4: Verificar que los tests pasan**

Run: `pytest tests/integration/test_analytics_entradas_salidas_bp.py -v`
Expected: `9 passed` (los 9 tests del archivo; los que no requieren template no fallan porque el template no se renderiza en estos tests).

Si pytest reporta error de import circular, mover el `from app.domain import analytics_entradas_salidas as aes_svc` a un import dentro de la función y volver a correr.

- [ ] **Paso 5: Commit**

```bash
git add app/web/analytics_bp.py tests/integration/test_analytics_entradas_salidas_bp.py
git commit -m "feat(web): endpoint GET /api/analytics/entradas-salidas y vista HTML"
```

---

## Tarea 8: Template `analytics_entradas_salidas.html` (UI mínima)

**Files:**
- Create: `templates/analytics_entradas_salidas.html`

- [ ] **Paso 1: Crear el template**

`templates/analytics_entradas_salidas.html`:

```html
{% extends "base.html" %}

{% block content %}
<div class="page-header mb-4">
    <h3>Entradas y Salidas por Persona</h3>
    <p class="text-muted">
        Vista analítica cronológica de marcaciones.
        {% if not grupos_funcionales_disponible %}
        Filtro por grupo funcional no disponible (requiere activación del administrador).
        {% endif %}
    </p>
</div>

<!-- Form de filtros -->
<div class="card border-0 shadow-sm mb-4">
    <div class="card-body p-4">
        <form class="row g-3 align-items-end" id="esForm">
            <div class="col-md-3">
                <label class="form-label small text-uppercase text-muted fw-bold">Fecha inicio</label>
                <input type="date" class="form-control" id="es_fecha_inicio" value="{{ fecha_inicio }}">
            </div>
            <div class="col-md-3">
                <label class="form-label small text-uppercase text-muted fw-bold">Fecha fin</label>
                <input type="date" class="form-control" id="es_fecha_fin" value="{{ fecha_fin }}">
            </div>

            {% if grupos_funcionales_disponible %}
            <div class="col-md-3">
                <label class="form-label small text-uppercase text-muted fw-bold">Grupo funcional</label>
                <input type="text" class="form-control" id="es_grupo_funcional_id"
                       placeholder="UUID (opcional)">
            </div>
            {% endif %}

            <div class="col-md-3">
                <label class="form-label small text-uppercase text-muted fw-bold">Persona (UUID)</label>
                <input type="text" class="form-control" id="es_persona_id"
                       placeholder="Buscar UUID de persona" list="personas-list" autocomplete="off">
                <datalist id="personas-list">
                    {% for p in personas %}
                    <option value="{{ p.id }}">{{ p.nombre }} ({{ p.identificacion or 'sin id' }})</option>
                    {% endfor %}
                </datalist>
            </div>

            <div class="col-md-12 d-flex gap-2">
                <button type="submit" class="btn btn-primary fw-bold">
                    <span class="material-symbols-outlined" style="font-size:1rem;vertical-align:-3px;">search</span>
                    Consultar
                </button>
                <button type="button" id="es-limpiar" class="btn btn-outline-secondary">Limpiar</button>
            </div>
        </form>
    </div>
</div>

<!-- Loading -->
<div id="es-loading" style="display:none;" class="text-center py-4">
    <div class="spinner-border text-primary" role="status"></div>
    <span class="ms-2 text-muted">Consultando marcaciones…</span>
</div>

<!-- Error -->
<div id="es-error" style="display:none;" class="alert alert-danger" role="alert"></div>

<!-- Resultados -->
<div id="es-results" style="display:none;">
    <p class="text-muted small mb-2">
        Total: <strong id="es-total">0</strong> marcaciones.
        Página <strong id="es-page">1</strong> de <strong id="es-total-pages">1</strong>.
    </p>
    <div class="table-responsive border rounded-3">
        <table class="table table-hover align-middle mb-0">
            <thead class="bg-light">
                <tr>
                    <th>Fecha</th>
                    <th>Hora</th>
                    <th>Persona</th>
                    <th>Tipo</th>
                    <th>Dispositivo</th>
                </tr>
            </thead>
            <tbody id="es-tbody"></tbody>
        </table>
    </div>
    <div class="d-flex justify-content-between mt-3">
        <button type="button" id="es-prev" class="btn btn-outline-secondary" disabled>← Anterior</button>
        <button type="button" id="es-next" class="btn btn-outline-secondary" disabled>Siguiente →</button>
    </div>
</div>

{% endblock %}

{% block extra_js %}
<script>
(function() {
    'use strict';

    const estado = { page: 1, per_page: 50, last_data: null };

    function show(id)  { const el = document.getElementById(id); if (el) el.style.display = ''; }
    function hide(id)  { const el = document.getElementById(id); if (el) el.style.display = 'none'; }

    function tipoBadge(tipo) {
        const map = {
            'entrada': ['bg-success-soft text-success', 'login',          'Entrada'],
            'salida':  ['bg-warning-soft text-warning', 'logout',         'Salida'],
            'otro':    ['bg-secondary text-white',      'help_outline',   'Otro'],
        };
        const [cls, icon, label] = map[tipo] || map['otro'];
        return `<span class="badge rounded-pill ${cls}">
            <span class="material-symbols-outlined" style="font-size:13px;vertical-align:-2px;">${icon}</span>
            ${label}
        </span>`;
    }

    function renderResultados(data) {
        estado.last_data = data;
        const tbody = document.getElementById('es-tbody');
        if (!data.items || data.items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-muted">No hay marcaciones en el rango.</td></tr>';
        } else {
            tbody.innerHTML = data.items.map(r => `
                <tr>
                    <td>${r.fecha || ''}</td>
                    <td><code>${r.hora || ''}</code></td>
                    <td>${r.persona_nombre || ''}</td>
                    <td>${tipoBadge(r.tipo)}</td>
                    <td class="text-muted small">${r.dispositivo_nombre || '—'}</td>
                </tr>
            `).join('');
        }
        document.getElementById('es-total').textContent       = data.pagination.total;
        document.getElementById('es-page').textContent        = data.pagination.page;
        document.getElementById('es-total-pages').textContent = data.pagination.total_pages || 1;
        document.getElementById('es-prev').disabled           = !data.pagination.has_prev;
        document.getElementById('es-next').disabled           = !data.pagination.has_next;
        show('es-results');
    }

    function consultar(opts) {
        const page = (opts && opts.page) || estado.page;
        const qs = new URLSearchParams({
            fecha_inicio: document.getElementById('es_fecha_inicio').value,
            fecha_fin:    document.getElementById('es_fecha_fin').value,
            page:         page,
            per_page:     estado.per_page,
        });
        const pid = document.getElementById('es_persona_id').value.trim();
        if (pid) qs.set('persona_id', pid);
        const gidEl = document.getElementById('es_grupo_funcional_id');
        if (gidEl && gidEl.value.trim()) qs.set('grupo_funcional_id', gidEl.value.trim());

        hide('es-results');
        hide('es-error');
        show('es-loading');

        apiCall('/api/analytics/entradas-salidas?' + qs.toString())
            .then(data => {
                hide('es-loading');
                estado.page = data.pagination.page;
                renderResultados(data);
            })
            .catch(err => {
                hide('es-loading');
                document.getElementById('es-error').textContent = err.message || 'Error desconocido';
                show('es-error');
            });
    }

    document.getElementById('esForm').addEventListener('submit', function(e) {
        e.preventDefault();
        estado.page = 1;
        consultar({ page: 1 });
    });
    document.getElementById('es-limpiar').addEventListener('click', function() {
        document.getElementById('es_persona_id').value = '';
        const gid = document.getElementById('es_grupo_funcional_id');
        if (gid) gid.value = '';
        estado.page = 1;
        hide('es-results');
        hide('es-error');
    });
    document.getElementById('es-prev').addEventListener('click', function() {
        if (estado.page > 1) consultar({ page: estado.page - 1 });
    });
    document.getElementById('es-next').addEventListener('click', function() {
        if (estado.last_data && estado.last_data.pagination.has_next) {
            consultar({ page: estado.page + 1 });
        }
    });
})();
</script>
{% endblock %}
```

- [ ] **Paso 2: Verificar que la vista renderiza**

Run: `pytest tests/integration/test_analytics_entradas_salidas_bp.py -v`
Expected: `9 passed` (incluye `test_sin_auth_retorna_401_o_302` que también cubre la vista).

Adicionalmente, agregar 1 test de la vista HTML en `tests/integration/test_analytics_entradas_salidas_bp.py`:

```python
    def test_vista_html_para_admin(self, admin_client):
        r = admin_client.get("/analytics/entradas-salidas")
        assert r.status_code == 200
        assert b"<html" in r.data
```

Run: `pytest tests/integration/test_analytics_entradas_salidas_bp.py::TestEndpointBasico::test_vista_html_para_admin -v`
Expected: `1 passed`.

- [ ] **Paso 3: Commit**

```bash
git add templates/analytics_entradas_salidas.html tests/integration/test_analytics_entradas_salidas_bp.py
git commit -m "feat(ui): template entradas-salidas con form, tabla y paginacion"
```

---

## Tarea 9: Tests de extremo a extremo (datos reales + auditoría)

**Files:**
- Modify: `tests/integration/test_analytics_entradas_salidas_bp.py`

- [ ] **Paso 1: Añadir tests que verifican resultados reales y auditoría**

Agregar al final de `tests/integration/test_analytics_entradas_salidas_bp.py`:

```python
import sqlalchemy as sa
from db import set_thread_tenant
from db.connection import get_engine
from db.queries.asistencias import insertar_asistencias
from db.queries.asistencias_entradas_salidas import (
    grupos_funcionales_disponibles,
    listar_marcaciones_por_persona,
)
from db.queries.dispositivos import eliminar_dispositivo, upsert_dispositivo
from db.queries.personas_crud import crear_persona


@pytest.fixture()
def persona_con_datos(dispositivo_test):
    """Persona + 3 marcaciones reales en BD."""
    id_zk = uuid.uuid4().int % 100000
    p = crear_persona(
        nombre=f"E2E-{uuid.uuid4().hex[:6]}",
        identificacion=str(uuid.uuid4().int)[:10],
        id_usuario_zk=str(id_zk),
    )
    from datetime import datetime, timezone
    registros = [
        {"id_usuario": id_zk, "fecha_hora": datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc), "tipo": "entrada"},
        {"id_usuario": id_zk, "fecha_hora": datetime(2026, 7, 10, 17, 0, tzinfo=timezone.utc), "tipo": "salida"},
        {"id_usuario": id_zk, "fecha_hora": datetime(2026, 7, 11, 8, 0, tzinfo=timezone.utc), "tipo": "entrada"},
    ]
    insertar_asistencias(registros, dispositivo_id=dispositivo_test)
    return p["id"]


@pytest.fixture()
def dispositivo_test():
    did = upsert_dispositivo({
        "nombre": f"ZK-E2E-{uuid.uuid4().hex[:8]}",
        "ip": "192.168.50.1",
        "puerto": 4370,
        "protocolo": "TCP",
        "tipo_driver": "zk",
        "prioridad": 1,
        "timeout_seg": 30,
        "activo": True,
        "password_enc": None,
    })
    yield did
    try:
        eliminar_dispositivo(did)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _tenant_setup():
    set_thread_tenant("istpet")
    yield
    from db.connection import clear_thread_tenant
    clear_thread_tenant()


class TestEndpointConDatosReales:

    def test_endpoint_devuelve_marcaciones_reales(self, admin_client, persona_con_datos):
        r = admin_client.get(ENDPOINT, query_string={
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-07-31",
            "persona_id": persona_con_datos,
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["pagination"]["total"] == 3
        assert len(data["items"]) == 3
        # Verificar tipos normalizados
        tipos = [r["tipo"] for r in data["items"]]
        assert "entrada" in tipos
        assert "salida" in tipos

    def test_endpoint_pagina_datos_correctamente(self, admin_client, persona_con_datos):
        r = admin_client.get(ENDPOINT, query_string={
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-07-31",
            "persona_id": persona_con_datos,
            "per_page": "2",
            "page": "1",
        })
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["items"]) == 2
        assert data["pagination"]["total"] == 3
        assert data["pagination"]["total_pages"] == 2
        assert data["pagination"]["has_next"] is True
        assert data["pagination"]["has_prev"] is False

    def test_endpoint_registra_auditoria(self, admin_client, persona_con_datos):
        """Verifica que el endpoint crea 1 fila en public.audit_log."""
        from db.connection import get_engine
        engine = get_engine()
        # Limpiar audit previo de esta acción
        with engine.connect() as conn:
            conn.execute(sa.text(
                "DELETE FROM public.audit_log WHERE accion = 'analytics_entradas_salidas_consultar'"
            ))
            conn.commit()

        r = admin_client.get(ENDPOINT, query_string={
            "fecha_inicio": "2026-07-01",
            "fecha_fin": "2026-07-31",
            "persona_id": persona_con_datos,
        })
        assert r.status_code == 200
        assert r.get_json()["audit_ok"] is True

        with engine.connect() as conn:
            row = conn.execute(sa.text(
                "SELECT COUNT(*), MAX(detalle::text) FROM public.audit_log "
                "WHERE accion = 'analytics_entradas_salidas_consultar'"
            )).fetchone()
            assert row[0] == 1
            # El detalle no contiene PII de marcaciones
            assert "marcacion_id" not in (row[1] or "")
            assert "count_resultados" in (row[1] or "")


class TestGruposFuncionalesDisponiblesIntegration:

    def test_devuelve_false_sin_tabla(self):
        """Sin la tabla persona_grupos_funcionales, devuelve False."""
        # El conftest no la crea, debe ser False
        set_thread_tenant("istpet")
        try:
            assert grupos_funcionales_disponibles("istpet") is False
        finally:
            from db.connection import clear_thread_tenant
            clear_thread_tenant()
```

- [ ] **Paso 2: Verificar que todos los tests pasan**

Run: `pytest tests/integration/test_analytics_entradas_salidas_bp.py -v`
Expected: todos los tests pasan.

- [ ] **Paso 3: Verificar la suite completa (regresión)**

Run: `pytest tests/ -v`
Expected: todas las suites pasan; ningún test previamente verde se rompe.

- [ ] **Paso 4: Commit**

```bash
git add tests/integration/test_analytics_entradas_salidas_bp.py
git commit -m "test(analytics): cobertura e2e de endpoint, paginacion y auditoria"
```

---

## Tarea 10: Verificación arquitectónica y de capas

**Files:**
- (Sin archivos nuevos; solo verificaciones)

- [ ] **Paso 1: Verificar la regla de capas del ADR-0001**

Run: `pytest tests/unit/test_arquitectura.py -v`
Expected: pasa (no se agregaron imports prohibidos: `app/web/analytics_bp.py` solo importa de `app.domain.*` y `db.queries.*` está importado dentro de funciones, no top-level).

Si falla, verificar:
- `app/web/analytics_bp.py` solo debe importar `app.domain.*` a nivel top-level.
- `db.queries.asistencias_entradas_salidas` se importa dentro de las funciones (no top-level) en `app/web/analytics_bp.py` para mantener `app/web` libre de dependencias de `db.queries`.

- [ ] **Paso 2: Verificar que NO se introdujeron imports circulares**

Run: `python -c "from app import create_app; app = create_app('testing'); print('OK')"`
Expected: `OK` (sin `ImportError` por ciclos).

- [ ] **Paso 3: Verificar que la suite unitaria + integración pasan**

Run: `pytest tests/unit tests/integration -v`
Expected: todas pasan.

- [ ] **Paso 4: Commit (solo si hubo ajustes)**

```bash
git status
# Solo commitear si hay cambios:
git diff --stat
# Si no hay diff, omitir el commit.
```

---

## Tarea 11 (OPCIONAL, P3): Índice en `<tenant>.asistencias` (solo tras EXPLAIN en staging)

> Esta tarea NO se ejecuta en el plan v1. Se documenta como follow-up explícito,
> siguiendo el requisito de la spec: "índices solo después de EXPLAIN en staging".
> Cualquier índice nuevo debe justificarse con un EXPLAIN real ejecutado contra
> un dataset representativo en staging.

**Trigger:** Si el EXPLAIN en staging muestra `Seq Scan on asistencias` para la query:

```sql
SELECT a.id, p.id, p.nombre, a.fecha_hora, a.tipo, d.id, d.nombre
FROM istpet.asistencias a
JOIN istpet.personas p ON p.id = a.persona_id
LEFT JOIN istpet.dispositivos d ON d.id = a.dispositivo_id
WHERE p.id = ANY(...)
  AND a.fecha_hora >= '2026-07-01T00:00:00+00:00'
  AND a.fecha_hora <  '2026-08-01T00:00:00+00:00'
ORDER BY a.fecha_hora ASC
LIMIT 50 OFFSET 0;
```

**Índice candidato (NO ejecutar sin EXPLAIN previo):**

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_asistencias_persona_fecha_tipo
    ON istpet.asistencias (persona_id, fecha_hora)
    INCLUDE (tipo);
```

Este índice cubre el filtro `persona_id = ANY(...)` + `fecha_hora` rango + `ORDER BY fecha_hora`, y permite index-only scan para `tipo`.

**Cuando se decida ejecutar:**
1. Obtener EXPLAIN actual (staging) y archivar en `docs/perf/2026-XX-XX-explain-entradas-salidas.md`.
2. Aplicar índice en ventana de mantenimiento baja (no es bloqueante por `CONCURRENTLY`).
3. Repetir EXPLAIN; comparar.
4. Si la mejora < 20%, revertir el índice (no aporta).
5. Solo entonces commitear la migración Alembic.

---

# Self-Review

**1. Cobertura del spec:**

| Requisito del spec | Tarea(s) |
|---|---|
| Selector/buscador por persona con UUID | T3, T7, T8 |
| Rango semiabierto `[fecha_inicio, fecha_fin + 1)` | T3, T4, T6 |
| Detalle de entradas/salidas con timestamp, dispositivo, tipo | T3, T8 (columnas de la tabla) |
| Agrupación diaria implícita (columna `fecha`) | T3 (campo `fecha` agregado en el dict) |
| Filtro por grupo funcional cuando feature flag exista | T2, T6, T7 (decisión basada en flag + tabla) |
| Fallback por persona si no existe grupo funcional | T6 (`validar_filtro` permite `persona_id` siempre) |
| No depender del feature de horarios (ADR 0003) | T4 (`grupos_funcionales_disponibles` retorna False si tabla no existe → el endpoint rechaza `grupo_funcional_id`) |
| Autorización server-side | T7 (`@require_role("admin", "superadmin", "gestor")`) |
| Alcance `supervisor_grupo` | T6 (`aplicar_alcance_supervisor_grupo`), T7 (lee `g.configuracion_usuario`) |
| Auditoría (1 fila por llamada) | T6 (`_registrar_consulta_audit`), T9 (test que verifica fila en `public.audit_log`) |
| Límites/paginación | T6 (`_parse_int` con clamp 1-200), T8 (UI con prev/next) |
| Normalización de tipo Entrada/Salida | T1 (`normalizar_tipo_marcacion`) |
| Índices solo después de EXPLAIN | T11 (documentado, no ejecutado) |
| UI | T8 (`templates/analytics_entradas_salidas.html`) |
| Tests | T1, T2, T3, T4, T6, T7, T9 (unit + integration) |
| Validación VA1 (`horario_por_grupo=false`, persona_id → 200) | T9 (test `test_endpoint_devuelve_marcaciones_reales`) |
| Validación VA1 (`horario_por_grupo=false`, grupo_funcional_id → 400) | T7 (test `test_grupo_funcional_con_flag_off_retorna_400`) |
| Validación VA2 (con flag + grupo_funcional_id → unión de personas) | T4 (`TestListarMarcacionesPorGrupoFuncional`) + T7 (ruta) |
| Validación VA3 (estable ante migraciones del ADR 0003) | T2 (`grupos_funcionales_disponibles` detecta tabla dinámicamente) |
| Validación VA4 (coincide con SQL directo) | T3 + T9 (tests verifican `listar_marcaciones_por_persona` retorna lo que la query directa retornaría) |
| Sin nuevos decoradores | T7 (reusa `@require_role` existente) |
| Sin cache Redis | T7 (consulta directa, sin cache) |
| Sin redefinir precedencia de horarios | Plan no toca `app/domain/schedule.py` |

**2. Escaneo de placeholders:**

- ❌ "TBD" / "TODO" / "implement later": no aparecen.
- ❌ "Add appropriate error handling": todos los errores tienen código explícito (`formato_fecha_invalido`, `rango_invalido`, `uuid_invalido`, `filtro_requerido`, `grupo_funcional_no_disponible`).
- ❌ "Similar to Task N": cada snippet está copiado completo (los snippets de queries son largos porque SQL no se trunca).
- ❌ "References to types not defined": todas las funciones referenciadas están definidas en el plan.

**3. Consistencia de tipos y nombres:**

- `normalizar_tipo_marcacion(raw) -> str` definido en T1, usado en T3 y T4. ✓
- `listar_marcaciones_por_persona(persona_id, fecha_inicio, fecha_fin, limit, offset)` consistente en T3, T6, T7. ✓
- `grupos_funcionales_disponibles(schema) -> bool` definido en T2, usado en T6, T7. ✓
- Shape de respuesta JSON idéntico en T6 (definición) y T8 (consumidor JS). Campos: `items`, `pagination`, `filtros_aplicados`, `audit_ok`. ✓
- Nombres de roles (`admin`, `superadmin`, `gestor`) consistentes con el resto del codebase (`app/web/analytics_bp.py:25`, `app/web/reports_bp.py:354`). ✓
- Endpoint path `/api/analytics/entradas-salidas` consistente entre T7 (servidor) y T8 (template JS). ✓

---

# Riesgos identificados

1. **Riesgo: la query `ANY(CAST(:personas AS uuid[]))` puede ser lenta con miles de personas en el grupo funcional.** Mitigación: el spec limita el alcance a "grupo funcional", no a "todos los empleados". Si en la práctica un grupo funcional tiene >1000 personas, considerar paginación por persona + merge en Python. Documentar como P3.

2. **Riesgo: `g.configuracion_usuario` puede no estar hidratado en el `before_request` actual** (`app/tenant.py`). Mitigación: el código en T7 usa `g.get("configuracion_usuario") or {}` con fallback defensivo. Si no está, supervisor_grupo queda inactivo (no rompe el endpoint).

3. **Riesgo: el `audit_log.detalle` puede crecer si `count_resultados` es grande.** Mitigación: solo se guarda el conteo, no los IDs de las marcaciones.

4. **Riesgo: tests de integración dependen de pgserver.** Mitigación: ya gestionado por `pytest_collection_modifyitems` en `tests/conftest.py` (skip automático si no hay PostgreSQL).

---

> Handoff: la Tarea 11 es explícitamente opcional y NO se ejecuta en v1; se documenta para que el implementador la relance cuando tenga un EXPLAIN real de staging. El plan está listo para ejecución con el sub-skill `subagent-driven-development` o `executing-plans`.