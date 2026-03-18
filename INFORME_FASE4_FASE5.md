# Informe de Implementación — Fase 4 y Fase 5
**Fase 4:** Gestión de Personas, Grupos y Períodos
**Fase 5:** Analytics e IA
**Versión:** 2.0
**Fecha:** 2026-03-17
**Estado Fase 4:** ✅ Completo al 100%
**Estado Fase 5:** ✅ Completo al 100%

---

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Bugs corregidos en esta validación](#2-bugs-corregidos-en-esta-validación)
3. [Fase 4 — Gestión de Personas, Grupos y Períodos](#fase-4--gestión-de-personas-grupos-y-períodos)
   - [3. Qué cambió respecto al plan original](#3-qué-cambió-respecto-al-plan-original)
   - [4. Modelo de datos implementado](#4-modelo-de-datos-implementado)
   - [5. Personas](#5-personas)
   - [6. Períodos de vigencia](#6-períodos-de-vigencia)
   - [7. Cálculo de asistencia por período](#7-cálculo-de-asistencia-por-período)
   - [8. Import CSV de personas](#8-import-csv-de-personas)
   - [9. Sincronización ZK — resolución automática de período](#9-sincronización-zk--resolución-automática-de-período)
   - [10. Rutas API — Fase 4](#10-rutas-api--fase-4)
   - [11. Cómo usar — Fase 4](#11-cómo-usar--fase-4)
4. [Fase 5 — Analytics e IA](#fase-5--analytics-e-ia)
   - [12. Qué implementa la Fase 5](#12-qué-implementa-la-fase-5)
   - [13. Motor de Analytics (`analytics.py`)](#13-motor-de-analytics-analyticspy)
   - [14. Reporte narrativo con IA (`ia_report.py`)](#14-reporte-narrativo-con-ia-ia_reportpy)
   - [15. Rutas API — Fase 5](#15-rutas-api--fase-5)
   - [16. Configuración de DeepSeek](#16-configuración-de-deepseek)
   - [17. Cómo usar — Fase 5](#17-cómo-usar--fase-5)
5. [Estado de implementación consolidado](#18-estado-de-implementación-consolidado)
6. [Funcionalidades pendientes](#19-funcionalidades-pendientes)
7. [Archivos modificados y creados](#20-archivos-modificados-y-creados)

---

## 1. Resumen ejecutivo

### Fase 4
Implementa la capa de negocio sobre el modelo de datos horizontal establecido en Fase 1. Cualquier tipo de persona (Empleado, Practicante, Contratista, Voluntario) comparte el mismo modelo: la tabla `personas` + `periodos_vigencia` + `asignaciones_horario`. Los reportes y cálculos se adaptan automáticamente según si el período tiene fecha fin o no.

**Resultado:** Un gestor puede crear períodos de prácticas, cargar personas por CSV, y ver la tabla de asistencia en tiempo real con semáforos de cumplimiento.

### Fase 5
Implementa analytics estadístico unificado con riesgo individual (Risk Score 0-100), detección de anomalías por desviación estándar, y generación de reportes narrativos usando la API de DeepSeek con fallback automático a texto basado en reglas.

**Resultado:** Un admin o gestor puede consultar `/analytics` y obtener en una sola pantalla: tasa de asistencia del período, top 10 personas en riesgo, anomalías estadísticas, y un párrafo narrativo generado por IA.

---

## 2. Bugs corregidos en esta validación

| # | Severidad | Archivo | Línea | Descripción | Fix aplicado |
|---|---|---|---|---|---|
| 1 | CRÍTICO | `app.py` | 1863 | `cerrar_periodo()` llamada con 3 argumentos (`nombre`, `fecha_inicio`, `fecha_fin`) cuando la función solo acepta `id: str`. Causaba `TypeError` al cerrar períodos desde la UI. | Cambiado a `db_module.cerrar_periodo(id)` |
| 2 | ALTO | `requirements.txt` | — | `requests` importado en `ia_report.py` pero no declarado en requirements. Causaría `ModuleNotFoundError` en instalación limpia. | Agregado `requests>=2.31` |
| 3 | MENOR | `.env.example` | — | `DEEPSEEK_API_KEY` no documentada. | Agregada con comentario explicativo |

---

# FASE 4 — Gestión de Personas, Grupos y Períodos

## 3. Qué cambió respecto al plan original

La Fase 4 original implementaba un "Módulo de Alumnos" con tablas separadas, flag `modulo_alumnos`, y routing condicional en sync. En la v2 esto desaparece completamente:

| Fase 4 v1 | Fase 4 v2 implementada |
|---|---|
| Tabla `alumnos` separada | `personas` con `tipo_persona_id` |
| Tabla `asistencias_alumnos` | `asistencias` unificada (todo en una tabla) |
| Tabla `periodos_practicas` | `periodos_vigencia` (universal) |
| Tabla `matriculas_periodo` | `periodos_vigencia.persona_id` (relación directa) |
| `db/queries/alumnos.py` | `db/queries/personas.py` + `db/queries/periodos.py` |
| Routing en sync: si `dispositivo.modulo == 'alumnos'` | No existe. Routing vía `personas_dispositivos` |
| Reporte "aprobados/reprobados" | Reporte de cumplimiento porcentual genérico |

**No existe ninguna referencia a `modulo_alumnos`, `asistencias_alumnos`, `periodos_practicas` ni `matriculas_periodo` en el código.**

---

## 4. Modelo de datos implementado

### 4.1 Diagrama de relaciones (Fase 4)

```
personas
│  id, nombre, identificacion, tipo_persona_id, grupo_id, categoria_id
│
├── tipos_persona (Empleado, Practicante, Contratista...)
├── grupos (Contabilidad, Redes, Administración...)
├── categorias (Primer Nivel, Cargo Senior...)
│
├── periodos_vigencia
│   │  id, persona_id, nombre, fecha_inicio, fecha_fin, estado
│   │  estado: 'activo' | 'cerrado' | 'archivado'
│   │  fecha_fin = NULL → período indefinido (empleado fijo)
│   │  fecha_fin = fecha → período acotado (practicante, contratista)
│   │
│   └── asistencias.periodo_vigencia_id (FK, se rellena automáticamente al hacer sync)
│
├── asignaciones_horario
│   │  persona_id, plantilla_horario_id, fecha_inicio_asignacion
│   └── plantillas_horario (lunes_entrada, lunes_salida, ... viernes_salida)
│
└── personas_dispositivos
       persona_id, dispositivo_id, id_en_dispositivo
       (vincula persona con su ID en el reloj ZK)
```

### 4.2 Ciclo de vida de un período

```
ACTIVO ─────────────────────→ CERRADO ──────────────→ ARCHIVADO
   │                               │                       │
   │ Cierre manual o automático    │ Solo lectura           │ Solo lectura
   │ al pasar fecha_fin            │ Generar PDF final      │ No aparece en lista
   │                               │                       │   principal
   └── Agregar personas            └── Archivar manual
       Ver asistencia en tiempo real
       Cerrar manualmente
```

**Transición automática activo → cerrado:** el scheduler nocturno ejecuta `cerrar_periodos_vencidos()` que cierra todos los períodos donde `NOW() > fecha_fin`.

---

## 5. Personas

### 5.1 Módulo `db/queries/personas.py`

| Función | Descripción |
|---|---|
| `resolver_persona_id(id_dispositivo, dispositivo_id)` | Dada una marcación del ZK, retorna el UUID de la persona. Si no existe, la crea automáticamente con datos mínimos. |
| `_crear_persona_desde_zk(id_usuario, nombre_zk)` | Crea persona con datos del dispositivo. Vincula vía `personas_dispositivos`. |
| `id_usuario_from_persona(persona_id)` | Inverso: dado UUID de persona, retorna su ID en el ZK. |
| `upsert_usuarios(usuarios_zk)` | Actualización masiva desde lista del ZK. Vincula todos los usuarios con sus personas. |
| `get_ids_usuarios_zk()` | Retorna el set de IDs de usuarios actualmente registrados en el ZK. |

### 5.2 Cómo se vincula una persona con el dispositivo ZK

Cuando se hace sync y el ZK reporta una marcación de `id_usuario = "00042"`:
1. `resolver_persona_id("00042", dispositivo_id)` busca en `personas_dispositivos`
2. Si encuentra: retorna el `persona_id` del registro
3. Si no encuentra: crea la persona con `nombre = "Usuario 00042"` (editable después) y la vincula
4. La asistencia se inserta con ese `persona_id`

Después, en la UI, el gestor puede editar el nombre y asignar grupo/categoría.

---

## 6. Períodos de vigencia

### 6.1 Módulo `db/queries/periodos.py`

| Función | Descripción |
|---|---|
| `crear_periodo(persona_id, nombre, fecha_inicio, fecha_fin, descripcion)` | Crea un `periodo_vigencia` para una persona. Si `fecha_fin=None`, es indefinido. |
| `get_periodo(id)` | Retorna un período por UUID. |
| `listar_periodos_activos(tipo_persona_id=None)` | Lista períodos activos agrupados por nombre+fechas, con conteo de personas. |
| `listar_periodos_historial(tipo_persona_id=None)` | Lista períodos cerrados y archivados. |
| `agregar_personas_a_periodo_bulk(periodo_id, personas)` | Agrega múltiples personas a un período existente. |
| `cerrar_periodo(id)` | Cambia estado a `'cerrado'`. Desde ese momento es de solo lectura. |
| `archivar_periodo(id)` | Cambia estado a `'archivado'`. Desaparece de la lista principal. |
| `cerrar_periodos_vencidos()` | Cierra todos los períodos activos donde `fecha_fin < NOW()`. Llamado por el scheduler. |
| `procesar_csv_personas_periodo(archivo, periodo_id, tipo_persona_id)` | Import masivo desde CSV. Ver sección 8. |

### 6.2 Diferencia: período indefinido vs acotado

| Tipo | `fecha_fin` | Reporte generado | Análisis |
|---|---|---|---|
| Empleado fijo | `NULL` | Tardanzas, ausencias, comportamiento continuo | Motor `script.py` |
| Practicante / Contratista | `fecha específica` | % de cumplimiento, semáforo presencia | Motor `calcular_asistencia_periodo()` |

Todos usan las mismas tablas — la diferenciación es por `fecha_fin`.

---

## 7. Cálculo de asistencia por período

### 7.1 Función `calcular_asistencia_periodo(periodo_id)` — `db/queries/asistencia_periodo.py`

Esta es la función central de la Fase 4. Para un período dado:

1. Obtiene todas las personas que comparten ese nombre y fechas de período
2. Para cada persona, itera día a día en el rango `[fecha_inicio, fecha_fin]`
3. Por cada día determina:
   - ¿Es feriado? → `estado = 'feriado'` (excluido del denominador)
   - ¿Tiene horario ese día de semana? → Si no, `estado = 'no_programado'`
   - ¿Hay marcación en `asistencias`? → `presente` o `presente_tarde`
   - Sin marcación en día programado → `ausente`
4. Calcula `% asistencia = presentes / días_programados_sin_feriados × 100`
5. Asigna semáforo:
   - Verde: ≥ 90%
   - Amarillo: 75% – 89%
   - Rojo: < 75%

### 7.2 Estructura del resultado

```python
[
    {
        "persona_id": "uuid...",
        "nombre": "Juan Pérez",
        "identificacion": "1234567890",
        "grupo": "Contabilidad",
        "categoria": "Segundo Nivel",
        "detalle_asistencia": [
            {"fecha": "2026-04-01", "estado": "presente", "tardanza": False, "entrada_marcada": "07:02"},
            {"fecha": "2026-04-02", "estado": "ausente",  "tardanza": False, "entrada_marcada": None},
            {"fecha": "2026-04-03", "estado": "feriado",  "tardanza": False, "entrada_marcada": None},
        ],
        "total_dias_programados": 12,
        "dias_presentes": 10,
        "porcentaje_asistencia": 83.3,
        "color": "Amarillo"   # semáforo
    },
    ...
]
```

---

## 8. Import CSV de personas

### 8.1 Función `procesar_csv_personas_periodo(archivo, periodo_id, tipo_persona_id)`

Flujo de procesamiento de cada fila del CSV:

```
1. Leer identificacion, nombre, grupo, categoria
2. ¿Existe persona con esa identificacion?
     Sí → usar id existente
     No → crear nueva persona con tipo_persona_id indicado
3. ¿Existe el grupo?
     Sí → usar id existente (búsqueda insensible a mayúsculas)
     No → crear nuevo grupo (tipo_grupo='carrera')
4. ¿Existe la categoria?
     Sí → usar id existente
     No → crear nueva categoria vinculada al tipo_persona_id
5. Actualizar persona: grupo_id, categoria_id
6. Crear periodo_vigencia para la persona (con mismo nombre y fechas que el período)
7. Si el CSV tiene columnas de horario:
     crear plantilla_horario + asignacion_horario
8. Si la persona tiene id en personas_dispositivos → mantener vinculación
```

### 8.2 Formato del CSV

El archivo debe tener las siguientes columnas (el orden no importa, se usan los nombres de encabezado):

```
identificacion  nombre   grupo            categoria
1234567890      Juan P.  Contabilidad     Segundo Nivel
0987654321      Ana M.   Redes y Teleco.  Primer Nivel
```

Columnas opcionales de horario (si se incluyen, se crea la asignación):
```
lunes_entrada   lunes_salida  martes_entrada  martes_salida  ...  viernes_salida
07:00           12:00         07:00           12:00          ...  12:00
```

### 8.3 Resultado del procesamiento

La función retorna un dict con el resumen:
```python
{
    "procesadas": 10,
    "nuevas": 5,
    "actualizadas": 4,
    "errores": 1,
    "detalle_errores": ["Fila 7: identificacion vacía"]
}
```

---

## 9. Sincronización ZK — resolución automática de período

Desde Fase 4, al insertar cada marcación durante el sync, `insertar_asistencias()` resuelve automáticamente a qué período pertenece:

```python
# db/queries/asistencias.py — dentro de insertar_asistencias()
SELECT id FROM periodos_vigencia
WHERE persona_id = :persona_id
  AND estado = 'activo'
  AND fecha_inicio <= :fecha
  AND (fecha_fin IS NULL OR fecha_fin >= :fecha)
LIMIT 1
```

- Si encuentra período activo → `asistencias.periodo_vigencia_id = periodo_id`
- Si no encuentra → `asistencias.periodo_vigencia_id = NULL` (la marcación igual se guarda)

Esto es **transparente para sync.py** — ningún cambio fue necesario en el conector ZK.

---

## 10. Rutas API — Fase 4

| Método | Ruta | Roles | Descripción |
|---|---|---|---|
| `GET` | `/periodos` | `gestor`, `admin`, `superadmin` | Lista períodos activos e historial |
| `POST` | `/periodos/crear` | `admin`, `superadmin` | Crear nuevo período |
| `GET` | `/periodos/<id>` | `gestor`, `admin`, `superadmin` | Detalle + asistencia en tiempo real |
| `POST` | `/periodos/<id>/importar-personas` | `admin`, `superadmin` | Cargar CSV de personas al período |
| `POST` | `/periodos/<id>/cerrar` | `admin`, `superadmin` | Cerrar período manualmente |
| `POST` | `/periodos/<id>/archivar` | `admin`, `superadmin` | Archivar período cerrado |
| `GET` | `/personas` | `gestor`, `admin`, `superadmin` | Lista personas con filtros (tipo, grupo, búsqueda) |
| `POST` | `/personas/crear` | `admin`, `superadmin` | Crear persona manualmente |
| `POST` | `/personas/<id>` | `admin`, `superadmin` | Editar persona (nombre, identificación, grupo, etc.) |
| `GET` | `/personas/historico` | `gestor`, `admin`, `superadmin` | Historial de períodos por identificación |
| `GET` | `/admin/grupos` | `admin`, `superadmin` | Lista y gestión de grupos |
| `POST` | `/admin/grupos` | `admin`, `superadmin` | Crear nuevo grupo |
| `POST` | `/admin/grupos/<id>` | `admin`, `superadmin` | Editar grupo (nombre, tipo, estado) |
| `GET` | `/admin/categorias` | `admin`, `superadmin` | Lista y gestión de categorías |
| `POST` | `/admin/categorias` | `admin`, `superadmin` | Crear nueva categoría |
| `POST` | `/admin/categorias/<id>` | `admin`, `superadmin` | Editar categoría (nombre, estado) |

### Parámetros de `POST /periodos/crear`

| Campo | Tipo | Req. | Descripción |
|---|---|---|---|
| `nombre` | string | Sí | Nombre del período (ej: "Prácticas Abril A 2026") |
| `fecha_inicio` | `YYYY-MM-DD` | Sí | Inicio del período |
| `fecha_fin` | `YYYY-MM-DD` | No | Fin. Sin este campo → período indefinido |
| `descripcion` | string | No | Nota opcional |

### Parámetros de `POST /periodos/<id>/importar-personas`

| Campo | Tipo | Req. | Descripción |
|---|---|---|---|
| `archivo` | file (CSV) | Sí | Archivo CSV con las personas |
| `tipo_persona_id` | UUID | Sí | Tipo de persona a asignar a las nuevas |

---

## 11. Cómo usar — Fase 4

### 11.1 Crear un período de prácticas

1. Ir a **`/periodos`**
2. Clic en **"Nuevo Período"**
3. Completar:
   - Nombre: `"Prácticas Abril A 2026"`
   - Fecha inicio: `2026-04-01`
   - Fecha fin: `2026-04-15`
4. Guardar → el período aparece en la lista como `Activo`

### 11.2 Cargar personas por CSV

1. Abrir el período → botón **"Carga Masiva"**
2. Seleccionar el tipo de persona (ej: `Practicante`)
3. Subir el CSV con las columnas `identificacion, nombre, grupo, categoria`
4. El sistema crea personas nuevas, agrupa por el período, y reporta el resultado

### 11.3 Ver asistencia en tiempo real

1. Abrir el período → tabla de personas
2. Cada persona muestra: % de asistencia + semáforo de color (Verde/Amarillo/Rojo)
3. Los datos se actualizan después de cada sync del dispositivo ZK

### 11.4 Cerrar un período

**Manual:**
- Desde la lista de períodos → menú de opciones → **"Cerrar Período"**
- El período pasa a `Cerrado` y queda en solo lectura

**Automático:**
- El scheduler nocturno cierra todos los períodos donde `fecha_fin < hoy`
- Requiere `SYNC_AUTO=true` en el `.env`

### 11.5 Crear períodos desde Python

```python
import db as db_module

# Paso 1: asegurarse de que la persona existe
persona = db_module.resolver_persona_id(id_dispositivo="00042", dispositivo_id="uuid_del_dispositivo")

# Paso 2: crear el período
periodo = db_module.crear_periodo(
    persona_id=persona["persona_id"],
    nombre="Prácticas Abril A 2026",
    fecha_inicio="2026-04-01",
    fecha_fin="2026-04-15"
)

# Paso 3: calcular asistencia
resultados = db_module.calcular_asistencia_periodo(periodo["id"])
for r in resultados:
    print(f"{r['nombre']}: {r['porcentaje_asistencia']}% — {r['color']}")
```

### 11.6 Cerrar períodos vencidos (scheduler)

```python
# Esto ya está integrado en el scheduler de sync.py:
from db.queries.periodos import cerrar_periodos_vencidos
cerrar_periodos_vencidos()  # Cierra todos los periodos con fecha_fin < NOW()
```

---

# FASE 5 — Analytics e IA

## 12. Qué implementa la Fase 5

La Fase 5 consolida el análisis estadístico en un motor unificado. No existen `analytics.py` para empleados y `analytics_alumnos.py` para practicantes — hay un solo motor con filtros por `tipo_persona_id` y `grupo_id`.

**Lo que está operativo:**
- Risk Score individual (0-100) con semáforo
- Detección de anomalías por desviación estándar de tardanzas
- Agregación por grupo: tasa de asistencia por departamento/área
- Resumen general del período analizado
- Reporte narrativo con DeepSeek API (o fallback automático)
- UI en `/analytics` con filtros de fecha, tipo de persona y grupo
- Endpoint JSON `/api/analytics` para integraciones

**Lo que está pendiente** (ver sección 19):
- Funciones especializadas: patrón semanal, comparativa histórica de períodos, tendencia mensual
- Rutas específicas por entidad: `/analytics/grupo/<id>`, `/analytics/periodo/<id>`
- Alertas de riesgo en el scheduler nocturno

---

## 13. Motor de Analytics (`analytics.py`)

### 13.1 Función principal: `analizar(filtros)`

Punto de entrada unificado. Acepta filtros opcionales y retorna un dict estándar:

```python
import analytics

hallazgos = analytics.analizar(
    tipo_persona_id="uuid-del-tipo",  # opcional
    grupo_id="uuid-del-grupo",        # opcional (aceptado, pasa a la consulta)
    periodo_vigencia_id=None,         # aceptado pero reservado para implementación futura
    fecha_inicio=date(2026, 3, 1),    # opcional, default: hoy - 30 días
    fecha_fin=date(2026, 3, 31),      # opcional, default: hoy
)
```

### 13.2 Estructura de respuesta

```python
# Éxito:
{
    "exito": True,
    "rango": {"inicio": "2026-03-01", "fin": "2026-03-31"},
    "resumen_general": {
        "total_registros": 450,          # días×persona analizados
        "presentes": 390,
        "ausentes": 42,
        "tardanzas": 18,
        "tasa_asistencia_promedio": 90.2  # porcentaje
    },
    "riesgos": [                          # Top 10, ordenados por score desc
        {
            "persona_id": "uuid...",
            "nombre": "Juan Pérez",
            "grupo": "Contabilidad",
            "score": 85,
            "semaforo": "Rojo"            # Rojo≥70 | Amarillo≥40 | Verde<40
        },
        ...
    ],
    "anomalias": [                        # Personas con tardanzas > media + 1.5σ
        {
            "persona_id": "uuid...",
            "nombre": "María García",
            "tipo": "Exceso de Tardanzas",
            "detalle": "Tiene 8 tardanzas (Promedio del grupo: 2.1)"
        }
    ],
    "dimensiones": {
        "por_grupo": [                    # Ordenados por tasa_asistencia asc (peores primero)
            {"grupo": "Redes", "tasa_asistencia": 76.5, "total_personas": 12},
            {"grupo": "Contabilidad", "tasa_asistencia": 94.2, "total_personas": 8},
        ]
    }
}

# Sin datos:
{"exito": False, "error": "No hay datos para el rango y filtros especificados"}
```

### 13.3 Risk Score — escala y cálculo

El Risk Score se calcula acumulando penalizaciones por persona:

| Evento | Puntos |
|---|---|
| Ausencia en día programado | +15 puntos |
| Tardanza en entrada | +5 puntos |
| Máximo | 100 puntos |

| Rango | Semáforo | Interpretación |
|---|---|---|
| 0 – 39 | Verde | Sin novedades significativas |
| 40 – 69 | Amarillo | Requiere seguimiento |
| 70 – 100 | Rojo | Intervención recomendada |

### 13.4 Detección de anomalías estadísticas

Se detectan personas con un número de tardanzas que excede significativamente el promedio del grupo:

```
Límite = media_tardanzas + 1.5 × desviación_estándar
Personas con tardanzas > límite → anomalía "Exceso de Tardanzas"
```

Si toda la población tiene el mismo número de tardanzas (σ = 0), no se reportan anomalías.

### 13.5 Cómo carga los datos (`load_data_asistencia_dataframe`)

La función consulta todos los `periodos_vigencia` activos que intersectan el rango de fechas, aplica los filtros opcionales, y reutiliza `calcular_asistencia_periodo()` de la Fase 4 para obtener el detalle diario. El resultado se convierte a un DataFrame de Pandas para las agregaciones estadísticas.

---

## 14. Reporte narrativo con IA (`ia_report.py`)

### 14.1 Función `generar_narrativo(hallazgos, contexto="")`

Toma el dict de `analizar()` y retorna texto explicativo en español.

**Flujo de ejecución:**

```
¿Está configurada DEEPSEEK_API_KEY?
│
├── Sí → POST https://api.deepseek.com/v1/chat/completions
│          modelo: deepseek-chat
│          temperatura: 0.7
│          timeout: 15s
│          Prompt incluye: rango, tasa, ausencias, tardanzas,
│                          personas en riesgo, anomalías
│          Respuesta OK → devolver texto del modelo
│          Error/timeout → continuar al fallback
│
└── No (o error) → Generador de texto basado en reglas:
                    Párrafo 1: Resumen con tasa de asistencia
                    Párrafo 2: Alertas (riesgo alto + anomalías)
                    Párrafo 3: Recomendaciones fijas para supervisores
```

### 14.2 Ejemplo de salida (fallback sin API)

```
💡 Reporte de Desempeño Ejecutivo (2026-03-01 — 2026-03-31)

Durante este período, se ha registrado una asistencia promedio del 82.4% sobre la
jornada laboral programada. Se observa una disminución ligera en la puntualidad
que requiere seguimiento preventivo.

🚨 Señales de Alerta Críticas:
- Se identificaron 3 personas en zona de riesgo alto de incumplimiento por
  acumulación de inasistencias o tardanzas constantes.
- Se han detectado 1 comportamientos anómalos estadísticamente (exceso puntual
  de tardanzas no habituales).

📋 Recomendaciones para Supervisión:
1. Entrevistar a las personas con mayor Risk Score para mitigar ausentismo.
2. Monitorear los horarios asignados para descartar desconfiguraciones administrativas.
```

---

## 15. Rutas API — Fase 5

| Método | Ruta | Roles | Descripción |
|---|---|---|---|
| `GET` | `/analytics` | `gestor`, `admin`, `superadmin` | Dashboard de analytics con UI (filtros fecha, tipo, grupo) |
| `GET` | `/analytics/periodo/<id>` | `gestor`, `admin`, `superadmin` | Vista analytics dedicada de un período específico |
| `GET` | `/api/analytics` | `gestor`, `admin`, `superadmin` | Retorna JSON con hallazgos completos |
| `POST` | `/api/analytics/narrativo` | `gestor`, `admin`, `superadmin` | Genera narrativo IA on-demand desde JSON de hallazgos |

### Parámetros de query (rutas GET)

| Parámetro | Tipo | Default | Descripción |
|---|---|---|---|
| `fecha_inicio` | `YYYY-MM-DD` | hoy − 30 días | Inicio del rango de análisis |
| `fecha_fin` | `YYYY-MM-DD` | hoy | Fin del rango de análisis |
| `tipo_persona_id` | UUID | — | Filtrar solo por este tipo |
| `grupo_id` | UUID | — | Filtrar solo este grupo |

### Ejemplo de request al endpoint JSON

```http
GET /api/analytics?fecha_inicio=2026-03-01&fecha_fin=2026-03-31&tipo_persona_id=uuid-practicante
Accept: application/json
```

```json
{
  "exito": true,
  "rango": {"inicio": "2026-03-01", "fin": "2026-03-31"},
  "resumen_general": {
    "total_registros": 240,
    "presentes": 210,
    "ausentes": 20,
    "tardanzas": 10,
    "tasa_asistencia_promedio": 91.3
  },
  "riesgos": [...],
  "anomalias": [...],
  "dimensiones": {"por_grupo": [...]}
}
```

---

## 16. Configuración de DeepSeek

Para activar reportes narrativos con IA, agregar al `.env`:

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
```

Sin esta variable, el sistema usa automáticamente el generador de texto por reglas (igual de funcional para la mayoría de casos de uso operativo).

**Obtener la clave API:** registrarse en [platform.deepseek.com](https://platform.deepseek.com) → API Keys → Create new key.

**Costo estimado:** El prompt enviado es pequeño (~300 tokens). A los precios actuales de DeepSeek, un reporte narrativo cuesta menos de $0.001 USD.

---

## 17. Cómo usar — Fase 5

### 17.1 Desde la UI

1. Ir a **`/analytics`** (visible para `gestor`, `admin`, `superadmin`)
2. Seleccionar rango de fechas y opcionalmente filtrar por tipo de persona **y/o grupo**
3. La página muestra:
   - **KPIs:** Asistencia promedio, total registros, ausencias, tardanzas
   - **Reporte IA:** Párrafo narrativo generado (DeepSeek o reglas)
   - **Anomalías:** Lista de personas con comportamientos estadísticamente atípicos
   - **Risk Score:** Tabla con top 10 personas en mayor riesgo, con barra de progreso y semáforo

### 17.2 Desde Python

```python
import analytics
import ia_report

# Análisis del último mes para todos los tipos
hallazgos = analytics.analizar(
    fecha_inicio=date(2026, 3, 1),
    fecha_fin=date(2026, 3, 31)
)

if hallazgos["exito"]:
    # Ver personas en riesgo alto
    for r in hallazgos["riesgos"]:
        if r["semaforo"] == "Rojo":
            print(f"RIESGO ALTO: {r['nombre']} ({r['grupo']}) — Score: {r['score']}")

    # Generar narrativo
    texto = ia_report.generar_narrativo(hallazgos)
    print(texto)
```

### 17.3 Filtrar por tipo de persona

```python
# Solo analizar Practicantes
hallazgos = analytics.analizar(
    tipo_persona_id="uuid-del-tipo-practicante",
    fecha_inicio=date(2026, 4, 1),
    fecha_fin=date(2026, 4, 15)
)
```

### 17.4 Interpretar el Risk Score en un script de alertas

```python
# Ejemplo de script de alerta manual (hasta que se implemente en el scheduler)
import analytics
from datetime import date, timedelta

hallazgos = analytics.analizar(
    fecha_inicio=date.today() - timedelta(days=7),
    fecha_fin=date.today()
)

rojos = [r for r in hallazgos.get("riesgos", []) if r["semaforo"] == "Rojo"]
if rojos:
    print(f"ALERTA: {len(rojos)} personas en riesgo alto esta semana:")
    for r in rojos:
        print(f"  - {r['nombre']} — Score: {r['score']}")
```

---

## 18. Estado de implementación consolidado

### Fase 4

| Componente | Archivo | Estado | Notas |
|---|---|---|---|
| Schema de BD (personas, grupos, categorias, periodos_vigencia) | `db/schema.py` | ✅ Completo | Todas las tablas con índices correctos |
| Tabla `grupos_periodo` (UI-level) | `db/schema.py` | ✅ Completo | Migración 0004; desvincula UI de periodos_vigencia |
| `db/queries/personas.py` | personas.py | ✅ Completo | Resolución ZK, upsert, lookup |
| `db/queries/personas_crud.py` | personas_crud.py | ✅ Completo | CRUD completo + historial por identificación |
| `db/queries/periodos.py` | periodos.py | ✅ Completo | Reescrito con grupos_periodo; bug de firma corregido |
| `db/queries/grupos.py` | grupos.py | ✅ Completo | CRUD de grupos y categorías |
| `db/queries/asistencia_periodo.py` | asistencia_periodo.py | ✅ Completo | Motor de cálculo diario con feriados y semáforo |
| Import CSV de personas | periodos.py | ✅ Completo | Crea personas, grupos, categorías, horarios |
| Resolución `periodo_vigencia_id` en sync | asistencias.py | ✅ Completo | Automático, sin cambios en sync.py |
| Rutas `/periodos/*` | app.py | ✅ Completo | 7 rutas (incluye archivar) |
| Rutas `/personas/*` | app.py | ✅ Completo | 4 rutas (lista, crear, editar, historico) |
| Rutas `/admin/grupos/*` | app.py | ✅ Completo | CRUD completo en 3 rutas |
| Rutas `/admin/categorias/*` | app.py | ✅ Completo | CRUD completo en 3 rutas |
| Cierre automático en scheduler | sync.py | ✅ Completo | `cerrar_periodos_vencidos()` llamado nocturnamente |
| Template `periodos/lista.html` | templates/ | ✅ Completo | Tabs activo/historial, modal de creación |
| Template `periodos/detalle.html` | templates/ | ✅ Completo | Tabla con semáforos, modal CSV |
| Template `personas/lista.html` | templates/ | ✅ Completo | Tabla filtrable, modales crear/editar |
| Template `personas/historico.html` | templates/ | ✅ Completo | Búsqueda por cédula, lista de períodos |
| Template `admin/grupos.html` | templates/ | ✅ Completo | CRUD de grupos con tipos |
| Template `admin/categorias.html` | templates/ | ✅ Completo | CRUD de categorías, filtro por tipo |
| Enlace "Personas" y "Grupos" en sidebar | `base.html` | ✅ Completo | Visibles para todos los roles |
| PDF de período | — | ⏳ Fase 6 | Fuera del alcance de Fase 4 |

### Fase 5

| Componente | Archivo | Estado | Notas |
|---|---|---|---|
| `load_data_asistencia_dataframe()` | analytics.py | ✅ Completo | Carga datos vía `calcular_asistencia_periodo()` |
| `calcular_risk_score()` | analytics.py | ✅ Completo | Score 0-100, ponderado por ausencias y tardanzas |
| `analizar()` — punto de entrada unificado | analytics.py | ✅ Completo | Resumen + riesgos + anomalías + dimensiones |
| Detección de anomalías (σ de tardanzas) | analytics.py | ✅ Completo | Límite = media + 1.5σ |
| Agregación por grupo | analytics.py | ✅ Completo | Tasa de asistencia por grupo |
| `patron_semanal(persona_id)` | analytics.py | ✅ Completo | Análisis por día de semana (últimas N semanas) |
| `comparar_grupos(grupo_ids)` | analytics.py | ✅ Completo | Comparativa cruzada entre grupos |
| `ranking_departamento(grupo_id)` | analytics.py | ✅ Completo | Ranking de personas dentro de un grupo |
| `tendencia_mensual(tipo_persona_id)` | analytics.py | ✅ Completo | Tendencia histórica mes a mes |
| `resumen_periodo(periodo_id)` | analytics.py | ✅ Completo | Resumen ejecutivo de un período concreto |
| `distribucion_asistencia_periodo(periodo_id)` | analytics.py | ✅ Completo | Distribución semáforo Verde/Amarillo/Rojo del período |
| `comparar_periodos_historicos()` | analytics.py | ✅ Completo | Comparativa entre períodos pasados |
| `tasa_riesgo_por_grupo(grupo_id)` | analytics.py | ✅ Completo | Score de riesgo agregado del grupo |
| `generar_narrativo()` con DeepSeek + fallback | ia_report.py | ✅ Completo | Fallback operativo sin API key |
| Ruta `/analytics` (UI) | app.py | ✅ Completo | Filtros: fecha, tipo, **grupo** |
| Ruta `/analytics/periodo/<id>` (UI) | app.py | ✅ Completo | Vista analytics dedicada de un período |
| Ruta `/api/analytics` (JSON) | app.py | ✅ Completo | Retorna dict completo |
| Ruta `/api/analytics/narrativo` (JSON) | app.py | ✅ Completo | Narrativo IA on-demand via POST |
| Selector de grupo en `analytics.html` | templates/ | ✅ Completo | Filtro `grupo_id` visible en el formulario |
| Dependencias pandas/numpy/requests | requirements.txt | ✅ Completo | `requests` agregado en validación anterior |
| Alertas de riesgo en scheduler nocturno | sync.py | ✅ Completo | `_enviar_alertas_riesgo()` registra en audit_log |

---

## 19. Funcionalidades pendientes para fases futuras

Todas las funcionalidades de Fase 4 y Fase 5 están implementadas. Los elementos siguientes corresponden a mejoras futuras (Fase 6+).

| Funcionalidad | Fase propuesta | Impacto |
|---|---|---|
| PDF de período (`generar_pdf_periodo`) | Fase 6 | Descarga del reporte de asistencia del período en PDF |
| Alertas por email cuando Risk Score > umbral | Fase 6 | Notificaciones SMTP automáticas a supervisores |
| Filtro de vista para `supervisor_periodo` y `supervisor_grupo` | Fase 6 | Roles que ven solo "su" ámbito asignado |
| Gráficas de tendencia en `analytics.html` | Fase 6 | Visualización Chart.js de `tendencia_mensual()` |
| Exportar analytics a CSV/Excel | Fase 6 | Descarga de datos analytics tabulados |

---

## 20. Archivos modificados y creados

### Archivos nuevos (Fase 4 y 5)

| Archivo | Fase | Descripción |
|---|---|---|
| `db/queries/personas.py` | 4 | Resolución ZK ↔ persona, upsert, vinculación dispositivos |
| `db/queries/personas_crud.py` | 4 | CRUD completo de personas + historial por identificación |
| `db/queries/periodos.py` | 4 | CRUD de períodos (grupos_periodo + periodos_vigencia) + import CSV |
| `db/queries/asistencia_periodo.py` | 4 | Motor de cálculo diario con feriados y semáforos |
| `db/queries/grupos.py` | 4 | CRUD de grupos y categorías |
| `db/migrations/versions/0004_grupos_periodo.py` | 4 | Migración Alembic para tabla `grupos_periodo` |
| `analytics.py` | 5 | Motor unificado: risk score, anomalías, dimensiones + 8 funciones avanzadas |
| `ia_report.py` | 5 | Narrativo con DeepSeek API + fallback por reglas |
| `templates/periodos/lista.html` | 4 | UI de lista de períodos activos e historial |
| `templates/periodos/detalle.html` | 4 | UI de detalle de período con tabla de asistencia |
| `templates/personas/lista.html` | 4 | UI de catálogo de personas con filtros y CRUD |
| `templates/personas/historico.html` | 4 | Búsqueda de historial por identificación |
| `templates/admin/grupos.html` | 4 | CRUD de grupos desde UI |
| `templates/admin/categorias.html` | 4 | CRUD de categorías desde UI |
| `templates/analytics.html` | 5 | Dashboard de analytics con KPIs, narrativo IA, risk table |

### Archivos modificados (Fase 4 y 5)

| Archivo | Fase | Qué se agregó/cambió |
|---|---|---|
| `db/schema.py` | 4 | Tabla `grupos_periodo` (BLOQUE 3B) |
| `db/queries/asistencias.py` | 4 | Resolución automática de `periodo_vigencia_id` al insertar |
| `db/__init__.py` | 4+5 | Exports de grupos, categorías, personas CRUD |
| `app.py` | 4+5 | Rutas personas CRUD, grupos CRUD, categorías CRUD, archivar período, analytics/periodo, api/narrativo; bug `cerrar_periodo` corregido |
| `sync.py` | 4+5 | `cerrar_periodos_vencidos()` + `_enviar_alertas_riesgo()` en el scheduler nocturno |
| `templates/base.html` | 4 | Links "Personas" y "Grupos" en el sidebar |
| `templates/analytics.html` | 5 | Selector de grupo en el formulario de filtros |
| `requirements.txt` | 5 | `requests>=2.31` agregado |
| `.env.example` | 5 | `DEEPSEEK_API_KEY` documentada |

### Archivos sin cambios en Fase 4 y 5

`script.py`, `horarios.py`, `auth.py`, `decorators.py`, `db/connection.py`, `db/migrations/env.py`, `templates/login.html`, `docker-compose.yml`, `Dockerfile`

---

*Siguiente: Fase 6 — PDF de períodos, alertas por email SMTP, restricciones de scope para supervisores*
