---
title: "Diseño — Sincronización automática confiable + Backups portables"
status: approved
created: 2026-07-01
related: ["[[ARQUITECTURA]]", "[[ADR-0001-modularizacion-monolito-flask]]"]
---

# Diseño: Sincronización automática confiable + Backups portables

## Problema

El sistema está en producción con datos biométricos irrecuperables, pero:

1. **La sync automática nunca corre.** El scheduler (`sync.py::iniciar_scheduler`) está completo
   (nocturna 02:00 + incremental cada 2 h, multi-tenant) pero solo arranca con `SYNC_AUTO=true`;
   el `.env` de producción tiene `SYNC_AUTO=false`. El operador debe apretar el botón de sync
   manual y "estar pendiente siempre".
2. **Si corriera, fallaría en silencio.** `_sync_automatico` y `_sync_nocturna_completa` envuelven
   todo en `except Exception: pass`. Si el loop del thread lanza una excepción, el thread muere
   sin aviso y no reinicia.
3. **No hay visibilidad.** Nada en la UI indica si el scheduler está activo, cuándo corrió por
   última vez ni con qué resultado.
4. **El backup de BD es un stub.** `/api/backup/descargar` devuelve `501 — use pg_dump`. Solo
   existe el CSV de asistencias del tenant actual.

## Decisión de enfoque

**Reforzar lo existente** (scheduler in-process `schedule` + 1 worker gunicorn, coherente con
ADR-0001). Descartados: cron del SO (infra fuera del contenedor, no resuelve visibilidad) y
Celery (ya descartado como Fase 6 del roadmap).

## Parte 1 — Sincronización automática confiable

### 1.1 Activación y arranque observable

- `SYNC_AUTO=true` en producción (cambio de `.env`, documentado en `.env.example`).
- Al arrancar, log INFO explícito:
  `"Scheduler ACTIVO: nocturna {SYNC_HORA_NOCTURNA}, incremental cada {SYNC_INTERVALO_HORAS}h"`
  o `"Scheduler INACTIVO (SYNC_AUTO=false)"`.

### 1.2 Fin de los fallos silenciosos

- Eliminar los `except Exception: pass` de `_sync_automatico` y `_sync_nocturna_completa`:
  cada corrida registra resultado por tenant (ok/error + mensaje) en `public.scheduler_runs`.
- El loop `_run()` del thread se envuelve en `try/except` con log de error y `continue`:
  el thread no puede morir.

### 1.3 Persistencia: tabla `public.scheduler_runs`

Migración Alembic `0009` (aditiva; cero impacto en datos existentes):

| Columna | Tipo | Notas |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `job` | TEXT NOT NULL | `'sync_nocturna'`, `'sync_incremental'`, `'backup_diario'` |
| `tenant_slug` | TEXT | NULL para jobs globales (backup) |
| `inicio` / `fin` | TIMESTAMPTZ | |
| `ok` | BOOLEAN NOT NULL | |
| `descargados` / `insertados` | INTEGER | NULL para backup |
| `detalle` | TEXT | mensaje de error o ruta del backup |

Retención: las filas > 90 días se purgan en el propio job nocturno.

### 1.4 Visibilidad en UI

Card "Sincronización automática" en `/configuracion` (solo lectura, roles admin+):

- Estado del scheduler: ACTIVO/INACTIVO (leído de config) + heartbeat (última pasada del loop).
- Última corrida de cada job con resultado y conteos; próxima programada
  (`schedule.next_run`).
- Tabla de las últimas 10 corridas de `scheduler_runs`.
- Endpoint nuevo: `GET /api/scheduler/estado` (JSON, `@require_role('superadmin','admin')`).

La alerta existente por email (3 fallos consecutivos de dispositivo → `ADMIN_EMAIL`) se mantiene.

## Parte 2 — Backups portables

### 2.1 Botón de descarga (implementar el stub)

`GET /api/backup/descargar` — `@require_role('superadmin')`:

1. Ejecuta `pg_dump -Fc` (formato custom comprimido) vía `subprocess`, credenciales tomadas de
   `DATABASE_URL` (pasadas por env `PGPASSWORD`, nunca por argv). Incluye **toda** la BD:
   `public` + todos los schemas de tenants.
