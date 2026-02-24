# Plan de Implementación: Horarios Personalizados por Persona

**Archivo de referencia:** `horarios_personal_ingreso.obd`
**Tipo de cambio:** Mejora de lógica de análisis (no rompe funcionalidad existente)
**Estado:** Plan — sin código implementado

---

## 1. Contexto y Problema Actual

El sistema actual aplica umbrales **globales** para todos los empleados:

```python
CONFIG_DEFAULT = {
    "tardanza_leve":    "08:00",   # Igual para TODOS
    "tardanza_severa":  "08:05",   # Igual para TODOS
    "max_almuerzo_min": 60,        # Igual para TODOS
}
```

**Problemas concretos con este enfoque:**
- Un empleado que entra a las 7:00 AM no tiene tardanza si llega a las 8:03, pero uno que debía entrar a las 7:00 sí debería tenerla.
- Empleados de turno de tarde (1:55 PM) siempre aparecen como tardanza severa con las reglas actuales.
- Empleados que no trabajan ciertos días (ej. solo fines de semana) generan falsas alertas de ausencia.
- Algunos empleados no tienen derecho a almuerzo o solo tienen 30 minutos.

**La solución** es cargar el archivo de horarios individuales y aplicar reglas por persona y por día de la semana.

---

## 2. Análisis del Archivo `horarios_personal_ingreso.obd`

### 2.1 Estructura de columnas

| Columna            | Tipo de valor               | Ejemplo             |
|--------------------|-----------------------------|---------------------|
| NOMBRES            | Texto                       | `ABREU UREÑA ELIESER IGNACIO` |
| ID                 | Número entero               | `5` (ID en dispositivo ZK) |
| LUNES (HORA ENTRADA) | Hora o `NO`              | `7:00:00 AM` / `NO` |
| MARTES (HORA ENTRADA) | Hora o `NO`             | `7:00:00 AM` / `NO` |
| MIERCOLES (HORA ENTRADA) | Hora o `NO`         | `7:00:00 AM` / `NO` |
| JUEVES (HORA ENTRADA) | Hora o `NO`              | `7:00:00 AM` / `NO` |
| VIERNES (HORA ENTRADA) | Hora o `NO`             | `7:00:00 AM` / `NO` |
| FIN DE SEMANA (HORA ENTRADA) | Hora o `NO`    | `6:50:00 AM` / `NO` |
| ALMUERZO (TIENE)   | `TRUE` / `FALSE` / `"30 min"` | `TRUE` |
| NOTAS              | Texto libre (opcional)      | (vacío o comentario) |

### 2.2 Reglas de negocio confirmadas por el usuario

| Condición | Significado | Acción en el sistema |
|-----------|-------------|----------------------|
| Día = `NO` | No trabaja ese día | No generar alerta de tardanza ni ausencia ese día |
| FIN DE SEMANA = hora | Solo cuenta el **sábado** | El domingo no genera alertas aunque haya marcaciones |
| FIN DE SEMANA = `NO` | No trabaja sábado | Sin alertas sábado |
| ALMUERZO = `TRUE` | Tiene 60 minutos de almuerzo | Analizar exceso sobre 60 min (solo L-V) |
| ALMUERZO = `FALSE` | No tiene almuerzo | No analizar almuerzo (no debería salir a almorzar) |
| ALMUERZO = `"30 min"` | Tiene 30 minutos de almuerzo | Analizar exceso sobre 30 min (solo L-V) |
| Sábado (siempre) | Sin importar ALMUERZO | **Nunca** analizar almuerzo el sábado |
| Domingo | No es día laboral actualmente | Readable, sin alertas |

### 2.3 Patrones de horarios encontrados en el archivo

- **Turno estándar 7:00 AM** — Mayoría de empleados
- **Turno estándar 7:55 / 8:00 / 8:30 / 9:00 AM** — Personal administrativo
- **Turno tarde 1:55 PM** — Guardia de seguridad u otros turnos (varias personas)
- **Solo fin de semana** — Algunos empleados (L-V = `NO`, FDS = hora específica)
- **Solo L-V** — La mayoría (FDS = `NO`)
- **Los 6 días** — Algunas personas trabajan L-V + Sábado
- **ID del dispositivo ZK** — El campo `ID` en el ODS coincide con `id_usuario` en la tabla `asistencias`

---

## 3. Impacto en el Sistema Actual

### 3.1 Archivos afectados

