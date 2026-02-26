# Plan de Refactorización — Lógica de Informes y UI

## Resumen de cambios solicitados

| # | Cambio | Archivos afectados |
|---|--------|--------------------|
| 1 | Tardanza relativa al horario individual, margen fijo 5 min | `script.py` |
| 2 | Omitir días sin observaciones en el PDF | `script.py` |
| 3 | Horarios obligatorios; sin ellos no se genera ningún reporte | `app.py`, `index.html` |
| 4 | Informe general solo incluye personas del documento | `app.py` (ya parcial, completar) |
| 5 | Eliminar campos de configuración avanzada (dejar solo excluir) | `script.py`, `app.py`, `index.html` |
| 6 | Tres tipos de reporte: General, Por persona, Por varias personas | `app.py`, `index.html` |
| 7 | Separar fechas del bloque ZK en la UI | `index.html` |

---

---

## Cambio 1 — Tardanza relativa al horario individual (margen fijo 5 min)

### Lógica actual

`analizar_dia()` y `analizar_por_persona()` calculan el margen de tolerancia como la diferencia entre `tardanza_leve` (08:00) y `tardanza_severa` (08:05) sacadas de config → da 5 minutos. Cuando hay horario individual ya hace la comparación relativa. Cuando no hay horario, cae al modo global (comparación contra las horas absolutas del config).

### Lógica nueva

El margen de 5 minutos pasa a ser una **constante fija** en el código, no configurable. La lógica global (sin horario) se **elimina** — si una persona no está en la lista de horarios simplemente se omite del análisis.

**Regla definitiva:**
- `delta = hora_llegada_real − hora_entrada_programada` (en minutos)
- `delta ≤ 0` → puntual, sin observación
- `0 < delta ≤ 5` → **Tardanza leve**
- `delta > 5` → **Tardanza severa**

### Cambios en `script.py`

**`analizar_dia()`**
- Eliminar parámetros `hora_tardanza_leve: str`, `hora_tardanza_severa: str`, `max_almuerzo_min: int` de la firma.
- Eliminar las líneas que crean `h_leve`, `h_severa`, `grace_min` desde esos parámetros.
- Añadir constante interna: `MARGEN_LEVE_MIN = 5`
- Eliminar el bloque `else` de la lógica global (el que compara contra `h_leve` / `h_severa` cuando `hora_prog` es `None`).
- Si `horario_persona is None` para una persona → saltar esa persona (`continue`), no analizarla.
- Si `info["trabaja"]` es `False` → la persona tiene día libre; seguir registrando marcaciones anómalas en ese día libre como `incompleto`, pero NO generar tardanza.

**`analizar_por_persona()`**
- Eliminar lectura de `config["tardanza_leve"]`, `config["tardanza_severa"]`, `config["max_almuerzo_min"]` al inicio de la función.
- Reemplazar `grace_min = _minutos_diferencia(h_leve, h_severa)` con la constante `MARGEN_LEVE_MIN = 5`.
- Eliminar el bloque `else` de lógica global (comparación contra `h_leve`/`h_severa` cuando `hora_prog is None`).
- Si `horario_persona is None` → no incluir esa persona en `resultado`.

**`DEFAULT_CONFIG` (líneas 46–53)**
- Eliminar las claves `tardanza_leve`, `tardanza_severa` y `max_almuerzo_min`.
- Dejar solo `duplicado_min` y `excluidos`.

---

## Cambio 2 — Omitir días sin observaciones en el PDF

### Lógica actual

`analizar_por_persona()` acumula todos los días en `dias_list` independientemente de si hay observaciones. `generar_pdf_persona()` renderiza todos los días mostrando `"✓ Ok"` cuando no hay nada.

`generar_pdf()` (general) renderiza todas las personas en el día, incluyendo las que llegaron bien.

### Lógica nueva

#### En `analizar_por_persona()`

Al construir `dias_list`, **no agregar** un día si cumple todas estas condiciones:
- `estado == "ok"` (sin tardanza, sin exceso de almuerzo)
- `observaciones == []`
- `estado != "incompleto"` (días con registros anómalos sí se incluyen)
- `estado != "libre"` (días libres con marcaciones sí se incluyen)

