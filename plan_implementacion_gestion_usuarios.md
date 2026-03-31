# Plan de Implementación: Gestión de Usuarios en Dispositivos Biométricos

> Referencia de análisis: `analisis_gestion_usuarios_biometrico.md`

---

## Visión general

Implementar la gestión completa del ciclo de vida de usuarios en dispositivos biométricos ZKTeco desde la plataforma, incluyendo: altas, bajas lógicas, detección y corrección de inconsistencias de uid, y replicación de templates entre dispositivos.

---

## Fase 1 — Fundamentos de BD y driver

**Objetivo:** tener la capa de datos lista para soportar todas las operaciones posteriores. Sin esta fase, nada de lo demás es posible.

### 1.1 Migración de schema

Nueva migración Alembic (`0009_gestion_usuarios_biometrico`):

- `usuarios_zk`: agregar columna `uid INTEGER` (uid interno del dispositivo)
- `usuarios_zk`: agregar columna `activo BOOLEAN NOT NULL DEFAULT true`
- `personas_dispositivos`: agregar columna `uid_dispositivo INTEGER`
- `personas_dispositivos`: agregar columna `uid_inconsistente BOOLEAN NOT NULL DEFAULT false`
- Nueva tabla `huellas_personas`:
  - `id UUID PRIMARY KEY`
  - `persona_id UUID REFERENCES personas(id)`
  - `dispositivo_id UUID REFERENCES dispositivos(id)`
  - `fid INTEGER` — índice del dedo (0-9)
  - `template_hex TEXT` — template serializado
  - `sincronizado_en TIMESTAMPTZ`
  - `UNIQUE (persona_id, dispositivo_id, fid)`

### 1.2 Actualizar `upsert_usuarios` en `db/queries/personas.py`

- Guardar el campo `uid` (interno del dispositivo) que viene del driver en `usuarios_zk.uid` y en `personas_dispositivos.uid_dispositivo`
- Agregar lógica de detección de inconsistencia: si el uid que reporta el dispositivo difiere del `uid_dispositivo` guardado en BD para ese `user_id`, marcar `uid_inconsistente = true`
- Garantizar que el sync **no modifique** `personas.activo` ni `personas_dispositivos.activo` — esos flags solo los controla la plataforma

### 1.3 Actualizar `get_usuarios` en `ZKDriver`

- El método ya retorna `id_usuario` y `nombre`. Agregar `uid` (el `u.uid` del objeto `User` de pyzk) al dict retornado:
  ```
  {"id_usuario": str(u.user_id), "nombre": ..., "privilegio": ..., "uid": u.uid}
  ```

### 1.4 Nuevos métodos en `ZKDriver`

Agregar los siguientes métodos al driver ZK (y declararlos como `NotImplementedError` en `BiometricDriver` base):

- `crear_usuario(uid, user_id, nombre, privilegio, password, card)` → wrappea `set_user`
- `eliminar_usuario(uid)` → wrappea `delete_user`
- `get_uid_por_user_id(user_id)` → busca en `get_users()` y retorna el uid del dispositivo para ese user_id lógico
- `get_next_uid_libre()` → retorna `next_uid` del dispositivo después de conectar
- `get_templates_usuario(uid)` → lista de `Finger` para ese uid
- `replicar_template(finger_origen, uid_destino)` → escribe el template con el uid del dispositivo destino
- `eliminar_templates_usuario(uid)` → borra todos los fid de un usuario antes de replicar

### 1.5 Nuevas funciones en `db/queries/personas.py`

- `get_uid_dispositivo(persona_id, dispositivo_id)` → retorna el `uid_dispositivo` guardado en `personas_dispositivos`
- `get_personas_con_uid_inconsistente()` → lista de personas con `uid_inconsistente = true`
- `marcar_uid_inconsistente(persona_id, dispositivo_id, inconsistente: bool)`
- `actualizar_uid_dispositivo(persona_id, dispositivo_id, uid)`
- `dar_de_baja_persona(persona_id, dispositivo_id)` → pone `activo = false` en `personas` y `personas_dispositivos`
- `upsert_template(persona_id, dispositivo_id, fid, template_hex)`
- `get_templates_persona(persona_id)` → todos los templates guardados para una persona

---

## Fase 2 — Lógica de negocio en `sync.py`

**Objetivo:** extender el sync para capturar templates y detectar inconsistencias automáticamente.

### 2.1 Captura de templates durante el sync

En `sincronizar_dispositivo`, después del paso de obtener usuarios:

```
1. get_templates() del dispositivo
2. Para cada template:
   a. Resolver persona_id desde uid/user_id
   b. Comparar con huellas_personas en BD
   c. Si es nuevo o difiere → upsert_template en BD
```

Este paso es opcional en la primera iteración — puede activarse por config por tenant.

