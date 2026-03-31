# Análisis: Gestión de Usuarios en Dispositivos Biométricos

## Contexto del sistema

El sistema actual maneja múltiples tenants con dispositivos ZKTeco. La plataforma se comunica con los dispositivos vía `pyzk` (modelo pull: el servidor consulta al dispositivo). La BD actúa como registro maestro y los dispositivos como puntos de captura.

---

## Estado actual de la gestión de usuarios

### Lo que ya existe

La plataforma actualmente **lee** usuarios del dispositivo durante el sync, pero no **escribe** hacia él. El flujo actual es:

```
Dispositivo → get_users() → upsert_usuarios() → BD
```

No existe ningún mecanismo para crear, modificar ni eliminar usuarios en el dispositivo desde la plataforma.

### Tablas involucradas

**`usuarios_zk`** — espejo del dispositivo:
- `id_usuario TEXT` — user_id lógico (ej. número de legajo)
- `nombre TEXT`
- `privilegio INTEGER`
- `actualizado_en TIMESTAMPTZ`
- ⚠️ **No tiene** `uid` interno del dispositivo
- ⚠️ **No tiene** columna `activo`

**`personas`** — registro maestro:
- Ya tiene `activo BOOLEAN DEFAULT true` ✅

**`personas_dispositivos`** — vinculación persona ↔ dispositivo:
- Ya tiene `activo BOOLEAN DEFAULT true` ✅
- Ya tiene `id_en_dispositivo TEXT` (el user_id lógico) ✅
- ⚠️ **No tiene** `uid_dispositivo` (uid interno del device)
- ⚠️ **No tiene** `uid_inconsistente` (flag de alerta)

---

## Modelo de bajas (activo/inactivo)

### Decisión de diseño

La BD es la fuente de verdad. Un usuario dado de baja en el dispositivo **no se elimina de la BD** — se marca `activo = false`. Su historial de marcaciones se conserva intacto.

### Flujo de baja

```
Operador da de baja al usuario desde la plataforma
         ↓
Plataforma verifica conexión con el dispositivo
         ↓
delete_user(uid) en el dispositivo   ← requiere uid guardado en BD
         ↓ (solo si la operación en el device fue exitosa)
personas.activo = false
personas_dispositivos.activo = false
         ↓
Historial en asistencias → intacto
```

**Regla clave:** si la operación en el dispositivo falla (sin conexión), no se cambia el estado en BD. Se requiere conexión exitosa para garantizar consistencia.

### Impacto en el sync

`upsert_usuarios` actualmente sobreescribe datos sin verificar el estado `activo`. Hay que asegurar que el sync **nunca reactive** un usuario marcado como inactivo. La regla es: el flag `activo` solo lo controla la plataforma, nunca el sync automático.

### Impacto en los informes

El filtro actual de personas por período ya funciona por marcaciones existentes, no por el flag `activo`. Esto es correcto: un empleado que se fue en febrero sigue apareciendo en el informe de enero (tiene marcaciones), pero no en el de marzo (no tiene marcaciones). No hay cambios necesarios en `script.py`.

Un caso edge: `resolver_persona_id` filtra `pd.activo = true`, lo que significa que si se desactiva el vínculo en `personas_dispositivos` y luego llega una marcación de ese usuario, la función no encontraría la persona y crearía una nueva duplicada. Este comportamiento debe revisarse para distinguir entre "no existe" y "existe pero inactivo".

---

## Creación de usuarios

### Lo que hace pyzk (`set_user`)

Escribe un usuario directamente en la memoria del dispositivo vía protocolo ZK. Parámetros relevantes:

- `uid` — identificador interno del dispositivo (autoincremental si no se especifica)
- `user_id` — identificador lógico controlado por la plataforma (ej. legajo o cédula)
- `name` — nombre del empleado
- `privilege` — `0` = usuario normal, `14` = administrador
- `password` — PIN numérico opcional
- `card` — número de tarjeta RFID (si el dispositivo lo soporta)

### Dos tipos de tenant

El sistema tiene tenants con comportamientos distintos respecto al uid:

| Tipo | Cómo se asigna el uid | Implicación |
|------|-----------------------|-------------|
| uid preestablecido | El listado central define el uid antes de crear el usuario | uid es el mismo en todos los dispositivos por diseño |
| uid auto-generado | El dispositivo asigna el próximo uid libre (`next_uid`) | uid puede diferir entre dispositivos para el mismo usuario |

### Problema del uid en multi-dispositivo (tenant auto)

Cada dispositivo mantiene su propio `next_uid` interno:

```
Dispositivo A: usuarios 1-8  → next_uid = 9
Dispositivo B: usuarios 1-6  → next_uid = 7
Dispositivo C: usuarios 1-11 → next_uid = 12
```

Si la plataforma usa el `next_uid` de A (9), ese uid puede estar ocupado en C. El uid "seguro" es el **máximo de todos los `next_uid`** entre todos los dispositivos del tenant — en este ejemplo, 12.

### Validación antes de crear

Antes de ejecutar `set_user`, la plataforma debe verificar que el uid propuesto esté libre en **todos** los dispositivos activos del tenant:

```
uid especificado por operador
         ↓
Consultar todos los dispositivos del tenant
         ├─ uid libre en todos → proceder
         └─ uid ocupado en alguno → BLOQUEAR
               Informar: "uid 5 ya está en uso por [nombre] en [dispositivo]"
               Operador modifica uid manualmente → reintenta
```

Si el operador no especifica uid, la plataforma sugiere el máximo `next_uid` calculado entre todos los dispositivos.

### Flujo completo de alta

```
1. Operador ingresa nombre, user_id, uid (o solicita auto-sugerido)
2. Plataforma valida uid en todos los dispositivos del tenant
3. set_user(uid, name, privilege, user_id) en cada dispositivo especificado
4. Guardar uid real asignado en personas_dispositivos.uid_dispositivo
5. Empleado va físicamente al dispositivo y enrola su huella desde el menú
6. En el próximo sync, el template queda disponible en BD (si se implementa)
```

---

## uid interno vs user_id lógico

Esta distinción es crítica para todas las operaciones de escritura:

| Campo | Qué es | Dónde vive | Para qué se usa |
|-------|--------|------------|-----------------|
| `uid` | Identificador interno del dispositivo, autoincremental | Solo en el dispositivo y en `personas_dispositivos.uid_dispositivo` | `delete_user`, `get_user_template`, `save_user_template`, `enroll_user` |
| `user_id` | Identificador lógico controlado por la plataforma | BD + dispositivo | Búsquedas, vinculación entre dispositivos, informes |

**Regla:** para operaciones de escritura en el dispositivo siempre se necesita el `uid` interno. Para lógica de negocio y vinculación entre dispositivos, siempre se usa el `user_id` lógico.

---

## Detección y corrección de inconsistencias de uid

### Cuándo ocurre

Cuando alguien enrola un usuario directamente desde el panel físico del dispositivo (sin pasar por la plataforma), el dispositivo asigna su propio `next_uid`. Si ese mismo usuario fue creado con un uid diferente en otro dispositivo, queda una inconsistencia silenciosa.

### Detección durante el sync

El sync puede detectar esto al comparar el uid reportado por el dispositivo con el `uid_dispositivo` guardado en BD para ese `user_id`:

```
Sync recibe: user_id="1043", uid=8 (desde dispositivo B)
BD tiene:    user_id="1043", uid_dispositivo=5 (para dispositivo B)
                  ↓
Inconsistencia detectada → uid_inconsistente = true en personas_dispositivos
```

### Corrección desde la plataforma

```
Operador ve alerta: "Juan Pérez tiene uid diferente entre dispositivos"
         ↓
Elige el uid correcto (ej. el del dispositivo A: uid=5)
         ↓
En dispositivo B:
  1. delete_user(uid=8)
  2. set_user(uid=5, user_id="1043", name="Juan Pérez", ...)
  3. Si tenía template → replicar con uid corregido
         ↓
BD: uid_inconsistente = false, uid_dispositivo = 5
```

---

## Huellas dactilares y templates

### Cómo funciona el enrolado

El dispositivo ZKTeco genera un **template biométrico** — un hash matemático de la huella (~500 bytes). El template se almacena internamente en el dispositivo. pyzk puede leerlo y escribirlo.