Es decir: un día perfecto y limpio no se añade a la lista.

Si al final un empleado no tiene ningún día con observaciones, **sí aparece** en el reporte, pero con una única línea de resumen: `"Sin novedades en el período consultado."` (para confirmar que fue revisado).

#### En `analizar_dia()` (para el reporte general)

El resultado actual es un dict con listas: `tardanza_leve`, `tardanza_severa`, `almuerzo_largo`, `registros_incompletos`. Esas listas ya solo incluyen personas con problemas — esto ya está bien. El resumen del día solo aparece en el PDF si hay al menos un flag.

**Cambio en `generar_pdf()` (reporte general):** Si el dict de un día tiene todos los conteos en 0, **omitir ese día del PDF**. Si el período completo no tiene ningún día con observaciones, mostrar una página de "Sin novedades en el período consultado."

---

## Cambio 3 — Horarios obligatorios para generar cualquier reporte

### Lógica actual

`_build_pdf()` en `app.py` carga horarios y si no hay, pone `horarios = None` y continúa con lógica global.

### Lógica nueva

En `_build_pdf()` (o antes de llamarlo en la ruta `/generar-desde-db`):

1. Llamar a `db_module.get_horarios()`
2. Si `horarios["by_id"]` está vacío → **retornar error 400** con mensaje:
   > "No se pueden generar reportes sin horarios cargados. Suba el archivo de horarios primero."
3. Eliminar el bloque `if not horarios["by_id"]: horarios = None`. Los horarios serán siempre requeridos.
4. **No eliminar** el bloqueo del Cambio 4 (solo personas del documento) — esto ahora aplica a todos los modos.

En `index.html`: deshabilitar visualmente el botón "Generar Reporte PDF" y mostrar aviso si el estado de horarios tiene `total == 0`. Esto da feedback inmediato sin necesidad de hacer la petición.

---

## Cambio 4 — Informe general solo incluye personas del documento

### Lógica actual

En `_build_pdf()` hay un bloque condicional:
```python
if horarios is not None and modo == "general":
    # filtrar registros al conjunto de personas del horario
```
Funciona pero está condicionado a `modo == "general"`.

### Lógica nueva

Con horarios ahora obligatorios, **eliminar** la condición `modo == "general"` del filtro. El filtro aplica siempre — en `generar_pdf()` y en `generar_pdf_persona()` el análisis ya descarta personas sin horario (Cambio 1). No hace falta filtrar en dos lugares.

El bloque en `_build_pdf()` se simplifica: siempre filtrar `registros` al conjunto de IDs/nombres del documento. Si queda vacío → error:
> "Ningún registro del período corresponde a personas del archivo de horarios."

---

## Cambio 5 — Simplificar configuración avanzada

### En `script.py`

`DEFAULT_CONFIG` queda solo con:
```python
DEFAULT_CONFIG = {
    "duplicado_min": 3,
    "excluidos":     [],
}
```

Las firmas de `analizar_dia()` y `analizar_por_persona()` ya no reciben parámetros de tardanza (Cambio 1).

**En `generar_pdf()` y `generar_pdf_persona()`:** eliminar las filas de la tabla de configuración que muestran:
- "Tardanza leve desde: HH:MM"
- "Tardanza severa desde: HH:MM"
- "Almuerzo máximo: N minutos"

Reemplazarlas por una sola línea informativa:
- "Tolerancia de entrada: 5 minutos | Almuerzo: según horario individual"

### En `app.py`

`_parse_config()` deja de leer `tardanza_leve`, `tardanza_severa`, `max_almuerzo_min` del body JSON. Solo lee `excluidos` y `duplicado_min` (este último con su default fijo).

En `_build_pdf()`, las llamadas a `analizar_dia()` y `analizar_por_persona()` dejan de pasar los parámetros de tardanza.

### En `index.html`

Dentro del `<div class="collapse" id="configAvanzada">`, eliminar los tres `<div class="col-md-4">` de:
- Tardanza Leve (HH:MM)
- Tardanza Severa (HH:MM)
- Max. Almuerzo (min)