| Archivo | Tipo de cambio | Impacto |
|---------|----------------|---------|
| `db.py` | Agregar tabla `horarios_personal` + funciones CRUD | Medio |
| `script.py` | Modificar `analizar_dia()` y `analizar_por_persona()` | Alto |
| `app.py` | Agregar rutas `/cargar-horarios`, `/horarios` | Bajo |
| `templates/index.html` | Agregar sección de carga de horarios | Bajo |
| `requirements.txt` | Agregar `odfpy` | Trivial |
| **`horarios.py`** | **Nuevo módulo** (parser ODS + lógica de horarios) | Alto |

### 3.2 Lo que NO cambia

- La tabla `asistencias` (sin modificaciones)
- La tabla `usuarios_zk` (sin modificaciones)
- El flujo de sincronización ZK (`sync.py` — sin cambios)
- Las rutas existentes de Flask
- La generación de PDF por modo general (sin cambios)
- El comportamiento cuando no hay horarios cargados (modo de compatibilidad hacia atrás)

---

## 4. Diseño de la Solución

### 4.1 Nuevo módulo: `horarios.py`

Responsabilidades:
1. Parsear el archivo `.obd` (que es un `.ods` renombrado) usando `odfpy`
2. Normalizar los valores de hora y almuerzo
3. Proporcionar funciones de consulta al resto del sistema

**Función principal: `parsear_obd(ruta) → list[dict]`**

Proceso de parsing:
1. Abrir el archivo con `odf.opendocument.load(ruta)`
2. Iterar filas de la primera hoja
3. Para cada fila (saltando encabezados):
   - Extraer los 9 campos
   - Normalizar horas: `"7:00:00 AM"` → `"07:00"`, `"NO"` → `None`
   - Normalizar almuerzo: `"TRUE"` → `60`, `"FALSE"` → `0`, `"30 min"` → `30`
   - Construir dict con todos los campos

**Normalización de horas:**
```
"7:00:00 AM"  → "07:00"
"1:55:00 PM"  → "13:55"
"NO"          → None  (no trabaja ese día)
""  / vacío   → None
```

**Normalización de almuerzo:**
```
"TRUE"    → 60
"FALSE"   → 0
"30 min"  → 30
cualquier número → int(valor)
```

**Función de consulta: `get_horario_persona(id_usuario, dia_semana) → dict | None`**

Donde `dia_semana` es un entero Python (0=lunes, 5=sábado, 6=domingo).

Retorna:
```python
{
    "hora_entrada": "07:00",  # o None si no trabaja
    "almuerzo_min": 60,       # 0 = sin almuerzo
    "trabaja": True           # False si hora_entrada es None
}
```

**Función de utilidad: `get_todos_los_horarios() → dict[str, dict]`**

Retorna un dict indexado por `id_usuario` con todos los horarios cargados.
Útil para pasar a las funciones de análisis.

### 4.2 Cambios en `db.py`: nueva tabla

**Nueva tabla `horarios_personal`:**

```sql
CREATE TABLE IF NOT EXISTS horarios_personal (
    id_usuario   TEXT    PRIMARY KEY,
    nombre       TEXT    NOT NULL,
    lunes        TEXT,           -- HH:MM o NULL
    martes       TEXT,
    miercoles    TEXT,
    jueves       TEXT,
    viernes      TEXT,
    sabado       TEXT,
    domingo      TEXT,           -- futuro, por ahora siempre NULL
    almuerzo_min INTEGER DEFAULT 0,
    notas        TEXT,
    fuente       TEXT,           -- nombre del archivo ODS cargado
    actualizado_en TEXT DEFAULT (datetime('now'))
);
```

**Funciones nuevas en `db.py`:**

- `upsert_horarios(horarios: list[dict])` — Inserta o reemplaza todos los horarios del lote
- `get_horarios() → dict[str, dict]` — Retorna todos los horarios indexados por `id_usuario`
- `get_estado_horarios() → dict` — Cuántos horarios hay cargados, fuente y fecha de carga

### 4.3 Cambios en `script.py`

Esta es la parte de mayor impacto. Los cambios deben ser **compatibles hacia atrás** para que el sistema funcione aunque no se hayan cargado horarios.

#### 4.3.1 Cambio en `analizar_por_persona()`

La función actual recibe `config: dict` con valores globales. Se le agrega un parámetro opcional `horarios: dict = None`.

**Lógica con horarios cargados:**

Para cada persona, para cada día:

```
1. Obtener el día de la semana de la fecha (Python: fecha.weekday())
   0=lunes, 1=martes, ..., 5=sábado, 6=domingo

2. Si hay horarios cargados para esta persona (por id_usuario):
   a. Mapear weekday → columna del horario:
      0 → "lunes", 1 → "martes", ..., 5 → "sabado", 6 → "domingo"
   b. Obtener hora_entrada programada y almuerzo_min
   c. Si hora_entrada = None → persona no trabaja ese día:
      - Si hay marcaciones igual (puede haberse equivocado): registrar como "marcación en día libre"
      - Si no hay marcaciones: ignorar el día completamente (no es ausencia)
   d. Si es domingo: no generar alertas independientemente del horario

3. Si NO hay horarios cargados → usar config global (comportamiento actual)
```

**Nueva clasificación de tardanza con horarios:**

| Condición | Resultado |
|-----------|-----------|
| `llegada <= hora_programada` | Sin tardanza |
| `hora_programada < llegada <= hora_programada + 5 min` | Tardanza leve |
| `llegada > hora_programada + 5 min` | Tardanza severa |

El umbral de 5 minutos de gracia es configurable (puede mantenerse del config actual).

**Nueva lógica de almuerzo con horarios:**

| `almuerzo_min` | Día | Acción |
|----------------|-----|--------|
| `0` | cualquiera | No analizar almuerzo |
| `30` | L-V | Alertar si excede 30 min |
| `60` | L-V | Alertar si excede 60 min |
| cualquiera | Sábado | **No analizar** (regla fija) |
| cualquiera | Domingo | No analizar |

#### 4.3.2 Cambio en `analizar_dia()`

Esta función analiza un día por todos los empleados. Se le agrega `horarios: dict = None`.

Cambios:
- Para cada persona en ese día, consultar su horario para ese día de la semana
- Si `hora_entrada = None` → saltar análisis de tardanza para esa persona
- Usar `almuerzo_min` individual en lugar del `max_almuerzo_min` global
- Si es sábado → no analizar almuerzo para nadie

**Compatibilidad hacia atrás:** Si `horarios=None` o la persona no está en los horarios, usar la configuración global actual (sin cambio de comportamiento).

#### 4.3.3 Mapeo de id_usuario para el análisis

El problema: `analizar_por_persona()` agrupa por `nombre`, pero los horarios están indexados por `id_usuario`. La tabla `asistencias` tiene ambos campos (`id_usuario` y `nombre`). Sin embargo, `consultar_asistencias()` en `db.py` actualmente **no retorna `id_usuario`**.

**Solución:** Modificar `consultar_asistencias()` para incluir `id_usuario` en el resultado. Esto permite cruzar los registros con el horario por ID (más confiable que cruzar por nombre, que puede tener variaciones).

### 4.4 Cambios en `app.py`

**Nueva ruta: `POST /cargar-horarios`**
- Acepta upload de archivo `.obd` o `.ods`
- Llama a `horarios.parsear_obd(ruta_tmp)`
- Valida que los IDs existan en `usuarios_zk` (advertencia, no error)
- Llama a `db.upsert_horarios(lista)`
- Retorna JSON con: cuántos horarios se cargaron, cuántos IDs no se encontraron en ZK

**Nueva ruta: `GET /horarios`**
- Retorna JSON con todos los horarios cargados y su estado
- Incluye: total de personas, fecha de carga, fuente (nombre del archivo)

**Nueva ruta: `GET /estado-horarios`**
- Versión ligera para mostrar en la UI: ¿hay horarios cargados? ¿cuántos? ¿fecha?

**Modificación en `POST /generar-desde-db` y `POST /generar`:**
- Cargar horarios desde la DB antes del análisis: `horarios_dict = db.get_horarios()`
- Pasarlos a las funciones de `script.py`: `analizar_por_persona(registros, config, horarios=horarios_dict)`

### 4.5 Cambios en `templates/index.html`

Agregar una nueva sección (tarjeta/card) visible en ambos tabs o en una nueva sección fija:

**Card "Horarios Personalizados":**
```
┌─────────────────────────────────────────────────┐
│ 📋 Horarios Personalizados                       │
│                                                  │
│ Estado: ● Cargados (62 personas) — 2026-02-20   │
│ Fuente: horarios_personal_ingreso.obd            │
│                                                  │
│ [Actualizar archivo de horarios]                 │
│  (drag & drop o seleccionar .obd/.ods)           │
│                                                  │
│ [Ver horarios cargados ▼]                        │
└─────────────────────────────────────────────────┘
```