### 2.2 Replicación automática de templates nuevos

Después de guardar un template nuevo en BD, verificar si la persona tiene vínculo activo en otros dispositivos del tenant:

```
Para cada dispositivo activo del tenant (excepto el origen):
  1. Verificar conexión
  2. get_uid_dispositivo(persona_id, dispositivo_destino)
  3. replicar_template(finger, uid_destino)
  4. Actualizar huellas_personas con dispositivo_destino
```

Este comportamiento debe ser configurable por tenant (puede no querer replicación automática).

---

## Fase 3 — Backend: rutas en `app.py`

**Objetivo:** exponer la gestión de usuarios vía API REST. Todas las rutas requieren `@require_role(...)`.

### Rutas de usuarios por dispositivo

| Método | Ruta | Acción |
|--------|------|--------|
| `GET` | `/dispositivos/<id>/usuarios` | Listar usuarios del dispositivo con estado |
| `POST` | `/dispositivos/<id>/usuarios` | Crear usuario individual en el dispositivo |
| `POST` | `/dispositivos/<id>/usuarios/carga-masiva` | Crear usuarios en lote desde CSV |
| `GET` | `/dispositivos/<id>/usuarios/carga-masiva/plantilla` | Descargar plantilla CSV de ejemplo |
| `DELETE` | `/dispositivos/<id>/usuarios/<uid>` | Dar de baja (baja lógica en BD + delete en device) |

### Rutas de validación

| Método | Ruta | Acción |
|--------|------|--------|
| `GET` | `/dispositivos/<id>/usuarios/next-uid` | Sugerir el próximo uid libre entre todos los dispositivos del tenant |
| `GET` | `/dispositivos/<id>/usuarios/validar-uid/<uid>` | Verificar si un uid está libre en todos los dispositivos del tenant |
| `POST` | `/dispositivos/<id>/usuarios/validar-csv` | Validar un CSV sin crear — retorna reporte de errores y conflictos |

### Rutas de inconsistencias

| Método | Ruta | Acción |
|--------|------|--------|
| `GET` | `/personas/uid-inconsistentes` | Listar personas con uid inconsistente entre dispositivos |
| `POST` | `/personas/<persona_id>/corregir-uid` | Aplicar corrección de uid en el dispositivo afectado |

### Rutas de templates

| Método | Ruta | Acción |
|--------|------|--------|
| `GET` | `/personas/<persona_id>/huellas` | Ver en qué dispositivos tiene template registrado |
| `POST` | `/personas/<persona_id>/huellas/replicar` | Replicar templates desde un dispositivo origen a otros |

### Lógica de `POST /dispositivos/<id>/usuarios`

```
1. Recibir: nombre, user_id, uid (opcional), privilegio, password (opcional)
2. Si uid no viene → GET /next-uid para sugerir
3. Validar uid en todos los dispositivos del tenant
4. Si uid ocupado → 409 Conflict con detalle de quién lo usa
5. set_user en cada dispositivo especificado
6. Guardar en BD: personas, personas_dispositivos (con uid_dispositivo), usuarios_zk
7. Retornar el usuario creado con los uid asignados por dispositivo
```

### Lógica de `POST /dispositivos/<id>/usuarios/carga-masiva`

El endpoint recibe un archivo CSV y un listado de dispositivos destino. Opera en dos etapas: validación primero, creación después.

**Etapa 1 — Validación completa del CSV (sin tocar dispositivos ni BD):**

```
1. Parsear el CSV fila por fila
2. Para cada fila validar:
   a. Campos obligatorios presentes (nombre, user_id)
   b. Formato de uid correcto (entero positivo) si se especifica
   c. user_id no duplicado dentro del mismo CSV
   d. user_id no existente ya en BD (conflicto con usuario previo)
   e. uid no duplicado dentro del mismo CSV
   f. uid no ocupado en ningún dispositivo del tenant (igual que creación individual)
3. Construir reporte de validación:
   - Filas válidas: lista con los datos a crear
   - Filas con error: número de fila, nombre, user_id, uid, descripción del error
   - Filas con uid en conflicto: informar qué usuario ya usa ese uid y en qué dispositivo
4. Si hay cualquier error → NO crear nada, retornar reporte completo al operador
```

**Etapa 2 — Creación (solo si la validación fue 100% exitosa):**

```
Para cada fila del CSV:
  1. Si uid no especificado → calcular next_uid_seguro entre todos los dispositivos
  2. set_user en cada dispositivo destino seleccionado
  3. Guardar en BD: personas, personas_dispositivos, usuarios_zk
  4. Registrar resultado por fila: creado / fallido (con motivo)
5. Retornar resumen: X creados, Y fallidos, detalle por fila
```

