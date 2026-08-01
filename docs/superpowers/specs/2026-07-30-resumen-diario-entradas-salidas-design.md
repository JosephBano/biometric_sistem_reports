# Resumen diario en Analítica de Entradas y Salidas

Fecha: 2026-07-30
Estado: aprobado, pendiente de implementación

## Problema

La vista `/analytics/entradas-salidas` lista una fila por marcación, con columnas
`Dato crudo` y `Fuente` que al operador no le dicen nada. Para responder
"¿a qué hora entró y salió, cuánto estuvo dentro, y marcó bien?" hay que leer
el listado a ojo y aparear las filas mentalmente.

Los errores de marcaje son reales y frecuentes: en el rango de ejemplo
(persona ZK 56, 23–29 jul 2026) el día 2026-07-24 tiene dos marcajes de tipo
`Salida` seguidos, sin ninguna entrada.

## Solución

Cambiar la unidad de la tabla: **una fila por día calendario** del rango, con
los tiempos calculados y un estado que señala los marcajes inconsistentes.
Clic en la fila abre un popup con los marcajes crudos de ese día.

## Columnas

| Columna | Contenido |
|---|---|
| Fecha | día calendario |
| 1ª entrada | hora del primer marcaje del día, `—` si no hay |
| Última salida | hora del último marcaje, `—` si hay 0 o 1 marcaje |
| Permanencia | último − primer marcaje |
| Efectivo | suma de tramos por posición |
| Marc. | cantidad de marcajes del día |
| Estado | badge, ver más abajo |

Se eliminan `Hora` (suelta), `Dato crudo` y `Fuente`. Siguen disponibles en el
popup.

## Cálculo de tiempos

Siempre **por posición**, ignorando el campo `tipo`, que es justamente el dato
poco confiable. Sobre los marcajes del día ordenados por hora:

- `permanencia = marcajes[-1] - marcajes[0]`, `None` si hay menos de 2
- `efectivo = Σ (marcajes[2k+1] - marcajes[2k])` para cada par completo;
  un marcaje impar sobrante se ignora
- con 2 marcajes ambos valores coinciden
- con 0 o 1 marcaje ambos son `None` y se muestran `—`

Decisión tomada: un día con secuencia inválida **sí** muestra tiempos
calculados por posición. El Estado avisa de que el dato es sospechoso; se
prefiere un número señalado a una celda vacía.

Formato de salida: `7h 17m`. Los segundos se truncan, no se redondean.

## Estados

Se evalúa la secuencia de `tipo_norm` del día, ordenada por hora:

| Estado | Condición | Color |
|---|---|---|
| `ok` | cantidad par ≥ 2 y alterna entrada→salida desde el primero | verde |
| `sin_marcaciones` | 0 marcajes | gris |
| `impar` | cantidad impar (1, 3, …) | ámbar |
| `dos_entradas` | dos `entrada` consecutivas | ámbar |
| `dos_salidas` | dos `salida` consecutivas | ámbar |
| `empieza_salida` | el primer marcaje del día es `salida` | ámbar |
| `tipo_desconocido` | algún marcaje normaliza a `otro` | ámbar |

Cada estado viaja con un `mensaje` legible que incluye la hora del conflicto
(ej. `"Dos salidas seguidas a las 14:31:23"`). Cuando concurren varios
problemas se reporta uno solo, en este orden de prioridad:

`sin_marcaciones` → `tipo_desconocido` → `dos_entradas` / `dos_salidas` →
`empieza_salida` → `impar` → `ok`

Los duplicados consecutivos van antes que `empieza_salida` porque son el
diagnóstico más accionable: el día 07-24 del ejemplo cumple ambas condiciones
y lo útil es leer "dos salidas seguidas".

`sin_marcaciones` no es un error: es un día del rango sin actividad (fin de
semana, feriado, ausencia). Se muestra en gris, sin ícono de advertencia.

## Días vacíos