- Indicador de estado: verde si hay horarios, gris si no
- Al generar PDF, si no hay horarios cargados: mostrar advertencia ("Se usarán umbrales globales")
- Al cargar nuevos horarios: confirmar cuántos se procesaron y si hubo IDs desconocidos

### 4.6 Cambios en `requirements.txt`

```
odfpy        # Lectura de archivos .ods/.obd (OpenDocument Spreadsheet)
```

---

## 5. Nueva Lógica de Análisis Completa

### 5.1 Mapeo de weekday a columna de horario

```
fecha.weekday()  →  columna en DB
0 (lunes)        →  lunes
1 (martes)       →  martes
2 (miércoles)    →  miercoles
3 (jueves)       →  jueves
4 (viernes)      →  viernes
5 (sábado)       →  sabado
6 (domingo)      →  domingo  (NULL, no genera alertas)
```

### 5.2 Algoritmo de evaluación por día/persona

```
Para cada (persona, fecha) en el análisis:

  1. Obtener weekday = fecha.weekday()

  2. Si weekday == 6 (domingo):
     → Ignorar: no hay alertas de tardanza ni ausencia
     → Si hay marcaciones, mostrarlas informalmente en el reporte

  3. Buscar horario de la persona por id_usuario:
     Si no se encuentran horarios O la persona no está en el archivo:
     → Usar umbrales globales del config (compatibilidad hacia atrás)

  4. Obtener hora_entrada = horario[dia_de_la_semana]
     Si hora_entrada == None:
     → Persona no trabaja ese día
     → Si hay marcaciones: registrar como "marcación en día libre"
     → Si no hay marcaciones: día ignorado (NO es ausencia)

  5. Si hay marcaciones Y hora_entrada != None:
     a. primera_entrada = primera marcación de tipo "Entrada"
     b. Si primera_entrada existe:
        retraso = primera_entrada.hora - hora_entrada (en minutos)
        Si retraso <= 0: Sin tardanza
        Si 0 < retraso <= 5: Tardanza leve
        Si retraso > 5: Tardanza severa
     c. Si NO existe primera_entrada pero sí hay marcaciones:
        Estado = "Incompleto" (solo hay Salidas)

  6. Análisis de almuerzo (si weekday != 5 y weekday != 6):
     almuerzo_min = horario.almuerzo_min
     Si almuerzo_min == 0: No analizar almuerzo
     Si almuerzo_min > 0:
        Buscar patrón Entrada→Salida→Entrada en las marcaciones
        Si se encontró: calcular duración del intervalo
        Si duración > almuerzo_min: alerta de exceso de almuerzo
```

### 5.3 Casos especiales documentados

| Caso | Comportamiento |
|------|----------------|
| Persona en ODS pero no en ZK | Advertencia al cargar horarios; no afecta el análisis |
| Persona en ZK pero no en ODS | Usar umbrales globales del config |
| Marcaciones sin horario configurado | Usar umbrales globales |
| ID en ODS no coincide con ningún ID en ZK | Warning en la UI al cargar |
| Nombre distinto entre ODS y ZK | No importa: el cruce es por `id_usuario`, no por nombre |
| `punch` distinto de 0 o 1 (ej. 4, 15) | Ya filtrado en `sync.py` como `None` |
| Persona que trabaja solo FDS y tiene registro en L-V | Marcación en día libre |
| Turno tarde (ej. 13:55) que entra 14:05 | Tardanza severa (+10 min sobre 13:55) |

---

## 6. Flujo Completo con Horarios (Caso de Uso)

```
Usuario administrador:
  1. Carga el archivo horarios_personal_ingreso.obd via UI
  2. Sistema parsea el ODS, normaliza los datos, los guarda en horarios_personal
  3. UI confirma: "62 horarios cargados. 0 IDs sin coincidencia en ZK."

Sistema:
  4. Al siguiente sync ZK, los registros incluyen id_usuario
  5. db.consultar_asistencias() retorna registros con id_usuario incluido

Generación de PDF:
  6. app.py carga horarios_dict = db.get_horarios()
  7. Pasa horarios_dict a analizar_por_persona()
  8. Para cada persona: aplica horario individual por día
  9. PDF muestra "Hora programada: 07:00 | Hora llegada: 07:23 → Tardanza leve (+23 min)"
```

---

## 7. Consideraciones de Diseño

