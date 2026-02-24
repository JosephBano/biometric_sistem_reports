# Sistema de Informes Biométricos — RRHH ISTPET

Aplicación web para generar informes PDF de asistencia del personal a partir del sistema de control biométrico ZK. Permite obtener los datos directamente del dispositivo en red o mediante la carga manual de un archivo exportado `.xlsx`.

---

## Tabla de contenidos

1. [Requisitos](#1-requisitos)
2. [Estructura del proyecto](#2-estructura-del-proyecto)
3. [Instalación — modo desarrollo (sin Docker)](#3-instalación--modo-desarrollo-sin-docker)
4. [Instalación — modo producción (Docker)](#4-instalación--modo-producción-docker)
5. [Configuración del archivo `.env`](#5-configuración-del-archivo-env)
6. [Uso de la interfaz web](#6-uso-de-la-interfaz-web)
7. [Uso por línea de comandos (script directo)](#7-uso-por-línea-de-comandos-script-directo)
8. [Gestión y mantenimiento](#8-gestión-y-mantenimiento)
9. [Referencia de la API](#9-referencia-de-la-api)
10. [Solución de problemas](#10-solución-de-problemas)

---

## 1. Requisitos

### Para modo desarrollo (sin Docker)

| Requisito | Versión mínima |
|-----------|---------------|
| Python | 3.12 |
| LibreOffice | Cualquiera reciente (solo para archivos `.xls` binarios antiguos) |
| Acceso a la red local donde está el dispositivo ZK | — |

**Instalar LibreOffice en Ubuntu/Debian:**
```bash
sudo apt install libreoffice-calc
```

### Para modo producción (Docker)

| Requisito | Versión mínima |
|-----------|---------------|
| Docker Engine | 24.x |
| Docker Compose | v2 (`docker compose`, no `docker-compose`) |
| Sistema operativo del servidor | Linux (requerido para `network_mode: host`) |
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
│
├── requirements.txt        # Dependencias Python
│
└── data/                   # Creado automáticamente en runtime
    ├── asistencias.db      # Base de datos SQLite (persistida en Docker volume)
    ├── uploads/            # Archivos subidos temporalmente (TTL: 15 min)
    └── reports/            # PDFs generados temporalmente (TTL: 15 min)
```

---

## 3. Instalación — modo desarrollo (sin Docker)

Este modo es para desarrollo local o para correr el sistema directamente en la máquina sin contenedor.

### Paso 1 — Clonar o descargar el proyecto

```bash
cd /ruta/donde/quieras/instalar
# Si usas git:
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

> **Nota en modo desarrollo:** las rutas de datos (`DB_PATH`, `UPLOAD_FOLDER`, `REPORTS_FOLDER`) apuntan por defecto a `data/` dentro del directorio del proyecto. No es necesario cambiarlas para desarrollo local.

### Paso 5 — Iniciar el servidor

```bash
# Con Flask en modo desarrollo (recomendado solo para desarrollo)
python app.py

# O con gunicorn (más cercano a producción)
gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --timeout 120 app:app
```

El servidor queda disponible en `http://localhost:5000`.

---

## 4. Instalación — modo producción (Docker)

Esta es la forma recomendada para un servidor permanente dentro de la red del instituto.

### Paso 1 — Crear el archivo de configuración

```bash
cp .env.example .env
```

Editar `.env` con los datos reales (ver [sección 5](#5-configuración-del-archivo-env)).

### Paso 2 — Construir e iniciar el contenedor

```bash
docker compose up -d --build
```

Este comando:
- Construye la imagen Docker (descarga Python, instala LibreOffice y las dependencias)
- Crea el volumen `db_data` para persistencia de la base de datos
- Inicia el contenedor en segundo plano

> **Primera vez:** la construcción tarda varios minutos porque descarga e instala LibreOffice. Las veces siguientes es mucho más rápido gracias al cache de capas Docker.

### Paso 3 — Verificar que el contenedor está corriendo

```bash
docker compose ps
```

La columna `Status` debe mostrar `Up`. El sistema queda disponible en `http://IP_DEL_SERVIDOR:5000`.

### Actualizar a una nueva versión del código

```bash
# Reconstruir la imagen con los cambios nuevos
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

Copiar el resultado y pegarlo como valor de `FLASK_SECRET_KEY`.

### Cómo encontrar la contraseña del dispositivo ZK

La contraseña del dispositivo (`ZK_PASSWORD`) se configura en el menú del equipo físico, en `Menú → Opciones → Comunicación`. Si nunca se configuró, el valor predeterminado es `0`.

---

## 6. Uso de la interfaz web

Abrir el navegador en `http://IP_SERVIDOR:5000`.

### 6.1 Tab "Dispositivo Biométrico ZK"

Este es el flujo principal. Conecta directamente al dispositivo para obtener los datos.

#### Barra de estado

Al cargar la página se muestra automáticamente:

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

#### Generar informe desde la base de datos

Una vez sincronizado (o si la base ya tiene datos), configurar y generar el informe:

1. Seleccionar las fechas del período (pueden ser distintas al rango de sync).
2. En la sección inferior, elegir el **Tipo de reporte**:
   - `General (todos los días)` — un informe con todos los días del período, análisis de tardanzas y excesos de almuerzo
   - `Por persona` — un informe con una sección por cada empleado mostrando su historial diario
3. Si se seleccionó "Por persona", elegir en el selector si se quieren **Todas** las personas o una específica.
4. Expandir **Configuración avanzada** si se necesita ajustar parámetros (opcional).
5. Hacer clic en **Generar Reporte PDF**. El archivo se descarga automáticamente.

#### Limpiar log del dispositivo

Esta función **elimina todos los registros de marcaciones del dispositivo ZK** para reducir los tiempos de sincronización futuros. Los datos ya están guardados en la base de datos local.

> **Importante:** solo usar después de haber sincronizado y verificado que los datos están correctos en la base. Esta acción es irreversible.

1. Expandir la sección **Mantenimiento del dispositivo** (al fondo del panel ZK).
2. Hacer clic en **Limpiar log del dispositivo**.
3. Confirmar la acción en el diálogo de confirmación.

Se recomienda hacer esto **una vez al mes**, después del informe mensual.

---

### 6.2 Tab "Subir archivo .xlsx"

Este flujo permite generar informes a partir de un archivo exportado manualmente desde el dispositivo. Útil como respaldo si el dispositivo no está en red, o para importar datos históricos.

1. Arrastrar el archivo `.xls`, `.xlsx` o `.csv` a la zona de carga, o hacer clic para buscarlo.
2. El sistema procesa el archivo y detecta automáticamente las personas.
3. Configurar el tipo de reporte y las opciones (mismo proceso que en el flujo ZK).
4. Hacer clic en **Generar Reporte PDF**.

> Los archivos subidos se eliminan automáticamente a los 15 minutos.

---

### 6.3 Configuración avanzada del reporte

Disponible en ambos flujos expandiendo el panel **Configuración avanzada**:

| Campo | Valor por defecto | Descripción |
|-------|------------------|-------------|
| Tardanza Leve | `08:00` | Hora a partir de la cual se reporta tardanza leve |
| Tardanza Severa | `08:05` | Hora a partir de la cual se reporta tardanza severa |
| Max. Almuerzo (min) | `60` | Minutos máximos de almuerzo antes de reportar exceso |
| Personas a excluir | *(vacío)* | Nombres separados por coma — excluye personas del análisis |

---

## 7. Uso por línea de comandos (script directo)

El script puede ejecutarse directamente sin la interfaz web.

```bash
# Activar el entorno virtual primero
source .venv/bin/activate

# Reporte general (todos los días del archivo)
python script.py REPORTEBIOMETRICOENERO2026.xlsx

# Reporte por persona (todas las personas)
python script.py REPORTEBIOMETRICOENERO2026.xlsx --modo persona

# Reporte de una persona específica
python script.py REPORTEBIOMETRICOENERO2026.xlsx --modo persona --persona "JUAN PEREZ"

# Solo el día 15 del mes
python script.py REPORTEBIOMETRICOENERO2026.xlsx --fecha 15

# Cambiar horarios y excluir personas
python script.py REPORTEBIOMETRICOENERO2026.xlsx \
    --tardanza1 07:55 \
    --tardanza2 08:00 \
    --almuerzo 45 \
    --excluir "DIRECTOR" "CONSERJE"

# Especificar nombre del archivo de salida
python script.py REPORTEBIOMETRICOENERO2026.xlsx --salida informe_enero.pdf
```

**Todos los argumentos disponibles:**

| Argumento | Descripción | Ejemplo |
|-----------|-------------|---------|
| `archivo` | Archivo de entrada (obligatorio) | `REPORTE.xlsx` |
| `--modo` | `general` o `persona` | `--modo persona` |
| `--persona` | Nombre exacto (solo si `--modo persona`) | `--persona "JUAN PEREZ"` |
| `--tardanza1` | Hora de tardanza leve (HH:MM) | `--tardanza1 07:55` |
| `--tardanza2` | Hora de tardanza severa (HH:MM) | `--tardanza2 08:05` |
| `--almuerzo` | Minutos máximos de almuerzo | `--almuerzo 45` |
| `--excluir` | Nombres a excluir | `--excluir "JUAN" "MARIA"` |
| `--fecha` | Solo analizar este día del mes | `--fecha 15` |
| `--salida` | Nombre del PDF de salida | `--salida informe.pdf` |

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

Se recomienda automatizar este backup con un cron job en el servidor:

```bash
# Backup diario a las 02:00
0 2 * * * docker cp rrhh-biometrico:/data/asistencias.db /backups/asistencias_$(date +\%Y\%m\%d).db
```

### Restaurar un backup

```bash
# Detener el contenedor
docker compose down

# Copiar el backup al volumen
# Primero iniciar el contenedor para que el volumen sea accesible
docker compose up -d

# Copiar la DB al contenedor
docker cp ./backup_20260101.db rrhh-biometrico:/data/asistencias.db

# Reiniciar para que la app tome los datos nuevos
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

Con `SYNC_AUTO=true`, el sistema sincroniza automáticamente y la base de datos siempre estará actualizada. Los informes se pueden generar en cualquier momento sin necesidad de hacer sync manual.

### Rutina mensual recomendada

Al final de cada mes:

1. Abrir la aplicación en el navegador.
2. En la pestaña **Dispositivo ZK**, seleccionar el rango del mes completo y hacer clic en **Sincronizar**.
3. Verificar que la sincronización completó correctamente (registros nuevos guardados).
4. Generar el informe general del mes y verificar que los datos son correctos.
5. Expandir **Mantenimiento del dispositivo** → **Limpiar log del dispositivo** → confirmar.
6. Hacer un backup manual de la base de datos.

---

## 9. Referencia de la API

Todos los endpoints son consumidos por la interfaz web. También pueden usarse directamente con herramientas como `curl` o Postman.

### `GET /estado-sync`

Retorna el estado del dispositivo y estadísticas de la base de datos.

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
{
  "job_id": "a3f7c1d2e8b4",
  "estado": "en_progreso"
}
```

Si no se envían fechas, sincroniza todos los registros desde 2000-01-01 hasta hoy.

---

### `GET /sync-status/<job_id>`

Consulta el estado de un job de sincronización en curso.

```bash
curl http://localhost:5000/sync-status/a3f7c1d2e8b4
```

**Estados posibles:**

| `estado` | Descripción |
|----------|-------------|
| `conectando` | Estableciendo conexión con el dispositivo |
| `obteniendo_usuarios` | Descargando lista de usuarios del dispositivo |
| `descargando_marcaciones` | Descargando registros de asistencia |
| `procesando` | Filtrando y transformando registros |
| `completado` | Finalizado con éxito |
| `error` | Falló — ver campo `detalle` |

```json
{
  "estado": "completado",
  "registros_procesados": 1240,
  "total_dispositivo": 1240,
  "registros_nuevos": 87
}
```

---

### `GET /personas-db`

Retorna la lista de personas que tienen registros en la base de datos para un rango de fechas.

```bash
curl "http://localhost:5000/personas-db?fecha_inicio=2026-01-01&fecha_fin=2026-01-31"
```

```json
{
  "personas": ["GARCIA LOPEZ MARIA", "PEREZ JUAN", "RODRIGUEZ ANA"]
}
```

---

### `POST /generar-desde-db`

Genera un PDF usando los datos almacenados en la base de datos local.

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

```json
{
  "success": true,
  "download_url": "/descargar/reporte_a1b2c3d4.pdf",
  "filename": "Reporte_Biometrico_General_DB.pdf"
}
```

El PDF se descarga desde `GET /descargar/<filename>`.

---

### `POST /subir`

Sube un archivo `.xls`, `.xlsx` o `.csv` para el flujo manual.

```bash
curl -X POST http://localhost:5000/subir \
  -F "archivo=@REPORTEBIOMETRICOENERO2026.xlsx"
```

```json
{
  "success": true,
  "file_id": "uuid_filename.xlsx",
  "original_name": "REPORTEBIOMETRICOENERO2026.xlsx",
  "personas": ["GARCIA LOPEZ MARIA", "PEREZ JUAN"]
}
```

---

### `POST /generar`

Genera un PDF a partir de un archivo previamente subido con `/subir`.

```bash
curl -X POST http://localhost:5000/generar \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "uuid_filename.xlsx",
    "original_name": "REPORTEBIOMETRICOENERO2026.xlsx",
    "modo": "general",
    "persona": "TODAS",
    "tardanza_leve": "08:00",
    "tardanza_severa": "08:05",
    "max_almuerzo_min": 60,
    "excluidos": []
  }'
```

---

### `POST /limpiar-dispositivo`

Borra todos los registros de asistencia almacenados en el dispositivo ZK.

```bash
curl -X POST http://localhost:5000/limpiar-dispositivo \
  -H "Content-Type: application/json" \
  -d '{"confirmar": true}'
```

```json
{
  "success": true,
  "registros_borrados": 15420
}
```

> Sin `"confirmar": true` el endpoint retorna error 400 y no ejecuta ninguna acción.

---

## 10. Solución de problemas

### El dispositivo aparece como "no accesible"

1. Verificar que el servidor y el dispositivo están en la misma red local.
2. Comprobar la IP del dispositivo en `Menú → Opciones → Comunicación` en la pantalla del equipo.
3. Probar conectividad básica desde el servidor:
   ```bash
   ping 192.168.X.X
   ```
4. Verificar que el puerto 4370 no está bloqueado por un firewall:
   ```bash
   nc -zv 192.168.X.X 4370
   ```
5. Si el contenedor Docker usa `network_mode: host`, verificar que el host tiene acceso a esa IP (no solo el contenedor).

---

### La sincronización falla con "Error de conexión"

- El dispositivo ZK solo admite **una conexión a la vez**. Si otra aplicación está conectada (el software del fabricante, otra instancia del sistema), la conexión fallará.
- Esperar unos segundos y reintentar. Si persiste, reiniciar el dispositivo.

---

### La sincronización es muy lenta

El tiempo depende de cuántos registros históricos tenga acumulados el dispositivo. Con años de datos puede tomar varios minutos.

**Solución permanente:** hacer un sync completo, verificar los datos, y luego limpiar el log del dispositivo (ver [rutina mensual](#rutina-mensual-recomendada)). Después de limpiar, los syncs futuros serán casi instantáneos.

**Mejora rápida sin limpiar:** activar UDP en `.env`:
```ini
ZK_UDP=true
```
Reiniciar el contenedor y probar. UDP es entre 20% y 40% más rápido en redes locales.

---

### El PDF se genera vacío o con pocos datos

- Si se usa el flujo ZK: verificar que el rango de fechas en el formulario coincide con el rango que fue sincronizado.
- Si se usa el flujo de archivo: verificar que el archivo exportado contiene datos del período seleccionado.
- Llamar a `GET /personas-db?fecha_inicio=YYYY-MM-DD&fecha_fin=YYYY-MM-DD` para confirmar qué datos hay en la base.

---

### Error "Archivo expiró" al generar desde archivo subido

Los archivos subidos tienen un TTL de 15 minutos. Subir el archivo de nuevo y generar el informe sin demora.

---

### La aplicación no arranca en Docker

Ver los logs para diagnosticar:
```bash
docker compose logs rrhh-app
```

Causas comunes:
- El archivo `.env` no existe o tiene variables mal formateadas.
- El puerto 5000 ya está en uso por otro proceso en el host (con `network_mode: host`).
  ```bash
  sudo ss -tlnp | grep 5000
  ```
- Error al construir la imagen (falta de espacio en disco, problema de red).

---

### Instalar Docker en Ubuntu (si no está instalado)

```bash
# Remover versiones antiguas
sudo apt remove docker docker-engine docker.io containerd runc

# Instalar dependencias
sudo apt update
sudo apt install ca-certificates curl gnupg

# Agregar repositorio oficial de Docker
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Instalar Docker Engine y Compose plugin
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Permitir usar Docker sin sudo (requiere cerrar y abrir sesión)
sudo usermod -aG docker $USER
```

---

*Sistema de Informes Biométricos — RRHH ISTPET*