Todos los días del rango aparecen, incluidos los que no tienen ningún marcaje.
Decisión tomada: hace visibles las ausencias, a costa de mostrar también
sábados y domingos. El sistema hoy no conoce el calendario laboral de cada
persona, así que no puede distinguir un domingo de una falta.

## Popup

Clic en cualquier fila → modal con los marcajes de ese día: hora, tipo
normalizado y dato crudo. El par en conflicto se resalta en rojo.

Los marcajes ya vienen embebidos en la respuesta que arma la tabla, así que el
modal no dispara ningún request. Costo: un rango de 366 días con 4 marcajes
diarios son ~1500 objetos pequeños, del orden de 100 KB de JSON.

## Arquitectura

```
templates/analytics_entradas_salidas.html   tabla diaria + modal
        │ GET /api/analytics/entradas-salidas/resumen-diario
app/web/analytics_bp.py                     RBAC, parseo de params
        │
app/domain/analytics_entradas_salidas.py    consultar_resumen_diario()
        │                                   valida, agrupa, pagina por día
        ├── app/domain/asistencia_dia.py    ← MÓDULO NUEVO, PURO
        │                                   resumir_dia(), resumir_rango()
        └── db/queries/asistencias_entradas_salidas.py
                                            listar_marcaciones_rango()
```

### `app/domain/asistencia_dia.py` (nuevo)

Módulo puro: sin Flask, sin base de datos, sin `datetime.now()`. Toda la
lógica de cálculo y validación vive acá, que es lo único delicado del cambio.

- `resumir_dia(fecha, marcaciones) -> dict` — una fila
- `resumir_rango(fecha_inicio, fecha_fin, marcaciones) -> list[dict]` — agrupa
  por fecha y rellena los días sin marcajes
- `formatear_duracion(segundos) -> str` — `"7h 17m"`

Se testea exhaustivamente sin levantar nada.

### `db/queries/asistencias_entradas_salidas.py`

Se agrega `listar_marcaciones_rango(persona_id, fecha_inicio, fecha_fin, schema)`:
mismo SQL que `listar_marcaciones_por_persona` pero sin `LIMIT/OFFSET`, porque
para agrupar por día hacen falta todos los marcajes del rango. El volumen está
acotado por la validación de 366 días que ya existe.

### `app/domain/analytics_entradas_salidas.py`

Se agrega `consultar_resumen_diario(...)`, que reusa las validaciones actuales
(UUID, orden de fechas, tope de 366 días) y pagina **por día**, 31 por página.

`consultar_entradas_salidas()` queda intacta: el endpoint de marcaciones crudas
sigue existiendo.

### `app/web/analytics_bp.py`

Endpoint nuevo `GET /api/analytics/entradas-salidas/resumen-diario`, con el
mismo `@require_role` que el actual.

## Supuesto explícito

El agrupamiento es por **fecha calendario**. Un turno nocturno (entra 22:00,
sale 06:00) queda partido en dos días y ambos se marcan `impar`. Con el horario
observado (07:00–14:30) no aplica. Si aparecen guardias nocturnas, el
agrupamiento debe cambiar a "jornada", y eso es otro diseño.

## Errores

- rango inválido o `persona_id` no-UUID → 400 con mensaje, igual que hoy
- persona sin marcajes en el rango → tabla completa de días `sin_marcaciones`
- marcajes con `tipo` fuera del mapeo → estado `tipo_desconocido`, nunca
  excepción

## Testing

TDD sobre `asistencia_dia.py`, que es donde está el riesgo:

- 0, 1, 2, 3, 4, 6 marcajes
- dos entradas seguidas / dos salidas seguidas
- día que empieza con salida
- `tipo` desconocido
- efectivo con 4 marcajes ≠ permanencia (el caso del almuerzo)
- efectivo con 2 marcajes == permanencia
- relleno de días vacíos en los bordes del rango y en el medio
- formateo de duración: 0, < 1h, exactamente 1h, > 24h

Más un test de integración del endpoint nuevo (forma del JSON y RBAC).