Dejar solo el campo de "Personas a excluir".

El `<button>` de "Configuración avanzada" se puede mantener (para ocultar/mostrar el campo de excluidos) o simplificar a una línea siempre visible. Se recomienda dejar el campo excluidos siempre visible para simplificar la UI.

---

## Cambio 6 — Tres tipos de reporte

### Definición de cada modo

| Modo | Selector | Genera |
|------|----------|--------|
| `general` | Ninguno | Todas las personas del documento, organizadas por día. Usa `analizar_dia()` + `generar_pdf()`. |
| `persona` | Una persona (obligatorio, sin opción "TODAS") | Informe detallado de exactamente 1 persona. Usa `analizar_por_persona()` + `generar_pdf_persona()` con 1 persona. |
| `varias` | 1 o más personas (multiselect) | Informe por persona para el subconjunto seleccionado. Usa `analizar_por_persona()` + `generar_pdf_persona()` con N personas. |

### En `app.py`

Renombrar el modo `"persona"` a dos modos distintos en `/generar-desde-db`:

```
modo = "general"  →  analizar_dia + generar_pdf
modo = "persona"  →  analizar_por_persona + generar_pdf_persona, con persona = string (1 persona)
modo = "varias"   →  analizar_por_persona + generar_pdf_persona, con personas = list[str] (1..N)
```

Para `modo = "persona"`:
- El body JSON envía `persona: "Nombre Apellido"` (string)
- Si no se especifica persona o es vacío → error 400

Para `modo = "varias"`:
- El body JSON envía `personas: ["Nombre1", "Nombre2", ...]` (lista)
- Si la lista está vacía → error 400
- El análisis filtra `analisis = {k: v for k, v in analisis.items() if k in personas_set}`

### En `index.html`

**Select de tipo de reporte** — tres opciones:
```html
<option value="general">General (todos, por día)</option>
<option value="persona">Por persona (una sola)</option>
<option value="varias">Por varias personas</option>
```

**Selector de personas — dos paneles distintos:**

*Panel `#persona-group`* (visible cuando `modo == "persona"`):
- `<select id="persona">` sin la opción "TODAS"
- Se carga igual que hoy con `/personas-db`
- Si no hay personas cargadas → deshabilitar el select con aviso

*Panel `#varias-group`* (visible cuando `modo == "varias"`):
- `<select id="personas-varias" multiple>` con todas las personas del período
- Altura visible de ~6 opciones, con scroll
- Instrucción: "Ctrl+clic para seleccionar varias"
- Botones rápidos: "Seleccionar todas" / "Deseleccionar todas"

**JS — `generarReporte()`:**
- Detectar `modo`:
  - `general`: body sin campo de persona
  - `persona`: body con `persona: sel.value`; bloquear si valor vacío
  - `varias`: body con `personas: Array.from(sel.selectedOptions).map(o => o.value)`; bloquear si array vacío

**JS — listener del select `#modo`:**
- Actualizar visibilidad de `#persona-group` y `#varias-group`
- `general` → ocultar ambos
- `persona` → mostrar `#persona-group`, ocultar `#varias-group`
- `varias` → ocultar `#persona-group`, mostrar `#varias-group`; cargar multiselect

---

## Cambio 7 — Separar fechas del bloque ZK en la UI

### Problema actual

Las fechas (`zk-fecha-inicio` / `zk-fecha-fin`) están dentro de la sección del dispositivo ZK, visualmente acopladas al botón "Sincronizar". El usuario puede confundir las fechas como filtro de sincronización. Además el botón de sync ahora debe hacer sync completo (sin filtro de fechas).

### Nueva estructura de la UI (de arriba a abajo)

```
┌─────────────────────────────────────────────────────┐
│  CARD HORARIOS (ya existe)                          │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  CARD DISPOSITIVO ZK                                │
│  • Estado de conexión + estadísticas DB             │
│  • Botón "Sincronizar" (sin fechas, sync completo)  │
│  • Zona de mantenimiento (detalles/limpiar)         │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  CARD PERÍODO DEL INFORME ← NUEVO                   │
│  • Label: "Seleccione el período a analizar"        │
│  • Fecha inicio  ──  Fecha fin                      │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  FORMULARIO DEL REPORTE (ya existe, simplificado)   │
│  • Tipo de reporte                                  │
│  • Selector de personas (según modo)                │
│  • Excluir personas (siempre visible, sin collapse) │
│  • Botón "Generar Reporte PDF"                      │
└─────────────────────────────────────────────────────┘
```