**Si falla la creación de alguna fila:** continuar con las demás y reportar los fallos al final. No se hace rollback — cada fila es independiente. El operador puede corregir y reintentar solo las fallidas.

**Formato esperado del CSV:**

```
nombre,user_id,uid,privilegio,password,dispositivos
Juan Pérez,1043,5,0,,
María García,1044,,0,,
Carlos López,1045,8,14,1234,
```

- `nombre` — obligatorio
- `user_id` — obligatorio, único en el tenant
- `uid` — opcional; si vacío, la plataforma sugiere el próximo libre
- `privilegio` — opcional, default `0` (usuario normal)
- `password` — opcional, PIN numérico
- `dispositivos` — opcional; si vacío, se aplica a todos los dispositivos del tenant. Si se especifica, IDs o nombres separados por punto y coma

**Plantilla CSV descargable** (`GET /dispositivos/<id>/usuarios/carga-masiva/plantilla`):
Retorna un CSV con la cabecera correcta, una fila de ejemplo comentada y el próximo uid sugerido precargado como referencia.

### Lógica de `POST /dispositivos/<id>/usuarios/validar-csv`

Ejecuta solo la Etapa 1 descripta arriba sin crear nada. Útil para que el operador valide el archivo antes de confirmar la carga. Retorna el reporte completo con:

- Total de filas
- Filas válidas (count + lista)
- Filas con error (count + detalle por fila)
- Filas con uid en conflicto (count + detalle: quién usa ese uid y en qué dispositivo)
- uids que serán auto-asignados (filas sin uid especificado) con el valor sugerido

### Lógica de `DELETE /dispositivos/<id>/usuarios/<uid>`

```
1. Verificar conexión con dispositivo
2. delete_user(uid) en el dispositivo
3. Solo si el delete fue exitoso:
   a. personas_dispositivos.activo = false
   b. personas.activo = false (si no tiene vínculos activos en otros dispositivos)
4. Si falla la conexión → 503 con mensaje explicativo (no modificar BD)
```

---

## Fase 4 — Frontend: UI de gestión

**Objetivo:** interfaz para que el operador pueda gestionar usuarios sin tocar directamente el dispositivo.

### 4.1 Sección de usuarios por dispositivo

Dentro de la vista de detalle del dispositivo (`admin/dispositivos`), agregar tab o sección **"Usuarios"**:

- Tabla con columnas: ID lógico, Nombre, Privilegio, uid interno, Huellas registradas (cantidad de fid), Estado (activo/inactivo)
- Filtro por estado activo/inactivo
- Botón **"Agregar usuario"**
- Botón **"Dar de baja"** por fila (con confirmación)
- Indicador visual (badge) para uids inconsistentes

### 4.2 Modal de creación de usuario individual

Campos:
- Nombre
- ID lógico (user_id)
- uid — campo editable con botón "Sugerir" que llama a `/next-uid`
- Privilegio (select: Normal / Administrador)
- Contraseña PIN (opcional)
- Selección de dispositivos donde crearlo (checkboxes con los dispositivos activos del tenant)

Comportamiento:
- Al escribir un uid manualmente → llamar a `/validar-uid/<uid>` en tiempo real
- Si uid ocupado → mostrar alerta inline con el nombre del usuario que lo usa y en qué dispositivo
- Botón "Crear" deshabilitado mientras el uid tenga conflicto

### 4.2b Panel de carga masiva por CSV

Accesible desde la misma sección de usuarios, como tab o botón alternativo al modal individual.

**Paso 1 — Selección y prevalidación:**
- Botón para subir o arrastrar el archivo CSV
- Botón **"Descargar plantilla"** que descarga el CSV de ejemplo con cabeceras correctas
- Selector de dispositivos destino (checkboxes, igual que en creación individual)
- Al seleccionar el archivo → llamar automáticamente a `/validar-csv` y mostrar el resultado antes de que el operador confirme

**Paso 2 — Reporte de validación (antes de crear):**

Mostrar una tabla con todas las filas del CSV y su estado:

| Fila | Nombre | user_id | uid | Estado | Detalle |
|------|--------|---------|-----|--------|---------|
| 1 | Juan Pérez | 1043 | 5 | ✅ Válido | uid auto-sugerido: 12 |
| 2 | María García | 1044 | 7 | ❌ uid en uso | uid 7 usado por Carlos López en Dispositivo A |
| 3 | Carlos López | 1045 | — | ✅ Válido | uid auto-sugerido: 13 |
| 4 | Ana Ruiz | 1043 | 9 | ❌ user_id duplicado | user_id 1043 ya existe en el sistema |

- Si hay errores → botón "Crear" deshabilitado. El operador debe corregir el CSV y volver a subir.
- Si todo válido → botón **"Confirmar carga"** habilitado con el count de usuarios a crear.