### 7.1 Identificación de personas: ID vs Nombre

**Usar siempre `id_usuario` para cruzar horarios**, no el nombre. Razones:
- El nombre en el dispositivo ZK puede tener variaciones de formato
- El nombre en el ODS puede tener tildes o mayúsculas distintas
- El `id_usuario` es una clave numérica única sin ambigüedad

### 7.2 Compatibilidad hacia atrás

Si no hay horarios cargados en la DB:
- El sistema funciona exactamente igual que antes
- Se usan los umbrales globales de `config`
- No hay cambios visibles en los PDFs generados

Si se cargan horarios:
- Solo afecta personas que tienen ID en el archivo ODS
- Personas sin horario → siguen con reglas globales

### 7.3 Actualizaciones de horarios

El sistema debe soportar que el archivo ODS se actualice (cambios de horario, nuevas personas):
- La operación `upsert_horarios()` reemplaza los registros existentes por `id_usuario`
- El campo `fuente` y `actualizado_en` permiten auditar cuándo fue la última actualización
- No hay versionado (la última carga siempre reemplaza la anterior)

### 7.4 Tolerancia en tiempos del ODS

El archivo ODS almacena las horas como objetos `datetime.time` internamente (tipo ODS `time`). El parser debe manejar:
- Horas como string en formato AM/PM: `"7:00:00 AM"` → `time(7, 0)`
- Horas que podrían venir como timedelta (diferencia desde medianoche en ODS)
- Valores `None` o celdas vacías → tratar como `NO`

---

## 8. Fases de Implementación

### Fase 1 — Infraestructura (sin impacto en producción)
1. Agregar `odfpy` a `requirements.txt`
2. Crear nuevo módulo `horarios.py` con función `parsear_obd()`
3. Agregar tabla `horarios_personal` en `db.py` (en `init_db()`)
4. Agregar funciones `upsert_horarios()` y `get_horarios()` en `db.py`
5. Modificar `consultar_asistencias()` para incluir `id_usuario` en el resultado

### Fase 2 — Lógica de análisis
6. Modificar `analizar_por_persona()` en `script.py` para aceptar `horarios=None`
7. Modificar `analizar_dia()` en `script.py` para aceptar `horarios=None`
8. Implementar nueva lógica de tardanza relativa a horario individual
9. Implementar nueva lógica de almuerzo con `almuerzo_min` por persona
10. Garantizar compatibilidad hacia atrás (sin horarios = comportamiento actual)

### Fase 3 — API y UI
11. Agregar ruta `POST /cargar-horarios` en `app.py`
12. Agregar ruta `GET /horarios` y `GET /estado-horarios` en `app.py`
13. Modificar `POST /generar-desde-db` y `POST /generar` para pasar horarios al análisis
14. Agregar card de "Horarios Personalizados" en `templates/index.html`
15. Agregar lógica JS para carga de horarios y mostrar estado

### Fase 4 — PDF actualizado
16. Actualizar sección de encabezado de persona en el PDF para mostrar "Horario: L 7:00 | M 7:00 | ..."
17. Columna de observaciones en el reporte por persona: mostrar "Hora programada: 07:00"
18. En reporte general: reflejar que las tardanzas son relativas a horario individual

---

## 9. Dependencia nueva en Docker

```dockerfile
# En Dockerfile — agregar odfpy al build
# requirements.txt ya incluye odfpy, no necesita cambio en el Dockerfile
```

El archivo `.obd` del usuario es de ~68KB. El parsing en memoria es trivial; no hay necesidad de optimización.

El archivo de horarios se sube **una vez** y persiste en la DB. No necesita estar disponible en el volumen Docker (aunque sería útil un backup).

---

## 10. Resumen de Archivos a Crear/Modificar

| Archivo | Acción | Descripción del cambio |
|---------|--------|------------------------|
| `horarios.py` | **Crear** | Parser ODS + funciones de consulta |
| `db.py` | Modificar | Nueva tabla `horarios_personal`, nuevas funciones, agregar `id_usuario` en `consultar_asistencias` |
| `script.py` | Modificar | `analizar_por_persona()` y `analizar_dia()` con horarios opcionales |
| `app.py` | Modificar | 3 nuevas rutas, pasar horarios al análisis |
| `templates/index.html` | Modificar | Card de horarios con upload + estado |
| `requirements.txt` | Modificar | Agregar `odfpy` |
| `README.md` | Modificar | Documentar el archivo de horarios y su uso |
