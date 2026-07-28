---
title: "Runbook de Operaciones — Sistema Biométrico RRHH ISTPET"
tags: [operations, runbook, deploy, monitoring, troubleshooting, superpowers]
status: published
created: 2026-07-02
updated: 2026-07-02
authors: [implementer, documenter]
related:
  - "[[DEPLOYMENT]]"
  - "[[ARQUITECTURA]]"
  - "[[API]]"
  - "[[ADR-0001-modularizacion-monolito-flask]]"
  - "[[ADR-0002-sync-observable-y-backups]]"
  - "[[AUTENTICACION]]"
supersedes: []
superseded_by: []
---

# Runbook de Operaciones

> **Propósito**: documento único que un dev o sysadmin nuevo necesita para
> hacer deploy, monitorear, troubleshoot y rollback del sistema biométrico
> en producción. Para instalación inicial paso a paso ver `[[DEPLOYMENT]]`.
> Para entender la arquitectura ver `[[ARQUITECTURA]]`.

---

## 1. Variables de entorno críticas

> **Cambiar estas variables implica reinicio del contenedor. Las claves
> NUNCA deben commitearse al repo; vive solo en `.env` del servidor.**

| Variable | Tipo | Default | Función |
|---|---|---|---|
| `FLASK_SECRET_KEY` | str (≥32 bytes random) | _none_ | Firma cookies de sesión. **Sin esto, la app NO arranca.** |
| `DATABASE_URL` | str (postgresql://) | _none_ | Conexión a PostgreSQL. Formato `postgresql://user:pass@host:port/db`. |
| `DB_ENCRYPTION_KEY` | str (base64, 32 bytes) | _none_ | Cifrado AES-256-GCM de contraseñas de dispositivos ZK. Generar con `python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`. **Sin esto, la primera escritura de un dispositivo falla.** |
| `SYNC_AUTO` | bool (`true`/`false`) | `false` | Activa el scheduler en background. **Solo `true` en producción.** |
| `SYNC_HORA_NOCTURNA` | str (`HH:MM`) | `02:00` | Hora local del servidor para sync nocturna completa. |
| `SYNC_INTERVALO_HORAS` | int | `2` | Cada cuántas horas corre sync incremental. |
| `BACKUP_AUTO` | bool | `false` (si SYNC_AUTO=false) / `true` (si SYNC_AUTO=true) | Activa `pg_dump` diario. |
| `BACKUP_HORA` | str (`HH:MM`) | `03:00` | Hora local para `pg_dump`. 1h después de la sync nocturna. |
| `BACKUP_DIR` | str (path) | `/data/backups` | Carpeta destino de los `.dump`. |
| `BACKUP_RETENCION_DIAS` | int | `30` | Días que se conservan los `.dump`. |
| `ADMIN_EMAIL` | str (email) | `admin@localhost` | Destinatario de alertas (fallos de sync, fallos de backup). |
| `DEEPSEEK_API_KEY` | str | _none_ | Si está, activa narrativas IA. Si falta, fallback regla-base. |
| `FLASK_ENV` | str | `production` | `production` para prod, `development` para dev local. |

---

## 2. Deploy

### 2.1. Build & up (primera vez)

```bash
cd /opt/biometrico  # o donde clones el repo
cp .env.example .env
# Editar .env con las claves reales (ver §1).
docker compose up -d --build
```

### 2.2. Apply migrations

```bash
# Dentro del contenedor (es la fuente de verdad del esquema):
docker compose exec web alembic upgrade head

# Verificar versión actual:
docker compose exec web alembic current
docker compose exec web alembic heads  # debe coincidir con current
```

> **Importante**: si las migraciones Alembic no se ejecutan en el deploy,
> `db/init.py::init_db()` corre DDL propio al arrancar — **dos fuentes de
> verdad**. Esto es la **Fase −1 parcial** del roadmap (ADR-0001). En
> cuanto se cierre esa fase, `init_db()` solo ejecuta seed y nunca DDL.

### 2.3. Verificación post-deploy (smoke test)

```bash
# 1. La app responde en /login:
curl -sI http://localhost:5000/biometrico/login | head -1
# → 200 OK

# 2. El token CSRF está en la página:
curl -s http://localhost:5000/biometrico/login | grep -q 'csrf_token' && echo "OK CSRF" || echo "FAIL CSRF"

# 3. 82 rutas registradas:
docker compose exec web python -c "import wsgi; print(len(wsgi.app.url_map.iter_rules()))"
# → 82

# 4. 13 blueprints:
docker compose exec web python -c "from app.web import all_blueprints; print(len(all_blueprints))"
# → 13

# 5. Scheduler_runs no tiene corridas fallidas recientes:
docker compose exec db psql -U $PGUSER -d $PGDB -c \
  "SELECT count(*) FROM public.scheduler_runs WHERE ok=false AND inicio > now() - interval '1 hour'"

# 6. Audit log tiene el último login:
docker compose exec db psql -U $PGUSER -d $PGDB -c \
  "SELECT usuario_id, accion, ip, created_at FROM public.audit_log ORDER BY created_at DESC LIMIT 5"
```

### 2.4. Update (aplicar cambios al servidor)

```bash
git pull origin development  # o main, según la rama desplegada
docker compose up -d --build  # reconstruye imagen + reinicia
docker compose exec web alembic upgrade head  # nuevas migraciones si hay
```

---

## 3. Monitoreo

### 3.1. Scheduler runs

```sql
-- Últimas 20 corridas del scheduler (sync incremental, nocturna, backup):
SELECT job, tenant_slug, ok, descargados, insertados,
       inicio, fin, detalle
FROM public.scheduler_runs
ORDER BY inicio DESC
LIMIT 20;

-- Corridas que fallaron en las últimas 24h:
SELECT count(*) FROM public.scheduler_runs
WHERE ok = false AND inicio > now() - interval '24 hours';

-- Tiempo promedio por tipo de job:
SELECT job, round(avg(EXTRACT(EPOCH FROM (fin - inicio)))::numeric, 1) AS avg_seconds,
       count(*) AS n
FROM public.scheduler_runs
WHERE inicio > now() - interval '7 days'
GROUP BY job
ORDER BY avg_seconds DESC;
```

### 3.2. Audit log

```sql
-- Últimos 20 eventos de seguridad (login, logout, cambios de rol):
SELECT u.email, a.accion, a.ip, a.created_at
FROM public.audit_log a
LEFT JOIN public.usuarios u ON u.id = a.usuario_id
ORDER BY a.created_at DESC
LIMIT 20;

-- Intentos de login fallidos por IP en la última hora:
SELECT ip, count(*) AS intentos
FROM public.audit_log
WHERE accion = 'login_failed' AND created_at > now() - interval '1 hour'
GROUP BY ip
ORDER BY intentos DESC;

-- Cambios de tenant por superadmin en las últimas 24h:
SELECT u.email, a.detalle, a.created_at
FROM public.audit_log a
JOIN public.usuarios u ON u.id = a.usuario_id
WHERE a.accion = 'switch_tenant' AND a.created_at > now() - interval '24 hours';
```

### 3.3. Backups

```bash
# Listar backups disponibles (cron-like):
ls -lh /data/backups/*.dump

# Verificar que el más reciente NO esté corrupto (carga la cabecera):
pg_restore -l /data/backups/backup_completo_$(date +%Y%m%d)*.dump | head -20
```

### 3.4. Salud del proceso

```bash
# Estado de los contenedores:
docker compose ps

# Logs en vivo de la app:
docker compose logs -f web

# Logs en vivo de la BD (errores solo):
docker compose logs -f db 2>&1 | grep -iE 'error|fatal|panic'

# Uso de memoria y CPU:
docker stats biometrico-app biometrico-db --no-stream
```

---

## 4. Troubleshooting común

### 4.1. La app no arranca: `RuntimeError: FLASK_SECRET_KEY no configurado`

```bash
# Causa: falta la variable en .env del servidor.
grep FLASK_SECRET_KEY .env
# Si está vacía o falta:
echo "FLASK_SECRET_KEY=$(openssl rand -hex 32)" >> .env
docker compose restart web
```

### 4.2. La app no arranca: `RuntimeError: DB_ENCRYPTION_KEY no configurada`

```bash
# Causa: falta la clave de cifrado AES.
grep DB_ENCRYPTION_KEY .env
echo "DB_ENCRYPTION_KEY=$(python -c 'import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')" >> .env
docker compose restart web
```

### 4.3. `pg_dump: error: could not connect to server`

```bash
# Causa: DATABASE_URL no apunta a localhost del contenedor.
docker compose exec web env | grep DATABASE_URL
# Si DATABASE_URL apunta a localhost pero el contenedor de la app NO comparte
# red con el de la BD, usar el nombre del servicio ('db'):
#   DATABASE_URL=postgresql://user:pass@db:5432/biometrico
```

### 4.4. Login falla con "Demasiados intentos fallidos"

```bash
# Causa: rate limit 5/15min por IP en public.login_intentos.
docker compose exec db psql -U $PGUSER -d $PGDB -c \
  "SELECT ip, exitoso, count(*), max(created_at) FROM public.login_intentos
   WHERE created_at > now() - interval '15 minutes'
   GROUP BY ip, exitoso ORDER BY max(created_at) DESC;"

# Reset manual de intentos fallidos de una IP:
docker compose exec db psql -U $PGUSER -d $PGDB -c \
  "DELETE FROM public.login_intentos WHERE ip = 'X.X.X.X' AND exitoso = false;"
```

### 4.5. CSRF token inválido

```bash
# Causa típica: el `FLASK_SECRET_KEY` cambió entre requests (rotación no coordinada).
# Síntoma: formularios rechazados con 400.
# Solución: si rotas FLASK_SECRET_KEY, hazlo en un maintenance window donde
# no haya sesiones activas.

# Verificar que todas las réplicas de la app usen el mismo secret:
docker compose exec web python -c "import os; print(os.environ['FLASK_SECRET_KEY'][:8])"
# (debe ser idéntico en todas las réplicas)
```

### 4.6. Scheduler quedó colgado en una corrida

```sql
-- Ver corridas con fin NULL (no terminaron):
SELECT id, job, tenant_slug, inicio, detalle
FROM public.scheduler_runs
WHERE fin IS NULL
ORDER BY inicio DESC
LIMIT 10;

-- Si hay más de 1h sin fin, fue killed. Revisar logs:
docker compose logs web --since="1h" | grep -iE "scheduler|exception"
```

### 4.7. `Backup diario` falla con `Permission denied`

```bash
# Causa típica: BACKUP_DIR no existe o no tiene permisos de escritura
# para el usuario del contenedor (uid 1000 por defecto en python:slim).
docker compose exec web ls -la /data/backups/ 2>&1
docker compose exec web touch /data/backups/test && docker compose exec web rm /data/backups/test
# Si falla, dar permisos al volumen:
docker compose exec -u root web chown -R 1000:1000 /data/backups
```

### 4.8. Tenant schema no se setea (g.tenant_schema = None)

```bash
# Causa típica: el usuario no tiene tenant_id en public.usuarios.
docker compose exec db psql -U $PGUSER -d $PGDB -c \
  "SELECT id, email, tenant_id, activo FROM public.usuarios WHERE email = 'admin@x';"
# Si tenant_id es NULL, la sesión no podrá cargar el schema del tenant.
```

---

## 5. Rollback

### 5.1. Rollback de la app (sin tocar BD)

```bash
# 1. Identificar el SHA del commit bueno:
git log --oneline -20

# 2. Revertir el último commit problemático:
git revert <sha>
git push origin development

# 3. Rebuild + restart:
docker compose up -d --build
```

### 5.2. Rollback de la BD (con backup)

> **NUCLEAR OPTION**: solo usar si una migración dejó la BD en estado roto.

```bash
# 1. Listar backups disponibles:
ls -lh /data/backups/*.dump

# 2. Stop la app:
docker compose stop web

# 3. Drop y recreate la BD:
docker compose exec db dropdb -U $PGUSER $PGDB
docker compose exec db createdb -U $PGUSER $PGDB

# 4. Restore desde el .dump:
docker compose exec -T db pg_restore \
  -U $PGUSER -d $PGDB --no-owner --role=$PGUSER \
  < /data/backups/backup_completo_YYYYMMDD_HHMM.dump

# 5. Restart app:
docker compose start web
docker compose exec web alembic stamp head  # marcar como migrada
```

---

## 6. Comandos de verificación rápida (cheat sheet)

```bash
# ¿La app está sana?
curl -fsS http://localhost:5000/biometrico/login > /dev/null && echo "OK"

# ¿Cuántas rutas registradas?
docker compose exec web python -c "import wsgi; print(len(wsgi.app.url_map.iter_rules()))"

# ¿Scheduler corrió en la última hora?
docker compose exec db psql -U $PGUSER -d $PGDB -t -c \
  "SELECT 'OK' WHERE EXISTS (SELECT 1 FROM public.scheduler_runs WHERE inicio > now() - interval '1 hour')"

# ¿Backups están al día?
ls /data/backups/backup_completo_*.dump | tail -1

# ¿Espacio en disco del volumen?
docker system df -v | grep biometrico
```

---

## 7. Changelog

| Fecha | Cambio | Autor |
|---|---|---|
| 2026-07-02 | Creación inicial (cierre Fase 8 del ADR-0001). | documenter |
| 2026-07-27 | Pre-check ADR-0003 (Tar. 0.2 del plan): backup reciente OK, restore probado contra BD temporal, runbook actualizado. | implementer |
| 2026-07-27-r2 | Pre-Fase 1 ADR-0003 (Tar. 0.4 del plan): Alembic único, init_db=seed, runbook actualizado. | arquitecto |
