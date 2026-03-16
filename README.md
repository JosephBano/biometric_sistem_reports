# Sistema de Informes Biométricos — RRHH ISTPET

Aplicación web para generar informes PDF de asistencia del personal a partir del sistema de control biométrico ZK. Obtiene los datos directamente del dispositivo en red y los almacena en una base de datos local.

---

## Tabla de contenidos

1. [Requisitos](#1-requisitos)
2. [Estructura del proyecto](#2-estructura-del-proyecto)
3. [Instalación — modo desarrollo (sin Docker)](#3-instalación--modo-desarrollo-sin-docker)
4. [Instalación — modo producción (Docker)](#4-instalación--modo-producción-docker)
5. [Configuración del archivo `.env`](#5-configuración-del-archivo-env)
6. [Uso de la interfaz web](#6-uso-de-la-interfaz-web)
   - [6.1 Horarios personalizados](#61-horarios-personalizados-card-superior)
   - [6.2 Panel del dispositivo ZK](#62-panel-del-dispositivo-biométrico-zk)
   - [6.3 Parámetros fijos del análisis](#63-parámetros-fijos-del-análisis)
   - [6.4 Gestión de justificaciones](#64-gestión-de-justificaciones)
   - [6.5 Dashboard y alertas](#65-dashboard-y-alertas)
   - [6.6 Envío de informes por email](#66-envío-de-informes-por-email)
7. [Horarios personalizados por persona](#7-horarios-personalizados-por-persona)
8. [Gestión y mantenimiento](#8-gestión-y-mantenimiento)
9. [Referencia de la API](#9-referencia-de-la-api)
10. [Solución de problemas](#10-solución-de-problemas)

---

## 1. Requisitos

### Para modo desarrollo (sin Docker)

| Requisito | Versión mínima |
|-----------|---------------|
| Python | 3.12 |
| Acceso a la red local donde está el dispositivo ZK | — |

No se requiere ninguna dependencia externa del sistema operativo.

### Para modo producción (Docker)

| Requisito | Versión mínima |
|-----------|---------------|
| Docker Engine (Linux) o Docker Desktop (Windows / macOS) | 24.x |
| Docker Compose | v2 (`docker compose`, no `docker-compose`) |
| Sistema operativo | Linux, Windows 10/11, macOS |
| Acceso a la red local donde está el dispositivo ZK | — |

**Verificar versiones instaladas:**
```bash
docker --version
docker compose version
```

---

## 2. Estructura del proyecto

```
script_informe_asistencia/
│
├── app.py                  # Servidor Flask — rutas HTTP
├── script.py               # Motor de análisis y generación de PDF
├── db.py                   # Capa de acceso a SQLite
├── sync.py                 # Conector al dispositivo ZK (pyzk)
├── horarios.py             # Parser de horarios personalizados (.obd/.ods)
│
├── templates/
│   ├── base.html           # Layout base (navbar, scripts comunes)
│   ├── dashboard.html      # Panel principal — estado, alertas de tardanzas severas
│   ├── reportes.html       # Generación de PDF e informe por email
│   ├── justificaciones.html# Gestión de justificaciones (crear, editar, aprobar)
│   ├── configuracion.html  # Horarios, feriados, dispositivo ZK
│   └── login.html          # Pantalla de autenticación
├── static/
│   ├── style.css           # Estilos de la UI
│   └── js/
│       ├── api.js          # Helper fetch centralizado
│       ├── dashboard.js    # Lógica del dashboard y alertas
│       ├── reportes.js     # Lógica de reportes y envío por email
│       ├── justificaciones.js # CRUD de justificaciones
│       └── configuracion.js   # Horarios, feriados, mantenimiento ZK
│
├── .env                    # Variables de entorno (NO subir al repo)
├── .env.example            # Plantilla para crear el .env
├── .gitignore
│
├── Dockerfile              # Imagen Docker del servidor
├── docker-compose.yml      # Orquestación de servicios y volúmenes
├── DESPLIEGUE.md           # Guía paso a paso de instalación y despliegue
│
├── requirements.txt        # Dependencias Python
│
└── data/                   # Creado automáticamente en runtime
    ├── asistencias.db      # Base de datos SQLite (persistida en Docker volume)
    ├── uploads/            # Archivos de horarios subidos temporalmente
    └── reports/            # PDFs generados temporalmente (TTL: 15 min)
```

**Tablas en la base de datos SQLite:**

| Tabla | Contenido |
|-------|-----------|
| `asistencias` | Marcaciones del dispositivo ZK (Entrada/Salida por persona y fecha) |
| `usuarios_zk` | Directorio de usuarios registrados en el dispositivo |
| `sync_log` | Historial de sincronizaciones con el dispositivo |
| `horarios_personal` | Horarios individuales por día de la semana (cargados desde `.obd`) |
| `justificaciones` | Permisos, ausencias y tardanzas justificadas, con soporte de recuperación |
| `breaks_categorizados` | Salidas intermedias del día clasificadas (almuerzo, permiso, injustificado) |
| `feriados` | Días feriados nacionales o institucionales; excluidos del análisis |

---

## 3. Instalación — modo desarrollo (sin Docker)

### Paso 1 — Clonar o descargar el proyecto

```bash
cd /ruta/donde/quieras/instalar
git clone <url-del-repo> script_informe_asistencia
cd script_informe_asistencia
```

### Paso 2 — Crear y activar el entorno virtual

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### Paso 3 — Instalar dependencias

```bash
pip install -r requirements.txt
```

### Paso 4 — Crear el archivo de configuración

```bash
cp .env.example .env
```

Editar el archivo `.env` con los datos reales del dispositivo (ver [sección 5](#5-configuración-del-archivo-env)).

### Paso 5 — Iniciar el servidor

```bash
# Con Flask en modo desarrollo (solo para desarrollo)
python app.py

# O con gunicorn (más cercano a producción)
gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 120 app:app
```

El servidor queda disponible en `http://localhost:5000`.

---

## 4. Instalación — modo producción (Docker)

Esta es la forma recomendada. El sistema corre en un contenedor Docker y funciona en **Linux (servidor o escritorio), Windows 10/11 y macOS**.

Para instrucciones detalladas paso a paso según tu sistema operativo, consultar **[DESPLIEGUE.md](DESPLIEGUE.md)**.

### Instalación rápida (todos los sistemas)

**1 — Crear el archivo de configuración:**

```bash
cp .env.example .env
# Editar .env con los datos del dispositivo ZK
```

**2 — Construir e iniciar el contenedor:**

```bash
docker compose up -d --build
```

Este comando:
- Descarga la imagen base de Python 3.12 e instala las dependencias
- Crea el volumen `db_data` para persistencia de la base de datos
- Inicia el contenedor en segundo plano (`restart: unless-stopped`)

La primera vez puede tardar 3–5 minutos.

**3 — Verificar que está corriendo:**

```bash
docker compose ps
```

La columna `Status` debe mostrar `Up`. Abrir el navegador en:

- Escritorio (Linux o Windows, misma máquina): `http://localhost:5000`
- Servidor (desde otra máquina en la red): `http://IP_DEL_SERVIDOR:5000`

### Actualizar a una nueva versión del código

```bash
docker compose up -d --build
# El volumen de datos NO se pierde en este proceso
```

### Detener el sistema

```bash
docker compose down
# Los datos en el volumen db_data se conservan
```

### Detener y eliminar todos los datos (reset total)

```bash
docker compose down -v
# ADVERTENCIA: esto elimina la base de datos SQLite y todos los datos sincronizados
```

---

## 5. Configuración del archivo `.env`

El archivo `.env` concentra toda la configuración sensible. **Nunca subir este archivo al repositorio.**

```ini
# ── Dispositivo biométrico ZK ──────────────────────
ZK_IP=192.168.X.X          # IP del dispositivo en la red local
ZK_PORT=4370               # Puerto del protocolo ZK (casi siempre 4370)
ZK_PASSWORD=XXXX           # Contraseña del dispositivo (Menú → Opciones → Comunicación). Fábrica: 0
ZK_TIMEOUT=5               # Segundos de espera para conectar
ZK_UDP=false               # true = protocolo UDP (más rápido, probar primero)
ZK_CAPACIDAD_MAX=80000     # Capacidad máxima del dispositivo ZK K30 para monitoreo

# ── Sincronización automática ──────────────────────
SYNC_AUTO=false            # true = activa sync automático en background
SYNC_HORA_NOCTURNA=00:30   # Hora del sync completo diario (HH:MM)
SYNC_INTERVALO_MIN=30      # Cada cuántos minutos hacer un sync parcial

# ── Rutas de datos (dentro del contenedor) ─────────
DB_PATH=/data/asistencias.db
UPLOAD_FOLDER=/data/uploads
REPORTS_FOLDER=/data/reports

# ── Flask ──────────────────────────────────────────
FLASK_SECRET_KEY=cadena_larga_aleatoria_y_secreta
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_DEBUG=false          # Nunca true en producción

# ── Correo electrónico (SMTP) ──────────────────────
SMTP_HOST=smtp.gmail.com           # Servidor SMTP (Gmail, Outlook, institucional)
SMTP_PORT=587                      # 587 con STARTTLS o 465 con SSL directo
SMTP_USER=notificaciones@tuinstituto.edu.ec
SMTP_PASSWORD=abcd efgh ijkl mnop  # App Password si usa Gmail/Outlook (ver sección 5.1)
SMTP_FROM=notificaciones@tuinstituto.edu.ec
SMTP_USE_TLS=true                  # true para puerto 587; false para 465 SSL directo
```

### Generar una `FLASK_SECRET_KEY` segura

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 5.1 Configurar Gmail para el envío de correos

Gmail no permite usar la contraseña normal de la cuenta. Requiere una **Contraseña de Aplicación**:

1. Ir a `Cuenta de Google → Seguridad`.
2. Activar la **Verificación en dos pasos** (si no está activa).
3. Buscar **"Contraseñas de aplicaciones"** → crear una nueva con nombre "Sistema Asistencia".
4. Google genera un código de 16 letras (ej: `abcd efgh ijkl mnop`).
5. Pegar ese código en `SMTP_PASSWORD` del `.env` (con o sin espacios; ambos funcionan).

Para Outlook el proceso es equivalente. Para un servidor institucional, consultar con el administrador de correos de la institución.

---

### Cómo encontrar la contraseña del dispositivo ZK

La contraseña del dispositivo (`ZK_PASSWORD`) se configura en `Menú → Opciones → Comunicación` en la pantalla del equipo. Si nunca se configuró, el valor predeterminado es `0`.

> **Atención:** un `ZK_PASSWORD` incorrecto produce el error `Unauthenticated` internamente — el dispositivo aparecerá como "no accesible" aunque el ping y el puerto respondan. Siempre verificar el valor real en la pantalla del equipo.

---

## 6. Uso de la interfaz web

Abrir el navegador en `http://localhost:5000` (misma máquina) o `http://IP_SERVIDOR:5000` (desde la red).

### 6.1 Horarios personalizados (card superior)

Al abrir la página se muestra una card azul en la parte superior con el estado de los horarios individuales del personal. Ver [sección 7](#7-horarios-personalizados-por-persona) para el flujo completo.

---

### 6.2 Panel del dispositivo biométrico ZK

Fuente única de datos. Conecta directamente al dispositivo para sincronizar y generar informes.

#### Barra de estado

| Indicador | Significado |
|-----------|-------------|
| ● verde | Dispositivo accesible en la red |
| ● rojo | Dispositivo no responde (apagado, IP incorrecta, fuera de red) |
| ● gris | Verificando o estado desconocido |

También muestra: total de registros en la base de datos local, cantidad de personas, y fecha/hora de la última sincronización.

#### Sincronizar desde el dispositivo

1. Hacer clic en **Sincronizar**.
2. Una barra de progreso mostrará el estado en tiempo real:
   - *Conectando al dispositivo...*
   - *Descargando marcaciones (puede tardar)...*
   - *Procesando y filtrando marcaciones...*
   - *Completado — N registros nuevos guardados.*

La sincronización descarga **todos los registros históricos** del dispositivo. No requiere seleccionar un rango de fechas — el filtro de período se aplica al generar el informe, no al sincronizar.

> **Por qué tarda:** el dispositivo ZK descarga todos sus registros históricos acumulados cada vez que se conecta. La primera vez es la más lenta. Para reducir los tiempos futuros, ver [Limpiar log del dispositivo](#limpiar-log-del-dispositivo).

#### Generar informe

> **Requisito previo:** los horarios del personal deben estar cargados (card azul superior). Sin horarios, el botón **Generar Reporte PDF** queda deshabilitado.

1. En la card **Período del informe**, seleccionar **Fecha inicio** y **Fecha fin**.
2. Elegir el **Tipo de reporte**:
   - `General (todos, por día)` — informe organizado por día; solo incluye personas del archivo de horarios; omite días sin incidencias.
   - `Por persona (una sola)` — historial diario de un empleado con hora programada vs. real; omite días sin incidencias; si no hay ninguna, muestra "Sin novedades".
   - `Por varias personas` — igual que el anterior pero para un subconjunto seleccionado.
3. Si se eligió **Por persona**, seleccionar el empleado en el desplegable.
4. Si se eligió **Por varias personas**, seleccionar los empleados en la lista múltiple (Ctrl+clic para selección múltiple; los botones **Seleccionar todas** / **Deseleccionar todas** agilizan la selección).
5. Opcionalmente, escribir nombres en **Personas a excluir** (separados por coma).
6. Hacer clic en **Generar Reporte PDF**. El archivo se descarga automáticamente.

#### Limpiar log del dispositivo

Esta función **elimina todos los registros de marcaciones del dispositivo ZK** para reducir los tiempos de sincronización futuros. Los datos ya están guardados en la base de datos local.

> **Importante:** solo usar después de haber sincronizado y verificado que los datos están correctos en la base. Esta acción es irreversible.

1. Expandir la sección **Mantenimiento del dispositivo** (al fondo del panel).
2. Hacer clic en **Limpiar log del dispositivo**.
3. Confirmar la acción en el diálogo de confirmación.

Se recomienda hacer esto **una vez al mes**, después del informe mensual.

---

### 6.3 Parámetros fijos del análisis

La lógica de tardanzas usa una **tolerancia fija de 5 minutos** sobre la hora programada de cada persona:

| Retraso | Clasificación |
|---------|--------------|
| 0 min | Puntual — no aparece en el informe |
| 1 – 5 min | Tardanza leve |
| > 5 min | Tardanza severa |

El límite de almuerzo se toma del archivo de horarios de cada persona (0, 30 ó 60 minutos). Estos valores no son configurables desde la UI.

El único parámetro ajustable es **Personas a excluir** — campo de texto visible siempre debajo del selector de modo.

---

### 6.4 Gestión de justificaciones

La página **Justificaciones** permite registrar y administrar los permisos, ausencias y tardanzas justificadas del personal. Los datos cargados aquí son considerados por el motor de análisis al generar cualquier informe PDF.

#### Crear una justificación

1. En la tabla de justificaciones, hacer clic en **Nueva Justificación**.
2. Completar: empleado, fecha, tipo (`ausencia`, `tardanza`, `permiso`, `almuerzo`, `salida_anticipada`, `incompleto`), motivo y aprobador.
3. Para tipos `permiso` y `tardanza`, se puede activar el checkbox **"¿Es recuperable / compensable?"**. Al hacerlo aparecen dos campos obligatorios:
   - **Fecha de recuperación** — día en que se compensarán las horas.
   - **Hora de recuperación** — hora acordada.
   El informe PDF incluirá automáticamente la nota `[RECUPERABLE – se compensará DD/MM/AAAA HH:MM]` junto al motivo.
4. Guardar. La justificación queda en estado **aprobada** por defecto (puede cambiarse a `pendiente` para flujos de aprobación).

#### Editar una justificación existente

1. En cada fila de la tabla aparece el botón de edición (ícono de lápiz).
2. Al pulsarlo, el panel lateral se carga con todos los datos actuales.
3. Modificar los campos necesarios (motivo, horas, recuperable, etc.) y guardar.

#### Cambiar estado de aprobación

El selector de estado en cada fila permite cambiar entre `pendiente`, `aprobada` y `rechazada` sin abrir el formulario completo.

---

### 6.5 Dashboard y alertas

El **Dashboard** (panel principal) muestra al abrirse:

- Estado de sincronización con el dispositivo (último sync, registros totales, personas).
- **Tarjeta de alertas de tardanzas severas:** escanea el mes en curso y lista a las personas que acumulan **3 o más tardanzas severas**. Se calcula de forma asíncrona sin bloquear el resto de la interfaz. Si no hay incidencias, se muestra un mensaje verde confirmando que no hay alertas críticas.

La tarjeta de alertas muestra nombre, ID de usuario y cantidad de tardanzas para cada caso detectado.

---

### 6.6 Envío de informes por email

Desde la página **Reportes**, cuando el modo seleccionado es **"Por persona"**:

1. Seleccionar el empleado y el período.
2. Completar el campo **Correo electrónico de destino**.
3. Hacer clic en **Enviar Informe ahora**.
4. El sistema genera el PDF, lo adjunta al correo, lo envía y elimina el archivo temporal del disco.

Requiere que las variables `SMTP_*` estén configuradas en `.env` (ver [sección 5.1](#51-configurar-gmail-para-el-envío-de-correos)).

---

## 7. Horarios personalizados por persona

El sistema soporta un archivo de horarios individuales (`.obd` o `.ods`) que define la hora de entrada programada de cada persona por día de la semana, y su derecho a almuerzo.

### 7.1 Formato del archivo de horarios

El archivo debe ser un OpenDocument Spreadsheet (`.ods` o `.obd`) con las siguientes columnas en la primera hoja:

| Columna | Tipo | Descripción |
|---------|------|-------------|
| NOMBRES | Texto | Nombre completo del empleado |
| ID | Número | ID del usuario en el dispositivo ZK |
| LUNES (HORA ENTRADA) | Hora o `NO` | Hora programada de llegada el lunes |
| MARTES (HORA ENTRADA) | Hora o `NO` | Hora programada de llegada el martes |
| MIERCOLES (HORA ENTRADA) | Hora o `NO` | Ídem miércoles |
| JUEVES (HORA ENTRADA) | Hora o `NO` | Ídem jueves |
| VIERNES (HORA ENTRADA) | Hora o `NO` | Ídem viernes |
| FIN DE SEMANA (HORA ENTRADA) | Hora o `NO` | Hora de llegada el sábado (domingo no aplica) |
| ALMUERZO (TIENE) | `TRUE` / `FALSE` / `"30 min"` | Derecho a almuerzo |
| NOTAS | Texto | Observaciones libres (opcional) |

**Reglas del archivo:**

| Valor | Efecto |
|-------|--------|
| `NO` en una columna de día | La persona no trabaja ese día — no se genera alerta de tardanza ni ausencia |
| Hora (ej. `7:00:00 AM`) | Hora programada de llegada — la tardanza se mide contra este horario individual |
| `ALMUERZO = TRUE` | 60 minutos de almuerzo permitidos (solo lunes a viernes) |
| `ALMUERZO = FALSE` | Sin derecho a almuerzo — no se analiza el intervalo de almuerzo |
| `ALMUERZO = "30 min"` | 30 minutos de almuerzo permitidos (solo lunes a viernes) |
| Sábado (siempre) | Nunca se analiza almuerzo, independientemente del valor de ALMUERZO |
| Domingo | Nunca genera alertas |

### 7.2 Cómo cargar el archivo de horarios

1. En la card azul **Horarios Personalizados** (parte superior de la página), hacer clic en **Actualizar horarios**.
2. Seleccionar el archivo `.obd` o `.ods`.
3. El sistema parsea el archivo, guarda los horarios en la base de datos y muestra cuántos se cargaron.
4. Si algún ID del archivo no coincide con un usuario del dispositivo ZK, se muestra una advertencia (pero no impide la carga).

Los horarios cargados **persisten entre reinicios** del servidor (se guardan en la base de datos SQLite).

### 7.3 Ver los horarios cargados

Hacer clic en el botón **Ver detalle** (visible cuando hay horarios cargados). Se despliega una tabla con todos los horarios: nombre, ID y hora programada por día.

### 7.4 Efecto en los informes

Los horarios son **obligatorios** para generar cualquier reporte. Las personas sin horario en el archivo no aparecen en ningún tipo de informe, independientemente de si tienen registros en el dispositivo.

**Informe general:** organizado por día; solo incluye a las personas del archivo de horarios. Los días en que nadie tuvo incidencias se omiten del PDF. Si el período completo no tiene novedades, se genera una página única "Sin novedades en el período consultado."

**Informe por persona / por varias personas:** cada empleado muestra en su tabla diaria:
- **Prog.** — la hora programada de llegada para ese día
- **Llegada** — la hora real de llegada según el dispositivo
- Retraso de 1 a 5 min → *Tardanza leve (+Xm sobre HH:MM)*
- Retraso mayor a 5 min → *Tardanza severa (+Xm sobre HH:MM)*
- Día marcado como `NO` en el horario → *Día libre según horario*

Los días sin incidencias no generan fila en la tabla. Si una persona no tuvo ninguna novedad en el período, aparece con el mensaje "Sin novedades registradas en el período consultado."

---

## 8. Gestión y mantenimiento

### Ver logs del contenedor en tiempo real

```bash
docker compose logs -f
```

### Hacer backup de la base de datos

```bash
docker cp rrhh-biometrico:/data/asistencias.db ./backup_$(date +%Y%m%d).db
```

Se recomienda automatizar con un cron job (Linux):

```bash
# Backup diario a las 02:00
0 2 * * * docker cp rrhh-biometrico:/data/asistencias.db /backups/asistencias_$(date +\%Y\%m\%d).db
```

### Restaurar un backup

```bash
docker compose down
docker compose up -d
docker cp ./backup_20260101.db rrhh-biometrico:/data/asistencias.db
docker compose restart
```

### Reiniciar el contenedor

```bash
docker compose restart
```

### Ver espacio usado por el volumen de datos

```bash
docker system df -v | grep db_data
```

### Activar la sincronización automática

Editar `.env` y cambiar:

```ini
SYNC_AUTO=true
SYNC_HORA_NOCTURNA=00:30   # Sync completo cada noche a la 00:30
SYNC_INTERVALO_MIN=30      # Sync parcial cada 30 minutos
```

Luego reiniciar:

```bash
docker compose restart
```

### Rutina mensual recomendada

1. Abrir la aplicación en el navegador.
2. Hacer clic en **Sincronizar** (sincronización completa, sin filtro de fechas).
3. Verificar que la sincronización completó correctamente.
4. En la card **Período del informe**, seleccionar el rango del mes completo.
5. Generar el informe general del mes y verificar que los datos son correctos.
6. Expandir **Mantenimiento del dispositivo** → **Limpiar log del dispositivo** → confirmar.
7. Hacer un backup manual de la base de datos.

---

### 8.1 Respaldos y Carga de Históricos (Fases 2 y 3)

Desde la pestaña de **Respaldos y Históricos** en Configuración, el sistema ahora permite:
*   **Descargar Base de Datos (.db)**: Descarga una copia de seguridad en caliente del archivo SQLite actual.
*   **Descargar Historial completa (CSV)**: Exporta todas las marcaciones existentes para guardado plano.
*   **Importar Históricos (.csv / .xlsx)**: Ingesta de asistencias antiguas de forma asistida. Se requiere que el archivo contenga las columnas `nombre` y `fecha_hora` como mínimo.

> **Backup automático en Limpieza**: Al ejecutar la acción "Limpiar log" desde la zona de peligro en el Dashboard, el sistema genera automáticamente un respaldo pre-limpieza en la máquina para salvaguardar los datos ante cualquier percance.

---

---

## 9. Referencia de la API

### `GET /estado-sync`

Estado del dispositivo y estadísticas de la base de datos.

```bash
curl http://localhost:5000/estado-sync
```

```json
{
  "total_registros": 1842,
  "personas_en_db": 47,
  "ultima_sync": {
    "fecha_sync": "2026-02-24T14:30:00",
    "registros_nuevos": 87,
    "exito": 1,
    "error_detalle": null
  },
  "dispositivo_accesible": true
}
```

---

### `POST /sincronizar`

Inicia una sincronización completa en segundo plano. Retorna un `job_id` para hacer polling.

```bash
curl -X POST http://localhost:5000/sincronizar \
  -H "Content-Type: application/json" \
  -d '{}'
```

```json
{ "job_id": "a3f7c1d2e8b4", "estado": "en_progreso" }
```

El body puede incluir `fecha_inicio` y `fecha_fin` (formato `YYYY-MM-DD`) para restringir el rango de registros guardados en la DB, pero en uso normal se recomienda no filtrar y dejar que el sistema descargue todo.

---

### `GET /sync-status/<job_id>`

Estado de un job de sincronización en curso.

| `estado` | Descripción |
|----------|-------------|
| `conectando` | Estableciendo conexión con el dispositivo |
| `obteniendo_usuarios` | Descargando lista de usuarios |
| `descargando_marcaciones` | Descargando registros de asistencia |
| `procesando` | Filtrando y transformando registros |
| `completado` | Finalizado con éxito |
| `error` | Falló — ver campo `detalle` |

---

### `GET /personas-db`

Personas con registros en la base de datos para un rango de fechas.

```bash
curl "http://localhost:5000/personas-db?fecha_inicio=2026-01-01&fecha_fin=2026-01-31"
```

---

### `POST /generar-desde-db`

Genera un PDF usando datos de la base de datos local. Requiere que haya horarios cargados; retorna 400 si no los hay.

**Campos del body:**

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `fecha_inicio` | `"YYYY-MM-DD"` | Sí | Inicio del período |
| `fecha_fin` | `"YYYY-MM-DD"` | Sí | Fin del período |
| `modo` | `"general"` \| `"persona"` \| `"varias"` | No (default `"general"`) | Tipo de reporte |
| `persona` | `string` | Sí si `modo == "persona"` | Nombre exacto del empleado |
| `personas` | `string[]` | Sí si `modo == "varias"` | Lista de nombres de empleados |
| `excluidos` | `string[]` | No | Personas a excluir del análisis |

**Ejemplos:**

```bash
# Reporte general
curl -X POST http://localhost:5000/generar-desde-db \
  -H "Content-Type: application/json" \
  -d '{"fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31", "modo": "general"}'

# Reporte por una persona
curl -X POST http://localhost:5000/generar-desde-db \
  -H "Content-Type: application/json" \
  -d '{"fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31", "modo": "persona", "persona": "PEREZ GARCIA JUAN"}'

# Reporte por varias personas
curl -X POST http://localhost:5000/generar-desde-db \
  -H "Content-Type: application/json" \
  -d '{"fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31", "modo": "varias", "personas": ["PEREZ GARCIA JUAN", "LOPEZ TORRES ANA"]}'
```

---

### `POST /cargar-horarios`

Carga un archivo `.obd` o `.ods` de horarios personalizados.

```bash
curl -X POST http://localhost:5000/cargar-horarios \
  -F "archivo=@horarios_personal_ingreso.obd"
```

```json
{
  "success": true,
  "total_cargados": 83,
  "sin_match_zk": [],
  "fuente": "horarios_personal_ingreso.obd"
}
```

El campo `sin_match_zk` lista los IDs del archivo que no se encontraron en el dispositivo ZK (advertencia, no error).

---

### `GET /estado-horarios`

Estado actual de los horarios cargados.

```bash
curl http://localhost:5000/estado-horarios
```

```json
{
  "total": 83,
  "fuente": "horarios_personal_ingreso.obd",
  "actualizado_en": "2026-02-24 10:30:00"
}
```

---

### `GET /horarios`

Lista completa de horarios por persona.

```bash
curl http://localhost:5000/horarios
```

---

### `POST /limpiar-dispositivo`

Borra todos los registros de asistencia del dispositivo ZK.

```bash
curl -X POST http://localhost:5000/limpiar-dispositivo \
  -H "Content-Type: application/json" \
  -d '{"confirmar": true}'
```

```json
{ "success": true, "registros_borrados": 15420 }
```

> Sin `"confirmar": true` el endpoint retorna error 400.

---

### `GET /api/justificaciones`

Lista todas las justificaciones. Acepta parámetros opcionales `fecha_inicio` y `fecha_fin` (formato `YYYY-MM-DD`).

```bash
curl "http://localhost:5000/api/justificaciones?fecha_inicio=2026-03-01&fecha_fin=2026-03-31"
```

---

### `POST /api/justificaciones`

Crea una nueva justificación.

**Campos del body:**

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `id_usuario` | string | Sí | ID del usuario en el dispositivo ZK |
| `nombre` | string | Sí | Nombre del empleado |
| `fecha` | `"YYYY-MM-DD"` | Sí | Fecha de la novedad |
| `tipo` | string | Sí | `ausencia`, `tardanza`, `permiso`, `almuerzo`, `salida_anticipada`, `incompleto` |
| `motivo` | string | No | Descripción libre |
| `aprobado_por` | string | No | Nombre del responsable que aprueba |
| `hora_permitida` | `"HH:MM"` | No | Hora de llegada autorizada (para tardanzas justificadas) |
| `estado` | string | No | `aprobada` (default), `pendiente`, `rechazada` |
| `recuperable` | int (0/1) | No | 1 si la novedad será compensada en otra fecha |
| `fecha_recuperacion` | `"YYYY-MM-DD"` | Condicional | Obligatorio si `recuperable=1` |
| `hora_recuperacion` | `"HH:MM"` | Condicional | Obligatorio si `recuperable=1` |

---

### `GET /api/justificaciones/<id>`

Retorna todos los campos de una justificación por su ID.

```bash
curl http://localhost:5000/api/justificaciones/42
```

---

### `PUT /api/justificaciones/<id>`

Actualiza todos los campos editables de una justificación existente. Acepta los mismos campos que el `POST`.

```bash
curl -X PUT http://localhost:5000/api/justificaciones/42 \
  -H "Content-Type: application/json" \
  -d '{"motivo": "Consulta médica urgente", "recuperable": 1, "fecha_recuperacion": "2026-03-20", "hora_recuperacion": "17:00"}'
```

---

### `PATCH /api/justificaciones/<id>`

Cambia únicamente el campo `estado` (`aprobada`, `pendiente`, `rechazada`).

```bash
curl -X PATCH http://localhost:5000/api/justificaciones/42 \
  -H "Content-Type: application/json" \
  -d '{"estado": "aprobada"}'
```

---

### `DELETE /api/justificaciones/<id>`

Elimina una justificación por su ID.

```bash
curl -X DELETE http://localhost:5000/api/justificaciones/42
```

---

### `GET /api/alertas/tardanzas-severas`

Retorna la lista de personas con 3 o más tardanzas severas en el mes indicado.

**Parámetros:** `anio` (default: año actual), `mes` (default: mes actual).

```bash
curl "http://localhost:5000/api/alertas/tardanzas-severas?anio=2026&mes=3"
```

```json
{
  "alertas": [
    {
      "nombre": "PEREZ GARCIA JUAN",
      "id_usuario": "42",
      "conteo": 4,
      "fechas": ["2026-03-03", "2026-03-10", "2026-03-17", "2026-03-24"]
    }
  ]
}
```

Si no hay horarios cargados, retorna `{ "alertas": [], "warning": "No hay horarios cargados" }`.

---

### `POST /api/enviar-informe`

Genera el informe PDF de una persona y lo envía por correo electrónico. Requiere variables `SMTP_*` en `.env`.

**Campos del body:**

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `fecha_inicio` | `"YYYY-MM-DD"` | Sí | Inicio del período |
| `fecha_fin` | `"YYYY-MM-DD"` | Sí | Fin del período |
| `persona` | string | Sí | Nombre exacto del empleado |
| `email` | string | Sí | Correo electrónico de destino |

```bash
curl -X POST http://localhost:5000/api/enviar-informe \
  -H "Content-Type: application/json" \
  -d '{"fecha_inicio": "2026-03-01", "fecha_fin": "2026-03-31", "persona": "PEREZ GARCIA JUAN", "email": "jperez@istpet.edu.ec"}'
```

```json
{ "success": true, "mensaje": "Informe enviado a jperez@istpet.edu.ec" }
```

---

### `GET /api/backup/descargar`

Descarga el archivo `.db` de la base de datos actual en caliente para respaldo.

---

### `GET /api/backup/csv`

Exporta todas las marcaciones vigentes en la base de datos a un archivo de formato CSV plano.

---

### `POST /api/historicos/importar`

Permite la ingesta de marcaciones históricas desde archivos de hoja de cálculo.

**Campos del request:**
*   `archivo` (Form-data / File): Archivo de formato `.csv` o `.xlsx`.

Debe contener como mínimo las columnas `nombre` y `fecha_hora`.

---

---

## 10. Solución de problemas

### El dispositivo aparece como "no accesible"

Seguir este orden:

1. **Verificar IP** — comprobar en la pantalla del dispositivo: `Menú → Opciones → Comunicación`.

2. **Probar conectividad desde la máquina host** (no desde el contenedor):
   ```bash
   ping 192.168.X.X
   nc -zv -w 3 192.168.X.X 4370   # Linux
   ```
   En Windows: `Test-NetConnection -ComputerName IP_ZK -Port 4370`

3. **Verificar la contraseña del dispositivo** — si el puerto responde pero la app no conecta, el error suele ser de autenticación (`ZK_PASSWORD` incorrecto). Confirmarlo en `Menú → Opciones → Comunicación → Contraseña del dispositivo` y actualizar `.env`. La contraseña de fábrica es `0`, pero muchos equipos la tienen modificada.

4. **Probar con UDP:** `ZK_UDP=true` en `.env` y `docker compose restart`.

5. **Una sola conexión simultánea:** si el software del fabricante está abierto, cerrarlo.

---

### La sincronización falla con "Error de conexión"

El dispositivo ZK admite **una sola conexión a la vez**. Si el software del fabricante u otra instancia está conectada, la conexión fallará. Esperar unos segundos y reintentar.

---

### La sincronización es muy lenta

El tiempo depende de cuántos registros históricos tenga el dispositivo acumulados. El protocolo ZK descarga **todos** los registros en cada sync; no permite filtrar por fecha en el dispositivo.

Referencia orientativa: ~8 500 registros (170 usuarios, varios meses) tarda unos 20 segundos en red local.

**Solución permanente:** sync completo → verificar datos → limpiar log del dispositivo. Las sincronizaciones posteriores serán casi instantáneas porque habrá pocos registros acumulados.

**Mejora rápida sin limpiar:** activar UDP en `.env`:
```ini
ZK_UDP=true
```
UDP es entre 20% y 40% más rápido en redes locales.

---

### El informe no muestra a ciertas personas

El sistema solo analiza a las personas presentes en el **archivo de horarios cargado**. Las personas del dispositivo que no estén en ese archivo se omiten en todos los modos de reporte.

Si falta algún empleado, verificar que está incluido en el archivo de horarios (nombre o ID) y volver a importarlo.

---

### El PDF se genera vacío o con pocos datos

Verificar que el rango de fechas del formulario coincide con el período sincronizado. Confirmar qué personas hay en la base:

```bash
curl "http://localhost:5000/personas-db?fecha_inicio=YYYY-MM-DD&fecha_fin=YYYY-MM-DD"
```

---

### La aplicación no arranca en Docker

```bash
docker compose logs rrhh-app
```

Causas comunes:
- El archivo `.env` no existe o tiene variables mal formateadas (espacios alrededor del `=`).
- El puerto 5000 ya está en uso. En Linux: `sudo ss -tlnp | grep 5000`. En Windows: `netstat -ano | findstr :5000`.

---

### El correo de informe no se envía

| Error | Causa probable | Solución |
|-------|---------------|----------|
| `535 Authentication Failed` | Credenciales incorrectas o Gmail requiere App Password | Generar una Contraseña de Aplicación (ver [sección 5.1](#51-configurar-gmail-para-el-envío-de-correos)) |
| `Connection refused` / timeout | Puerto 587 o 465 bloqueado por firewall o ISP | Probar cambiando `SMTP_PORT` entre `587` y `465`; verificar con el administrador de red |
| Correo llega a SPAM | El dominio emisor no tiene SPF/DKIM configurado | Usar un correo institucional o verificar con el área de IT |
| Variables SMTP no cargadas | `.env` no tiene las variables o el contenedor no fue reiniciado | Agregar variables y ejecutar `docker compose restart` |

---

### Instrucciones de instalación detalladas por sistema operativo

Ver **[DESPLIEGUE.md](DESPLIEGUE.md)** para guías paso a paso en:
- Linux escritorio (Ubuntu, Mint, Fedora)
- Linux servidor (headless, con SSH)
- Windows 10 / 11 con Docker Desktop

---

*Sistema de Informes Biométricos — RRHH ISTPET*