### Cambios en `index.html`

**Bloque ZK:**
- Eliminar el `<div class="row g-3 mb-3">` con los inputs de fecha y el botón "Sincronizar".
- Añadir directamente bajo el status card un botón `<button onclick="iniciarSync()">Sincronizar</button>` sin inputs de fecha.

**Nueva card "Período del informe":**
- Añadir después del bloque ZK y antes del `<div id="report-form">`.
- Estilo visual: card con borde izquierdo azul similar al `status-card`.
- Contenido: label, dos `<input type="date">` con IDs `fecha-inicio` y `fecha-fin`, con los mismos defaults que hoy (primer y último día del mes actual).
- Los listeners de cambio de fecha que recargan el selector de personas se mueven aquí.

**`iniciarSync()`:**
- Eliminar la lectura de `fi` y `ff` desde los inputs de fecha.
- Enviar la petición POST a `/sincronizar` con body `{}` (sin fechas → sync completo).
- Eliminar la validación `if (!fi || !ff)`.

**`generarReporte()`:**
- Leer `fecha-inicio` y `fecha-fin` desde los nuevos IDs.

**Configuración avanzada:**
- Eliminar el `<div class="collapse" id="configAvanzada">` y su botón toggle.
- Colocar el campo "Personas a excluir" directamente antes del botón "Generar", como campo simple siempre visible.

---

## Cambios en el PDF (generar_pdf y generar_pdf_persona)

### `generar_pdf()` — Reporte general

**Tabla de configuración en el encabezado**: eliminar filas de tardanza y almuerzo. Dejar solo:
- Período analizado
- Fuente de datos
- Total personas incluidas
- Tolerancia: 5 minutos (fija) | Almuerzo: según horario individual

**Días sin ninguna observación**: si todos los conteos del día son 0, el día no se escribe en el PDF. Si el informe completo queda vacío → página única con "Sin novedades en el período consultado."

**Tabla del día**: las columnas de "Tardanza leve" y "Tardanza severa" en el resumen pueden fusionarse en "Tardanzas (leve/severa)" para simplificar visualmente.

### `generar_pdf_persona()` — Reporte por persona/varias

**Tabla de configuración en el encabezado**: misma simplificación que arriba.

**Tabla de días por persona**: omitir las filas donde `estado == "ok"` y `observaciones == []`.

Si una persona tiene todos sus días limpios → en lugar de la tabla de días, mostrar una línea:
> "Sin novedades registradas en el período consultado."

**Resumen por persona**: mantener los contadores (días analizados, tardanzas leves, severas, excesos de almuerzo, incompletos). Esto da contexto incluso si no hay observaciones que listar.

---

## Orden de implementación recomendado

1. **`script.py`** — Constante `MARGEN_LEVE_MIN`, eliminar parámetros globales de tardanza/almuerzo, lógica de omitir días limpios, adaptar `DEFAULT_CONFIG`, adaptar PDFs. Todo esto es autónomo del frontend.

2. **`app.py`** — Simplificar `_parse_config()`, añadir guard de horarios obligatorios, añadir modo `"varias"` en `_build_pdf()`, actualizar llamadas a `analizar_dia()`.

3. **`index.html`** — Reorganizar UI: separar fechas, simplificar config avanzada, añadir multiselect, actualizar `generarReporte()` e `iniciarSync()`.

Cada paso es independiente y se puede probar por separado. Completar 1 antes de 2 porque 2 llama funciones de 1.

---

## Precauciones y casos borde

