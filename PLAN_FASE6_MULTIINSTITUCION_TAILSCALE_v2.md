# Plan de Implementación — Fase 6: Multi-institución Tailscale + Multi-driver
**Versión:** 2.0 — Dispositivos agnósticos, sin campo `modulo`
**Fecha:** 2026-03-17
**Prerequisito:** Fases 1–5 v2 completadas y verificadas

---

## 1. Contexto y cambios respecto a v1

### 1.1 Qué cambia

El único cambio conceptual en esta fase respecto a la v1 es la eliminación del campo `dispositivo.modulo`.

En la v1, el campo `modulo` ('empleados', 'alumnos') determinaba a qué tabla se insertaban las marcaciones. En v2 ese routing no existe — todo va a `asistencias` y el routing ocurre a través de `personas_dispositivos`.

Esto **simplifica** la arquitectura de drivers:
- Un driver no necesita saber si está procesando empleados o alumnos
- Un driver solo necesita retornar `{id_usuario, nombre, fecha_hora, punch_raw}`
- El lookup de persona y período lo hace la capa de `sync.py`

Todo lo demás de esta fase (Tailscale, multi-driver, onboarding) es idéntico a la v1.

### 1.2 Lo que no cambia

- Infraestructura Tailscale (setup servidor, subnet router, etc.)
- Arquitectura de drivers intercambiables
- Driver ZKTeco (refactorización del código existente como clase)
- Driver Hikvision ISAPI
- UI de gestión de dispositivos
- Provisioning del tenant de la otra institución (ya cubierto en Fase 3)
- Documentación de onboarding

---

## 2. Alcance

**Qué incluye:**
- Guía de setup de Tailscale
- Refactorización de `sync.py` con arquitectura de drivers intercambiables
- Driver ZKTeco como clase
- Driver Hikvision ISAPI
- UI de gestión de dispositivos: agregar, editar, probar conectividad
- Provisioning del tenant de la otra institución

**Qué NO incluye:**
- Driver Suprema (cuando haya necesidad real)
- Driver Dahua
- Gestión de red Tailscale desde la UI

---

## 3. Tabla `dispositivos` en v2

La tabla `dispositivos` del schema v2 (definida en Fase 1) ya no tiene el campo `modulo`. Su estructura relevante para esta fase:

| Campo | Tipo | Nota |
|---|---|---|
| `tipo_driver` | TEXT DEFAULT 'zk' | `'zk'`, `'hikvision'`, `'suprema'`, `'dahua'` |
| `protocolo` | TEXT DEFAULT 'tcp' | `'tcp'`, `'udp'`, `'http'` |
| `ip` | TEXT | IP local o Tailscale (100.x.x.x) |
| `puerto` | INTEGER | 4370 para ZK, 80/443 para Hikvision |
| `password_enc` | TEXT | Cifrado AES-256-GCM |
| `watermark_ultimo_id` | TEXT | Para sync incremental (Fase 7) |

No existe `modulo`. Un dispositivo registra lo que sus personas tienen en `personas_dispositivos`.

---

## 4. Arquitectura de drivers

### 4.1 Interfaz base

```python
# drivers/base.py
class BiometricDriver:
    def __init__(self, dispositivo: dict):
        self.dispositivo = dispositivo

    def test_conexion(self) -> bool:
        raise NotImplementedError

    def get_usuarios(self) -> list[dict]:
        """Retorna [{id_usuario, nombre, privilegio}]"""
        raise NotImplementedError

    def get_asistencias(self, desde: datetime = None) -> list[dict]:
        """Retorna [{id_usuario, nombre, fecha_hora, punch_raw}]"""
        raise NotImplementedError

    def get_capacidad(self) -> dict:
        """Retorna {total_registros, capacidad_max}"""
        raise NotImplementedError
```

### 4.2 Driver ZKTeco

```python
# drivers/zk_driver.py
class ZKDriver(BiometricDriver):
    """Refactorización del código de sync.py actual como clase."""
    def __init__(self, dispositivo: dict):
        super().__init__(dispositivo)
        self._password = decrypt_device_password(dispositivo['password_enc'])
```

### 4.3 Driver Hikvision ISAPI

```python
# drivers/hikvision_driver.py
class HikvisionDriver(BiometricDriver):
    """Comunicación vía HTTP ISAPI de Hikvision."""
    BASE_URL = "http://{ip}:{puerto}/ISAPI"
```

### 4.4 Factory de drivers

```python
# drivers/__init__.py
def get_driver(dispositivo: dict) -> BiometricDriver:
    drivers = {
        'zk': ZKDriver,
        'hikvision': HikvisionDriver,
    }
    cls = drivers.get(dispositivo['tipo_driver'])
    if not cls:
        raise ValueError(f"Driver no soportado: {dispositivo['tipo_driver']}")
    return cls(dispositivo)
```

### 4.5 `sync.py` refactorizado