La clase `Finger` en pyzk tiene:
- `uid` — uid interno del usuario **en ese dispositivo**
- `fid` — índice del dedo (0-9)
- `valid` — 1 = válido, 3 = solo verificación
- `template` — bytes crudos del modelo

Los templates son portátiles entre dispositivos ZKTeco del mismo fabricante. Los bytes del template son los mismos — lo que cambia es el `uid` que los referencia en cada dispositivo.

### Métodos disponibles en pyzk

| Método | Función |
|--------|---------|
| `get_templates()` | Descarga todos los templates del dispositivo |
| `get_user_template(uid, fid)` | Template de un dedo específico de un usuario |
| `save_user_template(user, fingers)` | Escribe template(s) en el dispositivo |
| `delete_user_template(uid, fid)` | Elimina un template específico |
| `enroll_user(uid, fid)` | Ordena al dispositivo entrar en modo captura (inestable) |
| `cancel_capture()` | Cancela una captura en curso |

### Replicación entre dispositivos

Para copiar el template de un usuario del dispositivo A al B:

```
1. get_user_template(uid_A, fid) → Finger con bytes del template
2. Buscar uid_B: el uid del mismo usuario en dispositivo B
3. Crear Finger(uid=uid_B, fid=fid, valid=1, template=mismos_bytes)
4. save_user_template(user_B, [finger_con_uid_B])
```

**Si los uids son iguales** (tenant uid-preestablecido): el paso 2 es trivial, uid_A = uid_B.
**Si los uids difieren** (tenant uid-auto): requiere el mapping guardado en `personas_dispositivos.uid_dispositivo`.

### Dedos distintos en distintos dispositivos

Si una persona tiene `fid=0` (índice derecho) en A y `fid=1` (índice izquierdo) en B, no hay error — son slots independientes. Al replicar, si no se limpian los templates previos del dispositivo destino, el usuario termina con ambos dedos registrados en B (fid=0 y fid=1), lo cual puede no ser lo deseado.

La replicación limpia requiere: `delete_user_template` de todos los fid existentes en el destino → `save_user_template` con los templates del origen.

### Guardado de templates en BD

`Finger.json_pack()` serializa el template a hex string. Esto permite guardar los templates en BD como respaldo y como fuente para replicar a nuevos dispositivos sin depender de que el dispositivo origen esté disponible.

---

## Sincronización automática entre dispositivos (ADMS)

Los dispositivos ZKTeco modernos soportan **ADMS** — un modo donde el dispositivo se conecta activamente a un servidor y empuja datos en tiempo real. Sin embargo:

- Los modelos actuales del sistema son **modelos viejos** que no necesariamente soportan ADMS.
- pyzk usa el modelo opuesto (servidor consulta al dispositivo), incompatible con ADMS.
- No existe sincronización nativa device-to-device sin un servidor central.

La replicación de templates se manejará desde la plataforma, no a nivel de configuración de dispositivos.

---

## Gaps en la BD actual

| Qué falta | Dónde | Para qué |
|-----------|-------|----------|
| Columna `uid INTEGER` | `usuarios_zk` | Guardar el uid interno del dispositivo |
| Columna `activo BOOLEAN` | `usuarios_zk` | Distinguir usuarios dados de baja |
| Columna `uid_dispositivo INTEGER` | `personas_dispositivos` | uid interno por dispositivo para operaciones de escritura |
| Columna `uid_inconsistente BOOLEAN` | `personas_dispositivos` | Flag de alerta para el operador |
| Tabla `huellas_personas` | Nueva | Guardar templates para replicación y backup |

---

## Resumen de capacidades pyzk para escritura

| Operación | Método pyzk | Estabilidad |
|-----------|-------------|-------------|
| Crear/editar usuario | `set_user()` | Estable |
| Eliminar usuario | `delete_user()` | Estable |
| Leer template de un dedo | `get_user_template()` | Estable |
| Leer todos los templates | `get_templates()` | Estable |
| Escribir template en dispositivo | `save_user_template()` | Funcional |
| Eliminar template | `delete_user_template()` | Funcional |
| Iniciar enrolado remoto | `enroll_user()` | Inestable / no recomendado |
