---
title: "ADR-0002 — Sync automática observable + Backups portables"
status: accepted
created: 2026-07-02
supersedes: []
related: ["[[ADR-0001-modularizacion-monolito-flask]]", "[[ARQUITECTURA]]", "[[API]]"]
---

# ADR-0002: Sync automática observable + Backups portables

## Contexto

El sistema está en producción con datos biométricos irrecuperables, pero:

1. La sync automática (`schedule.every(N).hours.do(...)`) **nunca corre** porque
   `SYNC_AUTO=false` en `.env` de producción. El operador debe apretar el botón
   de sync manual y "estar pendiente siempre".
2. Si corriera, **fallaría en silencio**: `_sync_automatico` y `_sync_nocturna_completa`
   envolvían todo en `except Exception: pass`, y el thread `_run()` moría sin reiniciar.
3. No había visibilidad del estado del scheduler ni de las corridas (UI muda).
4. El backup de BD era un stub (`/api/backup/descargar` devolvía 501).

## Decisión

Reforzar in-place el scheduler `schedule` in-process (decisión coherente con
ADR-0001: 1 worker gunicorn) + persistir corridas en `public.scheduler_runs` +
entregar backups portables vía `pg_dump -Fc` ejecutado por subprocess con
credenciales pasadas por env (`PGPASSWORD`, nunca argv).

### Cambios

| Componente | Cambio |
|---|---|
| `db/migrations/versions/0009_scheduler_runs.py` | Crea `public.scheduler_runs` (id, job, tenant_slug, inicio, fin, ok, descargados, insertados, detalle) + 2 índices. Guarda sobre `current_schema()='public'` para no duplicar en tenants. |
| `db/queries/scheduler_runs.py` | Helper `registrar_run`, `listar_ultimos(limit)`, `purgar_mayor_a(dias)` |
| `app/domain/scheduler.py` | Wrapper sobre `db.queries.scheduler_runs` para que `app/web/*` no importe `db/queries/*` directo (regla ADR-0001) |
| `app/web/system_bp.py` | Nuevo endpoint `GET /api/scheduler/estado` (rol: `admin`/`superadmin`) |
| `sync.py` | Logger (`logging.getLogger(__name__)`); helper `_registrar_corrida_sync`; `_run()` con try/except + `continue`; jobs `sync_incremental`, `sync_nocturna`, `backup_diario` registran en BD; flag singleton `_scheduler_started`; purga `> 90 días` al cierre de la sync nocturna |
| `backup.py` | `generar_dump(destino)` ejecuta `pg_dump -Fc` con `PGPASSWORD` por env; `purgar_backups_viejos(dir, dias)` |
| `app/web/reports_bp.py` | `/api/backup/descargar` implementa `pg_dump` real, registra en `audit_log` |
| `Dockerfile` | Añade `postgresql-client-16` (provee `pg_dump`); crea `/data/backups` |
| `docker-compose.yml` | El volumen `app_data:/data` ya cubre `/data/backups` (sin cambio obligatorio) |
| `templates/configuracion.html` + `static/js/configuracion.js` | Tercer tab "Sincronización" con card y tabla de corridas |
| `.env.example` | Variables `BACKUP_AUTO`, `BACKUP_HORA`, `BACKUP_DIR`, `BACKUP_RETENCION_DIAS`; nota `SYNC_AUTO=true` recomendado en producción; corrección de comentario `DB_ENCRYPTION_KEY` (AES-256-GCM, no Fernet) |

### Alternativas consideradas

| Opción | Por qué descartada |
|---|---|
| Cron del SO (`/etc/cron.d/biometrico-sync`) | Infra fuera del contenedor; no resuelve visibilidad (UI seguiría muda) |
| Celery + Redis | Ya descartado como Fase 6 del roadmap; overkill para este fix |
| Backup manual por el operador | Estado actual; no escala, depende de memoria humana |
| Off-site backup en este PR (rclone / S3 / NAS) | Alcance de Fase −1 del roadmap ([[ARQUITECTURA]] → "Fase −1"); este PR garantiza solo que **siempre exista un dump fresco local** |

## Consecuencias

**Positivas:**

