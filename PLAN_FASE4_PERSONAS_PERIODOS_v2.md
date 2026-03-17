# Plan de Implementación — Fase 4: Gestión de Personas, Grupos y Períodos
**Versión:** 2.0 — Reemplaza "Módulo de Alumnos" con gestión horizontal
**Fecha:** 2026-03-17
**Prerequisito:** Fases 1, 2 y 3 v2 completadas y verificadas

---

## Índice

1. [Contexto y cambio de enfoque](#1-contexto-y-cambio-de-enfoque)
2. [Alcance](#2-alcance)
3. [Qué desaparece del plan original](#3-qué-desaparece-del-plan-original)
4. [Modelo de negocio horizontal](#4-modelo-de-negocio-horizontal)
5. [Flujos de trabajo](#5-flujos-de-trabajo)
6. [Sincronización: routing unificado](#6-sincronización-routing-unificado)
7. [Reportes](#7-reportes)
8. [Consulta histórica](#8-consulta-histórica)
9. [Estructura de la UI](#9-estructura-de-la-ui)
10. [Nuevas rutas de API](#10-nuevas-rutas-de-api)
11. [Pasos de implementación](#11-pasos-de-implementación)
12. [Criterio de finalización](#12-criterio-de-finalización)

---

## 1. Contexto y cambio de enfoque

### 1.1 Por qué esta fase ya no es el "Módulo de Alumnos"

La Fase 4 original implementaba un módulo separado con tablas propias (`alumnos`, `asistencias_alumnos`, `periodos_practicas`, `matriculas_periodo`) activado por un flag `modulo_alumnos=true`.

Con el modelo horizontal de la Fase 1 v2:
- No existen tablas separadas para alumnos
- No existe el flag `modulo_alumnos`
- Los "alumnos en prácticas" son personas con `tipo_persona = 'Practicante'`
- Los "períodos de prácticas" son `periodos_vigencia` con fechas inicio/fin
- La "matrícula" es la combinación persona + período de vigencia + asignación de horario
- Las marcaciones van a la tabla `asistencias` unificada

### 1.2 Qué gana el sistema con este cambio

- Un contratista por 3 meses usa exactamente el mismo flujo que un practicante de 15 días
- Un empleado temporal usa el mismo flujo que un empleado indefinido
- Un voluntario por un evento puntual usa el mismo flujo
- Los reportes de todos ellos se generan con el mismo motor

Esta fase implementa la **capa de UI y lógica de negocio** sobre el modelo horizontal que ya existe en la base de datos desde la Fase 1.

---

## 2. Alcance

**Qué incluye:**
- UI de gestión de personas: crear, editar, buscar, listar por tipo y grupo
- UI de gestión de grupos: jerarquía de departamentos, áreas, bloques
- UI de gestión de categorías: cargos, niveles, especialidades
- UI de gestión de períodos de vigencia: crear, cerrar, archivar
- Import de personas desde CSV (con asignación de horario al período)
- Procesamiento de asistencia por período: presencia/ausencia por día
- Reportes de período: PDF con asistencia completa
- Reportes de grupo: PDF agregado por departamento/área
- Alerta temprana: personas en riesgo de incumplimiento
- Consulta histórica: buscar cualquier persona en cualquier período pasado
- Cierre automático de períodos al pasar `fecha_fin`

**Qué NO incluye:**
- Analytics avanzado (Fase 5)
- Drivers adicionales de hardware (Fase 6)

---

## 3. Qué desaparece del plan original

| Elemento de Fase 4 v1 | Reemplazado por |
|---|---|
| `UPDATE tenants SET modulo_alumnos=true` | Configurar `tipo_persona = 'Practicante'` (ya en Fase 3) |
| `carreras` como tabla | `grupos` con `tipo_grupo='carrera'` o `categorias` |
| `bloques` como tabla | `grupos` con `tipo_grupo='bloque'` |
| `db/queries/alumnos.py` | `db/queries/personas.py` + `db/queries/periodos.py` |
| Routing sync a `asistencias_alumnos` | No existe. Todo va a `asistencias` via `personas_dispositivos` |
| `calcular_asistencia_periodo()` específica de alumnos | `calcular_asistencia_periodo()` genérica por `tipo_persona_id` |
| PDF con "aprobados/reprobados" de alumnos | PDF de período genérico configurable |

---

## 4. Modelo de negocio horizontal

### 4.1 El caso de ISTPET con el modelo nuevo

```
Tipo: Practicante
Grupos:
  Contabilidad (tipo_grupo='carrera')
  Redes y Telecomunicaciones (tipo_grupo='carrera')
Categorías (por tipo Practicante):
  Primer Nivel, Segundo Nivel, Tercer Nivel

Personas (tipo=Practicante):
  Juan Pérez → grupo=Contabilidad, categoria=Segundo Nivel

Periodo de vigencia (para Juan Pérez):
  nombre = "Prácticas Abril A 2026"
  fecha_inicio = 2026-04-01
  fecha_fin = 2026-04-15
  estado = 'activo'

Asignación de horario:
  persona = Juan Pérez
  plantilla = "Horario Prácticas L-V 07:00-12:00"
  fecha_inicio = 2026-04-01
  ciclo_semanas = 1
```

### 4.2 Ciclo de vida de un período de vigencia

```
ACTIVO → CERRADO → ARCHIVADO
```

| Estado | Descripción | Acciones permitidas |
|---|---|---|
| `activo` | Período en curso | Agregar personas, ver asistencia en tiempo real, cerrar |
| `cerrado` | Datos congelados | Solo lectura, generar reporte final, archivar |
| `archivado` | Movido a historial | Solo lectura, no aparece en lista principal |

**Transiciones automáticas:**
- `activo → cerrado`: cuando `NOW() > fecha_fin`. Job nocturno verifica y cierra.
- `cerrado → archivado`: solo manual.

### 4.3 Umbral de cumplimiento por período

`periodos_vigencia` puede almacenar en `descripcion` o en la config del tenant un umbral de asistencia mínimo. Por defecto: 80%.

En la v2 esto se puede guardar en `configuracion JSONB` del tenant o directamente en el período como campo propio si se necesita por período. Para ISTPET es suficiente con la configuración del tenant.

### 4.4 Personas indefinidas vs con período

- **Empleado indefinido:** tiene un `periodo_vigencia` con `fecha_fin = NULL`. Puede tener múltiples si cambia de condición.
- **Practicante:** tiene `periodo_vigencia` con fechas definidas. Puede aparecer en múltiples períodos históricos.
- **Contratista:** igual al practicante.

Todos usan el mismo modelo. El comportamiento del reporte se adapta según si el período tiene fecha fin o no.

---

## 5. Flujos de trabajo

### 5.1 Flujo: configurar un nuevo tipo de persona (admin)

```
1. Admin va a Configuración → Tipos de Persona
2. Crea tipo "Practicante" con color y descripción
3. Crea categorías asociadas: "Primer Nivel", "Segundo Nivel", "Tercer Nivel"
4. Crea grupos (si no existen): "Contabilidad", "Redes"
5. Configura los dispositivos ZK asignados a practicantes:
   - Los mismos dispositivos existentes, ya no necesitan campo 'modulo'
   - Las personas del tipo Practicante se registran en esos dispositivos
     via personas_dispositivos
```

### 5.2 Flujo: crear un nuevo período de prácticas

```
Gestor:
1. Va a Períodos → Nuevo Período
2. Completa:
   - Nombre ("Prácticas Abril A 2026")
   - Tipo de persona asociado ("Practicante")
   - Fecha inicio y fin (típicamente 15 días)
   - Umbral de asistencia si difiere del default
3. Guarda → período en estado 'activo'
4. Procede a agregar personas al período
```

**Nota:** El período no está ligado a un bloque ni a un dispositivo. Las personas que marcan en cualquier dispositivo donde estén registradas contribuyen al período. Esto es más flexible que el modelo v1.

### 5.3 Flujo: agregar personas a un período

**Opción A — Carga masiva por CSV:**
```
1. Gestor descarga plantilla CSV
2. Completa la plantilla:
   Columnas: identificacion, nombre, grupo, categoria,
             lunes_entrada, lunes_salida, ..., viernes_entrada, viernes_salida
3. Sube el CSV
4. Sistema procesa:
   a. Por cada fila, busca persona por identificación en 'personas'
      → Existe: usa el id existente
      → No existe: crea la persona con el tipo correspondiente
   b. Crea periodo_vigencia para la persona con las fechas del período
   c. Crea asignacion_horario con los horarios del CSV
   d. Si la persona tiene id en usuarios_zk, verifica/crea personas_dispositivos
5. Resumen: X procesadas, Y nuevas, Z actualizadas, errores detallados
```

**Opción B — Alta individual:**
```
Gestor → Nueva Persona en el Período
→ Busca por identificación (pre-rellena si ya existe)
→ Completa horario del período
→ Guarda
```

### 5.4 Flujo: cierre de período

**Automático (nocturno):**
```
Scheduler verifica:
  SELECT * FROM periodos_vigencia
  WHERE estado='activo' AND fecha_fin IS NOT NULL AND fecha_fin < NOW()

Para cada período vencido:
  1. Calcular asistencia final de todas las personas del período
  2. Cambiar estado='cerrado'
  3. Guardar snapshot del resultado en periodo_vigencia.descripcion (JSONB)
  4. Notificar por email al gestor si SMTP configurado
```

---

## 6. Sincronización: routing unificado

### 6.1 El cambio más importante respecto a la v1

La v1 tenía routing condicional: si `dispositivo.modulo == 'alumnos'`, insertar en `asistencias_alumnos`; si `modulo == 'empleados'`, insertar en `asistencias`.

En v2 no existe ese routing. **Todo va a `asistencias`**. El routing ya ocurre implícitamente a través de `personas_dispositivos`:

```
ZK reporta: id_usuario = "00042"
  ↓
personas_dispositivos lookup:
  WHERE id_en_dispositivo = "00042" AND dispositivo_id = X
  → persona_id = UUID de Juan Pérez (tipo: Practicante)
  ↓
INSERT INTO asistencias (persona_id, fecha_hora, tipo, ...)
```

El sistema no necesita saber si Juan Pérez es empleado o practicante para insertar la marcación. Eso solo importa al generar el reporte.

### 6.2 Asociación de período en la inserción

Al insertar una marcación, el sistema puede opcionalmente resolver a qué período de vigencia pertenece:

```sql
SELECT id FROM periodos_vigencia
WHERE persona_id = :persona_id
  AND estado = 'activo'
  AND fecha_inicio <= :fecha
  AND (fecha_fin IS NULL OR fecha_fin >= :fecha)
LIMIT 1
```

Si encuentra un período activo, llena `asistencias.periodo_vigencia_id`. Si no, queda NULL (la persona marcó fuera de cualquier período activo).

### 6.3 Tabla `dispositivos` simplificada

El campo `modulo` ('empleados', 'alumnos') de la v1 **no existe** en el schema v2. Los dispositivos son agnósticos — registran marcaciones de quien está registrado en ellos vía `personas_dispositivos`.

---

## 7. Reportes

### 7.1 Reporte de período

Generado por `generar_pdf_periodo(periodo_vigencia_id)`. Estructura:

```
Portada:
  - Nombre del período
  - Tipo de persona
  - Rango de fechas
  - Total de personas

Por persona (una fila por día del período):
  - Nombre | Identificación | Grupo | Categoría
  - Por cada día: Presente / Ausente / Feriado
  - % de asistencia | Estado (semáforo)

Resumen final:
  - Lista: cumplieron el umbral / no cumplieron
  - Estadísticas del período
```

### 7.2 Reporte de grupo

Generado por `generar_pdf_grupo(grupo_id, fecha_inicio, fecha_fin)`. Agrega asistencia de todas las personas del grupo en el período. Útil para reportes de departamento de empleados.

### 7.3 Semáforo de cumplimiento

Basado en `% de días presentes vs días programados`:

| Rango | Estado | Color |
|---|---|---|
| ≥ 90% | Óptimo | Verde |
| 75% - 89% | Aceptable | Amarillo |
| < 75% | En riesgo | Rojo |

El umbral de "riesgo" es configurable en la `configuracion` del tenant.

### 7.4 Diferencia con reporte de empleados

Los reportes de personas con período indefinido (empleados) siguen siendo generados por `script.py` con el análisis de tardanzas. Los reportes de período (con fecha fin) usan el nuevo motor basado en cumplimiento porcentual.

La diferenciación se hace por `periodo_vigencia.fecha_fin`:
- `fecha_fin IS NULL` → reporte de comportamiento continuo (tardanzas, horas)
- `fecha_fin IS NOT NULL` → reporte de cumplimiento por período (presencia/ausencia, %)

---

## 8. Consulta histórica

Permite buscar cualquier persona por identificación y ver todos sus períodos pasados.

```
GET /personas/historico?identificacion=1234567890

Retorna:
  Persona: Juan Pérez, Tipo: Practicante, Grupo: Contabilidad
  Períodos:
    - Prácticas Enero A 2026 (cerrado) → 87% asistencia
    - Prácticas Julio A 2025 (archivado) → 93% asistencia

GET /personas/historico/<persona_id>/periodo/<periodo_id>

Retorna:
  Detalle día a día: marcaciones exactas del dispositivo
```

**Garantía de permanencia:** Una persona no se elimina. Un período cerrado es de solo lectura. Los datos históricos son inmutables.

---

## 9. Estructura de la UI

### 9.1 Nuevas secciones en la navegación

La navegación se adapta dinámicamente según los tipos de persona configurados y los roles del usuario. Las secciones no tienen nombres fijos de módulo; se generan a partir de los tipos:

```
Dashboard
Personas
  └── Empleados (si existe tipo 'Empleado')
  └── Practicantes (si existe tipo 'Practicante')
  └── Contratistas (si existe tipo 'Contratista')
Períodos
  └── Activos
  └── Historial
Reportes
Configuración (admin)
```

### 9.2 Vista de período activo

Tabla de asistencia en tiempo real:

| Nombre | ID | Grupo | Lun 1 | Mar 2 | ... | % | Estado |
|---|---|---|---|---|---|---|---|
| Juan Pérez | 123 | Contabilidad | ✓ | ✗ | ... | 87% | 🟡 |

La tabla se actualiza después de cada sync.

### 9.3 Vista de gestión de personas

Lista filtrable por tipo, grupo, categoría, estado. Permite crear, editar y buscar.

---

## 10. Nuevas rutas de API

| Método | Ruta | Función | Roles |
|---|---|---|---|
| `GET` | `/personas` | Lista de personas (filtros: tipo, grupo, activo) | `gestor`, `admin` |
| `POST` | `/personas` | Crear persona | `gestor`, `admin` |
| `GET/PUT` | `/personas/<id>` | Detalle y edición | `gestor`, `admin` |
| `GET` | `/personas/historico` | Búsqueda por identificación | `gestor`, `admin` |
| `GET` | `/grupos` | Lista de grupos | `gestor`, `admin` |
| `GET/POST` | `/admin/grupos` | CRUD de grupos | `admin` |
| `GET/POST` | `/admin/categorias` | CRUD de categorías | `admin` |
| `GET` | `/periodos` | Lista de períodos activos | `gestor`, `supervisor_periodo` |
| `POST` | `/periodos` | Crear período | `gestor`, `admin` |
| `GET` | `/periodos/<id>` | Detalle + asistencia en tiempo real | `gestor`, `supervisor_periodo` |
| `POST` | `/periodos/<id>/agregar-personas` | CSV o individual | `gestor`, `admin` |
| `POST` | `/periodos/<id>/cerrar` | Cerrar manualmente | `gestor`, `admin` |
| `POST` | `/periodos/<id>/archivar` | Archivar período cerrado | `gestor`, `admin` |
| `GET` | `/periodos/<id>/reporte` | PDF del período | `gestor`, `supervisor_periodo` |
| `GET` | `/grupos/<id>/reporte` | PDF del grupo en rango | `gestor`, `supervisor_grupo` |

---

## 11. Pasos de implementación

### Paso 1 — Verificar datos iniciales de ISTPET

Verificar que desde la Fase 3 ya están creados en ISTPET:
- `tipos_persona`: `Empleado`, `Practicante`
- `grupos`: departamentos y áreas de empleados
- Grupos de practicantes: `Contabilidad`, `Redes y Telecomunicaciones` (tipo_grupo='carrera')
- `categorias`: cargos de empleados + niveles de practicantes

**Verificación:**
- `SELECT * FROM istpet.tipos_persona;` muestra los tipos
- `SELECT * FROM istpet.grupos;` muestra la jerarquía

---

### Paso 2 — Implementar `db/queries/periodos.py`

- `crear_periodo(persona_id, nombre, fecha_inicio, fecha_fin, descripcion)` → dict
- `get_periodo(id)` → dict
- `listar_periodos_activos(tipo_persona_id=None)` → list
- `listar_periodos_historial(tipo_persona_id=None)` → list
- `agregar_personas_a_periodo_bulk(periodo_id, personas)` → resultado
- `cerrar_periodo(id)`
- `archivar_periodo(id)`
- `cerrar_periodos_vencidos()` → para el scheduler

**Verificación:**
- `crear_periodo()` crea el registro y lo retorna
- `listar_periodos_activos(tipo_persona_id=<practicante>)` retorna solo períodos de practicantes

---

### Paso 3 — Implementar `db/queries/asistencia_periodo.py`

Nueva función central `calcular_asistencia_periodo(periodo_id)`:

```python
def calcular_asistencia_periodo(periodo_id: str) -> list[dict]:
    """
    Por cada persona en el período × cada día del rango:
    - Determina si es día programado (tiene horario ese día de semana)
    - Excluye feriados
    - Cruza con asistencias WHERE periodo_vigencia_id = periodo_id
    - Determina: presente / presente_tarde / ausente / feriado / no_programado
    - Calcula % de asistencia y estado del semáforo
    """
```

Esta función reemplaza tanto `consultar_asistencias()` del script actual (para períodos con fecha fin) como la función `calcular_asistencia_periodo()` que existía en la v1 de alumnos.

**Verificación:**
- Con datos de prueba insertados manualmente en `asistencias`, la función retorna días correctamente clasificados
- Feriados excluidos del denominador
- % calculado correctamente
- Semáforo asignado según umbral

---

### Paso 4 — Implementar import CSV de personas a período

- Definir formato del CSV (columnas, encoding, validaciones)
- `procesar_csv_personas_periodo(archivo, periodo_id, tipo_persona_id)` → resultado
- Lógica de upsert: crear persona si no existe, actualizar si existe
- Crear `periodos_vigencia` por persona con las fechas del período
- Crear `asignaciones_horario` con la plantilla correspondiente o crear nueva plantilla desde el CSV

**Verificación:**
- CSV con 10 personas (5 nuevas, 5 existentes) → 5 creadas, 5 actualizadas, períodos y horarios creados
- CSV con errores → reporte detallado de qué falló y en qué fila

---

### Paso 5 — Actualizar `sync.py` para resolver `periodo_vigencia_id`

Agregar a la función de inserción de asistencias la resolución del período activo:

```python
# En sync.py, al insertar una marcación:
periodo_id = db.get_periodo_vigente_en_fecha(persona_id, fecha)
# Pasar periodo_id a insertar_asistencias()
```

**Verificación:**
- Sync de dispositivo → marcaciones de practicantes tienen `periodo_vigencia_id` lleno
- Marcación fuera de cualquier período → `periodo_vigencia_id = NULL`, se inserta igual

---

### Paso 6 — Implementar rutas de API

- Todas las rutas de la sección 10
- Plantillas: `personas/lista.html`, `periodos/lista.html`, `periodos/detalle.html`
- `periodos/detalle.html` muestra la tabla de asistencia en tiempo real con semáforos

**Verificación:**
- Gestor puede crear un período, subir CSV y ver la tabla de asistencia
- `supervisor_periodo` solo puede ver su período asignado
- `supervisor_grupo` solo puede ver las personas de su grupo

---

### Paso 7 — Generación de PDF de período

`generar_pdf_periodo(periodo_id)` usando ReportLab con la estructura de la sección 7.1.

**Verificación:**
- PDF contiene todas las personas del período con sus días
- Feriados marcados correctamente
- Página final con lista de cumplimiento
- Descargable desde la UI

---

### Paso 8 — Cierre automático de períodos en el scheduler

Agregar `cerrar_periodos_vencidos()` al scheduler nocturno existente en `sync.py`.

**Verificación:**
- Período con `fecha_fin = ayer` → después de correr el scheduler, aparece como `cerrado`
- Datos de asistencia en período cerrado coinciden con la vista previa al cierre

---

### Paso 9 — Alerta temprana

Tarea del scheduler `enviar_alertas_riesgo(tipo_persona_id=None)`:
- Se ejecuta cuando un período activo llega a la mitad de su duración
- Calcula `calcular_asistencia_periodo()` y filtra personas bajo el umbral
- Notifica por email al `gestor` asignado o al admin del tenant

**Verificación:**
- Período activo con 2 personas: una con 90% y otra con 50%
- La alerta menciona solo a la de 50%

---

### Paso 10 — Consulta histórica

- Ruta `GET /personas/historico` con búsqueda por identificación
- Vista de todos los períodos de la persona con resultados
- Detalle día a día de un período específico

**Verificación:**
- Buscar por identificación con 2 períodos → muestra ambos con sus resultados
- Detalle muestra marcaciones exactas del dispositivo
- Persona sin períodos → "No se encontraron registros"

---

## 12. Criterio de finalización

- [ ] Gestor puede crear personas, grupos, categorías y períodos desde la UI
- [ ] Import CSV crea personas, períodos de vigencia y horarios correctamente
- [ ] Sync deposita marcaciones en `asistencias` con `periodo_vigencia_id` resuelto
- [ ] `calcular_asistencia_periodo()` produce resultados correctos con feriados excluidos
- [ ] Tabla de asistencia en tiempo real muestra semáforos correctos
- [ ] PDF de período generado con estructura completa
- [ ] Cierre automático funciona al pasar `fecha_fin`
- [ ] Período cerrado es de solo lectura
- [ ] Alerta temprana notifica por email a las personas bajo el umbral
- [ ] Consulta histórica permite buscar cualquier persona y ver todos sus períodos
- [ ] Roles respetados: `supervisor_periodo` solo ve su período; `supervisor_grupo` solo su grupo
- [ ] `audit_log` registra: `crear_periodo`, `cerrar_periodo`, `agregar_personas`, `generar_pdf`
- [ ] No existen referencias a `modulo_alumnos`, `asistencias_alumnos`, `periodos_practicas`, ni `matriculas_periodo` en el código

**Una vez completados estos criterios, el sistema está listo para la Fase 5 (Analytics e IA).**