| Caso | Comportamiento esperado |
|------|------------------------|
| Persona en la DB pero no en el documento de horarios | No aparece en ningún reporte |
| Persona en el documento pero sin registros en el período | No aparece (sin registros = sin análisis) |
| Día laboral sin ningún registro de entrada | No se detecta como ausencia en esta versión — es una mejora futura |
| Modo `varias` con una sola persona seleccionada | Funciona igual que `persona`, usa `generar_pdf_persona()` |
| Período sin ninguna observación en ningún empleado | El PDF generado muestra una página de "Sin novedades" en lugar de un informe vacío |
| Horarios con `almuerzo_min = 0` | No se analiza almuerzo para esa persona, nunca se reporta exceso |
| Sábado con `almuerzo_min > 0` en el horario | `_get_info_dia()` ya fuerza `almuerzo_min = 0` en sábado — sin cambios |

---

## Estado de implementación

> Fecha de revisión: 2026-02-25

| # | Cambio | Estado | Notas |
|---|--------|--------|-------|
| 1 | Tardanza relativa, margen 5 min fijo | **PENDIENTE** | Lógica global aún en `script.py:324-337` y `507-517` |
| 2 | Omitir días sin observaciones | **PENDIENTE** | `dias_list.append(dia_info)` en línea 545 es incondicional |
| 3 | Horarios obligatorios | **PENDIENTE** | `app.py:120-121` todavía hace `horarios = None` si vacío |
| 4 | Informe general solo con personas del documento | **PARCIAL** | Guard existe pero condicionado a `modo == "general"` (`app.py:124`) |
| 5 | Eliminar config avanzada de tardanza/almuerzo | **PENDIENTE** | `DEFAULT_CONFIG` aún tiene `tardanza_leve`, `tardanza_severa`, `max_almuerzo_min` |
| 6 | Tres tipos de reporte (general / persona / varias) | **PENDIENTE** | Solo existen `general` y `persona` |
| 7 | Separar fechas del bloque ZK en la UI | **PENDIENTE** | Fechas aún dentro del bloque ZK |

---

## Referencias exactas de código

### `script.py`

#### Cambio 1 + 5 — `DEFAULT_CONFIG` (líneas 46–60)

**Eliminar:**
```python
"tardanza_leve":    "08:00",
"tardanza_severa":  "08:05",
"max_almuerzo_min": 60,
```
**Dejar solo:**
```python
DEFAULT_CONFIG = {
    "duplicado_min": 10,
    "excluidos":     [],
}
```

#### Cambio 1 — `analizar_dia()` firma (línea 237)

**Actual:**
```python
def analizar_dia(
    registros_dia: list[dict],
    hora_tardanza_leve: str,
    hora_tardanza_severa: str,
    max_almuerzo_min: int,
    horarios: dict = None,
) -> dict:
```
**Nueva:**
```python
MARGEN_LEVE_MIN = 5  # constante a nivel de módulo, antes de analizar_dia

def analizar_dia(
    registros_dia: list[dict],
    horarios: dict,
) -> dict:
```

#### Cambio 1 — `analizar_dia()` inicio (líneas 256–260)

**Eliminar las 5 líneas:**
```python
h_leve   = datetime.strptime(hora_tardanza_leve,   "%H:%M").time()
h_severa = datetime.strptime(hora_tardanza_severa, "%H:%M").time()
grace_min = _minutos_diferencia(h_leve, h_severa)
if grace_min <= 0:
    grace_min = 5
```
No se necesita reemplazo: `MARGEN_LEVE_MIN` ya es la constante global.

#### Cambio 1 — `analizar_dia()` bloque `else` global (líneas 297–299 y 324–337)

**Eliminar el `else` entero** (el bloque que asigna `hora_prog = None` / `max_almuerzo_per = max_almuerzo_min`):
```python
else:
    hora_prog        = None
    max_almuerzo_per = max_almuerzo_min
```
**Reemplazar por:**
```python
else:
    continue  # sin horario → no analizar
```

**Eliminar el bloque `else` de tardanza global** (líneas 324–337):
```python
else:
    # Lógica global (sin horario individual)
    if hora_llegada > h_severa:
        ...
    elif hora_llegada > h_leve:
        ...
```
(Simplemente borrar; el `continue` anterior ya evita llegar aquí.)