- Operador ya no necesita acordarse de sincronizar.
- Cualquier fallo de sync queda registrado y visible en UI + email.
- Backup diario automático con retención; restauración es 1 comando (`pg_restore`).
- Cobertura de tests > 30% (TDD estricto en módulos nuevos): 23 tests nuevos.

**Negativas / riesgos:**

- `pg_dump` añade dependencia (`postgresql-client-16`) → imagen Docker crece ~50 MB.
- El thread `pg_dump` mantiene 1 conexión a la BD durante segundos/minutos; con sync
  incremental simultánea podría haber contención. Mitigación: `BACKUP_HORA` (03:00)
  cae 1 h después de la sync nocturna (02:00).
- Si `BACKUP_DIR` se llena (disco), el job falla y **no purga** (mitigación: alerta por email).
- Si `pg_dump` no está instalado en el contenedor (imagen vieja), el endpoint responde
  500 claro y el job de scheduler registra error + email. La fix es reconstruir la
  imagen con la migración `0009` aplicada.
- El log de `sync.py` usa `logging.getLogger("sync")`. Si el operador no configura
  handlers de log, los mensajes pueden no aparecer. Gunicorn captura stderr/stdout
  con `PYTHONUNBUFFERED=1`, así que los prints irían. Recomendado configurar
  `LOG_LEVEL=INFO` en `.env`.

## Testing

- Unit (TDD): 23 tests nuevos distribuidos en 4 archivos:
  - `tests/unit/test_scheduler_runs.py` — 6 tests sobre `registrar_run` /
    `listar_ultimos` / `purgar_mayor_a` (mock de engine).
  - `tests/unit/test_sync_logging.py` — 7 tests sobre logger +
    `_registrar_corrida_sync` + `iniciar_scheduler` inactivo + singleton guard
    + estructura del loop inkillable.
  - `tests/unit/test_scheduler_estado.py` — 6 tests sobre el endpoint (auth,
    roles, formato JSON, serialización de datetimes, robustez ante fallos de BD).
  - `tests/unit/test_backup.py` — 10 tests sobre `generar_dump` +
    `purgar_backups_viejos` (mock de subprocess y filesystem; verifica que
    `PGPASSWORD` va por env y NO por argv).

- Total: **73 tests unitarios pasan** (50 previos + 23 nuevos).

- Integración (manual/staging):
  - Levantar el sistema con `SYNC_AUTO=true` + `BACKUP_AUTO=true` en `.env`.
  - Reconstruir imagen Docker (incluye `postgresql-client-16`).
  - Aplicar migración: `alembic upgrade head`.
  - Esperar a la próxima corrida y verificar fila en `public.scheduler_runs`.
  - Descargar `/api/backup/descargar` → `pg_restore` en BD limpia → conteos coinciden.

## Operaciones

**Para activar en producción:**

1. Editar `.env`: `SYNC_AUTO=true`, `BACKUP_AUTO=true` (o dejar el valor heredado),
   `ADMIN_EMAIL=tu@correo`.
2. Reconstruir imagen: `docker compose build biometrico-app`.
3. Aplicar migración: `docker compose exec biometrico-app alembic upgrade head`.
4. Reiniciar: `docker compose restart biometrico-app`.
5. Verificar en `/configuracion` → tab "Sincronización": badge "ACTIVO".
6. Verificar dump: `docker compose exec biometrico-app ls -lh /data/backups`.

**Restauración de emergencia:**

```bash
# 1. Copiar dump al host
docker cp biometrico-app:/data/backups/backup_completo_YYYYMMDD_HHMM.dump ./restore.dump
# 2. Crear BD limpia
createdb -h localhost -U postgres restore_db
# 3. Restaurar
pg_restore -h localhost -U postgres -d restore_db ./restore.dump
```

## Relacionado

- [[ADR-0001-modularizacion-monolito-flask]] — Arquitectura base que preservamos.
- [[ARQUITECTURA]] → "Operación: sync automática y backups" — Sección operacional.
- [[API]] — Inventario de endpoints (`/api/scheduler/estado`, `/api/backup/descargar`).
- Spec: `docs/superpowers/specs/2026-07-01-sync-backup-confiable-design.md`.
- Plan: `docs/superpowers/plans/2026-07-01-sync-backup-confiable.md`.