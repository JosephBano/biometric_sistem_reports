# Sistema de Informes Biométricos — RRHH ISTPET

Aplicación web para gestión de asistencia del personal a partir del sistema de control biométrico ZK. Sincroniza marcaciones directamente del dispositivo, las almacena en PostgreSQL, y genera informes PDF, analytics estadísticos con narrativos IA opcionales, y gestión de justificaciones y períodos.

---

## Tabla de contenidos

1. [Requisitos](#1-requisitos)
2. [Estructura del proyecto](#2-estructura-del-proyecto)
3. [Instalación — modo desarrollo (sin Docker)](#3-instalación--modo-desarrollo-sin-docker)
4. [Instalación — modo producción (Docker)](#4-instalación--modo-producción-docker)
5. [Configuración del archivo `.env`](#5-configuración-del-archivo-env)
6. [Primera vez: crear el superadmin](#6-primera-vez-crear-el-superadmin)
7. [Módulos de la interfaz web](#7-módulos-de-la-interfaz-web)
   - [7.1 Dashboard](#71-dashboard)
   - [7.2 Reportes PDF](#72-reportes-pdf)
   - [7.3 Justificaciones](#73-justificaciones)
   - [7.4 Períodos](#74-períodos)
   - [7.5 Analytics e IA](#75-analytics-e-ia)
   - [7.6 Personas](#76-personas)
   - [7.7 Configuración](#77-configuración)
   - [7.8 Administración (admin / superadmin)](#78-administración-admin--superadmin)
8. [Horarios personalizados por persona](#8-horarios-personalizados-por-persona)
9. [Gestión y mantenimiento](#9-gestión-y-mantenimiento)
10. [Referencia de la API](#10-referencia-de-la-api)
11. [Solución de problemas](#11-solución-de-problemas)

---

## 1. Requisitos

### Modo desarrollo (sin Docker)

| Requisito | Versión mínima |
|-----------|----------------|
| Python | 3.12 |
| PostgreSQL | 14+ |
| Acceso a la red local donde está el dispositivo ZK | — |

### Modo producción (Docker) — recomendado

| Requisito | Versión mínima |
|-----------|----------------|
| Docker Engine (Linux) o Docker Desktop (Windows / macOS) | 24.x |
| Docker Compose | v2 (`docker compose`) |
| Sistema operativo | Linux, Windows 10/11, macOS |
| Acceso a la red local donde está el dispositivo ZK | — |

```bash
docker --version
docker compose version
```

---

## 2. Estructura del proyecto

```
script_informe_asistencia/
│
├── app.py                  # Servidor Flask — todas las rutas HTTP
├── script.py               # Motor de análisis y generación de PDF
├── analytics.py            # Motor de analytics estadísticos (pandas/numpy)
├── ia_report.py            # Narrativos ejecutivos con IA (DeepSeek) o fallback
├── sync.py                 # Conector al dispositivo ZK (pyzk) + scheduler
├── auth.py                 # Lógica de autenticación con bcrypt
├── decorators.py           # @require_role — control de acceso por rol
├── crear_superadmin.py     # Script CLI para crear la cuenta maestra inicial
│
├── db/                     # Capa de acceso a PostgreSQL
│   ├── __init__.py         # Re-exporta todas las funciones públicas (from db import *)
│   ├── connection.py       # Pool de conexiones SQLAlchemy + set search_path por tenant
│   ├── migrations/         # Migraciones Alembic (0001 → 0005)
│   └── queries/            # Módulos por dominio
│       ├── asistencias.py
│       ├── asistencia_periodo.py
│       ├── auth.py
│       ├── breaks.py
│       ├── dispositivos.py
│       ├── feriados.py
│       ├── grupos.py
│       ├── horarios.py
│       ├── justificaciones.py
│       ├── periodos.py
│       ├── personas.py
│       ├── personas_crud.py
│       ├── sync_log.py
│       └── tenants.py
│
├── templates/
│   ├── base.html           # Layout base (sidebar, toasts, scripts comunes)
│   ├── dashboard.html      # Panel principal
│   ├── reportes.html       # Generación de PDF e informe por email
│   ├── justificaciones.html
│   ├── analytics.html      # Analytics estadísticos + narrativo IA
│   ├── configuracion.html  # Feriados + respaldos
│   ├── login.html
│   ├── periodos/           # Listado y detalle de períodos
│   └── admin/              # Gestión de usuarios, grupos, dispositivos, tenants
│
├── static/
│   ├── style.css
│   └── js/
│       ├── api.js          # Helper fetch centralizado
│       ├── dashboard.js
│       ├── reportes.js
│       ├── justificaciones.js
│       └── configuracion.js
│
├── .env                    # Variables de entorno (NO subir al repo)
├── .env.example            # Plantilla
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

### Base de datos PostgreSQL

El sistema usa un modelo **multi-tenant** con schema por institución. El schema por defecto es `istpet`.

| Schema | Contenido |
|--------|-----------|
| `public` | Usuarios del sistema, tenants, dispositivos, configuración global |
| `istpet` (u otro tenant) | Personas, asistencias, horarios, justificaciones, períodos, feriados, grupos |

Las migraciones se aplican con Alembic y están versionadas en `db/migrations/versions/`.

---

## 3. Instalación — modo desarrollo (sin Docker)

### Paso 1 — Clonar el proyecto

```bash
git clone <url-del-repo> script_informe_asistencia
cd script_informe_asistencia
```

### Paso 2 — Entorno virtual y dependencias

```bash
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Paso 3 — PostgreSQL local

```bash
# Crear usuario y base de datos
psql -U postgres -c "CREATE USER asistencias_user WITH PASSWORD 'tu_password';"
psql -U postgres -c "CREATE DATABASE asistencias_db OWNER asistencias_user;"
```

### Paso 4 — Archivo de configuración

```bash
cp .env.example .env
# Editar .env: ajustar DATABASE_URL con host=localhost, contraseña real, etc.
# Ver sección 5 para detalle de variables
```

### Paso 5 — Aplicar migraciones

```bash
alembic upgrade head
```

### Paso 6 — Crear el superadmin inicial

```bash
python crear_superadmin.py --email admin@istpet.edu.ec --nombre "Administrador"
# Ingresa una contraseña segura cuando se solicite
```

### Paso 7 — Iniciar el servidor

```bash
# Desarrollo
python app.py

# Más cercano a producción
gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 120 app:app
```

Disponible en `http://localhost:5000`.

---

## 4. Instalación — modo producción (Docker)

Esta es la forma recomendada. Incluye PostgreSQL 16 como servicio separado.

### Instalación rápida

**1 — Crear el archivo de configuración:**

```bash
cp .env.example .env
# Editar .env con los valores reales (ver sección 5)
```

**2 — Construir e iniciar los contenedores:**

```bash
docker compose up -d --build
```

Esto levanta dos servicios:
- `biometrico-db` — PostgreSQL 16 con volumen `postgres_data`
- `biometrico-app` — la aplicación Flask con gunicorn, volumen `app_data`

La primera vez puede tardar 3–5 minutos (descarga de imagen + instalación de dependencias).

**3 — Aplicar migraciones (solo la primera vez o tras actualizaciones):**

```bash
docker compose exec biometrico-app alembic upgrade head
```

**4 — Crear el superadmin inicial (solo la primera vez):**

```bash
docker compose exec biometrico-app python crear_superadmin.py \
  --email admin@istpet.edu.ec --nombre "Administrador"
```

**5 — Verificar:**

```bash
docker compose ps
# Columna Status debe mostrar "Up (healthy)" para db y "Up" para app
```

Abrir: `http://localhost:5000` (misma máquina) o `http://IP_SERVIDOR:5000` (red local).

### Acceso al dispositivo ZK desde Docker

El contenedor usa `ports: "5000:5000"` por defecto. Para que la app pueda conectar al dispositivo ZK en la red local se necesita que ambos estén en la misma red.

En **Linux con Docker Engine**, la opción más directa es `network_mode: host` (comentada en `docker-compose.yml`). En ese caso:
1. Comentar el bloque `ports` y `depends_on` de `biometrico-app`
2. Descomentar `network_mode: host`
3. Levantar primero la DB: `docker compose up -d db`, luego `docker compose up -d biometrico-app`

En **Windows/macOS con Docker Desktop**, la red del host es accesible por defecto desde los contenedores.

### Actualizar el código

```bash
docker compose up -d --build
docker compose exec biometrico-app alembic upgrade head
```

Los volúmenes de datos no se pierden.

### Detener

```bash
docker compose down          # conserva volúmenes
docker compose down -v       # ELIMINA todos los datos (reset total)
```

---

## 5. Configuración del archivo `.env`

**Nunca subir este archivo al repositorio.**

```ini
# ── Información del sistema ────────────────────────
NOMBRE_SISTEMA=Informes Biométricos
NOMBRE_INSTITUCION=ISTPET

# ── Rutas de datos (dentro del contenedor) ─────────
DATA_DIR=/data
UPLOAD_FOLDER=/data/uploads
REPORTS_FOLDER=/data/reports

# ── PostgreSQL ──────────────────────────────────────
POSTGRES_USER=asistencias_user
POSTGRES_PASSWORD=contraseña_segura
POSTGRES_DB=asistencias_db
# En Docker usar 'db' como host; en desarrollo local usar 'localhost'
DATABASE_URL=postgresql://asistencias_user:contraseña_segura@db:5432/asistencias_db

# Tenant activo (slug del schema PostgreSQL)
TENANT_DEFAULT=istpet

# Clave AES-256 para cifrar contraseñas de dispositivos ZK en la BD
# Generar con: python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
DB_ENCRYPTION_KEY=clave_base64_de_32_bytes

# ── Flask ───────────────────────────────────────────
# Generar con: python -c "import secrets; print(secrets.token_hex(32))"
FLASK_SECRET_KEY=cadena_larga_aleatoria_y_secreta
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=false

# ── Autenticación ───────────────────────────────────
SESSION_LIFETIME_HOURS=8

# Solo para la primera instalación (crear superadmin automático al iniciar)
INITIAL_SUPERADMIN_EMAIL=admin@istpet.edu.ec
INITIAL_SUPERADMIN_PASSWORD=contraseña_segura_inicial

# ── Correo electrónico (SMTP) ───────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=notificaciones@istpet.edu.ec
SMTP_PASSWORD=app_password_de_gmail
SMTP_FROM=notificaciones@istpet.edu.ec
SMTP_USE_TLS=true

# ── Sincronización automática ───────────────────────
SYNC_AUTO=false
SYNC_HORA_NOCTURNA=02:00
SYNC_INTERVALO_HORAS=2

# ── Dispositivo biométrico ZK ───────────────────────
# Fallback si el dispositivo no tiene contraseña en BD (gestionado desde /admin/dispositivos)
ZK_IP=192.168.7.129
ZK_PORT=4370
ZK_PASSWORD=12345
ZK_TIMEOUT=120
ZK_CAPACIDAD_MAX=80000

# ── Analytics e IA ──────────────────────────────────
# API key de DeepSeek para narrativos ejecutivos generados por IA.
# Sin esta clave el sistema usa un generador de texto basado en reglas (completamente funcional).
# Obtener en: https://platform.deepseek.com/api_keys
DEEPSEEK_API_KEY=

# ── Alertas de dispositivos ─────────────────────────
# Email que recibe alertas cuando un dispositivo falla 3 syncs consecutivas.
# Dejar vacío para deshabilitar.
ADMIN_EMAIL=
```

### Generar claves seguras

```bash
# FLASK_SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# DB_ENCRYPTION_KEY
python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

### 5.1 Configurar Gmail para el envío de correos

Gmail requiere una **Contraseña de Aplicación**, no la contraseña de la cuenta:

1. `Cuenta de Google → Seguridad → Verificación en dos pasos` (activar si no está).
2. Buscar **"Contraseñas de aplicaciones"** → crear una con nombre "Biométrico ISTPET".
3. Google genera un código de 16 letras. Pegarlo en `SMTP_PASSWORD`.

Para Outlook el proceso es equivalente. Para servidor institucional, consultar con el administrador de correos.

---

## 6. Primera vez: crear el superadmin

El sistema no tiene usuarios por defecto. Antes de poder iniciar sesión se debe crear la cuenta maestra:

```bash
# En desarrollo
python crear_superadmin.py --email admin@istpet.edu.ec --nombre "Administrador"

# En Docker
docker compose exec biometrico-app python crear_superadmin.py \
  --email admin@istpet.edu.ec --nombre "Administrador"
```

El script solicita una contraseña de forma interactiva. Tras esto, iniciar sesión en `http://localhost:5000/login`.

### Roles del sistema

| Rol | Acceso |
|-----|--------|
| `superadmin` | Acceso total, gestión de tenants y usuarios |
| `admin` | Gestión de dispositivos, grupos, personas, horarios |
| `gestor` | Reportes, analytics, justificaciones |
| `supervisor_grupo` | Vista de su grupo asignado |
| `supervisor_periodo` | Vista de su período asignado |
| `readonly` | Solo lectura |

Los roles se asignan desde `Administración → Usuarios`.

---

## 7. Módulos de la interfaz web

### 7.1 Dashboard

Panel principal. Muestra:

- Estado del dispositivo ZK (accesible / no accesible, última sync, total registros).
- Botón **Sincronizar** con barra de progreso en tiempo real.
- **Tarjeta de alertas de tardanzas severas**: personas con 3 o más tardanzas severas en el mes actual.
- Acceso rápido a las secciones de reportes y períodos.

### 7.2 Reportes PDF

Genera informes de asistencia en PDF a partir de los datos sincronizados.

**Requisito previo:** los horarios del personal deben estar cargados (ver [sección 8](#8-horarios-personalizados-por-persona)).

**Tipos de reporte:**

| Modo | Descripción |
|------|-------------|
| `General (todos, por día)` | Organizado por día; solo incluye personas con horario; omite días sin incidencias |
| `Por persona (una sola)` | Historial diario de un empleado con hora programada vs. real |
| `Por varias personas` | Igual que el anterior para un subconjunto seleccionado |

**Parámetros:**
1. Seleccionar **Fecha inicio** y **Fecha fin**.
2. Elegir el **Tipo de reporte**.
3. Si corresponde, seleccionar empleado(s).
4. Opcionalmente, escribir nombres en **Personas a excluir** (separados por coma).
5. Hacer clic en **Generar Reporte PDF**.

**Enviar por email (modo "Por persona"):**
1. Completar el campo **Correo electrónico de destino**.
2. Hacer clic en **Enviar Informe ahora**.

Requiere `SMTP_*` configurado en `.env`.

### 7.3 Justificaciones

Registra y administra permisos, ausencias y tardanzas justificadas. Los datos son considerados por el motor de análisis al generar informes PDF.

**Tipos:** `ausencia`, `tardanza`, `permiso`, `almuerzo`, `salida_anticipada`, `incompleto`.

**Justificaciones recuperables:** al activar el checkbox *"¿Es recuperable?"* se habilitan los campos **Fecha de recuperación** y **Hora de recuperación**. El informe PDF incluye automáticamente la nota `[RECUPERABLE – se compensará DD/MM/AAAA HH:MM]`.

**Estados:** `pendiente`, `aprobada`, `rechazada`. Cambiable directamente desde la tabla.

### 7.4 Períodos

Gestión de períodos de vigencia para personal contratado o practicantes (contratos con fecha inicio/fin definida).

- Crear, editar y cerrar períodos.
- Ver el detalle de asistencia y tasa de cumplimiento por período.
- Cada período genera su propio reporte de asistencia con semáforo por persona (Verde ≥ 90%, Amarillo ≥ 75%, Rojo < 75%).

### 7.5 Analytics e IA

Análisis estadístico del conjunto completo de empleados activos para un rango de fechas.

**Pestaña Resumen Analítico:**

1. Seleccionar rango de fechas, tipo de persona y/o grupo (opcional).
2. Hacer clic en **Analizar Datos**.
3. El sistema calcula:
   - **Tasa de asistencia promedio** del período.
   - **Risk Score por persona** (0–100): ausencias × 15 pts + tardanzas × 5 pts.
   - **Top 10 personas en riesgo** con semáforo (Rojo ≥ 70, Amarillo ≥ 40, Verde < 40).
   - **Anomalías estadísticas**: personas que superan en 1.5σ el promedio de tardanzas o ausencias del grupo.
   - **Reporte Narrativo Ejecutivo**: texto generado por IA (DeepSeek) o por reglas deterministas.

**Pestaña Gestión de Alertas:**

- Personas con 3+ tardanzas severas en el período seleccionado.
- Lista de anomalías estadísticas detectadas.

**Configurar narrativo IA (opcional):**

Agregar en `.env`:
```ini
DEEPSEEK_API_KEY=sk-...
```
Luego reiniciar el servidor (`docker compose restart`). Sin la clave, el narrativo se genera con reglas basadas en los datos (completamente funcional para uso operativo).

### 7.6 Personas

Directorio del personal sincronizado desde el dispositivo ZK.

- Ver y editar datos de cada persona (nombre, identificación, grupo, categoría, tipo).
- Asignar o cambiar grupo/categoría.
- Ver el historial de marcaciones de cada persona.

### 7.7 Configuración

**Pestaña Feriados:**
- Agregar, importar (CSV) y exportar feriados nacionales, locales o institucionales.
- Los feriados son excluidos automáticamente del análisis de ausencias.

**Pestaña Respaldos y Históricos:**
- Descargar backup de la base de datos (`pg_dump`).
- Descargar historial completo en CSV.
- Importar marcaciones históricas desde `.csv` o `.xlsx` (columnas mínimas: `nombre`, `fecha_hora`).

### 7.8 Administración (admin / superadmin)

Visible en el sidebar solo para roles `admin` y `superadmin`.

| Sección | Función |
|---------|---------|
| **Dispositivos** | Registrar dispositivos ZK, configurar IP/puerto/contraseña (cifrada con AES-256) |
| **Usuarios** | Crear cuentas de acceso, asignar roles, activar/desactivar |
| **Grupos** | Crear y gestionar grupos de personas (departamentos, áreas) |
| **Categorías** | Tipos de contrato o categorías del personal |
| **Tenants** | Solo superadmin — gestión de instituciones (multi-tenant) |

---

## 8. Horarios personalizados por persona

El sistema requiere un archivo de horarios cargado para analizar tardanzas y ausencias. Sin horarios, los reportes PDF no pueden generarse.

### 8.1 Formato del archivo

Archivo OpenDocument Spreadsheet (`.ods` o `.obd`), primera hoja, con las columnas:

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `NOMBRES` | Texto | Nombre completo del empleado |
| `ID` | Número | ID del usuario en el dispositivo ZK |
| `LUNES (HORA ENTRADA)` | `HH:MM` o `NO` | Hora programada el lunes |
| `MARTES (HORA ENTRADA)` | `HH:MM` o `NO` | Ídem martes |
| `MIERCOLES (HORA ENTRADA)` | `HH:MM` o `NO` | Ídem miércoles |
| `JUEVES (HORA ENTRADA)` | `HH:MM` o `NO` | Ídem jueves |
| `VIERNES (HORA ENTRADA)` | `HH:MM` o `NO` | Ídem viernes |
| `FIN DE SEMANA (HORA ENTRADA)` | `HH:MM` o `NO` | Hora el sábado |
| `ALMUERZO (TIENE)` | `TRUE` / `FALSE` / `"30 min"` | Derecho a almuerzo |
| `NOTAS` | Texto | Observaciones libres (opcional) |

**Reglas:**

| Valor | Efecto |
|-------|--------|
| `NO` en un día | La persona no trabaja ese día — no genera alerta de tardanza ni ausencia |
| Hora (ej. `07:00`) | Hora programada de entrada |
| `ALMUERZO = TRUE` | 60 min de almuerzo (solo lunes–viernes) |
| `ALMUERZO = FALSE` | Sin almuerzo |
| `ALMUERZO = "30 min"` | 30 min de almuerzo (solo lunes–viernes) |
| Sábado | Nunca se analiza almuerzo |

### 8.2 Cargar horarios

Ir a **Reportes** → card azul **Horarios Personalizados** → **Actualizar horarios** → seleccionar archivo `.obd` o `.ods`.

Los horarios se persisten en la base de datos. Si algún ID del archivo no coincide con un usuario del dispositivo, se muestra una advertencia (no impide la carga).

### 8.3 Tolerancia de tardanzas

| Retraso sobre hora programada | Clasificación |
|-------------------------------|--------------|
| 0 min | Puntual — no aparece en el informe |
| 1 – 5 min | Tardanza leve |
| > 5 min | Tardanza severa |

La tolerancia de 5 minutos es fija y no configurable desde la UI.

---

## 9. Gestión y mantenimiento

### Ver logs en tiempo real

```bash
docker compose logs -f
docker compose logs -f biometrico-app   # solo la app
```

### Backup de PostgreSQL

```bash
# Dump SQL
docker exec biometrico-db pg_dump -U asistencias_user asistencias_db > backup_$(date +%Y%m%d).sql

# Restaurar
docker exec -i biometrico-db psql -U asistencias_user asistencias_db < backup_20260101.sql
```

Automatizar con cron (Linux):

```bash
# Backup diario a las 02:00
0 2 * * * docker exec biometrico-db pg_dump -U asistencias_user asistencias_db > /backups/asistencias_$(date +\%Y\%m\%d).sql
```

### Reiniciar el servidor

```bash
docker compose restart biometrico-app
```

Necesario después de cambiar variables en `.env`.

### Activar sincronización automática

Editar `.env`:

```ini
SYNC_AUTO=true
SYNC_HORA_NOCTURNA=02:00    # sync completo diario
SYNC_INTERVALO_HORAS=2      # sync incremental cada 2 horas
```

Reiniciar: `docker compose restart biometrico-app`

### Rutina mensual recomendada

1. Hacer clic en **Sincronizar** en el Dashboard.
2. Verificar que la sync completó correctamente.
3. Generar el informe general del mes y verificar datos.
4. **Mantenimiento del dispositivo** → **Limpiar log** → confirmar.
   - Esto elimina los registros del dispositivo ZK (ya están en la BD). Las próximas sincronizaciones serán casi instantáneas.
5. Hacer backup: `docker exec biometrico-db pg_dump ...`

### Ver espacio de volúmenes

```bash
docker system df -v
```

---

## 10. Referencia de la API

Todas las rutas de la API (`/api/...`) requieren sesión activa. Sin sesión retornan `401`.

### Sincronización

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/estado-sync` | Estado del dispositivo y estadísticas de la BD |
| `POST` | `/sincronizar` | Inicia sync en background; retorna `job_id` |
| `GET` | `/sync-status/<job_id>` | Estado del job de sync |
| `POST` | `/limpiar-dispositivo` | Limpia log del ZK (requiere `{"confirmar": true}`) |

### Reportes

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/personas-db` | Personas con registros para un rango (`?fecha_inicio=&fecha_fin=`) |
| `POST` | `/generar-desde-db` | Genera PDF desde la BD |
| `POST` | `/api/enviar-informe` | Genera PDF y lo envía por email |

**Body de `/generar-desde-db`:**

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `fecha_inicio` | `"YYYY-MM-DD"` | Sí | Inicio del período |
| `fecha_fin` | `"YYYY-MM-DD"` | Sí | Fin del período |
| `modo` | `"general"` \| `"persona"` \| `"varias"` | No (default `general`) | Tipo de reporte |
| `persona` | string | Si `modo == "persona"` | Nombre exacto del empleado |
| `personas` | string[] | Si `modo == "varias"` | Lista de nombres |
| `excluidos` | string[] | No | Personas a excluir |

### Horarios

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/cargar-horarios` | Sube archivo `.obd` / `.ods` de horarios |
| `GET` | `/estado-horarios` | Resumen del estado de horarios cargados |
| `GET` | `/horarios` | Lista completa de horarios por persona |

### Justificaciones

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/justificaciones` | Lista (acepta `?fecha_inicio=&fecha_fin=`) |
| `POST` | `/api/justificaciones` | Crea una nueva |
| `GET` | `/api/justificaciones/<id>` | Detalle |
| `PUT` | `/api/justificaciones/<id>` | Actualiza todos los campos |
| `PATCH` | `/api/justificaciones/<id>` | Cambia solo el `estado` |
| `DELETE` | `/api/justificaciones/<id>` | Elimina |

**Campos del body (POST / PUT):**

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `id_usuario` | string | Sí | ID del usuario en el dispositivo |
| `nombre` | string | Sí | Nombre del empleado |
| `fecha` | `"YYYY-MM-DD"` | Sí | Fecha de la novedad |
| `tipo` | string | Sí | `ausencia`, `tardanza`, `permiso`, `almuerzo`, `salida_anticipada`, `incompleto` |
| `motivo` | string | No | Descripción libre |
| `aprobado_por` | string | No | Responsable que aprueba |
| `hora_permitida` | `"HH:MM"` | No | Hora autorizada (tardanzas) |
| `estado` | string | No | `aprobada` (default), `pendiente`, `rechazada` |
| `recuperable` | int (0/1) | No | 1 si la novedad será compensada |
| `fecha_recuperacion` | `"YYYY-MM-DD"` | Si `recuperable=1` | — |
| `hora_recuperacion` | `"HH:MM"` | Si `recuperable=1` | — |

### Alertas

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/alertas/tardanzas-severas` | Personas con ≥ 3 tardanzas severas (`?fecha_inicio=&fecha_fin=`) |

### Analytics

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/analytics` | Hallazgos JSON para un rango (`?fecha_inicio=&fecha_fin=`) |
| `POST` | `/api/analytics/narrativo` | Genera narrativo IA a partir de hallazgos enviados como JSON |

### Respaldos

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/backup/descargar` | Descarga dump de la BD |
| `GET` | `/api/backup/csv` | Exporta historial completo en CSV |
| `POST` | `/api/historicos/importar` | Importa historial desde `.csv` / `.xlsx` |

---

## 11. Solución de problemas

### El dispositivo aparece como "no accesible"

1. Verificar IP en el dispositivo: `Menú → Opciones → Comunicación`.
2. Probar desde el host:
   ```bash
   ping 192.168.X.X
   nc -zv -w 3 192.168.X.X 4370
   ```
3. Verificar `ZK_PASSWORD`: un password incorrecto produce `Unauthenticated` aunque el puerto responda. Revisar en `Menú → Opciones → Comunicación → Contraseña`. Fábrica: `0`.
4. Probar `ZK_UDP=true` en `.env` y reiniciar.
5. El dispositivo solo admite **una conexión simultánea** — cerrar el software del fabricante si está abierto.

### La sincronización es muy lenta

El protocolo ZK descarga **todos** los registros históricos cada vez. Para acelerar:

- **Solución permanente:** sincronizar → verificar datos → **limpiar log del dispositivo** mensualmente.
- **Mejora rápida:** `ZK_UDP=true` (20–40% más rápido en LAN).

Referencia: ~8.500 registros (170 usuarios) tarda ~20 segundos en red local.

### Analytics no muestra datos

El módulo de analytics analiza **todas las personas activas** (`personas.activo = TRUE`) que tengan horario cargado. Si muestra "No hay suficientes datos":

1. Verificar que hay horarios cargados: `GET /estado-horarios`.
2. Verificar que hay asistencias sincronizadas en el rango seleccionado.
3. Revisar los logs del servidor: `docker compose logs -f biometrico-app`.

### El narrativo IA no aparece (solo muestra texto básico)

- Verificar que `DEEPSEEK_API_KEY` está configurado en `.env`.
- Reiniciar el servidor: `docker compose restart biometrico-app` (los cambios en `.env` requieren reinicio).
- Revisar logs: si hay un error de API (código de estado, timeout), aparece en los logs con nivel `WARNING`.
- Sin la clave, el sistema usa un generador de texto basado en reglas — esto es el comportamiento esperado.

### El informe PDF no muestra a ciertas personas

El sistema solo analiza personas presentes en el **archivo de horarios cargado**. Verificar que el empleado está incluido (por nombre o ID) y volver a importar el archivo.

### La aplicación no arranca en Docker

```bash
docker compose logs biometrico-app
```

Causas comunes:
- El archivo `.env` no existe o tiene variables mal formateadas.
- La BD no está lista — verificar: `docker compose logs biometrico-db`.
- Migraciones no aplicadas: `docker compose exec biometrico-app alembic upgrade head`.
- Puerto 5000 en uso: `sudo ss -tlnp | grep 5000` (Linux) / `netstat -ano | findstr :5000` (Windows).

### El correo no se envía

| Error | Causa | Solución |
|-------|-------|---------|
| `535 Authentication Failed` | Credenciales incorrectas o Gmail requiere App Password | Generar App Password (ver [sección 5.1](#51-configurar-gmail-para-el-envío-de-correos)) |
| `Connection refused` / timeout | Puerto 587 o 465 bloqueado por firewall | Cambiar `SMTP_PORT` entre `587` y `465` |
| Correo llega a SPAM | Sin SPF/DKIM en el dominio emisor | Usar correo institucional o configurar SPF con IT |
| Variables SMTP no cargadas | Contenedor no reiniciado tras editar `.env` | `docker compose restart biometrico-app` |

---

*Sistema de Informes Biométricos — RRHH ISTPET*
