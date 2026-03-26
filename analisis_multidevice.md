# Análisis: Multi-dispositivo — Duplicación de Personas y Capacidad

**Fecha:** 2026-03-26
**Contexto:** La institución usa 3 biométricos en paralelo para marcación de practicantes. Un mismo practicante puede marcar en cualquiera de los 3. Al sincronizar los 3 dispositivos, el sistema crea personas duplicadas.

---

## 1. Por qué se duplican las personas

### El mecanismo actual

Cuando se sincroniza un dispositivo, el sistema llama `upsert_usuarios()` → `resolver_persona_id()`. Esta función busca si ya existe una persona vinculada al par `(dispositivo_id, id_en_dispositivo)` en la tabla `personas_dispositivos`.

Si **no** encuentra ese par exacto → **crea una persona nueva**.

El problema es que la búsqueda es **estrictamente por dispositivo**:

```
Dispositivo A, id_usuario=5, nombre="Juan Pérez"  → Persona UUID-001
Dispositivo B, id_usuario=5, nombre="Juan Pérez"  → Persona UUID-002  ← DUPLICADO
Dispositivo C, id_usuario=5, nombre="Juan Pérez"  → Persona UUID-003  ← DUPLICADO
```

### Por qué el nombre no ayuda

La tabla `personas` no tiene índice UNIQUE sobre `nombre`. Dos personas pueden tener el mismo nombre. Esto es intencional (puede haber dos Juan Pérez reales), pero en este caso es contraproducente.

### El índice único NO previene el problema

La tabla `personas_dispositivos` tiene:

```sql
UNIQUE (dispositivo_id, id_en_dispositivo)
```

Esto solo garantiza que el mismo ID no aparezca **dos veces en el mismo dispositivo**. No tiene ninguna restricción entre dispositivos distintos.

### El caso del nombre sin ID

El usuario menciona personas "sin id pero con el mismo nombre". Esto ocurre probablemente con usuarios ZK que tienen `id_usuario` vacío o "0". En ese caso, el sistema los distingue únicamente por dispositivo, generando aún más duplicados sin identificador real.

### Impacto en asistencias

La tabla `asistencias` tiene:

```sql
UNIQUE (persona_id, fecha_hora)
```

Si Juan Pérez es UUID-001 en dispositivo A y UUID-002 en dispositivo B, y marca a las 09:00, se insertan **dos registros de asistencia distintos** (uno por cada persona duplicada). El UNIQUE no los detecta como duplicados porque son personas diferentes. El informe de asistencia entonces muestra a "Juan Pérez" múltiples veces.

---

## 2. Cómo se puede corregir

### Opción A — Vincular personas duplicadas (solución manual, viable ahora)

La arquitectura ya soporta esto. La tabla `personas_dispositivos` permite que **una sola persona** tenga múltiples registros en distintos dispositivos:

```
Persona UUID-001 "Juan Pérez"
  ├── Dispositivo A, id_en_dispositivo=5
  ├── Dispositivo B, id_en_dispositivo=5
  └── Dispositivo C, id_en_dispositivo=5
```

La función `_upsert_zk_id()` ya existe y permite reasignar un par `(dispositivo, id)` a una persona diferente. El flujo manual sería:

1. Identificar grupos de personas duplicadas (mismo nombre, distintos dispositivos).
2. Elegir cuál es la persona "canónica" (la que tiene el historial más completo).
3. Reasignar los vínculos de los duplicados hacia la canónica usando `_upsert_zk_id()`.
4. Eliminar las personas huérfanas (sin vínculos activos).
5. Las asistencias de los duplicados se re-atribuyen automáticamente al migrar `persona_id`.

Esta opción requiere una pantalla de gestión (similar a la de "vincular usuario ZK a persona" que ya existe) pero orientada a unificar duplicados.

### Opción B — Cambiar la lógica de `resolver_persona_id` (corrección automática)

En lugar de crear una persona nueva cuando no hay vínculo en `personas_dispositivos`, la función podría primero **buscar por nombre exacto** entre las personas ya existentes antes de crear una nueva. Si encuentra un match único por nombre → la vincula automáticamente al nuevo dispositivo en vez de crear un duplicado.

