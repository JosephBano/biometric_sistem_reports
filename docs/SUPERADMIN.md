# Panel de Superadmin — Gestión Global de Usuarios

> **Alcance:** Este documento describe la funcionalidad del panel de superadmin para gestionar cuentas de acceso (`public.usuarios`) de forma cross-tenant.
>
> **No confundir con:** La gestión de `personas` (empleados biométricos). Las personas biométricas viven en los schemas de tenant y son inamovibles entre tenants por diseño (contienen registros de asistencia históricos). Las `personas` no se mueven; solo las cuentas de acceso (`usuarios`) pueden moverse.

---

## Conceptos clave

### ¿Qué es un usuario de aplicación?

Un **usuario de aplicación** (`public.usuarios`) es una cuenta que permite hacer login en la interfaz Flask del sistema. Cada usuario:
- Tiene un **email único global** (no se repite entre tenants)
- Pertenece a **un solo tenant** (columna `tenant_id`)
- Tiene uno o más **roles**: `superadmin`, `admin`, `gestor`, `supervisor_grupo`, `supervisor_periodo`, `readonly`

### Modelo de tenants (Opción A — un gestor = un tenant)

Un mismo email no puede existir en dos tenants. Si un gestor necesita acceso en dos tenants, debe tener **dos cuentas separadas** con emails distintos (ej: `juan@istpet.edu.ec` y `juan@otro.edu.ec`).

### Operaciones disponibles

| Operación | Descripción |
|-----------|-------------|
| **Ver todos** | Lista todos los usuarios de todos los tenants |
| **Mover** | Elimina del tenant origen + crea en tenant destino (con clave temporal) |
| **Eliminar** | Soft-delete: `activo = false` |
| **Crear en otro tenant** | Registrar un usuario directamente en un tenant específico |

---

## Acceso

**URL:** `/admin/superadmin/usuarios`

**Requisito:** Rol `superadmin`. Solo visible en el menú lateral para superadmins.

---

## API Endpoints

### GET /admin/superadmin/usuarios

Panel HTML. Requiere sesión autenticada con rol `superadmin`.

---

### POST /api/superadmin/usuarios/mover

Mueve un usuario de un tenant a otro: soft-delete en origen + creación en destino.

**Autenticación:** Sesión con rol `superadmin`.

**Request:**
```json
{
  "usuario_id": "uuid-del-usuario",
  "tenant_id_destino": "uuid-del-tenant-destino",
  "generar_password": true,
  "password": "clave-manual-si-generar-false"
}
```

**Respuesta (200):**
```json
{
  "ok": true,
  "password_temporal": "abc123xyz..."
}
```

**Notas:**
- El email, nombre y roles se conservan del usuario original
- La contraseña en el destino puede ser automática (generada) o manual
- El usuario original se **desactiva** (`activo = false`), no se borra
- Si el email ya existe en el tenant destino → error 409

---

### POST /api/superadmin/usuarios

Crea un usuario directamente en un tenant específico.

**Autenticación:** Sesión con rol `superadmin`.

**Request:**
```json
{
  "tenant_id": "uuid-del-tenant",
  "email": "nuevo@email.com",
  "nombre": "Nombre Completo",
  "roles": ["admin"],
  "generar_password": true,
  "password": "clave-manual"
}
```

**Respuesta (201):**
```json
{
  "ok": true,
  "usuario": { "id": "...", "email": "...", "nombre": "...", "roles": [...], "activo": true },
  "password_temporal": "abc123xyz..."
}
```

---

### DELETE /api/superadmin/usuarios/<usuario_id>

Elimina (soft-delete) un usuario de cualquier tenant.

**Autenticación:** Sesión con rol `superadmin`.

**Respuesta (200):**
```json
{
  "ok": true,
  "mensaje": "Usuario eliminado"
}
```

---

## Flujo: Mover un usuario de tenant incorrecto

### Situación
Se registró un usuario gestor en el tenant `istpet` (incorrecto), cuando debería estar en `otro`.

### Pasos

1. Ir a `/admin/superadmin/usuarios`
2. Buscar el usuario por email
3. Click **"Mover"**
4. Seleccionar `otro` como tenant destino
5. Asegurar que "Generar contraseña temporal" esté marcado
6. Click **"Mover usuario"**
7. **Copiar la contraseña temporal** mostrada en pantalla
8. Entregar la contraseña al usuario por un canal seguro

### Resultado

| Tabla | Efecto |
|-------|--------|
| `public.usuarios` en tenant origen | `activo = false` (soft-delete) |
| `public.usuarios` en tenant destino | Nuevo registro con email, nombre y roles originales |

---

## Seguridad

- Todos los endpoints requieren rol `superadmin`
- Los movimientos se registran en `audit_log` con `accion = "superadmin_mover_usuario"`
- No se transfieren datos biométricos ni de asistencia (estos son independientes del tenant del usuario)

---

## Vistas relacionadas

- [ER.md](./ER.md) — Documentación del schema `public.usuarios`
- [API.md](./API.md) — Referencia completa de rutas