2. Escribe a archivo temporal en `REPORTS_FOLDER` y lo sirve como descarga
   (`backup_completo_YYYYMMDD_HHMM.dump`); el cleanup thread existente (15 min) lo purga.
3. Registra la descarga en `audit_log` (quién, cuándo, tamaño).
4. Errores de `pg_dump` → 500 con mensaje claro + log (nunca descarga parcial: se valida
   returncode antes de servir).

Requisito de imagen: añadir `postgresql-client` (v16, igual que el servidor) al `Dockerfile`.

El CSV existente (`/api/backup/csv`) se conserva como exportación "legible en Excel".

**Restauración (portabilidad):** `pg_restore -d <db> backup.dump` en cualquier PostgreSQL ≥ 16.
Se documenta el procedimiento en la sección de operación de ARQUITECTURA.md.

### 2.2 Backup diario automático

- Job nuevo en el mismo scheduler: diario a `BACKUP_HORA` (default `03:00`, después de la sync
  nocturna), ejecuta el mismo `pg_dump -Fc` hacia `BACKUP_DIR` (default `/data/backups`,
  volumen Docker persistente).
- Retención: conserva `BACKUP_RETENCION_DIAS` (default 30) días; borra los más viejos tras un
  backup exitoso (nunca borra si el backup del día falló).
- Resultado registrado en `scheduler_runs` (job `backup_diario`); visible en la card de la UI.
- Si el backup falla, email a `ADMIN_EMAIL` (mismo mecanismo de alertas existente).
- Variables nuevas en `.env.example`: `BACKUP_AUTO` (default `true` si `SYNC_AUTO=true`),
  `BACKUP_HORA`, `BACKUP_DIR`, `BACKUP_RETENCION_DIAS`.

> **Nota**: el backup queda en el mismo host. Copiarlo fuera (rclone/NAS/nube) es
> responsabilidad de la Fase −1 del roadmap; este job garantiza que siempre exista un backup
> local fresco y restaurable.

## Estructura de módulos

Nuevo módulo `backup.py` (raíz, futuro `app/domain/backup.py` según ADR-0001):
`generar_dump(destino: Path) -> Path`, `purgar_backups_viejos(dir, dias) -> int`.
`sync.py` gana el registro en `scheduler_runs` y el job de backup; las rutas nuevas viven en
`app.py` (se moverán a `reports_bp`/`system_bp` en la Fase 3 del refactor).

## Errores y edge cases

- `pg_dump` no instalado → el endpoint responde 500 con instrucción de rebuild; el job diario
  registra error y alerta. Chequeo al arranque con log WARNING.
- Disco lleno en `BACKUP_DIR` → error registrado + email; la retención nunca corre tras fallo.
- Dos syncs simultáneas (manual + automática) → ya tolerado hoy (idempotencia por watermark +
  `ON CONFLICT`); se documenta.
- Multi-worker gunicorn → igual que hoy: el diseño asume `--workers 1` (restricción ADR-0001).

## Testing

- Unit: `purgar_backups_viejos` (fixtures de archivos con fechas), armado del comando `pg_dump`
  desde `DATABASE_URL`, registro en `scheduler_runs` (mock de conexión).
- Integración (manual/staging): descargar backup → `pg_restore` en BD limpia → conteos coinciden.
- Smoke: card de estado renderiza con scheduler activo e inactivo.

## Fuera de alcance

- Barra de progreso en vivo de la sync manual (la card muestra resultados reales; progreso en
  vivo se trata aparte si hace falta).
- Copia off-site de backups (Fase −1).
- Restore desde la UI (solo por CLI documentada — restaurar por botón es demasiado peligroso).

## Documentación a actualizar

- `docs/ARQUITECTURA.md`: sección nueva "Operación: sync automática y backups" + job en la tabla
  del scheduler.
- `docs/API.md`: rutas nuevas/cambiadas (`/api/scheduler/estado`, `/api/backup/descargar` real).
- `docs/adr/0002-sync-observable-y-backups.md`: ADR corto con esta decisión.
- `.env.example`: variables nuevas + corregir el comentario de `DB_ENCRYPTION_KEY`
  (menciona Fernet; el mecanismo real es AES-256-GCM — la clave Fernet sirve por ser 32 bytes
  base64, pero el comentario confunde).
