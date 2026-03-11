# Plan de Implementación — Sistema de Informes Biométricos RRHH ISTPET
**Versión:** 2.0
**Fecha:** 2026-03-11
**Estado:** Borrador técnico para revisión

---

## Resumen ejecutivo

Este plan cubre dos funcionalidades independientes que pueden implementarse en cualquier orden:

| Parte | Funcionalidad | Complejidad |
|-------|--------------|-------------|
| [Parte I](#parte-i--horas-de-contrato) | Horas de contrato (semanales o mensuales) + verificación de cumplimiento + tiempo extra | Media |
| [Parte II](#parte-ii--permisos-temporales-durante-la-jornada) | Permisos temporales durante la jornada + categorización de días con múltiples breaks | Alta |

Ambas partes son **retrocompatibles**: no rompen datos ni flujos existentes.

---
---

# PARTE I — Horas de Contrato

---

## 1. Descripción

Agregar a la configuración de horarios del personal el campo **horas de contrato** (ya sea semanal o mensual), con validación de exclusividad entre ambas, visualización en la tabla de horarios, y nuevas opciones en los reportes para **verificar cumplimiento** de horas estipuladas y **contabilizar tiempo extra**.

---

## 2. Base de datos (`db.py`)

> **Commit:** `feat(db): add horas_semana and horas_mes columns to horarios_personal`

### 2.1 Nuevas columnas

Agregar al `CREATE TABLE horarios_personal` (dentro del `executescript`):

```sql
horas_semana   REAL,   -- Horas contrato por semana (ej: 40). NULL si usa horas_mes.
horas_mes      REAL,   -- Horas contrato por mes (ej: 160). NULL si usa horas_semana.
```

> La restricción de exclusividad se enforcea en el backend, NO en la base de datos. SQLite no soporta `CHECK` entre columnas de forma práctica.

### 2.2 Migración automática

En `init_db()`, después de las migraciones existentes:

```python
_migrar_columna(conn, "horarios_personal", "horas_semana", "REAL")
_migrar_columna(conn, "horarios_personal", "horas_mes",    "REAL")
```

### 2.3 Funciones afectadas

- `upsert_horarios()` — agregar `horas_semana` y `horas_mes` en `INSERT` y `ON CONFLICT ... DO UPDATE`
- `get_horarios()` — agregar en el `SELECT`
- `get_horario()` — agregar en el `SELECT`

Patrón en `upsert_horarios()`:

```python
# En el INSERT (lista de columnas):
(id_usuario, ..., notas, fuente, horas_semana, horas_mes, actualizado_en)
VALUES (?, ..., ?, ?, ?, ?, datetime('now'))

# En ON CONFLICT DO UPDATE:
horas_semana = excluded.horas_semana,
horas_mes    = excluded.horas_mes,
```

---

## 3. API Flask (`app.py`)

> **Commit:** `feat(app): validate and expose horas_semana/horas_mes in horarios API`

### 3.1 Validación en `_validar_horario_body()`

Después de la validación actual de `almuerzo_min`:

```python
horas_semana = data.get("horas_semana")
horas_mes    = data.get("horas_mes")

def _parse_horas(val, campo):
    if val is None or str(val).strip() == "":
        return None, None
    try:
        v = float(val)
        if v <= 0:
            raise ValueError
        return v, None
    except (ValueError, TypeError):
        return None, f"'{campo}' debe ser un número positivo."

hs, err = _parse_horas(horas_semana, "horas_semana")
if err: return None, err
hm, err = _parse_horas(horas_mes, "horas_mes")
if err: return None, err

if hs is not None and hm is not None:
    return None, "Solo puede especificarse 'horas_semana' O 'horas_mes', no ambas."

horario["horas_semana"] = hs
horario["horas_mes"]    = hm
```

### 3.2 Exportar CSV (`exportar_horarios_csv()`)

Agregar `"horas_semana"` y `"horas_mes"` al encabezado y filas (antes de `"notas"`).

### 3.3 Nuevos filtros en `_build_pdf()` y `/api/generar-desde-db`

```python
verificar_horas      = filtros.get("verificar_horas",      False)
mostrar_tiempo_extra = filtros.get("mostrar_tiempo_extra",  False)

analisis = analizar_por_persona(
    ...,
    verificar_horas=verificar_horas,
    mostrar_tiempo_extra=mostrar_tiempo_extra,
)

generar_pdf_persona(
    ...,
    filtros={..., "verificar_horas": verificar_horas, "mostrar_tiempo_extra": mostrar_tiempo_extra},
)
```

---

## 4. Offcanvas de configuración (`configuracion.html`)

> **Commit:** `feat(ui): add contract hours radio selector to schedule offcanvas`

Agregar después del bloque de "Almuerzo" y antes de "Notas":

```html
<div class="mb-3">
    <label class="form-label small fw-semibold text-muted">Horas de contrato</label>
    <div class="d-flex gap-3 mb-2">
        <div class="form-check">
            <input class="form-check-input" type="radio" name="mh-tipo-horas"
                   id="mh-tipo-ninguno" value="ninguno" checked onchange="toggleTipoHoras()">
            <label class="form-check-label small" for="mh-tipo-ninguno">Sin estipular</label>
        </div>
        <div class="form-check">
            <input class="form-check-input" type="radio" name="mh-tipo-horas"
                   id="mh-tipo-semana" value="semana" onchange="toggleTipoHoras()">
            <label class="form-check-label small" for="mh-tipo-semana">Por semana</label>
        </div>
        <div class="form-check">
            <input class="form-check-input" type="radio" name="mh-tipo-horas"
                   id="mh-tipo-mes" value="mes" onchange="toggleTipoHoras()">
            <label class="form-check-label small" for="mh-tipo-mes">Por mes</label>
        </div>
    </div>
    <div id="mh-horas-semana-group" style="display:none">
        <input type="number" class="form-control form-control-sm" id="mh-horas-semana"
               min="1" max="168" step="0.5" placeholder="Ej: 40">
        <div class="form-text small text-muted">Horas totales por semana</div>
    </div>
    <div id="mh-horas-mes-group" style="display:none">
        <input type="number" class="form-control form-control-sm" id="mh-horas-mes"
               min="1" max="744" step="0.5" placeholder="Ej: 160">
        <div class="form-text small text-muted">Horas totales por mes</div>
    </div>
</div>
```

> Los radios garantizan la exclusividad en el formulario. El backend tiene la segunda capa de validación.

Actualizar la columna `<th>` en el `<thead>` de la tabla: agregar `<th>H. contrato</th>` entre "Almuerzo" y "Acciones". Actualizar colspan de filas vacías de 11 a 12.

---

## 5. Lógica del formulario (`configuracion.js`)

> **Commit:** `feat(js): implement hours toggle, table column and offcanvas wiring in configuracion`

### 5.1 Nueva función `toggleTipoHoras()`

```javascript
function toggleTipoHoras() {
    const tipo = document.querySelector('input[name="mh-tipo-horas"]:checked').value;
    document.getElementById('mh-horas-semana-group').style.display = tipo === 'semana' ? 'block' : 'none';
    document.getElementById('mh-horas-mes-group').style.display    = tipo === 'mes'    ? 'block' : 'none';
    if (tipo !== 'semana') document.getElementById('mh-horas-semana').value = '';
    if (tipo !== 'mes')    document.getElementById('mh-horas-mes').value    = '';
}
```

### 5.2 Modificar `abrirOffcanvasCrear()`

```javascript
document.getElementById('mh-tipo-ninguno').checked = true;
toggleTipoHoras();
```

### 5.3 Modificar `abrirOffcanvasEditar(h)`

```javascript
if (h.horas_semana) {
    document.getElementById('mh-tipo-semana').checked = true;
    document.getElementById('mh-horas-semana').value = h.horas_semana;
} else if (h.horas_mes) {
    document.getElementById('mh-tipo-mes').checked = true;
    document.getElementById('mh-horas-mes').value = h.horas_mes;
} else {
    document.getElementById('mh-tipo-ninguno').checked = true;
}
toggleTipoHoras();
```

### 5.4 Modificar `guardarHorario()`

```javascript
const tipoHoras = document.querySelector('input[name="mh-tipo-horas"]:checked').value;
if (tipoHoras === 'semana') {
    const v = parseFloat(document.getElementById('mh-horas-semana').value);
    if (!v || v <= 0) return errMh("Ingrese un valor válido para horas semanales.");
    payload.horas_semana = v;
} else if (tipoHoras === 'mes') {
    const v = parseFloat(document.getElementById('mh-horas-mes').value);
    if (!v || v <= 0) return errMh("Ingrese un valor válido para horas mensuales.");
    payload.horas_mes = v;
}
```

### 5.5 Modificar `renderTablaHorarios()` — nueva columna

```javascript
let hContrato = '<span class="text-muted">—</span>';
if (h.horas_semana) hContrato = `${h.horas_semana}h/sem`;
else if (h.horas_mes) hContrato = `${h.horas_mes}h/mes`;

// En el <tr>:
<td class="text-center">${hContrato}</td>
```

---

## 6. Motor de análisis — cálculo diario (`script.py`)

> **Commit:** `feat(script): calculate net worked time per day with _calcular_tiempo_neto_min`

### 6.1 Nueva función auxiliar `_calcular_tiempo_neto_min()`

```python
def _calcular_tiempo_neto_min(marcaciones: list) -> int:
    """
    Suma los minutos netos de presencia sumando cada par Entrada→Salida.
    Ignora registros huérfanos o en orden incorrecto.
    """
    total = 0
    i = 0
    while i < len(marcaciones):
        if marcaciones[i]["tipo"] == "Entrada":
            for j in range(i + 1, len(marcaciones)):
                if marcaciones[j]["tipo"] == "Salida":
                    delta = int(
                        (marcaciones[j]["datetime"] - marcaciones[i]["datetime"])
                        .total_seconds() / 60
                    )
                    if delta > 0:
                        total += delta
                    i = j
                    break
        i += 1
    return total
```

> Para jornada simple (E→S) equivale a `tiempo_dentro`. Para jornada con almuerzo (E→S→E→S) descuenta el tiempo fuera de las instalaciones automáticamente.

### 6.2 Agregar `tiempo_neto_min` a `dia_info`

En los bloques de secuencia válida e inválida dentro de `analizar_por_persona()`:

```python
dia_info["tiempo_neto_min"] = _calcular_tiempo_neto_min(marcaciones)
```

Para días `ausente`, `libre`, `feriado`: `tiempo_neto_min = 0`.

---

## 7. Motor de análisis — agregación y alertas (`script.py`)

> **Commit:** `feat(script): add verificar_horas and mostrar_tiempo_extra to analizar_por_persona`

### 7.1 Nuevos parámetros en `analizar_por_persona()`

```python
def analizar_por_persona(
    ...,
    verificar_horas: bool = False,
    mostrar_tiempo_extra: bool = False,
) -> dict:
```

### 7.2 Agregación al final del loop por persona

```python
if verificar_horas or mostrar_tiempo_extra:
    hs = horario_persona.get("horas_semana")
    hm = horario_persona.get("horas_mes")

    if hs or hm:
        total_neto_min = sum(d.get("tiempo_neto_min", 0) for d in dias_list)

        if hs:
            from collections import defaultdict as _dd
            semanas = _dd(int)
            for d in dias_list:
                if d.get("tiempo_neto_min", 0) > 0:
                    iso = d["fecha"].isocalendar()
                    semanas[(iso[0], iso[1])] += d["tiempo_neto_min"]

            esperado_sem_min = int(hs * 60)
            detalle_semanas, deficit_total_min, excedente_total_min = [], 0, 0
            for (anio, num_sem), trabajados in sorted(semanas.items()):
                diff = trabajados - esperado_sem_min
                detalle_semanas.append({
                    "semana":         f"{anio}-S{num_sem:02d}",
                    "trabajados_min": trabajados,
                    "esperados_min":  esperado_sem_min,
                    "diferencia_min": diff,
                })
                if diff < 0: deficit_total_min    += abs(diff)
                else:        excedente_total_min  += diff

            resumen["horas_contrato_tipo"]  = "semana"
            resumen["horas_contrato_valor"] = hs
            resumen["total_neto_min"]       = total_neto_min
            resumen["deficit_horas_min"]    = deficit_total_min
            resumen["excedente_horas_min"]  = excedente_total_min
            resumen["detalle_semanas"]      = detalle_semanas

        elif hm:
            esperado_mes_min = int(hm * 60)
            diff = total_neto_min - esperado_mes_min
            resumen["horas_contrato_tipo"]  = "mes"
            resumen["horas_contrato_valor"] = hm
            resumen["total_neto_min"]       = total_neto_min
            resumen["deficit_horas_min"]    = abs(diff) if diff < 0 else 0
            resumen["excedente_horas_min"]  = diff if diff > 0 else 0
            resumen["detalle_semanas"]      = []
```

---

## 8. UI de reportes (`reportes.html` + `reportes.js`)

> **Commit:** `feat(ui): add contract hours verification filters to reports page`

Agregar dentro del bloque de opciones, **no activados por defecto**:

```html
<div class="col-12"><hr class="my-1"></div>
<div id="bloque-horas-contrato">
    <div class="col-6 col-md-4">
        <div class="form-check form-switch cursor-pointer">
            <input class="form-check-input" type="checkbox" id="f-verificar-horas">
            <label class="form-check-label small user-select-none" for="f-verificar-horas">
                Verificar horas de contrato
            </label>
        </div>
    </div>
    <div class="col-6 col-md-4">
        <div class="form-check form-switch cursor-pointer">
            <input class="form-check-input" type="checkbox" id="f-tiempo-extra">
            <label class="form-check-label small user-select-none" for="f-tiempo-extra">
                Mostrar tiempo extra / déficit
            </label>
        </div>
    </div>
</div>
```

En `actualizarVisibilidadModo()` (`reportes.js`):

```javascript
const bloquHoras = document.getElementById('bloque-horas-contrato');
if (bloquHoras) bloquHoras.style.display = (v !== 'general') ? 'block' : 'none';
```

En `leerFiltros()`:

```javascript
verificar_horas:      chk('f-verificar-horas'),
mostrar_tiempo_extra: chk('f-tiempo-extra'),
```

---

## 9. Sección PDF — cumplimiento de horas (`script.py`)

> **Commit:** `feat(script): add contract hours compliance section to per-person PDF`

### 9.1 Helper `_fmt_horas()`

```python
def _fmt_horas(minutos: int) -> str:
    """Convierte minutos a 'Xh YYm'. Ej: 487 → '8h 07m'."""
    h, m = divmod(abs(minutos), 60)
    signo = "-" if minutos < 0 else ""
    return f"{signo}{h}h {m:02d}m"
```

### 9.2 Llamada en `generar_pdf_persona()`

```python
_F_horas = filtros.get("verificar_horas",    False)
_F_extra = filtros.get("mostrar_tiempo_extra", False)

if (_F_horas or _F_extra) and resumen.get("horas_contrato_tipo"):
    story += _seccion_horas_contrato(st, resumen)
```

### 9.3 Contenido de `_seccion_horas_contrato()`

- Título: "Cumplimiento de Horas de Contrato"
- Subtítulo: horas estipuladas (semanal o mensual)
- Si `tipo == "semana"`: tabla `Semana | Horas esperadas | Horas trabajadas | Diferencia` con color por fila (verde ≥ 0, amarillo déficit < 2h, rojo déficit ≥ 2h)
- Si `tipo == "mes"`: fila única con el total del período

---

## 10. Exportar CSV de horarios (actualización) (`app.py`)

> **Commit:** `feat(app): include horas_semana and horas_mes in horarios CSV export`

En `exportar_horarios_csv()`, agregar las dos columnas al encabezado y filas:

```python
writer.writerow([..., "horas_semana", "horas_mes", "notas"])
# ...
writer.writerow([..., h.get("horas_semana") or "", h.get("horas_mes") or "", h.get("notas") or ""])
```

---

## 11. Casos borde

| Caso | Comportamiento esperado |
|------|------------------------|
| Sin `horas_semana` ni `horas_mes` | Los filtros no generan ninguna alerta ni sección extra |
| Período < 1 semana con `horas_semana` | Semana parcial con horas reales vs. esperadas (sin prorrateo) |
| Período < 1 mes con `horas_mes` | Total vs. mensual completo; aclarar en el PDF que es período parcial |
| Día incompleto | `tiempo_neto_min` calculado con los pares válidos existentes (puede ser 0) |
| Día ausente | `tiempo_neto_min = 0`, cuenta como horas no trabajadas |
| Día libre / feriado | `tiempo_neto_min = 0`, NO descuenta de horas esperadas |
| Solo entradas sin salida biométrica | `_calcular_tiempo_neto_min` retorna 0 (sin par E→S válido) |

---

## 12. Archivos modificados (Parte I)

| Archivo | Tipo de cambio |
|---------|---------------|
| `db.py` | Migración, SELECT, INSERT/UPDATE |
| `app.py` | Validación, exportar CSV, pasar filtros |
| `script.py` | Nueva función auxiliar, nuevos parámetros, nueva sección PDF |
| `templates/configuracion.html` | Nuevo bloque en offcanvas, nueva columna en `<thead>` |
| `static/js/configuracion.js` | `toggleTipoHoras()`, abrir/editar offcanvas, render tabla |
| `templates/reportes.html` | Dos nuevos toggles (off por defecto) |
| `static/js/reportes.js` | `leerFiltros()`, `actualizarVisibilidadModo()` |

---
---

# PARTE II — Permisos Temporales durante la Jornada

---

## 1. Definición del caso de uso

Un empleado llega a trabajar, durante su jornada solicita permiso para ausentarse un período de tiempo definido (ej: 2 horas), y regresa para continuar trabajando. RRHH autoriza ese permiso con un rango de tiempo específico.

**Secuencia de marcaciones resultante:**

```
Entrada 08:00 → Salida 10:00 → Entrada 12:00 → Salida 17:00
```

Esta secuencia es **idéntica en datos biométricos** a la de un almuerzo extendido. La diferencia es de contexto, no de datos. El sistema necesita que RRHH registre una justificación `permiso` que le diga cómo interpretar esa salida/reentrada.

---

## 2. Estado actual del sistema

### Lo que ya existe
- Secuencia `[E, S, E, S]` es válida (no genera alerta de "incompleto")
- El break intermedio se analiza **como almuerzo** si `almuerzo_min > 0`
- Existe `tipo=almuerzo` con `duracion_permitida_min` que puede suprimir la alerta de exceso

### El problema
- No hay concepto de "permiso" separado del almuerzo
- El sistema no puede validar que el empleado salió en el rango autorizado ni que regresó a tiempo
- Si `almuerzo_min=0`, el break intermedio pasa invisible sin ningún registro
- El PDF etiqueta todo como "almuerzo", no como "permiso"
- No existe campo `hora_retorno_permiso` en la tabla `justificaciones`

---

## 3. Diseño de la solución

### 3.1 Principio fundamental

**Un permiso justificado para un día reemplaza el análisis de almuerzo para ese día.** No coexisten. Esto evita ambigüedad en la secuencia `[E,S,E,S]`.

Si se requiere almuerzo + permiso en el mismo día, se necesitaría una secuencia de 6 marcaciones — cubierta en la sección 8 (Cola de revisión).

### 3.2 Campos necesarios en `justificaciones`

Se necesita **un nuevo campo** que aún no existe:

```
hora_retorno_permiso  TEXT  -- Hora máxima de retorno (HH:MM), ej: "12:00"
```

El campo `hora_permitida` existente se reutiliza como **hora mínima de salida autorizada** (ej: "10:00").

| Campo existente | Rol para `permiso` |
|---|---|
| `tipo` | `"permiso"` (nuevo valor válido) |
| `hora_permitida` | Hora desde la que puede ausentarse, ej: `"10:00"` |
| `hora_retorno_permiso` *(nuevo)* | Hora límite de retorno, ej: `"12:00"` |
| `motivo` | Razón del permiso, ej: `"Cita médica IESS"` |
| `aprobado_por` | Quien autorizó |
| `estado` | `pendiente / aprobada / rechazada` (ya existe) |

### 3.3 Restricción UNIQUE y permisos múltiples en un día

La restricción `UNIQUE(id_usuario, fecha, tipo)` limita a un `permiso` por persona por día. Para múltiples permisos en el mismo día, el mecanismo de `breaks_categorizados` (sección 8) es el camino correcto.

---

## 4. Lógica de análisis (`script.py`)

> **Commit:** `feat(script): add permiso type analysis to analizar_por_persona replacing almuerzo logic`

### 4.1 Punto de entrada en el flujo

```
Si existe justificación tipo="permiso" para (id_usuario, fecha):
    → Ejecutar análisis de PERMISO (ver 4.2)
    → Saltar análisis de almuerzo

Si NO existe:
    → Ejecutar análisis de almuerzo normal (código actual sin cambios)
```

### 4.2 Algoritmo de análisis del permiso

**Precondición:** Existe justificación `tipo=permiso`, estado=`aprobada`.

**Paso 1 — Buscar el par de marcaciones del permiso**

Buscar la primera `Salida` seguida de una `Entrada` (mismo patrón que el código de almuerzo).

**Paso 2 — Validar salida**

```
Si hora_permitida está definida:
    Si salida_real < hora_permitida:
        → Observación informativa (no genera alerta disciplinaria)
        → "Salió a las HH:MM, permiso autorizado desde HH:MM"
    Si salida_real >= hora_permitida:
        → OK
```

**Paso 3 — Validar retorno**

```
retardo_retorno = retorno_real - hora_retorno_permiso (en minutos)

Si retardo_retorno > MARGEN_LEVE_MIN (5 min):
    → RETORNO TARDÍO SEVERO
    → "Retorno tardío del permiso (+Xm sobre límite HH:MM)"
    → resumen["permiso_retorno_tardio"] += 1  →  estado = "severa"

Si 0 < retardo_retorno <= MARGEN_LEVE_MIN:
    → RETORNO TARDÍO LEVE
    → resumen["permiso_retorno_tardio_leve"] += 1  →  estado = "leve"

Si retardo_retorno <= 0:
    → dia_info["justificado"] = True
    → "Permiso OK (retorno HH:MM, límite HH:MM)"
```

**Paso 4 — Solo `[E, S]` con permiso justificado (no regresó)**

```
→ "PERMISO SIN RETORNO — salió a las HH:MM, no registró regreso"
→ resumen["permiso_sin_retorno"] += 1  →  estado = "severa"
```

**Paso 5 — Secuencia inválida + permiso**

Si la secuencia es inválida (ej: `[E,E,S,S]`), el análisis de `incompleto` tiene prioridad y el permiso se ignora.

### 4.3 Campos nuevos en `dia_info`

```python
dia_info["permiso_salida"]   = None  # Hora real de salida del permiso "HH:MM"
dia_info["permiso_retorno"]  = None  # Hora real de retorno "HH:MM"
dia_info["permiso_duracion"] = None  # Duración real en minutos
```

### 4.4 Campos nuevos en `resumen` por persona

```python
resumen["permiso_retorno_tardio"]      = 0
resumen["permiso_retorno_tardio_leve"] = 0
resumen["permiso_sin_retorno"]         = 0
```

---

## 5. Cambios en la base de datos (`db.py`)

> **Commit:** `feat(db): add hora_retorno_permiso column and permiso as valid justification type`

### 5.1 Nueva columna en `justificaciones`

```python
_migrar_columna(conn, "justificaciones", "hora_retorno_permiso", "TEXT")
```

### 5.2 Nuevo tipo válido en `insertar_justificacion()`

```python
# Antes:
('ausencia', 'tardanza', 'almuerzo', 'incompleto', 'salida_anticipada')

# Después:
('ausencia', 'tardanza', 'almuerzo', 'incompleto', 'salida_anticipada', 'permiso')
```

### 5.3 `get_justificaciones_dict()` — incluir el nuevo campo

Agregar `hora_retorno_permiso` al SELECT de la query de justificaciones.

---

## 6. Cambios en la API (`app.py`)

> **Commit:** `feat(app): validate permiso type with hora_permitida and hora_retorno_permiso required fields`

### 6.1 `POST /api/justificaciones`

Aceptar los nuevos campos:

```json
{
  "tipo": "permiso",
  "hora_permitida": "10:00",
  "hora_retorno_permiso": "12:00",
  "motivo": "Cita IESS",
  "aprobado_por": "RRHH"
}
```

**Validaciones específicas para `tipo=permiso`:**

1. `hora_permitida` — **requerido**
2. `hora_retorno_permiso` — **requerido**
3. `hora_retorno_permiso` debe ser **posterior** a `hora_permitida`
4. Ambas deben ser formato HH:MM válido

---

## 7. Cambios en la interfaz (`justificaciones.html` + `justificaciones.js`)

> **Commit:** `feat(ui): add dynamic permiso fields and frontend validation to justificaciones form`

### 7.1 Formulario dinámico

Cuando el usuario selecciona `tipo=permiso`, aparecen:

```
Tipo: [ Permiso temporal ▼ ]

  ┌── Rango del permiso (obligatorio) ─────────────────────┐
  │  Puede salir desde:  [ 10:00 ]  (hora_permitida)       │
  │  Debe regresar a:    [ 12:00 ]  (hora_retorno_permiso) │
  └────────────────────────────────────────────────────────┘

  Motivo: [ Cita médica IESS  ]
  Aprobado por: [ RRHH        ]
```

### 7.2 Tabla de justificaciones

Para `tipo=permiso`, la columna de "Reglas" muestra:

```
Permiso: 10:00 → 12:00
```

### 7.3 Validación frontend

```javascript
if (tipo === 'permiso') {
    if (!horaPermitida)   return error("Especifique la hora desde la que puede ausentarse");
    if (!horaRetorno)     return error("Especifique la hora de retorno límite");
    if (horaRetorno <= horaPermitida) return error("El retorno debe ser posterior a la salida");
}
```

---

## 8. Extensión — Cola de revisión para días con 6+ marcaciones

> **Commit:** `feat(db,app): add breaks_categorizados table and CRUD routes for multi-break days`

### 8.1 El problema

El código actual en `script.py` solo acepta dos secuencias válidas:

```python
_seq_valida = _tipos_seq in (
    ["Entrada", "Salida"],
    ["Entrada", "Salida", "Entrada", "Salida"],
)
```

Cualquier secuencia `[E, S, E, S, E, S]` cae en "incompleto". El sistema no puede distinguir si corresponde a almuerzo + permiso legítimos, almuerzo + salida sin autorización, o error del biométrico.

### 8.2 Nueva tabla `breaks_categorizados`

```sql
CREATE TABLE IF NOT EXISTS breaks_categorizados (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario   TEXT    NOT NULL,
    fecha        TEXT    NOT NULL,
    hora_inicio  TEXT    NOT NULL,   -- HH:MM — hora de Salida del break
    hora_fin     TEXT    NOT NULL,   -- HH:MM — hora de Entrada de retorno
    duracion_min INTEGER,
    categoria    TEXT    NOT NULL CHECK(categoria IN ('almuerzo','permiso','injustificado')),
    motivo       TEXT,
    aprobado_por TEXT,
    creado_en    TEXT    DEFAULT (datetime('now')),
    UNIQUE (id_usuario, fecha, hora_inicio)
);
```

### 8.3 Nuevo estado `pendiente_revision`

Ciclo de vida completo de un día:

```
ok → leve → severa → ausente → incompleto → pendiente_revision
```

`pendiente_revision` indica "hay datos pero necesitan interpretación humana".

| Estado de categorización | Tratamiento |
|---|---|
| Sin categorizar | `estado = "pendiente_revision"` — aparece en cola de revisión |
| Categorización parcial | Sigue como `pendiente_revision` |
| Todos categorizados | Analizar cada break según su categoría |

### 8.4 Panel "Días con múltiples breaks" en la UI

> **Commit:** `feat(ui): add multi-break categorization panel and offcanvas to justificaciones view`

```
┌──── Días con múltiples breaks pendientes de revisión ───────────────────┐
│  Fecha    │ Persona       │ Secuencia                      │             │
├───────────┼───────────────┼────────────────────────────────┤             │
│ 10 Mar    │ Ana Torres    │ E 08:00 · S 10:05 · E 12:10 ·  │ [Categorizar│
│           │               │ S 13:05 · E 14:02 · S 17:00    │           ] │
└───────────┴───────────────┴────────────────────────────────┴─────────────┘
```

Al pulsar "Categorizar", offcanvas con los breaks identificados:

```
┌──── Categorizar breaks: Ana Torres — 10 Mar ──────────────────────────────┐
│  Break 1:  Salida 10:05 → Retorno 12:10  (2h 05m)                        │
│  Categoría: [ Permiso temporal ▼ ]  Motivo: [ Cita médica IESS ]          │
│                                                                             │
│  Break 2:  Salida 13:05 → Retorno 14:02  (57m)                           │
│  Categoría: [ Almuerzo ▼ ]  (dentro del límite de 60m configurado)        │
│                                                                             │
│                                  [Guardar categorización]                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.5 Identificación de breaks en la secuencia

Para `[E, S, E, S, E, S]`:
- **Break 1:** Par `S[1] → E[2]`
- **Break 2:** Par `S[3] → E[4]`
- La Salida final `S[5]` no es un break — es la salida del día

### 8.6 Lógica de análisis por categoría

> **Commit:** `feat(script): analyze categorized multi-break days with pendiente_revision state`

| Categoría | Análisis |
|---|---|
| `almuerzo` | Comparar duración contra `almuerzo_min`; aplicar lógica de exceso existente |
| `permiso` | La categorización es la autorización; registrar duración en sección Permisos del PDF |
| `injustificado` | Alerta "Salida sin autorización"; nuevo contador `salidas_injustificadas` |

### 8.7 Rutas API nuevas

```
GET  /api/breaks-pendientes?fecha_inicio=&fecha_fin=
     → Lista días con 6+ marcaciones sin categorización completa

GET  /api/breaks-categorizados?id_usuario=&fecha=
     → Categorización de un día específico

POST /api/breaks-categorizados
     Body: [{ id_usuario, fecha, hora_inicio, hora_fin, categoria, motivo, aprobado_por }, ...]
     → Atómico: inserta/reemplaza todas las categorizaciones de un día

DELETE /api/breaks-categorizados/<id_usuario>/<fecha>
     → Elimina toda la categorización de un día
```

### 8.8 Badge en el dashboard y navegación

El panel principal agrega un indicador para días pendientes de categorización, integrado en la vista de Justificaciones como sub-sección visible al tope.

---

## 9. Extensión — Permiso que incluye almuerzo

> **Commit:** `feat(db,app,script): add incluye_almuerzo support to permiso justifications`

### 9.1 El caso de uso

Empleado con almuerzo de 60 min. Permiso autorizado de 12:00 a 15:00 (3 horas). De esas 3 horas, 1 corresponde al almuerzo habitual. El permiso neto real es de 2 horas.

**Secuencia biométrica:** `[E 08:00, S 12:00, E 15:00, S 17:00]` — secuencia `[E,S,E,S]` estándar.

### 9.2 Nueva columna en `justificaciones`

```python
_migrar_columna(conn, "justificaciones", "incluye_almuerzo", "INTEGER DEFAULT 0")
```

### 9.3 Cómo afecta al análisis

```
permiso_total_min    = hora_retorno_permiso - hora_permitida
almuerzo_min_persona = info["almuerzo_min"]
permiso_neto_min     = permiso_total_min - almuerzo_min_persona

→ Análisis de almuerzo: OMITIDO (incluido en el permiso)
→ Observación: "Permiso 12:00-15:00 (incluye 60min almuerzo) — Permiso neto: 2h"
```

### 9.4 Casos especiales

| Caso | Comportamiento |
|---|---|
| `almuerzo_min = 0` | API advierte; `permiso_neto = permiso_total` |
| `almuerzo_min > permiso_total_min` | API rechaza: "El almuerzo excede la duración del permiso" |
| Retorno tardío | Se analiza contra `hora_retorno_permiso` normalmente |

### 9.5 UI — Checkbox en el offcanvas de justificaciones

```
  Puede salir desde:  [ 12:00 ]
  Debe regresar a:    [ 15:00 ]

  ☑ Incluye almuerzo habitual
    └── El tiempo de almuerzo del empleado (60 min) se descuenta del permiso.
        Permiso neto estimado: 2h 00m  ← calculado en tiempo real con JS
```

Para que el JS calcule `almuerzo_min`, la persona debe estar seleccionada en el TomSelect — el dato viene de `_horariosData` (caché del horario cargado en la vista).

---

## 10. Cambios en el PDF (`script.py`)

> **Commit:** `feat(script): add permisos section and salidas_injustificadas to per-person PDF`

### 10.1 Filtro en reportes

Agregar checkbox en `reportes.html` (activado por defecto):

```html
<input class="form-check-input" type="checkbox" id="f-permisos" checked>
<label ...>Permisos durante jornada</label>
```

Key en `leerFiltros()`: `mostrar_permisos`.

### 10.2 Sección "Permisos durante la jornada"

```
┌─── PERMISOS DURANTE LA JORNADA ────────────────────────────────────────┐
│ Fecha  │ Salida │ Retorno │ Límite ret. │ P.Neto │ Alm.incl. │ Estado  │
├────────┼────────┼─────────┼─────────────┼────────┼───────────┼─────────┤
│ 15 Mar │ 10:05  │ 12:15   │ 12:00       │ 2h     │ —         │ ⚠ +15m  │
│ 22 Mar │ 09:55  │ 11:50   │ 12:00       │ 1h     │ ✓ 60min   │ ✓ OK    │
└────────┴────────┴─────────┴─────────────┴────────┴───────────┴─────────┘
```

Las columnas "P.Neto" y "Alm.incl." solo se muestran si hay algún permiso con `incluye_almuerzo=True`.

### 10.3 Tabla resumen por persona — nueva columna

```
| Persona | Días | Aus. | T.Sev. | T.Lev. | S.Ant. | Permisos | Exc.Alm | Anóm. | Just. |
```

"Permisos" = `retorno_tardio_severo + retorno_tardio_leve + sin_retorno`.

---

## 11. Tabla completa de estados de un día

| Estado | Cuándo ocurre | Aparece en |
|---|---|---|
| `ok` | Sin novedades | Solo si "mostrar todos los días" activo |
| `leve` | Tardanza 1-5m, salida ant. leve | Sección tardanzas leves |
| `severa` | Tardanza >5m, salida ant. severa, retorno tardío | Sección tardanzas severas |
| `ausente` | Sin marcaciones en día laborable | Sección ausencias |
| `libre` | Día libre según horario con marcaciones | Detalle cronológico |
| `feriado` | Día feriado con marcaciones | Solo si "mostrar todos" activo |
| `incompleto` | Secuencia inválida no categorizable | Sección incompletos |
| `pendiente_revision` *(nuevo)* | 6+ marcaciones sin categorización completa | Cola de revisión (UI) + sección pendientes (PDF) |

---

## 12. Casos borde

| Caso | Comportamiento |
|---|---|
| Permiso + Almuerzo el mismo día (6 punches) | No soportado en v1. Usar mecanismo de `breaks_categorizados` (sección 8) |
| Empleado no regresó después del permiso | `[E,S]` + permiso → "PERMISO SIN RETORNO" (estado `severa`) |
| Se fue antes del inicio autorizado | Nota informativa, NO genera alerta de salida anticipada |
| Permiso con estado `pendiente` | Se trata como si no existiera; alerta normal de exceso de almuerzo |
| `hora_retorno_permiso` ausente | La API rechaza: campo requerido para `tipo=permiso` |
| Break `injustificado` categorizado | Nuevo contador `salidas_injustificadas` en `resumen` |
| 8+ marcaciones (3 breaks) | No contemplado. Se trata como `incompleto` |

---

## 13. Esquema completo de cambios en DB (Parte II)

### Tabla `justificaciones` — columnas nuevas

```python
_migrar_columna(conn, "justificaciones", "hora_retorno_permiso", "TEXT")
_migrar_columna(conn, "justificaciones", "incluye_almuerzo",     "INTEGER DEFAULT 0")
```

### Tabla nueva `breaks_categorizados`

```sql
CREATE TABLE IF NOT EXISTS breaks_categorizados (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario   TEXT    NOT NULL,
    fecha        TEXT    NOT NULL,
    hora_inicio  TEXT    NOT NULL,
    hora_fin     TEXT    NOT NULL,
    duracion_min INTEGER,
    categoria    TEXT    NOT NULL CHECK(categoria IN ('almuerzo','permiso','injustificado')),
    motivo       TEXT,
    aprobado_por TEXT,
    creado_en    TEXT    DEFAULT (datetime('now')),
    UNIQUE (id_usuario, fecha, hora_inicio)
);
```

---

## 14. Diferencias conceptuales en el PDF

| Situación | Tipo actual | Tipo correcto tras implementación |
|---|---|---|
| Break de 2h → alarma de exceso | almuerzo | permiso (si está autorizado) |
| Volvió tarde del permiso | — (no existe) | `permiso_retorno_tardio` |
| No volvió después del permiso | — (no existe) | `permiso_sin_retorno` |
| Break de 2h almuerzo justificado | almuerzo justificado | almuerzo justificado (sin cambios) |

---

## 15. Orden de implementación (Parte II)

### Fase 1 — DB
1. `db.py`: Migrar `hora_retorno_permiso` e `incluye_almuerzo` en `justificaciones`
2. `db.py`: Crear tabla `breaks_categorizados` en `init_db()`
3. `db.py`: CRUD: `upsert_breaks_categorizados()`, `get_breaks_categorizados()`, `delete_breaks_dia()`, `get_breaks_pendientes()`

### Fase 2 — API
4. `app.py`: Agregar `hora_retorno_permiso` e `incluye_almuerzo` en `POST /api/justificaciones`
5. `app.py`: Validaciones para `tipo=permiso`
6. `app.py`: Nuevas rutas `GET/POST/DELETE /api/breaks-categorizados` y `GET /api/breaks-pendientes`

### Fase 3 — Lógica de análisis
7. `script.py`: Extender `analizar_por_persona()` para recibir `breaks_categorizados`
8. `script.py`: Detectar días con 6+ marcaciones y secuencia válida alternada → estado `pendiente_revision`
9. `script.py`: Análisis por categoría para días categorizados
10. `script.py`: Análisis de permiso-con-almuerzo (`incluye_almuerzo=True`)
11. `app.py` → `_build_pdf()`: Cargar `breaks_categorizados` y pasarlos al análisis

### Fase 4 — PDF
12. `script.py`: `_seccion_permisos_persona()`
13. `script.py`: `_seccion_salidas_injustificadas_persona()`
14. `script.py`: `_seccion_pendientes_revision_persona()`
15. `script.py`: Actualizar tabla resumen con nuevas columnas

### Fase 5 — UI
16. `justificaciones.html`: Campos `hora_retorno_permiso` e `incluye_almuerzo` en offcanvas
17. `justificaciones.js`: Campos dinámicos, validación frontend, cálculo neto en tiempo real
18. `justificaciones.html`: Panel "Días con múltiples breaks" (cola de revisión)
19. `justificaciones.js`: Cargar cola + offcanvas de categorización
20. `reportes.html`: Checkboxes `f-permisos`, `f-salidas-injustificadas`
21. `reportes.js`: Incluir nuevos filtros en `leerFiltros()`
22. `app.py` → `_DEFAULT_FILTROS`: `mostrar_permisos: True`, `mostrar_salidas_injustificadas: True`

---

## 16. Archivos modificados (Parte II)

| Archivo | Cambio | Riesgo |
|---|---|---|
| `db.py` | Nuevas columnas + nueva tabla + CRUD breaks | Bajo — migración automática, retrocompatible |
| `app.py` | Nuevos campos POST, validación permiso, nuevas rutas, nuevo filtro | Bajo — extensión sin romper lo existente |
| `script.py` | Nuevo bloque análisis permiso, nuevos contadores, nuevas secciones PDF, nuevo estado | Medio — lógica crítica, requiere pruebas |
| `justificaciones.html` | Nuevos campos en offcanvas, nuevo panel cola revisión | Bajo |
| `justificaciones.js` | Campos dinámicos, cálculo neto, categorización breaks | Bajo — extensión lógica existente |
| `reportes.html` | Nuevos checkboxes | Mínimo |
| `reportes.js` | Leer nuevos checkboxes | Mínimo |

---

## 17. Limitaciones conocidas persistentes (fuera de scope)

1. **Secuencias de 8+ marcaciones** (3 breaks) — No contempladas. Se tratan como `incompleto`.
2. **Permiso al inicio o fin de jornada** — Puede confundirse con tardanza o salida anticipada; requiere lógica adicional fuera de scope.
3. **Múltiples permisos independientes en `justificaciones`** — Restricción UNIQUE limita a uno. Para múltiples, usar `breaks_categorizados`.