Cambiar también `grace_min` → `MARGEN_LEVE_MIN` en las comparaciones de retraso (líneas 310–317):
```python
# antes
if retraso > grace_min:
    ...
elif retraso > 0:
# después  (sin cambio de lógica, solo el nombre)
if retraso > MARGEN_LEVE_MIN:
    ...
elif retraso > 0:
```

#### Cambio 1 — `analizar_por_persona()` inicio (líneas 399–406)

**Eliminar:**
```python
h_leve   = datetime.strptime(config["tardanza_leve"],   "%H:%M").time()
h_severa = datetime.strptime(config["tardanza_severa"], "%H:%M").time()
max_almuerzo_min = config.get("max_almuerzo_min", 60)
grace_min = _minutos_diferencia(h_leve, h_severa)
if grace_min <= 0:
    grace_min = 5
```

#### Cambio 1 — `analizar_por_persona()` bloque sin horario (líneas 466–468)

**Eliminar:**
```python
else:
    hora_prog        = None
    max_almuerzo_per = max_almuerzo_min
```
**Reemplazar por:** (al final del bloque `if horario_persona is not None:`)
```python
else:
    continue  # sin horario → omitir persona completa
```
> Nota: el `continue` debe estar en el nivel del loop `for nombre, por_fecha`, antes de llegar al bucle de días. La estructura actual hace el lookup de horario antes del loop de fechas, así que basta con mover el `else` y el `continue` ahí.

**Cambio en la lógica de tardanza global** (líneas 507–517): eliminar el bloque `else` completo:
```python
else:
    # ── Tardanza global ────────────────────────────
    if primera["hora"] > h_severa:
        ...
    elif primera["hora"] > h_leve:
        ...
```

Cambiar `grace_min` → `MARGEN_LEVE_MIN` en las comparaciones (líneas 494, 500).

#### Cambio 2 — `analizar_por_persona()` — omitir días limpios (línea 545)

**Actual:**
```python
dias_list.append(dia_info)
```
**Nuevo:**
```python
# Solo agregar días con alguna observación (o días libres/incompletos)
if dia_info["observaciones"] or dia_info["estado"] not in ("ok",):
    dias_list.append(dia_info)
```
> `estado == "libre"` ya tiene observaciones (`["Día libre según horario"]`), así que se incluye. `estado == "incompleto"` también tiene observaciones. Solo los días perfectos (`estado == "ok"`, `observaciones == []`) se omiten.

Después del loop, cuando se construye `resultado[nombre]` (línea 547-551), cambiar:
```python
if dias_list:
    resultado[nombre] = {"dias": dias_list, "resumen": resumen}
```
por:
```python
# Siempre incluir a la persona si tiene días analizados (resumen.total_dias > 0)
if resumen["total_dias"] > 0:
    resultado[nombre] = {
        "dias":           dias_list,       # puede estar vacía si todos los días son ok
        "resumen":        resumen,
        "sin_novedades":  not dias_list,   # bandera para el PDF
    }
```

#### Cambio 2 — `generar_pdf()` — omitir días sin observaciones (línea 654–657)

**Actual:**
```python
dias_ordenados = sorted(analisis_por_dia.keys())
for i, dia in enumerate(dias_ordenados):
    story.append(PageBreak())
    story += _pagina_dia(st, dia, analisis_por_dia[dia], config)
```
**Nuevo:**
```python
dias_con_novedades = [
    d for d in sorted(analisis_por_dia.keys())
    if any(analisis_por_dia[d]["resumen"][k] > 0
           for k in ("tardanza_leve","tardanza_severa","almuerzo_largo","incompletos"))
]
if not dias_con_novedades:
    story.append(Paragraph("Sin novedades en el período consultado.", st["normal"]))
else:
    for dia in dias_con_novedades:
        story.append(PageBreak())
        story += _pagina_dia(st, dia, analisis_por_dia[dia], config)
```

#### Cambio 5 — `generar_pdf_persona()` portada (líneas 698–705)

