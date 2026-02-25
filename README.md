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
│   └── index.html          # Interfaz web de una sola página
├── static/
│   └── style.css           # Estilos de la UI
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
ZK_PASSWORD=XXXX           # Contraseña numérica del dispositivo (ver pantalla del equipo)
ZK_TIMEOUT=5               # Segundos de espera para conectar
ZK_UDP=false               # true = protocolo UDP (más rápido, probar primero)

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
```

### Generar una `FLASK_SECRET_KEY` segura

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Cómo encontrar la contraseña del dispositivo ZK

La contraseña del dispositivo (`ZK_PASSWORD`) se configura en `Menú → Opciones → Comunicación` en la pantalla del equipo. Si nunca se configuró, el valor predeterminado es `0`.

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

1. Seleccionar **Fecha inicio** y **Fecha fin** del período a sincronizar.
2. Hacer clic en **Sincronizar**.
3. Una barra de progreso mostrará el estado en tiempo real:
   - *Conectando al dispositivo...*
   - *Descargando marcaciones (puede tardar)...*
   - *Procesando y filtrando marcaciones...*
   - *Completado — N registros nuevos guardados.*

> **Por qué tarda:** el dispositivo ZK descarga todos sus registros históricos acumulados cada vez que se conecta. La primera vez es la más lenta. Para reducir los tiempos futuros, ver [Limpiar log del dispositivo](#limpiar-log-del-dispositivo).

#### Generar informe

1. Seleccionar las fechas del período.
2. Elegir el **Tipo de reporte**:
   - `General (todos los días)` — un informe con todos los días del período. Si hay horarios cargados, **solo incluye a las personas del archivo de horarios**.
   - `Por persona` — un informe con una sección por cada empleado mostrando su historial diario con la hora programada de llegada.
3. Si se seleccionó "Por persona", elegir en el selector **Todas** las personas o una específica.
4. Expandir **Configuración avanzada** si se necesita ajustar parámetros (opcional).
5. Hacer clic en **Generar Reporte PDF**. El archivo se descarga automáticamente.

#### Limpiar log del dispositivo

Esta función **elimina todos los registros de marcaciones del dispositivo ZK** para reducir los tiempos de sincronización futuros. Los datos ya están guardados en la base de datos local.

> **Importante:** solo usar después de haber sincronizado y verificado que los datos están correctos en la base. Esta acción es irreversible.

1. Expandir la sección **Mantenimiento del dispositivo** (al fondo del panel).
2. Hacer clic en **Limpiar log del dispositivo**.
3. Confirmar la acción en el diálogo de confirmación.

Se recomienda hacer esto **una vez al mes**, después del informe mensual.

---

### 6.3 Configuración avanzada del reporte

Disponible expandiendo el panel **Configuración avanzada**.

Estos valores son los **umbrales globales por defecto**. Si hay horarios personalizados cargados, estos umbrales solo aplican a personas que NO estén en el archivo de horarios.

| Campo | Valor por defecto | Descripción |
|-------|------------------|-------------|
| Tardanza Leve | `08:00` | Hora a partir de la cual se reporta tardanza leve |
| Tardanza Severa | `08:05` | Hora a partir de la cual se reporta tardanza severa |
| Max. Almuerzo (min) | `60` | Minutos máximos de almuerzo antes de reportar exceso |
| Personas a excluir | *(vacío)* | Nombres separados por coma — excluye personas del análisis |

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

**Informe general:** cuando hay horarios cargados, el informe solo incluye a las personas presentes en el archivo de horarios. Las personas del dispositivo que no estén en el archivo se omiten.

**Informe por persona:** cada empleado muestra en su tabla diaria:
- **Prog.** — la hora programada de llegada para ese día
- **Llegada** — la hora real de llegada según el dispositivo
- Si la diferencia es de 1 a 5 minutos → *Tardanza leve (+Xm sobre HH:MM)*
- Si la diferencia es mayor a 5 minutos → *Tardanza severa (+Xm sobre HH:MM)*
- Si el día está marcado como `NO` → *Día libre según horario*

**Compatibilidad:** si no se cargan horarios, el sistema funciona exactamente igual que antes, usando los umbrales globales para todos.

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
2. Seleccionar el rango del mes completo y hacer clic en **Sincronizar**.
3. Verificar que la sincronización completó correctamente.
4. Generar el informe general del mes y verificar que los datos son correctos.
5. Expandir **Mantenimiento del dispositivo** → **Limpiar log del dispositivo** → confirmar.
6. Hacer un backup manual de la base de datos.

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

Inicia una sincronización en segundo plano. Retorna un `job_id` para hacer polling.

```bash
curl -X POST http://localhost:5000/sincronizar \
  -H "Content-Type: application/json" \
  -d '{"fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31"}'
```

```json
{ "job_id": "a3f7c1d2e8b4", "estado": "en_progreso" }
```

Si no se envían fechas, sincroniza todos los registros desde 2000-01-01 hasta hoy.

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

Genera un PDF usando datos de la base de datos local.

```bash
curl -X POST http://localhost:5000/generar-desde-db \
  -H "Content-Type: application/json" \
  -d '{
    "fecha_inicio": "2026-01-01",
    "fecha_fin": "2026-01-31",
    "modo": "general",
    "persona": "TODAS",
    "tardanza_leve": "08:00",
    "tardanza_severa": "08:05",
    "max_almuerzo_min": 60,
    "excluidos": []
  }'
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

## 10. Solución de problemas

### El dispositivo aparece como "no accesible"

1. Verificar que la máquina y el dispositivo están en la misma red local.
2. Comprobar la IP del dispositivo en `Menú → Opciones → Comunicación`.
3. Probar conectividad básica desde la máquina host (no desde el contenedor):
   ```bash
   ping 192.168.X.X
   ```
4. Si el ping responde pero la app no conecta, probar UDP: `ZK_UDP=true` en `.env` y reiniciar.

---

### La sincronización falla con "Error de conexión"

El dispositivo ZK admite **una sola conexión a la vez**. Si el software del fabricante u otra instancia está conectada, la conexión fallará. Esperar unos segundos y reintentar.

---

### La sincronización es muy lenta

El tiempo depende de cuántos registros históricos tenga el dispositivo acumulados.

**Solución permanente:** sync completo → verificar datos → limpiar log del dispositivo. Las sincronizaciones posteriores serán casi instantáneas.

**Mejora rápida sin limpiar:** activar UDP en `.env`:
```ini
ZK_UDP=true
```
UDP es entre 20% y 40% más rápido en redes locales.

---

### El informe general no muestra a todas las personas

Si hay horarios cargados, el informe general solo incluye a las personas presentes en el archivo de horarios. Las personas del dispositivo que no estén en ese archivo se omiten intencionalmente.

Para incluir a todos independientemente, generar el informe en modo **Por persona**, que no aplica este filtro.

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

### Instrucciones de instalación detalladas por sistema operativo

Ver **[DESPLIEGUE.md](DESPLIEGUE.md)** para guías paso a paso en:
- Linux escritorio (Ubuntu, Mint, Fedora)
- Linux servidor (headless, con SSH)
- Windows 10 / 11 con Docker Desktop

---

*Sistema de Informes Biométricos — RRHH ISTPET*