```python
# sync.py
def sincronizar_dispositivo(dispositivo_id: str):
    dispositivo = db.get_dispositivo(dispositivo_id)
    driver = get_driver(dispositivo)

    if not driver.test_conexion():
        db.registrar_sync(..., exito=False, error="No se pudo conectar")
        return

    usuarios = driver.get_usuarios()
    db.upsert_usuarios(usuarios)  # actualiza usuarios_zk

    asistencias_raw = driver.get_asistencias()

    # Lookup persona para cada marcación (agnóstico al tipo)
    registros = []
    for a in asistencias_raw:
        persona_id, nombre = db.resolver_persona_id(a['id_usuario'], dispositivo_id)
        periodo_id = db.get_periodo_vigente_en_fecha(persona_id, a['fecha_hora'].date())
        registros.append({
            **a,
            'persona_id': persona_id,
            'periodo_vigencia_id': periodo_id,
            'dispositivo_id': dispositivo_id,
        })

    nuevos = db.insertar_asistencias(registros)
    db.registrar_sync(..., nuevos=nuevos, exito=True)
```

---

## 5. Infraestructura Tailscale (sin cambios respecto a v1)

### 5.1 Setup del servidor central (ISTPET)

```bash
# Una sola vez
# Instalar Tailscale en el host Linux del servidor
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up --accept-routes
tailscale ip  # anotar esta IP
```

### 5.2 Setup de institución remota

Por cada institución remota, su IT hace:
```bash
# En el PC que servirá como subnet router
# Windows: instalador .exe desde tailscale.com
# Linux:
apt install tailscale
tailscale up --advertise-routes=192.168.X.0/24  # su red local
# Autenticar con la auth-key que provee el admin de ISTPET
```

El dispositivo ZK no necesita ninguna instalación. Solo necesita que el PC subnet router esté encendido.

### 5.3 Verificación de conectividad

La UI de dispositivos incluye un botón "Probar conectividad" que ejecuta `driver.test_conexion()` y muestra el resultado.

---

## 6. Onboarding de nueva institución

### 6.1 Flujo completo

```
1. Superadmin crea el tenant (Fase 3):
   - Configura slug, nombre, tipos de persona
   - Provisioning automático del schema

2. La institución configura Tailscale en su PC subnet router

3. Admin del nuevo tenant configura sus dispositivos en la UI:
   - IP del biométrico (local o Tailscale)
   - tipo_driver
   - Contraseña del dispositivo (se cifra al guardar)
   - Puerto y protocolo

4. Admin prueba conectividad desde la UI

5. Admin ejecuta la primera sync manual

6. Admin verifica que las personas aparecen en usuarios_zk

7. Admin crea personas y las vincula con personas_dispositivos
   (o el sistema las auto-crea como "sin perfil" y el admin las completa)
```

---

## 7. UI de gestión de dispositivos

### 7.1 Lista de dispositivos

Tabla con: nombre, IP, tipo de driver, sede, estado de conexión (último ping), fecha de última sync.

### 7.2 Formulario crear/editar dispositivo

Campos: nombre, IP, puerto, tipo_driver (dropdown), protocolo, contraseña (enmascarada), sede, timeout.

Al guardar: la contraseña se cifra con AES-256-GCM antes de persistir.

### 7.3 Acciones por dispositivo

- Probar conectividad → `driver.test_conexion()`
- Sincronizar ahora → `sincronizar_dispositivo(id)`
- Ver historial de sync → tabla de `sync_log` filtrado por `dispositivo_id`
- Editar / Desactivar

---

## 8. Pasos de implementación

### Paso 1 — Crear `drivers/` con interfaz base y ZKDriver

Refactorizar el código de sync existente como `ZKDriver`.

**Verificación:** La sync de ISTPET funciona exactamente igual usando `ZKDriver` en lugar del código inline.

### Paso 2 — Implementar `HikvisionDriver`

**Verificación:** `test_conexion()` y `get_asistencias()` funcionan contra un dispositivo Hikvision de prueba.

### Paso 3 — Refactorizar `sync.py`

Usar el factory de drivers y el lookup unificado de personas.

**Verificación:** Sync completa sin errores para todos los dispositivos activos. Los registros tienen `persona_id` y `periodo_vigencia_id` correctos.

### Paso 4 — UI de gestión de dispositivos

**Verificación:** Admin puede crear dispositivo, probar conectividad y ejecutar sync manual desde la UI.

### Paso 5 — Setup Tailscale y onboarding de la otra institución

**Verificación:** Dispositivo ZK de la otra institución accesible desde el servidor de ISTPET vía Tailscale. Sync manual produce registros correctos en el schema del tenant.

---

## 9. Criterio de finalización

- [ ] `ZKDriver` funciona como refactorización del código existente
- [ ] `HikvisionDriver` implementado y probado
- [ ] Factory de drivers selecciona el correcto según `tipo_driver`
- [ ] `sync.py` usa drivers intercambiables y lookup unificado de personas
- [ ] Sync no hace distinción por tipo de persona — todo va a `asistencias`
- [ ] UI de gestión de dispositivos funcional: crear, editar, probar, sincronizar
- [ ] Tailscale configurado en servidor y en la otra institución
- [ ] La otra institución puede sincronizar sus dispositivos remotamente
- [ ] No existe el campo `modulo` en la tabla `dispositivos`
- [ ] No existe routing condicional a `asistencias_alumnos` en el código

**Una vez completados estos criterios, el sistema está listo para la Fase 7 (Sincronización Mejorada).**