**Eliminar las filas:**
```python
["Tardanza leve desde:", config.get("tardanza_leve", "")],
["Tardanza severa desde:", config.get("tardanza_severa", "")],
["Almuerzo máximo:", f"{config.get('max_almuerzo_min', '')} minutos"],
```
**Reemplazar por:**
```python
["Tolerancia entrada:", "5 minutos (fija)"],
["Almuerzo:", "Según horario individual"],
```

Mismo cambio en `_portada()` de `generar_pdf()` (buscar las mismas filas en esa función).

---

### `app.py`

#### Cambio 3 — guard horarios obligatorios (líneas 119–121)

**Actual:**
```python
horarios = db_module.get_horarios()
if not horarios["by_id"]:
    horarios = None  # Sin horarios → modo global (comportamiento original)
```
**Nuevo:**
```python
horarios = db_module.get_horarios()
if not horarios["by_id"]:
    raise ValueError(
        "No se pueden generar reportes sin horarios cargados. "
        "Suba el archivo de horarios primero."
    )
```

#### Cambio 4 — eliminar condición `modo == "general"` del filtro (línea 124)

**Actual:**
```python
if horarios is not None and modo == "general":
```
**Nuevo:**
```python
if True:   # horarios siempre obligatorios (guard arriba lo garantiza)
```
O simplemente eliminar la condición del `if` y dejar solo el bloque interno.

#### Cambio 5 — `_parse_config()` (líneas 95–102)

**Actual:**
```python
def _parse_config(data: dict) -> dict:
    return {
        "tardanza_leve":    data.get("tardanza_leve",    DEFAULT_CONFIG["tardanza_leve"]),
        "tardanza_severa":  data.get("tardanza_severa",  DEFAULT_CONFIG["tardanza_severa"]),
        "max_almuerzo_min": int(data.get("max_almuerzo_min", DEFAULT_CONFIG["max_almuerzo_min"])),
        "duplicado_min":    DEFAULT_CONFIG["duplicado_min"],
        "excluidos":        data.get("excluidos", []),
    }
```
**Nuevo:**
```python
def _parse_config(data: dict) -> dict:
    return {
        "duplicado_min": DEFAULT_CONFIG["duplicado_min"],
        "excluidos":     data.get("excluidos", []),
    }
```

#### Cambio 5 — llamadas a `analizar_dia()` en `_build_pdf()` (líneas 156–162)

**Actual:**
```python
analisis[fecha] = analizar_dia(
    regs,
    config["tardanza_leve"],
    config["tardanza_severa"],
    config["max_almuerzo_min"],
    horarios=horarios,
)
```
**Nuevo:**
```python
analisis[fecha] = analizar_dia(regs, horarios)
```

#### Cambio 6 — modo `varias` en `_build_pdf()` y `generar_desde_db()`

En `_build_pdf()`, extender el bloque `if modo == "persona":` (línea 143):

**Actual:**
```python
if modo == "persona":
    analisis = analizar_por_persona(registros, config, horarios=horarios)
    if persona and persona != "TODAS":
        if persona not in analisis:
            raise ValueError(f"No se encontraron registros para '{persona}'")
        analisis = {persona: analisis[persona]}
    generar_pdf_persona(pdf_path, analisis, config, nombre_origen)
else:
    # modo general ...
```
**Nuevo:**
```python
if modo in ("persona", "varias"):
    analisis = analizar_por_persona(registros, config, horarios=horarios)

    if modo == "persona":
        if not persona:
            raise ValueError("Se requiere especificar una persona para el modo 'persona'.")
        if persona not in analisis:
            raise ValueError(f"No se encontraron registros para '{persona}'.")
        analisis = {persona: analisis[persona]}

    elif modo == "varias":
        personas_sel = set(config.get("personas", []))
        if not personas_sel:
            raise ValueError("Se requiere al menos una persona para el modo 'varias'.")
        analisis = {k: v for k, v in analisis.items() if k in personas_sel}
        if not analisis:
            raise ValueError("Ninguna de las personas seleccionadas tiene registros en el período.")

    generar_pdf_persona(pdf_path, analisis, config, nombre_origen)
else:
    # modo general ...
```

En `generar_desde_db()` (línea 246–248), agregar lectura del campo `personas`:

**Actual:**
```python
modo    = data.get('modo', 'general')
persona = data.get('persona', 'TODAS')
config  = _parse_config(data)
```
**Nuevo:**
```python
modo    = data.get('modo', 'general')
persona = data.get('persona', '')
config  = _parse_config(data)
if modo == 'varias':
    config['personas'] = data.get('personas', [])
```

En el bloque de respuesta JSON al final (línea 266-271):
```python
label = {'general': 'General', 'persona': 'Persona', 'varias': 'Varias_Personas'}.get(modo, 'Reporte')
```

---

### `index.html`

#### Cambio 7 — Separar fechas del bloque ZK

Las fechas actuales se encuentran dentro del bloque ZK. Buscar el `<div>` que contiene `zk-fecha-inicio` y `zk-fecha-fin` dentro de la sección `#tab-zk` y **moverlo** a un nuevo `<div class="card ...">` independiente entre el bloque ZK y el formulario del reporte.

IDs de los inputs de fecha a cambiar: `zk-fecha-inicio` → `fecha-inicio`, `zk-fecha-fin` → `fecha-fin`.

#### Cambio 6 — Select de modo y paneles de personas

En el formulario del reporte, donde actualmente está el `<select id="modo">` y el `<select id="persona">`:

1. Agregar opción `varias` al select de modo.
2. Renombrar el panel actual de persona a `#persona-group` (ya existe implícitamente).
3. Añadir después un nuevo `<div id="varias-group" style="display:none">` con:
   - `<select id="personas-varias" multiple size="6">`
   - Botones "Seleccionar todas" / "Deseleccionar todas"
4. En el JS, listener `change` del select `#modo` que muestra/oculta los dos paneles.

#### Cambio 5 + 7 — Eliminar collapse de configuración avanzada

Buscar el `<div class="collapse" id="configAvanzada">` y su botón toggle. Extraer solo el campo de "Personas a excluir" y colocarlo directamente visible antes del botón "Generar Reporte PDF". Eliminar el resto.

---

## Plan de pruebas

### Pruebas manuales — `script.py`

| Escenario | Verificar |
|-----------|-----------|
| Persona con horario, llega a tiempo | No aparece en `dias_list` (día omitido) |
| Persona con horario, llega 3 min tarde | Aparece con "Tardanza leve (+3m)" |
| Persona con horario, llega 7 min tarde | Aparece con "Tardanza severa (+7m)" |
| Persona SIN horario | No aparece en `resultado` de `analizar_por_persona()` |
| Persona con horario, todos los días ok | `resultado[nombre]["sin_novedades"] == True`, `dias == []` |
| Período sin ninguna novedad | `generar_pdf()` genera página única "Sin novedades" |
| `analizar_dia()` llamado sin horarios | Debe lanzar `TypeError` o simplemente no analizar a nadie |

### Pruebas manuales — `app.py`

| Escenario | Verificar |
|-----------|-----------|
| POST `/generar-desde-db` sin horarios cargados | Respuesta 400 con mensaje de horarios requeridos |
| POST con `modo=varias` y `personas=["Ana", "Luis"]` | PDF solo contiene a Ana y Luis |
| POST con `modo=varias` y `personas=[]` | Respuesta 400 |
| POST con `modo=persona` sin campo `persona` | Respuesta 400 |
| Config sin `tardanza_leve` / `tardanza_severa` en el body | No debe fallar — `_parse_config` ya no los lee |

### Pruebas manuales — UI

| Escenario | Verificar |
|-----------|-----------|
| Sin horarios cargados, botón "Generar" | Deshabilitado o aviso visible |
| Cambiar modo a "varias" | `#varias-group` visible, `#persona-group` oculto |
| Cambiar modo a "persona" | `#persona-group` visible, `#varias-group` oculto |
| Cambiar modo a "general" | Ambos paneles ocultos |
| Botón "Sincronizar" | Hace POST a `/sincronizar` con body `{}` (sin fechas) |
| Cambiar fecha-inicio / fecha-fin | Recarga selector de personas en el panel activo |
| "Seleccionar todas" en modo varias | Todas las opciones del multiselect quedan seleccionadas |