**Paso 3 — Resultado de la carga:**

Después de confirmar, mostrar progreso fila por fila (o resumen final):
- X usuarios creados correctamente
- Y usuarios fallidos (con motivo por fila)
- Opción de descargar un CSV de resultados con una columna adicional `resultado` para auditoría

### 4.3 Sección de alertas: uids inconsistentes

Panel separado (o badge en el menú) que muestra personas con `uid_inconsistente = true`:

- Tabla: Nombre, user_id, uid en dispositivo A, uid en dispositivo B, acción
- Botón **"Corregir"** → modal que muestra los uids actuales y permite elegir cuál es el correcto
- Confirmación explícita antes de ejecutar la corrección

### 4.4 Sección de huellas por persona

Dentro del perfil de cada persona (vista `personas/detalle`):

- Lista de dispositivos con estado de huella: "Registrada", "Sin huella", "Inconsistente"
- Botón **"Replicar"** → seleccionar dispositivo origen y destinos
- Aviso: la persona debe enrolarse físicamente en el dispositivo si no tiene huella aún

---

## Fase 5 — Corrección de `resolver_persona_id`

**Objetivo:** evitar duplicados cuando llega una marcación de un usuario con `personas_dispositivos.activo = false`.

Modificar la query en `resolver_persona_id` para:
- Primero buscar con `activo = true` (comportamiento actual)
- Si no encuentra, buscar con `activo = false` — si existe, retornar la persona existente sin crear una nueva y registrar un warning en log
- Solo crear persona nueva si definitivamente no existe ningún registro (ni activo ni inactivo)

---

## Orden de implementación recomendado

```
Fase 1.1 → Fase 1.3 → Fase 1.2 → Fase 1.4 → Fase 1.5
   ↓
Fase 3 (rutas básicas: crear individual, validar-uid, next-uid, dar de baja)
   ↓
Fase 4.1 + 4.2 (UI: listar usuarios + modal creación individual)
   ↓
Fase 3 (rutas carga masiva: validar-csv, carga-masiva, plantilla)
   ↓
Fase 4.2b (UI: panel carga masiva con prevalidación)
   ↓
Fase 4.3 (UI de alertas de inconsistencia)
   ↓
Fase 3 (rutas de inconsistencia y corrección)
   ↓
Fase 5 (fix resolver_persona_id)
   ↓
Fase 2.1 (captura de templates en sync)
   ↓
Fase 3 + 4.4 (rutas y UI de huellas/replicación)
   ↓
Fase 2.2 (replicación automática en sync)
```

---

## Decisiones pendientes antes de implementar

| Decisión | Opciones | Impacto |
|----------|---------|---------|
| ¿La baja requiere conexión obligatoria al device? | Sí (recomendado) / No (solo BD) | Si no, puede quedar usuario activo en device sin saberlo |
| ¿El sync captura templates siempre o por config de tenant? | Siempre / Config por tenant | Performance del sync — los templates son pesados |
| ¿La replicación de templates es automática o manual? | Automática en sync / Solo manual desde UI | Complejidad del sync vs control del operador |
| ¿Qué pasa si crear en uno de N dispositivos falla? | Rollback total / Crear en los que se pudo | Consistencia vs tolerancia a fallos |
| ¿El operador elige en cuáles dispositivos crear el usuario? | Sí (checkboxes) / En todos siempre | Flexibilidad operativa |
| ¿La carga masiva se bloquea ante cualquier error o crea las filas válidas? | Bloqueo total (recomendado) / Parcial | Bloqueo total obliga a un CSV limpio; parcial puede generar cargas incompletas difíciles de auditar |
| ¿El CSV de resultados se guarda en servidor para descarga posterior? | Sí / Solo en respuesta inmediata | Si la carga es grande y el usuario cierra la ventana, ¿pierde el reporte? |

---

## Riesgos identificados

| Riesgo | Mitigación |
|--------|-----------|
| Enrolado manual en panel físico rompe consistencia de uid | Detección en sync + alerta en UI (Fase 1.2 + 4.3) |
| Template de A no compatible con firmware de B | Validar modelos antes de replicar; loguear errores sin romper sync |
| Tenant uid-auto: next_uid calculado puede estar desactualizado si otro proceso crea un usuario | Recalcular next_uid justo antes de crear, dentro de una operación atómica |
| Baja exitosa en BD pero falla en device (pérdida de conexión posterior al delete) | Registrar el uid en un log de "pendiente de baja" para reintento |
| CSV con uids mezclados (algunos especificados, otros vacíos) y cálculo de next_uid concurrente | Calcular todos los uids auto-asignados al inicio de la validación, reservarlos, y no recalcular por fila — evita que dos filas sin uid reciban el mismo valor sugerido |