**Riesgo**: Si hay dos personas reales con el mismo nombre, se vincularían incorrectamente. Requeriría un umbral de confianza o confirmación manual.

### Opción C — Deduplicación por `id_usuario` entre dispositivos (más robusta)

Si el mismo ID de usuario ZK (`id_usuario=5`) aparece en múltiples dispositivos, es razonable asumir que es la misma persona biométrica (los ZK sincronizan usuarios entre sí en muchas instalaciones). Se podría buscar primero en `personas_dispositivos` por `id_en_dispositivo=5` **sin filtrar por dispositivo**, y si hay un único resultado, vincularlo en lugar de crear persona nueva.

**Riesgo**: Si los dispositivos son completamente independientes (IDs distintos para personas distintas), esto causaría fusiones incorrectas. Hay que conocer si en la institución los 3 ZK están sincronizados entre sí.

---

## 3. Situación de capacidad de dispositivos

### Qué existe actualmente

El método `get_capacidad()` existe en `ZKDriver`. Descarga todos los registros del dispositivo y cuenta cuántos hay, comparándolos contra `ZK_CAPACIDAD_MAX` (variable de entorno, default 100.000).

**El problema**: esta operación requiere conectarse al dispositivo y descargar el log completo — es costosa. No se consulta de forma independiente; se ejecuta **durante cada sincronización** y el resultado se guarda en la columna `registros_en_dispositivo` de la tabla `sync_log`.

### Por qué solo se ve la capacidad de un dispositivo

La ruta `GET /api/estado-sync` lee `get_estado()` que obtiene el **último registro general de `sync_log`**, sin distinguir por dispositivo. Usa `ZK_CAPACIDAD_MAX` del `.env`, que es la variable "quemada" para el primer dispositivo.

Los nuevos dispositivos sincronizados también guardan su conteo en `sync_log` con su propio `dispositivo_id`, pero **no hay ninguna ruta que los exponga por separado**.

### Qué hace falta

1. Una ruta que consulte el **último `sync_log` por dispositivo** y devuelva `registros_en_dispositivo` para cada uno.
2. Mostrar ese dato en la tabla de dispositivos de la UI, junto con el porcentaje de ocupación.
3. Eliminar la dependencia de `ZK_CAPACIDAD_MAX` del `.env` como valor global; idealmente la capacidad máxima debería ser un atributo del dispositivo o al menos configurable por driver.

### Capacidad de HikvisionDriver

El driver Hikvision implementa `get_capacidad()` devolviendo siempre `{"total_registros": 0, "capacidad_max": 100000}` — **no está implementado**. Si se agregan dispositivos Hikvision, la capacidad siempre aparecerá en 0.

---

## 4. Orden de acción sugerido

| Prioridad | Acción | Complejidad |
|-----------|--------|-------------|
| 1 | Identificar duplicados existentes con una consulta SQL (personas con mismo nombre, distintos dispositivos) | Baja |
| 2 | Decidir si los 3 ZK están sincronizados entre sí (mismo `id_usuario` = misma persona) | Operativa |
| 3 | Implementar UI de "unificar personas duplicadas" para corrección manual de lo ya ingresado | Media |
| 4 | Corregir `resolver_persona_id` para que busque por `id_usuario` cross-dispositivo antes de crear nuevo | Media |
| 5 | Agregar columna de capacidad por dispositivo en la tabla de la UI, leyendo el último `sync_log` | Baja-Media |
| 6 | Mover `capacidad_max` del `.env` global a un atributo por dispositivo en la tabla `dispositivos` | Baja |

---

## 5. Pregunta clave antes de proceder

**¿Los 3 biométricos ZK están sincronizados entre sí?**

- Si **SÍ** (mismos IDs de usuario en los 3): la opción C es la más limpia y automatizable.
- Si **NO** (cada ZK tiene sus propios IDs): hay que ir por la opción A (vinculación manual) o B (matching por nombre con confirmación).

Esta respuesta define la estrategia de corrección correcta.
